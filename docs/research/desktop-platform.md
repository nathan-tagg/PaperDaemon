# Desktop platform for PaperDaemon

Research note, checked 2026-09-26. Desk research only: nothing was installed or benchmarked. Sizes
marked *measured* were read from the published wheels and archives; everything else is cited in
[Sources](#sources).

## Recommendation

**Use Tauri 2 (the stable 2.x line) as the shell. Keep the HTML/CSS/JS UI. Run the Python engine as
its own process that the shell starts, health-checks and stops.** The shell owns the tray icon and
the window. Closing the window destroys the webview; the shell stays in the tray and the engine keeps
watching the tablet.

Why Tauri:

1. **Least rework for the most gain.** The UI is already web code talking to an HTTP API, so it moves
   over nearly unchanged. Tauri adds what pywebview lacks: tray icon and menus, a tray-only mode,
   single instance, autostart, window-state, updater, NSIS/MSI installers, and a Windows 11 Mica
   window effect.
2. **Light where it can be.** The shell is about 3 MB (benchmark build output). Closing the window
   frees the WebView2 processes (maintainer guidance) and reopening creates a new one; a whole Tauri
   app started in about 0.7 s in the benchmark.
3. **Crash isolation.** A WebView crash cannot take the daemon down with it, and the shell attaches to
   the one running engine instead of starting a second daemon.
4. **Android.** The same frontend builds for Android with Tauri 2, or sits in a thin native WebView
   app. Either reaches the engine over the tunnel.
5. **Healthy project.** Apache-2.0 or MIT; 2.11.5 shipped 2026-07-01.

What it costs:

- **A new development toolchain** (users need nothing): Rust via rustup plus Microsoft C++ Build Tools
  ("Desktop development with C++"). Node is optional; plain HTML/CSS/JS works. An empty app took
  about 4 minutes to build on the benchmark's CI runner.
- **Some Rust.** Spawn and watch the engine, tray menu, close-to-tray. Tauri has no sidecar supervisor;
  an open feature request (2025-10) puts production-grade supervision at "200+ lines" of boilerplate.
- **No memory win on Windows.** WebView2 is Chromium. In the empty-app benchmark, counting all child
  processes: Tauri about 317 MB, Wails 323 MB, Electron 278 MB. pywebview uses the same WebView2.
  Tauri saves disk, not RAM.
- **Tauri 3 is in alpha** (since 2026-09-13). Build on 2.x and expect a migration later; its size is
  unknown.
- **The updater calls a release endpoint,** so it would have to be opt-in.

**Runner-up: stay on pywebview.** No new toolchain, pure Python, and on Windows it renders with the same
WebView2, so it looks and weighs the same as Tauri. Add a tray (pystray or a small ctypes wrapper),
hide on close through the `closing` event, and ship a PyInstaller one-folder build inside an installer
(Briefcase MSI or Inno Setup). You give up Tauri's ready-made tray, updater, installer and
single-instance pieces; pystray has had no release since 2023; `webview.start()` must own the main
thread; Android would mean Buildozer and Python on the phone. Pick it if installing Rust and the C++
Build Tools is a deal-breaker. The UI stays portable, so moving to Tauri later is cheap.

**"Native window" is not "no web engine."** Tauri, pywebview, Wails and Neutralino draw the UI with
WebView2 inside an ordinary OS window: no browser frame, tabs or address bar, but Chromium underneath.
If the goal is no web engine at all, the options are PySide6 with Qt Quick (most mature, built-in tray,
heavy, and its Android tool runs only on Linux or macOS) or Flet 1.0 (simplest Python, the same Python
UI builds for Android, released 2026-09-15, no tray). Both mean rewriting the UI.

**The engine sets the download size, not the shell.** vl-convert (79 MB), numpy (40 MB) and Pillow
(14 MB) are about 133 MB unpacked (*measured*); those three wheels plus a stripped CPython 3.12 are
about 71 MB compressed. Choose the shell for polish, tray and Android, not for megabytes.

**For the Android client, whatever the shell:** the engine must also listen on the tunnel address, not
only 127.0.0.1, and keep the pairing token. Android 9 and later block cleartext HTTP by default, so
serve TLS or add a network-security-config exception for the tunnel address. (If the tunnel is
Tailscale, `tailscale serve` fronts a local port with an automatic HTTPS certificate.)

## Comparison

| | Renders with (Windows) | Shell size¹ | RAM¹ | Start¹ | Python engine | Tray | Android path | Toolchain needed² | License | Status, Sept 2026 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Tauri 2** | WebView2 | ≈3 MB | ≈317 MB | ≈0.7 s | Separate process (sidecar) | Built in | Same frontend, Tauri Android | Rust, C++ Build Tools | Apache-2.0 or MIT | 2.11.5 (Jul 1); 3.0 alpha |
| Electron | Its own Chromium | ≈384 MB | ≈278 MB | ≈0.2 s | Child process | Built in | None | Node.js | MIT | 44.4.5 (Sep 23) |
| **pywebview** (today) | WebView2 in WinForms | Python + small libs (pywebview, pythonnet) | WebView2 + Python | n/m | Same or second process | None (pystray) | Buildozer, Python on phone | None | BSD-3-Clause | 6.2.1 (Apr 15) |
| Flet | Flutter engine | 78–100+ MB reported³ | n/m | n/m | Embedded Python | None (pystray) | Same Python UI to APK/AAB | VS C++ workload for `flet build` | Apache-2.0 | 1.0.1 (Sep 22) |
| PySide6 / Qt Quick | Qt Quick | Qt: 73 MB wheel, 202 MB unpacked, before trimming | n/m | n/m | Same process | Built in | Same QML; Linux/macOS build host only | None to run; MSVC tools for `pyside6-deploy` | LGPLv3 | 6.11.2 (Aug 18) |
| Wails | WebView2 | ≈11 MB | ≈323 MB | ≈0.6 s | Child process | v3 only | v3, experimental | Go 1.25 (+ npm) | MIT | v2.14 stable; v3 beta |
| Neutralinojs | WebView2 | ≈2 MB | ≈497 MB | n/m | Extension process | Built in | None | Node (neu CLI) | MIT | 6.9.0 (Jul 24) |
| Avalonia | Skia | ≈80 MB self-contained (2024 report) | n/m | n/m | Child process | Built in | Same C#/XAML | .NET 10 SDK | MIT | 12.1.3 (Sep 22) |
| Slint | Own renderer | Python wheel 12 MB | n/m | n/m | Same process (pre-release) | Built in (1.17+) | Rust or C++ only | None | GPLv3, royalty-free or commercial | 1.18.1 (Sep 21) |
| NiceGUI native | WebView2 via pywebview | Python + pywebview | WebView2 + Python | n/m | Inside the engine's FastAPI | None | Phone browser only | None | MIT | 3.17.1 (Sep 18) |
| *Flutter (Dart)*⁴ | Flutter engine | ≈25 MB | ≈104 MB | ≈2.1 s | Child process | Package (tray_manager) | Same Dart UI | Flutter SDK, VS C++ workload | BSD-3-Clause | 3.47.5 (Sep 18) |
| *Compose Multiplatform*⁴ | Skia on the JVM | Bundles a JRE | n/m | n/m | Child process | Basic | Same Kotlin UI | JDK 17+, Gradle | Apache-2.0 | 1.12.1 (Sep 22) |

¹ Elanis "web-to-desktop" empty-app benchmark on GitHub's windows-latest runner, results updated
2026-09-04: build output size, memory of the main process plus its children (release build), start
time (release build). CI numbers with a wide margin; n/m = not measured there. The benchmark's second
memory method gives the same order (Electron ≈104 MB, Tauri ≈204 MB, Wails ≈201 MB, Flutter ≈82 MB).
² Beyond Python 3.12 and uv. On the development PC (checked 2026-09-26) a JDK 25 is present; no Rust,
Node, Go, .NET SDK or Visual Studio was found.
³ Flet issue #4620, December 2024, before 1.0. Not re-measured.
⁴ Not on the original list.

## Candidates

### Tauri 2 (recommended)

Rust core plus the OS webview (WebView2, WKWebView, WebKitGTK). Stable 2.11.5 (2026-07-01). The 3.0
alphas (2026-09-13 to 2026-09-21) ship a separate runtime crate that bundles Chromium (CEF) for
identical rendering everywhere.

- **Engine:** a sidecar is declared in `bundle.externalBin` with a target-triple file name
  (`paperdaemon-engine-x86_64-pc-windows-msvc.exe`) and spawned through the shell plugin. `externalBin`
  takes one file; a PyInstaller one-folder build goes in `bundle.resources` and is started from Rust
  (a maintainer calls that "more of a hassle", but it avoids one-file unpacking).
- **Tray and background:** the `tray-icon` feature; prevent exit when the last window closes and close
  (not hide) the window so WebView2 exits, then recreate it on demand (maintainer answer, discussion
  #6308).
- **Look:** full CSS, custom title bars, `windowEffects` "mica" (Windows 11 only).
- **UI loading:** bundle the frontend (the engine then needs CORS for the shell's origin), or point the
  window at the engine's URL (then any Tauri command needs a `remote` capability entry).
- **Android:** added in 2.0 (October 2024); the team noted that mobile tooling was not yet on par with desktop.
  Needs Android Studio, the SDK and NDK, and `JAVA_HOME`.
- **Cross-platform:** Windows, macOS, Linux. Each OS has its own webview, so test all three.

### Electron

Bundles Chromium and Node: the fastest cold start and the same rendering everywhere, but about 384 MB
of build output, and on Windows no lower memory than the WebView2 shells in the benchmark. You ship
Chromium, so its security fixes reach users only when you ship. Tray is built in (main process); the
engine would be a child process. No Android. Needs Node. MIT; 44.x is current, a new major every eight
weeks, three supported. It fails "lightweight."

### pywebview (today; runner-up)

6.2.1 (2026-04-15), BSD-3-Clause. On Windows it hosts WebView2 in a WinForms window through pythonnet.

- `webview.start()` must be called from the main thread. A `closing` handler that returns `False`
  cancels the close, which gives hide-to-tray.
- No tray of its own: pystray (0.19.5, September 2023, LGPLv3) or a small ctypes `Shell_NotifyIcon`
  wrapper.
- Hosting: inside the engine process (fewest processes, but a GUI crash stops the daemon and WebView2
  stays resident while hidden) or as a second Python process (isolated, costs a second interpreter).
- Packaging: PyInstaller has a pywebview hook. Android goes through Buildozer; 6.0 made that path
  Kivy-free, though the freezing guide still lists Kivy.
- BeeWare's Positron (a Toga web view plus a Python server, packaged by Briefcase, Android included) is
  the same idea with Briefcase packaging.

### Flet

1.0 (2026-09-15), 1.0.1 (2026-09-22); Apache-2.0. The UI is written in Python and drawn by Flutter.
Packaged apps embed Python (3.12 to 3.14) through serious_python; a mobile package index covers 100+
packages including numpy; Android now loads packages straight from the APK.

- **Pros:** no web engine; the same Python UI builds for Android; one tool builds every target.
- **Cons:** a UI rewrite. No tray: the feature request was turned into a discussion, and pystray is the
  suggested workaround. `flet build windows` needs Visual Studio 2022 or 2026 with the C++ workload and
  Developer Mode (the Flutter SDK downloads itself); `flet pack` is a PyInstaller route without them.
  Built apps exit without running `atexit` handlers, so the daemon should not live inside one. 1.0 is
  eleven days old.

### PySide6 / Qt Quick (QML)

6.11.2 (2026-08-18); LGPLv3 (GPL and commercial also offered).

- **Pros:** GPU-drawn and polished. The FluentWinUI3 style (since Qt 6.8) gives a Windows 11 look; a few
  controls fall back to Fusion. `QSystemTrayIcon` (a QtWidgets class, so use `QApplication`) plus
  running with no windows open. The engine can live in-process.
- **Cons:** heavy (*measured*: the PySide6-Essentials wheel is 73 MB, 202 MB unpacked, before trimming).
  A UI rewrite in QML. `pyside6-deploy` wraps Nuitka (default 4.1.1) and wants MSVC tools on Windows.
  `pyside6-android-deploy` runs only on Linux or macOS hosts (WSL here), needs JDK 17+ and NDK r28c, and
  the phone runs CPython 3.14 built by python-for-android.

### Wails (Go)

v2.14.0 (2026-08-10) is the stable line and has no built-in tray (a v2 request was closed as not
planned). v3 has been in beta since 2026-08-02 (beta.26 on 2026-09-25) and adds a tray; the project says
"Wails v2 remains the current stable release." Go 1.25+; npm is optional but most templates use it.
Android and iOS are experimental in v3. Benchmark: about 11 MB, 323 MB, 0.6 s. MIT. It adds Go to a
Python project without any gain over Tauri here.

### Neutralinojs

6.9.0 (2026-07-24); MIT core. Tiny (about 2 MB) on WebView2, with a tray API. "Extensions" run
processes in any language over a WebSocket, but Neutralino does not kill them when it exits. Highest
memory of the web shells in the benchmark (about 497 MB; possibly a CI artifact). No mobile. The `neu`
CLI comes from npm. Smaller project (about 8.6k stars).

### Avalonia (.NET)

12.0 (2026-04-07), 12.1.3 (2026-09-22); MIT; moved to .NET 10. Targets Windows, macOS, Linux, iOS,
Android and WebAssembly; 12.0 brought large Android gains (NativeAOT startup 1,960 ms to 460 ms).
TrayIcon with a NativeMenu, fully supported on Windows and macOS. Fluent theme. Size: about 80 MB
self-contained and untrimmed in a 2024 report; trimming and NativeAOT shrink that (not measured here).
Needs the .NET SDK and a C#/XAML rewrite; the same UI runs on Android. Paid add-ons exist but are not
needed.

### Slint

1.18.1 (2026-09-21); a tray icon arrived in 1.17 (2026-06-24). The Python bindings are still
pre-release (PyPI 1.18.1b1). Android works from Rust or C++, not Python. Licenses: GPLv3, a
royalty-free license for desktop, mobile and web apps, or commercial. Light native renderer with
Fluent, Material and Cupertino styles. Promising, but the Python and Android story is not there yet.

### NiceGUI native mode

3.17.1 (2026-09-18); MIT. The UI is written in Python (Vue and Quasar components) and driven from the
server over a websocket. `native=True` opens it in pywebview in a separate process, and
`ui.run_with(app)` mounts it inside an existing FastAPI app, so the engine could serve it directly.
Packaged with `nicegui-pack` (PyInstaller). No tray; same WebView2 footprint as pywebview. No native
Android client, though a phone browser could open the same pages over the tunnel.

### Strong options not on the list

- **Flutter (Dart)**, 3.47.5 (2026-09-18), BSD-3-Clause. Lowest memory in the benchmark (about 104 MB),
  its own renderer, and first-class Android from the same UI code. Tray via the `tray_manager` package
  (0.7.0, leanflutter). Needs the Flutter SDK, the VS C++ workload and a Dart rewrite. The best pick if
  the Android app matters more than keeping the web UI.
- **Compose Multiplatform (Kotlin)**, 1.12.1 (2026-09-22), Apache-2.0. The same UI on Android (native)
  and desktop (JVM, packaged with jpackage and jlink, which bundle a JRE; no cross-building). Its Tray
  composable is basic (a 2022 write-up). JVM memory and startup.
- **PyTauri.** Tauri driven from Python through PyO3; its precompiled wheel needs no Rust. It would fit
  PaperDaemon well, but it has had no release or main-branch commit since September 2025. Watch it.
- **Also looked at:** Electrobun (Bun plus system webview or CEF; v2 in beta, "a young project" per
  InfoWorld in March 2026); Deno 2.9's `deno desktop` (experimental, June 2026); BeeWare Toga (WinForms
  on Windows, a dated look, with a WinUI 3 backend still an open request); Kivy (last release December
  2024); .NET MAUI (no Linux).

## Packaging the Python engine

*Measured* sizes, Windows x64:

| Piece | Compressed | Unpacked |
|---|---|---|
| vl-convert-python 1.9.0.post1 (one native module) | 30.6 MB | 79.2 MB |
| numpy 2.5.3 (19.6 MB of it is OpenBLAS) | 12.0 MB | 40.0 MB |
| Pillow 12.3.0 | 6.9 MB | 14.1 MB |
| CPython 3.12.14, python-build-standalone `install_only_stripped` | 21.0 MB | not measured |

| Tool | Latest | How it works | Good | Watch out |
|---|---|---|---|---|
| PyInstaller | 6.22.3 (2026-09-12) | Freezes into one folder or one file | Best documented; hooks for keyring, uvicorn, numpy, Pillow, pywebview | One-file unpacks on every launch; antivirus flags; no cross-compiling |
| Nuitka | 4.2.2 (2026-09-22) | Compiles Python to C | Faster startup; used by `pyside6-deploy` | Long builds; needs VS 2022+, Nuitka's MinGW64 (Python 3.12 and older) or Zig; AGPLv3 compiler with a runtime exception for your output |
| Briefcase | 0.4.5 (2026-09-08) | Embeds the python.org embeddable package; MSI (WiX) or ZIP | Real installer, code signing, console apps | Its own project layout; redundant when Tauri builds the installer |
| python-build-standalone + uv | 20260924 | Ship a relocatable CPython and install the dependencies into it at build time | No freezing tricks: the same Python as development | No venvs, no `pip.exe`; start with `python -m`; build-time paths linger in sysconfig |
| PyApp | active (2026-08) | Rust launcher unpacks python-build-standalone and your wheel on first run | Self-update commands | Needs Rust; first run installs |
| cx_Freeze | 8.7.1 (2026-09-23) | Freezer | Active, builds MSI | Smaller community |

PyOxidizer is dormant (last release December 2022).

Pitfalls, in the order they bite:

1. **One folder, not one file.** One-file unpacks to a temp folder on every launch ("a little slower to
   start") and is the pattern antivirus heuristics distrust. PyInstaller's docs say to get one-folder
   working first.
2. **Windowed builds have no stdout.** Since PyInstaller 5.7, `sys.stdout` and `sys.stderr` are `None`
   under `--noconsole`; uvicorn's default log formatter calls `isatty()` and crashes. Pass
   `log_config=None` or log to a file.
3. **Hooks cover most of the engine.** PyInstaller ships hooks for keyring (it collects
   `keyring.backends` and the package metadata), uvicorn (all submodules), numpy, Pillow and pywebview.
   vl_convert and rmscene have none; one is a single native module and the other pure Python, so they
   should freeze, but only a real run of the frozen engine proves it.
4. **Sign both executables.** Signing "dramatically reduces" Defender and SmartScreen false positives.
   SignPath Foundation signs OSI-licensed projects for free from their public CI builds; the publisher
   shown is "SignPath Foundation." Azure Artifact Signing is paid and takes individuals only in the US
   and Canada.
5. **Build on each OS.** PyInstaller output is tied to the OS and Python version; use a CI matrix.
6. **Relocation.** Virtual environments are "not considered as movable or copyable." With
   python-build-standalone, install into that interpreter's own site-packages. Windows builds ship no
   `pip.exe`, and build-time paths stay in sysconfig (uv patches them).
7. **One engine, supervised.** Make the engine single-instance (the port is a natural lock) so a second
   launch attaches instead of starting a second daemon. Let the shell health-check and restart it, and
   stop it with an API call rather than a process kill.

A recipe for PaperDaemon:

1. Engine: PyInstaller one-folder, windowed, file logging and `log_config=None`, single-instance on
   port 8770.
2. Shell: Tauri 2 with the existing frontend, a tray menu (Open, Quit), exit prevented when the window
   closes, and the window destroyed to release WebView2.
3. The shell ships the engine folder as a resource, starts it hidden when port 8770 does not answer,
   polls a health endpoint, restarts it on failure, and asks it to shut down on Quit.
4. Both executables signed through SignPath in GitHub Actions; Windows first, macOS and Linux later in
   the same matrix.
5. Later: a Tauri Android build of the same frontend, pointed at the engine's tunnel address over HTTPS.

## Sources

All checked 2026-09-26.

Benchmarks and WebView2

- https://github.com/Elanis/web-to-desktop-framework-comparison (README; results updated 2026-09-04)
- https://github.com/tauri-apps/tauri/issues/5889
- https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/end-user-faq

Tauri

- https://v2.tauri.app/release/tauri/
- https://github.com/tauri-apps/tauri/releases (3.0.0-alpha.0, alpha.2 and tauri-runtime-cef tags)
- https://crates.io/crates/tauri (license)
- https://v2.tauri.app/start/prerequisites/
- https://v2.tauri.app/develop/sidecar/
- https://v2.tauri.app/learn/system-tray/
- https://v2.tauri.app/plugin/
- https://v2.tauri.app/reference/config/
- https://v2.tauri.app/security/capabilities/
- https://v2.tauri.app/blog/tauri-20/
- https://github.com/tauri-apps/tauri/discussions/2759
- https://github.com/tauri-apps/tauri/discussions/6308
- https://github.com/tauri-apps/plugins-workspace/issues/3062

Electron

- https://endoflife.date/electron
- https://www.electronjs.org/docs/latest/api/tray

pywebview, NiceGUI, BeeWare

- https://pywebview.flowrl.com/blog/pywebview6.html
- https://pywebview.flowrl.com/guide/installation.html
- https://pywebview.flowrl.com/guide/freezing.html
- https://pywebview.flowrl.com/api/
- https://pypi.org/project/pywebview/
- https://pypi.org/project/pystray/
- https://nicegui.io/documentation/section_configuration_deployment
- https://github.com/zauberzeug/nicegui/blob/main/examples/fastapi/main.py
- https://github.com/zauberzeug/nicegui/releases
- https://briefcase.beeware.org/en/stable/reference/commands/new/
- https://toga.beeware.org/en/stable/reference/platforms/windows.html
- https://github.com/beeware/toga/issues/2574

Flet

- https://flet.dev/blog/flet-1-0/
- https://flet.dev/docs/publish/
- https://flet.dev/docs/publish/windows/
- https://github.com/flet-dev/flet/releases
- https://github.com/flet-dev/flet/issues/954
- https://github.com/flet-dev/flet/issues/4620

PySide6 / Qt

- https://pypi.org/project/PySide6-Essentials/
- https://github.com/pyside/pyside-setup/blob/dev/sources/pyside6/doc/deployment/deployment-pyside6-deploy.rst
- https://github.com/pyside/pyside-setup/blob/dev/sources/pyside6/doc/deployment/deployment-pyside6-android-deploy.rst
- https://doc.qt.io/qt-6/qtquickcontrols-fluentwinui3.html
- https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QSystemTrayIcon.html

Wails, Neutralinojs

- https://v3.wails.io/blog/wails-v3-beta/
- https://v3.wails.io/status/
- https://v3.wails.io/getting-started/installation/
- https://v3.wails.io/guides/mobile/
- https://github.com/wailsapp/wails/releases
- https://github.com/wailsapp/wails/issues/4990
- https://github.com/neutralinojs/neutralinojs/releases
- https://github.com/neutralinojs/neutralinojs/blob/main/LICENSE
- https://neutralino.js.org/docs/release-notes/framework/
- https://neutralino.js.org/docs/how-to/extensions-overview/

Avalonia, Slint

- https://avaloniaui.net/blog/avalonia-12
- https://github.com/AvaloniaUI/Avalonia/discussions/21091
- https://github.com/AvaloniaUI/Avalonia/releases
- https://docs.avaloniaui.net/controls/navigation/trayicon
- https://github.com/AvaloniaUI/Avalonia/discussions/14633
- https://slint.dev/blog/slint-1.17-released
- https://slint.dev/blog/slint-1.18-released
- https://slint.dev/pricing
- https://pypi.org/project/slint/

Flutter, Compose, others

- https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json
- https://docs.flutter.dev/platform-integration/windows/setup
- https://pub.dev/packages/tray_manager
- https://github.com/JetBrains/compose-multiplatform/releases
- https://kotlinlang.org/docs/multiplatform/compose-native-distribution.html
- https://composables.com/blog/compose-desktop
- https://github.com/pytauri/pytauri
- https://pytauri.github.io/pytauri/latest/usage/pytauri-wheel/
- https://www.infoworld.com/article/4137964/first-look-electrobun-for-typescript-powered-desktop-apps.html
- https://github.com/blackboardsh/electrobun/releases
- https://deno.com/blog/v2.9
- https://github.com/kivy/kivy/releases
- https://learn.microsoft.com/en-us/dotnet/maui/what-is-maui

Packaging and signing

- https://pyinstaller.org/en/stable/operating-mode.html
- https://github.com/pyinstaller/pyinstaller/releases
- https://github.com/pyinstaller/pyinstaller/issues/7339
- https://github.com/pyinstaller/pyinstaller/blob/develop/PyInstaller/hooks/hook-keyring.py
- https://github.com/pyinstaller/pyinstaller-hooks-contrib/blob/master/_pyinstaller_hooks_contrib/stdhooks/hook-uvicorn.py
- https://www.pythonguis.com/faq/problems-with-antivirus-software-and-pyinstaller/
- https://nuitka.net/user-documentation/user-manual.html
- https://pypi.org/project/Nuitka/
- https://briefcase.beeware.org/en/stable/reference/platforms/windows/
- https://github.com/astral-sh/python-build-standalone
- https://github.com/astral-sh/python-build-standalone/releases/tag/20260924
- https://gregoryszorc.com/docs/python-build-standalone/main/quirks.html
- https://docs.python.org/3/library/venv.html
- https://ofek.dev/pyapp/latest/
- https://github.com/marcelotduarte/cx_Freeze/releases
- https://github.com/indygreg/PyOxidizer
- https://pypi.org/project/vl-convert-python/
- https://pypi.org/project/numpy/
- https://pypi.org/project/pillow/
- https://signpath.org/
- https://www.devclass.com/security/2026/01/14/code-signing-windows-apps-may-be-easier-and-more-secure-with-new-azure-artifact-service/4079554

Android and networking

- https://developer.android.com/privacy-and-security/security-config
- https://tailscale.com/kb/1312/serve
