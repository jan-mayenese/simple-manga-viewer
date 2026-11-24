import argparse
import sys

from PySide6.QtWidgets import QApplication

from .theme import apply_theme
from .window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="Open a manga archive or PDF.")
    parser.add_argument("file", nargs="?", help="path to a manga archive or PDF")
    args = parser.parse_args()

    app = QApplication([sys.argv[0]])
    app.setOrganizationName("SimpleMangaViewer")
    app.setApplicationName("Simple Manga Viewer")
    apply_theme(app)
    window = MainWindow()
    window.show()
    if args.file:
        window.open_file(args.file)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
