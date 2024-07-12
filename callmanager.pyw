import tkinter as tk
from tkinter import simpledialog, messagebox, ttk, filedialog
from datetime import datetime, timedelta
import threading
import json
import webbrowser
import re
import logging
from PIL import Image, ImageTk
import pystray
from pystray import MenuItem as item
from PIL import Image as PILImage
import csv

# Paths to the logos in PNG format
XF24_LOGO_PATH = r"C:\Users\theod\OneDrive\Desktop\Callmanager\XF24.png"
CAPITAGAINS_LOGO_PATH = r"C:\Users\theod\OneDrive\Desktop\Callmanager\CapitaGains.png"

# Function to center a window
def center_window(window):
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    x = (window.winfo_screenwidth() // 2) - (width // 2)
    y = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


# Function to switch themes
def switch_theme(theme_name):
    sv_ttk.set_theme(theme_name)


# Function to load image from file and convert to PhotoImage
def load_image_from_file(file_path, size):
    image = Image.open(file_path)
    image = image.resize(size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image)


# Function to show toast notifications
def show_toast(root, message, success=True):
    toast = tk.Toplevel(root)
    toast.overrideredirect(True)
    toast.geometry(f"+{root.winfo_x() + 50}+{root.winfo_y() + 50}")
    toast.configure(bg="green" if success else "red")

    tk.Label(
        toast,
        text=message,
        bg="green" if success else "red",
        fg="white",
        font=("Modern UI", 12),
    ).pack(padx=10, pady=5)
    toast.after(3000, toast.destroy)


class Timer:
    def __init__(self, interval, customer_name, profile_link=""):
        self.interval = interval
        self.customer_name = customer_name
        self.profile_link = profile_link
        self.category = self.determine_category(profile_link)
        self.remaining_time = interval
        self.calls_count = 0
        self.timer_frame = None
        self.timer_label = None
        self.calls_count_label = None
        self.end_time_label = None
        self.timer_running = False
        self.pause_symbol = "⏸"
        self.start_symbol = "⏵"
        self.end_time = None
        self.progress_bar = None

    def determine_category(self, url):
        if "crm.x-f24" in url:
            return "XF24"
        elif "crm.silliconbay" in url:
            return "CapitaGains"
        return "Unbekannt"

    def start(self):
        if not self.timer_running:
            self.calls_count += 1
            if self.calls_count_label:
                self.calls_count_label.config(text=f"Anrufe: {self.calls_count}")
            self.timer_running = True
            self.end_time = datetime.now() + timedelta(seconds=self.remaining_time)
            self.update_timer()

    def pause(self):
        self.timer_running = False

    def reset(self):
        self.pause()
        self.remaining_time = self.interval
        self.update_display()

    def update_timer(self):
        if self.remaining_time > 0 and self.timer_running:
            self.remaining_time -= 1
            mins, secs = divmod(self.remaining_time, 60)
            hours, mins = divmod(mins, 60)
            time_str = f"{hours:02}:{mins:02}:{secs:02}"
            self.update_display(time_str)
            self.timer_frame.after(1000, self.update_timer)
        else:
            if self.timer_running:
                self.timer_running = False
                self.show_alarm()

    def show_alarm(self):
        def visit_profile():
            webbrowser.open(self.profile_link)

        def ask_if_called():
            alarm_window.destroy()
            followup_window = tk.Toplevel()
            followup_window.title("Erinnerung")
            followup_window.geometry("400x200")
            followup_window.attributes("-topmost", True)
            center_window(followup_window)
            followup_window.resizable(False, False)

            tk.Label(
                followup_window,
                text="Hast du den Kunden angerufen? Wenn nicht klicke hier, um das Profil zu besuchen",
                font=("Modern UI", 14),
                wraplength=380,
            ).pack(pady=20)
            tk.Button(
                followup_window,
                text="Profil besuchen",
                command=visit_profile,
                font=("Modern UI", 12),
            ).pack(pady=10)
            tk.Button(
                followup_window,
                text="Schließen",
                command=followup_window.destroy,
                font=("Modern UI", 12),
            ).pack(pady=10)
            followup_window.mainloop()

        alarm_window = tk.Toplevel()
        alarm_window.title("Alarm")
        alarm_window.geometry("400x200")
        alarm_window.attributes("-topmost", True)
        center_window(alarm_window)
        alarm_window.resizable(False, False)

        tk.Label(
            alarm_window,
            text=f"Es ist Zeit, {self.customer_name} anzurufen!",
            font=("Modern UI", 14),
            wraplength=380,
        ).pack(pady=20)
        tk.Button(
            alarm_window,
            text="Schließen",
            command=ask_if_called,
            font=("Modern UI", 12),
        ).pack(pady=10)

        for _ in range(10):  # Play sound 10 times with shorter intervals
            alarm_window.bell()
            alarm_window.after(500)

        alarm_window.mainloop()

    def update_display(self, time_str=""):
        if self.timer_frame:
            end_time_str = (
                f"{self.end_time.strftime('%H:%M Uhr')}" if self.end_time else ""
            )
            self.end_time_label.config(text=end_time_str)
            self.timer_label.config(text=time_str)
            self.progress_bar["value"] = self.interval - self.remaining_time
            self.timer_frame.update()

    def edit(self):
        edit_dialog = EditTimerDialog(self.timer_frame, self)
        self.timer_frame.wait_window(edit_dialog.top)
        self.update_display()


class Customer:
    def __init__(self, first_name, last_name, profile_link):
        self.first_name = first_name
        self.last_name = last_name
        self.profile_link = profile_link
        self.last_call = "Nie"
        self.customer_number = self.extract_customer_number()
        self.company = self.determine_company(profile_link)
        self.notes = ""
        self.comments = []

    def extract_customer_number(self):
        match = re.search(r"itemId=([A-Z0-9]+)", self.profile_link)
        return match.group(1) if match else "Unbekannt"

    def determine_company(self, url):
        if "crm.x-f24" in url:
            return "XF24"
        elif "crm.silliconbay" in url:
            return "CapitaGains"
        return "Unbekannt"


class TimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kundenanruf-Timer")
        self.root.geometry("1200x800")

        # Initialize json_path
        self.json_path = tk.StringVar(value="timers.json")
        self.customer_json_path = tk.StringVar(value="customers.json")

        # Initialize logger
        self.logger = logging.getLogger("TimerAppLogger")
        self.logger.setLevel(logging.INFO)
        handler = logging.FileHandler("app.log")
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # Main frame with notebook for better navigation
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side="left", fill="both", expand=True)

        self.timer_frame = ttk.Frame(self.notebook, style="Main.TFrame")
        self.settings_frame = ttk.Frame(self.notebook, style="Main.TFrame")
        self.customers_frame = ttk.Frame(self.notebook, style="Main.TFrame")
        self.stats_frame = ttk.Frame(self.notebook, style="Main.TFrame")

        self.notebook.add(self.timer_frame, text="Timer")
        self.notebook.add(self.customers_frame, text="Kundenliste")
        self.notebook.add(self.settings_frame, text="Settings")
        self.notebook.add(self.stats_frame, text="Statistiken")

        # Initialize timers list
        self.timers = []
        self.timer_frames = []  # To store timer frames
        self.customers = []
        self.history = []

        # Load existing timers and customers from file
        self.load_timers()
        self.load_customers()

        # Create timer view widgets
        self.create_timer_view()
        self.create_customers_view()
        self.create_stats_view()
        self.create_edit_customer_dashboard()

        # Keybindings for closing the script
        self.root.bind("<Alt-Key-1>", lambda e: self.root.quit())
        self.root.bind("<Alt-Key-2>", lambda e: self.root.quit())
        self.root.bind("<Alt-Key-3>", lambda e: self.root.quit())
        self.root.bind("<Alt-Key-4>", lambda e: self.root.quit())

        # Keybinding for creating a new timer
        self.root.bind("<Control-n>", lambda e: self.add_timer())

        # Setup system tray
        self.icon_image = PILImage.open(XF24_LOGO_PATH)
        self.tray_icon = pystray.Icon(
            "Kundenanruf-Timer",
            self.icon_image,
            "Kundenanruf-Timer",
            self.create_tray_menu(),
        )
        self.setup_tray()

    def create_tray_menu(self):
        return pystray.Menu(
            item("Open", self.show_window), item("Quit", self.quit_application)
        )

    def setup_tray(self):
        self.tray_thread = threading.Thread(target=self.tray_icon.run)
        self.tray_thread.start()

    def show_window(self, icon, item):
        self.root.deiconify()

    def hide_window(self):
        self.root.withdraw()
        self.tray_icon.notify(
            "Die Anwendung läuft weiter im Hintergrund.", "Kundenanruf-Timer"
        )

    def quit_application(self, icon, item):
        self.save_timers()
        self.save_customers()
        self.tray_icon.stop()
        self.root.quit()

    def show_timer_view(self):
        self.notebook.select(self.timer_frame)

    def show_settings(self):
        self.notebook.select(self.settings_frame)

    def show_customers_view(self):
        self.notebook.select(self.customers_frame)

    def show_stats_view(self):
        self.notebook.select(self.stats_frame)

    def create_timer_view(self):
        self.canvas = tk.Canvas(self.timer_frame)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(
            self.timer_frame, orient="vertical", command=self.canvas.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.create_add_buttons()

        self.refresh_timer_display()

    def create_add_buttons(self):
        add_timer_button = ttk.Label(
            self.scrollable_frame, text="+", style="Plus.TLabel", cursor="hand2"
        )
        add_timer_button.grid(row=0, column=0, padx=5, pady=10, columnspan=2)
        add_timer_button.bind("<Button-1>", self.show_add_menu)

    def show_add_menu(self, event):
        self.add_menu = tk.Toplevel(self.root)
        self.add_menu.geometry("150x100")
        self.add_menu.overrideredirect(True)
        x, y, _, _ = event.widget.bbox("insert")
        x += event.widget.winfo_rootx()
        y += event.widget.winfo_rooty()
        self.add_menu.geometry(f"+{x}+{y}")

        ttk.Button(
            self.add_menu,
            text="Neuen Timer erstellen",
            command=self.add_timer_and_close_menu,
        ).pack(fill="x", padx=10, pady=5)
        ttk.Button(
            self.add_menu,
            text="Erstell ein Timer für Alle Kunden",
            command=self.add_timers_for_all_customers_and_close_menu,
        ).pack(fill="x", padx=10, pady=5)

    def hide_add_menu(self, event):
        if self.add_menu:
            self.add_menu.destroy()

    def add_timer_and_close_menu(self):
        self.add_timer()
        self.hide_add_menu(None)

    def add_timers_for_all_customers_and_close_menu(self):
        self.add_timers_for_all_customers()
        self.hide_add_menu(None)

    def create_customers_view(self):
        self.customer_tabs = ttk.Notebook(self.customers_frame)
        self.customer_tabs.pack(fill="both", expand=True)

        self.company_frames = {}
        companies = ["CapitaGains", "XF24"]

        for company in companies:
            frame = ttk.Frame(self.customer_tabs)
            self.customer_tabs.add(frame, text=company)
            self.company_frames[company] = frame

            add_customer_button = ttk.Label(
                frame, text="+ Kunde hinzufügen", style="Plus.TLabel", cursor="hand2"
            )
            add_customer_button.pack(pady=10)
            add_customer_button.bind(
                "<Button-1>", lambda e, c=company: self.add_customer()
            )

            customers_table = ttk.Treeview(
                frame,
                columns=(
                    "Vorname",
                    "Nachname",
                    "Kundennummer",
                    "Letzter Anruf",
                    "Zeit seit letztem Anruf",
                    "Notizen",
                ),
                show="headings",
            )
            customers_table.heading("Vorname", text="Vorname")
            customers_table.heading("Nachname", text="Nachname")
            customers_table.heading("Kundennummer", text="Kundennummer")
            customers_table.heading("Letzter Anruf", text="Letzter Anruf")
            customers_table.heading(
                "Zeit seit letztem Anruf", text="Zeit seit letztem Anruf"
            )
            customers_table.heading("Notizen", text="Notizen")
            customers_table.pack(fill="both", expand=True)

            customers_table.bind(
                "<Button-3>", lambda e, c=company: self.show_context_menu(e, company)
            )

            self.refresh_customers_display(company)

        # Search and filter
        search_frame = ttk.Frame(self.customers_frame)
        search_frame.pack(pady=10)
        ttk.Label(search_frame, text="Suche:").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side="left")
        search_entry.bind("<KeyRelease>", self.filter_customers)

    def create_stats_view(self):
        ttk.Label(self.stats_frame, text="Statistiken", font=("Modern UI", 18)).pack(
            pady=10
        )
        self.stats_text = tk.Text(
            self.stats_frame, state="disabled", wrap="word", font=("Modern UI", 12)
        )
        self.stats_text.pack(pady=10, fill="both", expand=True)
        self.update_stats()

    def update_stats(self):
        self.stats_text.configure(state="normal")
        self.stats_text.delete(1.0, tk.END)
        total_calls = sum(timer.calls_count for timer in self.timers)
        total_timers = len(self.timers)
        total_customers = len(self.customers)
        average_calls = total_calls / total_timers if total_timers > 0 else 0
        stats_content = f"Gesamtanzahl Anrufe: {total_calls}\n"
        stats_content += f"Gesamtanzahl Timer: {total_timers}\n"
        stats_content += f"Durchschnittliche Anrufe pro Timer: {average_calls:.2f}\n"
        stats_content += f"Gesamtanzahl Kunden: {total_customers}\n"
        self.stats_text.insert(tk.END, stats_content)
        self.stats_text.configure(state="disabled")
        self.stats_frame.after(60000, self.update_stats)

    def create_edit_customer_dashboard(self):
        self.edit_customer_dashboard = ttk.Frame(self.root, style="Main.TFrame")
        self.edit_customer_dashboard.place(
            relx=1.0, rely=0, anchor="ne", relwidth=0.3, relheight=1.0
        )
        self.edit_customer_dashboard.lower()

        self.edit_customer_title = ttk.Label(
            self.edit_customer_dashboard,
            text="Profil Bearbeiten",
            font=("Modern UI", 18),
        )
        self.edit_customer_title.pack(pady=10)

        self.edit_customer_close_button = ttk.Label(
            self.edit_customer_dashboard, text="❌", style="Close.TLabel", cursor="hand2"
        )
        self.edit_customer_close_button.place(relx=1.0, rely=0, anchor="ne")
        self.edit_customer_close_button.bind(
            "<Button-1>", self.hide_edit_customer_dashboard
        )

        self.edit_customer_form = ttk.Frame(self.edit_customer_dashboard)
        self.edit_customer_form.pack(pady=20, padx=20)

        ttk.Label(self.edit_customer_form, text="Name:").grid(
            row=0, column=0, sticky="w", pady=5
        )
        self.edit_customer_name = ttk.Entry(self.edit_customer_form)
        self.edit_customer_name.grid(row=0, column=1, pady=5)

        ttk.Label(self.edit_customer_form, text="Nachname:").grid(
            row=1, column=0, sticky="w", pady=5
        )
        self.edit_customer_lastname = ttk.Entry(self.edit_customer_form)
        self.edit_customer_lastname.grid(row=1, column=1, pady=5)

        ttk.Label(self.edit_customer_form, text="Profillink:").grid(
            row=2, column=0, sticky="w", pady=5
        )
        self.edit_customer_profile_link = ttk.Entry(self.edit_customer_form)
        self.edit_customer_profile_link.grid(row=2, column=1, pady=5)

        ttk.Label(self.edit_customer_form, text="Letzter Anruf:").grid(
            row=3, column=0, sticky="w", pady=5
        )
        self.edit_customer_last_call_date = ttk.Entry(self.edit_customer_form)
        self.edit_customer_last_call_date.grid(row=3, column=1, pady=5)

        ttk.Label(self.edit_customer_form, text="Letzte Anrufzeit:").grid(
            row=4, column=0, sticky="w", pady=5
        )
        self.edit_customer_last_call_time = ttk.Entry(self.edit_customer_form)
        self.edit_customer_last_call_time.grid(row=4, column=1, pady=5)

        self.save_edit_customer_button = ttk.Button(
            self.edit_customer_dashboard,
            text="Speichern",
            command=self.save_edit_customer,
            style="Accent.TButton",
        )
        self.save_edit_customer_button.pack(pady=10)

    def show_edit_customer_dashboard(self, customer):
        self.current_customer = customer
        self.edit_customer_name.delete(0, tk.END)
        self.edit_customer_name.insert(0, customer.first_name)
        self.edit_customer_lastname.delete(0, tk.END)
        self.edit_customer_lastname.insert(0, customer.last_name)
        self.edit_customer_profile_link.delete(0, tk.END)
        self.edit_customer_profile_link.insert(0, customer.profile_link)
        self.edit_customer_last_call_date.delete(0, tk.END)
        self.edit_customer_last_call_date.insert(
            0, customer.last_call.split(" ")[0] if customer.last_call != "Nie" else ""
        )
        self.edit_customer_last_call_time.delete(0, tk.END)
        self.edit_customer_last_call_time.insert(
            0, customer.last_call.split(" ")[1] if customer.last_call != "Nie" else ""
        )
        self.edit_customer_dashboard.lift()

    def hide_edit_customer_dashboard(self, event=None):
        self.edit_customer_dashboard.lower()

    def save_edit_customer(self):
        self.current_customer.first_name = self.edit_customer_name.get()
        self.current_customer.last_name = self.edit_customer_lastname.get()
        self.current_customer.profile_link = self.edit_customer_profile_link.get()
        self.current_customer.last_call = f"{self.edit_customer_last_call_date.get()} {self.edit_customer_last_call_time.get()}"
        self.save_customers()
        self.refresh_customers_display(self.current_customer.company)
        self.hide_edit_customer_dashboard()

    def refresh_timer_display(self):
        for widget in self.scrollable_frame.winfo_children():
            if (
                isinstance(widget, ttk.Frame)
                and widget != self.scrollable_frame.grid_slaves(row=0, column=0)[0]
            ):
                widget.destroy()

        self.timers.sort(key=lambda t: t.remaining_time)

        for idx, timer in enumerate(self.timers):
            self.create_timer_frame(timer, self.scrollable_frame, idx + 1)

    def create_timer_frame(self, timer, parent, idx):
        timer_frame = ttk.Frame(parent, style="Card.TFrame", padding=(10, 10))
        if timer.category == "CapitaGains":
            timer_frame.configure(style="GoldCard.TFrame")
        elif timer.category == "XF24":
            timer_frame.configure(style="GreenCard.TFrame")
        timer_frame.grid(
            row=idx // 2 + 1, column=idx % 2, padx=10, pady=10, sticky="nsew"
        )
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)

        self.timer_frames.append(timer_frame)  # Store reference to the timer frame

        # Add logo based on category
        logo_image = None
        if timer.category == "XF24":
            logo_image = load_image_from_file(XF24_LOGO_PATH, (50, 50))  # Adjusted size
        elif timer.category == "CapitaGains":
            logo_image = load_image_from_file(
                CAPITAGAINS_LOGO_PATH, (50, 50)
            )  # Adjusted size

        if logo_image:
            logo_label = tk.Label(timer_frame, image=logo_image, bg="#222")
            logo_label.image = logo_image
            logo_label.pack(pady=10)

        customer_label = ttk.Label(
            timer_frame,
            text=timer.customer_name,
            style="Card.TLabel",
            font=("Modern UI", 14),
        )
        customer_label.pack(pady=(10, 0))

        close_label = ttk.Label(
            timer_frame, text="X", style="Close.TLabel", cursor="hand2"
        )
        close_label.place(relx=1.0, rely=0.0, anchor="ne")
        close_label.bind("<Button-1>", lambda e: self.remove_timer(timer, timer_frame))

        edit_label = ttk.Label(
            timer_frame, text="⚙️", style="Edit.TLabel", cursor="hand2"
        )
        edit_label.place(relx=0.0, rely=0.0, anchor="nw")
        edit_label.bind("<Button-1>", lambda e: timer.edit())

        profile_label = ttk.Label(
            timer_frame,
            text="Profil ansehen..",
            style="Link.TLabel",
            font=("Modern UI", 12),
        )
        profile_label.pack(pady=(0, 10))
        profile_label.bind("<Button-1>", lambda e: webbrowser.open(timer.profile_link))

        time_str = timedelta(seconds=timer.remaining_time)
        timer_label = ttk.Label(
            timer_frame, text=str(time_str), style="Card.TLabel", font=("Modern UI", 24)
        )
        timer_label.pack()

        end_time_label = ttk.Label(
            timer_frame, text="", style="Card.TLabel", font=("Modern UI", 12)
        )
        end_time_label.pack()

        button_frame = ttk.Frame(timer_frame)
        button_frame.pack(pady=(0, 10))

        start_pause_button = ttk.Button(
            button_frame,
            text=timer.start_symbol,
            command=lambda: self.toggle_timer(timer, start_pause_button),
            style="Accent.TButton",
        )
        start_pause_button.grid(row=0, column=0, padx=5)

        calls_count_label = ttk.Label(
            timer_frame,
            text=f"Anrufe: {timer.calls_count}",
            style="Card.TLabel",
            font=("Modern UI", 12),
        )
        calls_count_label.pack()

        progress_bar = ttk.Progressbar(
            timer_frame,
            maximum=timer.interval,
            value=timer.interval - timer.remaining_time,
        )
        progress_bar.pack(fill="x", pady=5)

        calls_bar = ttk.Progressbar(
            timer_frame, maximum=3, value=min(timer.calls_count, 3)
        )
        calls_bar.pack(fill="x", pady=5)
        if timer.calls_count == 3:
            calls_bar.config(style="green.Horizontal.TProgressbar")
        elif timer.calls_count == 2:
            calls_bar.config(style="orange.Horizontal.TProgressbar")
        else:
            calls_bar.config(style="red.Horizontal.TProgressbar")

        timer.timer_frame = timer_frame
        timer.timer_label = timer_label
        timer.end_time_label = end_time_label
        timer.calls_count_label = calls_count_label
        timer.progress_bar = progress_bar
        timer.calls_bar = calls_bar

    def toggle_timer(self, timer, button):
        if timer.timer_running:
            timer.pause()
            button.config(text=timer.start_symbol)
        else:
            timer.start()
            button.config(text=timer.pause_symbol)
        self.update_progress_bar(timer)

    def update_progress_bar(self, timer):
        timer.progress_bar["value"] = timer.interval - timer.remaining_time
        timer.calls_bar["value"] = min(timer.calls_count, 3)
        if timer.calls_count == 3:
            timer.calls_bar.config(style="green.Horizontal.TProgressbar")
        elif timer.calls_count == 2:
            timer.calls_bar.config(style="orange.Horizontal.TProgressbar")
        else:
            timer.calls_bar.config(style="red.Horizontal.TProgressbar")
        if timer.timer_running:
            timer.timer_frame.after(1000, lambda: self.update_progress_bar(timer))

    def add_timer(self):
        add_timer_dialog = AddTimerDialog(self.root, self.customers)
        self.root.wait_window(add_timer_dialog.top)

        if add_timer_dialog.timer:
            self.timers.append(add_timer_dialog.timer)
            self.update_customer_last_call(add_timer_dialog.timer.customer_name)
            self.refresh_timer_display()
            self.save_timers()
            self.history.append(
                f"Timer hinzugefügt: {add_timer_dialog.timer.customer_name}"
            )

    def add_timers_for_all_customers(self):
        for customer in self.customers:
            timer = Timer(
                7200,
                f"{customer.first_name} {customer.last_name}",
                customer.profile_link,
            )
            self.timers.append(timer)
        self.refresh_timer_display()
        self.save_timers()
        self.history.append("Massen-Timer für alle Kunden hinzugefügt")

    def add_customer(self):
        add_customer_dialog = AddCustomerDialog(self.root)
        self.root.wait_window(add_customer_dialog.top)

        if add_customer_dialog.customer:
            self.customers.append(add_customer_dialog.customer)
            self.refresh_customers_display(add_customer_dialog.customer.company)
            self.save_customers()
            self.history.append(
                f"Kunde hinzugefügt: {add_customer_dialog.customer.first_name} {add_customer_dialog.customer.last_name}"
            )

    def update_customer_last_call(self, customer_name):
        for customer in self.customers:
            if f"{customer.first_name} {customer.last_name}" == customer_name:
                customer.last_call = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.refresh_customers_display(customer.company)
                self.save_customers()
                break

    def refresh_customers_display(self, company):
        frame = self.company_frames[company]
        customers_table = frame.winfo_children()[1]

        for row in customers_table.get_children():
            customers_table.delete(row)

        for customer in self.customers:
            if customer.company == company:
                last_call_datetime = self.parse_date(customer.last_call)
                time_since_last_call = (
                    (datetime.now() - last_call_datetime).days
                    if last_call_datetime
                    else "Nie"
                )
                customers_table.insert(
                    "",
                    "end",
                    values=(
                        customer.first_name,
                        customer.last_name,
                        customer.customer_number,
                        customer.last_call,
                        time_since_last_call,
                        customer.notes,
                    ),
                    tags=(customer.profile_link,),
                )

        customers_table.tag_configure("hyperlink", foreground="blue")
        customers_table.bind("<ButtonRelease-1>", self.on_customer_click)

    def parse_date(self, date_str):
        """Parse date string and return datetime object. Supports multiple formats."""
        date_formats = ["%Y-%m-%d %H:%M:%S", "%d.%m.%Y"]
        for date_format in date_formats:
            try:
                return datetime.strptime(date_str, date_format)
            except ValueError:
                continue
        return None

    def on_customer_click(self, event):
        customers_table = event.widget
        item = customers_table.identify("item", event.x, event.y)
        tags = customers_table.item(item, "tags")
        column = customers_table.identify_column(event.x)
        if tags and column == "#3":  # Kundennummer column
            webbrowser.open(tags[0])

    def show_context_menu(self, event, company):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label="Profil Öffnen", command=lambda: self.open_profile(event, company)
        )
        menu.add_command(
            label="Timer erstellen",
            command=lambda: self.create_timer_for_customer(event, company),
        )
        menu.add_command(
            label="Kunde bearbeiten", command=lambda: self.edit_customer(event, company)
        )
        menu.add_command(
            label="Kunde löschen", command=lambda: self.delete_customer(event, company)
        )
        menu.add_command(
            label="Notiz hinzufügen",
            command=lambda: self.add_note_to_customer(event, company),
        )
        menu.tk_popup(event.x_root, event.y_root)

    def open_profile(self, event, company):
        selected_item = self.get_selected_customer(event, company)
        if selected_item:
            webbrowser.open(selected_item.profile_link)

    def create_timer_for_customer(self, event, company):
        selected_item = self.get_selected_customer(event, company)
        if selected_item:
            timer = Timer(
                7200,
                f"{selected_item.first_name} {selected_item.last_name}",
                selected_item.profile_link,
            )
            self.timers.append(timer)
            self.refresh_timer_display()
            self.save_timers()
            show_toast(self.root, "Erfolgreich Timer erstellt 🗸")

    def edit_customer(self, event, company):
        selected_item = self.get_selected_customer(event, company)
        if selected_item:
            self.show_edit_customer_dashboard(selected_item)

    def delete_customer(self, event, company):
        selected_item = self.get_selected_customer(event, company)
        if selected_item:
            self.customers.remove(selected_item)
            self.refresh_customers_display(company)
            self.save_customers()
            show_toast(self.root, "Kunde erfolgreich gelöscht 🗸")

    def add_note_to_customer(self, event, company):
        selected_item = self.get_selected_customer(event, company)
        if selected_item:
            note = simpledialog.askstring("Notiz hinzufügen", "Notiz:")
            if note:
                selected_item.notes = note
                self.refresh_customers_display(company)
                self.save_customers()
                show_toast(self.root, "Notiz erfolgreich hinzugefügt 🗸")

    def get_selected_customer(self, event, company):
        customers_table = self.company_frames[company].winfo_children()[1]
        selected_item_id = customers_table.selection()
        if selected_item_id:
            item_values = customers_table.item(selected_item_id, "values")
            for customer in self.customers:
                if customer.customer_number == item_values[2]:
                    return customer
        return None

    def filter_customers(self, event=None):
        search_term = self.search_var.get().lower()
        for company, frame in self.company_frames.items():
            customers_table = frame.winfo_children()[1]
            for row in customers_table.get_children():
                values = customers_table.item(row, "values")
                if any(search_term in str(value).lower() for value in values):
                    customers_table.item(row, tags=())
                else:
                    customers_table.item(row, tags=("hidden",))
            customers_table.tag_configure(
                "hidden", background="#f0f0f0", foreground="#f0f0f0"
            )

    def remove_timer(self, timer, frame):
        self.timers.remove(timer)
        self.timer_frames.remove(frame)  # Remove the frame reference
        self.refresh_timer_display()
        self.save_timers()
        self.history.append(f"Timer entfernt: {timer.customer_name}")

    def save_timers(self):
        timers_data = []
        for timer in self.timers:
            timer_data = {
                "interval": timer.interval,
                "customer_name": timer.customer_name,
                "profile_link": timer.profile_link,
                "category": timer.category,
                "remaining_time": timer.remaining_time,
                "calls_count": timer.calls_count,
            }
            timers_data.append(timer_data)

        with open(self.json_path.get(), "w") as f:
            json.dump(timers_data, f)
        self.logger.info("Timers saved to file.")

    def load_timers(self):
        try:
            with open(self.json_path.get(), "r") as f:
                timers_data = json.load(f)
                for timer_data in timers_data:
                    profile_link = timer_data.get("profile_link", "")
                    timer = Timer(
                        timer_data["interval"],
                        timer_data["customer_name"],
                        profile_link,
                    )
                    timer.remaining_time = timer_data["remaining_time"]
                    timer.calls_count = timer_data["calls_count"]
                    self.timers.append(timer)
            self.logger.info("Timers loaded from file.")
        except FileNotFoundError:
            self.logger.warning("No existing timers file found.")

    def save_customers(self):
        customers_data = []
        for customer in self.customers:
            customer_data = {
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "profile_link": customer.profile_link,
                "last_call": customer.last_call,
                "company": customer.company,
                "notes": customer.notes,
                "comments": customer.comments,
            }
            customers_data.append(customer_data)

        with open(self.customer_json_path.get(), "w") as f:
            json.dump(customers_data, f)
        self.logger.info("Customers saved to file.")

    def load_customers(self):
        try:
            with open(self.customer_json_path.get(), "r") as f:
                customers_data = json.load(f)
                for customer_data in customers_data:
                    customer = Customer(
                        customer_data["first_name"],
                        customer_data["last_name"],
                        customer_data["profile_link"],
                    )
                    customer.last_call = customer_data.get("last_call", "Nie")
                    customer.company = customer_data.get(
                        "company", customer.determine_company(customer.profile_link)
                    )
                    customer.notes = customer_data.get("notes", "")
                    customer.comments = customer_data.get("comments", [])
                    self.customers.append(customer)
            self.logger.info("Customers loaded from file.")
        except FileNotFoundError:
            self.logger.warning("No existing customers file found.")


class AddTimerDialog:
    def __init__(self, parent, customers):
        self.top = tk.Toplevel(parent)
        self.top.title("Neuen Timer hinzufügen")
        self.top.attributes("-topmost", True)
        self.top.resizable(False, False)

        self.customers = customers

        # Entry variables
        self.hours = tk.StringVar(value="2")
        self.minutes = tk.StringVar(value="0")
        self.seconds = tk.StringVar(value="0")
        self.customer_name = tk.StringVar()
        self.profile_link = tk.StringVar(value="http://")

        # Labels and entries
        ttk.Label(self.top, text="Stunden:").grid(row=0, column=0)
        hours_entry = ttk.Entry(self.top, textvariable=self.hours)
        hours_entry.grid(row=0, column=1)
        ttk.Label(self.top, text="Minuten:").grid(row=1, column=0)
        minutes_entry = ttk.Entry(self.top, textvariable=self.minutes)
        minutes_entry.grid(row=1, column=1)
        ttk.Label(self.top, text="Sekunden:").grid(row=2, column=0)
        seconds_entry = ttk.Entry(self.top, textvariable=self.seconds)
        seconds_entry.grid(row=2, column=1)
        ttk.Label(self.top, text="Kundenname:").grid(row=3, column=0)
        customer_combobox = ttk.Combobox(
            self.top,
            textvariable=self.customer_name,
            values=[
                f"{c.first_name} {c.last_name}"
                for c in sorted(self.customers, key=lambda x: x.last_name)
            ],
            state="readonly",
        )
        customer_combobox.grid(row=3, column=1)
        customer_combobox.bind("<<ComboboxSelected>>", self.update_profile_link)
        ttk.Label(self.top, text="Profil Link:").grid(row=4, column=0)
        profile_link_entry = ttk.Entry(self.top, textvariable=self.profile_link)
        profile_link_entry.grid(row=4, column=1)

        # Clipboard paste buttons
        paste_profile_button = ttk.Button(
            self.top, text="Paste", command=self.paste_profile_link
        )
        paste_profile_button.grid(row=4, column=2, padx=5)

        # Save and cancel buttons
        save_button = ttk.Button(
            self.top, text="Speichern", command=self.save, style="Accent.TButton"
        )
        save_button.grid(row=5, column=0, padx=5, pady=10)
        cancel_button = ttk.Button(
            self.top, text="Abbrechen", command=self.top.destroy, style="Accent.TButton"
        )
        cancel_button.grid(row=5, column=1, padx=5, pady=10)

        self.timer = None

        center_window(self.top)

        # Bind Enter key to navigate between entries and save timer when the last entry is focused
        entries = [
            hours_entry,
            minutes_entry,
            seconds_entry,
            customer_combobox,
            profile_link_entry,
            save_button,
        ]
        for i, entry in enumerate(entries):
            entry.bind(
                "<Return>",
                lambda e, idx=i: entries[idx + 1].focus()
                if idx < len(entries) - 1
                else self.save(),
            )

    def paste_profile_link(self):
        profile_link = self.top.clipboard_get()
        self.profile_link.set(profile_link)

    def update_profile_link(self, event):
        selected_customer = next(
            (
                c
                for c in self.customers
                if f"{c.first_name} {c.last_name}" == self.customer_name.get()
            ),
            None,
        )
        if selected_customer:
            self.profile_link.set(selected_customer.profile_link)

    def save(self):
        try:
            interval = (
                int(self.hours.get()) * 3600
                + int(self.minutes.get()) * 60
                + int(self.seconds.get())
            )
            customer_name = self.customer_name.get()
            profile_link = self.profile_link.get()

            if not re.match(r"^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", profile_link):
                messagebox.showerror(
                    "Fehler", "Bitte geben Sie einen gültigen Link ein."
                )
                return

            if not customer_name:
                customer_name = simpledialog.askstring(
                    "Neuer Kunde",
                    "Bitte geben Sie den Namen des neuen Kunden ein (Vorname Nachname):",
                )
                if not customer_name:
                    messagebox.showerror("Fehler", "Kundenname darf nicht leer sein.")
                    return

                first_name, last_name = customer_name.split()
                new_customer = Customer(first_name, last_name, profile_link)
                self.customers.append(new_customer)

            self.timer = Timer(interval, customer_name, profile_link)
            self.top.destroy()
        except ValueError:
            messagebox.showerror(
                "Fehler",
                "Bitte geben Sie gültige Zahlen für Stunden, Minuten und Sekunden ein.",
            )


class EditTimerDialog:
    def __init__(self, parent, timer):
        self.timer = timer
        self.top = tk.Toplevel(parent)
        self.top.title("Timer bearbeiten")
        self.top.attributes("-topmost", True)
        self.top.resizable(False, False)

        # Entry variables
        self.hours = tk.StringVar(value=str(timer.interval // 3600))
        self.minutes = tk.StringVar(value=str((timer.interval % 3600) // 60))
        self.seconds = tk.StringVar(value=str(timer.interval % 60))
        self.customer_name = tk.StringVar(value=timer.customer_name)
        self.profile_link = tk.StringVar(value=timer.profile_link)
        self.calls_count = tk.StringVar(value=str(timer.calls_count))

        # Labels and entries
        ttk.Label(self.top, text="Stunden:").grid(row=0, column=0)
        hours_entry = ttk.Entry(self.top, textvariable=self.hours)
        hours_entry.grid(row=0, column=1)
        ttk.Label(self.top, text="Minuten:").grid(row=1, column=0)
        minutes_entry = ttk.Entry(self.top, textvariable=self.minutes)
        minutes_entry.grid(row=1, column=1)
        ttk.Label(self.top, text="Sekunden:").grid(row=2, column=0)
        seconds_entry = ttk.Entry(self.top, textvariable=self.seconds)
        seconds_entry.grid(row=2, column=1)
        ttk.Label(self.top, text="Kundenname:").grid(row=3, column=0)
        customer_entry = ttk.Entry(self.top, textvariable=self.customer_name)
        customer_entry.grid(row=3, column=1)
        ttk.Label(self.top, text="Profil Link:").grid(row=4, column=0)
        profile_link_entry = ttk.Entry(self.top, textvariable=self.profile_link)
        profile_link_entry.grid(row=4, column=1)
        ttk.Label(self.top, text="Anrufe:").grid(row=5, column=0)
        calls_count_entry = ttk.Entry(self.top, textvariable=self.calls_count)
        calls_count_entry.grid(row=5, column=1)

        # Clipboard paste buttons
        paste_customer_button = ttk.Button(
            self.top,
            text="Paste",
            command=lambda: self.customer_name.set(self.top.clipboard_get()),
        )
        paste_customer_button.grid(row=3, column=2, padx=5)
        paste_profile_button = ttk.Button(
            self.top,
            text="Paste",
            command=lambda: self.profile_link.set(self.top.clipboard_get()),
        )
        paste_profile_button.grid(row=4, column=2, padx=5)

        # Save and cancel buttons
        save_button = ttk.Button(
            self.top, text="Speichern", command=self.save, style="Accent.TButton"
        )
        save_button.grid(row=6, column=0, padx=5, pady=10)
        cancel_button = ttk.Button(
            self.top, text="Abbrechen", command=self.top.destroy, style="Accent.TButton"
        )
        cancel_button.grid(row=6, column=1, padx=5, pady=10)

        center_window(self.top)

    def save(self):
        try:
            self.timer.interval = (
                int(self.hours.get()) * 3600
                + int(self.minutes.get()) * 60
                + int(self.seconds.get())
            )
            self.timer.customer_name = self.customer_name.get()
            self.timer.profile_link = self.profile_link.get()
            self.timer.calls_count = int(self.calls_count.get())
            self.timer.reset()
            self.top.destroy()
        except ValueError:
            messagebox.showerror(
                "Fehler",
                "Bitte geben Sie gültige Zahlen für Stunden, Minuten und Sekunden ein.",
            )


class AddCustomerDialog:
    def __init__(self, parent, customer=None):
        self.top = tk.Toplevel(parent)
        self.top.title("Kunde hinzufügen" if customer is None else "Kunde bearbeiten")
        self.top.attributes("-topmost", True)
        self.top.resizable(False, False)

        # Entry variables
        self.first_name = tk.StringVar(value=customer.first_name if customer else "")
        self.last_name = tk.StringVar(value=customer.last_name if customer else "")
        self.profile_link = tk.StringVar(
            value=customer.profile_link if customer else ""
        )

        # Labels and entries
        ttk.Label(self.top, text="Vorname:").grid(row=0, column=0)
        first_name_entry = ttk.Entry(self.top, textvariable=self.first_name)
        first_name_entry.grid(row=0, column=1)
        ttk.Label(self.top, text="Nachname:").grid(row=1, column=0)
        last_name_entry = ttk.Entry(self.top, textvariable=self.last_name)
        last_name_entry.grid(row=1, column=1)
        ttk.Label(self.top, text="Profil Link:").grid(row=2, column=0)
        profile_link_entry = ttk.Entry(self.top, textvariable=self.profile_link)
        profile_link_entry.grid(row=2, column=1)

        # Clipboard paste button
        paste_profile_button = ttk.Button(
            self.top, text="Paste", command=self.paste_profile_link
        )
        paste_profile_button.grid(row=2, column=2, padx=5)

        # Save and cancel buttons
        save_button = ttk.Button(
            self.top, text="Speichern", command=self.save, style="Accent.TButton"
        )
        save_button.grid(row=3, column=0, padx=5, pady=10)
        cancel_button = ttk.Button(
            self.top, text="Abbrechen", command=self.top.destroy, style="Accent.TButton"
        )
        cancel_button.grid(row=3, column=1, padx=5, pady=10)

        self.customer = customer

        center_window(self.top)

        # Bind Enter key to navigate between entries and save customer when the last entry is focused
        entries = [first_name_entry, last_name_entry, profile_link_entry, save_button]
        for i, entry in enumerate(entries):
            entry.bind(
                "<Return>",
                lambda e, idx=i: entries[idx + 1].focus()
                if idx < len(entries) - 1
                else self.save(),
            )

    def paste_profile_link(self):
        profile_link = self.top.clipboard_get()
        self.profile_link.set(profile_link)

    def save(self):
        try:
            first_name = self.first_name.get()
            last_name = self.last_name.get()
            profile_link = self.profile_link.get()

            if not first_name or not last_name:
                messagebox.showerror(
                    "Fehler", "Vorname und Nachname dürfen nicht leer sein."
                )
                return

            if not re.match(r"^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+", profile_link):
                messagebox.showerror(
                    "Fehler", "Bitte geben Sie einen gültigen Link ein."
                )
                return

            if not self.customer:
                self.customer = Customer(first_name, last_name, profile_link)
            else:
                self.customer.first_name = first_name
                self.customer.last_name = last_name
                self.customer.profile_link = profile_link

            self.top.destroy()
        except ValueError:
            messagebox.showerror("Fehler", "Bitte geben Sie gültige Daten ein.")


if __name__ == "__main__":
    import sv_ttk

    root = tk.Tk()
    sv_ttk.set_theme("dark")

    style = ttk.Style()
    style.configure("Sidebar.TFrame", background="#333")
    style.configure(
        "Sidebar.TLabel", background="#333", foreground="white", font=("Modern UI", 12)
    )
    style.configure(
        "Sidebar.TButton", background="#444", foreground="white", font=("Modern UI", 12)
    )
    style.configure("Main.TFrame", background="#222")
    style.configure("Card.TFrame", background="#222", relief="solid", borderwidth=2)
    style.configure(
        "GoldCard.TFrame",
        background="#222",
        relief="solid",
        borderwidth=2,
        bordercolor="#FFD700",
    )
    style.configure(
        "GreenCard.TFrame",
        background="#222",
        relief="solid",
        borderwidth=2,
        bordercolor="#00FF00",
    )
    style.configure(
        "Card.TLabel", background="#222", foreground="white", font=("Modern UI", 12)
    )
    style.configure("Link.TLabel", foreground="orange", font=("Modern UI", 12))
    style.configure(
        "Accent.TButton",
        background="orange",
        foreground="black",
        font=("Modern UI", 12),
    )
    style.configure("Close.TLabel", foreground="red", font=("Modern UI", 12))
    style.configure("Edit.TLabel", foreground="grey", font=("Modern UI", 12))
    style.configure(
        "Plus.TLabel", foreground="white", font=("Modern UI", 36), anchor="center"
    )
    style.configure(
        "green.Horizontal.TProgressbar", troughcolor="#00FF00", background="#00FF00"
    )
    style.configure(
        "orange.Horizontal.TProgressbar", troughcolor="#FFA500", background="#FFA500"
    )
    style.configure(
        "red.Horizontal.TProgressbar", troughcolor="#FF0000", background="#FF0000"
    )

    app = TimerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.hide_window)
    root.mainloop()
