//! PaperDaemon's desktop shell. It starts the engine (`paperdaemon --headless --announce`) as a child,
//! owns the window and the tray, and keeps the engine running while the window is closed. Quit in the
//! tray stops the daemon loop and ends the engine with everything it started.
//!
//! The engine announces itself on its first line of output:
//! `PAPERDAEMON_READY {"port": 8770, "token": "...", "webview": [...]}`. The window opens the engine's own page
//! with the pairing token in the URL fragment, the same way the development window does, its web view started
//! with the arguments the engine named for the graphics card it chose (the card to use, and WebGPU's Direct3D 11
//! backend on a card without Direct3D 12: paperdaemon/gpus.py).
//!
//! The engine executable is `engine\PaperDaemon.exe` next to the shell, or whatever
//! `PAPERDAEMON_ENGINE` names (a development checkout points it at `.venv\Scripts\paperdaemon.exe`).
//!
//! Updates are checked only when the user asks: "Check for updates" in the tray, or the Settings screen's Tools, whose
//! request reaches the shell as the engine's output line `PAPERDAEMON_SHELL check-updates`. The shell reads
//! the release's latest.json, shows the version and its changes, and on Update downloads the installer,
//! verifies its signature, stops the engine and installs; the installer starts the new version. The data
//! folder and the saved sign-ins are not touched. PAPERDAEMON_UPDATE_URL names another latest.json (tests).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, Wry, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_updater::UpdaterExt;

const READY: &str = "PAPERDAEMON_READY ";

struct Engine {
    child: Child,
    port: u16,
    token: String,
    webview: String, // the web view's arguments the engine named; empty: as WebView2 ships
    paused: bool,
    #[cfg(windows)]
    _job: job::Job, // held for its Drop: closing it ends the engine's whole process tree
}

struct Shell {
    engine: Mutex<Option<Engine>>,
    pause_item: Mutex<Option<MenuItem<Wry>>>,
}

fn engine_path() -> PathBuf {
    if let Some(p) = std::env::var_os("PAPERDAEMON_ENGINE") {
        return PathBuf::from(p);
    }
    let here = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_default();
    here.join("engine").join("PaperDaemon.exe")
}

/// Start the engine and wait for its announcement. Its later output lines are read for what it asks of the
/// shell.
fn start_engine(app: AppHandle) -> Result<Engine, String> {
    let exe = engine_path();
    let mut cmd = Command::new(&exe);
    cmd.args(["--headless", "--announce"])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console flashes up
    }
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("could not start the engine at {}: {}", exe.display(), e))?;
    #[cfg(windows)]
    let job = job::Job::new_kill_on_close(&child);

    let out = child.stdout.take().ok_or("the engine has no output pipe")?;
    let mut lines = BufReader::new(out).lines();
    let (port, token, webview) = loop {
        match lines.next() {
            Some(Ok(line)) => {
                if let Some(rest) = line.strip_prefix(READY) {
                    let v: serde_json::Value =
                        serde_json::from_str(rest).map_err(|e| format!("bad announcement: {}", e))?;
                    let port = v["port"].as_u64().ok_or("announcement without a port")? as u16;
                    let token = v["token"].as_str().ok_or("announcement without a token")?.to_string();
                    let webview = v["webview"].as_array().map(|a| {
                        a.iter().filter_map(|x| x.as_str()).collect::<Vec<_>>().join(" ")
                    }).unwrap_or_default();
                    break (port, token, webview);
                }
            }
            _ => {
                let _ = child.kill();
                return Err("the engine stopped before it was ready (is another PaperDaemon running?)".into());
            }
        }
    };
    // Keep reading, or the engine blocks once the pipe fills; act on what it asks of the shell.
    std::thread::spawn(move || {
        for line in lines.map_while(Result::ok) {
            let line = line.trim();
            if line == "PAPERDAEMON_SHELL check-updates" {
                check_for_updates(app.clone());
            } else if let Some(rest) = line.strip_prefix("PAPERDAEMON_SHELL webview ") {
                // the Renderer or its card changed: the window started again with the web view's new arguments
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(rest) {
                    let args: Vec<String> = v.as_array().map(|a| {
                        a.iter().filter_map(|x| x.as_str().map(String::from)).collect()
                    }).unwrap_or_default();
                    restart_window(app.clone(), args);
                }
            } else if let Some(text) = line.strip_prefix("PAPERDAEMON_SHELL status ") {
                // the tray's tooltip: what PaperDaemon is doing right now
                if let Some(tray) = app.tray_by_id("tray") {
                    let _ = tray.set_tooltip(Some(text));
                }
            }
        }
    });
    Ok(Engine {
        child,
        port,
        token,
        webview,
        paused: false,
        #[cfg(windows)]
        _job: job,
    })
}

/// One request to the engine's API, from this machine. Returns the status code.
fn api_post(port: u16, token: &str, path: &str) -> Option<u16> {
    api_post_json(port, token, path, "{}")
}

fn api_post_json(port: u16, token: &str, path: &str, body: &str) -> Option<u16> {
    let mut s = TcpStream::connect(("127.0.0.1", port)).ok()?;
    let req = format!(
        "POST /api/v1{} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {}\r\n\
         Content-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        path, token, body.len(), body
    );
    s.write_all(req.as_bytes()).ok()?;
    let mut answer = String::new();
    s.read_to_string(&mut answer).ok()?;
    answer.split_whitespace().nth(1)?.parse().ok()
}

fn show_window(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
        return;
    }
    let _ = build_window(app, "", None);
}

/// The window, made: the engine's page (at `pane`, when one is named) in a web view started with the arguments the
/// engine named, where `place` puts it (else at its usual size). Ok once the web view is up.
fn build_window(app: &AppHandle, pane: &str, place: Option<(tauri::PhysicalPosition<i32>, tauri::PhysicalSize<u32>)>)
    -> Result<(), String> {
    let shell = app.state::<Shell>();
    let target = shell.engine.lock().unwrap().as_ref().map(|e| (e.port, e.token.clone(), e.webview.clone()));
    let Some((port, token, webview)) = target else { return Err("no engine".into()) };
    let go = if pane.is_empty() { String::new() } else { format!("&pane={}", pane) };
    let url = format!("http://127.0.0.1:{}/#pair={}{}", port, token, go);
    let url = url.parse().map_err(|_| "bad address".to_string())?;
    let mut builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url));
    if !webview.is_empty() {
        // wry's own arguments (no mini menu, no SmartScreen) are given again: set, they are replaced
        builder = builder.additional_browser_args(&format!(
            "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection {}", webview));
    }
    let w = builder
        .title("PaperDaemon")
        .inner_size(1160.0, 780.0)
        .min_inner_size(900.0, 620.0)
        .theme(Some(tauri::Theme::Dark))
        .background_color(tauri::window::Color(0x1E, 0x21, 0x20, 0xFF))
        // drops go to the page (Decompose takes files and pictures dragged from a browser), not to the shell
        .disable_drag_drop_handler()
        .build()
        .map_err(|e| e.to_string())?;
    if let Some((pos, size)) = place {
        let _ = w.set_size(size);
        let _ = w.set_position(pos);
    }
    Ok(())
}

/// THE WINDOW ON A NEW CARD (the Renderer or its card changed): its web view started again with the arguments the
/// engine names now -- the card chosen, or no card at all for the processor -- where it was, back at Settings. A web
/// view's arguments are fixed while its browser process lives, so the window is taken down first, and made again once
/// that process has gone (tried a few times a second, at most fifty times). The engine is told which arguments the
/// window has, and until then its editor draws on no card.
fn restart_window(app: AppHandle, args: Vec<String>) {
    std::thread::spawn(move || {
        let shell = app.state::<Shell>();
        let target = {
            let mut guard = shell.engine.lock().unwrap();
            guard.as_mut().map(|e| { e.webview = args.join(" "); (e.port, e.token.clone()) })
        };
        let Some((port, token)) = target else { return };
        let told = serde_json::json!({ "args": args }).to_string();
        let Some(old) = app.get_webview_window("main") else {
            // no window open: the next one starts with these
            let _ = api_post_json(port, &token, "/render/window", &told);
            return;
        };
        let place = match (old.outer_position(), old.inner_size()) {
            (Ok(p), Ok(s)) => Some((p, s)),
            _ => None,
        };
        let _ = old.destroy();
        for _ in 0..50 {
            std::thread::sleep(std::time::Duration::from_millis(200));
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.destroy();                 // (the old one not gone yet, or one whose web view did not start)
                continue;
            }
            if build_window(&app, "settings", place).is_ok() {
                let _ = api_post_json(port, &token, "/render/window", &told);
                return;
            }
        }
        update_log("the window could not be started again on the new graphics card");
    });
}

fn toggle_pause(app: &AppHandle) {
    let shell = app.state::<Shell>();
    let mut guard = shell.engine.lock().unwrap();
    let Some(engine) = guard.as_mut() else { return };
    let path = if engine.paused { "/loop/start" } else { "/loop/stop" };
    if api_post(engine.port, &engine.token, path) == Some(200) {
        engine.paused = !engine.paused;
        if let Some(item) = shell.pause_item.lock().unwrap().as_ref() {
            let _ = item.set_text(if engine.paused { "Resume Daemon" } else { "Pause Daemon (Frees VRAM)" });
        }
    }
}

fn stop_engine(app: &AppHandle) {
    let shell = app.state::<Shell>();
    let taken = shell.engine.lock().unwrap().take();
    if let Some(mut engine) = taken {
        let _ = api_post(engine.port, &engine.token, "/loop/stop");
        let _ = engine.child.kill();
        let _ = engine.child.wait();
        // Dropping the job ends whatever the engine started (the daemon, the host, its model servers).
    }
}

/// Where the shell writes what an update check found: <data>\logs\updates.log.
fn update_log(line: &str) {
    let data = std::env::var_os("PAPERDAEMON_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("APPDATA").map(|a| PathBuf::from(a).join("PaperDaemon")));
    if let Some(dir) = data.map(|d| d.join("logs")) {
        let _ = std::fs::create_dir_all(&dir);
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(dir.join("updates.log")) {
            let _ = writeln!(f, "{}", line);
        }
    }
}

fn say(app: &AppHandle, text: &str, kind: MessageDialogKind) {
    update_log(text);
    if std::env::var_os("PAPERDAEMON_UPDATE_YES").is_none() {
        app.dialog().message(text).title("PaperDaemon").kind(kind).blocking_show();
    }
}

/// Look for an update, only because the user asked: show what there is, and install it if they agree.
fn check_for_updates(app: AppHandle) {
    std::thread::spawn(move || {
        let current = app.package_info().version.to_string();
        let mut builder = app.updater_builder();
        if let Some(url) = std::env::var_os("PAPERDAEMON_UPDATE_URL").and_then(|u| u.into_string().ok()) {
            match url.parse() {
                Ok(u) => match builder.endpoints(vec![u]) {
                    Ok(b) => builder = b,
                    Err(e) => return say(&app, &format!("The update address is not valid: {}", e), MessageDialogKind::Error),
                },
                Err(e) => return say(&app, &format!("The update address is not valid: {}", e), MessageDialogKind::Error),
            }
        }
        let updater = match builder.build() {
            Ok(u) => u,
            Err(e) => return say(&app, &format!("Updates are not set up in this build: {}", e), MessageDialogKind::Error),
        };
        let found = tauri::async_runtime::block_on(updater.check());
        let update = match found {
            Ok(Some(u)) => u,
            Ok(None) => return say(&app, &format!("PaperDaemon {} is the latest version.", current), MessageDialogKind::Info),
            Err(e) => return say(&app, &format!("PaperDaemon could not check for updates: {}", e), MessageDialogKind::Error),
        };
        let notes = update.body.clone().unwrap_or_default();
        let question = format!("PaperDaemon {} is available (you have {}).\n\n{}\n\nUpdate now? PaperDaemon closes, \
                                updates and starts again. Your settings, notepads and sign-ins stay as they are.",
                               update.version, current, notes.trim());
        update_log(&format!("found {} (have {})", update.version, current));
        let yes = std::env::var_os("PAPERDAEMON_UPDATE_YES").is_some()
            || app.dialog().message(question).title("PaperDaemon").kind(MessageDialogKind::Info)
                .buttons(MessageDialogButtons::OkCancelCustom("Update".into(), "Not now".into())).blocking_show();
        if !yes {
            return update_log("not now");
        }
        let app2 = app.clone();
        // the signature is verified before anything is installed; a download that does not match is refused
        let result = tauri::async_runtime::block_on(update.download_and_install(|_chunk, _total| {}, move || {
            update_log("downloaded and verified; stopping the engine to install");
            stop_engine(&app2);
        }));
        if let Err(e) = result {
            say(&app, &format!("The update was not installed: {}", e), MessageDialogKind::Error);
        }
    });
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open", true, None::<&str>)?;
    let pause = MenuItem::with_id(app, "pause", "Pause Daemon (Frees VRAM)", true, None::<&str>)?;
    let updates = MenuItem::with_id(app, "updates", "Check for updates", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &pause, &updates, &quit])?;
    *app.state::<Shell>().pause_item.lock().unwrap() = Some(pause);

    let mut tray = TrayIconBuilder::with_id("tray")
        .tooltip("Starting")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_window(app),
            "pause" => toggle_pause(app),
            "updates" => check_for_updates(app.clone()),
            "quit" => {
                stop_engine(app);
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_window(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

/// The folders earlier updates downloaded their installers to (`%TEMP%\PaperDaemon-<version>-updater-*`), taken
/// away: the updater leaves each behind, its installer run from it as the shell quits (173 MB an update). One still
/// in use (an installer running) is locked, and stays.
fn clear_old_updates() {
    let Ok(dir) = std::fs::read_dir(std::env::temp_dir()) else { return };
    for e in dir.flatten() {
        let name = e.file_name().to_string_lossy().to_string();
        if name.starts_with("PaperDaemon-") && name.contains("-updater-") && e.path().is_dir() {
            let _ = std::fs::remove_dir_all(e.path());
        }
    }
}

fn main() {
    std::thread::spawn(clear_old_updates);
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_window(app)))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(Shell {
            engine: Mutex::new(None),
            pause_item: Mutex::new(None),
        })
        .setup(|app| {
            let engine = start_engine(app.handle().clone())?;
            *app.state::<Shell>().engine.lock().unwrap() = Some(engine);
            build_tray(app)?;
            show_window(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("PaperDaemon could not start its window");

    app.run(|app, event| match event {
        // The last window closed: stay in the tray, the engine keeps working.
        RunEvent::ExitRequested { code: None, api, .. } => api.prevent_exit(),
        RunEvent::Exit => stop_engine(app),
        _ => {}
    });
}

#[cfg(windows)]
mod job {
    //! A kill-on-close job object: when the shell ends, however it ends, the engine and every process
    //! the engine started end with it.
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    pub struct Job(HANDLE);

    unsafe impl Send for Job {}

    impl Job {
        pub fn new_kill_on_close(child: &Child) -> Job {
            unsafe {
                let h = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if h.is_null() {
                    return Job(h);
                }
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                SetInformationJobObject(
                    h,
                    JobObjectExtendedLimitInformation,
                    &info as *const _ as *const _,
                    std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                AssignProcessToJobObject(h, child.as_raw_handle() as HANDLE);
                Job(h)
            }
        }
    }

    impl Drop for Job {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe { CloseHandle(self.0) };
            }
        }
    }
}
