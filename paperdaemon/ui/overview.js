"use strict";
/* Overview: PaperDaemon's control panel. What needs you (issues), the daemon's and the host's own output, and the
   controls. The jobs have a screen of their own, and the location is in Settings. */
(() => {
  const { $, esc } = PD;
  let R = null;
  const S = { loop: null, starting: false, startError: "", errs: {}, term: "daemon" };


  // ---- issues: anything that needs the user, above everything else; the rail flashes while there are any

  PD.issues = (st, lp) => {
    st = st || PD.status || {}; lp = lp || st.loop || {};
    const out = [];
    if (st.first_run) out.push({ text: PD.t("issue.setup"), fix: '<button type="button" class="btn small" data-act="setup">' + esc(PD.t("issue.setup_go")) + "</button>" });
    const t = st.tablet || {}, pull = st.pull || {}, pullErr = String(pull.error || "");
    if (!t.set || t.error || pull.error_code === "unauthorized")
      out.push({ text: PD.t("issue.tablet"), fix: PD.loginButtons() });
    else if (pullErr) out.push({ text: PD.t("issue.mirror", { why: pullErr }), fix: "" });
    // the loop says what state it is in by a code; the usual states are no issue, every other one is, in its own words
    const code = lp.code || "not_started";
    // no_token is the "can't reach your reMarkable" issue above, said once
    if (!["running", "stopped", "not_started", "paused", "no_token"].includes(code))
      out.push({ text: PD.t("issue.loop_" + code, lp.args || {}), fix: "" });
    return out;
  };

  function renderIssues() {
    const list = PD.issues(PD.status, S.loop);
    if (S.startError) list.push({ text: PD.t("issue.not_started", { why: S.startError }), fix: "" });
    PD.html($("#ov-issues", R), list.length ? '<div class="issues" role="alert">' + list.map(i =>
      '<div class="issue"><span class="warn" aria-hidden="true">' + PD.WARN + '</span><span class="issue-text">' + esc(i.text) + "</span>" +
      (i.fix ? '<span class="issue-fix">' + i.fix + "</span>" : "") + "</div>").join("") + "</div>" : "");
  }

  // ---- the daemon and the host, as they write

  const TERMS = {
    daemon: [PD.t("term.daemon"), PD.t("term.daemon_about")],
    host: [PD.t("term.host"), PD.t("term.host_about")],
  };

  function renderTerms() {
    const h = (S.loop && S.loop.halves) || {};
    const tab = w => '<button type="button" class="ftab" role="tab" data-term="' + w + '" aria-selected="' + (S.term === w) + '">' + TERMS[w][0] + "</button>";
    const x = h[S.term], lines = x && Array.isArray(x.tail) ? x.tail : (x && typeof x.tail === "string" && x.tail ? x.tail.split("\n") : []);
    const old = $("#ov-term-out", R), stick = !old || old.scrollTop + old.clientHeight >= old.scrollHeight - 8;
    PD.html($("#ov-terms", R), '<div class="ftabs" role="tablist">' + tab("daemon") + tab("host") + "</div>" +
      '<div class="fpanel term-panel"><p class="term-about">' + esc(TERMS[S.term][1]) + "</p>" +
      '<pre class="terminal" id="ov-term-out">' + (lines.length ? esc(lines.join("\n")) : ('<span class="dim">' + esc(PD.t("term.empty")) + "</span>")) + "</pre></div>");
    const out = $("#ov-term-out", R);
    if (out && stick) out.scrollTop = out.scrollHeight;
  }

  // ---- controls

  function renderControls() {
    const on = !!(S.loop && S.loop.running);
    let html;
    if (S.starting) html = '<button type="button" class="btn" disabled aria-busy="true">' + esc(PD.t(on ? "loop.pausing" : "loop.starting")) + "</button>";
    else if (on) html = '<button type="button" class="btn" data-act="stop">' + esc(PD.t("loop.pause")) + "</button>";
    else html = '<button type="button" class="btn primary" data-act="start">' + esc(PD.t("loop.start")) + "</button>";
    PD.html($("#ov-controls", R), '<div class="actions">' + html + "</div>");
  }

  async function load() {
    const [lp, e1] = await PD.safe(PD.api("GET", "/loop"));
    if (lp) { S.loop = lp; if (PD.status) { PD.status = Object.assign({}, PD.status, { loop: lp }); PD.paintRail(); } }
    S.errs.loop = e1 ? PD.errText(e1) : "";
    render();
  }

  function render() {
    if (!R) return;
    renderIssues(); renderTerms(); renderControls();
  }

  async function act(name) {
    if (name === "setup") { PD.reopenSetup(); return; }
    if (name === "borrow" || name === "steal") {
      const [d, e] = await PD.safe(PD.takeLogin(name));
      if (e) S.startError = PD.errText(e);
      else if (d) { const r = PD.loginResult(d, name); if (r.bad) S.startError = r.text; }
      await PD.refreshStatus(); render(); return;
    }
    S.startError = ""; S.starting = true; renderControls();
    const p = PD.api("POST", name === "start" ? "/loop/start" : "/loop/stop");
    p.finally(() => { S.starting = false; });
    const [, err] = await PD.safe(p);
    if (err) S.startError = PD.errText(err);
    await load();
  }

  PD.screen("overview", {
    label: PD.t("overview.label"), group: 0,
    rail(st) {
      if (PD.issues(st).length) return '<span class="warn flash" title="' + esc(PD.t("overview.needs_you")) + '">' + PD.WARN + "</span>";
      const l = st.loop;
      if (l == null) return "";
      return esc(PD.t((typeof l === "object" ? !!l.running : !!l) ? "loop.running" : "loop.paused"));     // the word, no dot
    },
    mount(root) {
      R = root;
      S.loop = null;
      R.innerHTML = '<header class="page-head"><h1>' + esc(PD.t("overview.label")) + "</h1></header>" +
        '<div id="ov-issues"></div><div id="ov-terms"></div><div id="ov-controls" class="controls"></div>';
      PD.on(R, "click", "[data-act]", (e, el) => act(el.dataset.act));
      PD.on(R, "click", "[data-term]", (e, el) => { S.term = el.dataset.term; renderTerms(); });
    },
    async show() { render(); load(); },
    async poll() { await load(); },
  });
})();
