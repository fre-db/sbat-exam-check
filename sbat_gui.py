import requests
import pytz
import configparser
import os
import sys
import threading
import queue  # For thread-safe communication
from constants import *

# --- GTK Imports ---
import gi  # pip install pycairo PyGObject

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango


# --- Global Variables ---
checking_thread = None
stop_event = threading.Event()
auth_token = None
all_dates_seen = set()
previous_dates = set()
gui_queue = queue.Queue()  # Queue for thread-safe GUI updates


# --- Utility Functions ---
def get_config_path():
    """Determines the correct path for the config.ini file."""
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, CONFIG_FILENAME)


def log_message(message):
    """Safely adds a message to the GUI log area from any thread via queue."""
    gui_queue.put(message)


def load_credentials_from_config():
    """Loads credentials from config.ini if it exists."""
    config_file = get_config_path()
    config = configparser.ConfigParser()
    username, password = "", ""
    if os.path.exists(config_file):
        try:
            config.read(config_file)
            username = config.get("Credentials", "username", fallback="")
            password = config.get("Credentials", "password", fallback="")
        except configparser.Error as e:
            # Can't use log_message here reliably before GUI loop starts
            print(f"[Config Load Error] {config_file}: {e}")
    return {"username": username, "password": password}


def save_credentials_to_config(username, password):
    """Saves credentials to config.ini."""
    config_file = get_config_path()
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        try:
            config.read(config_file)
        except configparser.Error as e:
            log_message(f"Warning: Could not read existing config before saving: {e}")
            config = configparser.ConfigParser()

    if "Credentials" not in config:
        config.add_section("Credentials")

    config.set("Credentials", "username", username)
    config.set("Credentials", "password", password)

    try:
        with open(config_file, "w") as configfile:
            config.write(configfile)
        log_message(f"Credentials saved to '{config_file}'.")
        return True
    except IOError as e:
        log_message(f"Error saving credentials to {config_file}: {e}")
        # Show GTK error dialog (needs main window reference)
        show_error_dialog("File Error", f"Could not save credentials:\n{e}")
        return False


def get_sleep_time() -> int:
    """Calculates sleep time based on Brussels time."""
    try:
        brussels_tz = pytz.timezone("Europe/Brussels")
        hour_in_brussels = datetime.now(brussels_tz).hour
        # New slots get added at these time usually
        if hour_in_brussels == 7 or hour_in_brussels == 16:
            return 30
    except Exception as e:
        log_message(
            f"Warning: Could not determine Brussels time ({e}). Defaulting to 120s sleep."
        )
    return 120


# --- GTK Specific Helper ---
def show_error_dialog(title, message, parent_window=None):
    """Displays a GTK error message dialog."""
    dialog = Gtk.MessageDialog(
        transient_for=parent_window,
        flags=0,
        message_type=Gtk.MessageType.ERROR,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


def show_info_dialog(title, message, parent_window=None):
    """Displays a GTK info message dialog."""
    dialog = Gtk.MessageDialog(
        transient_for=parent_window,
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(message)
    dialog.run()
    dialog.destroy()


# --- API Interaction ---


def attempt_authentication(username, password):
    """Attempts to authenticate and returns the token or None."""
    global auth_token
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    credentials = {"username": username, "password": password}
    log_message("Attempting authentication...")
    try:
        response = requests.post(
            AUTH_URL, json=credentials, headers=headers, timeout=15
        )
        if response.status_code == 200 and response.text:
            log_message("Authentication successful.")
            auth_token = response.text
            return auth_token
        else:
            log_message(
                f"Authentication failed. Status: {response.status_code}, Response: {response.text[:200]}..."
            )
            auth_token = None
            return None
    except requests.exceptions.RequestException as e:
        log_message(f"Network error during authentication: {e}")
        auth_token = None
        return None


def run_checks(username, password):
    """The main checking loop running in the background thread."""
    global auth_token, all_dates_seen, previous_dates

    if not auth_token:
        if not attempt_authentication(username, password):
            log_message("Initial authentication failed in thread. Stopping checks.")
            gui_queue.put("STOPPED_AUTH_FAILURE")
            return

    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {auth_token}",
    }

    log_message("Starting SBAT exam check loop...")
    while not stop_event.is_set():
        centers_with_new_data = {}
        current_run_dates = set()
        request_failed_in_cycle = False
        auth_needed = False

        for center_id, center_name in CENTER_IDS:
            if stop_event.is_set():
                break

            payload = PAYLOAD_BASE.copy()
            payload["examCenterId"] = center_id
            payload["startDate"] = (
                f"{(datetime.now() + timedelta(hours=24)).strftime('%Y-%m-%d')}T00:00"
            )

            try:
                response = requests.post(
                    AVAILABLE_URL, headers=headers, json=payload, timeout=20
                )

                if response.status_code == 200:
                    if data := response.json():
                        center_dates = {
                            center_name + " " + slot.get("from", "")[:10]
                            for slot in data
                        }
                        current_run_dates.update(center_dates)
                        new_dates_for_center = center_dates - all_dates_seen
                        if new_dates_for_center:
                            centers_with_new_data[center_name] = data

                elif response.status_code == 401:
                    log_message(
                        f"Authorization token expired or invalid (checking {center_name}). Re-authenticating..."
                    )
                    auth_needed = True
                    break

                else:
                    raise Exception(
                        f"PROBLEM checking {center_name}. Status: {response.status_code}, Response: {response.text[:200]}..."
                    )
            except Exception as e:
                log_message(f"Error checking {center_name}: {e}")
                request_failed_in_cycle = True

        if stop_event.is_set():
            break

        if auth_needed:
            new_token = attempt_authentication(username, password)
            if new_token:
                headers["Authorization"] = f"Bearer {new_token}"
                log_message("Re-authentication successful. Continuing checks.")
                continue
            else:
                log_message("Re-authentication failed. Stopping checks.")
                gui_queue.put("STOPPED_AUTH_FAILURE")
                break

        if not request_failed_in_cycle:
            newly_found_dates = current_run_dates - previous_dates

            if centers_with_new_data and newly_found_dates:
                center_messages = []
                for center, data in centers_with_new_data.items():
                    dates = sorted(
                        list(
                            {
                                slot.get("from", "")[:10]
                                for slot in data
                                if slot.get("from")
                            }
                        )
                    )
                    if dates:
                        center_messages.append(f"  {center}: {', '.join(dates)}")

                if center_messages:
                    log_message("--- NEW DATES FOUND! ---")
                    for msg in center_messages:
                        log_message(msg)
                    log_message("-------------------------")
                    # Send message to GUI thread to show the dialog
                    dialog_message = "\n".join(center_messages)
                    gui_queue.put(("SHOW_INFO", dialog_message))
                else:
                    log_message("New data detected but couldn't format message.")
            else:
                log_message(f"No changes detected. Seen: {len(all_dates_seen)}")
            previous_dates = current_run_dates.copy()
            all_dates_seen.update(current_run_dates)
        else:
            log_message("Check cycle completed with errors. Will retry.")

        sleep_duration = get_sleep_time()
        log_message(f"Sleeping for {sleep_duration} seconds...")
        stop_event.wait(sleep_duration)
    # --- End of While Loop ---
    log_message("Checking loop stopped.")
    if not gui_queue.full():
        gui_queue.put("STOPPED_NORMAL")


# --- GTK Application Class ---


class SbatCheckerWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="SBAT Exam Slot Checker")
        self.set_border_width(10)
        self.set_default_size(600, 450)
        self.connect("destroy", self.on_destroy)

        self.log_buffer = Gtk.TextBuffer()
        self.timeout_id = None  # To store the GLib timeout ID

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add(vbox)

        # --- Credentials Frame ---
        cred_frame = Gtk.Frame(label="Credentials")
        vbox.pack_start(cred_frame, False, True, 0)

        cred_grid = Gtk.Grid(column_spacing=10, row_spacing=5, margin=10)
        cred_frame.add(cred_grid)

        user_label = Gtk.Label(label="Username:", xalign=0)
        self.user_entry = Gtk.Entry()
        self.user_entry.set_hexpand(True)
        cred_grid.attach(user_label, 0, 0, 1, 1)
        cred_grid.attach(self.user_entry, 1, 0, 1, 1)

        pass_label = Gtk.Label(label="Password:", xalign=0)
        self.pass_entry = Gtk.Entry()
        # self.pass_entry.set_visibility(False) # Mask password
        self.pass_entry.set_hexpand(True)
        cred_grid.attach(pass_label, 0, 1, 1, 1)
        cred_grid.attach(self.pass_entry, 1, 1, 1, 1)

        # --- Control Area ---
        control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vbox.pack_start(control_box, False, True, 0)

        self.start_stop_button = Gtk.Button(label="Start Checking")
        self.start_stop_button.connect("clicked", self.on_start_stop_clicked)
        control_box.pack_start(self.start_stop_button, False, False, 0)

        # --- Log Area ---
        log_frame = Gtk.Frame(label="Log Output")
        vbox.pack_start(log_frame, True, True, 0)  # Expand and fill

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_hexpand(True)
        self.scrolled_window.set_vexpand(True)
        log_frame.add(self.scrolled_window)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_view.set_buffer(self.log_buffer)
        # Optional: Use a monospace font for logs
        font_desc = Pango.FontDescription("monospace")

        self.scrolled_window.add(self.log_view)

        # --- Initial Setup ---
        initial_creds = load_credentials_from_config()
        self.user_entry.set_text(initial_creds.get("username", ""))
        self.pass_entry.set_text(initial_creds.get("password", ""))

        if initial_creds.get("username"):
            self.append_log("Credentials loaded from config.ini.")
        else:
            self.append_log("config.ini not found or empty. Please enter credentials.")

        # Start processing the GUI update queue
        self.timeout_id = GLib.timeout_add(
            100, self.process_gui_queue_gtk
        )  # Check queue every 100ms

    def append_log(self, message):
        """Appends a message to the GTK TextView buffer."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        # Get end iterator and insert text
        end_iter = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end_iter, f"{timestamp} - {message}\n")
        # Auto-scroll to the end
        GLib.idle_add(self.scroll_to_end)  # Schedule scroll in idle time

    def scroll_to_end(self):
        """Scrolls the log view to the bottom."""
        # Get adjustment from the ScrolledWindow
        adj = self.scrolled_window.get_vadjustment()
        if adj:
            # Set the adjustment value to its upper limit to scroll down
            adj.set_value(adj.get_upper() - adj.get_page_size())
        return False  # Run only once via GLib.idle_add

    def process_gui_queue_gtk(self):
        """Processes messages from the queue to update the GUI log."""
        try:
            while True:
                message = gui_queue.get_nowait()
                if message == "STOPPED_AUTH_FAILURE":
                    self.append_log("Authentication failed. Controls reset.")
                    self.reset_gui_controls()
                elif message == "STOPPED_NORMAL":
                    self.append_log("Checker stopped normally. Controls reset.")
                    self.reset_gui_controls()
                elif isinstance(message, tuple) and message[0] == "SHOW_INFO":
                    show_info_dialog("NEW DATES FOUND", message[1], parent_window=self)
                else:
                    self.append_log(message)
        except queue.Empty:
            pass  # No messages in the queue
        # Reschedule itself - crucial!
        return True  # Keep the timeout running

    def on_start_stop_clicked(self, widget):
        """Handles the Start/Stop button click."""
        label = widget.get_label()
        if label == "Start Checking":
            self.start_checking()
        else:
            self.stop_checking()

    def start_checking(self):
        global checking_thread, stop_event, auth_token, all_dates_seen, previous_dates

        if checking_thread and checking_thread.is_alive():
            self.append_log("Checker is already running.")
            return

        user = self.user_entry.get_text()
        pwd = self.pass_entry.get_text()

        if not user or not pwd:
            show_error_dialog(
                "Input Required",
                "Please enter both username and password.",
                parent_window=self,
            )
            return

        # Reset state variables
        stop_event.clear()
        auth_token = None
        all_dates_seen = set()
        previous_dates = set()

        # Attempt initial authentication (can block GUI briefly, consider moving to thread if too long)
        token = attempt_authentication(user, pwd)
        if token:
            save_credentials_to_config(user, pwd)

            # Update GUI
            self.user_entry.set_sensitive(False)
            self.pass_entry.set_sensitive(False)
            self.start_stop_button.set_label("Stop Checking")

            # Start the background thread
            checking_thread = threading.Thread(
                target=run_checks, args=(user, pwd), daemon=True
            )
            checking_thread.start()
        else:
            show_error_dialog(
                "Authentication Failed",
                "Could not authenticate. Check details.",
            )

    def stop_checking(self):
        global checking_thread
        if checking_thread and checking_thread.is_alive():
            self.append_log("Stopping checker...")
            stop_event.set()
        else:
            self.append_log("Checker is not running.")
        # Reset GUI controls immediately
        self.reset_gui_controls()

    def reset_gui_controls(self):
        """Resets the GUI controls to the 'stopped' state."""
        self.user_entry.set_sensitive(True)
        self.pass_entry.set_sensitive(True)
        self.start_stop_button.set_label("Start Checking")
        # Don't log here, the calling function/queue message should log

    def on_destroy(self, *args):
        """Handles window close event."""
        global checking_thread
        if checking_thread and checking_thread.is_alive():
            self.append_log("Window closing, stopping checker...")
            stop_event.set()
            # Give the thread a moment to react before quitting GTK
            GLib.timeout_add_seconds(1, Gtk.main_quit)
        else:
            Gtk.main_quit()
        # Stop the GLib timeout for the queue
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None


# --- Main Execution ---
if __name__ == "__main__":
    win = SbatCheckerWindow()
    win.show_all()
    Gtk.main()
