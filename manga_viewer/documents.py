"""Archive indexing and page decoding, called from the reader's worker thread."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from io import BufferedRandom, BytesIO, FileIO
from math import sqrt
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
from threading import Event, Lock
from zipfile import ZipFile

from PIL import Image, ImageOps
import pillow_jxl  # Registers the JPEG XL decoder with Pillow.
import py7zr
from py7zr.io import Py7zIO, WriterFactory
from PySide6.QtCore import QSize
from PySide6.QtGui import QImage
from PySide6.QtPdf import QPdfDocument
import rarfile

from .rar_backend import configure_unrar


DOCUMENT_EXTENSIONS = {".cbz", ".cbr", ".cb7", ".zip", ".rar", ".7z", ".pdf"}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".jxl", ".avif", ".webp", ".gif", ".bmp", ".tif", ".tiff",
}
MAX_RENDER_PIXELS = 24_000_000


def natural_key(name):
    parts = re.split(r"([0-9]+)", name.casefold())
    return tuple(int(part) if index % 2 else part for index, part in enumerate(parts))


def is_page(name):
    path = PurePosixPath(name.replace("\\", "/"))
    return path.suffix.lower() in IMAGE_EXTENSIONS and not any(
        part.startswith(".") or part.casefold() == "__macosx" for part in path.parts
    )


@dataclass(frozen=True)
class Page:
    name: str
    size: QSize | None = None


class Document(ABC):
    def __init__(self, path, pages):
        self.path = path
        self.pages = pages

    @abstractmethod
    def render(self, index):
        """Return the decoded image and its logical size at 100% zoom."""


def raster_page(stream):
    with Image.open(stream) as source:
        ImageOps.exif_transpose(source, in_place=True)
        size = QSize(*source.size)
        has_alpha = "A" in source.getbands() or "transparency" in source.info
        if source.mode == "L" and not has_alpha:
            mode, pixel_format, stride = "L", QImage.Format.Format_Grayscale8, source.width
        elif has_alpha:
            mode, pixel_format, stride = "RGBA", QImage.Format.Format_RGBA8888, source.width * 4
        else:
            mode, pixel_format, stride = "RGB", QImage.Format.Format_RGB888, source.width * 3
        image = source if source.mode == mode else source.convert(mode)
        data = image.tobytes()
        rendered = QImage(data, image.width, image.height, stride, pixel_format)
        return rendered.copy(), size


class ArchiveDocument(Document):
    def __init__(self, path, archive, entries):
        super().__init__(path, [Page(entry.filename) for entry in entries])
        self.archive = archive
        self.entries = entries

    def render(self, index):
        entry = self.entries[index]
        try:
            if isinstance(self.archive, rarfile.RarFile):
                source = self.archive.getinfo_orig(entry)
                if source.compress_type != rarfile.RAR_M0:
                    configure_unrar()
                    # Decoder seeks within compressed RAR entries would restart UnRAR.
                    with BytesIO(self.archive.read(entry)) as buffered:
                        return raster_page(buffered)
            with self.archive.open(entry) as stream:
                return raster_page(stream)
        except rarfile.RarCannotExec as error:
            raise ValueError("No working RAR decoder was found. Install UnRAR or 7-Zip and add it to PATH.") from error


class ExtractedPage(BufferedRandom, Py7zIO):
    def __init__(self, path, cancelled):
        super().__init__(FileIO(path, "w+"))
        self.cancelled = cancelled

    def write(self, data):
        if self.cancelled.is_set():
            raise InterruptedError("Opening cancelled")
        return super().write(data)

    def size(self):
        position = self.tell()
        size = self.seek(0, 2)
        self.seek(position)
        return size


class PageFiles(WriterFactory):
    def __init__(self, directory, cancelled):
        self.directory = Path(directory)
        self.cancelled = cancelled
        self.files = {}
        self.lock = Lock()

    def create(self, filename):
        # Generated disk filenames keep archive paths out of filesystem writes.
        if self.cancelled.is_set():
            raise InterruptedError("Opening cancelled")
        with self.lock:
            path = self.directory / f"{len(self.files)}.page"
            stream = ExtractedPage(path, self.cancelled)
            self.files[filename] = path, stream
        return stream


class SevenZipDocument(Document):
    def __init__(self, path, cancelled):
        directory = TemporaryDirectory(prefix="manga-viewer-", ignore_cleanup_errors=True)
        try:
            with py7zr.SevenZipFile(path) as archive:
                names = {item.filename for item in archive.list() if item.is_file and is_page(item.filename)}
                factory = PageFiles(directory.name, cancelled)
                try:
                    if names:
                        # A single pass also handles solid archives in linear time.
                        archive.extract(targets=names, factory=factory)
                finally:
                    for _, stream in factory.files.values():
                        stream.close()
        except Exception:
            directory.cleanup()
            raise

        files = {name: file for name, (file, _) in factory.files.items()}
        super().__init__(path, [Page(name) for name in sorted(files, key=natural_key)])
        self.directory = directory
        self.files = files

    def render(self, index):
        with self.files[self.pages[index].name].open("rb") as stream:
            return raster_page(stream)


def load_pdf(path):
    document = QPdfDocument()
    error = document.load(str(path))
    if error == QPdfDocument.Error.IncorrectPassword:
        raise ValueError("This PDF requires a password.")
    if error != QPdfDocument.Error.None_:
        raise ValueError(f"Could not load the PDF ({error.name}).")
    return document


class PdfDocument(Document):
    def __init__(self, path):
        document = load_pdf(path)
        pages = []
        for index in range(document.pageCount()):
            points = document.pagePointSize(index)
            # PDF points are 1/72 in. Use 96 dpi as the standard 100% view.
            size = QSize(max(1, round(points.width() * 4 / 3)), max(1, round(points.height() * 4 / 3)))
            pages.append(Page(document.pageLabel(index) or str(index + 1), size))
        super().__init__(path, pages)

    def render(self, index):
        document = load_pdf(self.path)
        size = self.pages[index].size
        scale = min(1.5, sqrt(MAX_RENDER_PIXELS / (size.width() * size.height())))
        image = document.render(index, QSize(max(1, round(size.width() * scale)), max(1, round(size.height() * scale))))
        if image.isNull():
            raise ValueError("Could not render this PDF page.")
        return image, size


def open_document(path, cancelled: Event):
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        document = PdfDocument(path)
    elif suffix in {".cb7", ".7z"}:
        document = SevenZipDocument(path, cancelled)
    elif suffix in {".cbz", ".zip", ".cbr", ".rar"}:
        is_zip = suffix in {".cbz", ".zip"}
        archive = ZipFile(path) if is_zip else rarfile.RarFile(path)
        try:
            entries = [
                item for item in archive.infolist()
                if (not item.is_dir() if is_zip else item.is_file()) and is_page(item.filename)
            ]
            entries.sort(key=lambda item: natural_key(item.filename))
        except Exception:
            archive.close()
            raise
        document = ArchiveDocument(path, archive, entries)
    else:
        raise ValueError("Choose a CBZ, CBR, CB7, ZIP, RAR, 7Z or PDF file.")

    if not document.pages:
        raise ValueError("This file contains no readable pages.")
    return document
