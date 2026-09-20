import html
import sys
import os
import requests
from PyQt6.QtCore import QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextBrowser, 
    QVBoxLayout, QHBoxLayout, QWidget, QLabel, QLineEdit, QPushButton
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

# Sound file path
SOUND_PATH = os.path.join(os.path.dirname(__file__), "snd", "alert.mp3")


class IEMBotWorker(QThread):
    new_message = pyqtSignal(list)

    def __init__(self, room_name):
        super().__init__()
        self.room_name = room_name
        self.running = True
        self.session = requests.Session()

    def run(self):
        seqnum = 0  # 0 fetches all recent room history on launch
        
        while self.running:
            try:
                url = f"https://weather.im/iembot-json/room/{self.room_name}?seqnum={seqnum}"
                res = self.session.get(url, timeout=2)

                if res.status_code == 200:
                    data = res.json()
                    msgs = data.get("messages", [])

                    if msgs:
                        batch = []
                        for msg in msgs:
                            seqnum = max(seqnum, msg.get("seqnum", 0) + 1)
                            author = msg.get("author", "iembot")
                            room_name = msg.get("room", self.room_name)
                            raw_log = msg.get("log") or msg.get("message") or msg.get("text") or ""
                            
                            if raw_log:
                                log_html = html.unescape(str(raw_log)).strip()
                                formatted = (
                                    f'<div>'
                                    f'<b style="color: #2b5b84;">[{author} in {room_name}]:</b> {log_html}'
                                    f'</div>'
                                    f'<br>'
                                )
                                batch.append(formatted)

                        if batch:
                            self.new_message.emit(batch)

            except Exception:
                pass

            # Interruptible sleep loop to make thread termination instant
            for _ in range(50):
                if not self.running:
                    break
                self.msleep(100)

    def stop(self):
        self.running = False
        self.session.close()


class IEMBotWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("src/icon.png"))
        self.setWindowTitle("IEMBot Desktop")
        self.resize(800, 500)

        # Audio setup
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

        if os.path.exists(SOUND_PATH):
            self.player.setSource(QUrl.fromLocalFile(SOUND_PATH))

        central = QWidget()
        layout = QVBoxLayout(central)

        # Room name input
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>Room:</b> #")) 

        self.room_input = QLineEdit("botstalk")
        top_bar.addWidget(self.room_input)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.start_monitoring)
        top_bar.addWidget(self.connect_btn)

        layout.addLayout(top_bar)

        # Text browser
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.anchorClicked.connect(self.open_link) 
        self.browser.setStyleSheet("font-family: monospace; font-size: 13px;") 
        layout.addWidget(self.browser)

        self.setCentralWidget(central)

        self.worker = None
        self.start_monitoring() 

    def start_monitoring(self):
        room = self.room_input.text().strip().lower()
        if not room:
            return

        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(1000)  # Max wait 1s before force killing
            self.worker = None

        self.browser.clear()
        self.browser.append(f"<b><i>Connected to:</i></b> #{room}")
        
        self.worker = IEMBotWorker(room)
        self.worker.new_message.connect(self.handle_incoming)
        self.worker.start()

    def handle_incoming(self, batch):
        cursor = self.browser.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        
        for html_msg in reversed(batch):
            cursor.insertHtml(html_msg)

        scrollbar = self.browser.verticalScrollBar()
        scrollbar.setValue(0)

        if os.path.exists(SOUND_PATH) and self.player.source().isValid():
            self.player.setPosition(0)
            self.player.play()
        else:
            QApplication.beep()

    def open_link(self, url: QUrl): 
        QDesktopServices.openUrl(url)

    def closeEvent(self, event):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(500)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = IEMBotWindow()
    window.show()
    sys.exit(app.exec())
