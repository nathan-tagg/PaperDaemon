"use strict";
/* First run: connect the reMarkable, fill the Mirror, choose the models, start. Every step can be opened from
   the rail at any time; its mark shows its own state (done, under way, not yet), whichever step is open. */
(() => {
  const { $, esc, line, mk } = PD;
  let R = null;
  const STEPS = [PD.t("su.connect"), PD.t("su.mirror"), PD.t("lineup.label"), PD.t("su.finish")];
  const S = { step: 1, auth: "", authErr: "", conn: "", connErr: "", pullErr: "", gen: 0, lineup: null, active: "",
              scripts: [], form: {}, test: { text: "", image: "", search: "" }, msg: "", run: "", tab: "text" };

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const alive = () => !!R && R.isConnected && !!$("#su-step", R);
  const st = () => PD.status || {};
  const tabletSet = () => !!(st().tablet && st().tablet.set);

  // ---- the state of each step, for the rail's marks: "on" done, "busy" under way, "off" not yet
  function stepState(n) {
    if (n === 1) return tabletSet() ? "on" : "off";
    if (n === 2) { const m = PD.mirrorState(st()); return m.building ? "busy" : st().mirror && st().mirror.complete ? "on" : "off"; }
    if (n === 3) return modelsReady() ? "on" : "off";
    return st().loop && st().loop.running ? "on" : "off";
  }

  function frame() {
    const m = PD.mirrorState(st());
    const items = STEPS.map((t, i) => {
      const n = i + 1;
      const meter = n === 2 && m.building ? '<span class="step-meter" title="' + esc(PD.t("su.building_pct", { pct: m.pct })) + '"><span class="bar" aria-hidden="true"><i style="width:' + m.pct + '%"></i></span><span class="pct">' + m.pct + "%</span></span>" : "";
      return '<li><button type="button" class="steplink" data-act="go" data-n="' + n + '"' + (n === S.step ? ' aria-current="step"' : "") + ">" +
        '<i class="mk ' + stepState(n) + '"></i>' + esc(t) + meter + "</button></li>";
    }).join("");
    PD.html($("#su-steps", R), items);
  }

  function go(n) {
    S.step = n; frame(); render(); window.scrollTo(0, 0);
    if (n === 2 && tabletSet() && !S.conn) checkAndPull();
    if (n >= 3 && !S.lineup) loadModels().then(() => { if (S.step === 4) paintRun(); });
  }

  function render() {
    const box = $("#su-step", R);
    box.innerHTML = [step1, step2, step3, step4][S.step - 1]();
    [paintAuth, paintPull, paintModels, paintRun][S.step - 1]();
  }

  // ---- 1: connect

  const step1 = () => '<section class="step"><h1 class="step-title">' + esc(PD.t("su.connect")) + "</h1>" +
    '<div id="su-auth" class="stack-s" style="margin-top: var(--s4)"></div>' +
    '<div class="actions next" id="su-next1"></div></section>';

  const connected = m => m ? PD.t("su.connected_how", { how: PD.t(m === "borrowed" ? "su.borrowed" : "su.stolen") }) : PD.t("settings.login.connected");

  function paintAuth() {
    let html;
    if (S.auth === "checking") html = line("busy", PD.t("su.taking"));
    else if (tabletSet()) {
      // the login's method, and the other one a click away
      const m = st().tablet.method, other = m === "borrowed" ? "steal" : "borrow";
      html = '<div class="login-state">' + "<span>" + esc(connected(m)) + "</span>" +
        '<button type="button" class="btn quiet small" data-act="' + other + '">' + esc(PD.t(other === "steal" ? "su.steal_instead" : "su.borrow_instead")) + "</button></div>" +
        (S.auth === "error" ? line("fail", esc(S.authErr), "err") : "");
    }
    else html = (S.auth === "error" ? line("fail", esc(S.authErr), "err") : "") + PD.loginButtons();
    PD.html($("#su-auth", R), html);
    PD.html($("#su-next1", R), tabletSet() ? '<button type="button" class="btn primary" data-act="go" data-n="2">' + esc(PD.t("su.continue")) + "</button>" : "");
  }

  async function signin(mode) {
    S.auth = "checking"; paintAuth();
    const [d, e] = await PD.safe(PD.takeLogin(mode));
    if (e) { S.auth = "error"; S.authErr = PD.errText(e); }
    else if (!d) S.auth = "";
    else { const r = PD.loginResult(d, mode); if (r.bad) { S.auth = "error"; S.authErr = r.text; } else { S.auth = ""; S.authMsg = r.text; } }
    await PD.refreshStatus();
    if (S.step === 1) paintAuth();
  }

  // ---- 2: the Mirror

  const step2 = () => '<section class="step"><h1 class="step-title">' + esc(PD.t("su.mirror")) + "</h1>" +
    '<p class="lead">' + esc(PD.t("su.mirror_lead")) + "</p>" +
    '<div class="pull" id="su-pull" aria-live="polite"></div><div class="actions next" id="su-next2"></div></section>';

  function paintPull() {
    const p = st().pull || {};
    let html;
    if (!tabletSet()) html = '<p class="sub">' + esc(PD.t("su.connect_first")) + "</p>";
    else if (S.conn === "testing") html = line("spin", PD.t("su.connecting"));
    else if (S.conn === "fail") html = line("fail", esc(S.connErr), "err") + '<p><button type="button" class="btn" data-act="retry">' + esc(PD.t("common.try_again")) + "</button></p>";
    else if (S.pullErr) html = line("fail", esc(S.pullErr), "err") + '<p><button type="button" class="btn" data-act="retry">' + esc(PD.t("common.try_again")) + "</button></p>";
    else if (p.running) html = PD.mirrorBar(p);
    else if (st().mirror && st().mirror.complete) html = line("on", PD.t("su.mirror_complete"));
    else html = "";
    PD.html($("#su-pull", R), html);
    PD.html($("#su-next2", R), tabletSet() ? '<button type="button" class="btn primary" data-act="go" data-n="3">' + esc(PD.t("su.continue")) + "</button>" : "");
  }

  async function checkAndPull() {
    const gen = ++S.gen;
    S.conn = "testing"; S.connErr = ""; S.pullErr = ""; if (S.step === 2) paintPull();
    const [d, e] = await PD.safe(PD.api("POST", "/tablet/check"));
    if (gen !== S.gen) return;
    if (e || !d || !d.ok) { S.conn = "fail"; S.connErr = e ? PD.errText(e) : (d && d.error) || PD.t("su.cloud_silent"); if (S.step === 2) paintPull(); return; }
    S.conn = "ok";
    const s0 = await PD.refreshStatus();
    if (!(s0 && s0.pull && s0.pull.running)) {
      const [, e2] = await PD.safe(PD.api("POST", "/tablet/pull"));
      if (e2) { S.pullErr = PD.errText(e2); if (S.step === 2) paintPull(); return; }
    }
    for (let i = 0; gen === S.gen && alive(); i++) {             // until the pull ends; one status a second
      const s = await PD.refreshStatus();
      const p = (s && s.pull) || {};
      if (S.step === 2) paintPull();
      if (!p.running && i > 0) { if (p.error) S.pullErr = p.error; if (S.step === 2) paintPull(); frame(); return; }
      await sleep(1000);
    }
  }

  // ---- 3: the lineup (the shared form in slots.js)

  const step3 = () => '<section class="step"><h1 class="step-title">' + esc(PD.t("lineup.label")) + "</h1>" +
    '<p class="lead">' + esc(PD.t("su.lineup_lead")) + "</p>" +
    '<div id="su-models"></div><p class="msg" id="su-msg" role="status"></p>' +
    '<div class="actions next"><button type="button" class="btn primary" data-act="save" id="su-save">' + esc(PD.t("su.continue")) + "</button></div></section>";

  async function loadModels() {
    const [d, e] = await PD.safe(PD.api("GET", "/lineups"));
    if (e || !d) { S.msg = e ? PD.errText(e) : PD.t("su.lineup_unreadable"); if (S.step === 3) paintModels(); return; }
    S.lineup = d.lineups.find(l => l.name === d.in_use) || d.lineups[0];
    await loadHarnesses();
    S.form = { text: PD.slots.formOf("text", S.lineup.text), image: PD.slots.formOf("image", S.lineup.image) };
    S.tags = PD.slots.tagsOf(S.lineup.tags);
    S.name = S.lineup.name;
    S.search = PD.slots.searchOf(S.lineup.search);
    if (S.step === 3) paintModels();
  }

  async function loadHarnesses() {
    const [h] = await PD.safe(PD.api("GET", "/harnesses"));
    S.harnesses = Array.isArray(h) ? h.filter(x => x.id && !x.error) : [];
    PD.slots.harnesses = S.harnesses;
  }

  function modelsReady() { return !!(S.lineup && S.lineup.text && S.lineup.text.location); }

  function readForm() {
    if (!S.form.text) return;
    const nm = $("#su-name", R); if (nm) S.name = nm.value.trim();
    if (S.tab === "search") PD.slots.readSearch(R, "su", S.search);
    else if (S.tab === "tags") PD.slots.readTags(R, "su", S.tags);
    else PD.slots.read(R, "su", S.tab, S.form[S.tab]);
  }

  function paintModels(focusGrip) {
    const box = $("#su-models", R); if (!box) return;
    if (!S.form.text) { box.innerHTML = S.msg ? line("fail", esc(S.msg), "err") : '<p class="sub">' + esc(PD.t("common.reading")) + "</p>"; return; }
    const tab = (id, label) => '<button type="button" class="ftab" role="tab" data-act="tab" data-tab="' + id + '" aria-selected="' + (S.tab === id) + '">' + label + "</button>";
    box.innerHTML = '<div class="grid2"><label>' + esc(PD.t("lineup.name")) + '<input class="field" id="su-name" value="' + esc(S.name || "") + '" autocomplete="off"></label><span></span></div>' +
      '<div class="ftabs" role="tablist">' + tab("text", esc(PD.t("tab.text"))) + tab("image", esc(PD.t("tab.image"))) + tab("search", esc(PD.t("tab.network"))) + tab("tags", esc(PD.t("tab.tags"))) + "</div>" +
      '<div class="fpanel" role="tabpanel">' + (S.tab === "search" ? PD.slots.searchHtml("su", S.search, PD.slots.testHtml(S.test.search))
        : S.tab === "tags" ? PD.slots.tagsHtml("su", S.tags)
        : PD.slots.html("su", S.tab, S.form[S.tab], S.harnesses, PD.slots.testHtml(S.test[S.tab]))) + "</div>";
    PD.wireCode(box); PD.wireTypeahead(box);
    if (focusGrip != null) PD.slots.focusGrip(box, focusGrip);
  }

  async function save() {
    const msg = $("#su-msg", R);
    readForm();
    const text = PD.slots.slotOf("text", S.form.text, S.lineup.text);
    if (!text.location) { msg.className = "msg err"; msg.textContent = PD.t("su.need_address"); return false; }
    const err = await PD.slots.saveKeys(Object.assign({}, S.form, { search: S.search }));
    if (err) { msg.className = "msg err"; msg.textContent = err; return false; }
    if (!S.name) { msg.className = "msg err"; msg.textContent = PD.t("su.need_name"); return false; }
    const v = { name: S.name, text, image: PD.slots.slotOf("image", S.form.image, S.lineup.image),
                search: PD.slots.searchOut(S.search), tags: PD.slots.tagsOut(S.tags) };
    const [d, e] = await PD.safe(PD.api("PUT", "/lineups/" + encodeURIComponent(S.lineup.name), v));
    if (e) { msg.className = "msg err"; msg.textContent = PD.errText(e); return false; }
    S.lineup = d.lineups.find(l => l.name === S.name) || S.lineup;
    msg.className = "msg"; msg.textContent = "";
    await PD.refreshStatus(); frame();
    return true;
  }

  async function test(role) {
    S.test[role] = "testing"; paintModels();
    if (!await save()) { S.test[role] = ""; paintModels(); return; }
    if (role === "search") {
      const [d, e] = await PD.safe(PD.api("POST", "/search/test?lineup=" + encodeURIComponent((S.lineup && S.lineup.name) || "")));
      S.test.search = e ? PD.errText(e) : d && d.ok ? "ok" : (d && d.error) || PD.t("common.no_answer");
      paintModels(); return;
    }
    for (let i = 0; i < 4; i++) {
      const [m] = await PD.safe(PD.api("GET", "/models?lineup=" + encodeURIComponent((S.lineup && S.lineup.name) || "")));
      if (m && m[role] && m[role].server && m[role].server.answering) { S.test[role] = "ok"; paintModels(); return; }
      await sleep(1500);
    }
    S.test[role] = PD.t("lineup.test_no_answer"); paintModels();
  }

  // ---- 4: finish: everything chosen so far, and one way on

  const step4 = () => '<section class="step"><h1 class="step-title">' + esc(PD.t("su.finish")) + "</h1>" +
    '<p class="lead">' + esc(PD.t("su.finish_lead")) + "</p>" +
    '<dl class="summary" id="su-summary"></dl><p class="msg" id="su-run" role="status"></p>' +
    '<div class="actions next"><button type="button" class="btn primary" data-act="proceed">' + esc(PD.t("su.proceed")) + "</button></div></section>";

  const none = () => '<span class="dim">' + esc(PD.t("slot.none")) + "</span>";

  function modelSummary(role) {
    const slot = (S.lineup && S.lineup[role]) || {}, f = PD.slots.formOf(role, slot);
    if (f.kind === "none") return none();
    const h = slot.harness && slot.harness !== "auto" ? ((S.harnesses || []).find(x => x.id === slot.harness) || {}).name || slot.harness : PD.t("su.automatic");
    const where = f.kind === "local" ? esc(PD.t(slot.script_text && slot.script_text.trim() ? "su.local_at_script" : "su.local_at", { address: f.at }))
      : esc(f.provider === "other" ? f.at : f.provider.charAt(0).toUpperCase() + f.provider.slice(1)) + (f.model ? " · " + esc(f.model) : "");
    return where + '<span class="meta">' + esc(PD.t("su.harness_is", { harness: h })) + "</span>";
  }

  function paintRun() {
    const box = $("#su-summary", R); if (!box) return;
    const t = st().tablet || {}, m = PD.mirrorState(st()), lu = S.lineup || {};
    const sr = lu.search || {}, tags = (lu.tags || []).filter(c => c.name);
    const search = sr.kind === "api" ? esc({ brave: "Brave Search", tavily: "Tavily", exa: "Exa", serper: "Serper" }[sr.provider] || sr.provider)
      : sr.kind === "local" ? esc(PD.t("su.local_at", { address: sr.url })) : none();
    const rows = [
      ["reMarkable", t.set ? esc(connected(t.method)) : '<span class="err">' + esc(PD.t("settings.login.none")) + "</span>"],
      [PD.t("su.mirror"), m.building ? esc(PD.t("su.building", { pct: m.pct })) : st().mirror && st().mirror.complete ? esc(PD.t("su.complete")) : '<span class="dim">' + esc(PD.t("su.not_built")) + "</span>"],
      [PD.t("lineup.label"), esc(lu.name || "")],
      [PD.t("tab.text"), modelSummary("text")],
      [PD.t("tab.image"), modelSummary("image")],
      [PD.t("net.search"), search],
      [PD.t("su.tags"), tags.length ? tags.map(c => '<span class="mono">' + esc(c.name) + "</span>").join(" ") : esc(PD.t("su.no_tags"))],
    ];
    box.innerHTML = rows.map(([k, v]) => "<dt>" + esc(k) + "</dt><dd>" + v + "</dd>").join("");
  }

  async function proceed(btn) {
    await PD.busy(btn, async () => {
      if (tabletSet() && (S.lineup && (S.lineup.tags || []).some(c => c.name))) await PD.safe(PD.api("POST", "/loop/start-when-ready"));
      PD.finishSetup("overview");
    });
  }

  // ---- entry

  PD.setup = {
    start(at) {
      R = $("#root");
      R.className = "firstrun";
      R.innerHTML =
        '<nav class="rail" aria-label="' + esc(PD.t("su.steps")) + '"><span class="wordmark">PaperDaemon</span><ol class="steplist" id="su-steps"></ol>' +
        '<div class="rail-foot"><button type="button" class="btn quiet small" data-act="later">' + esc(PD.t("su.later")) + "</button></div></nav>" +
        '<main class="page"><div id="su-step"></div></main>';
      Object.assign(S, { step: 1, auth: "", conn: "", pullErr: "", run: "", test: { text: "", image: "", search: "" }, msg: "" });
      document.title = PD.t("su.title");
      if (!R.__wired) {                       // #root outlives each setup; its listeners are added once
        R.__wired = true;
        PD.on(R, "click", "[data-act]", (e, el) => {
          if (!$("#su-step", R)) return;
          const a = el.dataset.act;
          if (a === "borrow" || a === "steal") signin(a);
          else if (a === "go") { if (S.step === 3) readForm(); go(Number(el.dataset.n)); }
          else if (a === "retry") checkAndPull();
          else if (a === "save") PD.busy(el, async () => { if (await save()) go(4); });
          else if (a === "test") test(el.dataset.role);
          else if (a === "addharness") { readForm(); PD.api("POST", "/harnesses/open", { kind: el.dataset.kind }); S.harnessesStale = true; }
          else if (a === "tab") { readForm(); S.tab = el.dataset.tab; paintModels(); }
          else if (a === "proceed") proceed(el);
          else if (a === "addtag") { readForm(); S.tags.push({ name: "", prompt: "" }); paintModels(); }
          else if (a === "deltag") { readForm(); S.tags.splice(Number(el.dataset.i), 1); paintModels(); }
          else if (a === "later") PD.finishSetup(undefined, "later");
        });
        PD.slots.wireTagSort(R, "su", () => (S.step === 3 && S.tab === "tags" ? S.tags : null), i => paintModels(i));
        R.addEventListener("change", e => {
          if (S.step !== 3 || !$("#su-step", R)) return;
          if (/^su-(text|image|search)-(kind|provider)$/.test(e.target.id)) { readForm(); S.test[S.tab] = ""; paintModels(); }
        });
        document.addEventListener("pd:status", () => { if (alive()) frame(); });
        // back from the harnesses folder: list what is there now
        window.addEventListener("focus", async () => {
          if (!S.harnessesStale || !alive() || S.step !== 3) return;
          S.harnessesStale = false; readForm(); await loadHarnesses(); paintModels();
        });
      }
      frame(); render();
      if (at) { loadModels(); go(at); return; }
      // open the first step that is not done
      PD.refreshStatus().then(async s => {
        if (!s || !alive() || S.step !== 1 || !tabletSet()) return;
        await loadModels();
        if (!(s.mirror && s.mirror.complete) || (s.pull && s.pull.running)) go(2);
        else go(modelsReady() ? 4 : 3);
      });
    },
  };
})();
