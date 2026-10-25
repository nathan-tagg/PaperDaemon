"use strict";
/* Notes (Daemon > Notes): each notebook's memory of its jobs. Pick a notebook, read its entries, wipe it. A panel of
   the Daemon screen, not a screen of its own: PD.notes.mount(el), show(), poll().
   BOTH LIBRARIES: the tablet's notebooks keep their notes in the engine's state, the False Mirror's in the False
   Mirror's own (its own engine, reached through /fm): the list shows each under its library's name. A notebook is
   (base, doc): S.doc is the key "base|doc". */
(() => {
  const { $, esc } = PD;
  let R = null;
  const S = { list: null, err: "", doc: null, text: null, textErr: "", wipeErr: "", all: false, wiped: null };
  const SHOWN = 40;

  /** The engine's entries -> what the list shows: {date, hasTime, page (its label), asked, did}. */
  function blocksOf(entries) {
    return (entries || []).map(e => {
      const hm = String(e.when || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?/);
      const date = hm ? new Date(+hm[1], +hm[2] - 1, +hm[3], hm[4] ? +hm[4] : 0, hm[5] ? +hm[5] : 0) : null;
      return { date, hasTime: !!(hm && hm[4]), page: e.page ? PD.t("job.page", { n: e.page }) : "",
               asked: e.asked || [], did: e.did || [] };
    });
  }

  const keyOf = n => (n.base || "") + "|" + n.doc;
  const partsOf = k => { const i = k.indexOf("|"); return { base: k.slice(0, i), doc: k.slice(i + 1) }; };
  function listHtml() {
    if (S.err) return '<p class="notice attn" role="alert"><strong>' + esc(PD.t("np.list_unreadable")) + "</strong> " + esc(S.err) + "</p>";
    if (!S.list) return '<p class="sub" style="margin-top: var(--s3)">' + esc(PD.t("np.reading_list")) + "</p>";
    const group = (base, label) => {
      const its = S.list.filter(n => (n.base || "") === base).sort((a, b) => (b.updated || 0) - (a.updated || 0));   // newest first
      if (!its.length) return "";
      return '<p class="meta np-lib">' + esc(label) + '</p><ul class="booklist">' + its.map(n =>
        '<li><button type="button" data-doc="' + esc(keyOf(n)) + '"' + (keyOf(n) === S.doc ? ' aria-current="true"' : "") + "><strong>" + esc(n.notebook || n.doc) +
        "</strong></button></li>").join("") + "</ul>";
    };
    return group("", PD.t("tablet.label")) + group("/fm", PD.t("fm.label"));
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
      out += '<p class="actions" style="margin-top: var(--s3)"><button type="button" class="btn" data-np="more">' +
        esc(S.all ? PD.t("np.show_fewer") : PD.count("np.show_older", blocks.length - SHOWN)) + "</button></p>";
    }
    return out;
  }

  function padHtml() {
    if (!S.doc) return '<p class="sub" style="margin-top: var(--s3)">' + esc(PD.t("np.select")) + "</p>";
    const n = (S.list || []).find(x => keyOf(x) === S.doc) || {};
    const name = n.notebook || partsOf(S.doc).doc;
    if (S.wiped === S.doc) {
      return '<header class="padhead"><div><h2>' + esc(name) + '</h2></div></header>' + PD.empty("notepad",
        "<strong>" + esc(PD.t("np.wiped_at", { time: PD.clock(new Date()) })) + "</strong> " + esc(PD.t("np.wiped_body", { name })));
    }
    const head = '<header class="padhead"><div><h2>' + esc(name) + "</h2></div>" +
      '<div class="actions"><button type="button" class="btn danger small" data-np="wipe">' + esc(PD.t("np.wipe")) + "</button></div></header>";
    const wipeNote = S.wipeErr ? '<p class="notice attn" role="alert" style="margin-top: var(--s4)"><strong>' + esc(PD.t("np.not_wiped")) + "</strong> " + esc(S.wipeErr) + "</p>" : "";
    if (S.textErr) return head + '<p class="notice attn" role="alert" style="margin-top: var(--s4)"><strong>' + esc(PD.t("np.unreadable")) + "</strong> " + esc(S.textErr) + "</p>";
    if (S.text == null) return head + wipeNote + '<p class="sub" style="margin-top: var(--s4)">' + esc(PD.t("np.reading")) + "</p>";
    if (!S.text.trim()) return head + wipeNote + PD.empty("notepad", "<strong>" + esc(PD.t("np.empty")) + "</strong>");
    return head + wipeNote + '<div class="shown">' + entriesHtml(S.text) + "</div>";
  }

  function render() {
    if (!R) return;
    const none = !!S.list && !S.list.length && !S.err;
    $(".pads", R).hidden = none;
    PD.html($("#np-none", R), none ? PD.empty("notepad", "<strong>" + esc(PD.t("np.none")) + "</strong>") : "");
    PD.html($("#np-list", R), listHtml());
    PD.html($("#np-pad", R), padHtml());
  }

  const fmHere = () => !!((PD.status || {}).false_mirror || {}).exists;
  async function listOf(base) {
    const [d, e] = await PD.safe(PD.api("GET", base + "/notepads"));
    return [e ? null : (Array.isArray(d) ? d : d.notepads || []).map(n => Object.assign({}, n, { base })), e];
  }
  async function loadList() {
    const [[mine, e], [fmList]] = await Promise.all([listOf(""), fmHere() ? listOf("/fm") : Promise.resolve([[], null])]);
    if (e) { S.err = PD.errText(e); S.list = S.list || null; }
    else { S.err = ""; S.list = mine.concat(fmList || []); }       // the False Mirror's, when it answers
    if (S.list && S.doc && !S.list.some(n => keyOf(n) === S.doc)) { S.doc = null; S.text = null; }
    if (S.list && !S.doc && S.list.length) await open(keyOf(S.list[0]));
    render();
  }

  const padPath = k => { const p = partsOf(k); return p.base + "/notepads/" + encodeURIComponent(p.doc); };
  async function open(doc) {
    S.doc = doc; S.text = null; S.entries = []; S.textErr = ""; S.wipeErr = ""; S.all = false; S.wiped = null;
    render();
    const [d, e] = await PD.safe(PD.api("GET", padPath(doc)));
    if (S.doc !== doc) return;
    if (e) S.textErr = PD.errText(e); else { S.text = d.text || ""; S.entries = d.entries || []; }
    render();
  }

  async function wipe() {
    const n = (S.list || []).find(x => keyOf(x) === S.doc) || {}, name = n.notebook || PD.t("np.this_notebook");
    const ok = await PD.confirm({
      title: PD.t("np.wipe_q", { name }),
      body: [esc(PD.t("np.wipe_body", { entries: PD.count("count.entry", n.entries || 0), name })), esc(PD.t("np.wipe_body2"))],
      action: PD.t("np.wipe"),
    });
    if (!ok) return;
    const doc = S.doc;
    const [, e] = await PD.safe(PD.api("POST", padPath(doc) + "/wipe"));
    if (e) { S.wipeErr = PD.errText(e); render(); return; }
    S.wiped = doc; S.text = ""; S.textErr = ""; S.wipeErr = "";
    await loadList();
  }

  PD.notes = {
    mount(root) {
      R = root;
      R.innerHTML = '<p class="tab-note">' + esc(PD.t("np.intro")) + "</p>" +
        '<div id="np-none"></div><div class="pads"><aside class="books" aria-label="' + esc(PD.t("np.books")) + '">' +
        '<div id="np-list"></div></aside><div id="np-pad" aria-live="polite"></div></div>';
      PD.on(R, "click", "button[data-doc]", (e, el) => open(el.dataset.doc));
      PD.on(R, "click", "button[data-np]", (e, el) => {
        const a = el.dataset.np;
        if (a === "more") { S.all = !S.all; render(); }
        else if (a === "wipe") wipe();
      });
    },
    show() { render(); loadList(); },
    async poll() { if (S.doc && !S.wiped) { const [d] = await PD.safe(PD.api("GET", padPath(S.doc))); if (d && S.doc) { const t = d.text || ""; if (t !== S.text) { S.text = t; S.entries = d.entries || []; loadList(); } } } },
  };
})();
