"use strict";
/* The PaperDaemon window: pairing, the rail, the router and the polling. The screens are in their own
   files (overview.js, notepads.js, ...); each registers itself with PD.screen(). */
(() => {
  const { $, $$, esc } = PD;
  const root = document.getElementById("root");
  let current = null;
  let tick = 0;

  // ---- the setup flag: the engine says whether this is a first run; leaving setup early is kept for this session

  let leftSetup = "";
  const flag = () => { try { return sessionStorage.getItem("setup-left") || leftSetup; } catch (e) { return leftSetup; } };
  const skipped = () => !!flag();
  PD.finishSetup = (go, how) => {
    leftSetup = how || "done";
    try { sessionStorage.setItem("setup-left", leftSetup); } catch (e) { /* kept for this page only */ }
    startApp(go);
  };
  PD.reopenSetup = () => { leftSetup = ""; try { sessionStorage.removeItem("setup-left"); } catch (e) { /* none */ } PD.setup.start(); };

  // ---- pages that are not a screen: pairing, and an engine that did not answer

  function plainPage(html) {
    root.className = "";
    root.innerHTML = '<main class="page pair">' + html + "</main>";
  }

  function showPairing(note) {
    document.title = PD.t("pair.title") + " · PaperDaemon";
    plainPage("<h1>" + esc(PD.t("pair.title")) + "</h1>" +
      "<p>" + esc(PD.t("pair.intro")) + "</p>" +
      '<form class="actions" id="pair-form" novalidate><input class="field mono w-l" type="password" id="pair-token" aria-label="' + esc(PD.t("pair.token")) + '" autocomplete="off" spellcheck="false">' +
      '<button class="btn primary" type="submit">' + esc(PD.t("pair.go")) + "</button></form>" +
      '<p class="msg err" id="pair-msg" role="alert">' + esc(note || "") + "</p>");
    $("#pair-token").focus();
    $("#pair-form").addEventListener("submit", async e => {
      e.preventDefault();
      const v = $("#pair-token").value.trim();
      if (!v) { $("#pair-msg").textContent = PD.t("pair.empty"); return; }
      PD.pairing.set(v);
      const [, err] = await PD.safe(PD.api("GET", "/status"));
      if (err && err.status === 401) { $("#pair-msg").textContent = PD.t("pair.refused"); return; }
      location.reload();
    });
  }

  function showFatal(err) {
    document.title = "PaperDaemon";
    plainPage("<h1>" + esc(PD.t("fatal.title")) + "</h1><p>" + esc(PD.errText(err)) + "</p>" +
      '<p class="actions"><button class="btn primary" id="retry">' + esc(PD.t("common.try_again")) + "</button></p>");
    $("#retry").addEventListener("click", boot);
  }

  document.addEventListener("pd:unpaired", () => { if (!$("#pair-form")) showPairing(PD.t("pair.window_refused")); });

  // ---- the rail and the router

  // THE RAIL, in this order and one list (no dividing line): Daemon, Mirror, False Mirror (once there is one),
  // Decompose, Lineup, Settings
  const RAIL = ["overview", "tablet", "fmirror", "decompose", "models", "settings"];

  function railHtml() {
    const items = RAIL.filter(id => PD.screens[id]).map(id => {
      const s = PD.screens[id];
      return '<li><a href="#' + id + '" data-screen="' + id + '">' + esc(s.label) + ' <span class="state"></span></a></li>';
    }).join("");
    return '<nav class="rail" aria-label="PaperDaemon"><a class="wordmark" href="#overview">PaperDaemon</a>' +
      '<ul class="nav">' + items + "</ul>" +
      '<div class="rail-foot"><p class="meta">' + (SHOW_ENGINE_ADDRESS ? esc(PD.t("rail.engine_on")) + ' <code id="rail-engine"></code><br>' : "") +
      '<span id="rail-version"></span></p></div></nav>' +
      '<main class="page" id="main" tabindex="-1"></main>';
  }

  // the engine's own address, shown again when reaching PaperDaemon from other devices is worked on (off for now)
  const SHOW_ENGINE_ADDRESS = false;

  PD.paintRail = () => {
    const st = PD.status || {};
    $$(".nav a[data-screen]").forEach(a => {
      const s = PD.screens[a.dataset.screen];
      // a screen that is not there yet (the False Mirror before it is made) has no place in the rail; one that goes
      // while it is open leaves the window on Settings, where it went
      const gone = !!(s.hidden && s.hidden(st));
      a.parentElement.hidden = gone;
      if (gone && current === s) PD.go("settings");
      const html = (s.rail && s.rail(st)) || "";
      const el = $(".state", a);
      el.className = "state" + (s.railNum ? " num" : "");
      PD.html(el, html);
    });
    const eng = $("#rail-engine"); if (eng) eng.textContent = location.host;
    const ver = $("#rail-version"); if (ver) ver.textContent = st.version ? PD.t("rail.version", { version: st.version }) : "";
  };

  PD.refreshStatus = async () => {
    const [st] = await PD.safe(PD.api("GET", "/status"));
    if (st) { PD.status = st; PD.paintRail(); document.dispatchEvent(new CustomEvent("pd:status", { detail: st })); }
    return st;
  };

  function show(id) {
    const def = PD.screens[id] || PD.screens.overview;
    id = def.id;
    if (current && current !== def && current.hide) current.hide();
    const main = $("#main");
    $$(".screen", main).forEach(el => { el.hidden = el.dataset.screen !== id; });
    let el = $('.screen[data-screen="' + id + '"]', main);
    if (!el) {
      el = document.createElement("div");
      el.className = "screen"; el.dataset.screen = id;
      main.append(el);
      def.root = el;
      def.mount(el);
    }
    el.hidden = false;
    current = def;
    $$(".nav a[data-screen]").forEach(a => {
      if (a.dataset.screen === id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.title = def.label + " · PaperDaemon";
    if (def.show) def.show();
    return el;
  }

  function route(focus) {
    const h = location.hash, id = (h.match(/pane=([a-z-]+)/) || h.match(/^#\/?([a-z-]+)$/) || [])[1] || "overview";
    const el = show(PD.screens[id] ? id : "overview");
    if (focus) { const h = $("h1", el); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); } }
    window.scrollTo(0, 0);
  }

  let polling = false;
  async function poll() {
    tick++;
    PD.refreshStatus();
    if (polling || !current || !current.poll || document.hidden) return;     // a slow answer is never overlapped
    polling = true;
    try { await current.poll(tick); } catch (e) { /* the screen shows its own errors */ }
    finally { polling = false; }
  }

  function startApp(go) {
    root.className = "app";
    root.innerHTML = railHtml();
    PD.paintRail();
    if (go) location.hash = go;
    else if (!location.hash.replace(/^#\/?/, "") && PD.firstPane) location.hash = PD.firstPane;
    route(false);
    window.removeEventListener("hashchange", onHash);
    window.addEventListener("hashchange", onHash);
    if (!PD.timer) {
      PD.timer = setInterval(poll, 3000);
      document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
    }
    PD.safe(PD.loadSettings()).then(PD.paintRail);
    PD.prefetch.forEach(f => f());
  }
  const onHash = () => route(true);

  async function boot() {
    if (!PD.pairing.token) return showPairing();
    const [st, err] = await PD.safe(PD.api("GET", "/status"));
    if (err) { if (err.status === 401) return showPairing(); return showFatal(err); }
    PD.status = st;
    const at = ((PD.firstPane || "").match(/^setup([1-4])$/) || [])[1];       // a link straight to a setup step
    if (at) return PD.setup.start(Number(at));
    if (st.first_run && !skipped()) return PD.setup.start();
    startApp();
  }
  PD.boot = boot;

  boot();
})();
