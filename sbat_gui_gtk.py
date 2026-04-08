import requests
import pytz
import sys
import threading
import queue  # For thread-safe communication
from constants import *
from auth import authenticate_with_browser, test_token

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
def log_message(message):
    """Safely adds a message to the GUI log area from any thread via queue."""
    gui_queue.put(message)


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
def run_checks():
    """The main checking loop running in the background thread."""
    global auth_token, all_dates_seen, previous_dates

    if not auth_token:
        log_message("No valid token. Stopping checks.")
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
            log_message("Token expired. Please re-authenticate via itsme.")
            gui_queue.put("NEEDS_REAUTH")
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

        # --- Authentication Frame ---
        auth_frame = Gtk.Frame(label="Authentication")
        vbox.pack_start(auth_frame, False, True, 0)

        auth_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin=10)
        auth_frame.add(auth_vbox)

        # itsme login row
        itsme_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        auth_vbox.pack_start(itsme_box, False, True, 0)

        self.itsme_button = Gtk.Button(label="Login with itsme")
        self.itsme_button.connect("clicked", self.on_itsme_login)
        itsme_box.pack_start(self.itsme_button, False, False, 0)

        self.auth_status_label = Gtk.Label(label="")
        itsme_box.pack_start(self.auth_status_label, False, False, 0)

        # Token paste row
        token_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        auth_vbox.pack_start(token_box, False, True, 0)

        token_label = Gtk.Label(label="Or paste token:")
        token_box.pack_start(token_label, False, False, 0)

        self.token_entry = Gtk.Entry()
        self.token_entry.set_placeholder_text("Bearer token from browser DevTools")
        self.token_entry.set_hexpand(True)
        token_box.pack_start(self.token_entry, True, True, 0)

        self.token_paste_button = Gtk.Button(label="Use Token")
        self.token_paste_button.connect("clicked", self.on_paste_token)
        token_box.pack_start(self.token_paste_button, False, False, 0)

        # --- Control Area ---
        control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vbox.pack_start(control_box, False, True, 0)

        self.check_button = Gtk.Button(label="Start Checking")
        self.check_button.set_sensitive(False)
        self.check_button.connect("clicked", self.on_check_button_clicked)
        control_box.pack_start(self.check_button, False, False, 0)

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
        self.append_log("Please login with itsme or paste a token to start.")

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

    def on_itsme_login(self, widget):
        """Launch browser-based itsme authentication."""
        self.itsme_button.set_sensitive(False)
        self.auth_status_label.set_text("Opening browser... Confirm on itsme app.")
        self.append_log("Starting itsme authentication...")
        threading.Thread(target=self._do_itsme_auth, daemon=True).start()

    def _do_itsme_auth(self):
        """Run itsme browser auth in background thread."""
        global auth_token
        token = authenticate_with_browser(log_fn=log_message)
        if token:
            auth_token = token
            gui_queue.put("ITSME_AUTH_SUCCESS")
        else:
            gui_queue.put("ITSME_AUTH_FAILURE")

    def on_paste_token(self, widget):
        """Handle manual token paste."""
        global auth_token
        token = self.token_entry.get_text().strip()
        if not token:
            show_error_dialog("Input Required", "Please paste a Bearer token.", parent_window=self)
            return
        self.append_log("Testing pasted token...")
        self.token_paste_button.set_sensitive(False)
        threading.Thread(target=self._test_pasted_token, args=(token,), daemon=True).start()

    def _test_pasted_token(self, token):
        """Test pasted token in background thread."""
        global auth_token
        if test_token(token):
            auth_token = token
            gui_queue.put("PASTE_TOKEN_VALID")
        else:
            gui_queue.put("PASTE_TOKEN_INVALID")

    def process_gui_queue_gtk(self):
        """Processes messages from the queue to update the GUI."""
        try:
            while True:
                message = gui_queue.get_nowait()

                if message == "ITSME_AUTH_SUCCESS":
                    self.append_log("itsme authentication successful! Starting checks...")
                    self.auth_status_label.set_text("Authenticated via itsme")
                    self.start_checking()

                elif message == "ITSME_AUTH_FAILURE":
                    self.append_log("itsme authentication failed or timed out.")
                    self.auth_status_label.set_text("Authentication failed")
                    self.itsme_button.set_sensitive(True)
                    self.token_entry.set_sensitive(True)
                    self.token_paste_button.set_sensitive(True)

                elif message == "PASTE_TOKEN_VALID":
                    self.append_log("Pasted token is valid. Starting checks...")
                    self.auth_status_label.set_text("Authenticated (pasted token)")
                    self.start_checking()

                elif message == "PASTE_TOKEN_INVALID":
                    self.append_log("Pasted token is invalid or expired.")
                    show_error_dialog("Invalid Token", "The pasted token is not valid.", parent_window=self)
                    self.token_paste_button.set_sensitive(True)

                elif message == "NEEDS_REAUTH":
                    self.append_log("Token expired. Please re-authenticate via itsme to continue.")
                    self.set_stopped_state(token_expired=True)
                elif message == "STOPPED_AUTH_FAILURE":
                    self.append_log("Authentication failed. Please re-authenticate.")
                    self.set_stopped_state(token_expired=True)
                elif message == "STOPPED_NORMAL":
                    self.append_log("Checker stopped.")
                    self.set_stopped_state(token_expired=False)
                elif isinstance(message, tuple) and message[0] == "SHOW_INFO":
                    show_info_dialog("NEW DATES FOUND", message[1], parent_window=self)
                elif isinstance(message, str):
                    self.append_log(message)
        except queue.Empty:
            pass
        return True  # Keep the timeout running

    def on_check_button_clicked(self, widget):
        if widget.get_label() == "Stop Checking":
            self.stop_checking()
        else:
            self.start_checking()

    def start_checking(self):
        global checking_thread, stop_event, all_dates_seen, previous_dates

        if checking_thread and checking_thread.is_alive():
            return

        if not auth_token:
            return

        stop_event.clear()
        all_dates_seen = set()
        previous_dates = set()

        self.itsme_button.set_sensitive(False)
        self.token_entry.set_sensitive(False)
        self.token_paste_button.set_sensitive(False)
        self.check_button.set_label("Stop Checking")
        self.check_button.set_sensitive(True)

        checking_thread = threading.Thread(target=run_checks, daemon=True)
        checking_thread.start()

    def stop_checking(self):
        global checking_thread
        if checking_thread and checking_thread.is_alive():
            self.append_log("Stopping checker...")
            stop_event.set()
            self.check_button.set_sensitive(False)
            self.check_button.set_label("Stopping...")

    def set_stopped_state(self, token_expired):
        """Update GUI after checking stops."""
        global auth_token

        if token_expired:
            auth_token = None
            self.auth_status_label.set_text("Token expired")
            self.itsme_button.set_sensitive(True)
            self.token_entry.set_sensitive(True)
            self.token_paste_button.set_sensitive(True)
            self.check_button.set_label("Start Checking")
            self.check_button.set_sensitive(False)
        else:
            self.itsme_button.set_sensitive(True)
            self.token_entry.set_sensitive(True)
            self.token_paste_button.set_sensitive(True)
            self.check_button.set_label("Start Checking")
            self.check_button.set_sensitive(bool(auth_token))

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
