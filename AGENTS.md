# DeskCal · embedded Anki fork

- Fork of `HANSEIDON/DeskCal`, upstream baseline `e6c62fc` (1.3.2).
- Current architecture: **embedded official Anki core**, authorized by the user.
  The earlier requirement to use only external AnkiConnect is superseded.
- Keep the original Tk/Win32 shell, wallpaper glass, Calendar, Timetable, dimensions,
  gear/settings, original data files and single-instance mechanism.
- Never open/modify a personal external `collection.anki2`, alter installed Anki
  templates/add-ons, or start/close/restart the user's external Anki automatically.
- All embedded data lives at `APP_DIR/anki/`. No configurable external collection
  path and no auto-migration from `%APPDATA%/Anki2`; import user-selected `.apkg`
  packages into the independent collection instead. Do not share live collections.
- Use official native scheduling/import/export/sync, not handcrafted SQL or FSRS.
  All collection operations, including shutdown, run on ONE worker. The sole
  cross-thread exception is the official thread-safe Rust progress/abort RPCs,
  as used by Anki Qt; never touch Python collection/DB state in the monitor.
  Invalidate state before writes and never retry uncertain scheduling/full-sync writes.
- The user authorized AnkiWeb sync and requires login AND deck selection inside
  the ORIGINAL gear settings. Do not restore the card-page deck menu.
- Sync only on an explicit action; login does not sync. Require explicit direction
  and a second default-cancel confirmation before full upload/download. Back up
  locally first; never silently choose a direction, even for an empty collection.
- Sync applies to the ENTIRE AnkiWeb collection, not the selected study deck.
  Warn that cloud changes affect other clients; switching accounts forces a new
  full-sync decision. Cancelling does not roll back already completed sync changes.
- Never save passwords. Persist optional session tokens only with user-level
  Windows DPAPI, without LOCAL_MACHINE or a plaintext fallback. Never expose any
  login/session credential to templates, logs, package manifests or source archives.
- Do not claim desktop add-on compatibility. Desktop hooks are not loaded;
  custom scheduling JS is blocked explicitly.
- Preserve original rendered templates/JS/media; transparency is runtime-only.
  The WebView never receives a scheduling token or collection/filesystem path.
- Never commit/package personal `data/`, keys, profiles, logs or collections.

## No testing or desktop disruption

**The user explicitly said not to run tests.** A later request authorizes
building on GitHub Actions Windows runners, but NOT running the application or
any tests there. Cloud compiler/build-tool execution is allowed for that request;
local Windows execution, real login/sync and deployment remain separately gated.
Do not run unit/integration/GUI
suites, open test windows, take screenshots, or automate keyboard/mouse input.
Do not execute Windows programs during development. Syntax parsing, source
inspection, downloading dependency wheels and assembling ZIP files are allowed;
do not describe them as runtime/Windows verification. Do not log in to AnkiWeb,
call Windows credential APIs, or execute real sync while developing.

Historical tests under `tests/`, `tools/test_anki_headless.py`, `anki_api.py` and
`anki_effects.py` describe the old external-AnkiConnect architecture. They are
not the current runtime and are not proof that the embedded implementation works.
Update them only if a future request authorizes testing work; do not run them now.

Earlier visible Windows regression: 326/329 passed; the 3 font failures showed
`AddFontResourceExW` could not load bundled fonts from a WSL UNC path. Fonts are
unchanged. Windows compositing, focus, native extensions and final packaging
acceptance are not verified by static checks or old test results.

## Development and packaging

- `anki_core.py`: official `anki==26.9.2`, isolated collection, scheduling/import.
- `anki_sync.py`: native AnkiWeb sync, full-sync decisions, progress/cancellation.
- `anki_credentials.py`: optional user-bound DPAPI session-token storage.
- `anki_settings.py`: login, sync and deck/import/export controls in gear settings.
- `anki_render.py`: card transport with no native authority exposed to templates.
- `anki_tab.py`: controller and single worker; minimal shell hooks.
- `anki_webview/CardHost.cs`: transparent WebView2 child; SDK 1.0.3856.49.
  Serves bundled reviewer/media files without a new HTTP listener.
- `tools/prepare_anki_assets.py`: extract matching aqt wheel's static assets only;
  preserve upstream source archive under `build/anki-upstream`.
- `tools/prepare_anki_vendor.py`: download/unpack Windows wheels without running
  them; source preview defaults to Windows x64 Python 3.14. No aqt/PyQt GUI dependency.
- `tools/build.py`: standalone Nuitka packaging includes core, metadata/resources,
  notices and source. Do not execute Windows compilers on the local desktop;
  explicitly authorized GitHub Actions builds may run them on hosted runners.
- `.github/workflows/build-windows.yml`: manual Windows x64/Python 3.12 build;
  compile/package only, upload ZIP/checksum/log artifacts, never auto-publish Release.
- `.github/workflows/build-setup.yml` and `tools/build_setup.py`: reuse a successful
  standalone artifact only if runtime sources/version/provenance still match;
  compile Inno Setup on the hosted runner, never execute Setup.exe or DeskCal.exe.
- `tools/DeskCal.iss`: distinct per-user AppID and DeskCal-Anki directory; no auto
  close/start/restart, no recursive personal-data deletion. AppMutex requires the
  user to exit existing DeskCal manually. Existing data/junctions must survive.
- Publishing a public Release requires an explicit user request (e.g. "release
  setup"). Verify assets first, never overwrite an existing Release/tag, and attach
  Setup/ZIP checksums plus licensing/source. Do not install it locally as part of publishing.
- `anki_vendor/`, `anki_webview/assets/`, `build/`, `dist/` are generated/ignored.
- Keep upstream MIT notice; embedded integration/combined distribution is AGPL-3+
  with `COPYING`, `LICENSING.md`, dependency notices and corresponding sources.
- User approved default first-normal-launch autostart and following only
  `Z3O1/DeskCal` releases. Do not write startup entries during development.
- Do not deploy or switch the currently running app without user approval. A real
  switch can require the user to exit the old DeskCal manually; never auto-close it.
