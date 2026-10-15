"use strict";
/* Notepads: each notebook's memory of its jobs. Pick a notebook, read its entries, wipe it. */
(() => {
  const { $, $$, esc, line } = PD;
  let R = null;
  const S = { list: null, err: "", doc: null, text: null, textErr: "", wipeErr: "", view: "entries", all: false, wiped: null, find: "", count: null };
  const SHOWN = 40;

  PD.prefetch.push(async () => {
    const [d] = await PD.safe(PD.api("GET", "/notepads"));
    if (Array.isArray(d)) { S.count = d.length; PD.paintRail(); }
  });

  /** The engine's entries -> what the list shows: {date, hasTime, page (its label), asked, did}. */
  function blocksOf(entries) {
    return (entries || []).map(e => {
      const hm = String(e.when || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?/);
      const date = hm ? new Date(+hm[1], +hm[2] - 1, +hm[3], hm[4] ? +hm[4] : 0, hm[5] ? +hm[5] : 0) : null;
      return { date, hasTime: !!(hm && hm[4]), page: e.page ? PD.t("job.page", { n: e.page }) : "",
               asked: e.asked || [], did: e.did || [] };
    });
  }

  function summary(n) { return PD.t("np.summary", { entries: PD.count("count.entry", n.entries || 0), chars: PD.n(n.chars || 0) }); }

  function listHtml() {
    if (S.err) return '<p class="notice attn" role="alert"><strong>' + esc(PD.t("np.list_unreadable")) + "</strong> " + esc(S.err) + "</p>";
    if (!S.list) return '<p class="sub" style="margin-top: var(--s3)">' + esc(PD.t("np.reading_list")) + "</p>";
    const q = S.find.trim().toLowerCase();
    const items = S.list.filter(n => !q || String(n.notebook || n.doc).toLowerCase().includes(q));
    return '<ul class="booklist">' + items.map(n =>
      '<li><button type="button" data-doc="' + esc(n.doc) + '"' + (n.doc === S.doc ? ' aria-current="true"' : "") + "><strong>" + esc(n.notebook || n.doc) +
      '</strong><span class="meta num">' + esc(summary(n)) + "</span></button></li>").join("") + "</ul>" +
      (q && !items.length ? '<p class="meta">' + esc(PD.t("np.no_match")) + "</p>" : "");
  }

  function entriesHtml(text) {
    let blocks = blocksOf(S.entries);
    // newest first: by date when every entry has one, otherwise the file's order reversed
    blocks = blocks.every(b => b.date) ? blocks.map((b, i) => [b, i]).sort((x, y) => (y[0].date - x[0].date) || (y[1] - x[1])).map(x => x[0]) : blocks.reverse();
    if (!blocks.length) return '<pre class="snippet pad-text">' + esc(text) + "</pre>";
    const shown = S.all ? blocks : blocks.slice(0, SHOWN);
    let day = "", out = '<ol class="pad">';
    for (const b of shown) {
      const label = b.date ? PD.dayLabel(b.date) : "";
      if (label !== day) { out += '<li class="day">' + esc(label || PD.t("np.undated")) + "</li>"; day = label; }
      out += '<li class="entry"><div class="when">' + (b.hasTime ? "<time>" + esc(PD.clock(b.date)) + "</time>" : "") +
        (b.page ? '<span class="meta">' + esc(b.page) + "</span>" : "") + "</div><div>" +
        (b.asked.length ? b.asked.map(a => '<p class="asked">' + esc(a) + "</p>").join("") : "") +
        b.did.map(d => '<p class="did">' + esc(d) + "</p>").join("") + "</div></li>";
    }
    out += "</ol>";
    if (blocks.length > SHOWN) {
      out += '<p class="actions" style="margin-top: var(--s3)"><button type="button" class="btn" data-act="more">' +
        esc(S.all ? PD.t("np.show_fewer") : PD.count("np.show_older", blocks.length - SHOWN)) + "</button></p>";
    }
    return out;
  }

  function padHtml() {
    if (!S.doc) return '<p class="sub" style="margin-top: var(--s3)">' + esc(PD.t("np.select")) + "</p>";
    const n = (S.list || []).find(x => x.doc === S.doc) || {};
    const name = n.notebook || S.doc;
    if (S.wiped === S.doc) {
      return '<header class="padhead"><div><h2>' + esc(name) + '</h2></div></header>' + PD.empty("notepad",
        "<strong>" + esc(PD.t("np.wiped_at", { time: PD.clock(new Date()) })) + "</strong> " + esc(PD.t("np.wiped_body", { name })));
    }
    const head = '<header class="padhead"><div><h2>' + esc(name) + '</h2><p class="meta num">' + esc(summary(n)) + "</p></div>" +
      '<div class="actions"><button type="button" class="btn quiet small" data-act="copy">' + esc(PD.t("np.copy")) + "</button>" +
      '<button type="button" class="btn danger small" data-act="wipe">' + esc(PD.t("np.wipe")) + "</button></div></header>";
    const wipeNote = S.wipeErr ? '<p class="notice attn" role="alert" style="margin-top: var(--s4)"><strong>' + esc(PD.t("np.not_wiped")) + "</strong> " + esc(S.wipeErr) + "</p>" : "";
    if (S.textErr) return head + '<p class="notice attn" role="alert" style="margin-top: var(--s4)"><strong>' + esc(PD.t("np.unreadable")) + "</strong> " + esc(S.textErr) + "</p>";
    if (S.text == null) return head + wipeNote + '<p class="sub" style="margin-top: var(--s4)">' + esc(PD.t("np.reading")) + "</p>";
    if (!S.text.trim()) return head + wipeNote + PD.empty("notepad", "<strong>" + esc(PD.t("np.empty")) + "</strong>");
    return head + wipeNote + '<div class="spread tight"><div class="seg small" role="group" aria-label="' + esc(PD.t("np.show")) + '">' +
      '<button type="button" data-view="entries" aria-pressed="' + (S.view === "entries") + '">' + esc(PD.t("np.entries")) + "</button>" +
      '<button type="button" data-view="text" aria-pressed="' + (S.view === "text") + '">' + esc(PD.t("np.as_text")) + "</button></div>" +
      "</div>" +
      '<div class="shown">' + (S.view === "entries" ? entriesHtml(S.text) : '<pre class="snippet pad-text">' + esc(S.text) + "</pre>") + "</div>";
  }

  function render() {
    if (!R) return;
    const none = !!S.list && !S.list.length && !S.err;
    $(".pads", R).hidden = none;
    PD.html($("#np-none", R), none ? PD.empty("notepad", "<strong>" + esc(PD.t("np.none")) + "</strong>") : "");
    PD.html($("#np-list", R), listHtml());
    PD.html($("#np-pad", R), padHtml());
  }

  async function loadList() {
    const [d, e] = await PD.safe(PD.api("GET", "/notepads"));
    if (e) { S.err = PD.errText(e); S.list = S.list || null; }
    else { S.err = ""; S.list = Array.isArray(d) ? d : d.notepads || []; S.count = S.list.length; PD.paintRail(); }
    if (S.list && S.doc && !S.list.some(n => n.doc === S.doc)) { S.doc = null; S.text = null; }
    if (S.list && !S.doc && S.list.length) await open(S.list[0].doc);
    render();
  }

  async function open(doc) {
    S.doc = doc; S.text = null; S.entries = []; S.textErr = ""; S.wipeErr = ""; S.all = false; S.wiped = null;
    render();
    const [d, e] = await PD.safe(PD.api("GET", "/notepads/" + encodeURIComponent(doc)));
    if (S.doc !== doc) return;
    if (e) S.textErr = PD.errText(e); else { S.text = d.text || ""; S.entries = d.entries || []; }
    render();
  }

  async function wipe() {
    const n = (S.list || []).find(x => x.doc === S.doc) || {}, name = n.notebook || PD.t("np.this_notebook");
    const ok = await PD.confirm({
      title: PD.t("np.wipe_q", { name }),
      body: [esc(PD.t("np.wipe_body", { entries: PD.count("count.entry", n.entries || 0), name })), esc(PD.t("np.wipe_body2"))],
      action: PD.t("np.wipe"),
    });
    if (!ok) return;
    const doc = S.doc;
    const [, e] = await PD.safe(PD.api("POST", "/notepads/" + encodeURIComponent(doc) + "/wipe"));
    if (e) { S.wipeErr = PD.errText(e); render(); return; }
    S.wiped = doc; S.text = ""; S.textErr = ""; S.wipeErr = "";
    const [d] = await PD.safe(PD.api("GET", "/notepads"));
    if (Array.isArray(d)) { S.list = d; S.count = d.length; PD.paintRail(); }
    render();
  }

  PD.screen("notepads", {
    label: PD.t("np.label"), group: 0, railNum: true,
    rail() { return S.count != null ? esc(String(S.count)) : ""; },
    mount(root) {
      R = root;
      R.innerHTML =
        '<header class="page-head"><h1>' + esc(PD.t("np.label")) + "</h1>" +
        "<p>" + esc(PD.t("np.intro")) + "</p></header>" +
        '<div id="np-none"></div><div class="pads"><aside class="books" aria-label="' + esc(PD.t("np.books")) + '">' +
        '<input class="field" type="search" id="np-find" placeholder="' + esc(PD.t("np.find")) + '" aria-label="' + esc(PD.t("np.find")) + '" autocomplete="off">' +
        '<div id="np-list"></div></aside><div id="np-pad" aria-live="polite"></div></div>';
      $("#np-find", R).addEventListener("input", e => { S.find = e.target.value; render(); });
      PD.on(R, "click", "button[data-doc]", (e, el) => open(el.dataset.doc));
      PD.on(R, "click", "button[data-view]", (e, el) => { S.view = el.dataset.view; render(); });
      PD.on(R, "click", "button[data-act]", async (e, el) => {
        const a = el.dataset.act;
        if (a === "more") { S.all = !S.all; render(); }
        else if (a === "wipe") wipe();
        else if (a === "copy") { const ok = await PD.copy(S.text || ""); el.textContent = PD.t(ok ? "common.copied" : "common.copy_failed"); setTimeout(() => { el.textContent = PD.t("np.copy"); }, 1500); }
      });
    },
    show() { S.find = ""; const f = $("#np-find", R); if (f) f.value = ""; render(); loadList(); },
    async poll() { if (S.doc && !S.wiped) { const [d] = await PD.safe(PD.api("GET", "/notepads/" + encodeURIComponent(S.doc))); if (d && S.doc) { const t = d.text || ""; if (t !== S.text) { S.text = t; S.entries = d.entries || []; loadList(); } } } },
  });
})();
