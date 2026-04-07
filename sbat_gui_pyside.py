# sbat_gui_qt.py
import requests
import pytz
import sys
import threading
import queue  # For thread-safe communication
from constants import *
from auth import get_token, authenticate_with_browser, load_cached_token, test_token

# --- PySide6 Imports ---
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QSizePolicy,
)
from PySide6.QtCore import QTimer, Qt, Slot  # Import Slot explicitly
from PySide6.QtGui import QTextCursor, QFont  # Import QFont


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
        now_brussels = datetime.now(brussels_tz)
        hour_in_brussels = now_brussels.hour
        # New slots get added at these times usually
        if hour_in_brussels == 7 or hour_in_brussels == 16:
            log_message(
                f"Brussels time {now_brussels.strftime('%H:%M')}. Using short sleep (30s)."
            )
            return 30
    except Exception as e:
        log_message(
            f"Warning: Could not determine Brussels time ({e}). Defaulting to 120s sleep."
        )
    return 120


# --- Qt Specific Helpers ---
def show_error_dialog_qt(title, message, parent=None):
    """Displays a Qt error message dialog."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


def show_info_dialog_qt(title, message, parent=None):
    """Displays a Qt info message dialog."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Information)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)  # Use setText for primary message if short
    # msg_box.setInformativeText(message) # Use for longer secondary text if needed
    msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
    msg_box.exec()


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
                break  # Exit loop immediately if stop is requested

            payload = PAYLOAD_BASE.copy()
            payload["examCenterId"] = center_id
            # Ensure start date is always calculated relative to now
            payload["startDate"] = (
                f"{(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}T00:00"
            )

            try:
                response = requests.post(
                    AVAILABLE_URL, headers=headers, json=payload, timeout=20
                )

                if response.status_code == 200:
                    if data := response.json():
                        center_dates = {
                            # Use YYYY-MM-DD format consistently
                            center_name + " " + slot.get("from", "")[:10]
                            for slot in data
                            if slot.get("from")  # Ensure 'from' exists
                        }
                        current_run_dates.update(center_dates)
                        # Find dates for this center that haven't been seen *at all* before
                        new_dates_for_center = center_dates - all_dates_seen
                        if new_dates_for_center:
                            # Store the raw data for formatting later
                            centers_with_new_data[center_name] = data

                elif response.status_code == 401:
                    log_message(
                        f"Authorization token expired or invalid (checking {center_name}). Re-authenticating..."
                    )
                    auth_needed = True
                    break  # Break inner loop to re-authenticate

                else:
                    # Raise an exception for non-200/401 status codes
                    response.raise_for_status()

            except requests.exceptions.HTTPError as http_err:
                log_message(
                    f"HTTP error checking {center_name}: {http_err.response.status_code} - {http_err.response.text[:200]}..."
                )
                request_failed_in_cycle = True
            except requests.exceptions.RequestException as req_err:
                log_message(f"Network error checking {center_name}: {req_err}")
                request_failed_in_cycle = True
            except Exception as e:
                log_message(f"Unexpected error checking {center_name}: {e}")
                request_failed_in_cycle = True

        # --- After checking all centers ---

        if stop_event.is_set():
            break  # Exit outer loop if stop is requested

        if auth_needed:
            log_message("Token expired. Please re-authenticate via itsme.")
            gui_queue.put("NEEDS_REAUTH")
            break

        # Process results only if the cycle didn't fail and wasn't interrupted for auth
        if not request_failed_in_cycle:
            # Find dates found in this run that were not found in the *previous* run
            newly_found_dates_since_last = current_run_dates - previous_dates

            if centers_with_new_data and newly_found_dates_since_last:
                center_messages = []
                log_message("--- NEW DATES FOUND! ---")
                # Sort centers by name for consistent output
                for center in sorted(centers_with_new_data.keys()):
                    data = centers_with_new_data[center]
                    # Extract unique dates found *in this run* for this center
                    dates_in_run = sorted(
                        list(
                            {
                                slot.get("from", "")[:10]
                                for slot in data
                                if slot.get("from")
                            }
                        )
                    )
                    # Filter to show only dates that are actually new since the last check
                    new_dates_output = [
                        d
                        for d in dates_in_run
                        if f"{center} {d}" in newly_found_dates_since_last
                    ]

                    if new_dates_output:
                        msg = f"  {center}: {', '.join(new_dates_output)}"
                        center_messages.append(msg)
                        log_message(msg)  # Log each center individually

                log_message("-------------------------")

                if center_messages:
                    # Send message to GUI thread to show the dialog
                    dialog_message = "\n".join(center_messages)
                    gui_queue.put(("SHOW_INFO", dialog_message))
                else:
                    # This case might happen if data structure changes or filtering is too strict
                    log_message(
                        "New data detected but couldn't format message (or no truly new dates)."
                    )

                # Update seen dates *after* processing
                all_dates_seen.update(current_run_dates)
                previous_dates = current_run_dates.copy()

            elif not newly_found_dates_since_last and not request_failed_in_cycle:
                log_message(
                    f"No new dates detected. Total unique dates seen so far: {len(all_dates_seen)}"
                )
                # Still update previous_dates even if no new ones, in case some disappeared
                previous_dates = current_run_dates.copy()
                # Ensure all_dates_seen includes everything from this run too
                all_dates_seen.update(current_run_dates)
            else:
                # This case covers request_failed_in_cycle = True
                log_message("Check cycle completed with errors. Will retry.")
                # Do not update previous_dates or all_dates_seen if errors occurred

        # --- Sleep before next cycle ---
        if not stop_event.is_set():
            sleep_duration = get_sleep_time()
            log_message(f"Sleeping for {sleep_duration} seconds...")
            stop_event.wait(sleep_duration)  # Use wait() for interruptible sleep

    # --- End of While Loop ---
    log_message("Checking loop stopped.")
    # Send stop message only if not already stopped by auth failure
    if not auth_needed:  # Avoid sending duplicate stop messages
        # Check if queue is not full before putting (optional, good practice)
        if not gui_queue.full():
            gui_queue.put("STOPPED_NORMAL")


# --- Qt Application Class ---
class SbatCheckerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SBAT Exam Slot Checker")
        self.setGeometry(100, 100, 600, 450)  # x, y, width, height

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout(self.central_widget)

        # --- Authentication Group ---
        auth_group = QGroupBox("Authentication")
        auth_layout = QVBoxLayout(auth_group)

        # itsme login button
        itsme_layout = QHBoxLayout()
        self.itsme_button = QPushButton("Login with itsme")
        self.itsme_button.clicked.connect(self.on_itsme_login)
        self.itsme_button.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        self.auth_status_label = QLabel("")
        itsme_layout.addWidget(self.itsme_button)
        itsme_layout.addWidget(self.auth_status_label)
        itsme_layout.addStretch()
        auth_layout.addLayout(itsme_layout)

        # Manual token paste fallback
        token_layout = QHBoxLayout()
        token_label = QLabel("Or paste token:")
        self.token_entry = QLineEdit()
        self.token_entry.setPlaceholderText("Bearer token from browser DevTools")
        self.token_paste_button = QPushButton("Use Token")
        self.token_paste_button.clicked.connect(self.on_paste_token)
        token_layout.addWidget(token_label)
        token_layout.addWidget(self.token_entry)
        token_layout.addWidget(self.token_paste_button)
        auth_layout.addLayout(token_layout)

        self.main_layout.addWidget(auth_group)

        # --- Control Area ---
        self.start_stop_button = QPushButton("Start Checking")
        self.start_stop_button.clicked.connect(self.on_start_stop_clicked)
        self.start_stop_button.setEnabled(False)  # Disabled until authenticated
        self.start_stop_button.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        self.main_layout.addWidget(
            self.start_stop_button, alignment=Qt.AlignmentFlag.AlignLeft
        )

        # --- Log Area ---
        log_group = QGroupBox("Log Output")
        log_layout = QVBoxLayout(log_group)  # Use QVBoxLayout inside group

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        # Make log area expand vertically and horizontally
        log_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.log_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        self.main_layout.addWidget(log_group)

        # --- Initial Setup ---
        cached = load_cached_token()
        if cached:
            self.append_log("Cached token found. Testing validity...")
            # Test in background to avoid blocking GUI
            threading.Thread(target=self._test_cached_token, args=(cached,), daemon=True).start()
        else:
            self.append_log("No cached token. Please login with itsme or paste a token.")

        # --- Queue Timer ---
        self.queue_timer = QTimer(self)
        self.queue_timer.timeout.connect(self.process_gui_queue_qt)
        self.queue_timer.start(100)  # Check queue every 100ms

    def append_log(self, message):
        """Appends a message to the Qt QTextEdit."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"{timestamp} - {message}")
        # Auto-scroll to the end
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        # self.log_view.ensureCursorVisible() # Alternative scrolling method

    def _test_cached_token(self, token):
        """Test cached token in background thread."""
        global auth_token
        if test_token(token):
            auth_token = token
            gui_queue.put("CACHED_TOKEN_VALID")
        else:
            gui_queue.put("CACHED_TOKEN_INVALID")

    @Slot()
    def on_itsme_login(self):
        """Launch browser-based itsme authentication."""
        self.itsme_button.setEnabled(False)
        self.auth_status_label.setText("Opening browser... Confirm on itsme app.")
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

    @Slot()
    def on_paste_token(self):
        """Handle manual token paste."""
        global auth_token
        token = self.token_entry.text().strip()
        if not token:
            show_error_dialog_qt("Input Required", "Please paste a Bearer token.", parent=self)
            return
        self.append_log("Testing pasted token...")
        self.token_paste_button.setEnabled(False)
        threading.Thread(target=self._test_pasted_token, args=(token,), daemon=True).start()

    def _test_pasted_token(self, token):
        """Test pasted token in background thread."""
        global auth_token
        if test_token(token):
            auth_token = token
            from auth import save_cached_token
            save_cached_token(token)
            gui_queue.put("PASTE_TOKEN_VALID")
        else:
            gui_queue.put("PASTE_TOKEN_INVALID")

    @Slot()
    def process_gui_queue_qt(self):
        """Processes messages from the queue to update the GUI."""
        try:
            while not gui_queue.empty():
                message_data = gui_queue.get_nowait()

                if message_data == "CACHED_TOKEN_VALID":
                    self.append_log("Cached token is valid. Ready to start checking.")
                    self.auth_status_label.setText("Authenticated (cached token)")
                    self.start_stop_button.setEnabled(True)
                elif message_data == "CACHED_TOKEN_INVALID":
                    self.append_log("Cached token expired. Please re-authenticate.")
                    self.auth_status_label.setText("")

                elif message_data == "ITSME_AUTH_SUCCESS":
                    self.append_log("itsme authentication successful!")
                    self.auth_status_label.setText("Authenticated via itsme")
                    self.itsme_button.setEnabled(True)
                    self.start_stop_button.setEnabled(True)
                elif message_data == "ITSME_AUTH_FAILURE":
                    self.append_log("itsme authentication failed or timed out.")
                    self.auth_status_label.setText("Authentication failed")
                    self.itsme_button.setEnabled(True)

                elif message_data == "PASTE_TOKEN_VALID":
                    self.append_log("Pasted token is valid. Ready to start checking.")
                    self.auth_status_label.setText("Authenticated (pasted token)")
                    self.token_paste_button.setEnabled(True)
                    self.start_stop_button.setEnabled(True)
                elif message_data == "PASTE_TOKEN_INVALID":
                    self.append_log("Pasted token is invalid or expired.")
                    show_error_dialog_qt("Invalid Token", "The pasted token is not valid.", parent=self)
                    self.token_paste_button.setEnabled(True)

                elif message_data == "NEEDS_REAUTH":
                    self.append_log("Token expired during checks. Please re-authenticate.")
                    self.reset_gui_controls()
                elif message_data == "STOPPED_AUTH_FAILURE":
                    self.append_log("Authentication failed during checks. Controls reset.")
                    self.reset_gui_controls()
                elif message_data == "STOPPED_NORMAL":
                    self.append_log("Checker stopped normally. Controls reset.")
                    self.reset_gui_controls()
                elif isinstance(message_data, tuple) and message_data[0] == "SHOW_INFO":
                    show_info_dialog_qt("NEW DATES FOUND", message_data[1], parent=self)
                elif isinstance(message_data, str):
                    self.append_log(message_data)

        except queue.Empty:
            pass

    @Slot()
    def on_start_stop_clicked(self):
        if self.start_stop_button.text() == "Start Checking":
            self.start_checking()
        else:
            self.stop_checking()

    def start_checking(self):
        global checking_thread, stop_event, all_dates_seen, previous_dates

        if checking_thread and checking_thread.is_alive():
            self.append_log("Checker is already running.")
            return

        if not auth_token:
            show_error_dialog_qt(
                "Not Authenticated",
                "Please login with itsme or paste a valid token first.",
                parent=self,
            )
            return

        stop_event.clear()
        all_dates_seen = set()
        previous_dates = set()

        self.itsme_button.setEnabled(False)
        self.token_entry.setEnabled(False)
        self.token_paste_button.setEnabled(False)
        self.start_stop_button.setText("Stop Checking")

        checking_thread = threading.Thread(target=run_checks, daemon=True)
        checking_thread.start()

    def stop_checking(self):
        global checking_thread
        if checking_thread and checking_thread.is_alive():
            self.append_log("Stopping checker...")
            stop_event.set()
            self.start_stop_button.setText("Stopping...")
            self.start_stop_button.setEnabled(False)
        else:
            self.append_log("Checker is not running.")
            self.reset_gui_controls()

    def reset_gui_controls(self):
        """Resets the GUI controls to the 'stopped' state."""
        self.itsme_button.setEnabled(True)
        self.token_entry.setEnabled(True)
        self.token_paste_button.setEnabled(True)
        self.start_stop_button.setText("Start Checking")
        self.start_stop_button.setEnabled(bool(auth_token))

    def closeEvent(self, event):
        """Handles window close event."""
        global checking_thread
        self.append_log("Close requested.")
        if self.queue_timer:
            self.queue_timer.stop()  # Stop the queue timer

        if checking_thread and checking_thread.is_alive():
            self.append_log("Stopping checker thread...")
            stop_event.set()
            # Give the thread a moment to stop - adjust timeout as needed
            checking_thread.join(timeout=1.5)
            if checking_thread.is_alive():
                self.append_log("Warning: Checker thread did not stop gracefully.")

        self.append_log("Exiting application.")
        event.accept()  # Accept the close event


# --- Main Execution ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = SbatCheckerWindow()
    win.show()
    sys.exit(app.exec())
