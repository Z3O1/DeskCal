# Third-party notices

The original DeskCal calendar/timetable uses Python/Tk/Win32 and remains MIT
licensed (`LICENSE`). This fork embeds the official Anki core; the integration
and combined distribution are AGPL-3.0-or-later (`COPYING`, `LICENSING.md`).

| Component | Used for | License |
| --- | --- | --- |
| [Anki 26.09.2](https://github.com/ankitects/anki/tree/26.09.2) / PyPI `anki==26.9.2` | Official Rust/Python collection, scheduling, templates and import/export | AGPL-3.0-or-later, with upstream component exceptions in `licenses/Anki-LICENSE.txt` |
| Matching `aqt==26.9.2` reviewer assets | HTML/CSS/JavaScript/MathJax; **no Qt GUI is installed or started by this fork** | Anki AGPL plus upstream vendored-component notices |
| [Microsoft WebView2 SDK 1.0.3856.49](https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.3856.49) | Transparent native card renderer | Original Microsoft terms in `anki_webview/WEBVIEW2-LICENSE.txt` in packages |
| [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk) | UI fonts | SIL Open Font License 1.1 (`fonts/OFL-LICENSE.txt`) |
| [Python](https://www.python.org/) runtime/stdlib | Standalone application runtime | Python Software Foundation License |
| [Tcl/Tk](https://www.tcl-lang.org/) | Original window/drawing toolkit | Tcl/Tk BSD-style license |
| [Nuitka](https://nuitka.net/) | Standalone compilation | Apache-2.0 |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Per-user Windows installer | Inno Setup License; notice in `licenses/InnoSetup-LICENSE.txt` |

Anki's vendored source exceptions include MathJax (Apache-2.0), jQuery/jQuery-UI
(MIT), plot.js (MIT), protobuf.js (BSD-3-Clause), translations and other items;
consult the exact upstream `LICENSE` and sources carried with the package.
The Rust backend also links its upstream crate dependencies, whose declarations
and lockfile are retained in the corresponding upstream source archive.

The core's Python dependencies include decorator, Markdown, orjson, protobuf,
requests/PySocks, typing_extensions and their transitive dependencies. Source
previews preserve their `.dist-info` license/copyright files. Standalone builds
copy dependency license files into `licenses/python-packages/`. Individual
component licenses are not replaced by the combined application's AGPL license.

WebView2 Runtime is a Microsoft runtime component required on the target Windows
machine; it is not included in the source preview. Fonts are loaded privately,
not installed system-wide. The source preview requires Windows x64 Python 3.14
with Tk; the standalone build also includes Python.

The hosted setup build preserves the exact Inno Setup compiler's license with the
installer payload. Inno Setup and its copyright/website notices are unmodified;
its compiler is used only for packaging, not executed as part of normal DeskCal use.

No external local Anki profile, AnkiConnect add-on, personal dark-card CSS or Zoom
config is redistributed or read by the embedded integration. Manual synchronization
uses the official AnkiWeb service via Anki's native backend. Windows DPAPI is an OS
API, not an additional bundled library; passwords are never persisted, and optional
user-encrypted session tokens remain in the personal data directory, never packages.
