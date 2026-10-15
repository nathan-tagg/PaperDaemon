# Tasks

## 1. Shell

- [x] 1.1 Build the Tauri 2 window and tray with Open, Pause daemon and Quit; verify closing the window leaves the daemon answering a test page on a test mirror
- [x] 1.2 Add single instance; verify a second start brings up the running window and starts no engine

## 2. Engine build and installer

- [x] 2.1 Freeze the engine as a one-folder build; verify it starts, serves the API and runs the test suite from the build
- [ ] 2.2 Build a per-user Windows installer with a Start menu entry and an uninstaller that keeps data unless asked; verify on a clean user account
- [x] 2.3 Dropped by the maintainer: no login start, ever. Update checks run only when the user asks; verify a fresh install makes no update call (network capture)
- [ ] 2.4 Sign release builds; verify the installer shows the publisher

## 3. Real-run evidence

- [ ] 3.1 Install a release build on the maintainer's machine with the maintainer's go-ahead, run it through a day of real pages with the window closed, and record the outcome here

## Notes from the first build

- The shell is `shell/` (Rust, Tauri 2.x): it starts `engine\PaperDaemon.exe --headless --announce`, reads the
  announced port and pairing token, opens the engine's page, keeps running in the tray when the window
  closes, and holds the engine in a kill-on-close job object so nothing outlives it. `tools/build_app.py`
  assembles `dist/app/` (the shell as PaperDaemon.exe, WebView2Loader.dll, `engine/`).
- Verified on a test data folder: the window opens dark with the setup page; closing it frees WebView2 while
  the engine keeps answering; a second start opens no second engine; ending the shell ends the engine and its
  children. Not yet verified by hand: the tray menu's Open / Pause / Quit (no clicks were possible).
- Built without Visual Studio: Rust's x86_64-pc-windows-gnullvm target with the llvm-mingw toolchain
  (`shell/.cargo/config.toml` links its unwinder statically). The MSVC toolchain works as well.
