"use strict";
/* Daemon: PaperDaemon's control panel. What needs you (issues), the controls, and three tabs: the Queue (the jobs
   waiting, next first, reordered by dragging), Notes (each notebook's memory of its jobs, notepads.js) and the
   Terminal (the daemon's and the host's own output). */
(() => {
  const { $, esc } = PD;
  let R = null;
  const S = { loop: null, startError: "", errs: {}, term: "daemon", tab: "queue", queue: null, qErr: "" };
  const X = '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6"/></svg>';
  const GRIP = '<svg viewBox="0 0 12 12" aria-hidden="true"><g fill="currentColor">' +
    [2, 6, 10].map(y => [2, 6, 10].map(x => '<circle cx="' + x + '" cy="' + y + '" r="1.2"/>').join("")).join("") + "</g></svg>";


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
    const why = S.startError || PD.loopError;
    if (why) list.push({ text: PD.t("issue.not_started", { why }), fix: "" });
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
    if (S.tab !== "terminal") return;
    const h = (S.loop && S.loop.halves) || {};
    const which = w => '<button type="button" data-term="' + w + '" aria-pressed="' + (S.term === w) + '">' + esc(TERMS[w][0]) + "</button>";
    const x = h[S.term], lines = x && Array.isArray(x.tail) ? x.tail : (x && typeof x.tail === "string" && x.tail ? x.tail.split("\n") : []);
    const old = $("#ov-term-out", R), stick = !old || old.scrollTop + old.clientHeight >= old.scrollHeight - 8;
    PD.html($("#ov-terms", R), '<div class="seg small" role="group" aria-label="' + esc(PD.t("ov.tab.terminal")) + '">' + which("daemon") + which("host") + "</div>" +
      '<p class="term-about">' + esc(TERMS[S.term][1]) + "</p>" +
      '<pre class="terminal" id="ov-term-out">' + (lines.length ? esc(lines.join("\n")) : ('<span class="dim">' + esc(PD.t("term.empty")) + "</span>")) + "</pre>");
    const out = $("#ov-term-out", R);
    if (out && stick) out.scrollTop = out.scrollHeight;
  }

  // (Start and Pause are the rail's, left of the version: app.js paintLoop)

  // ---- the queue: next first; the job being worked is grayed out and stays where it is

  function renderQueue() {
    if (S.tab !== "queue") return;
    const box = $("#ov-queue", R); if (!box) return;
    if (S.qErr) { PD.html(box, '<p class="msg err">' + esc(S.qErr) + "</p>"); return; }
    if (!S.queue) { PD.html(box, '<p class="sub">' + esc(PD.t("common.reading")) + "</p>"); return; }
    if (!S.queue.length) { PD.html(box, '<p class="tab-note">' + esc(PD.t("q.empty")) + "</p>"); return; }
    PD.html(box, '<p class="tab-note">' + esc(PD.t("q.intro")) + '</p><ol class="queue">' + S.queue.map((j, i) => {
      const busy = j.status === "working", name = j.notebook + (j.page ? " · " + PD.t("job.page", { n: j.page }) : "");
      // a row: the handle (on the job being worked too, which cannot move), the notebook and page, the tags that sent
      // it, and the cross at the right
      return '<li class="qrow' + (busy ? " busy" : "") + '" data-i="' + i + '">' +
        '<button type="button" class="grip"' + (busy ? " disabled" : ' draggable="true"') + ' data-i="' + i + '" aria-label="' + esc(PD.t("q.move", { name })) +
          '" title="' + esc(PD.t("q.drag")) + '">' + GRIP + "</button>" +
        '<span class="qname"><strong>' + esc(j.notebook) + "</strong>" + (j.page ? '<span class="meta">' + esc(PD.t("job.page", { n: j.page })) + "</span>" : "") + "</span>" +
        '<span class="qtags">' + (j.tags || []).map(t => '<span class="chip">' + esc(t) + "</span>").join("") + "</span>" +
        // ONE CONTROL for every job: a waiting one leaves the queue; the one being worked is stopped at once and
        // thrown away
        '<button type="button" class="icon-btn qdrop" data-drop="' + esc(j.key) + '" aria-label="' + esc(PD.t(busy ? "q.abandon" : "q.remove", { name })) +
        '" title="' + esc(PD.t(busy ? "q.abandon" : "q.remove", { name })) + '">' + X + "</button></li>";
    }).join("") + "</ol>");
  }

  // BOTH MIRRORS' JOBS, the Mirror's first, then the False Mirror's (marked), each run one at a time across both. A job
  // moves only among its own mirror's, and its controls go to its own mirror's engine.
  const qbase = j => (j && j.fm ? "/fm" : "");
  const mine = (list, fm) => (list || []).map(j => Object.assign(j, { fm }));
  function setPart(fm, list) {
    S.queue = (S.queue || []).filter(j => !!j.fm !== fm).concat(mine(list, fm));
    S.queue.sort((a, b) => (a.fm ? 1 : 0) - (b.fm ? 1 : 0));
  }
  async function loadQueue() {
    const [q, e] = await PD.safe(PD.api("GET", "/queue"));
    const fm = ((PD.status || {}).false_mirror || {}).exists;
    const [f] = fm ? await PD.safe(PD.api("GET", "/fm/queue")) : [[]];
    if (e) S.qErr = PD.errText(e); else { S.qErr = ""; S.queue = mine(Array.isArray(q) ? q : [], false).concat(mine(Array.isArray(f) ? f : [], true)); }
    renderQueue();
  }

  /** A waiting job moved from place a to place b (the job being worked never moves). */
  async function moveJob(a, b) {
    const q = S.queue || [];
    if (a === b || a < 0 || b < 0 || a >= q.length || b >= q.length || q[a].status === "working" || q[b].status === "working") return;
    if (!!q[a].fm !== !!q[b].fm) return;                  // a job stays among its own mirror's
    const fm = !!q[a].fm, rows = q.slice();
    rows.splice(b, 0, rows.splice(a, 1)[0]);
    S.queue = rows;
    renderQueue();
    const g = $('.queue .grip[data-i="' + b + '"]', R); if (g) g.focus();
    const keys = rows.filter(j => !!j.fm === fm && j.status !== "working").map(j => j.key);
    const [d, e] = await PD.safe(PD.api("POST", (fm ? "/fm" : "") + "/queue/order", { keys }));
    if (e) S.qErr = PD.errText(e); else if (Array.isArray(d)) setPart(fm, d);
    renderQueue();
  }

  /** A job taken out of the queue: a waiting one is settled until its page changes; the one being worked is stopped
      at once and thrown away, what it had written put back. */
  async function dropJob(key) {
    const job = (S.queue || []).find(j => j.key === key) || {}, busy = job.status === "working";
    S.queue = (S.queue || []).filter(j => j.key !== key);
    renderQueue();
    const [d, e] = await PD.safe(PD.api("POST", qbase(job) + (busy ? "/queue/abandon" : "/queue/drop"), { key }));
    if (e) S.qErr = PD.errText(e); else if (Array.isArray(d)) setPart(!!job.fm, d);
    renderQueue();
  }

  function wireQueue(box) {
    PD.on(box, "click", "[data-drop]", (e, el) => dropJob(el.dataset.drop));
    let from = null;
    box.addEventListener("dragstart", e => {
      const g = e.target.closest && e.target.closest(".grip"); if (!g) return;
      from = Number(g.dataset.i);
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", String(from)); } catch (x) { /* some hosts refuse it */ }
      const row = g.closest(".qrow"); if (row) { row.classList.add("dragging"); e.dataTransfer.setDragImage(row, 16, 16); }
    });
    box.addEventListener("dragover", e => {
      if (from === null) return;
      const row = e.target.closest && e.target.closest(".qrow:not(.busy)"); if (!row) return;
      e.preventDefault();
      box.querySelectorAll(".qrow.over").forEach(x => x !== row && x.classList.remove("over"));
      row.classList.add("over");
    });
    box.addEventListener("drop", e => {
      if (from === null) return;
      const row = e.target.closest && e.target.closest(".qrow:not(.busy)"); if (!row) return;
      e.preventDefault();
      const a = from; from = null;
      moveJob(a, Number(row.dataset.i));
    });
    box.addEventListener("dragend", () => {
      from = null;
      box.querySelectorAll(".qrow.dragging, .qrow.over").forEach(x => x.classList.remove("dragging", "over"));
    });
    box.addEventListener("keydown", e => {
      const g = e.target.closest && e.target.closest(".grip"); if (!g) return;
      const i = Number(g.dataset.i);
      if (e.key === "ArrowUp") { e.preventDefault(); moveJob(i, i - 1); }
      else if (e.key === "ArrowDown") { e.preventDefault(); moveJob(i, i + 1); }
    });
  }

  // ---- the tabs

  function renderTabs() {
    const tab = w => '<button type="button" class="ftab" role="tab" data-tab="' + w + '" aria-selected="' + (S.tab === w) + '">' + esc(PD.t({ queue: "ov.tab.queue", notes: "np.label", terminal: "ov.tab.terminal" }[w])) + "</button>";
    PD.html($("#ov-tabs", R), tab("queue") + tab("notes") + tab("terminal"));
    $("#ov-queue", R).hidden = S.tab !== "queue";
    $("#ov-notes", R).hidden = S.tab !== "notes";
    $("#ov-terms", R).hidden = S.tab !== "terminal";
  }

  function pick(tab) {
    S.tab = tab;
    renderTabs();
    if (tab === "queue") { renderQueue(); loadQueue(); }
    else if (tab === "notes") PD.notes.show();
    else renderTerms();
  }

  async function load() {
    const [lp, e1] = await PD.safe(PD.api("GET", "/loop"));
    if (lp) { S.loop = lp; if (PD.status) { PD.status = Object.assign({}, PD.status, { loop: lp }); PD.paintRail(); } }
    S.errs.loop = e1 ? PD.errText(e1) : "";
    render();
  }

  function render() {
    if (!R) return;
    renderIssues(); renderTabs(); renderQueue(); renderTerms();
  }

  async function act(name) {
    if (!["setup", "borrow", "steal"].includes(name)) return;      // a panel's own buttons are not these
    if (name === "setup") { PD.reopenSetup(); return; }
    if (name === "borrow" || name === "steal") {
      const [d, e] = await PD.safe(PD.takeLogin(name));
      if (e) S.startError = PD.errText(e);
      else if (d) { const r = PD.loginResult(d, name); if (r.bad) S.startError = r.text; }
      await PD.refreshStatus(); render(); return;
    }
  }
  document.addEventListener("pd:loop", () => { if (R) load(); });     // started or paused from the rail

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
        '<div id="ov-issues"></div>' +
        '<div class="ftabs" role="tablist" id="ov-tabs"></div><div class="fpanel">' +
        '<div id="ov-queue"></div><div id="ov-notes" hidden></div><div id="ov-terms" hidden></div></div>';
      PD.notes.mount($("#ov-notes", R));
      wireQueue($("#ov-queue", R));
      PD.on(R, "click", "[data-act]", (e, el) => act(el.dataset.act));
      PD.on(R, "click", "[data-term]", (e, el) => { S.term = el.dataset.term; renderTerms(); });
      PD.on(R, "click", "[data-tab]", (e, el) => pick(el.dataset.tab));
    },
    async show() { render(); load(); pick(S.tab); },
    async poll() {
      await load();
      if (S.tab === "queue") await loadQueue();
      else if (S.tab === "notes") await PD.notes.poll();
    },
  });
})();
