"""
This is a simple media player that plays videos from a selected folder (and subfolders) in random
order. By default, videos will auto play, but this and other configurations can be changed in the
context menu (right-click anywhere on the video). 

The main window is split into clickable zones for navigation and control:
    - Center third: Play/Pause (single click), Fullscreen toggle (double click))
    - Left third: Previous video
    - Right third: Next video
    - Top: Exit fullscreen
    - Bottom: Toggle control bar visibility

The control bar at the bottom of the main window has filters for orientation and max length.

Video info is cached in local app data after the initial scan of a folder for faster subsequent 
loading times. If a video is modified or a new file is added to a folder, the cache will be 
updated with the new info.
"""

import sys, os, random, subprocess, platform, shutil, math, cv2, json, time
from colorama import Fore, Back, Style
from pathlib import Path
from PyQt6.QtCore import (Qt, QUrl, QSettings, pyqtSignal, QTimer, QEvent,
    QSize, QSizeF, QRectF, QThread)
from PyQt6.QtWidgets import (QApplication, QStackedLayout, QWidget, QVBoxLayout, QHBoxLayout,
    QStyle, QPushButton, QSlider, QLabel, QComboBox, QFileDialog, QLineEdit, 
    QFrame, QMenu, QProgressBar, QWidgetAction, QSpacerItem, QSizePolicy, QMainWindow)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtGui import (QGuiApplication, QIcon, QAction, QFont, QPaintEvent, 
    QPainter, QPalette, QPalette, QColor, QPainter)

# To be able to access resources when compiled with PyInstaller
def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def load_stylesheet(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

stylesheet = load_stylesheet(resource_path("styles.qss"))

def get_cache_path():
        appdata = os.getenv("LOCALAPPDATA")  # Windows AppData\Local
        folder = os.path.join(appdata, "RandomVideoPlayer")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "media_info_cache.json")

def normalize_path(path: str) -> str:
    path = os.path.abspath(path)
    path = os.path.normpath(path)
    return path

class VideoScanner(QThread):
    import subprocess
    import json
    
    scanned = pyqtSignal(list)
    scanned_progress = pyqtSignal(int, int) # scanned_count, total_count

    def __init__(self, folder, orientation, max_length, force_reload=False):
        super().__init__()
        self.folder = folder
        self.orientation = orientation
        self.max_length = max_length
        self.force_reload = force_reload

        # Load cache if exists
        self.cache_path = get_cache_path()
        if os.path.exists(self.cache_path):
            with open(self.cache_path, "r") as f:
                self.media_info_cache = json.load(f)
        else:
            self.media_info_cache = {}    

    def run(self):
        startTime = time.time()
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov')
        videos = []

        # Count total video files first
        total_videos = sum(
            1 for root, dirs, files in os.walk(self.folder)
            for file in files if file.lower().endswith(video_extensions)
        )
        scanned_count = 0

        for root, dirs, files in os.walk(self.folder):
            for file in files:
                if file.lower().endswith(video_extensions):
                    full = normalize_path(os.path.join(root, file))
                    scanned_count += 1
                    self.scanned_progress.emit(scanned_count, total_videos)

                    # Add functionality: If a different folder is selected or reload is selected, stop the current scan

                    mtime = os.path.getmtime(full)

                    info = self.media_info_cache.get(full)

                    #If force reload was selected or it's a new file or the file has been modified, update it in cache
                    if self.force_reload or info is None or info.get("mtime") != mtime:
                        duration = self.get_video_length(full)
                        orientation = self.detect_orientation(full)
                        info = {"duration": duration, "orientation": orientation, "mtime": mtime}
                        self.media_info_cache[full] = info

                    # Skip if orientation doesn't match
                    if self.orientation != "All" and info["orientation"] != self.orientation:
                        continue

                    # If there is no max length, allow all lengths. if there is a max length, skip if video is longer
                    if self.max_length == 0:
                        pass
                    elif info["duration"] > self.max_length:
                        continue

                    videos.append(full)

        try:
            with open(self.cache_path, "w") as f:
                json.dump(self.media_info_cache, f)
        except Exception as e:
            print(f"Failed to save duration cache: {e}")

        self.scanned.emit(videos)
        endTime = time.time()
        print(Fore.GREEN + "Loading folder duration:" + Style.RESET_ALL, endTime - startTime)

    # Returns video length in seconds using ffprobe.
    def get_video_length(self, path):
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            return float(result.stdout.strip())
        except Exception:
            return 999999  # treat un-readable files as too long
    
    def detect_orientation(self, path):
        cap = cv2.VideoCapture(path)
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        cap.release()
        if w > h:
            return "Horizontal"
        elif h >= w:
            return "Vertical"
        return "All"

class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool| Qt.WindowType.FramelessWindowHint)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(34, 34, 34, 160);")

        # Progress bar centered
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.loading_progress_bar = QProgressBar()
        self.loading_progress_bar.setMinimum(0)
        self.loading_progress_bar.setMaximum(100)
        self.loading_progress_bar.setTextVisible(True)
        self.loading_progress_bar.setFixedWidth(200)
        self.loading_progress_bar.setStyleSheet(stylesheet)

        self.layout.addWidget(self.loading_progress_bar)

        self.hide()

    def update_loading_progress(self, scanned, total):
        self.loading_progress_bar.setMaximum(total)
        self.loading_progress_bar.setValue(scanned)

class ControlsOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)

        self.setStyleSheet("background-color: #222;")

        self.loop_off_icon = resource_path(os.path.join("icons", "loop-off.svg"))
        self.loop_on_icon = resource_path(os.path.join("icons", "loop.svg"))
        self.volume_on_icon = resource_path(os.path.join("icons", "volume.svg"))
        self.volume_off_icon = resource_path(os.path.join("icons", "volume-off.svg"))

        # --- Widgets ---
        self.loop_btn = QPushButton()
        self.loop_btn.setObjectName("playOptions")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setIcon(QIcon(self.loop_off_icon))
        self.loop_btn.setIconSize(QSize(22, 22))
        self.loop_btn.setStyleSheet(stylesheet)
        self.loop_enabled = False

        self.mute_btn = QPushButton()
        self.mute_btn.setObjectName("playOptions")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setIcon(QIcon(self.volume_on_icon))
        self.mute_btn.setIconSize(QSize(22, 22))
        self.mute_btn.setStyleSheet(stylesheet)

        self.volume_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("not-minimum")
        self.volume_slider.setStyleSheet(stylesheet)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setFixedHeight(15)
        self.volume_slider.valueChanged.connect(self.update_volume_slider_visibility)
        self.volume_slider_stored = 50 # Default value

        self.orientation_label = QLabel("Orientation:")
        self.orientation_label.setStyleSheet(stylesheet)
        self.orientation_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.orientation_dropdown = QComboBox()
        self.orientation_dropdown.addItems(["Vertical", "Horizontal", "All"])
        self.orientation_dropdown.setCurrentText("All")
        self.orientation_dropdown.setStyleSheet(stylesheet)
        self.orientation_dropdown.currentTextChanged.connect(self.on_orientation_changed)
        self.current_orientation = self.orientation_dropdown.currentText()
        self.pending_orientation = self.current_orientation

        self.max_length_label = QLabel("Max Length:")
        self.max_length_label.setStyleSheet(stylesheet)
        self.max_length_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.max_len_dec_btn = QPushButton("▼")
        self.max_len_dec_btn.setObjectName("max_len")
        self.max_len_dec_btn.setFixedWidth(25)
        self.max_len_dec_btn.setFixedHeight(12)
        self.max_len_dec_btn.setStyleSheet(stylesheet)

        self.max_len_input = QLineEdit("None")
        self.max_len_input.setFixedWidth(35)
        self.max_len_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.max_len_input.setStyleSheet(stylesheet)

        self.max_len_inc_btn = QPushButton("▲")
        self.max_len_inc_btn.setObjectName("max_len")
        self.max_len_inc_btn.setFixedWidth(25)
        self.max_len_inc_btn.setFixedHeight(12)
        self.max_len_inc_btn.setStyleSheet(stylesheet)   

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

        self.current_max_length = 0
        self.pending_max_length = 0
        self.duration_ms = 0

        # Progress bar + time
        self.progress_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setObjectName("minimum")
        self.progress_slider.setStyleSheet(stylesheet)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setFixedHeight(12)
        self.progress_slider.valueChanged.connect(self.update_progress_slider_visibility)

        self.time_label = QLabel("00:00 / 00:00")
        self.max_len_inc_btn.setObjectName("time_label")
        self.time_label.setStyleSheet(stylesheet)

        max_len_btn_layout = QVBoxLayout()
        max_len_btn_layout.setSpacing(1)
        max_len_btn_layout.addWidget(self.max_len_inc_btn)
        max_len_btn_layout.addWidget(self.max_len_dec_btn)

        # Main control buttons layout
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(2)
        controls_layout.addWidget(self.loop_btn, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        controls_layout.addWidget(self.mute_btn, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        controls_layout.addWidget(self.volume_slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        controls_layout.addStretch()
        controls_layout.addWidget(self.orientation_label)
        controls_layout.addWidget(self.orientation_dropdown)
        controls_layout.addItem(QSpacerItem(20, 0))
        controls_layout.addWidget(self.max_length_label)
        controls_layout.addWidget(self.max_len_input)
        controls_layout.addLayout(max_len_btn_layout)

        # Progress bar + time layout
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.addWidget(self.progress_slider, 1)
        progress_layout.addWidget(self.time_label)

        # Final assembly
        self.controls_container = QWidget(self)
        self.controls_container.setStyleSheet("background-color: #222; border-radius: 3px;")
        self.controls_container_layout = QVBoxLayout()
        self.controls_container_layout.setContentsMargins(3, 3, 3, 3)
        self.controls_container_layout.setSpacing(2)
        self.controls_container_layout.addLayout(progress_layout)
        self.controls_container_layout.addLayout(controls_layout)
        self.controls_container.setLayout(self.controls_container_layout)

        overlay_window_layout = QVBoxLayout(self)
        overlay_window_layout.setContentsMargins(0, 0, 0, 0)
        overlay_window_layout.addWidget(self.controls_container)

    def update_video_duration(self, dur):        
        self.duration_ms = dur

    def update_video_progress(self, pos):        
        if self.duration_ms > 0:
            val = int(pos / self.duration_ms * 1000)
            self.progress_slider.setValue(val)
        self.time_label.setText(f"{self.format_time(pos)} / {self.format_time(self.duration_ms)}")

    def format_time(self, ms):
        sec = ms // 1000
        m = sec // 60
        s = sec % 60
        return f"{m:02}:{s:02}"

    def set_max_length(self, value):        
        try:
            value = max(0, int(value))
        except:
            return
        if value == 0:
            self.max_len_input.setText("None")
        else:
            self.max_len_input.setText(self.format_time(value * 1000))
        self.pending_max_length = value 

    def manual_max_length_changed(self, text):        
        if text.isdigit():
            self.set_max_length(text)
        elif text.lower() in ["no limit", "nolimit"]:
            self.set_max_length(0)

    def on_orientation_changed(self, text):        
        self.pending_orientation = text
        
    def start_max_len_hold(self, direction):        
        self._max_len_change_direction = direction
        self.change_max_length(direction)
        self.max_len_delay_timer.start()

    def start_auto_max_length_timer(self):        
        self.max_len_auto_timer.start()

    def stop_max_len_hold(self):        
        self.max_len_delay_timer.stop()
        self.max_len_auto_timer.stop()

    def _auto_change_max_length(self):        
        self.change_max_length(self._max_len_change_direction)

    def change_max_length(self, direction):        
        new_value = self.pending_max_length + (10 * direction)
        self.set_max_length(new_value)

    def update_volume_slider_visibility(self, value):
        if value == self.volume_slider.minimum():
            self.volume_slider.setObjectName("minimum")
        else:
            self.volume_slider.setObjectName("not-minimum")
        self.volume_slider.setStyleSheet(stylesheet)

    def update_progress_slider_visibility(self, value):
        if value == self.progress_slider.minimum():
            self.progress_slider.setObjectName("minimum")
        else:
            self.progress_slider.setObjectName("not-minimum")
        self.progress_slider.setStyleSheet(stylesheet)

class ClickOverlay(QWidget):
    clickedLeft = pyqtSignal()
    clickedMiddle = pyqtSignal()
    clickedRight = pyqtSignal()
    doubleClickedMiddle = pyqtSignal()
    clickedTop = pyqtSignal() 
    clickedBottom = pyqtSignal() 
    
    # We'll use a single-click/double-click detector logic similar to the old frame
    def __init__(self, parent=None):   
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background-color: transparent;")
        
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
        
        # tunable timings (from your original code)
        self.single_delay_ms = 200
        self.double_timeout_ms = 400

    def mousePressEvent(self, event):
        # Only handle left clicks for navigation/control
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        w = self.width()
        h = self.height()
        x = event.position().x()
        y = event.position().y()
        
        third_w = w / 3
        # Use 1/5 (20%) of the height for top/bottom zones
        sixth_h = h / 6 

        if y < sixth_h:
            self.clickedTop.emit()
            return
  
        if y > h - sixth_h:
            self.clickedBottom.emit()
            return

        if x < third_w:
            self.clickedLeft.emit()
            return

        if x >= 2 * third_w:
            self.clickedRight.emit()
            return

        if not self._waiting_double:
            self._waiting_double = True
            self._waiting_single = True

            self._single_delay_timer.start(self.single_delay_ms)
            self._double_timeout_timer.start(self.double_timeout_ms)
            return

        else:
            if self._waiting_single:
                self._single_delay_timer.stop()
                self._waiting_single = False
            else:
                self.clickedMiddle.emit()

            self.doubleClickedMiddle.emit()

            self._waiting_double = False
            self._double_timeout_timer.stop()
            return
            
        # For non-handled events (like Right Click), let the base class handle them (e.g., context menu)
        super().mousePressEvent(event)

    def _emit_delayed_single(self):
        if self._waiting_single:
            self.clickedMiddle.emit()
            self._waiting_single = False

    def _reset_double_click(self):
        self._waiting_double = False
        self._waiting_single = False

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

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("RandomVideoPlayer", "Settings")

        self.resize(800, 900)
        self.setMinimumSize(500,450)

        video_widget = QVideoWidget(self)
        self.setCentralWidget(video_widget)

        self.controls = ControlsOverlay(self)

        self.loading = LoadingOverlay(self)

        self.mediaPlayer = QMediaPlayer()
        self.audioOutput = QAudioOutput()
        self.mediaPlayer.setAudioOutput(self.audioOutput)
        self.mediaPlayer.setVideoOutput(video_widget)

        self.click_overlay = ClickOverlay(self)
        self.click_overlay.clickedLeft.connect(self.previous_video)
        self.click_overlay.clickedRight.connect(self.next_video)
        self.click_overlay.doubleClickedMiddle.connect(self.toggle_fullscreen)
        self.click_overlay.clickedMiddle.connect(self.toggle_play_pause)
        self.click_overlay.clickedTop.connect(self.exit_fullscreen)
        self.click_overlay.clickedBottom.connect(self.toggle_controls_visibility)

        self.mediaPlayer.positionChanged.connect(self.controls.update_video_progress)
        self.mediaPlayer.durationChanged.connect(self.controls.update_video_duration)
        self.controls.progress_slider.sliderReleased.connect(self.seek_video)
        self.mediaPlayer.mediaStatusChanged.connect(self.media_finished)

        self.video_list = []
        self.current_index = -1
        self.current_video_path = None
        
        self.check_box_unfilled_icon = QIcon(resource_path(os.path.join("icons", "square.svg")))
        self.check_box_filled_icon = QIcon(resource_path(os.path.join("icons", "square-filled.svg")))

        # Context Menu Actions
        self.mute_action = QAction("Mute", self)
        self.mute_action.setCheckable(True)
        self.mute_action.toggled.connect(self.toggle_mute)
        self.mute_action.toggled.connect(self.update_mute_check_icon)

        self.loop_action = QAction("Loop", self)
        self.loop_action.setCheckable(True)
        self.loop_action.toggled.connect(self.toggle_loop)
        self.loop_action.toggled.connect(self.update_loop_check_icon)

        self.auto_play_action = QAction("Auto Play", self)
        self.auto_play_action.setCheckable(True)
        self.auto_play_action.toggled.connect(self.toggle_auto_play)
        self.auto_play_action.toggled.connect(self.update_auto_play_check_icon)
        self.auto_play_enabled = True
        
        self.fullscreen_action = QAction("Full Screen", self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.toggled.connect(self.toggle_fullscreen)
        self.fullscreen_action.toggled.connect(self.update_fullscreen_check_icon)

        self.borderless_action = QAction("Borderless", self)
        self.borderless_action.setCheckable(True)
        self.borderless_action.toggled.connect(self.toggle_borderless)
        self.borderless_action.toggled.connect(self.update_borderless_check_icon)

        self.hide_controls_action = QAction("Hide Controls", self)
        self.hide_controls_action.setCheckable(True)
        self.hide_controls_action.toggled.connect(self.toggle_controls_visibility)
        self.hide_controls_action.toggled.connect(self.update_hide_controls_check_icon)

        self.update_mute_button_style()
        self.update_loop_button_style() 
        self.update_mute_check_icon(False)
        self.update_loop_check_icon(False)
        self.update_auto_play_check_icon(False)
        self.update_fullscreen_check_icon(False)
        self.update_borderless_check_icon(False)
        self.update_hide_controls_check_icon(False)

        self.select_play_action = QAction("Select Play Folder")
        self.select_play_action.triggered.connect(self.select_play_folder)

        self.select_home_action = QAction("Select Home Folder")
        self.select_home_action.triggered.connect(self.select_home_folder)

        self.open_action = QAction("Open in Explorer")
        self.open_action.triggered.connect(self.open_in_explorer)

        self.save_action = QAction("Save Video As...")
        self.save_action.triggered.connect(self.save_current_video_as)

        self.reload_action = QAction("Reload Folder")
        self.reload_action.triggered.connect(self.reload_current_folder)
        
        self.controls.loop_btn.clicked.connect(self.toggle_loop)
        self.controls.mute_btn.clicked.connect(self.toggle_mute)
        self.controls.volume_slider.valueChanged.connect(self.update_volume)
        self.controls.volume_slider.setValue(50)
        self.controls.orientation_dropdown.currentTextChanged.connect(self.controls.on_orientation_changed)

        self.update_overlay_position()
        self.controls.show()
        self.controls_visible = True

        self.loading_folder = False

        # Load Home Folder from settings. If it doesn't exist, prompt to set one.
        self.home_folder = self.settings.value("home_folder", "")
        if not self.home_folder == "" and os.path.exists(self.home_folder):
            self.settings.setValue("home_folder", self.home_folder)
        else:
            self.select_home_folder()
        
        # Note: Could add a pop up to "load last folder" or "select a folder to load from the Home Folder" on startup
        # Auto-load last folder, or if not set, select from Home Folder
        self.last_folder = self.settings.value("last_folder", "")
        if not self.last_folder == "" and os.path.exists(self.last_folder):
            self.load_folder(self.last_folder)
        else:
            self.select_play_folder()
    
    def changeEvent(self, event):
        super().changeEvent(event)
        
        if event.type() == QEvent.Type.WindowStateChange:
            if self.controls_visible:
                self.update_overlay_position()

        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow() and self.controls_visible:
                self.controls.raise_()
    
    def update_overlay_position(self):
        if not self.controls.isVisible():
            return
        
        geo = self.geometry()  # main window geometry on screen
        
        w = geo.width()
        h = self.controls.sizeHint().height()
        x = geo.x()
        y = geo.y() + geo.height() - h

        self.controls.setGeometry(x, y, w, h)
        self.controls.raise_()
        self.controls.show()

        if self.loading.isVisible():
            self.loading.setGeometry(geo.x(), geo.y(), geo.width(), geo.height())
            self.loading.raise_()
            self.loading.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        
        geo = self.geometry()
        self.loading.setGeometry(geo.x(), geo.y(), geo.width(), geo.height())
        self.click_overlay.setGeometry(0, 0, w, h)
        
        self.click_overlay.raise_()

        self.controls.raise_()

        self.loading.raise_()
            
        self.update_overlay_position()

    def show_loader(self, total=0):
        if total > 0:
            self.loading.loading_progress_bar.setMaximum(total)
        self.loading.loading_progress_bar.setValue(0)

        self.resize(self.size())
        self.loading.show()
        self.loading.raise_()
        self.update_overlay_position()
        
    def moveEvent(self, event):
        super().moveEvent(event)
        self.update_overlay_position()

    def update_mute_check_icon(self, checked):
        self.mute_action.setIcon(
            self.check_box_filled_icon if checked else self.check_box_unfilled_icon)

    def update_loop_check_icon(self, checked):
        self.loop_action.setIcon(
            self.check_box_filled_icon if checked else self.check_box_unfilled_icon)

    def update_auto_play_check_icon(self, checked):
        self.auto_play_action.setIcon(
            self.check_box_unfilled_icon if checked else self.check_box_filled_icon)
            
    def update_fullscreen_check_icon(self, checked):
        self.fullscreen_action.setIcon(
            self.check_box_filled_icon if checked else self.check_box_unfilled_icon)

    def update_borderless_check_icon(self, checked):
        self.borderless_action.setIcon(
            self.check_box_filled_icon if checked else self.check_box_unfilled_icon)

    def update_hide_controls_check_icon(self, checked):
        self.hide_controls_action.setIcon(
            self.check_box_filled_icon if checked else self.check_box_unfilled_icon)
        
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(stylesheet)

        menu.addAction(self.mute_action)
        menu.addAction(self.loop_action)
        menu.addAction(self.auto_play_action)
        menu.addAction(self.fullscreen_action)
        menu.addAction(self.borderless_action)
        menu.addAction(self.hide_controls_action)
        menu.addSeparator()
        menu.addAction(self.select_play_action)
        menu.addAction(self.select_home_action)
        #menu.addAction(self.reload_action) # refresh cache for current Play Folder
        menu.addSeparator()
        menu.addAction(self.open_action)
        menu.addAction(self.save_action)

        menu.exec(event.globalPos())

    def update_loader_progress(self, scanned, total):
        self.loading.update_loading_progress(scanned, total)
        self.loading.loading_progress_bar.setFormat(f"Loading {self.current_folder_name}: %p% ({scanned}/{total})")

    def scan_folder(self, folder):
        self.loader_timer = QTimer()
        self.loader_timer.setSingleShot(True)
        self.loader_timer.timeout.connect(self.show_loader)
        self.loader_timer.start(1000)

        self.scanner = VideoScanner(folder, self.controls.current_orientation, self.controls.current_max_length, force_reload=False)
        self.scanner.scanned.connect(self.on_scan_complete)
        self.scanner.scanned_progress.connect(self.update_loader_progress)
        self.scanner.start()

    def load_folder(self, folder):
        self.loading_folder = True
        self.current_folder = folder
        self.current_folder_name = os.path.basename(folder)
        self.setWindowTitle(f"Random Video Player - {self.current_folder_name}")
        self.video_list = []

        self.scan_folder(folder)

    def on_scan_complete(self, videos):
        self.loading_folder = False
        self.loader_timer.stop()
        self.loading.hide()
        self.video_list = videos
        random.shuffle(self.video_list)
        print(Fore.GREEN + f"Found {len(videos)} videos." + Style.RESET_ALL)
        self.play_video()

    def load_folder_with_pending_settings(self):
        self.controls.current_orientation = self.controls.pending_orientation
        self.controls.current_max_length = self.controls.pending_max_length
        if self.current_folder and os.path.exists(self.current_folder):
            self.load_folder(self.current_folder)

    def play_video(self):
        if not self.video_list:
            print(Fore.RED + "No videos to play" + Style.RESET_ALL)
            return
        self.load_video(0)
        self.mediaPlayer.play()

    def load_video(self, index):        
        self.current_index = index
        path = self.video_list[index]
        self.current_video_path = path
        url = QUrl.fromLocalFile(path)
        self.mediaPlayer.setSource(url)

    def next_video(self):
        if (self.controls.pending_orientation != self.controls.current_orientation or
            self.controls.pending_max_length != self.controls.current_max_length):
            self.load_folder_with_pending_settings()
            
        if not self.video_list:
            return
        self.current_index = (self.current_index + 1) % len(self.video_list)
        self.load_video(self.current_index)
        if self.auto_play_enabled:
            self.mediaPlayer.play()
        else:
            self.mediaPlayer.pause()

    def previous_video(self):        
        if not self.video_list:
            return
        self.current_index = (self.current_index - 1) % len(self.video_list)
        self.load_video(self.current_index)
        if self.auto_play_enabled:
            self.mediaPlayer.play()
        else:
            self.mediaPlayer.pause()

    def toggle_play_pause(self):
        if self.mediaPlayer.isPlaying():
            self.mediaPlayer.pause()
        else:
            self.mediaPlayer.play()

    def toggle_loop(self):
        self.controls.loop_enabled = not self.controls.loop_enabled
        self.controls.loop_btn.setChecked(self.controls.loop_enabled)
        self.update_loop_button_style()
            
    def update_loop_button_style(self):
        if self.controls.loop_enabled:
            self.controls.loop_btn.setIcon(QIcon(self.controls.loop_on_icon))
            self.loop_action.setIcon(self.check_box_filled_icon)
        else:
            self.controls.loop_btn.setIcon(QIcon(self.controls.loop_off_icon))
            self.loop_action.setIcon(self.check_box_unfilled_icon)

    def toggle_auto_play(self):
            self.auto_play_enabled = not self.auto_play_enabled

    def toggle_mute(self):        
        if self.audioOutput.isMuted():
            self.audioOutput.setMuted(False)
            self.update_mute_button_style(50)
            self.controls.volume_slider.setValue(self.controls.volume_slider_stored)
        else:
            self.controls.volume_slider_stored = int(self.audioOutput.volume() * 100)
            self.audioOutput.setMuted(True)
            self.update_mute_button_style(0)
            self.controls.volume_slider.setValue(0)

    def update_volume(self, slider_value):        
        volume_value = (slider_value / 100)
        if slider_value == 0:
            self.audioOutput.setMuted(True)
        else:
            self.audioOutput.setMuted(False)
        self.audioOutput.setVolume(volume_value)
        self.update_mute_button_style(volume_value)
        
    def update_mute_button_style(self, volume_current = 50):        
        if self.audioOutput.isMuted() or volume_current == 0:
            self.controls.mute_btn.setIcon(QIcon(self.controls.volume_off_icon))
            self.mute_action.setIcon(self.check_box_filled_icon)
        else:
            self.controls.mute_btn.setIcon(QIcon(self.controls.volume_on_icon))
            self.mute_action.setIcon(self.check_box_unfilled_icon)

    def seek_video(self):        
        if self.controls.duration_ms > 0:
            pct = self.controls.progress_slider.value() / 1000
            self.mediaPlayer.setPosition(int(self.controls.duration_ms * pct))

    def media_finished(self, status):        
        if status == self.mediaPlayer.MediaStatus.EndOfMedia:
            if self.controls.loop_enabled:
                self.mediaPlayer.setPosition(0)
            else:
                self.next_video()

            if self.auto_play_enabled:
                self.mediaPlayer.play()
            else:
                self.mediaPlayer.pause()

    def toggle_fullscreen(self):        
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_action.setIcon(self.check_box_unfilled_icon)
        else:
            self.showFullScreen()
            self.fullscreen_action.setIcon(self.check_box_filled_icon)
    
    def exit_fullscreen(self):        
        if self.isFullScreen():
            self.showNormal()

    # Issue: When borderless is toggled, the window size changes. But I want the window size to say the 
    # same size, but the video player should take up the entire thing including the title bar.
    def toggle_borderless(self): 
        if bool(self.windowFlags() & Qt.WindowType.FramelessWindowHint):
            print(f"\nWithout border Height: {self.height()}")
            print(f"Without border Width: {self.width()}")
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
            self.borderless_action.setIcon(self.check_box_unfilled_icon)
            self.show()
            print(f"With border Height: {self.height()}")
            print(f"With border Width: {self.width()}")
        else:
            print(f"\nWith border Height: {self.height()}")
            print(f"With border Width: {self.width()}")
            self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            self.borderless_action.setIcon(self.check_box_filled_icon)
            self.show()
            print(f"Without border Height: {self.height()}")
            print(f"Without border Width: {self.width()}")

    def toggle_controls_visibility(self):
        if self.controls.isVisible():
            self.controls.hide()
        else:
            self.controls.show()
            self.update_overlay_position()

    # Select a folder to play videos from. Can't do this if a folder is already loading
    def select_play_folder(self):
        if self.loading_folder:
            return
        
        folder = QFileDialog.getExistingDirectory(self, "Select Play Folder", self.home_folder)
        if folder and os.path.exists(folder):
            self.settings.setValue("last_folder", folder)
            self.current_folder = folder
            self.load_folder(self.current_folder)

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

    def select_home_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Home Folder", self.home_folder)
        if folder:
            self.settings.setValue("home_folder", folder)
            self.home_folder = folder

    # Remove items in the current folder from the cache json and rescan the folder. Can't do this if a folder is already loading
    def reload_current_folder(self):  
        if not self.current_folder:
            return

        if self.loading_folder:
            return

        self.loading_folder = True

        cache_path = get_cache_path()
        if os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                cache_data = json.load(f)
        else:
            cache_data = {}

        folder = os.path.normpath(self.current_folder)
        keys_to_remove = [k for k in list(cache_data.keys()) if os.path.normpath(k).startswith(folder)]

        for k in keys_to_remove:
            del cache_data[k]

        with open(cache_path, "w") as f:
            json.dump(cache_data, f)

        self.scan_folder(folder)
        
    def save_current_video_as(self):        
        if not self.current_video_path:
            return

        start_dir = self.home_folder if self.home_folder and os.path.exists(self.home_folder) else self.current_folder

        source = self.current_video_path
        filename = os.path.basename(source)
        base, ext = os.path.splitext(filename)

        save_path = os.path.join(self.settings.value("last_save_folder",start_dir), filename)

        save_file_path, _ = QFileDialog.getSaveFileName(self, "Save Video As...", save_path, f"*{ext}")
        save_dir = os.path.dirname(save_file_path)
        self.settings.setValue("last_save_folder", save_dir)

        if not save_dir:
            return

        destination = save_file_path
        i = 1
        while os.path.exists(destination):
            destination = os.path.join(save_dir, f"{base} ({i}){ext}")
            i += 1

        try:
            shutil.copy(source, destination)
        except Exception as e:
            print(f"Save failed: {e}")
            return

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec())