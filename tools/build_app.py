"""Build the desktop app and its installer in one command.

    uv run python tools/build_app.py [--repo OWNER/NAME] [--update-key PUBLIC_KEY] [--native]
                                     [--skip-engine] [--skip-shell] [--stage FOLDER]

In order:
  1. the C decomposer (paperdaemon/pipeline/decompose/fastdecomp/build.py), for any x86-64 unless --native
  2. the icons (tools/make_icons.py)
  3. the frozen engine (tools/build_exe.py) -> build/engine/PaperDaemon
  4. Stockfish, downloaded once into build/stockfish, checked against its SHA-256, and put beside the engine
     with its license and a link to its source
  5. the Tauri shell and its NSIS installer, with dist/app/engine bundled into it

Result, in dist/app/:
    PaperDaemon.exe        the shell: the window and the tray (shell/, Tauri 2)
    WebView2Loader.dll     beside the shell when it was built with a GNU toolchain
    engine/                the frozen engine, with stockfish/ inside it
and the installer under shell/target/release/bundle/nsis/.

A release build names the GitHub repository its updates come from (--repo) and the public half of the update
key (--update-key, the text of the .pub file `npx tauri signer generate` writes). The private key signs the
update bundle; Tauri reads it from TAURI_SIGNING_PRIVATE_KEY and TAURI_SIGNING_PRIVATE_KEY_PASSWORD, which
are never written to a file here. Without --update-key the build makes no update bundle (a local build).

The shell needs Rust and a Windows linker (Visual Studio's C++ build tools, or Rust's
x86_64-pc-windows-gnullvm target with llvm-mingw), and Node for the Tauri CLI (`npm ci` in shell/ once);
cargo, the linker and node must be on PATH.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL = os.path.join(ROOT, "shell")
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")
ENGINE_BUILD = os.path.join(BUILD, "engine", "PaperDaemon")     # a build step: dist/ holds only the app
APP = os.path.join(DIST, "app")
FASTDECOMP = os.path.join(ROOT, "paperdaemon", "pipeline", "decompose", "fastdecomp", "build.py")

STOCKFISH = {
    "version": "19",
    "url": "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/"
           "stockfish-windows-x86-64-universal.zip",
    "sha256": "3c8bf1f9ea66a09350a40df4f632288285ac206d99f33ab5842c408fc30b48a7",
    "exe": "stockfish/stockfish-windows-x86-64-universal.exe",
    "source": "https://github.com/official-stockfish/Stockfish/tree/sf_19",
}


def run(cmd, cwd, env=None):
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True, env=env, shell=(os.name == "nt" and cmd[0] in ("npx", "npm")))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stockfish_zip():
    """The Stockfish release zip in build/stockfish, downloaded once; refused unless its SHA-256 matches."""
    folder = os.path.join(BUILD, "stockfish")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, os.path.basename(STOCKFISH["url"]))
    if not os.path.isfile(path):
        print("downloading %s" % STOCKFISH["url"])
        with urllib.request.urlopen(STOCKFISH["url"]) as r, open(path + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(path + ".part", path)
    got = sha256(path)
    if got != STOCKFISH["sha256"]:
        os.remove(path)
        raise SystemExit("Stockfish's download does not match its SHA-256 (got %s); removed it" % got)
    return path


def add_stockfish(engine_dir):
    """Stockfish beside the engine, as engine/stockfish/stockfish.exe (paths.stockfish finds it there), with
    its GPL license, its authors and where its source is."""
    out = os.path.join(engine_dir, "stockfish")
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(stockfish_zip()) as z:
        for member, name in ((STOCKFISH["exe"], "stockfish.exe"), ("stockfish/Copying.txt", "Copying.txt"),
                             ("stockfish/AUTHORS", "AUTHORS")):
            with z.open(member) as src, open(os.path.join(out, name), "wb") as dst:
                shutil.copyfileobj(src, dst)
    with open(os.path.join(out, "SOURCE.txt"), "w", encoding="utf-8") as f:
        f.write("Stockfish %s, the official build for Windows x86-64, unchanged.\n"
                "License: GNU General Public License version 3 (Copying.txt).\n"
                "Source: %s\nDownload: %s\n" % (STOCKFISH["version"], STOCKFISH["source"], STOCKFISH["url"]))


def add_licenses(engine_dir):
    """Every installed Python package's license files into engine/licenses/<package>/ (the environment the
    engine was frozen from; a package without license files gets its metadata's license line)."""
    from importlib import metadata
    out = os.path.join(engine_dir, "licenses")
    os.makedirs(out, exist_ok=True)
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        folder = os.path.join(out, name)
        files = [f for f in (dist.files or []) if any(k in f.name.upper() for k in ("LICEN", "COPYING", "NOTICE"))]
        os.makedirs(folder, exist_ok=True)
        for f in files:
            src = dist.locate_file(f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(folder, os.path.basename(str(f))))
        if not files:
            with open(os.path.join(folder, "LICENSE.txt"), "w", encoding="utf-8") as fh:
                fh.write("%s %s: %s\n" % (name, dist.version, dist.metadata.get("License-Expression")
                                          or dist.metadata.get("License") or "see the package's metadata"))


def shell_config(repo, update_key):
    """The settings this build adds to shell/tauri.conf.json: the engine as a bundled resource, and for a
    release the update endpoint and public key -> the path of a JSON file for `tauri build --config`."""
    resources = {os.path.join(APP, "engine").replace("\\", "/") + "/": "engine/"}
    # a GNU-toolchain shell cannot link WebView2Loader.dll in, so the installer puts it beside PaperDaemon.exe
    loader = os.path.join(SHELL, "target", "release", "WebView2Loader.dll")
    host = subprocess.run(["rustc", "-vV"], capture_output=True, text=True).stdout
    if "windows-gnu" in host:
        resources[loader.replace("\\", "/")] = "WebView2Loader.dll"
    conf = {"bundle": {"resources": resources,
                       "createUpdaterArtifacts": bool(update_key)}}
    if update_key:
        conf["plugins"] = {"updater": {"pubkey": update_key.strip()}}
    if repo:
        conf.setdefault("plugins", {}).setdefault("updater", {})["endpoints"] = [
            "https://github.com/%s/releases/latest/download/latest.json" % repo]
    path = os.path.join(BUILD, "tauri.build.json")
    os.makedirs(BUILD, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    return path


def write_latest(bundle_dir, repo):
    """latest.json beside the signed installer: what Check for updates reads from the latest GitHub release."""
    import datetime
    with open(os.path.join(SHELL, "tauri.conf.json"), encoding="utf-8") as f:
        version = json.load(f)["version"]
    # THIS version's installer: the folder keeps earlier builds' installers too
    exe = "PaperDaemon_%s_x64-setup.exe" % version
    if not os.path.isfile(os.path.join(bundle_dir, exe + ".sig")):
        raise SystemExit("no signed %s in %s" % (exe, bundle_dir))
    with open(os.path.join(bundle_dir, exe + ".sig"), encoding="utf-8") as f:
        sig = f.read().strip()
    latest = {"version": version, "notes": "See the release notes on GitHub.",
              "pub_date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "platforms": {"windows-x86_64": {"signature": sig, "url": "https://github.com/%s/releases/download/v%s/%s"
                                                % (repo, version, exe)}}}
    with open(os.path.join(bundle_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest, f, indent=2)


def shell_output():
    """The release folder cargo wrote, whichever target it built for."""
    candidates = [os.path.join(SHELL, "target", "release")]
    target_dir = os.path.join(SHELL, "target")
    if os.path.isdir(target_dir):
        candidates += [os.path.join(target_dir, d, "release") for d in os.listdir(target_dir)]
    for folder in candidates:
        if os.path.isfile(os.path.join(folder, "PaperDaemon.exe")):
            return folder
    raise SystemExit("the shell's build output was not found under %s" % target_dir)


SIGNING = ("PaperDaemon release signing", "update key password")    # the credential store entry (never a file)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", help="OWNER/NAME of the GitHub repository updates come from (a release build)")
    ap.add_argument("--update-key", help="the public update key, or a path to the .pub file holding it")
    ap.add_argument("--native", action="store_true", help="build the C decomposer for this machine's CPU only")
    ap.add_argument("--skip-engine", action="store_true", help="reuse build/engine/PaperDaemon as it is")
    ap.add_argument("--skip-shell", action="store_true", help="stop before the shell and the installer")
    ap.add_argument("--stage", help="assemble the app in this folder instead of dist/app (dist/app may be running)")
    ap.add_argument("--signing-key", default=os.path.join(os.path.expanduser("~"), ".tauri", "paperdaemon.key"),
                    help="the private update key's file, used when TAURI_SIGNING_PRIVATE_KEY is not set")
    ap.add_argument("--save-signing-password", action="store_true",
                    help="ask for the private key's password once and keep it in the credential store, then stop")
    args = ap.parse_args()
    if args.save_signing_password:
        import getpass
        import keyring
        keyring.set_password(*SIGNING, getpass.getpass("Update key password (not shown): "))
        print("saved in the credential store as %r" % SIGNING[0])
        return
    if args.update_key and not os.environ.get("TAURI_SIGNING_PRIVATE_KEY") and os.path.isfile(args.signing_key):
        # a release built without typing anything: the key from its file, its password from the credential store
        import keyring
        with open(args.signing_key, encoding="utf-8") as f:
            os.environ["TAURI_SIGNING_PRIVATE_KEY"] = f.read().strip()
        if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY_PASSWORD"):
            pw = keyring.get_password(*SIGNING)
            if pw is None:
                raise SystemExit("no saved key password: run tools/build_app.py --save-signing-password once")
            os.environ["TAURI_SIGNING_PRIVATE_KEY_PASSWORD"] = pw
    global APP
    if args.stage:
        APP = os.path.abspath(args.stage)
    key = args.update_key
    if key and os.path.isfile(key):
        with open(key, encoding="utf-8") as f:
            key = f.read()
    if key and not args.repo:
        raise SystemExit("--update-key needs --repo: the update's address names the repository")
    if key and not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        raise SystemExit("--update-key needs the private key in TAURI_SIGNING_PRIVATE_KEY to sign the update")
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from build_exe import free_to_replace
    if not free_to_replace(APP):
        raise SystemExit("%s is in use (the app is running from it): quit it, then build again" % APP)
    py = sys.executable
    run([py, FASTDECOMP] + ([] if args.native else ["--generic"]), ROOT)
    run([py, os.path.join(ROOT, "tools", "make_icons.py")], ROOT)
    if not args.skip_engine:
        run([py, os.path.join(ROOT, "tools", "build_exe.py")], ROOT)
    if not os.path.isfile(os.path.join(ENGINE_BUILD, "PaperDaemon.exe")):
        raise SystemExit("no engine build at %s" % ENGINE_BUILD)
    if os.path.isdir(APP):
        shutil.rmtree(APP)
    shutil.copytree(ENGINE_BUILD, os.path.join(APP, "engine"))
    add_stockfish(os.path.join(APP, "engine"))
    add_licenses(os.path.join(APP, "engine"))
    if args.skip_shell:
        print("built %s (no shell)" % APP)
        return
    run(["npx", "tauri", "build", "--config", shell_config(args.repo, key)], SHELL)
    built = shell_output()
    shutil.copy2(os.path.join(built, "PaperDaemon.exe"), os.path.join(APP, "PaperDaemon.exe"))
    loader = os.path.join(built, "WebView2Loader.dll")
    if os.path.isfile(loader):
        shutil.copy2(loader, APP)
    if key:
        write_latest(os.path.join(built, "bundle", "nsis"), args.repo)
    print("built %s and the installer in %s" % (APP, os.path.join(built, "bundle", "nsis")))


if __name__ == "__main__":
    main()
