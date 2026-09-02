"""Netzwerk-Capture: haelt fest, wie die Antwort aussieht, WENN etwas frei ist.

Eigenstaendiges Skript neben dem Booker - es bucht nichts und aendert nichts an
der Konfiguration. Es benutzt die vorhandenen Bausteine des Projekts (Proxies,
Login-Session, Request-Header, Timeouts), damit die Anfrage byte-gleich zu der
ist, die der Booker sendet.

Unterschied zum Booker: KEIN Monatsfenster, KEIN Mindestabstand. Es wird der
komplette buchbare Horizont in einem Call abgefragt und JEDER freie Termin
gezaehlt - egal in welchem Monat er liegt. Sobald etwas frei ist, landen die
rohe Anfrage und die vollstaendige Server-Antwort in captures/.

  python netcapture.py                 # Login + Dauerlauf
  python netcapture.py --no-login      # nur anonymer Scan
  python netcapture.py --stop-on-first # nach dem ersten Fund beenden
"""

import argparse
import getpass
import json
import os
import signal
import time
from datetime import timedelta

from booker import capture as capture_mod
from booker import httpclient
from booker import state
from booker.captcha import solve_captcha_from_html
from booker.config import BASE_URL, BOOK_URL, RP_ID, TOKEN, load_config
from booker.dates import nicosia_dt, nicosia_now
from booker.login import create_login_session, session_is_logged_in
from booker.proxy import _proxies
from booker.scan import _cap_headers

CAPACITY_URL = f"{BASE_URL}/ajax/capacity/{RP_ID}"

# Gleicher Horizont wie der gemeinsame Scanner des Bookers
# (booker/manager.py -> Manager.scan_window: today + 121 Tage). Laut
# telegram_bot.py deckt ein Call den ganzen buchbaren Zeitraum ab, weil der
# Server bei ~112 Tagen abschneidet.
HORIZON_DAYS = 121

_stop = False


def _sig(*_a):
    global _stop
    _stop = True


signal.signal(signal.SIGINT, _sig)


def _save(tag, payload):
    """Capture-Datei in captures/ schreiben (gleicher Ordner wie der Booker)."""
    os.makedirs(capture_mod.CAPTURE_DIR, exist_ok=True)
    name = (f"{time.strftime('%Y%m%d_%H%M%S')}_netcap_{tag}_"
            f"{int(time.time() * 1000) % 100000}.json")
    path = os.path.join(capture_mod.CAPTURE_DIR, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def _exchange(resp, request):
    """Anfrage + vollstaendige Antwort als Dict (Cookies/Auth werden maskiert)."""
    out = {"request": request, "response": None}
    if resp is not None:
        out["response"] = {
            "status_code": resp.status_code,
            "url": resp.url,
            "elapsed_ms": round(resp.elapsed.total_seconds() * 1000, 1)
            if resp.elapsed is not None else None,
            "headers": capture_mod._redact_headers(dict(resp.headers or {})),
            "body": resp.text,
        }
    return out


def capacity_window():
    """Kompletter buchbarer Horizont ab heute (Zypern-Zeit)."""
    today = nicosia_now().date()
    return today, today + timedelta(days=HORIZON_DAYS)


def capacity_params(dt_from, dt_to, captcha_answer=None):
    """Exakt die Parameter, die booker/scan.py fetch_capacity() sendet."""
    params = {
        "token": TOKEN,
        "afrom": dt_from.strftime("%Y-%m-%d 00:00"),
        "ato": dt_to.strftime("%Y-%m-%d 00:00"),
        "ad": "r",
        "efrom": dt_from.strftime("%Y-%m-%d"),
        "eto": dt_to.strftime("%Y-%m-%d"),
        "ed": "r",
    }
    if captcha_answer:
        params["captcha"] = str(captcha_answer)
    return params


def fetch(session=None):
    """Kapazitaets-Call. session=None -> anonym ueber den rotierenden Proxy.

    Rueckgabe: (resp, params, err). Bei 422 wird das Captcha geloest und der
    Call einmal wiederholt - wie im Booker.
    """
    dt_from, dt_to = capacity_window()
    params = capacity_params(dt_from, dt_to)
    sess = session if session is not None else httpclient.make_session(
        _proxies())
    resp, err = httpclient.safe_get(sess, CAPACITY_URL, params=params,
                                    headers=_cap_headers())
    if resp is not None and resp.status_code == 422:
        ans = solve_captcha_from_html(resp.text)
        if ans is not None:
            params = capacity_params(dt_from, dt_to, captcha_answer=ans)
            resp, err = httpclient.safe_get(sess, CAPACITY_URL, params=params,
                                            headers=_cap_headers())
    return resp, params, err


def read_rows(resp):
    """(alle Zeilen, freie Zeilen, mine) aus der Antwort - ohne jeden Filter."""
    try:
        data = resp.json()
    except Exception:
        return [], [], []
    rows = data.get("app", []) or []
    free = []
    for row in rows:
        try:
            start_ts, _end_ts, slot_id, booked, capacity = (row[0], row[1],
                                                            row[2], row[3],
                                                            row[4])
        except (IndexError, TypeError):
            continue
        if booked < capacity:
            free.append({"slot_id": slot_id, "start_ts": start_ts,
                         "booked": booked, "capacity": capacity,
                         "start_local": nicosia_dt(start_ts)
                         .strftime("%Y-%m-%d %H:%M"),
                         "raw_row": row})
    free.sort(key=lambda s: s["start_ts"])
    return rows, free, data.get("mine", []) or []


def booking_page(session, slot):
    """Die Buchungsseite des freien Slots holen - nur GET, es wird nicht gebucht.

    Gleiche URL, auf die booker/booking.py den Buchungs-POST schickt. Es werden
    die Header der Login-Session benutzt (kein XMLHttpRequest wie beim
    Kapazitaets-Call), damit die Seite so ankommt wie im Browser.
    """
    local = nicosia_dt(slot["start_ts"])
    url = f"{BOOK_URL}?view=week&day={local.day}&month={local.month}"
    resp, err = httpclient.safe_get(session, url)
    return resp, url, err


def login():
    """Gespeicherte Session benutzen, sonst nach E-Mail/Passwort fragen."""
    cfg = load_config()
    if (cfg.get("session_cookie") or "").strip():
        sess = create_login_session()
        if sess is not None and session_is_logged_in(sess):
            print("Angemeldet (gespeicherte Session).")
            return sess
        print("Gespeicherte Anmeldung ungueltig - bitte neu anmelden.")
    email = input("E-Mail: ").strip()
    try:
        password = getpass.getpass("Passwort: ").strip()
    except Exception:
        password = input("Passwort: ").strip()
    if not email or not password:
        print("E-Mail und Passwort sind erforderlich.")
        return None
    state.runtime_email = email
    state.runtime_password = password
    sess = create_login_session(email=email, password=password)
    if sess is not None and session_is_logged_in(sess):
        print("Angemeldet.")
        return sess
    print("Login FEHLGESCHLAGEN - es wird nur anonym gescannt.")
    return None


def capture_free(free, rows, anon_resp, anon_params, session, cycle):
    """Alles festhalten, was zu diesem freien Zeitpunkt sichtbar ist."""
    written = []
    proxy_used = bool(_proxies())
    written.append(_save("free_anon", {
        "kind": "capacity_free_anonymous",
        "ts": time.time(), "cycle": cycle,
        "horizon_days": HORIZON_DAYS,
        "proxy": "iproyal-rotating" if proxy_used else "direct",
        "rows_total": len(rows), "free_count": len(free),
        "free_slots": free,
        **_exchange(anon_resp, {"method": "GET", "url": CAPACITY_URL,
                                "params": dict(anon_params),
                                "headers": _cap_headers()}),
    }))

    if session is not None:
        resp, params, err = fetch(session=session)
        _rows, _free, mine = read_rows(
            resp) if resp is not None else ([], [], [])
        written.append(_save("free_session", {
            "kind": "capacity_free_logged_in",
            "ts": time.time(), "cycle": cycle,
            "horizon_days": HORIZON_DAYS,
            "error": None if resp is not None else str(err),
            "rows_total": len(_rows), "free_count": len(_free), "mine": mine,
            **_exchange(resp, {"method": "GET", "url": CAPACITY_URL,
                               "params": dict(params),
                               "headers": _cap_headers()}),
        }))

        page, url, perr = booking_page(session, free[0])
        written.append(_save("free_page", {
            "kind": "booking_page_when_free",
            "ts": time.time(), "cycle": cycle,
            "slot": {k: v for k, v in free[0].items() if k != "raw_row"},
            "error": None if page is not None else str(perr),
            **_exchange(page, {
                "method": "GET", "url": url, "params": {},
                "headers": capture_mod._redact_headers(dict(session.headers))}),
        }))
    return written


def main():
    ap = argparse.ArgumentParser(description="Netzwerk-Capture freier Termine")
    ap.add_argument("--no-login", action="store_true",
                    help="nur anonym scannen, kein Login")
    ap.add_argument("--stop-on-first", action="store_true",
                    help="nach dem ersten freien Termin beenden")
    ap.add_argument("--interval", type=float, default=None,
                    help="Sekunden zwischen den Abfragen "
                         "(Standard: poll_interval aus booker_config.json)")
    args = ap.parse_args()

    cfg = load_config()
    interval = args.interval if args.interval is not None \
        else float(cfg.get("poll_interval") or 0)
    dt_from, dt_to = capacity_window()
    print("=== Netzwerk-Capture (bucht nichts) ===")
    print(
        f"Zeitraum:  {dt_from} .. {dt_to}  (kompletter Horizont, kein Monat)")
    print(f"Proxy:     {'an' if cfg.get('proxy_enabled') else 'aus'}")
    print(f"Intervall: {interval} s")
    print(f"Ablage:    {capture_mod.CAPTURE_DIR}")

    session = None if args.no_login else login()
    print("-" * 60)

    cycle = 0
    baseline_done = False
    last_free_ids = None
    while not _stop:
        cycle += 1
        t0 = time.time()
        resp, params, err = fetch()
        ms = (time.time() - t0) * 1000
        if resp is None:
            print(f"[{time.strftime('%H:%M:%S')}] #{cycle} Fehler: {err}")
        elif resp.status_code != 200:
            print(f"[{time.strftime('%H:%M:%S')}] #{cycle} "
                  f"HTTP {resp.status_code} ({ms:.0f} ms)")
        else:
            rows, free, _mine = read_rows(resp)
            if not baseline_done:
                # Erste erfolgreiche Antwort als Vergleichsbasis mitschreiben.
                path = _save("baseline", {
                    "kind": "capacity_baseline", "ts": time.time(),
                    "cycle": cycle, "horizon_days": HORIZON_DAYS,
                    "rows_total": len(rows), "free_count": len(free),
                    **_exchange(resp, {"method": "GET", "url": CAPACITY_URL,
                                       "params": dict(params),
                                       "headers": _cap_headers()}),
                })
                baseline_done = True
                print(f"Baseline gespeichert: {os.path.basename(path)} "
                      f"({len(rows)} Termine in der Antwort)")
            print(f"[{time.strftime('%H:%M:%S')}] #{cycle} OK {ms:.0f} ms | "
                  f"Termine: {len(rows)} | frei: {len(free)}")
            if free:
                ids = tuple(s["slot_id"] for s in free)
                if ids != last_free_ids:
                    last_free_ids = ids
                    files = capture_free(
                        free, rows, resp, params, session, cycle)
                    print(f"  >>> {len(free)} FREI - Capture geschrieben:")
                    for p in files:
                        print(f"      {os.path.basename(p)}")
                    for s in free:
                        print(f"      {s['start_local']} Zypern "
                              f"(ID {s['slot_id']}, {s['booked']}/{s['capacity']})")
                    if args.stop_on_first:
                        break
            else:
                last_free_ids = None
        s = time.time()
        while time.time() - s < interval and not _stop:
            time.sleep(0.2)
    print("\nBeendet.")


if __name__ == "__main__":
    main()
