"""
IEMBot Desktop

changes as of 10/1/26:

added error messages, notifs for warns/advisories, room persistence, customizable sound effects,
custom audio file selection
shh devmode is a secret with the konami cod- shit, that was sound outloud wasn't it?

AI assistance was used in the creation of these features.
"""

import html
import os
import random
import re
import subprocess
import sys
import requests

from PyQt6.QtCore import QEvent, QObject, QSettings, QThread, QUrl, pyqtSignal, Qt
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

# Base asset paths
BASE_DIR = os.path.dirname(__file__)
DEFAULT_ALERT_PATH = os.path.join(BASE_DIR, "snd", "alert.mp3")
ERRORS_DIR = os.path.join(BASE_DIR, "snd", "errors")

# Available default error sound options mapped to filenames
ERROR_SOUND_MAP = {
    "Wilhelm Scream": "wilhelm.mp3",
    "Explosion": "explode.mp3",
    "Odd Explosion": "oddExplode.mp3",
    "HyperLaser Fire": "HypLaser_Fire.ogg",
}

# Global Dev Mode State & Active MIDI Process Handle
MIDI_DEV_MODE_ENABLED = False
CURRENT_TIMIDITY_PROC = None


def clean_xml_tags(text):
    """Strips XML/HTML tags and namespaces to leave clean raw text."""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def stop_midi_playback():
    """Stops any active TiMidity MIDI playback process."""
    global CURRENT_TIMIDITY_PROC
    if CURRENT_TIMIDITY_PROC is not None:
        try:
            CURRENT_TIMIDITY_PROC.terminate()
            CURRENT_TIMIDITY_PROC.wait(timeout=1)
        except Exception:
            pass
        CURRENT_TIMIDITY_PROC = None


def play_audio_file(file_path, media_player):
    """
    Plays audio files natively via Qt QMediaPlayer, or forks TiMidity exclusively
    if the target is a .mid / .midi file using the configured SoundFont.
    """
    global CURRENT_TIMIDITY_PROC

    if not file_path or not os.path.exists(file_path):
        QApplication.beep()
        return

    ext = os.path.splitext(file_path)[1].lower()

    if ext in [".mid", ".midi"]:
        try:
            stop_midi_playback()

            settings = QSettings("IEMBotDesktop", "IEMBotClient")
            soundfont_path = settings.value("soundfont_path", "", type=str)

            cmd = ["timidity"]

            # If user configured a valid SoundFont in Settings, pass it via -x
            if soundfont_path and os.path.exists(soundfont_path):
                cmd.extend(["-x", f"soundfont {soundfont_path}"])

            cmd.append(file_path)

            # Launch TiMidity asynchronously
            CURRENT_TIMIDITY_PROC = subprocess.Popen(cmd)

        except Exception as e:
            print(f"[TiMidity Error]: {e}")
            QApplication.beep()
    else:
        # Standard QMediaPlayer playback for mp3, wav, ogg
        media_player.setSource(QUrl.fromLocalFile(file_path))
        media_player.setPosition(0)
        media_player.play()


class IEMBotNotifier:
    def __init__(self):
        self.app_name = "IEMBot Desktop"
        self.icon_path = "/usr/share/pixmaps/iembot-desktop.png"

        if not os.path.exists(self.icon_path):
            self.icon_path = os.path.join(BASE_DIR, "icon.png")

    def send_warning_alert(self, summary, full_text, sound_path=None):
        try:
            plain_summary = clean_xml_tags(summary)
            plain_body = clean_xml_tags(full_text)

            cmd = [
                "notify-send",
                "-a",
                self.app_name,
                "-u",
                "critical",
                plain_summary,
                plain_body,
            ]
            if os.path.exists(self.icon_path):
                cmd.extend(["-i", self.icon_path])

            # Attach notification sound hint if sound file exists and isn't a MIDI
            if sound_path and os.path.exists(sound_path):
                ext = os.path.splitext(sound_path)[1].lower()
                if ext not in [".mid", ".midi"]:
                    cmd.extend(["--hint=string:sound-file:" + sound_path])

            subprocess.Popen(cmd)
        except Exception as e:
            print(f"[Notifier Error] Failed to send warning notification: {e}")

    def send_system_error(self, title, error_message):
        try:
            subprocess.Popen(
                [
                    "notify-send",
                    "-a",
                    self.app_name,
                    "-u",
                    "critical",
                    f"IEMBot Error: {title}",
                    error_message,
                ]
            )
        except Exception as e:
            print(f"[Notifier Error] Failed to send error notification: {e}")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            "Settings" + (" [DEV MODE: UNLOCKED]" if MIDI_DEV_MODE_ENABLED else "")
        )
        self.setMinimumWidth(500)

        self.settings = QSettings("IEMBotDesktop", "IEMBotClient")

        self.test_player = QMediaPlayer()
        self.test_audio_output = QAudioOutput()
        self.test_player.setAudioOutput(self.test_audio_output)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # --- Warning Alert Sound Selection ---
        alert_row = QHBoxLayout()
        self.alert_combo = QComboBox()
        self.alert_combo.addItem("Default Alert")

        saved_alert_type = self.settings.value("alert_sound_type", "Default Alert", type=str)
        self.custom_alert_path = self.settings.value("custom_alert_path", "", type=str)

        if self.custom_alert_path and os.path.exists(self.custom_alert_path):
            filename = os.path.basename(self.custom_alert_path)
            self.alert_combo.addItem(f"Custom File ({filename})...")
        else:
            self.alert_combo.addItem("Custom File...")

        if saved_alert_type.startswith("Custom File") and self.custom_alert_path:
            self.alert_combo.setCurrentIndex(1)

        self.alert_combo.currentIndexChanged.connect(self.handle_alert_selection)
        alert_row.addWidget(self.alert_combo)

        self.test_alert_btn = QPushButton("▶ Test")
        self.test_alert_btn.setFixedWidth(70)
        self.test_alert_btn.clicked.connect(self.test_alert_sound)
        alert_row.addWidget(self.test_alert_btn)

        form_layout.addRow("<b>Warning Alert Sound:</b>", alert_row)

        # --- Error Sound Selection ---
        error_row = QHBoxLayout()
        self.error_combo = QComboBox()
        for label in ERROR_SOUND_MAP.keys():
            self.error_combo.addItem(label)

        saved_error_type = self.settings.value("error_sound_type", "Wilhelm Scream", type=str)
        self.custom_error_path = self.settings.value("custom_error_path", "", type=str)

        if self.custom_error_path and os.path.exists(self.custom_error_path):
            filename = os.path.basename(self.custom_error_path)
            self.error_combo.addItem(f"Custom File ({filename})...")
        else:
            self.error_combo.addItem("Custom File...")

        if saved_error_type.startswith("Custom File") and self.custom_error_path:
            self.error_combo.setCurrentText(f"Custom File ({os.path.basename(self.custom_error_path)})...")
        elif saved_error_type in ERROR_SOUND_MAP:
            self.error_combo.setCurrentText(saved_error_type)

        self.error_combo.currentIndexChanged.connect(self.handle_error_selection)
        error_row.addWidget(self.error_combo)

        self.test_error_btn = QPushButton("▶ Test")
        self.test_error_btn.setFixedWidth(70)
        self.test_error_btn.clicked.connect(self.test_error_sound)
        error_row.addWidget(self.test_error_btn)

        form_layout.addRow("<b>Error Sound:</b>", error_row)

        layout.addLayout(form_layout)

        # --- DEV TOOLS SECTION (Unlocked via Konami Code) ---
        if MIDI_DEV_MODE_ENABLED:
            dev_box = QGroupBox("🛠️ Developer Tools (SECRET SHHHH 🤫)")
            dev_layout = QFormLayout(dev_box)

            # SoundFont Picker
            sf_row = QHBoxLayout()
            self.sf_input = QLineEdit()
            self.sf_input.setPlaceholderText("System Default / None")
            saved_sf = self.settings.value("soundfont_path", "", type=str)
            self.sf_input.setText(saved_sf)
            sf_row.addWidget(self.sf_input)

            self.sf_browse_btn = QPushButton("Browse...")
            self.sf_browse_btn.clicked.connect(self.browse_soundfont)
            sf_row.addWidget(self.sf_browse_btn)

            dev_layout.addRow("<b>SoundFont (.sf2):</b>", sf_row)

            # MIDI Control Buttons (Test & Stop)
            midi_btn_row = QHBoxLayout()
            self.test_midi_btn = QPushButton("▶ Test Current MIDI")
            self.test_midi_btn.clicked.connect(self.test_midi_file)
            midi_btn_row.addWidget(self.test_midi_btn)

            self.stop_midi_btn = QPushButton("⏹ Stop MIDI")
            self.stop_midi_btn.clicked.connect(stop_midi_playback)
            midi_btn_row.addWidget(self.stop_midi_btn)

            dev_layout.addRow("<b>MIDI Controls:</b>", midi_btn_row)

            # Notification Test Button
            notif_btn_row = QHBoxLayout()
            self.force_notif_btn = QPushButton("🔔 Test Force Notification")
            self.force_notif_btn.clicked.connect(self.force_test_notification)
            notif_btn_row.addWidget(self.force_notif_btn)

            dev_layout.addRow("<b>Notification Tester:</b>", notif_btn_row)

            layout.addWidget(dev_box)

        # Save Button
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_settings)
        layout.addWidget(self.save_btn)

    def browse_soundfont(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SoundFont File",
            "",
            "SoundFont Files (*.sf2)",
        )
        if file_path:
            self.sf_input.setText(file_path)

    def handle_alert_selection(self):
        if self.alert_combo.currentText().startswith("Custom File"):
            filter_str = (
                "Audio Files (*.mp3 *.wav *.ogg *.mid *.midi)"
                if MIDI_DEV_MODE_ENABLED
                else "Audio Files (*.mp3 *.wav *.ogg)"
            )
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Custom Alert Sound",
                "",
                filter_str,
            )
            if file_path:
                self.custom_alert_path = file_path
                filename = os.path.basename(file_path)
                self.alert_combo.setItemText(1, f"Custom File ({filename})...")
            else:
                self.alert_combo.setCurrentIndex(0)

    def handle_error_selection(self):
        if self.error_combo.currentText().startswith("Custom File"):
            filter_str = (
                "Audio Files (*.mp3 *.wav *.ogg *.mid *.midi)"
                if MIDI_DEV_MODE_ENABLED
                else "Audio Files (*.mp3 *.wav *.ogg)"
            )
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Custom Error Sound",
                "",
                filter_str,
            )
            if file_path:
                self.custom_error_path = file_path
                filename = os.path.basename(file_path)
                custom_label = f"Custom File ({filename})..."

                # Update or append item
                if self.error_combo.count() > len(ERROR_SOUND_MAP):
                    self.error_combo.setItemText(len(ERROR_SOUND_MAP), custom_label)
                else:
                    self.error_combo.addItem(custom_label)
            else:
                self.error_combo.setCurrentIndex(0)

    def test_alert_sound(self):
        sound_type = self.alert_combo.currentText()
        sound_path = DEFAULT_ALERT_PATH

        if sound_type.startswith("Custom File") and self.custom_alert_path:
            sound_path = self.custom_alert_path

        play_audio_file(sound_path, self.test_player)

    def test_error_sound(self):
        sound_type = self.error_combo.currentText()
        sound_path = None

        if sound_type.startswith("Custom File") and self.custom_error_path:
            sound_path = self.custom_error_path
        elif sound_type in ERROR_SOUND_MAP:
            sound_path = os.path.join(ERRORS_DIR, ERROR_SOUND_MAP[sound_type])

        play_audio_file(sound_path, self.test_player)

    def test_midi_file(self):
        """Finds any selected .mid/.midi file across Alert or Error sound selections and plays it."""
        midi_paths = []
        for path in [self.custom_alert_path, self.custom_error_path]:
            if path and path.lower().endswith((".mid", ".midi")) and os.path.exists(path):
                midi_paths.append(path)

        if midi_paths:
            play_audio_file(midi_paths[0], self.test_player)
        else:
            QMessageBox.warning(
                self,
                "No MIDI File Found",
                "Please select a .mid / .midi file in either the Alert or Error custom sound setting first!",
            )

    def force_test_notification(self):
        """Fires a forced desktop notification passing the currently configured sound path."""
        if random.randint(1, 10) == 1:
            body = "NO WORK LOOSER!!!111"
        else:
            body = "Test!"

        sound_path = DEFAULT_ALERT_PATH
        if self.alert_combo.currentText().startswith("Custom File") and self.custom_alert_path:
            sound_path = self.custom_alert_path

        notifier = IEMBotNotifier()
        notifier.send_warning_alert(summary="IEMBot Dev Test", full_text=body, sound_path=sound_path)

    def save_settings(self):
        self.settings.setValue("alert_sound_type", self.alert_combo.currentText())
        self.settings.setValue("custom_alert_path", self.custom_alert_path)

        self.settings.setValue("error_sound_type", self.error_combo.currentText())
        self.settings.setValue("custom_error_path", self.custom_error_path)

        if MIDI_DEV_MODE_ENABLED:
            self.settings.setValue("soundfont_path", self.sf_input.text().strip())

        self.accept()


class IEMBotWorker(QThread):
    new_messages = pyqtSignal(list, bool)
    network_error = pyqtSignal(str)

    def __init__(self, room_name):
        super().__init__()
        self.room_name = room_name
        self.running = True
        self.session = requests.Session()
        self.initial_fetch = True
        self.has_notified_error = False
        self.failed_consecutive_attempts = 0

    def run(self):
        seqnum = 0

        while self.running:
            try:
                url = f"https://weather.im/iembot-json/room/{self.room_name}?seqnum={seqnum}"
                res = self.session.get(url, timeout=15)

                if res.status_code == 200:
                    data = res.json()
                    msgs = data.get("messages", [])

                    self.failed_consecutive_attempts = 0
                    self.has_notified_error = False

                    if msgs:
                        raw_batch = []
                        formatted_batch = []

                        for msg in msgs:
                            seqnum = max(seqnum, msg.get("seqnum", 0) + 1)
                            author = msg.get("author", "iembot")
                            room_name = msg.get("room", self.room_name)
                            raw_log = (
                                msg.get("log")
                                or msg.get("message")
                                or msg.get("text")
                                or ""
                            )

                            if raw_log:
                                clean_text = clean_xml_tags(str(raw_log))

                                if not clean_text:
                                    continue

                                raw_batch.append(clean_text)

                                formatted = (
                                    f"<div>"
                                    f'<b style="color: #2b5b84;">[{author} in {room_name}]:</b> {clean_text}'
                                    f"</div><br>"
                                )
                                formatted_batch.append(formatted)

                        if formatted_batch:
                            self.new_messages.emit(
                                list(zip(formatted_batch, raw_batch)),
                                self.initial_fetch,
                            )

                    if self.initial_fetch:
                        self.initial_fetch = False

                else:
                    self._handle_failure(f"Server returned status code {res.status_code}")

            except requests.RequestException:
                self._handle_failure("Connection lost to weather.im servers.")

            for _ in range(50):
                if not self.running:
                    break
                self.msleep(100)

    def _handle_failure(self, message):
        self.failed_consecutive_attempts += 1

        if self.initial_fetch:
            self.initial_fetch = False

        if self.failed_consecutive_attempts >= 3 and not self.has_notified_error:
            if self.running:
                self.network_error.emit(message)
                self.has_notified_error = True

    def stop(self):
        self.running = False
        self.session.close()


class KonamiFilter(QObject):
    """Global event filter capturing the Konami Code anywhere without leaking into text boxes."""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.konami_code = [
            Qt.Key.Key_Up,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Down,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_B,
            Qt.Key.Key_A,
        ]
        self.konami_index = 0

    def eventFilter(self, obj, event):
        global MIDI_DEV_MODE_ENABLED

        if event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if event.text().lower() == "b":
                key = Qt.Key.Key_B
            elif event.text().lower() == "a":
                key = Qt.Key.Key_A

            if key == self.konami_code[self.konami_index]:
                self.konami_index += 1

                if self.konami_index == len(self.konami_code):
                    MIDI_DEV_MODE_ENABLED = True
                    self.konami_index = 0

                    sound_path = self.main_window.get_active_alert_sound_path()

                    self.main_window.notifier.send_warning_alert(
                        summary="IEMBot Developer Mode",
                        full_text="🎮 Developer Mode Enabled! Open Settings to access Dev Tools.",
                        sound_path=sound_path,
                    )

                    QMessageBox.information(
                        self.main_window,
                        "Dev Mode Unlocked!",
                        "🎮 KONAMI CODE DETECTED!\n\nDeveloper Mode is now ENABLED! (SHHHH 🤫)\n\nOpen ⚙ Settings to access the new Developer Tools section.",
                    )

                return True
            else:
                self.konami_index = 0

        return super().eventFilter(obj, event)


class IEMBotWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("/usr/share/pixmaps/iembot-desktop.png"))
        self.setWindowTitle("IEMBot Desktop")
        self.resize(800, 500)

        self.notifier = IEMBotNotifier()
        self.settings = QSettings("IEMBotDesktop", "IEMBotClient")

        self.alert_player = QMediaPlayer()
        self.alert_audio_output = QAudioOutput()
        self.alert_player.setAudioOutput(self.alert_audio_output)

        self.error_player = QMediaPlayer()
        self.error_audio_output = QAudioOutput()
        self.error_player.setAudioOutput(self.error_audio_output)

        central = QWidget()
        layout = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Room:</b> #"))

        last_room = self.settings.value("last_room", "botstalk", type=str)
        self.room_input = QLineEdit(last_room)
        top_bar.addWidget(self.room_input)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.start_monitoring)
        top_bar.addWidget(self.connect_btn)

        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        top_bar.addWidget(self.settings_btn)

        layout.addLayout(top_bar)

        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self.open_link)
        self.browser.setStyleSheet("font-family: monospace; font-size: 13px;")
        layout.addWidget(self.browser)

        self.setCentralWidget(central)

        self.worker = None
        self.start_monitoring()

    def get_active_alert_sound_path(self):
        sound_type = self.settings.value("alert_sound_type", "Default Alert", type=str)
        sound_path = DEFAULT_ALERT_PATH

        if sound_type.startswith("Custom File"):
            custom_path = self.settings.value("custom_alert_path", "", type=str)
            if custom_path and os.path.exists(custom_path):
                sound_path = custom_path

        return sound_path

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def start_monitoring(self):
        room = self.room_input.text().strip().lower()
        if not room:
            return

        self.settings.setValue("last_room", room)

        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(1000)
            self.worker = None

        self.browser.clear()
        self.browser.append(f"<b><i>Connected to:</i></b> #{room}")

        self.worker = IEMBotWorker(room)
        self.worker.new_messages.connect(self.handle_incoming)
        self.worker.network_error.connect(self.handle_network_error)
        self.worker.start()

    def play_warning_sound(self):
        sound_path = self.get_active_alert_sound_path()
        play_audio_file(sound_path, self.alert_player)

    def handle_incoming(self, batch_data, is_initial_fetch):
        cursor = self.browser.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)

        url_pattern = re.compile(r'(https?://[^\s<>"]+)')
        alert_pattern = re.compile(
            r"\b(warning|advisory|watch|issues|statement|emergency|discussion)\b",
            re.IGNORECASE,
        )

        sound_path = self.get_active_alert_sound_path()

        for html_msg, raw_text in reversed(batch_data):
            clickable_msg = url_pattern.sub(
                r'<a href="\1" style="color: #0066cc;">\1</a>', html_msg
            )
            cursor.insertHtml(clickable_msg)

            if not is_initial_fetch and alert_pattern.search(raw_text):
                self.notifier.send_warning_alert(
                    summary="IEMBot Alert", full_text=raw_text, sound_path=sound_path
                )

        scrollbar = self.browser.verticalScrollBar()
        scrollbar.setValue(0)

        if not is_initial_fetch:
            self.play_warning_sound()

    def handle_network_error(self, error_message):
        self.notifier.send_system_error("Network Failure", error_message)

        sound_type = self.settings.value("error_sound_type", "Wilhelm Scream", type=str)
        sound_path = None

        if sound_type.startswith("Custom File"):
            custom_path = self.settings.value("custom_error_path", "", type=str)
            if custom_path and os.path.exists(custom_path):
                sound_path = custom_path
        elif sound_type in ERROR_SOUND_MAP:
            sound_path = os.path.join(ERRORS_DIR, ERROR_SOUND_MAP[sound_type])

        play_audio_file(sound_path, self.error_player)

    def open_link(self, url: QUrl):
        QDesktopServices.openUrl(url)

    def closeEvent(self, event):
        stop_midi_playback()
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(500)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IEMBotWindow()

    # Install global event filter for secret Konami Code
    konami_filter = KonamiFilter(window)
    app.installEventFilter(konami_filter)

    window.show()
    sys.exit(app.exec())
