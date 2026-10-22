"use strict";
/* Models: the lineups, every one of them live: a page's tag picks the lineup that works it. Pick one in the dropdown,
   edit its text model, image model, network and tags in their tabs; every change is saved as it is made (no Save
   button). Its Memories tab holds what its model
   has learned about working for the user, its Jobs tab the pages it has worked, and its Test tab what the lineup can do, tested. */
(() => {
  const { $, esc } = PD;
  const P = "md";
  let R = null;
  const S = { data: null, show: "", tab: "text", forms: {}, search: {}, tags: [], harnesses: [], test: { text: "", image: "", search: "" }, msg: "", bad: false, stale: false,
              mem: null, memMax: 30, memErr: "" };

  const lineup = () => (S.data ? S.data.lineups.find(l => l.name === S.show) : null);

  async function load(keepShow) {
    const [d, e] = await PD.safe(PD.api("GET", "/lineups"));
    const [h] = await PD.safe(PD.api("GET", "/harnesses"));
    if (e || !d) { S.msg = e ? PD.errText(e) : PD.t("lineup.unreadable"); S.bad = true; paint(); return; }
    S.data = d;
    S.harnesses = Array.isArray(h) ? h.filter(x => x.id && !x.error) : [];
    PD.slots.harnesses = S.harnesses;
    if (!keepShow || !d.lineups.some(l => l.name === S.show)) S.show = d.in_use || (d.lineups[0] && d.lineups[0].name) || "";
    fill();
    paint();
  }

  function fill() {
    const l = lineup(); if (!l) return;
    S.forms = { text: PD.slots.formOf("text", l.text), image: PD.slots.formOf("image", l.image) };
    S.search = PD.slots.searchOf(l.search);
    S.tags = PD.slots.tagsOf(l.tags);
    S.test = { text: "", image: "", search: "" };
    S.mem = null; S.memErr = "";
  }

  function readAll() {
    if (S.tab === "search") PD.slots.readSearch(R, P, S.search);
    else if (S.tab === "tags") PD.slots.readTags(R, P, S.tags);
    else if (S.forms[S.tab]) PD.slots.read(R, P, S.tab, S.forms[S.tab]);
  }

  // ---- the Memories tab: what the lineup's model has learned about working for the user. The model adds them;
  // the user reads, edits and deletes them.

  async function loadMemories() {
    const want = S.show;
    const [d, e] = await PD.safe(PD.api("GET", "/lineups/" + encodeURIComponent(want) + "/memories"));
    if (want !== S.show) return;
    if (d) { S.mem = d.memories || []; S.memMax = d.max || 30; S.memErr = ""; } else S.memErr = PD.errText(e);
    if (S.tab === "memories") paint();
  }

  function memoriesHtml() {
    const note = '<p class="tab-note">' + esc(PD.t("memories.note")) + "</p>";
    if (S.memErr) return note + '<p class="msg err">' + esc(S.memErr) + "</p>";
    if (!S.mem) return note + '<p class="sub">' + esc(PD.t("common.reading")) + "</p>";
    if (!S.mem.length) return note + PD.empty("bulb", "<strong>" + esc(PD.t("memories.none")) + "</strong> " + esc(PD.t("memories.none_hint")));
    return note + '<p class="meta">' + esc(PD.t("memories.count", { n: S.mem.length, max: S.memMax })) + "</p>" +
      '<div class="custom-tags">' + S.mem.map(m => '<div class="custom-tag memory-card">' +
        '<div class="label-row"><span class="meta">' + esc(PD.t("memories.saved_on", { date: m.saved || "" })) + "</span>" +
        '<span class="actions-inline"><button type="button" class="link-btn" data-act="memdel" data-id="' + esc(m.id) + '">' + esc(PD.t("common.delete")) + "</button></span></div>" +
        '<textarea class="field" id="md-mem-' + esc(m.id) + '" rows="3" aria-label="' + esc(PD.t("memories.one")) + '">' + esc(m.text) + "</textarea></div>").join("") + "</div>";
  }

  async function memAct(a, id) {
    const box = $("#md-mem-" + id, R);
    const base = "/lineups/" + encodeURIComponent(S.show) + "/memories/" + encodeURIComponent(id);
    const [d, e] = a === "memsave"
      ? await PD.safe(PD.api("PUT", base, { text: box ? box.value : "" }))
      : await PD.safe(PD.api("DELETE", base));
    if (e) { S.msg = PD.errText(e); S.bad = true; }
    else { S.mem = d.memories || []; S.msg = PD.t(a === "memsave" ? "memories.saved" : "memories.deleted"); S.bad = false; }
    paint();
  }

  function paint(focusGrip) {
    const box = $("#md-body", R); if (!box) return;
    if (!S.data) { box.innerHTML = S.msg ? '<p class="msg err">' + esc(S.msg) + "</p>" : ('<p class="sub">' + esc(PD.t("common.reading")) + "</p>"); return; }
    const top = '<div class="lineup-top"><span class="select"><select class="field" id="md-pick" aria-label="' + esc(PD.t("lineup.label")) + '">' +
      S.data.lineups.map(l => '<option value="' + esc(l.name) + '"' + (l.name === S.show ? " selected" : "") + ">" + esc(l.name) + "</option>").join("") +
      '<option value="__new__">' + esc(PD.t("lineup.new_option")) + "</option></select></span>" +
      '<span class="actions-inline"><button type="button" class="btn" data-act="rename">' + esc(PD.t("lineup.rename")) + "</button>" +
      '<button type="button" class="btn" data-act="delete"' + (S.data.lineups.length < 2 ? " disabled" : "") + ">" + esc(PD.t("common.delete")) + "</button></span></div>";
    const tab = (id, label) => '<button type="button" class="ftab" role="tab" data-act="tab" data-tab="' + id + '" aria-selected="' + (S.tab === id) + '">' + label + "</button>";
    const panel = S.tab === "search" ? PD.slots.searchHtml(P, S.search, PD.slots.testHtml(S.test.search))
      : S.tab === "tags" ? PD.slots.tagsHtml(P, S.tags)
      : S.tab === "memories" ? memoriesHtml()
      : S.tab === "jobs" ? '<div id="md-jobs"></div>'
      : S.tab === "tests" ? '<div id="md-tests"></div>'
      : PD.slots.html(P, S.tab, S.forms[S.tab], S.harnesses, PD.slots.testHtml(S.test[S.tab]), S.show);
    const msg = '<span class="msg' + (S.bad ? " err" : "") + '" id="md-msg" role="status">' + esc(S.msg) + "</span>";
    box.innerHTML = top +
      '<div class="ftabs" role="tablist">' + tab("text", PD.t("tab.text")) + tab("image", PD.t("tab.image")) + tab("search", PD.t("tab.network")) + tab("tags", PD.t("tab.tags")) +
      tab("memories", PD.t("tab.memories")) + tab("jobs", PD.t("jobs.label")) + tab("tests", PD.t("tab.tests")) + "</div>" +
      '<div class="fpanel" role="tabpanel">' + panel + "</div>" +
      '<div class="actions next">' + msg + "</div>";
    PD.wireCode(box); PD.wireTypeahead(box);
    if (focusGrip != null) PD.slots.focusGrip(box, focusGrip);
    const tests = $("#md-tests", R);                 // the Tests screen, run against the lineups, inside this tab
    if (tests && PD.screens.tests) { PD.screens.tests.mount(tests); PD.screens.tests.use(S.show); if (PD.screens.tests.show) PD.screens.tests.show(); }
    const jobs = $("#md-jobs", R);                   // the Jobs list, of this lineup only
    if (jobs && PD.screens.jobs) { PD.screens.jobs.mount(jobs); PD.screens.jobs.use(S.show, (S.tags[0] && S.tags[0].name) || ""); PD.screens.jobs.show(); }
    if (S.tab === "memories" && !S.mem && !S.memErr) loadMemories();
  }

  // EVERY CHANGE IS SAVED AS IT IS MADE: a field's change, a tag added, removed or moved. Saves run one after
  // another, and a quiet one leaves the page as it is (the field being typed into keeps its focus).
  let chain = Promise.resolve(true);
  function autosave() { chain = chain.then(() => save(true), () => save(true)); return chain; }

  async function save(quiet) {
    readAll();
    const l = lineup(); if (!l) return false;
    const err = await PD.slots.saveKeys(Object.assign({}, S.forms, { search: S.search }));
    if (err) { S.msg = err; S.bad = true; paint(); return false; }
    // a key typed in is kept now: it leaves the field (it is never read back from the credential store)
    for (const role of ["text", "image", "search"]) {
      const box = $("#" + P + "-" + role + "-key", R);
      if (box && box.value) { box.value = ""; box.placeholder = PD.t("slot.saved"); }
    }
    const body = { text: PD.slots.slotOf("text", S.forms.text, l.text), image: PD.slots.slotOf("image", S.forms.image, l.image),
                   search: PD.slots.searchOut(S.search), tags: PD.slots.tagsOut(S.tags) };
    const [d, e] = await PD.safe(PD.api("PUT", "/lineups/" + encodeURIComponent(l.name), body));
    if (e) { S.msg = PD.errText(e); S.bad = true; paint(); return false; }
    S.data = d; S.msg = PD.t("common.saved"); S.bad = false;
    if (quiet) { const m = $("#md-msg", R); if (m) { m.textContent = S.msg; m.className = "msg"; } }
    else { fill(); paint(); }
    PD.refreshStatus();
    return true;
  }

  async function test(role) {
    S.test[role] = "testing"; paint();
    if (!await save()) { S.test[role] = ""; paint(); return; }
    const q = "?lineup=" + encodeURIComponent(S.show);
    if (role === "search") {
      const [d, e] = await PD.safe(PD.api("POST", "/search/test" + q));
      S.test.search = e ? PD.errText(e) : d && d.ok ? "ok" : (d && d.error) || PD.t("common.no_answer");
      paint(); return;
    }
    for (let i = 0; i < 4; i++) {
      const [m] = await PD.safe(PD.api("GET", "/models" + q));
      if (m && m[role] && m[role].server && m[role].server.answering) { S.test[role] = "ok"; paint(); return; }
      await new Promise(r => setTimeout(r, 1500));
    }
    S.test[role] = PD.t("lineup.test_no_answer"); paint();
  }

  async function act(a, el) {
    if (a === "tab") { readAll(); S.tab = el.dataset.tab; S.msg = ""; paint(); }
    else if (a === "addtag") { readAll(); S.tags.push({ name: "", prompt: "" }); paint(); }
    else if (a === "deltag") { readAll(); S.tags.splice(Number(el.dataset.i), 1); paint(); autosave(); }
    else if (a === "memdel") {
      if (a === "memdel" && !await PD.confirm({ title: PD.t("memories.delete_q"), body: [esc(PD.t("memories.delete_body"))], action: PD.t("common.delete"), danger: true })) return;
      PD.busy(el, () => memAct(a, el.dataset.id));
    }
    else if (a === "test") test(el.dataset.role);
    else if (a === "loras") {                         // the lineup's LoRA folder, in Explorer (made when it is not there)
      const [, e] = await PD.safe(PD.api("POST", "/lineups/" + encodeURIComponent(el.dataset.lineup) + "/loras/open"));
      if (e) { S.msg = PD.errText(e); S.bad = true; paint(); }
    }
    else if (a === "addharness") { readAll(); PD.api("POST", "/harnesses/open", { kind: el.dataset.kind }); S.stale = true; }
    else if (a === "new" || a === "rename") {
      const v = await PD.ask({ title: PD.t(a === "new" ? "lineup.new" : "lineup.rename_title"), action: PD.t(a === "new" ? "lineup.create" : "lineup.rename"),
        fields: [{ name: "name", label: PD.t("lineup.name"), kind: "text", value: a === "new" ? "" : S.show }] });
      if (!v || !v.name.trim()) return;
      const name = v.name.trim();
      const [, e] = a === "new"
        ? await PD.safe(PD.api("PUT", "/lineups/" + encodeURIComponent(name), { name }))
        : await PD.safe(PD.api("PUT", "/lineups/" + encodeURIComponent(S.show), { name }));
      if (e) { S.msg = PD.errText(e); S.bad = true; paint(); return; }
      S.show = name; S.msg = ""; await load(true);
    }
    else if (a === "delete") {
      const ok = await PD.confirm({ title: PD.t("lineup.delete_q", { name: S.show }), body: [esc(PD.t("lineup.delete_body"))], action: PD.t("common.delete"), danger: true });
      if (!ok) return;
      const [, e] = await PD.safe(PD.api("DELETE", "/lineups/" + encodeURIComponent(S.show)));
      if (e) { S.msg = PD.errText(e); S.bad = true; paint(); return; }
      S.show = ""; S.msg = ""; await load(false);
    }
  }

  PD.screen("models", {
    label: PD.t("lineup.label"), group: 1,
    mount(root) {
      R = root;
      root.innerHTML = '<div class="page-head"><h1>' + esc(PD.t("lineup.label")) + '</h1></div><div id="md-body"></div>';
      PD.on(root, "click", "[data-act]", (e, el) => act(el.dataset.act, el));
      PD.slots.wireTagSort(root, P, () => (S.tab === "tags" ? S.tags : null), i => { paint(i); autosave(); });
      root.addEventListener("change", e => {
        const t = e.target;
        if (t.id === "md-pick" && t.value === "__new__") { t.value = S.show; act("new", t); }
        else if (t.id === "md-pick") { S.show = t.value; S.msg = ""; fill(); paint(); }
        else if (/^md-(text|image|search)-(kind|provider)$/.test(t.id)) { readAll(); S.test[S.tab] = ""; paint(); autosave(); }
        else if (/^md-mem-/.test(t.id)) memAct("memsave", t.id.slice(7));
        else if (/^md-/.test(t.id) && ["text", "image", "search", "tags"].includes(S.tab)) autosave();
      });
      window.addEventListener("focus", async () => {
        if (!S.stale || !R || !R.isConnected) return;
        S.stale = false; readAll(); const [h] = await PD.safe(PD.api("GET", "/harnesses"));
        S.harnesses = Array.isArray(h) ? h.filter(x => x.id && !x.error) : S.harnesses; PD.slots.harnesses = S.harnesses; paint();
      });
    },
    show() { if (PD.firstTab) { S.tab = PD.firstTab; PD.firstTab = ""; } load(true); },
    poll(n) {
      if (S.tab === "tests" && PD.screens.tests && PD.screens.tests.poll) return PD.screens.tests.poll(n);
      if (S.tab === "jobs" && PD.screens.jobs && PD.screens.jobs.poll) return PD.screens.jobs.poll(n);
    },
  });
})();
