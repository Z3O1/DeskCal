# DeskCal · Anki fork

- Fork of `HANSEIDON/DeskCal`, upstream baseline `e6c62fc` (1.3.2).
- Keep the original Tk/Win32 shell, wallpaper glass, Calendar, Timetable, dimensions and gear/settings. Add Anki as a peer tab, using the full content area.
- Anki tab connects ONLY to an already running Anki through standard AnkiConnect v1. If unavailable, clicking must not change the current view, launch Anki, or show a dialog.
- No DeskCal-specific Anki add-on; the old `anki_deskcal` add-on was backed up and removed.
- Never open the personal collection directly, modify its stored templates, or close/restart/start the user's Anki automatically.
- Keep original rendered HTML/CSS/JS/media. Apply background transparency only at runtime. Preserve the existing dark-card CSS and Zoom settings via read-only compatibility; do not claim universal add-on compatibility.
- Never commit/package personal `data/`, API keys, profiles, logs, or collections. The WebView never receives the AnkiConnect key or native scheduling token.

## Mandatory testing boundary

**Do not run tests in the user's current Windows desktop session.** The previous visible Tk regression suite caused disruptive flashing.

- No test windows, screenshots, mouse/keyboard automation, or visible/native Windows test sessions without fresh explicit permission.
- Use Linux headless unit tests and `QT_QPA_PLATFORM=offscreen`, with `DISPLAY` and `WAYLAND_DISPLAY` removed. Use isolated profiles and random test ports only.
- `tools/test_anki_headless.py` is the supported test entry point. Do not run `tests/test_deskcal.py`, `tests/test_anki_tab_windows.py`, screenshot scripts or `real_input_check.py` on the current desktop.
- Windows-only font loading, compositing, focus and final GUI acceptance remain unverified after later changes unless tested in an explicitly authorized, genuinely isolated environment. Do not describe headless tests as proof of Windows GUI correctness.
- Earlier Windows suite: 326/329 passed; the 3 failures were font checks. Its logs show `AddFontResourceExW` failed to load bundled fonts from the WSL UNC path. Font loading code/assets were not changed; local Windows-package validation is still needed.

## Development

- Logic: `anki_api.py`, `anki_effects.py`, `anki_tab.py`; keep hooks in `deskcal.py` minimal.
- Native transparent child: `anki_webview/CardHost.cs`; uses WebView2 SDK 1.0.3856.49, serves Anki assets/media without a new HTTP listener.
- Never patch AnkiConnect or other installed add-ons to gain functionality without explicit approval.
- Operator approved retaining default first-normal-launch autostart and following `Z3O1/DeskCal` releases only. Current development must not write startup registry entries or launch Windows processes. Actual installation/launch is not authorized by a request to run tests.
- Preserve the original Calendar/Timetable data directory and single-instance mechanism; do not migrate/delete original data or auto-close the original DeskCal. A real switch may require the user to exit the old app manually.
- Only fork installers are eligible for self-update; invalidate cached upstream update metadata while preserving the user's update-check preference. Never silently install upstream DeskCal over the Anki fork.
