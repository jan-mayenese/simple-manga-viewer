from string import Template

from PySide6.QtGui import QColor, QPalette


MANGO_GREEN = "#6fc219"
MANGO_LEAF = "#1d7b01"
TEXT_ON_ACCENT = "#101114"


def apply_theme(app):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in {
        "Window": "#18191e", "WindowText": "#eceef1", "Base": "#101114",
        "AlternateBase": "#202127", "Text": "#eceef1", "Button": "#25272e",
        "ButtonText": "#eceef1", "Highlight": MANGO_GREEN, "HighlightedText": TEXT_ON_ACCENT,
        "ToolTipBase": "#292c33", "ToolTipText": "#eceef1", "PlaceholderText": "#a1a6b1",
    }.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#757982"))
    app.setPalette(palette)
    app.setStyleSheet(Template("""
        QWidget#toolbar, QWidget#footer { background: #18191e; }
        QWidget#toolbar { border-bottom: 1px solid #2b2d33; }
        QWidget#footer { border-top: 1px solid #2b2d33; }
        QWidget#welcome { background: #101114; }
        QLabel#bookName { color: #e4e7ec; font-weight: 600; }
        QLabel#welcomeTitle { color: #f1f2f5; font-size: 32px; font-weight: 700; }
        QLabel#welcomeHint { color: #b1b5bf; font-size: 14px; }
        QLabel#formats { color: #969ba7; font-size: 12px; }
        QLabel#pageCount, QLabel#columnHeading { color: #b1b5bf; }
        QLabel#settingsError { color: #ffb6a6; }
        QWidget#notice { background: #25272e; border-top: 1px solid #3a3d45; }
        QLabel#noticeText { color: #e6e8ec; }
        QToolTip { border: 1px solid #454a53; padding: 4px; }
        QPushButton, QComboBox {
            background: #22242a; border: 1px solid #393c45; border-radius: 6px;
            min-height: 28px; padding: 2px 10px;
        }
        QPushButton:hover, QComboBox:hover { background: #2d3038; }
        QPushButton:focus, QComboBox:focus, QLineEdit:focus { border: 1px solid $mango_highlight; }
        QPushButton:pressed { background: #343842; }
        QPushButton:disabled { color: #777c87; background: #1c1e23; border-color: #292b32; }
        QPushButton#openButton {
            color: $text_on_accent; background: $mango_green; border-color: $mango_green; font-weight: 700;
        }
        QPushButton#openButton:hover { background: $leaf_highlight; }
        QPushButton#openButton:pressed { background: $mango_shade; }
        QPushButton#openButton:focus { border-color: $mango_highlight; }
        QPushButton[layoutChoice="true"] { border-radius: 5px; border-color: transparent; background: transparent; }
        QPushButton[layoutChoice="true"]:hover { background: #292b33; }
        QPushButton[layoutChoice="true"]:focus { border-color: $mango_highlight; }
        QPushButton[layoutChoice="true"]:checked {
            background: $mango_outline; color: $mango_highlight; border-color: $mango_leaf;
        }
        QFrame#layoutGroup { background: #141519; border: 1px solid #31333b; border-radius: 8px; }
        QComboBox { padding-right: 24px; }
        QComboBox::drop-down { border: 0; width: 24px; }
        QComboBox::down-arrow { width: 0; height: 0; }
        QComboBox QAbstractItemView {
            background: #22242a; border: 1px solid #393c45;
            selection-background-color: $mango_green; selection-color: $text_on_accent;
        }
        QComboBox QAbstractItemView::item { padding: 5px 9px; }
        QFrame#divider { background: #353841; }
        QPushButton[nav="true"] { padding: 0 8px; min-height: 25px; font-size: 16px; }
        QLineEdit { background: #101114; border: 1px solid #393c45; border-radius: 4px; padding: 3px 6px; }
        QSlider::groove:horizontal { background: #363942; height: 4px; border-radius: 2px; }
        QSlider::sub-page:horizontal { background: $mango_shade; border-radius: 2px; }
        QSlider::handle:horizontal { background: $mango_green; width: 12px; margin: -4px 0; border-radius: 6px; }
        QSlider::handle:disabled { background: #62666f; }
        QSlider:focus { border: 1px solid $mango_highlight; border-radius: 4px; }
        QScrollBar { background: #17181d; }
        QScrollBar:vertical { width: 12px; }
        QScrollBar:horizontal { height: 12px; }
        QScrollBar::handle { background: #525663; border: 2px solid #17181d; border-radius: 5px; min-height: 24px; min-width: 24px; }
        QScrollBar::handle:hover { background: #707682; }
        QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
        QScrollBar::add-page, QScrollBar::sub-page { background: none; }
    """).substitute(
        mango_green=MANGO_GREEN,
        mango_leaf=MANGO_LEAF,
        mango_highlight="#b4f275",
        leaf_highlight="#9aee43",
        mango_shade="#44a203",
        mango_outline="#035500",
        text_on_accent=TEXT_ON_ACCENT,
    ))
