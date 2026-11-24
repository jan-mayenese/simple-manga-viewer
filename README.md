# Simple Manga Viewer

A Python desktop reader for Linux and Windows. Open CBZ, CBR, CB7, ZIP, RAR, 7Z, and PDF files from the file picker, or drag one into the window. Archives can contain JPEG, PNG, JPEG XL, AVIF, WebP, GIF, BMP, or TIFF pages.

## Install and run

Use Python 3.10 or newer. Run these commands from the project folder.

**Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m manga_viewer
```

**Windows (PowerShell)**

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m manga_viewer
```

For compressed CBR and RAR files, the viewer tries UnRAR on `PATH` first and falls back to the bundled copy on x64 Linux and Windows. It can also use other tools supported by `rarfile` when neither UnRAR copy can run. [Compatible extraction tools](https://rarfile.readthedocs.io/).

On Windows ARM64, run the viewer with x64 Python for AVIF support. [Pillow wheel support](https://pillow.readthedocs.io/en/stable/releasenotes/11.3.0.html#avif-support-in-wheels).

You can also pass a file path to `python -m manga_viewer` to open it at launch.

## Build a Linux executable

To make an x64 Linux one-file build, use a build environment with a C compiler, Python development headers, `patchelf`, and Qt's system libraries. This recipe was tested on Ubuntu 22.04.

```sh
python -m pip install . 'Nuitka==4.3.5' jsonschema zstandard
python -m nuitka --mode=onefile --enable-plugin=pyside6 \
  --user-package-configuration-file=nuitka-linux.nuitka-package.config.yml \
  --include-data-files=LICENSE=LICENSE --include-module=PIL.AvifImagePlugin \
  --output-dir=dist --output-filename=simple-manga-viewer-linux-x86_64 \
  --remove-output nuitka_launcher.py
```

Run `dist/simple-manga-viewer-linux-x86_64` to launch the viewer. The executable includes Python, Qt, and the UnRAR fallback.

To list the viewer in your file manager’s **Open With** menu, save this as `~/.local/share/applications/io.github.valkexia.SimpleMangaViewer.desktop` and replace the executable path with the absolute path to your build.

```ini
[Desktop Entry]
Type=Application
Name=Simple Manga Viewer
Exec="/absolute/path/to/simple-manga-viewer-linux-x86_64" %f
Terminal=false
Categories=Graphics;Viewer;
MimeType=application/vnd.comicbook+zip;application/vnd.comicbook-rar;application/x-cb7;
```

## Reading controls

Choose **Single page** or **Long strip** in the toolbar. The page slider jumps to a page in either layout. Page images and manga in the same folder are sorted naturally, so `Chapter 2` comes before `Chapter 10`.

Press **Enter** to toggle fullscreen. Fullscreen hides the toolbar, page controls, and scrollbars and removes the margins around the images. Page navigation, scrolling, and zoom shortcuts still work. Use **Shift+mouse wheel** to pan sideways when the image is wider than the screen. To leave with the mouse, right-click and choose **Exit fullscreen**.

| Action | Default keys |
| --- | --- |
| Open a file | Ctrl+O |
| Previous or next page | Left / Right or A / D |
| Scroll up or down | Up / Down or W / S |
| First or last page | Home / End |
| Previous or next manga in the folder | Page Up / Page Down |
| 100%, fit to window, fit to width, fit to height | 1 / 2 / 3 / 4 |
| Single page / Long strip | 5 / 6 |
| Toggle fullscreen | Enter |
| Exit fullscreen | Esc |
| Settings | Ctrl+, |

In **Settings**, you can set two bindings per action and adjust the speed of held-key scrolling. The viewer remembers your shortcuts, scroll speed, layout, zoom, window size, and last opened folder.

## License

Simple Manga Viewer’s own code is available under the [MIT License](LICENSE).

The bundled UnRAR executables are distributed under RARLAB’s UnRAR license. [Linux UnRAR license](manga_viewer/vendor/unrar/linux-x86_64/LICENSE.txt) · [Windows UnRAR license](manga_viewer/vendor/unrar/windows-x86_64/LICENSE.txt) · [RARLAB downloads](https://www.rarlab.com/rar_add.htm).
