from pathlib import Path
from threading import Event
from time import monotonic

from PySide6.QtCore import QEvent, QPointF, QSettings, QSignalBlocker, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QPainter, QPen, QPolygonF, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QPushButton, QSizePolicy, QSlider, QStackedWidget, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from .documents import DOCUMENT_EXTENSIONS, natural_key, open_document
from .jobs import Job
from .preferences import DEFAULT_SPEED, MAX_SPEED, MIN_SPEED, PORTABLE, SHORTCUTS, PreferencesDialog, load_bindings
from .reader import PageView, ZOOM_MODES
from .theme import MANGO_LEAF


class BookName(QLabel):
    def __init__(self):
        super().__init__(objectName="bookName", textFormat=Qt.TextFormat.PlainText)
        self.full_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_name(self, name):
        self.full_text = name
        self.setToolTip(name)
        self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, self.width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class ZoomPicker(QComboBox):
    def __init__(self):
        super().__init__()
        self.setItemDelegate(QStyledItemDelegate(self))
        self.view().setMouseTracking(True)
        self.currentIndexChanged.connect(self._highlight_current_option)

    def _highlight_current_option(self, selected):
        # The popup moves its own selection with the pointer or arrow keys.
        current_background = QBrush(QColor(MANGO_LEAF))
        for row in range(self.count()):
            self.setItemData(row, current_background if row == selected else None, Qt.ItemDataRole.BackgroundRole)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#c9cdd6"), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        x, y = self.width() - 14, self.height() / 2
        painter.drawPolyline(QPolygonF([QPointF(x - 3, y - 1), QPointF(x, y + 2), QPointF(x + 3, y - 1)]))


class MainWindow(QMainWindow):
    book_opened = Signal(int, object, object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Manga Viewer")
        self.setWindowIcon(QIcon(str(Path(__file__).with_name("assets") / "unripe-mango.png")))
        self.setAcceptDrops(True)
        self.setMinimumSize(640, 440)
        self.resize(1120, 780)

        self.settings = QSettings()
        self.speed = max(MIN_SPEED, min(MAX_SPEED, self.settings.value("scrollSpeed", DEFAULT_SPEED, int)))
        self.bindings = load_bindings(self.settings)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.view = PageView(self.pool)
        self.view.current_page_changed.connect(self._page_changed)
        self.book_opened.connect(self._finish_open, Qt.ConnectionType.QueuedConnection)
        self._open_generation = 0
        self._cancel_open = Event()
        self._target = None
        self._windowed_geometry = None
        self._shortcuts = []
        self._scroll_keys = {}
        self._scroll_fraction = 0.0
        self._scroll_time = 0.0
        self._scroll_timer = QTimer(self, interval=16, timerType=Qt.TimerType.PreciseTimer)
        self._scroll_timer.timeout.connect(self._scroll_tick)
        self._notice_timer = QTimer(self, singleShot=True)
        self._notice_timer.timeout.connect(self._hide_notice)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toolbar = self._toolbar()
        layout.addWidget(self.toolbar)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._welcome())
        self.stack.addWidget(self.view)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self._notice_bar())
        self.footer = self._footer()
        layout.addWidget(self.footer)
        self.setCentralWidget(content)
        self._page_changed(0)

        self._set_layout(self.settings.value("longStrip", False, bool))
        zoom = self.settings.value("zoom", "window", str)
        self._select_zoom(zoom if zoom in ZOOM_MODES else "window")
        geometry = self.settings.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)
        self._install_shortcuts()
        QApplication.instance().installEventFilter(self)

    def _toolbar(self):
        toolbar = QWidget(objectName="toolbar")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(10)

        self.open_button = QPushButton("Open file…", objectName="openButton")
        self.open_button.clicked.connect(self._choose_file)
        row.addWidget(self.open_button)
        self.book_name = BookName()
        self.book_name.set_name("Simple Manga Viewer")
        row.addWidget(self.book_name, 1)

        group_frame = QFrame(objectName="layoutGroup")
        group_layout = QHBoxLayout(group_frame)
        group_layout.setContentsMargins(3, 3, 3, 3)
        group_layout.setSpacing(2)
        group = QButtonGroup(group_frame)
        for label, strip in [("Single page", False), ("Long strip", True)]:
            button = QPushButton(label, checkable=True)
            button.setProperty("layoutChoice", True)
            button.clicked.connect(lambda checked, strip=strip: self._set_layout(strip))
            group.addButton(button, int(strip) + 1)
            group_layout.addWidget(button)
        self.layout_group = group
        row.addWidget(group_frame)

        self.zoom_picker = ZoomPicker()
        self.zoom_picker.setAccessibleName("Zoom")
        for mode, label in ZOOM_MODES.items():
            self.zoom_picker.addItem(label, mode)
        self.zoom_picker.currentIndexChanged.connect(self._set_zoom)
        row.addWidget(self.zoom_picker)

        self.fullscreen_button = QPushButton("Fullscreen")
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        row.addWidget(self.fullscreen_button)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self._show_settings)
        row.addWidget(self.settings_button)
        return toolbar

    def _welcome(self):
        welcome = QWidget(objectName="welcome")
        column = QVBoxLayout(welcome)
        column.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.setSpacing(0)
        icon = QLabel()
        icon.setPixmap(self.windowIcon().pixmap(QSize(112, 112), self.devicePixelRatioF()))
        column.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(21)
        column.addWidget(QLabel("Open a manga", objectName="welcomeTitle"), 0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(7)
        column.addWidget(QLabel("Drop an archive or PDF anywhere in this window.", objectName="welcomeHint"),
                         0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(20)
        column.addWidget(QLabel("CBZ · CBR · CB7 · ZIP · RAR · 7Z · PDF", objectName="formats"),
                         0, Qt.AlignmentFlag.AlignHCenter)
        return welcome

    def _notice_bar(self):
        self.notice = QWidget(objectName="notice")
        row = QHBoxLayout(self.notice)
        row.setContentsMargins(16, 6, 16, 6)
        self.notice_text = QLabel(objectName="noticeText", wordWrap=True, textFormat=Qt.TextFormat.PlainText)
        row.addWidget(self.notice_text, 1)
        dismiss = QPushButton("×", accessibleName="Dismiss message")
        dismiss.setProperty("nav", True)
        dismiss.clicked.connect(self._hide_notice)
        row.addWidget(dismiss)
        self.notice.hide()
        return self.notice

    def _nav_button(self, glyph, action, callback):
        button = QPushButton(glyph, accessibleName=SHORTCUTS[action][0])
        button.setFixedWidth(36)
        button.setProperty("nav", True)
        button.clicked.connect(callback)
        return button

    def _footer(self):
        footer = QWidget(objectName="footer")
        row = QHBoxLayout(footer)
        row.setContentsMargins(16, 8, 16, 8)
        row.setSpacing(10)
        self.previous_page = self._nav_button("‹", "previous_page", lambda: self._step_page(-1))
        self.next_page = self._nav_button("›", "next_page", lambda: self._step_page(1))
        self.previous_book = self._nav_button("«", "previous_book", lambda: self._step_book(-1))
        self.next_book = self._nav_button("»", "next_book", lambda: self._step_book(1))
        self.seek = QSlider(Qt.Orientation.Horizontal, accessibleName="Go to page")
        self.seek.valueChanged.connect(self.view.go_to)
        self.page_count = QLabel("", alignment=Qt.AlignmentFlag.AlignCenter, objectName="pageCount")
        self.page_count.setMinimumWidth(72)
        divider = QFrame(objectName="divider")
        divider.setFixedSize(1, 20)
        row.addWidget(self.previous_page)
        row.addWidget(self.seek, 1)
        row.addWidget(self.page_count)
        row.addWidget(self.next_page)
        row.addWidget(divider)
        row.addWidget(self.previous_book)
        row.addWidget(self.next_book)
        return footer

    def _set_layout(self, strip):
        self.layout_group.button(int(strip) + 1).setChecked(True)
        self.view.set_layout(strip)
        self.settings.setValue("longStrip", strip)
        self._focus_view()

    def _set_zoom(self, _index):
        mode = self.zoom_picker.currentData()
        self.view.set_zoom(mode)
        self.settings.setValue("zoom", mode)
        self._focus_view()

    def _select_zoom(self, mode):
        self.zoom_picker.setCurrentIndex(self.zoom_picker.findData(mode))

    def _toggle_fullscreen(self):
        if not self.isFullScreen():
            self._windowed_geometry = self.saveGeometry()
        self.setWindowState(self.windowState() ^ Qt.WindowState.WindowFullScreen)

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self._toggle_fullscreen()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            fullscreen = self.isFullScreen()
            was_fullscreen = bool(event.oldState() & Qt.WindowState.WindowFullScreen)
            if fullscreen != was_fullscreen:
                self.toolbar.setVisible(not fullscreen)
                self.footer.setVisible(not fullscreen)
                self.view.set_fullscreen(fullscreen)
                self._focus_view()

    def contextMenuEvent(self, event):
        if self.isFullScreen():
            menu = QMenu()
            exit_action = menu.addAction("Exit fullscreen")
            if menu.exec(event.globalPos()) is exit_action:
                self._exit_fullscreen()
            event.accept()
        else:
            super().contextMenuEvent(event)

    def _focus_view(self):
        if self.stack.currentWidget() is self.view:
            self.view.setFocus(Qt.FocusReason.OtherFocusReason)

    def _choose_file(self):
        self._stop_scroll()
        start = self.settings.value("lastFolder", str(Path.home()), str)
        patterns = " ".join(f"*{suffix}" for suffix in sorted(DOCUMENT_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Open manga", start, f"Manga files ({patterns});;All files (*)")
        self.activateWindow()
        self._focus_view()
        if path:
            self.open_file(Path(path))

    def open_file(self, path):
        self._stop_scroll()
        self._hide_notice()
        path = Path(path).expanduser().absolute()
        self._cancel_open.set()
        self._cancel_open = Event()
        cancelled = self._cancel_open
        self._target = path
        self._open_generation += 1
        generation = self._open_generation
        self.book_name.set_name(f"Opening {path.name}…")
        self.pool.start(Job(
            lambda: None if cancelled.is_set() else open_document(path, cancelled),
            lambda result, error: self.book_opened.emit(generation, result, error),
        ), 1)

    @Slot(int, object, object)
    def _finish_open(self, generation, document, error):
        if generation != self._open_generation:
            return
        target = self._target
        self._target = None
        if error:
            current = self.view.document
            self.book_name.set_name(current.path.name if current else "Simple Manga Viewer")
            self._show_notice(f"Could not open {target.name}. {error}")
            return
        self.stack.setCurrentWidget(self.view)
        self.view.set_document(document)
        self.book_name.set_name(document.path.name)
        self.settings.setValue("lastFolder", str(document.path.parent))
        self._focus_view()

    def _page_changed(self, index):
        document = self.view.document
        count = len(document.pages) if document else 0
        with QSignalBlocker(self.seek):
            self.seek.setRange(0, max(0, count - 1))
            self.seek.setValue(index)
        self.seek.setEnabled(count > 1)
        self.previous_page.setEnabled(index > 0)
        self.next_page.setEnabled(index + 1 < count)
        self.previous_book.setEnabled(bool(count))
        self.next_book.setEnabled(bool(count))
        self.page_count.setText(f"{index + 1} / {count}" if count else "—")
        self.page_count.setToolTip(document.pages[index].name if document else "")

    def _step_page(self, offset):
        self._focus_view()
        index = self.view.index + offset
        if self.view.document and 0 <= index < len(self.view.document.pages):
            self.view.go_to(index)

    def _last_page(self):
        if self.view.document:
            self.view.go_to(len(self.view.document.pages) - 1)

    def _step_book(self, offset):
        document = self.view.document
        current = self._target or (document.path if document else None)
        if not current:
            return
        try:
            books = sorted(
                (path for path in current.parent.iterdir()
                 if path.suffix.lower() in DOCUMENT_EXTENSIONS and path.is_file()),
                key=lambda path: (natural_key(path.name), path.name),
            )
            index = books.index(current) + offset
        except (OSError, ValueError) as error:
            self._show_notice(f"Could not find neighboring manga. {error}")
            return
        if 0 <= index < len(books):
            self.open_file(books[index])
        else:
            self._show_notice("No previous manga in this folder." if offset < 0 else "No next manga in this folder.",
                              temporary=True)

    def _show_notice(self, message, temporary=False):
        self._notice_timer.stop()
        self.notice_text.setText(message)
        self.notice.show()
        if temporary:
            self._notice_timer.start(2600)

    def _hide_notice(self):
        self._notice_timer.stop()
        self.notice.hide()

    def _show_settings(self):
        self._stop_scroll()
        dialog = PreferencesDialog(self, self.bindings, self.speed)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.speed = dialog.speed.value()
            self.settings.setValue("scrollSpeed", self.speed)
            self.bindings = dialog.bindings()
            for action, keys in self.bindings.items():
                for i, key in enumerate(keys):
                    self.settings.setValue(f"shortcuts/{action}/{i}", key)
            self._install_shortcuts()
        dialog.deleteLater()
        self.activateWindow()
        self._focus_view()

    def _install_shortcuts(self):
        for shortcut in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts.clear()
        actions = {
            "open": self._choose_file,
            "preferences": self._show_settings,
            "previous_page": lambda: self._step_page(-1),
            "next_page": lambda: self._step_page(1),
            "first_page": lambda: self.view.go_to(0),
            "last_page": self._last_page,
            "previous_book": lambda: self._step_book(-1),
            "next_book": lambda: self._step_book(1),
            "single_page": lambda: self._set_layout(False),
            "long_strip": lambda: self._set_layout(True),
            "fullscreen": self._toggle_fullscreen,
            "exit_fullscreen": self._exit_fullscreen,
        }
        for mode in ZOOM_MODES:
            actions[mode] = lambda mode=mode: self._select_zoom(mode)
        for action, keys in self.bindings.items():
            for text in filter(None, keys):
                key = QKeySequence.fromString(text, PORTABLE)
                shortcut = QShortcut(key, self)
                shortcut.setAutoRepeat(action in {"previous_page", "next_page"})
                if action in {"scroll_up", "scroll_down"}:
                    direction = -1 if action == "scroll_up" else 1
                    shortcut.activated.connect(lambda key=key[0].key(), direction=direction: self._hold_scroll(key, direction))
                else:
                    shortcut.activated.connect(actions[action])
                self._shortcuts.append(shortcut)
        for action, button in {
            "open": self.open_button, "preferences": self.settings_button,
            "previous_page": self.previous_page, "next_page": self.next_page,
            "previous_book": self.previous_book, "next_book": self.next_book,
            "single_page": self.layout_group.button(1), "long_strip": self.layout_group.button(2),
            "fullscreen": self.fullscreen_button,
        }.items():
            names = [QKeySequence.fromString(key, PORTABLE).toString() for key in filter(None, self.bindings[action])]
            label = SHORTCUTS[action][0]
            button.setToolTip(f"{label} ({' / '.join(names)})" if names else label)

    def _hold_scroll(self, key, direction):
        if self.view.document:
            self._scroll_keys[key] = direction
            self._scroll_time = monotonic()
            self._scroll_fraction = 0.0
            self.view.scroll_by(direction * max(1, round(self.speed / 60)))
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()

    def _scroll_tick(self):
        now = monotonic()
        direction = next(reversed(self._scroll_keys.values()))
        self._scroll_fraction += direction * self.speed * min(0.05, now - self._scroll_time)
        self._scroll_time = now
        pixels = int(self._scroll_fraction)
        self._scroll_fraction -= pixels
        self.view.scroll_by(pixels)

    def _stop_scroll(self):
        self._scroll_timer.stop()
        self._scroll_keys.clear()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyRelease and self._scroll_keys and not event.isAutoRepeat():
            self._scroll_keys.pop(event.key(), None)
            if not self._scroll_keys:
                self._stop_scroll()
        elif watched is self and event.type() == QEvent.Type.WindowDeactivate:
            self._stop_scroll()
        return super().eventFilter(watched, event)

    @staticmethod
    def _dropped_file(event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.suffix.lower() in DOCUMENT_EXTENSIONS and path.is_file():
                    return path
        return None

    def dragEnterEvent(self, event):
        if self._dropped_file(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = self._dropped_file(event)
        if path:
            event.acceptProposedAction()
            self.open_file(path)

    def closeEvent(self, event):
        geometry = self._windowed_geometry if self.isFullScreen() else self.saveGeometry()
        if geometry is not None:
            self.settings.setValue("windowGeometry", geometry)
        self.settings.sync()
        self._stop_scroll()
        self._cancel_open.set()
        self.pool.clear()
        self.pool.waitForDone()
        super().closeEvent(event)
