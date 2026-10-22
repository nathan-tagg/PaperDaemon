"use strict";
/* Decompose: turn a picture into pen strokes and send it to the tablet's inbox. A picture dropped (a file, or an
   image dragged from a browser) shows in the drop zone under its progress ring while it decomposes, then joins the
   Decomps. */
(() => {
  const { $, esc } = PD;
  let R = null, seq = 0;
  const MAX_BYTES = 25e6;
  // SENT, FOR THIS SESSION ONLY: a decomp sent says so on its button until the window is loaded again
  const S = { working: [], items: [], width: 1200, err: "", page: 0, per: 10, total: 0, sent: new Set() };

  const uploadIcon = '<svg viewBox="0 0 40 52" aria-hidden="true"><rect x="1" y="1" width="38" height="50" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M20 34V16M13 23l7-7 7 7" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
  const eyeIcon = '<svg viewBox="0 0 24 16" aria-hidden="true"><path d="M1 8s4-7 11-7 11 7 11 7-4 7-11 7S1 8 1 8z" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';

  const widthOk = w => Number.isFinite(w) && w >= 200 && w <= 1600;            // the page's safe width (studio.box_for)
  function setErr(t) { S.err = t || ""; const el = $("#dc-err", R); if (el) el.textContent = S.err; }

  // ---- the drop zone: the prompt, or the pictures being decomposed, each under a ring that fills as the engine
  // reports its progress (the decompose from inside the C, then the preview as its strokes are drawn)

  const ring = (w) => {
    const pct = Math.round((w.done || 0) * 100);
    return '<span class="ring" role="progressbar" aria-label="' + esc(PD.t("dc.decomposing", { name: w.name })) + '" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct + '">' +
      '<svg viewBox="0 0 44 44" aria-hidden="true"><circle class="track" cx="22" cy="22" r="19"/>' +
      '<circle class="fill" cx="22" cy="22" r="19" pathLength="100" stroke-dasharray="100" stroke-dashoffset="' + (100 - pct) + '" transform="rotate(-90 22 22)"/></svg>' +
      '<span class="pct">' + (w.state === "waiting" ? esc(PD.t("job.waiting")) : pct + "%") + "</span></span>";
  };

  function renderZone() {
    const zone = $("#dc-zone", R); if (!zone) return;
    zone.classList.toggle("loaded", S.working.length > 0);
    $("#dc-zone-body", R).innerHTML = S.working.length
      ? '<div class="dc-working">' + S.working.map(w => '<div class="decomp-pic working" data-job="' + w.job + '"><img alt="' + esc(w.name) + '" src="' + esc(w.src) + '">' + ring(w) + "</div>").join("") + "</div>"
      : '<span class="drop-icon">' + uploadIcon + '</span><p>' + PD.tHtml("dc.drop", {
          choose: '<button type="button" class="link-btn" data-act="choose">' + esc(PD.t("dc.choose")) + "</button>",
          paste: '<button type="button" class="link-btn" data-act="paste">' + esc(PD.t("dc.paste")) + "</button>" }) + "</p>";
  }

  /** Ask the engine how far each picture in the zone has come, and move its ring; until none is left. */
  let polling = false;
  async function poll() {
    if (polling) return;
    polling = true;
    while (S.working.length && R && R.isConnected) {
      for (const w of S.working.slice()) {
        const [p] = await PD.safe(PD.api("GET", "/decompose/progress?job=" + encodeURIComponent(w.job)));
        if (!p) continue;
        w.state = p.state;
        w.done = Math.max(w.done || 0, p.done || 0);
        const el = R.querySelector('[data-job="' + w.job + '"] .ring');
        if (el) el.outerHTML = ring(w);
      }
      await new Promise(r => setTimeout(r, 250));
    }
    polling = false;
  }

  // ---- the decomps: KEPT BY THE ENGINE, on disk (strokes and preview, studio's note), shown a page at a time; nothing
  // of them stays here but the page in view. The pager sits on the Decomps title's row, at its right.

  const PER = [10, 50, 100];
  const chevron = d => '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="' + d + '"/></svg>';
  const PREV = chevron("M10 3L5 8l5 5"), NEXT = chevron("M6 3l5 5-5 5");
  try { const v = Number(localStorage.getItem("pd-decomps-per")); if (PER.includes(v)) S.per = v; } catch (e) { /* the default */ }

  function itemHtml(it) {
    const act = S.sent.has(it.id) ? '<span class="sent">' + esc(PD.t("dc.sent")) + "</span>"
      : '<button type="button" class="btn primary small" data-send="' + it.id + '"' + (it.sending ? ' disabled aria-busy="true"' : "") + ">" + esc(PD.t(it.sending ? "dc.sending" : "dc.send")) + "</button>";
    return '<figure class="decomp">' +
      '<div class="decomp-pic"><img alt="" data-preview="' + it.id + '">' +
      '<button type="button" class="eye" data-look="' + it.id + '" aria-label="' + esc(PD.t("dc.look")) + '">' + eyeIcon + "</button></div>" +
      '<figcaption><span class="name">' + esc(it.name) + '</span><span class="meta num">' + esc(PD.t("dc.size_px", { w: PD.n(it.width), h: PD.n(it.height) })) + "</span><span class=\"meta\">" + PD.count("count.stroke", it.strokes) + " · " + esc(PD.dur(it.seconds || 0)) + "</span>" +
      // Delete and Save together at the left, Send to Tablet at the right
      '<span class="decomp-actions"><span class="decomp-keep"><button type="button" class="btn small" data-del="' + it.id + '">' + esc(PD.t("common.delete")) + "</button>" +
      '<button type="button" class="btn small" data-save="' + it.id + '"' + (it.saving ? ' disabled aria-busy="true"' : "") + ">" + esc(PD.t(it.saving ? "dc.saving" : "dc.save")) + "</button></span>" +
      act + "</span>" + (it.note ? '<span class="meta' + (it.noteBad ? " attn-text" : "") + '" role="status">' + esc(it.note) + "</span>" : "") + "</figcaption></figure>";
  }

  function pagerHtml() {
    const pages = Math.max(1, Math.ceil(S.total / S.per)), at = S.page;
    const from = S.total ? at * S.per + 1 : 0, to = Math.min(S.total, (at + 1) * S.per);
    const a = Math.max(0, Math.min(at - 2, pages - 5)), b = Math.min(pages, a + 5);
    const nums = [];
    for (let i = a; i < b; i++) nums.push('<button type="button" class="pg-n' + (i === at ? " on" : "") + '" data-pg="' + i + '"' + (i === at ? ' aria-current="page"' : "") + ">" + PD.n(i + 1) + "</button>");
    return '<span class="pg-count num">' + esc(PD.t("dc.range", { from: PD.n(from), to: PD.n(to), total: PD.n(S.total) })) + "</span>" +
      '<span class="pg-per"><span class="meta">' + esc(PD.t("dc.per_page")) + "</span>" +
      PER.map(n => '<button type="button" class="pg-n' + (n === S.per ? " on" : "") + '" data-per="' + n + '" aria-pressed="' + (n === S.per) + '">' + n + "</button>").join("") + "</span>" +
      '<button type="button" class="icon-btn" data-pg="' + (at - 1) + '" aria-label="' + esc(PD.t("viewer.prev")) + '" title="' + esc(PD.t("viewer.prev")) + '"' + (at <= 0 ? " disabled" : "") + ">" + PREV + "</button>" +
      nums.join("") +
      '<button type="button" class="icon-btn" data-pg="' + (at + 1) + '" aria-label="' + esc(PD.t("viewer.next")) + '" title="' + esc(PD.t("viewer.next")) + '"' + (at >= pages - 1 ? " disabled" : "") + ">" + NEXT + "</button>";
  }

  function renderItems() {
    const box = $("#dc-items", R); if (!box) return;
    $("#dc-decomps", R).hidden = !S.total;
    $("#dc-pager", R).innerHTML = pagerHtml();
    box.innerHTML = S.items.map(itemHtml).join("");
    for (const img of box.querySelectorAll("img[data-preview]")) PD.loadImage(img, "/decomps/" + img.dataset.preview + "/preview.png");
  }

  /** The page of decomps in view, from the engine; a page past the last (after a delete) goes back to the last. */
  async function loadItems() {
    const [d] = await PD.safe(PD.api("GET", "/decomps?offset=" + S.page * S.per + "&limit=" + S.per));
    if (!d) return;
    S.total = d.total;
    if (!d.items.length && S.page > 0 && S.total) { S.page = Math.max(0, Math.ceil(S.total / S.per) - 1); return loadItems(); }
    const kept = new Map(S.items.map(it => [it.id, it]));     // what is under way on a card stays as it is
    S.items = d.items.map(m => Object.assign(kept.get(m.id) || {}, m));
    renderItems();
  }

  async function add(name, src) {
    if (!widthOk(S.width)) { setErr(PD.t("dc.size_range")); return; }
    const w = { name: name || PD.t("dc.picture"), src, width: S.width, job: "dc-" + Date.now().toString(36) + "-" + (++seq), state: "waiting", done: 0 };
    S.working.push(w); renderZone(); setErr(""); poll();
    const [d, e] = await PD.safe(PD.api("POST", "/decompose", { image: src, width: w.width, job: w.job, keep: true, name: w.name }));
    S.working = S.working.filter(x => x !== w); renderZone();
    if (e || !d || !d.id) { setErr(w.name + ": " + (e ? PD.errText(e) : "the engine kept no decomp.")); return; }
    S.page = 0; loadItems();                          // the newest is first
  }

  async function send(it) {
    if (!it || it.sending) return;
    it.sending = true; renderItems(); setErr("");
    try {
      await PD.api("POST", "/decompose/send", { id: it.id });
      S.sent.add(it.id);
    } catch (e) { setErr(PD.errText(e)); }
    it.sending = false; renderItems();
  }

  /** The decomp's preview (at the tablet's own scale) into the user's Downloads folder. */
  async function save(it) {
    if (!it || it.saving) return;
    it.saving = true; it.note = ""; renderItems();
    const [got, e] = await PD.safe(PD.api("POST", "/decompose/save", { id: it.id }));
    it.saving = false; it.note = e ? PD.errText(e) : PD.t("fm.exported", { name: got.name }); it.noteBad = !!e;
    renderItems();
  }

  async function remove(it) {
    if (!it) return;
    const [, e] = await PD.safe(PD.api("DELETE", "/decomps/" + it.id));
    if (e) { setErr(PD.errText(e)); return; }
    S.items = S.items.filter(x => x !== it); loadItems();
  }

  /** The paste control: an image on the clipboard (or an image's link), as if dropped. Ctrl+V does the same. */
  async function pasteClipboard() {
    setErr("");
    let items;
    try { items = await navigator.clipboard.read(); } catch (e) { setErr(PD.t("dc.paste_denied")); return; }
    for (const it of items) {
      const type = it.types.find(t => /^image\/(png|jpeg|webp)$/.test(t));
      if (type) { const b = await it.getType(type); fromFile(new File([b], PD.t("dc.picture") + "." + type.split("/")[1], { type })); return; }
    }
    for (const it of items) {                       // a copied image from a web page comes as its markup or its link
      const text = {};
      for (const t of ["text/html", "text/uri-list", "text/plain"]) if (it.types.includes(t)) text[t] = await (await it.getType(t)).text();
      const html = text["text/html"] || "", link = (text["text/uri-list"] || text["text/plain"] || "").trim();
      if (/<img[^>]+src="/i.test(html) || /^(https?:|data:image\/)/i.test(link)) {
        fromDrop({ files: [], getData: t => t === "text/html" ? html : t === "text/uri-list" ? link : "" }); return;
      }
    }
    setErr(PD.t("dc.paste_none"));
  }

  /** A close look at a decomp, in a viewer like the Tablet tab's. */
  function look(it) {
    if (!it) return;
    let dlg = $("#dc-viewer");
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "dc-viewer"; dlg.className = "viewer";
      dlg.innerHTML = '<div class="viewer-head"><span class="viewer-title"></span><button type="button" class="link-btn" data-v="close">' + esc(PD.t("common.close")) + "</button></div>" +
        '<div class="viewer-bar"><span class="viewer-tags"></span><span class="viewer-tools"></span></div><div class="viewer-page" tabindex="-1" autofocus><img alt=""></div>';
      dlg.addEventListener("click", e => { if (e.target.closest("[data-v=close]") || e.target === dlg) dlg.close(); });
      document.body.append(dlg);
    }
    $(".viewer-title", dlg).textContent = it.name;
    $(".viewer-tools", dlg).innerHTML = '<span class="meta">' + esc(PD.t("dc.size_px", { w: PD.n(it.width), h: PD.n(it.height) }) + " · " + PD.count("count.stroke", it.strokes)) + "</span>";
    const img = $(".viewer-page img", dlg), box = $(".viewer-page", dlg);
    img.style.width = ""; img.removeAttribute("src");
    dlg.showModal();
    // the kept preview, at the tablet's own scale; never enlarged: one picture pixel to at most one screen pixel, so the
    // pencil hatching shows as drawn, not smoothed
    PD.loadImage(img, "/decomps/" + it.id + "/preview.png").then(ok => {
      if (ok) img.style.width = Math.min(img.naturalWidth / (window.devicePixelRatio || 1), box.clientWidth - 32,
                                         (box.clientHeight - 32) * img.naturalWidth / img.naturalHeight) + "px";
    });
  }

  // ---- taking pictures in: files, chosen or dropped, and images dragged from a browser

  function fromFile(f) {
    if (!f) return;
    if (!/^image\/(png|jpeg|webp)$/.test(f.type)) { setErr(PD.t("dc.bad_type")); return; }
    if (f.size > MAX_BYTES) { setErr(PD.t("dc.too_big", { size: PD.bytes(f.size), max: PD.bytes(MAX_BYTES) })); return; }
    const r = new FileReader();
    r.onerror = () => setErr(PD.t("dc.unreadable"));
    r.onload = () => add(f.name, r.result);
    r.readAsDataURL(f);
  }

  function fromDrop(dt) {
    if (dt.files && dt.files.length) { [...dt.files].forEach(fromFile); return; }
    // a browser drags the image's address (and often its HTML); the engine fetches it
    const html = dt.getData("text/html") || "";
    const src = (html.match(/<img[^>]+src="([^"]+)"/i) || [])[1] || (dt.getData("text/uri-list") || "").split(/\r?\n/).find(l => /^https?:/i.test(l)) || "";
    if (!/^data:image\//.test(src) && !/^https?:/i.test(src)) { setErr(PD.t("dc.drop_what")); return; }
    let name = PD.t("dc.picture");
    try { name = decodeURIComponent(src.split("?")[0].split("/").pop()).slice(0, 80) || name; } catch (e) { /* keep the plain name */ }
    add(/^data:/.test(src) ? PD.t("dc.picture") : name, src.replace(/&amp;/g, "&"));
  }

  PD.screen("decompose", {
    label: PD.t("dc.label"), group: 0,
    mount(root) {
      R = root;
      R.innerHTML = '<header class="page-head"><h1>' + esc(PD.t("dc.label")) + "</h1>" +
        "<p>" + esc(PD.t("dc.intro")) + "</p></header>" +
        '<section class="section" aria-labelledby="dc-h-img"><h2 id="dc-h-img">' + esc(PD.t("dc.image")) + "</h2>" +
        '<div class="actions dc-size"><label class="meta" for="dc-width">' + esc(PD.t("dc.size")) + '</label><input class="field num w-s" id="dc-width" type="number" min="200" max="1600" step="50" value="' + S.width + '">' +
        '<span class="meta">' + esc(PD.t("dc.size_unit")) + '</span><span class="drop-note">' + esc(PD.t("dc.types")) + "</span></div>" +
        '<div class="drop" id="dc-zone"><div id="dc-zone-body"></div><input type="file" id="dc-file" accept="image/png,image/jpeg,image/webp" multiple hidden></div>' +
        '<p class="msg err" id="dc-err" role="alert"></p></section>' +
        '<section class="section" id="dc-decomps" aria-labelledby="dc-h-dec" hidden><div class="dc-head"><h2 id="dc-h-dec">' + esc(PD.t("dc.decomps")) +
        '</h2><nav class="pager" id="dc-pager" aria-label="' + esc(PD.t("dc.decomps")) + '"></nav></div><div class="decomps" id="dc-items"></div></section>';
      const zone = $("#dc-zone", R);
      PD.on(R, "click", "[data-act=choose]", () => $("#dc-file", R).click());
      PD.on(R, "click", "[data-act=paste]", () => pasteClipboard());
      PD.on(R, "click", "[data-save]", (e, el) => save(S.items.find(x => x.id === el.dataset.save)));
      $("#dc-file", R).addEventListener("change", e => { [...e.target.files].forEach(fromFile); e.target.value = ""; });
      for (const t of ["dragenter", "dragover"]) zone.addEventListener(t, e => { e.preventDefault(); zone.classList.add("over"); });
      zone.addEventListener("dragleave", () => zone.classList.remove("over"));
      zone.addEventListener("drop", e => { e.preventDefault(); zone.classList.remove("over"); fromDrop(e.dataTransfer); });
      $("#dc-width", R).addEventListener("input", e => { S.width = Number(e.target.value); setErr(widthOk(S.width) ? "" : PD.t("dc.size_range")); });
      PD.on(R, "click", "[data-del]", (e, el) => remove(S.items.find(x => x.id === el.dataset.del)));
      PD.on(R, "click", "[data-send]", (e, el) => send(S.items.find(x => x.id === el.dataset.send)));
      PD.on(R, "click", "[data-look]", (e, el) => look(S.items.find(x => x.id === el.dataset.look)));
      PD.on(R, "click", "[data-pg]", (e, el) => { const p = Number(el.dataset.pg); if (p >= 0 && p !== S.page) { S.page = p; loadItems(); } });
      PD.on(R, "click", "[data-per]", (e, el) => {
        const n = Number(el.dataset.per); if (n === S.per) return;
        S.page = Math.floor(S.page * S.per / n); S.per = n;  // the first decomp in view stays in view
        try { localStorage.setItem("pd-decomps-per", String(n)); } catch (err) { /* this session only */ }
        loadItems();
      });
      document.addEventListener("paste", e => {
        if (!R.isConnected || R.hidden) return;
        const f = [...(e.clipboardData ? e.clipboardData.files : [])].find(x => x.type.startsWith("image/"));
        if (f) fromFile(f);
      });
      renderZone(); renderItems();
    },
    async show() {
      // SEND IS ALWAYS ON: the engine lands it in every inbox (the inbox tag, else Quick sheets), or says why not
      loadItems();
    },
  });
})();
