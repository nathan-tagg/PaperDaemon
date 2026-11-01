// The README's pictures of PaperDaemon's screens that need a press or a key: headless Microsoft Edge driven over its
// debugging port (tools/readme_shots.py starts the engine and calls this), at twice the screen's pixels.
//
//   node tools/readme_editor.mjs PORT TOKEN OUTDIR EDITOR_DOC
//
// PAPERDAEMON_SHOT_ADAPTER (a card's LUID, "high,low") picks the graphics card the editor draws on.
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [PORT, TOKEN, OUT, DOC] = process.argv.slice(2);
const EDGE = ["C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
              "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"].find(existsSync);
const DEBUG = 9300 + Math.floor(Math.random() * 400);
const profile = mkdtempSync(join(tmpdir(), "pd-readme-edge-"));
const flags = process.env.PAPERDAEMON_SHOT_ADAPTER ? ["--use-adapter-luid=" + process.env.PAPERDAEMON_SHOT_ADAPTER] : [];
const edge = spawn(EDGE, ["--headless=new", "--no-first-run", "--hide-scrollbars", "--user-data-dir=" + profile,
  "--remote-debugging-port=" + DEBUG, "--window-size=1280,860", ...flags, "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
// the profile removed once Edge has gone (its processes hold the folder for a moment after it is told to stop)
const done = code => {
  const clean = () => { try { rmSync(profile, { recursive: true, force: true, maxRetries: 50, retryDelay: 100 }); } catch (e) {} process.exit(code); };
  edge.once("exit", () => setTimeout(clean, 500));
  setTimeout(clean, 8000).unref();
  try { edge.kill(); } catch (e) { clean(); }
};
setTimeout(() => { console.error("the screens did not finish in time"); done(3); }, 240000).unref();

let ws;
for (let i = 0; i < 100 && !ws; i++) {
  try { const t = await (await fetch(`http://127.0.0.1:${DEBUG}/json/list`)).json(); const p = t.find(x => x.type === "page"); if (p) ws = new WebSocket(p.webSocketDebuggerUrl); } catch (e) { await sleep(200); }
}
await new Promise(r => ws.addEventListener("open", r));
let id = 0;
const wait = new Map();
ws.addEventListener("message", m => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d); wait.delete(d.id); } });
const call = (method, params = {}) => new Promise(r => { const n = ++id; wait.set(n, r); ws.send(JSON.stringify({ id: n, method, params })); });
const ev = async expr => (await call("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
const until = async (expr, ms = 30000) => { for (let t = 0; t < ms; t += 100) { if (await ev(expr)) return true; await sleep(100); } return false; };
const key = async (k, code, vk, mods = 0) => {
  await call("Input.dispatchKeyEvent", { type: "rawKeyDown", key: k, code, windowsVirtualKeyCode: vk, modifiers: mods });
  await call("Input.dispatchKeyEvent", { type: "keyUp", key: k, code, windowsVirtualKeyCode: vk, modifiers: mods });
};
const shot = async name => {
  const s = await call("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(s.result.data, "base64"));
  console.log(join(OUT, name));
};
await call("Page.enable"); await call("Runtime.enable");
await call("Emulation.setDeviceMetricsOverride", { width: 1280, height: 860, deviceScaleFactor: 2, mobile: false });
const go = async pane => {
  await call("Page.navigate", { url: "about:blank" }); await sleep(200);
  await call("Page.navigate", { url: `http://127.0.0.1:${PORT}/#pair=${TOKEN}&pane=${pane}` });
};

// THE PAGE EDITOR: the painting's page open, every stroke of it selected, its make-up beside the selection
await go("tablet&open=" + DOC);
const frame = `document.querySelector("dialog[open] iframe.page-editor")`;
if (!await until(`(() => { const f = ${frame}; const d = f && f.contentDocument; return !!(d && d.getElementById("loading") && d.getElementById("loading").hidden && f.contentWindow.editorPage); })()`, 60000)) { console.error("the editor did not open"); done(2); }
await sleep(1500);
await ev(`${frame}.focus()`);
await key("a", "KeyA", 65, 2);
await until(`!!document.querySelector("dialog[open] > .sel-makeup.on")`, 10000);
await sleep(900);
await shot("editor.png");

// THE PEN'S MENU: the pen chosen, then pressed again
const tool = t => `document.querySelector('dialog[open] .ed-tools [data-tool="${t}"]')`;
await key("Escape", "Escape", 27);
await sleep(400);
for (let i = 0; i < 2; i++) { await ev(`${tool("a")} && ${tool("a")}.click()`); await sleep(500); }
await until(`(() => { const p = ${frame}.contentDocument.getElementById("pop"); return !!(p && !p.hidden); })()`, 5000);
await sleep(500);
await shot("editor-pens.png");
await key("Escape", "Escape", 27);
await sleep(400);

// DECOMPOSE: the paintings kept there, their previews and what they came to
await go("decompose");
await until(`!!document.querySelector("img[data-preview]") && [...document.querySelectorAll("img[data-preview]")].every(i => i.complete && i.naturalWidth)`, 30000);
await sleep(800);
await shot("decompose-screen.png");

// THE DAEMON: its Notes, the first notebook's open
await go("overview");
await until(`!!document.querySelector('[data-tab="notes"]')`, 15000);
await ev(`document.querySelector('[data-tab="notes"]').click()`);
await until(`!!document.querySelector("#ov-notes button[data-doc]")`, 15000);
await ev(`document.querySelector("#ov-notes button[data-doc]").click()`);
await sleep(1500);
await shot("daemon.png");

// THE LINEUP: its text, image and network tabs, each with its start script
await go("models");
await sleep(2500);
await shot("lineup.png");
for (const [tab, name] of [["image", "lineup-image.png"], ["search", "lineup-network.png"]]) {
  await ev(`document.querySelector('[data-act="tab"][data-tab="${tab}"]').click()`);
  await sleep(1500);
  await shot(name);
}

// THE LIBRARY and SETTINGS (Edit the Mirror as it ships, off)
await go("tablet");
await until(`document.querySelectorAll(".doc-card .cover img").length > 0 && [...document.querySelectorAll(".doc-card .cover img")].every(i => i.complete && i.naturalWidth)`, 30000);
await sleep(600);
await shot("library.png");
await ev(`PD.saveSettings(st => { PD.setK(st, "mirror.edit", false); }).then(() => true)`);
await go("settings");
await until(`!!document.querySelector("#st-gpu") && !!document.querySelector("#st-loc").value`, 15000);
await sleep(1500);
await shot("settings.png");
done(0);
