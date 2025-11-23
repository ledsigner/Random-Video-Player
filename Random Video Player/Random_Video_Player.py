import sys
import os
import random
import subprocess
import platform
import cv2
from PyQt6.QtCore import Qt, QUrl, QSettings, pyqtSignal, QTimer, QEvent, QSize, QSizeF, QRectF
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QStyle,
    QPushButton, QSlider, QLabel, QComboBox, QFileDialog, QLineEdit, QFrame,
    QGraphicsView, QGraphicsScene, QMenu, QGraphicsOpacityEffect
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
from PyQt6.QtGui import QIcon, QAction

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

class NoScrollGraphicsView(QGraphicsView):
    def wheelEvent(self, event):
        # Disable mouse wheel scrolling completely
        return

# --------------------------
# Clickable Video Frame
# --------------------------
class ClickableVideoFrame(QFrame):
    clickedLeft = pyqtSignal()
    clickedMiddle = pyqtSignal()
    clickedRight = pyqtSignal()
    clickedTop = pyqtSignal()
    clickedBottom = pyqtSignal()
    doubleClickedMiddle = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # === TIMER #1: delayed single click (~200 ms) ===
        self._single_delay_timer = QTimer()
        self._single_delay_timer.setSingleShot(True)
        self._single_delay_timer.timeout.connect(self._emit_delayed_single)

        # === TIMER #2: double-click window (~400 ms) ===
        self._double_timeout_timer = QTimer()
        self._double_timeout_timer.setSingleShot(True)
        self._double_timeout_timer.timeout.connect(self._reset_double_click)

        # states
        self._waiting_single = False
        self._waiting_double = False

        # tunable timings
        self.single_delay_ms = 200
        self.double_timeout_ms = 400

    def mousePressEvent(self, event):
        y = event.position().y()
        h = self.height()
        w = self.width()
        x = event.position().x()
        third = w / 3

        # ==================== TOP AREA ====================
        if event.button() == Qt.MouseButton.LeftButton and y < 20:
            self.clickedTop.emit()
            return

        # ==================== BOTTOM AREA ====================
        if event.button() == Qt.MouseButton.LeftButton and (h - y) < 90:
            self.clickedBottom.emit()
            return

        # ==================== LEFT AREA ====================
        if event.button() == Qt.MouseButton.LeftButton and x < third:
            self.clickedLeft.emit()
            return

        # ==================== RIGHT AREA ====================
        if event.button() == Qt.MouseButton.LeftButton and x >= 2 * third:
            self.clickedRight.emit()
            return

        # ==================== MIDDLE AREA CLICK ====================
        if event.button() == Qt.MouseButton.LeftButton:

            # FIRST CLICK
            if not self._waiting_double:
                self._waiting_double = True
                self._waiting_single = True

                self._single_delay_timer.start(self.single_delay_ms)
                self._double_timeout_timer.start(self.double_timeout_ms)
                return

            # SECOND CLICK
            else:
                # if single hasn't fired yet → cancel it
                if self._waiting_single:
                    self._single_delay_timer.stop()
                    self._waiting_single = False
                else:
                    # emit single-click for the second click
                    self.clickedMiddle.emit()

                # emit double-click
                self.doubleClickedMiddle.emit()

                # reset
                self._waiting_double = False
                self._double_timeout_timer.stop()
                return

        # ==================== RIGHT CLICK ====================
        #if event.button() == Qt.MouseButton.RightButton:
            #self.parent().toggle_fullscreen()

    # === Timer fired: single click delay expired ===
    def _emit_delayed_single(self):
        if self._waiting_single:
            self.clickedMiddle.emit()
            self._waiting_single = False


    # === Timer fired: double-click window expired ===
    def _reset_double_click(self):
        self._waiting_double = False
        self._waiting_single = False

# --------------------------
# Clickable Slider
# --------------------------
class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ratio = event.position().x() / self.width()
            ratio = max(0, min(ratio, 1))
            new_value = int(ratio * self.maximum())
            self.setValue(new_value)
            self.sliderMoved.emit(new_value)
            self.sliderReleased.emit()
        super().mousePressEvent(event)

# --------------------------
# Video Player
# --------------------------
class VideoPlayer(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Random Video Player")
        #self.setStyleSheet("background-color: #222; color: white;")
        self.resize(800, 1100)

        self.settings = QSettings("RandomVideoPlayer", "Settings")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Graphics scene and view
        self.scene = QGraphicsScene()
        self.view = NoScrollGraphicsView(self.scene, self)
        self.view.setParent(self)
        layout.addWidget(self.view)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Video item
        self.video_item = QGraphicsVideoItem()
        self.video_item.setSize(QSizeF(self.width(), self.height()))
        self.scene.addItem(self.video_item)

        # Media Player
        self.mediaPlayer = QMediaPlayer()
        self.audioOutput = QAudioOutput()
        self.mediaPlayer.setAudioOutput(self.audioOutput)
        self.mediaPlayer.setVideoOutput(self.video_item)

        # Clickable Video Frame + Video Widget
        self.video_frame = ClickableVideoFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.clickedLeft.connect(self.previous_video)
        self.video_frame.clickedMiddle.connect(self.toggle_play_pause)
        self.video_frame.clickedRight.connect(self.next_video)
        self.video_frame.clickedTop.connect(self.exit_fullscreen)
        self.video_frame.clickedBottom.connect(self.toggle_controls_visibility)
        self.video_frame.doubleClickedMiddle.connect(self.toggle_fullscreen)

        self.video_frame.setLayout(layout)

        # Progress bar + time
        self.progress = ClickableSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 1000)
        self.progress.setFixedHeight(12)
        self.progress.sliderReleased.connect(self.seek_video)

        self.time_label = QLabel("00:00 / 00:00")
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.addWidget(self.progress)
        progress_layout.addWidget(self.time_label)

        self.check_box_unfilled_icon = QIcon(resource_path(os.path.join("icons", "square.svg")))
        self.check_box_filled_icon = QIcon(resource_path(os.path.join("icons", "square-filled.svg")))

        # Controls
        self.button_style = """
            QPushButton {
                background-color: #333;   /* slightly lighter than main background */
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px 6px;
            }
            QPushButton:pressed {
                background-color: #555;
            }
        """
        
        self.button_style_selected = """
            QPushButton {
                background-color: #555;     /* lighter so it stands out */
                color: white;
                border: 1px solid #aaa;     /* clear active indicator */
                border-radius: 3px;
                padding: 3px 6px;
            }
        """
        
        self.dropdown_style = """
            QComboBox {
                background-color: #333;
                color: white;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 3px 6px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #444;
                color: white;
                selection-background-color: #666;
            }
        """

        self.menu_style = f"""
            QMenu {{
                background-color: #222;
                border: 1px solid #444;
                border-radius: 4px;
                color: white;
            }}
            QMenu::item {{
                border-radius: 4px;
                padding: 2px 15px 2px 5px;
                margin: 3px;
            }}
            QMenu::item:selected {{
                background-color: #333;
                border-radius: 3px;
                margin: 3px;
            }}
            QMenu::separator {{
                height: 1px;
                background-color: #444;
                margin-left: 4px;
                margin-right: 4px;
            }}
            QMenu::indicator {{
                width: 0px;
                height: 0px;
            }}
        """

        self.loop_btn = QPushButton()
        self.loop_btn.setCheckable(True)
        loop_off_icon_path = resource_path(os.path.join("icons", "loop-off.svg"))
        self.loop_btn.setIcon(QIcon(loop_off_icon_path))
        self.loop_btn.setIconSize(QSize(24, 24))
        self.loop_btn.setStyleSheet("background: transparent; border: none;")
        self.loop_btn.clicked.connect(self.toggle_loop)
        self.loop_enabled = False

        self.mute_btn = QPushButton()
        self.mute_btn.setCheckable(True)
        volume_icon_path = resource_path(os.path.join("icons", "volume.svg"))
        self.mute_btn.setIcon(QIcon(volume_icon_path))
        self.mute_btn.setIconSize(QSize(24, 24))
        self.mute_btn.setStyleSheet("background: transparent; border: none;")
        self.mute_btn.clicked.connect(self.toggle_mute)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(20)
        self.volume_slider.valueChanged.connect(lambda v: self.audioOutput.setVolume(v / 100))
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setFixedHeight(16)

        self.orientation_label = QLabel("Orientation:")
        self.orientation_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.orientation_dropdown = QComboBox()
        self.orientation_dropdown.addItems(["Vertical", "Horizontal", "Both"])
        self.orientation_dropdown.setCurrentText("Vertical")
        self.orientation_dropdown.setStyleSheet(self.dropdown_style)
        self.orientation_dropdown.currentTextChanged.connect(self.on_orientation_changed)

        self.max_length_label = QLabel("Max Length:")
        self.max_length_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.max_len_dec_btn = QPushButton("-")
        self.max_len_dec_btn.setFixedWidth(25)
        self.max_len_dec_btn.setStyleSheet(self.button_style)

        self.max_len_input = QLineEdit("00:30")
        self.max_len_input.setFixedWidth(50)
        self.max_len_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.max_len_input.textChanged.connect(self.manual_max_length_changed)

        self.max_len_inc_btn = QPushButton("+")
        self.max_len_inc_btn.setFixedWidth(25)
        self.max_len_inc_btn.setStyleSheet(self.button_style)
        
        self.max_len_delay_timer = QTimer()
        self.max_len_delay_timer.setSingleShot(True)
        self.max_len_delay_timer.setInterval(1000)  # 1 sec delay
        self.max_len_delay_timer.timeout.connect(self.start_auto_max_length_timer)

        self.max_len_auto_timer = QTimer()
        self.max_len_auto_timer.setInterval(150)  # auto-change interval
        self.max_len_auto_timer.timeout.connect(self._auto_change_max_length)
        self._max_len_change_direction = 0  # +1 for increment, -1 for decrement

        self.max_len_inc_btn.pressed.connect(lambda: self.start_max_len_hold(1))
        self.max_len_inc_btn.released.connect(self.stop_max_len_hold)
        self.max_len_dec_btn.pressed.connect(lambda: self.start_max_len_hold(-1))
        self.max_len_dec_btn.released.connect(self.stop_max_len_hold)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(5)
        controls_layout.addWidget(self.loop_btn)
        controls_layout.addWidget(self.mute_btn)
        controls_layout.addWidget(self.volume_slider)
        controls_layout.addWidget(self.orientation_label)
        controls_layout.addWidget(self.orientation_dropdown)
        controls_layout.addWidget(self.max_length_label)
        controls_layout.addWidget(self.max_len_dec_btn)
        controls_layout.addWidget(self.max_len_input)
        controls_layout.addWidget(self.max_len_inc_btn)

        # Controls container for show/hide
        self.controls_container = QWidget()
        controls_container_layout = QVBoxLayout()
        controls_container_layout.setContentsMargins(4,0,4,4)
        controls_container_layout.setSpacing(0)
        controls_container_layout.addLayout(progress_layout)
        controls_container_layout.addLayout(controls_layout)
        self.controls_container.setLayout(controls_container_layout)
        self.controls_container.raise_()

        # Main Layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.video_frame)
        main_layout.addWidget(self.controls_container)
        self.setLayout(main_layout)

        # Player Events
        self.mediaPlayer.positionChanged.connect(self.update_progress)
        self.mediaPlayer.durationChanged.connect(self.update_duration)
        self.mediaPlayer.mediaStatusChanged.connect(self.media_finished)

        # Video Data
        self.video_list = []
        self.current_index = -1
        self.duration_ms = 0
        self.current_orientation = self.orientation_dropdown.currentText()
        self.pending_orientation = self.current_orientation
        self.max_length_value = 30
        self.pending_max_length = 30
        self.current_max_length = 30
        
        self.current_video_path = None

        # Auto-load last folder
        last_folder = self.settings.value("last_folder", "D:\\Porn\\Video")
        if last_folder and os.path.exists(last_folder):
            self.load_folder(last_folder)
            self.play_random_video()
        else:
            self.select_folder()
        
        self.mute_action = QAction("Mute", self)
        self.mute_action.setCheckable(True)
        #self.mute_action.setChecked(False)
        self.mute_action.toggled.connect(self.toggle_mute)
        self.mute_action.toggled.connect(self.update_mute_check_icon)

        self.loop_action = QAction("Loop", self)
        self.loop_action.setCheckable(True)
        #self.loop_action.setChecked(False)
        self.loop_action.toggled.connect(self.toggle_loop)
        self.loop_action.toggled.connect(self.update_loop_check_icon)

        self.update_mute_button_style()
        self.update_loop_button_style() 
        self.update_mute_check_icon(False)
        self.update_loop_check_icon(False)

        self.select_action = QAction("Select Folder")
        self.select_action.triggered.connect(self.select_folder)

        self.open_action = QAction("Open in Explorer")
        self.open_action.triggered.connect(self.open_in_explorer)

        self.copy_action = QAction("Copy to...")
        self.copy_action.triggered.connect(self.copy_current_video_to)

        #self.defaults_action = QAction("Configure Defaults")
        #self.defaults_action.changed.connect(self.defaults_page) # Need a defaults window that saves values to settings
    
    def update_mute_check_icon(self, checked):
        self.mute_action.setIcon(
            self.check_box_filled_icon if checked else self.check_box_unfilled_icon)

    def update_loop_check_icon(self, checked):
        self.loop_action.setIcon(
            self.check_box_unfilled_icon if checked else self.check_box_filled_icon)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style)

        menu.addAction(self.mute_action)
        menu.addAction(self.loop_action)
        menu.addSeparator()
        menu.addAction(self.select_action)
        menu.addAction(self.open_action)
        menu.addAction(self.copy_action)
        menu.addSeparator()
        #menu.addAction(self.defaults_action)  # Open a window where defaults can be configured
                                               # Defuault Folders, max length, loop, mute, orientation, window size

        menu.exec(event.globalPos())

    # --- Video / Folder Methods ---
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Video Folder", "D:\\Porn\\Video")
        if folder:
            self.settings.setValue("last_folder", folder)
            self.load_folder(folder)
            self.play_random_video()

    def load_folder(self, folder):
        self.setWindowTitle(f"Random Video Player - {os.path.basename(folder)}")
        valid_ext = (".mp4", ".mov", ".avi", ".mkv")
        self.video_list = []
        orientation = self.current_orientation
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(valid_ext):
                    full = os.path.join(root, f)
                    if self.orientation_match(full, orientation):
                        self.video_list.append(full)
        random.shuffle(self.video_list)

    def load_folder_with_pending_settings(self):
        self.current_orientation = self.pending_orientation
        self.current_max_length = self.pending_max_length
        last_folder = self.settings.value("last_folder", "")
        if last_folder and os.path.exists(last_folder):
            self.load_folder(last_folder)

    def orientation_match(self, path, mode):
        cap = cv2.VideoCapture(path)
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        cap.release()
        if mode == "Both":
            return True
        if mode == "Vertical":
            return h >= w
        if mode == "Horizontal":
            return w > h

    def play_random_video(self):
        if not self.video_list:
            return
        index = random.randint(0, len(self.video_list) - 1)
        self.load_video(index)
        self.mediaPlayer.play()

    def load_video(self, index):
        self.current_index = index
        path = self.video_list[index]
        self.current_video_path = path
        url = QUrl.fromLocalFile(path)
        self.mediaPlayer.setSource(url)

    # --- Controls ---
    def next_video(self):
        if (self.pending_orientation != self.current_orientation or
            self.pending_max_length != self.current_max_length):
            self.load_folder_with_pending_settings()
            
        if not self.video_list:
            return
        self.current_index = (self.current_index + 1) % len(self.video_list)
        self.load_video(self.current_index)
        self.mediaPlayer.play()

    def previous_video(self):
        if not self.video_list:
            return
        self.current_index = (self.current_index - 1) % len(self.video_list)
        self.load_video(self.current_index)
        self.mediaPlayer.play()

    def toggle_play_pause(self):
        if self.mediaPlayer.isPlaying():
            self.mediaPlayer.pause()
        else:
            self.mediaPlayer.play()

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        self.loop_btn.setChecked(self.loop_enabled)
        self.update_loop_button_style()
        if self.loop_enabled:
            self.mediaPlayer.setLoops(QMediaPlayer.Loops.Infinite)
        else:
            self.mediaPlayer.setLoops(QMediaPlayer.Loops(1))
            
    def update_loop_button_style(self):
        if self.loop_enabled:
            self.loop_btn.setIcon(QIcon(resource_path(os.path.join("icons", "loop.svg"))))
        else:
            self.loop_btn.setIcon(QIcon(resource_path(os.path.join("icons", "loop-off.svg"))))

    def toggle_mute(self):
        new_state = not self.audioOutput.isMuted()
        self.audioOutput.setMuted(new_state)
        self.update_mute_button_style()
        
    def update_mute_button_style(self):
        if self.audioOutput.isMuted():
            self.mute_btn.setIcon(QIcon(resource_path(os.path.join("icons", "volume-off.svg"))))
        else:
            self.mute_btn.setIcon(QIcon(resource_path(os.path.join("icons", "volume.svg"))))

    def on_orientation_changed(self, text):
        self.pending_orientation = text

    # --- Progress ---
    def update_duration(self, dur):
        self.duration_ms = dur

    def update_progress(self, pos):
        if self.duration_ms > 0:
            val = int(pos / self.duration_ms * 1000)
            self.progress.setValue(val)
        self.time_label.setText(f"{self.format_time(pos)} / {self.format_time(self.duration_ms)}")

    def seek_video(self):
        if self.duration_ms > 0:
            pct = self.progress.value() / 1000
            self.mediaPlayer.setPosition(int(self.duration_ms * pct))

    def format_time(self, ms):
        sec = ms // 1000
        m = sec // 60
        s = sec % 60
        return f"{m:02}:{s:02}"

    def media_finished(self, status):
        from PyQt6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.loop_enabled:
                self.mediaPlayer.setPosition(0)
                QTimer.singleShot(50, self.mediaPlayer.play)
            else:
                self.next_video()

    # --- Max Length ---
    def set_max_length(self, value):
        try:
            value = max(0, int(value))  # minimum is 0
        except:
            return
        self.max_length_value = value
        if value == 0:
            self.max_len_input.setText("None")
        else:
            self.max_len_input.setText(self.format_time(value * 1000))
        self.pending_max_length = value 

    def increment_max_length(self):
        self.set_max_length(self.max_length_value + 10)

    def decrement_max_length(self):
        self.set_max_length(self.max_length_value - 10)

    def manual_max_length_changed(self, text):
        if text.isdigit():
            self.set_max_length(text)
        elif text.lower() in ["no limit", "nolimit"]:
            self.set_max_length(0)

    # --- Explorer & Fullscreen ---
    def open_in_explorer(self):
        if not self.video_list or self.current_index == -1:
            return
        path = os.path.abspath(self.video_list[self.current_index])
        if platform.system() == "Windows":
            subprocess.Popen(['explorer', '/select,', path])
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def toggle_controls_visibility(self):
        if self.controls_container.isVisible():
            self.controls_container.hide()
        else:
            self.controls_container.show()
            self.controls_container.raise_()
        
    def start_max_len_hold(self, direction):
        self._max_len_change_direction = direction
        # Immediate single-step change
        self.change_max_length(direction)
        # Start the 1-second delay timer
        self.max_len_delay_timer.start()

    def start_auto_max_length_timer(self):
        # Called after 1 second delay
        self.max_len_auto_timer.start()

    def stop_max_len_hold(self):
        # Stop both timers
        self.max_len_delay_timer.stop()
        self.max_len_auto_timer.stop()

    def _auto_change_max_length(self):
        self.change_max_length(self._max_len_change_direction)

    def change_max_length(self, direction):
        new_value = self.max_length_value + (10 * direction)
        self.set_max_length(new_value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self.video_item.setSize(QSizeF(w, h))
        self.scene.setSceneRect(QRectF(0, 0, w, h))
        self.controls_container.raise_()
        
    def copy_current_video_to(self):
        """
        Ask the user for a destination folder (starting at D:\\Porn\\Video), copy the
        currently playing video into it, avoid overwriting by auto-numbering,
        and set the copied file's modified time to the original file's creation time.
        """
        if not self.current_video_path:
            return

        start_dir = "D:\\Porn\\Video"

        # Ask user to select a folder
        target_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Destination Folder",
            start_dir,
            QFileDialog.Option.ShowDirsOnly
        )

        if not target_dir:
            return  # user cancelled

        import shutil
        
        source = self.current_video_path
        filename = os.path.basename(source)
        base, ext = os.path.splitext(filename)

        # Avoid overwrite: if the filename exists in target, append (1), (2), ...
        destination = os.path.join(target_dir, filename)
        i = 1
        while os.path.exists(destination):
            destination = os.path.join(target_dir, f"{base} ({i}){ext}")
            i += 1

        try:
            shutil.copy(source, destination)
        except Exception as e:
            # you can replace this with a QMessageBox if you prefer a GUI error
            print(f"Copy failed: {e}")
            return

        # Use the source file's creation time (stat.st_ctime) and set that as
        # the copied file's modified + accessed times.
        try:
            subprocess.run(
                [
                    "exiftool",
                    "-overwrite_original",
                    "-F",
                    "-FileModifyDate<FileCreateDate",
                    destination
                ],
                shell=True
            )
        except Exception as e:
            print(f"Exiftool failed: {e}")


# --------------------------
# Run App
# --------------------------
if __name__ == "__main__":
    # Best-effort hide/close any console created by python.exe on Windows.
    # This will hide the console even when the script is launched with python.exe.
    """if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                SW_HIDE = 0
                user32.ShowWindow(hwnd, SW_HIDE)   # hide console window
                kernel32.FreeConsole()             # detach from console
        except Exception:
            pass"""

    app = QApplication(sys.argv)
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec())
