# Third-party notices

The original DeskCal calendar/timetable code uses only the Python standard library.
This fork adds an optional Anki tab using a transparent .NET/WebView2 child host.
The Windows release bundles the following third-party components so it can run
without a Python installation.

| Component | Used for | License |
| --- | --- | --- |
| [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk) | UI font (Chinese, Korean, Latin) | SIL Open Font License 1.1 |
| [Python](https://www.python.org/) 3.12 runtime and standard library | Runs the app | [Python Software Foundation License](https://docs.python.org/3/license.html) |
| [Tcl/Tk](https://www.tcl-lang.org/) 8.6 | Window and drawing toolkit (tkinter) | [Tcl/Tk license](https://www.tcl-lang.org/software/tcltk/license.html) (BSD-style) |
| [Nuitka](https://nuitka.net/) | Compiles `deskcal.py` to the bundled app (`DeskCal.exe`) | [Apache License 2.0](https://github.com/Nuitka/Nuitka/blob/main/LICENSE.txt) |

The full license texts are in the `licenses` folder of the release. In this
repository, the font license is `fonts/OFL-LICENSE.txt`.

The font is loaded privately by DeskCal while it runs. It is not installed on
your system.

## Anki tab in this fork

- Microsoft WebView2 SDK 1.0.3856.49: the .NET Core DLL and x64 loader are distributed
  with `anki_webview/WEBVIEW2-LICENSE.txt`, the SDK's original Microsoft license.
  WebView2 Runtime is a separately installed Microsoft component.
- Anki is a separately installed application; its reviewer CSS/JavaScript/media are
  loaded from that local installation, not redistributed in this fork's package.
  See [Anki's license](https://github.com/ankitects/anki/blob/main/LICENSE) for its
  AGPL-3.0-or-later and included-component notices.
- AnkiConnect is a separately installed standard HTTP API add-on, not a bundled
  DeskCal-specific add-on. See [its upstream source](https://github.com/FooSoft/anki-connect).
- Existing dark-card CSS and Zoom configuration are read only at runtime from the
  user's installed add-ons. Personal settings and API keys are never bundled.
