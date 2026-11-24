from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QKeySequenceEdit, QLabel,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)


SHORTCUTS = {
    "open": ("Open file", "Ctrl+O", ""),
    "preferences": ("Settings", "Ctrl+,", ""),
    "previous_page": ("Previous page", "Left", "A"),
    "next_page": ("Next page", "Right", "D"),
    "scroll_up": ("Scroll up", "Up", "W"),
    "scroll_down": ("Scroll down", "Down", "S"),
    "first_page": ("First page", "Home", ""),
    "last_page": ("Last page", "End", ""),
    "previous_book": ("Previous manga", "PgUp", ""),
    "next_book": ("Next manga", "PgDown", ""),
    "actual": ("100%", "1", ""),
    "window": ("Fit to window", "2", ""),
    "width": ("Fit to width", "3", ""),
    "height": ("Fit to height", "4", ""),
    "single_page": ("Single page", "5", ""),
    "long_strip": ("Long strip", "6", ""),
    "fullscreen": ("Toggle fullscreen", "Return", "Enter"),
    "exit_fullscreen": ("Exit fullscreen", "Esc", ""),
}

DEFAULT_SPEED = 1080
MIN_SPEED = 120
MAX_SPEED = 4200
PORTABLE = QKeySequence.SequenceFormat.PortableText


def load_bindings(settings):
    stored = {
        action: tuple(settings.value(f"shortcuts/{action}/{i}") for i in range(2))
        for action in SHORTCUTS
    }
    # A new default must not take over a key the user has already assigned.
    assigned = {key for keys in stored.values() for key in keys if key}
    return {
        action: tuple(
            saved if saved is not None else (default if default not in assigned else "")
            for saved, default in zip(stored[action], defaults)
        )
        for action, (_, *defaults) in SHORTCUTS.items()
    }


class PreferencesDialog(QDialog):
    def __init__(self, parent, bindings, speed):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(560, 616)

        self.speed = QSpinBox(minimum=MIN_SPEED, maximum=MAX_SPEED, singleStep=120, suffix=" px/s")
        self.speed.setValue(speed)
        form = QFormLayout()
        form.addRow("Keyboard scroll speed", self.speed)

        shortcut_table = QWidget()
        grid = QGridLayout(shortcut_table)
        grid.setContentsMargins(0, 2, 2, 2)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(5)
        grid.addWidget(QLabel("Action", objectName="columnHeading"), 0, 0)
        grid.addWidget(QLabel("Primary", objectName="columnHeading"), 0, 1)
        grid.addWidget(QLabel("Alternate", objectName="columnHeading"), 0, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        self.editors = {}
        for row, (action, (label, _, _)) in enumerate(SHORTCUTS.items(), start=1):
            grid.addWidget(QLabel(label), row, 0)
            editors = []
            for column, key in enumerate(bindings[action], start=1):
                editor = QKeySequenceEdit(QKeySequence.fromString(key, PORTABLE))
                editor.setMaximumSequenceLength(1)
                editor.setClearButtonEnabled(True)
                editor.setAccessibleName(f"{label}, {'primary' if column == 1 else 'alternate'}")
                grid.addWidget(editor, row, column)
                editors.append(editor)
            self.editors[action] = editors

        self.error = QLabel(objectName="settingsError", wordWrap=True)
        self.error.hide()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.reset_defaults)

        scroll = QScrollArea(widgetResizable=True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(shortcut_table)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def reset_defaults(self):
        self.speed.setValue(DEFAULT_SPEED)
        for action, editors in self.editors.items():
            for editor, key in zip(editors, SHORTCUTS[action][1:]):
                editor.setKeySequence(QKeySequence.fromString(key, PORTABLE))
        self.error.hide()

    def bindings(self):
        return {
            action: tuple(editor.keySequence().toString(PORTABLE) for editor in editors)
            for action, editors in self.editors.items()
        }

    def accept(self):
        assigned = {}
        for action, keys in self.bindings().items():
            label = SHORTCUTS[action][0]
            for key in filter(None, keys):
                if key in assigned:
                    native = QKeySequence.fromString(key, PORTABLE).toString(QKeySequence.SequenceFormat.NativeText)
                    self.error.setText(f"{native} is assigned to both {assigned[key]} and {label}.")
                    self.error.show()
                    return
                assigned[key] = label
        super().accept()
