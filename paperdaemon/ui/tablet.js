"use strict";
/* Mirror and False Mirror: the library as the tablet shows it. My files at the root, the breadcrumb of the open folder,
   its folders, then its notebooks and documents as covers. A notebook opens in a viewer the height of the window, one
   page at a time.

   One screen, made twice: MIRROR over the tablet's library (its pages edited in the page editor and written in place;
   nothing else changed there: tags shown, never changed), and FALSE MIRROR over
   the false mirror's (its requests go to /fm/..., which the engine passes to the false mirror's own engine). Only the
   false mirror has the making and changing: New notebook, New folder and Import in the head; a long press selects a
   notebook or folder and a menu slides down over the top of the screen with Export, Move, Tags and Delete; the
   viewer adds pages, edits a page's tags, and opens each page in the page editor. */
(() => {
  const { $, esc } = PD;

  const ICON = {
    pages: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="1.5" width="5.5" height="5.5"/><rect x="9" y="1.5" width="5.5" height="5.5"/><rect x="1.5" y="9" width="5.5" height="5.5"/><rect x="9" y="9" width="5.5" height="5.5"/></svg>',
    chapters: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="2.5" cy="3.5" r="1.2"/><circle cx="2.5" cy="8" r="1.2"/><circle cx="2.5" cy="12.5" r="1.2"/><path d="M6 3.5h8.5M6 8h8.5M6 12.5h8.5"/></svg>',
    tag: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 2h5.8l6.4 6.5-5.7 5.7L2 7.8z"/><circle cx="5" cy="5" r="1"/></svg>',
    add: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5v11M2.5 8h11"/></svg>',
    settings: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="2.1"/><circle cx="8" cy="8" r="4.6"/>' +
      '<path d="M8 1.2v2.2M8 12.6v2.2M1.2 8h2.2M12.6 8h2.2M3.2 3.2l1.5 1.5M11.3 11.3l1.5 1.5M3.2 12.8l1.5-1.5M11.3 4.7l1.5-1.5"/></svg>',
    newpage: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 1.5h6l3 3v10h-9z"/><path d="M9.5 1.5v3h3"/><path d="M8 7.5v5M5.5 10h5"/></svg>',
    prev: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3L5 8l5 5"/></svg>',
    next: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3l5 5-5 5"/></svg>',
  };
  // a folder's own tags, as the tablet tags it: an icon on the folder, and pills after its name in the path
  // a shopping tag, as the tablet draws one: square corner at the top left with the hole in it, the point at the bottom right
  const tagged = tags => '<svg class="tagged" viewBox="0 0 24 24" role="img" aria-label="' + esc(tags.join(", ")) + '"><title>' +
    esc(tags.join(", ")) + '</title><path d="M3.5 3.5h8.7l9.6 9.8-8.5 8.5-9.8-9.8z"/><circle cx="8" cy="8" r="1.5"/></svg>';
  const pills = tags => (tags || []).length ? '<span class="crumb-tags">' + tags.map(t => '<span class="chip">' + esc(t) + "</span>").join("") + "</span>" : "";

  function library(id, { label, base, fm }) {
    let R = null, seen = null;
    const S = { list: null, err: "", at: "", doc: null, page: 1, view: "page", tags: null, chapters: null, hist: [1], hpos: 0,
                picked: null, held: false, pp: [], ppHeld: false };
    const api = (m, p, b) => PD.api(m, base + p, b);
    const byId = x => (S.list || []).find(d => d.id === x);
    const VIEWER = id + "-viewer";
    // THE FOLDER SHOWN IS REMEMBERED, this screen's own, and opened again when the window starts with no address
    const AT = "pd-last-at:" + id;
    const remember = () => { try { localStorage.setItem(AT, S.at || ""); } catch (e) { /* kept for this run only */ } };
    const lastAt = () => { try { return localStorage.getItem(AT) || ""; } catch (e) { return ""; } };

    function path(x) {
      const out = [];
      for (let d = byId(x), n = 0; d && n < 20; d = byId(d.parent), n++) out.unshift(d);
      return out;
    }

    /** Where the reader is: a book's share read (its last open page of its pages), a PDF's or a notebook's page. */
    function where(b) {
      const n = b.pages || 0, at = b.at_page || 1;
      if (!n) return "";
      if (b.kind === "epub") return PD.t("tablet.read", { pct: n > 1 ? Math.round(100 * (at - 1) / (n - 1)) : 100 });
      return PD.t("tablet.page_of", { page: PD.n(at), pages: PD.n(n) });
    }

    function cover(img) {
      return PD.loadThumb(img, base + "/library/" + img.dataset.id + "/cover.png",
                          { tries: 4, giveUp: () => { const c = img.closest(".doc-card"); if (c) c.classList.add("nocover"); } });
    }

    function paint() {
      const box = $("#" + id + "-files", R); if (!box) return;
      if (S.err) { box.innerHTML = '<p class="msg err">' + esc(S.err) + "</p>"; return; }
      if (!S.list) { box.innerHTML = '<p class="sub">' + esc(PD.t("common.reading")) + "</p>"; return; }
      const crumbs = [{ id: "", name: PD.t("tablet.my_files") }].concat(path(S.at));
      const here = S.list.filter(x => x.parent === S.at && x.parent !== "trash");
      const folders = here.filter(x => x.type === "folder"), docs = here.filter(x => x.type === "document");
      const on = x => (S.picked || []).includes(x) ? " picked" : "";
      box.innerHTML =
        '<nav class="crumbs" aria-label="' + esc(PD.t("tablet.folder")) + '">' + crumbs.map((c, i) => (i === crumbs.length - 1
          ? '<span aria-current="page">' + esc(c.name) + "</span>"
          : '<button type="button" class="link-btn crumb" data-at="' + esc(c.id) + '">' + esc(c.name) + "</button>") + pills(c.tags)).join('<span class="sep">›</span>') + "</nav>" +
        (folders.length ? '<div class="folders">' + folders.map(f =>
          '<button type="button" class="folder' + on(f.id) + '" data-at="' + esc(f.id) + '" data-item="' + esc(f.id) + '"><svg viewBox="0 0 24 20" aria-hidden="true"><path d="M1 3a2 2 0 0 1 2-2h6l2 3h10a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2z"/></svg>' +
          "<span>" + esc(f.name) + "</span>" + ((f.tags || []).length ? tagged(f.tags) : "") +
          "</button>").join("") + "</div>" : "") +
        (docs.length ? '<div class="doc-grid">' + docs.map(b =>
          '<button type="button" class="doc-card' + on(b.id) + '" data-open="' + esc(b.id) + '" data-item="' + esc(b.id) + '"><span class="cover"><img alt="" data-id="' + esc(b.id) + '">' +
          ((b.tags || []).length ? '<span class="cover-tags">' + b.tags.map(t => '<span class="chip">' + esc(t) + "</span>").join("") + "</span>" : "") + "</span>" +
          '<span class="name">' + esc(b.name) + '</span><span class="meta">' + esc(where(b)) + "</span></button>").join("") + "</div>" : "") +
        (!folders.length && !docs.length ? '<p class="sub">' + esc(PD.t(!fm && PD.mirrorState(PD.status).building ? "tablet.arriving" : "tablet.empty")) + "</p>" : "");
      if (seen) seen.disconnect();
      seen = new IntersectionObserver(es => es.forEach(x => { if (x.isIntersecting) { seen.unobserve(x.target); cover(x.target); } }), { rootMargin: "400px" });
      box.querySelectorAll("img[data-id]").forEach(img => seen.observe(img));
      paintProgress();                                 // the covers were drawn anew: the job's bar goes back on its own
      paintSync();                                     // ... and a sync's
    }

    // ---- the viewer, as the tablet has it: one page at a time, a grid of all the pages, the chapters

    const pageCount = () => Math.max(1, (S.doc && S.doc.pages) || 1);

    function paintBar() {
      const dlg = $("#" + VIEWER); if (!dlg || !S.doc) return;
      paintPagePick();                    // the pages' bar only over the grid with pages chosen: never left behind
      const n = pageCount();
      $(".viewer-title", dlg).textContent = S.doc.name;
      // THE BAR, LAID OUT AS THE TABLET'S TOOLBAR. A page: on the left the page editor's tools in the false mirror (pen,
      // pen, text, eraser, layers; the editor sends them; selection and capture will go between eraser and layers), then on the right
      // the tag, the page grid and the page arrows. The grid: on the right the chapters, the grid and Go to page. The
      // page's tags are in the tag button's menu, not in the bar.
      $(".viewer-tags", dlg).innerHTML = "";
      const tool = (v, l) => '<button type="button" class="icon-btn" data-v="' + v + '" aria-pressed="' + (S.view === v) + '" title="' + l + '" aria-label="' + l + '">' + ICON[v] + "</button>";
      const edHere = ["notebook", "pdf", "epub"].includes(S.doc.kind) && S.view === "page";
      $(".viewer-tools", dlg).innerHTML = edHere ? '<span class="ed-tools">' + (S.edHtml || "") + "</span>" : "";
      $(".viewer-nav", dlg).innerHTML = S.view === "page"
        ? '<button type="button" class="icon-btn" data-v="tagpop" aria-pressed="' + !!S.tagPop + '" title="' + esc(PD.t("fm.tags")) +
            '" aria-label="' + esc(PD.t("fm.tags")) + '">' + ICON.tag + "</button>" + tool("pages", PD.t("viewer.pages")) +
          // the arrows the same buttons as the tag, the grid and the new page beside them
          '<button type="button" class="icon-btn" data-v="prev" title="' + esc(PD.t("viewer.prev")) + '" aria-label="' + esc(PD.t("viewer.prev")) + '"' +
            (S.page <= 1 ? " disabled" : "") + ">" + ICON.prev + "</button>" +
          '<span class="viewer-count">' + esc(PD.t("tablet.page_of", { page: S.page, pages: n })) + "</span>" +
          '<button type="button" class="icon-btn" data-v="next" title="' + esc(PD.t("viewer.next")) + '" aria-label="' + esc(PD.t("viewer.next")) + '"' +
            (S.page >= n ? " disabled" : "") + ">" + ICON.next + "</button>" +
          (fm && S.doc.kind === "notebook" ? '<button type="button" class="icon-btn" data-v="newpage" title="' + esc(PD.t("fm.new_page")) + '" aria-label="' +
            esc(PD.t("fm.new_page")) + '">' + ICON.newpage + "</button>" : "")
        : ((S.chapters || []).length ? tool("chapters", PD.t("viewer.chapters")) : "") + tool("pages", PD.t("viewer.pages")) +
          '<label class="viewer-goto">' + esc(PD.t("viewer.goto", { last: PD.n(n) })) +
          '<input class="field num" type="number" data-goto min="1" max="' + n + '" step="1" value="' + S.page + '" aria-label="' +
          esc(PD.t("viewer.goto_aria", { last: n })) + '"></label>';
    }

    function goTyped(input) {
      const n = pageCount(), k = Number(input.value);
      if (Number.isInteger(k) && k >= 1 && k <= n) { go(k); return; }
      input.setAttribute("aria-invalid", "true");
      input.select();
    }

    // THE PAGE OPEN is the page the document opens at next, and the one its cover shows when the tablet's setting says
    // the page last open: told to the engine as it opens (kept in PaperDaemon's own files, not the document's)
    const opened = (doc, page) => PD.safe(api("POST", "/library/" + encodeURIComponent(doc) + "/opened?page=" + page));
    function seenPage() {
      const now = S.view === "page" && S.doc ? S.doc.id + "|" + S.page : null;
      if (now === S.seen) return;
      if (now) S.told = opened(S.doc.id, S.page);
      S.seen = now;
    }
    async function paintBody() {
      const dlg = $("#" + VIEWER); if (!dlg || !S.doc) return;
      paintMakeUp({ show: false });                          // (a page left: its selection's icons with it)
      seenPage();
      const body = $(".viewer-page", dlg), n = pageCount();
      body.scrollTop = 0;
      if (S.view === "pages") {
        body.className = "viewer-page grid";
        body.innerHTML = Array.from({ length: n }, (_, i) => '<button type="button" class="thumb' + (i + 1 === S.page ? " here" : "") + '" data-go="' + (i + 1) + '">' +
          '<span class="cover"><img alt="" data-thumb="' + (i + 1) + '"></span><span class="meta">' + (i + 1) + "</span></button>").join("");
        paintPagePick();
        const d = S.doc.id, io = new IntersectionObserver(es => es.forEach(x => {
          if (!x.isIntersecting) return;
          io.unobserve(x.target);
          PD.loadThumb(x.target, base + "/library/" + d + "/thumb/" + x.target.dataset.thumb + ".png",
                       { stale: () => !S.doc || S.doc.id !== d || S.view !== "pages" });
        }), { root: body, rootMargin: "600px" });
        body.querySelectorAll("img[data-thumb]").forEach(img => io.observe(img));
        const here = body.querySelector(".thumb.here"); if (here) here.scrollIntoView({ block: "center" });
        return;
      }
      if (S.view === "chapters") {
        body.className = "viewer-page chapters";
        if (S.chapters === null) { body.innerHTML = '<p class="sub viewer-wait">' + esc(PD.t("viewer.reading_chapters")) + "</p>"; return; }
        body.innerHTML = '<ol class="chapter-list">' + (S.chapters || []).map(c =>
          '<li style="padding-left: ' + (c.level * 20) + 'px"><button type="button" class="chapter" data-go="' + c.page + '"><span>' + esc(c.title) + '</span><span class="meta">' + c.page + "</span></button></li>").join("") + "</ol>";
        return;
      }
      // A PAGE OPENS IN THE PAGE EDITOR (editor.html, in a frame: it draws with PaperDaemon's own renderer, on the card),
      // with its tools in either library: the False Mirror's saved as it goes, the Mirror's (the tablet's own pages)
      // written in place when saved (Ctrl+S, the document closed, the page left with changes) and sent to the tablet
      body.className = "viewer-page editing";
      // (a Mirror page only to look at unless Edit the Mirror is on in Settings)
      const look = !fm && !PD.getK(PD.settings || {}, "mirror.edit");
      body.innerHTML = '<iframe class="page-editor" allow="clipboard-read; clipboard-write" title="' + esc(PD.t("viewer.page", { n: S.page })) + '" src="/ui/editor.html#doc=' +
        encodeURIComponent(S.doc.id) + "&page=" + S.page + "&base=" + encodeURIComponent(base) + (look ? "&view=1" : "") + '"></iframe>';
      const efr = $("iframe.page-editor", body);
      efr.addEventListener("load", () => efr.focus());        // the keys go to the page from the start, no click first
    }

    // THE VIEWER IS AS TALL AS THE PORT. The port is the Paper Pro's screen, 3:4, as large as the window allows (by its
    // height or its width, whichever runs out first, within 92% x 94% of the window, whatever the UI zoom); the viewer is
    // the port and its title and bar, never taller, and at least wide enough for the bar.
    // the width the bar's own content takes in one row, measured at its natural width (its tools stretch to fill the
    // viewer, so its present width says nothing; this way the viewer can narrow again)
    function barNeeds(dlg) {
      const bar = $(".viewer-bar", dlg); if (!bar) return 0;
      const was = bar.style.width;
      bar.style.width = "max-content";
      const w = bar.offsetWidth;
      bar.style.width = was;
      return w;
    }
    function sizeViewer() {
      const dlg = $("#" + VIEWER); if (!dlg || !dlg.open) return;
      const body = $(".viewer-page", dlg); if (!body) return;
      const z = PD.uiZoom || 1, availW = window.innerWidth * 0.92 / z, availH = window.innerHeight * 0.94 / z;
      for (let pass = 0; pass < 2; pass++) {                  // the bar can wrap at a new width: measured again
        const chrome = dlg.offsetHeight - body.clientHeight, side = dlg.offsetWidth - body.clientWidth;
        const vh = Math.max(240, Math.min(availH - chrome, (availW - side) * 4 / 3)), vw = vh * 0.75;
        // AS WIDE AS ITS BAR NEEDS, the window allowing: the tools never push a scrollbar onto the viewer
        const need = barNeeds(dlg) + (dlg.offsetWidth - dlg.clientWidth);
        dlg.style.width = Math.min(availW, Math.max(vw + side, 560, need)) + "px";
        dlg.style.height = (chrome + vh) + "px";
      }
    }
    window.addEventListener("resize", sizeViewer);
    window.addEventListener("pd-zoom", sizeViewer);
    function wheelPage(e) {                                   // Ctrl + scroll outside the page never zooms the window
      if (e.ctrlKey) e.preventDefault();
    }

    // THE TAG BUTTON'S MENU, under it: the tags used before as pills (on the page: pressed), and in the false mirror a
    // field and Add for a new one; a pill there puts the tag on the page or takes it off. The Mirror only shows them.
    function paintTagPop() {
      const dlg = $("#" + VIEWER); if (!dlg) return;
      const efr = editorFrame();                                  // the page hears it too, so Esc there closes this first
      if (efr && efr.contentWindow) efr.contentWindow.postMessage({ pd: "viewer-menu", open: !!(S.tagPop && S.view === "page") }, location.origin);
      const old = $(".tag-pop", dlg); if (old) old.remove();
      if (!S.tagPop || S.view !== "page") return;
      const btn = $('[data-v="tagpop"]', dlg); if (!btn) return;
      const here = (S.tags && S.tags.page_tags && S.tags.page_tags[S.page - 1]) || [];
      // TAGS HAVE NO CASE: "Joi" and "joi" are one tag, one pill, spelled as the page (else the library) has it
      const used = new Map(here.map(t => [t.toLowerCase(), t]));
      const keep = t => { if (!used.has(t.toLowerCase())) used.set(t.toLowerCase(), t); };
      (S.list || []).forEach(d => (d.tags || []).forEach(keep));
      ((S.tags && S.tags.page_tags) || []).forEach(ts => (ts || []).forEach(keep));
      const all = [...used.values()].sort((a, b) => a.localeCompare(b));
      const pill = t => fm ? '<button type="button" class="chip tag-pill" data-tagtoggle="' + esc(t) + '" aria-pressed="' + hasTag(here, t) + '">' + esc(t) + "</button>"
                           : '<span class="chip">' + esc(t) + "</span>";
      const pop = document.createElement("div");
      pop.className = "tag-pop";
      pop.innerHTML = '<div class="tag-pills">' + (fm ? all : here).map(pill).join("") + "</div>" +
        (fm ? '<div class="tag-new"><input class="field" data-tag-add spellcheck="false" placeholder="' + esc(PD.t("fm.tag_add")) + '" aria-label="' +
              esc(PD.t("fm.tag_add")) + '"><button type="button" class="btn small" data-v="tagadd">' + esc(PD.t("fm.add")) + "</button></div>" : "");
      $(".viewer-bar", dlg).append(pop);
      // under the tag button, kept inside the bar: near the right edge it opens leftward
      const bar = $(".viewer-bar", dlg);
      pop.style.left = Math.max(8, Math.min(btn.offsetLeft, bar.clientWidth - pop.offsetWidth - 8)) + "px";
      const inp = $("[data-tag-add]", pop); if (inp) inp.focus();
    }
    function addTypedTag() {
      const inp = $("#" + VIEWER + " [data-tag-add]"); const typed = inp && inp.value.trim(); if (!typed) return;
      const t = knownSpelling(typed);
      pageTags(now => hasTag(now, t) ? now : now.concat([t])).then(paintTagPop);
    }
    // a tag compared as the tablet's tags are, without regard to case; one typed is spelled as it is already in use
    const hasTag = (list, t) => (list || []).some(x => x.toLowerCase() === String(t).toLowerCase());
    function knownSpelling(t) {
      const all = [];
      (S.list || []).forEach(d => (d.tags || []).forEach(x => all.push(x)));
      ((S.tags && S.tags.page_tags) || []).forEach(ts => (ts || []).forEach(x => all.push(x)));
      return all.find(x => x.toLowerCase() === t.toLowerCase()) || t;
    }
    // THE PAGE EDITOR'S TOOLS LIVE IN THE BAR: the editor (in its frame) sends its buttons, and a press here goes back
    // to it with where the button is, so its menu opens right under it
    const editorFrame = () => $("#" + VIEWER + " iframe.page-editor");
    window.addEventListener("message", e => {
      const d = e.data, fr = editorFrame();
      if (!d || !fr || e.source !== fr.contentWindow) return;
      if (d.pd === "editor-menu") { S.edMenu = !!d.open; return; }                       // a menu of the editor's is open
      if (d.pd === "viewer-menu-close") { S.tagPop = false; paintBar(); paintTagPop(); return; }   // Esc pressed in the page
      // the Mirror's view (the editor with view=1): a page's link followed, a page turned from the keys
      if (d.pd === "view-go") { go(Number(d.page)); return; }
      if (d.pd === "view-open") { PD.api("POST", "/open-link", { url: String(d.uri || "") }); return; }
      if (d.pd === "viewer-key") {                          // Ctrl+W, Ctrl+Tab pressed in the page
        const dlg = $("#" + VIEWER);
        if (d.key === "w" && dlg && dlg.open) dlg.close();
        else if (d.key === "Escape" && dlg && dlg.open) {   // Esc the page had no use for: the tags' menu first, then close
          if (S.tagPop) { S.tagPop = false; paintBar(); paintTagPop(); } else dlg.close();
        }
        else if (d.key === "Tab") cycleDoc(d.shiftKey ? -1 : 1);
        return;
      }
      if (d.pd === "view-key") {
        if (d.altKey && (d.key === "ArrowLeft" || d.key === "ArrowRight")) { walk(d.key === "ArrowLeft" ? -1 : 1); return; }
        go(S.page + (d.key === "ArrowRight" ? 1 : -1));
        return;
      }
      if (d.pd === "editor-sync") { syncBar(d); return; }   // a Mirror sync started, or ended
      if (d.pd === "editor-makeup") { paintMakeUp(d); return; }   // what a settled selection is made of, or none
      if (d.pd === "editor-save") {                         // a save that failed, said by the name (its reason on hover); the ?
        const f = $("#" + VIEWER + " .save-failed"); if (!f) return;   // beside it is the shortcuts' and nothing else
        f.hidden = d.state !== "error";
        if (d.state === "error") f.title = PD.t("viewer.notSaved", { why: d.why });
        return;
      }
      if (d.pd !== "editor-tools") return;
      S.edHtml = d.html;
      const span = $("#" + VIEWER + " .ed-tools"); if (span) span.innerHTML = d.html;
    });
    function pressEditorTool(b) {
      const fr = editorFrame(); if (!fr || !fr.contentWindow) return;
      const r = fr.getBoundingClientRect(), k = r.width ? fr.contentWindow.innerWidth / r.width : 1;
      fr.contentWindow.postMessage({ pd: "editor-press", tool: b.dataset.tool, x: (b.getBoundingClientRect().left - r.left) * k }, location.origin);
      fr.focus();
    }
    // TYPING NEEDS NO CLICK ON THE PAGE: a key pressed anywhere in the viewer outside a field (after a press in the bar, say)
    // goes to the editor, as if pressed there, and the keys follow it there. Esc stays the viewer's.
    document.addEventListener("keydown", e => {
      const fr = editorFrame(), dlg = $("#" + VIEWER);
      if (!fr || !fr.contentWindow || !dlg || !dlg.open || e.key === "Escape" || e.defaultPrevented) return;
      if (document.querySelector("#keys-sheet[open]")) return;     // the shortcuts sheet is over the page: its keys are its own
      const t = e.target;
      if (t && t.closest && t.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "Tab" || e.getModifierState(e.key)) return;     // Tab, and a modifier pressed on its own, stay here
      e.preventDefault();
      fr.contentWindow.postMessage({ pd: "editor-key", key: e.key, code: e.code, ctrlKey: e.ctrlKey, shiftKey: e.shiftKey,
                                     altKey: e.altKey, metaKey: e.metaKey }, location.origin);
      fr.focus();
    });

    // A JOB'S PROGRESS, as the host reports it (GET /progress): a bar over the bottom edge of the document's cover, and
    // along the bottom of the viewer when that document is open; no count until the model's plan is in
    function progressBar(p) {
      const known = p && p.total;
      return '<span class="job-bar' + (known ? "" : " busy") + '" role="progressbar"' +
        (known ? ' aria-valuemin="0" aria-valuemax="' + p.total + '" aria-valuenow="' + p.done + '"' : "") +
        '><i style="width:' + (known ? Math.max(4, 100 * p.done / p.total) : 30) + '%"></i></span>';
    }
    // A BAR THAT IS THERE IS CHANGED IN PLACE, never drawn anew: a new element each poll started its animation over
    // every second (it looked stuck) and could not slide its width from the last value
    function setBar(holder, old, p) {
      if (!old) { holder.insertAdjacentHTML("beforeend", progressBar(p)); return; }
      const known = !!(p && p.total);
      old.classList.toggle("busy", !known);
      if (known) {
        old.setAttribute("aria-valuemin", "0"); old.setAttribute("aria-valuemax", String(p.total)); old.setAttribute("aria-valuenow", String(p.done));
      } else ["aria-valuemin", "aria-valuemax", "aria-valuenow"].forEach(a => old.removeAttribute(a));
      const w = (known ? Math.max(4, 100 * p.done / p.total) : 30) + "%";
      const i = old.querySelector("i"); if (i && i.style.width !== w) i.style.width = w;
    }
    function paintProgress() {
      if (!R) return;
      const p = S.progress;
      R.querySelectorAll(".cover .job-bar").forEach(b => { if (!p || b.closest(".doc-card").dataset.open !== p.doc) b.remove(); });
      if (p) {
        const card = R.querySelector('.doc-card[data-open="' + p.doc + '"] .cover');
        if (card) setBar(card, card.querySelector(".job-bar"), p);
      }
      const dlg = $("#" + VIEWER);
      if (dlg) {
        const old = dlg.querySelector(":scope > .job-bar");
        if (p && dlg.open && S.doc && S.doc.id === p.doc) setBar(dlg, old, p);
        else if (old) old.remove();
      }
    }
    // THE MIRROR'S SYNC (a document's edits going up to the tablet: Ctrl+S, the document closed), as the engine reports
    // it (GET /library/<doc>/sync): a thin bar under the viewer's bar while the document is open, along the top of its
    // cover once it is closed. It fills by the push's requests to the cloud and is gone a moment after it is through;
    // a sync that failed leaves no bar (its reason is by the document's name)
    function syncBar(d) {
      if (d.state === "start") {
        if (!S.doc) return;
        clearInterval(S.syncPoll);
        const s = S.sync = { doc: S.doc.id, frac: 0, busy: true, t0: Date.now() };
        paintSync();
        S.syncPoll = setInterval(async () => {
          if (S.sync !== s) { clearInterval(S.syncPoll); return; }
          if (Date.now() - s.t0 > 120000) { syncOver(s, false); return; }
          const [p] = await PD.safe(api("GET", "/library/" + encodeURIComponent(s.doc) + "/sync"));
          if (S.sync !== s || !p) return;
          if (p.state === "sending" && p.steps) { s.busy = false; s.frac = Math.max(s.frac, p.done / p.steps); s.seen = true; paintSync(); }
          else if (s.seen && p.state !== "sending") syncOver(s, p.state === "sent");   // (its editor gone before it said)
        }, 250);
      } else if (S.sync) syncOver(S.sync, !!d.ok);
    }
    function syncOver(s, ok) {
      if (S.sync !== s) return;
      clearInterval(S.syncPoll);
      if (!ok) { S.sync = null; paintSync(); return; }
      s.busy = false; s.frac = 1; paintSync();
      setTimeout(() => { if (S.sync === s) { S.sync = null; paintSync(); } }, 700);
    }
    function paintSync() {
      const s = S.sync, dlg = $("#" + VIEWER);
      const open = !!(s && dlg && dlg.open && S.doc && S.doc.id === s.doc);
      const places = [];
      const vb = dlg && $(".viewer-bar", dlg);
      if (vb) places.push([vb, open]);
      if (R) R.querySelectorAll(".doc-card .cover").forEach(c => places.push([c, !!s && !open && c.closest(".doc-card").dataset.open === s.doc]));
      for (const [at, want] of places) {
        let bar = at.querySelector(":scope > .sync-bar");
        if (!want) { if (bar) bar.remove(); continue; }
        if (!bar) {
          at.insertAdjacentHTML("beforeend", '<span class="sync-bar" role="progressbar" aria-label="' + esc(PD.t("keys.sync")) + '"><i></i></span>');
          bar = at.querySelector(":scope > .sync-bar");
        }
        bar.classList.toggle("busy", s.busy);
        const w = (s.busy ? 30 : Math.max(4, 100 * s.frac)) + "%", i = bar.querySelector("i");
        if (i.style.width !== w) i.style.width = w;
      }
    }
    // THE SELECTION'S MAKE-UP, as the page editor tells it: brush icons (or color swatches) with their counts, to the
    // right of the selection, drawn here over the viewer so they reach past the editor's frame; a press keeps only those
    // strokes selected (the editor does it)
    function paintMakeUp(d) {
      const dlg = $("#" + VIEWER), fr = editorFrame();
      let box = dlg && dlg.querySelector(":scope > .sel-makeup");
      if (!d.show || !dlg || !dlg.open || !fr) { if (box) { box.classList.remove("on"); box.hidden = true; } return; }
      if (!box) {
        dlg.insertAdjacentHTML("beforeend", '<div class="sel-makeup" hidden></div>');
        box = dlg.querySelector(":scope > .sel-makeup");
        box.addEventListener("pointerdown", e => e.preventDefault());   // (the keys stay the page's)
        box.addEventListener("click", e => {
          const b = e.target.closest("[data-row]"), f = editorFrame();
          if (b && f && f.contentWindow) f.contentWindow.postMessage({ pd: "editor-makeup-pick", row: Number(b.dataset.row) }, location.origin);
        });
      }
      if (box.dataset.key !== String(d.key)) {               // a new selection: its icons, slid in anew
        box.dataset.key = String(d.key);
        box.innerHTML = d.rows.map(r => '<button type="button" tabindex="-1" data-row="' + r.row + '" title="' + esc(r.title) +
          '"><span class="mi">' + r.icon + '</span><span class="mn">' + esc(r.label) + "</span></button>").join("");
        box.classList.remove("on"); box.hidden = true;
      }
      const at = fr.getBoundingClientRect();
      box.style.left = Math.round(at.left + d.x) + "px"; box.style.top = Math.round(at.top + d.y) + "px";
      if (box.hidden) { box.hidden = false; requestAnimationFrame(() => { if (!box.hidden) box.classList.add("on"); }); }
    }
    async function loadProgress() {
      const [p] = await PD.safe(api("GET", "/progress"));
      S.progress = p && p.doc ? p : null;
      paintProgress();
    }

    // THE PAGES OPENED, IN OPENING ORDER: the mouse's back and forward buttons (and Alt+arrows) walk this list, like a
    // browser's history, not the page order. Opening a page after going back drops the pages ahead, as a browser does.
    function go(n, walking) {
      const page = Math.min(Math.max(1, n), pageCount());
      if (!walking && page !== S.page) {
        S.hist = S.hist.slice(0, S.hpos + 1).concat([page]);
        S.hpos = S.hist.length - 1;
      }
      S.page = page;
      S.view = "page";
      S.tagPop = false;
      paintBar(); paintBody(); paintTagPop();
    }

    // the next (or previous) document in the open one's folder: this one closed first (it saves and syncs as a close
    // does), then that one opened
    function cycleDoc(step) {
      const dlg = $("#" + VIEWER);
      if (!dlg || !dlg.open || !S.doc) return;
      const here = (S.list || []).filter(x => x.type === "document" && x.parent === S.doc.parent);
      const i = here.findIndex(x => x.id === S.doc.id);
      if (here.length < 2 || i < 0) return;
      const next = here[(i + step + here.length) % here.length].id;
      dlg.close();
      setTimeout(() => openDoc(next), 250);
    }
    function walk(step) {
      const dlg = $("#" + VIEWER);
      if (!dlg || !dlg.open) return false;
      // THE PAGES' HISTORY ONLY: at either end nothing happens (the viewer stays open, the app behind it stays put)
      const at = S.hpos + step;
      if (at < 0 || at >= S.hist.length) return true;
      S.hpos = at;
      go(S.hist[at], true);
      return true;
    }

    async function pageTags(change) {
      const now = ((S.tags && S.tags.page_tags && S.tags.page_tags[S.page - 1]) || []).slice();
      const next = change(now);
      const [, e] = await PD.safe(api("PUT", "/library/" + S.doc.id + "/page/" + S.page + "/tags", { tags: next }));
      if (e) return;
      const [d] = await PD.safe(api("GET", "/library/" + S.doc.id));
      if (d) { S.tags = d; paintBar(); paintTagPop(); }
    }

    function openDoc(x) {                                     // at the page it was last open on, as the tablet opens it
      PD.holdCard();                                          // (the shaders compiled stay compiled from page to page)
      // (the window on another card than Settings chose: the document opens in a fresh one on that card, PD.moveWindow)
      if (PD.windowStale && !PD.moved) { PD.moveWindow(id, S.at, x).then(moving => { if (!moving) openDoc(x); }); return; }
      S.doc = byId(x); S.page = Math.min(Math.max(1, (S.doc && S.doc.at_page) || 1), pageCount());
      S.tags = null; S.chapters = null; S.hist = [S.page]; S.hpos = 0; S.pp = [];
      S.view = PD.firstTab === "pages" || PD.firstTab === "chapters" ? PD.firstTab : "page"; PD.firstTab = "";
      if (S.pmove && S.pmove.out) { S.pmove.out = false; S.pmove.at = 0; S.view = "pages"; unpick(); }   // where they go: its pages
      let dlg = $("#" + VIEWER);
      if (!dlg) {
        dlg = document.createElement("dialog");
        dlg.id = VIEWER; dlg.className = "viewer";
        dlg.innerHTML = '<div class="viewer-head"><span class="viewer-name"><button type="button" class="viewer-title" data-v="docsheet"></button><button type="button" class="keys-q" data-v="keys" title="' +
          esc(PD.t("keys.open")) + '" aria-label="' + esc(PD.t("keys.open")) + '">?</button><span class="save-failed" role="status" hidden>' +
          esc(PD.t("viewer.notSavedShort")) + '</span></span><button type="button" class="link-btn" data-v="close">' + esc(PD.t("common.close")) + "</button></div>" +
          '<div class="viewer-bar"><span class="viewer-tools"></span><span class="viewer-tags"></span><span class="viewer-nav"></span>' +
          '<div class="select-bar page-pick" role="toolbar" hidden></div></div>' +
          '<div class="viewer-page" tabindex="-1" autofocus></div>';
        dlg.addEventListener("click", async e => {
          const et = e.target.closest(".ed-tools [data-tool]");
          if (et) { pressEditorTool(et); return; }
          const efr = editorFrame();                      // a press anywhere else closes the editor's open menu
          if (efr && efr.contentWindow) efr.contentWindow.postMessage({ pd: "editor-close" }, location.origin);
          if (S.tagPop && !e.target.closest(".tag-pop") && !e.target.closest('[data-v="tagpop"]')) { S.tagPop = false; paintBar(); paintTagPop(); }
          const tg = e.target.closest("[data-tagtoggle]");
          if (tg) { const t = tg.dataset.tagtoggle; pageTags(now => hasTag(now, t) ? now.filter(x => x.toLowerCase() !== t.toLowerCase()) : now.concat([t])); return; }
          const pa = e.target.closest("[data-pp]");
          if (pa) { pagePickAct(pa.dataset.pp); return; }
          const g = e.target.closest("[data-go]");
          if (g && g.matches(".thumb") && gridHere()) {
            if (S.ppHeld) { S.ppHeld = false; return; }              // the click that ends a long press
            if (S.pmove) { moveTarget(Number(g.dataset.go)); return; }
            if (S.pp.length) { pickPage(Number(g.dataset.go)); return; }
          }
          if (g) { go(Number(g.dataset.go)); return; }
          const x = e.target.closest("[data-untag]");
          if (x) { pageTags(now => now.filter(t => t !== x.dataset.untag)); return; }
          const b = e.target.closest("[data-v]");
          if (!b) { if (e.target === dlg) dlg.close(); return; }
          const v = b.dataset.v;
          if (v === "close") dlg.close();
          else if (v === "prev" || v === "next") go(S.page + (v === "next" ? 1 : -1));
          else if (v === "tagpop") { S.tagPop = !S.tagPop; paintBar(); paintTagPop(); }
          else if (v === "keys") PD.openShortcuts(!!editorFrame());
          else if (v === "docsheet") docSheet();
          else if (v === "tagadd") addTypedTag();
          else if (v === "newpage") {
            const [got] = await PD.safe(api("POST", "/library/" + S.doc.id + "/pages", { after: S.page }));
            if (got) { S.doc.pages = (S.doc.pages || 1) + 1; go(got.page); }
          }
          else if (v === "pages" || v === "chapters") { S.view = S.view === v ? "page" : v; S.pp = []; paintPagePick(); paintBar(); paintBody(); }
        });
        // A LONG PRESS OR A RIGHT-CLICK ON A PAGE IN THE GRID selects it (the False Mirror's own notebooks)
        let ppTimer = 0;
        dlg.addEventListener("pointerdown", e => {
          S.ppHeld = false;
          const t = e.target.closest(".thumb[data-go]"); if (!t || e.button !== 0 || !gridHere()) return;
          clearTimeout(ppTimer);
          ppTimer = setTimeout(() => { S.ppHeld = true; pickPage(Number(t.dataset.go)); }, 500);
        });
        ["pointerup", "pointerleave", "pointercancel"].forEach(t => dlg.addEventListener(t, () => clearTimeout(ppTimer)));
        dlg.addEventListener("contextmenu", e => {
          const t = e.target.closest(".thumb[data-go]"); if (!t || !gridHere()) return;
          e.preventDefault(); clearTimeout(ppTimer); pickPage(Number(t.dataset.go));
        });
        dlg.addEventListener("wheel", wheelPage, { passive: false });
        new ResizeObserver(sizeViewer).observe($(".viewer-bar", dlg));    // a bar that wraps makes the viewer taller
        dlg.addEventListener("keydown", e => {
          if (e.target.matches("[data-tag-add]")) {
            if (e.key === "Enter") { e.preventDefault(); addTypedTag(); }
            if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); S.tagPop = false; paintBar(); paintTagPop(); }
            return;
          }
          if (e.target.matches("[data-goto]")) {
            if (e.key === "Enter") { e.preventDefault(); goTyped(e.target); }
            else e.target.removeAttribute("aria-invalid");
            return;
          }
          if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
            e.preventDefault(); walk(e.key === "ArrowLeft" ? -1 : 1); return;
          }
          // (on a page the keys go on to the editor, which turns the page, moves what is selected, or scrolls)
        });
        // back from the editor: the covers and the page pictures show what was drawn
        // CLOSING A FALSE-MIRROR DOCUMENT SYNCS it, as on the tablet: the page editor saves and tells the daemon to look
        // ESC CLOSES WHAT IS OPEN FIRST: the tags' menu, then the editor's menus, and only then the viewer
        // ESC IN THE GRID steps back one thing at a time: the page chosen to move next to, the move, the pages chosen, and
        // then out of the grid to the page (the chapters too) -- the viewer closes only from the page
        dlg.addEventListener("cancel", e => {
          if (S.pmove && gridHere()) { e.preventDefault(); if (S.pmove.at) S.pmove.at = 0; else S.pmove = null; paintPagePick(); return; }
          if (S.pp.length && gridHere()) { e.preventDefault(); S.pp = []; paintPagePick(); return; }
          if (S.view !== "page" && !S.tagPop) { e.preventDefault(); S.view = "page"; paintBar(); paintBody(); return; }
          if (S.tagPop) { e.preventDefault(); S.tagPop = false; paintBar(); paintTagPop(); return; }
          const fr = editorFrame();
          if (S.edMenu && fr && fr.contentWindow) { e.preventDefault(); S.edMenu = false; fr.contentWindow.postMessage({ pd: "editor-close" }, location.origin); }
        });
        dlg.addEventListener("close", () => {
          S.pp = []; if (S.pmove && !S.pmove.out) S.pmove = null;   // closing lets the chosen pages go (but not pages moving out)
          paintPagePick();
          S.seen = null;
          paintMakeUp({ show: false });
          if (!fm) {                                         // THE MIRROR: the page written if changed, then the document sent to the tablet
            const fr = editorFrame();
            if (fr && fr.contentWindow) fr.contentWindow.postMessage({ pd: "editor-commit" }, location.origin);
            else if (S.doc) PD.safe(api("POST", "/library/" + S.doc.id + "/push"));
            Promise.resolve(S.told).then(load);              // its card: the page it opens at next, its cover
            return;
          }
          const fr = editorFrame();
          if (fr && fr.contentWindow) fr.contentWindow.postMessage({ pd: "editor-commit" }, location.origin);
          else PD.safe(api("POST", "/library/sync"));
          load();
        });
        document.body.append(dlg);
        // the mouse's back (button 3) and forward (button 4) buttons, while a notebook is open: its pages, not the
        // app's screens. The press and the release are both taken, or the window would also go back a screen.
        // CTRL+W CLOSES THE NOTEBOOK; CTRL+TAB AND CTRL+SHIFT+TAB GO TO THE NEXT AND THE PREVIOUS ONE in its folder (as
        // the library lists them, round from the last to the first), wherever the keys are while it is open
        window.addEventListener("keydown", e => {
          if (!dlg.open || !(e.ctrlKey || e.metaKey) || e.altKey) return;
          if (e.key === "w" || e.key === "W") { e.preventDefault(); e.stopImmediatePropagation(); dlg.close(); }
          else if (e.key === "Tab") { e.preventDefault(); e.stopImmediatePropagation(); cycleDoc(e.shiftKey ? -1 : 1); }
        }, true);
        // and Alt+Left and Alt+Right wherever the keys are while it is open: the same walk, never the app's Back
        window.addEventListener("keydown", e => {
          if (!dlg.open || !e.altKey || e.ctrlKey || (e.key !== "ArrowLeft" && e.key !== "ArrowRight") || dlg.contains(e.target)) return;
          e.preventDefault(); e.stopImmediatePropagation(); walk(e.key === "ArrowLeft" ? -1 : 1);
        }, true);
        ["mousedown", "mouseup", "auxclick"].forEach(type => window.addEventListener(type, e => {
          if ((e.button !== 3 && e.button !== 4) || !dlg.open) return;
          e.preventDefault(); e.stopImmediatePropagation();
          if (type === "mouseup") walk(e.button === 3 ? -1 : 1);
        }, true));
      }
      dlg.showModal();
      paintBar(); paintBody(); sizeViewer();
      PD.safe(api("GET", "/library/" + x)).then(([d]) => { if (S.doc && S.doc.id === x) { S.tags = d; paintBar(); } });
      PD.safe(api("GET", "/library/" + x + "/chapters")).then(([c]) => {
        if (!S.doc || S.doc.id !== x) return;
        S.chapters = Array.isArray(c) ? c : [];
        paintBar();
        if (S.view === "chapters") paintBody();
      });
    }

    // ---- PAGES CHOSEN IN THE GRID, as the tablet's page overview chooses them: a long press or a right-click on a page
    // selects it, and while any is selected a click adds a page or takes it away. A strip at the top of the grid says
    // how many and does it to all of them: Select all, Duplicate, Move, Tags, Delete. S.pp: the page numbers chosen.
    const gridHere = () => fm && S.doc && S.view === "pages";
    function pickPage(n) {
      S.pp = S.pp.includes(n) ? S.pp.filter(x => x !== n) : S.pp.concat([n]).sort((a, b) => a - b);
      paintPagePick();
    }
    // MOVING PAGES, AS THE TABLET DOES: Move turns the bar into where to. A page chosen in the grid, and the bar offers
    // Move before and Move after it; Move out leaves the notebook for the library, where a notebook opened shows its
    // grid to choose in the same way. S.pmove: {doc, name, pages, at (the page chosen, 0 none), out (in the library)}.
    const PMOVE_ICON = {
      before: '<svg viewBox="0 0 20 16" aria-hidden="true"><rect x="10.5" y="1.5" width="8" height="13" rx="1"/><path d="M1.5 8h6M5 5.5 7.5 8 5 10.5"/></svg>',
      after: '<svg viewBox="0 0 20 16" aria-hidden="true"><rect x="1.5" y="1.5" width="8" height="13" rx="1"/><path d="M12.5 8h6M16 5.5 18.5 8 16 10.5"/></svg>',
    };
    function moveTarget(n) {
      if (S.pmove.doc === S.doc.id && S.pmove.pages.includes(n)) return;     // not next to themselves
      S.pmove.at = S.pmove.at === n ? 0 : n;
      paintPagePick();
    }
    function paintPagePick() {
      const dlg = $("#" + VIEWER); if (!dlg) return;
      const mv = S.pmove && S.doc && S.pmove.doc === S.doc.id ? S.pmove.pages : [];
      dlg.querySelectorAll(".thumb[data-go]").forEach(t => {
        const n = Number(t.dataset.go);
        t.classList.toggle("picked", S.pp.includes(n)); t.classList.toggle("moving", mv.includes(n));
        t.classList.toggle("target", !!(S.pmove && S.pmove.at === n));
      });
      const strip = dlg.querySelector(".page-pick"); if (!strip) return;
      const on = (S.pp.length > 0 || !!(S.pmove && !S.pmove.out)) && gridHere();
      strip.hidden = !on;
      strip.parentElement.classList.toggle("choosing", on);
      if (!on) { strip.innerHTML = ""; return; }
      const nb = S.doc.kind === "notebook";
      const btn = (act, l, cls, icon) => '<button type="button" class="btn' + (cls ? " " + cls : "") + '" data-pp="' + act + '">' + (icon || "") + esc(l) + "</button>";
      if (S.pmove) {
        const n = S.pmove.pages.length;
        strip.innerHTML = !nb
          ? '<span class="pick-name attn" role="status">' + esc(PD.t("fm.pmove_notebooks_only")) + "</span>"
          : S.pmove.at
          ? '<span class="pick-name" role="status">' + esc(PD.t("fm.pmove_at", { page: S.pmove.at })) + '</span><span class="pick-acts">' +
            btn("before", PD.t("fm.move_before"), "with-icon", PMOVE_ICON.before) + btn("after", PD.t("fm.move_after"), "with-icon", PMOVE_ICON.after) + "</span>"
          : '<span class="pick-name" role="status">' + esc(PD.t(n === 1 ? "fm.pmove_pick_one" : "fm.pmove_pick_n", { n })) + '</span><span class="pick-acts">' +
            (S.pmove.doc === S.doc.id ? btn("moveout", PD.t("fm.move_out")) : "") + "</span>";
        return;
      }
      strip.innerHTML = '<span class="pick-name" role="status">' + esc(PD.t("fm.selected_n", { n: S.pp.length })) + '</span><span class="pick-acts">' +
        (S.pp.length < pageCount() ? btn("all", PD.t("fm.select_all")) : "") +
        (nb ? btn("duplicate", PD.t("fm.duplicate")) + btn("move", PD.t("fm.move")) : "") + btn("tags", PD.t("fm.tag")) +
        btn("delete", PD.t("common.delete"), "danger") + "</span>";
    }
    // PAGES DELETED, as they go: out of the grid, the pages left numbered anew where they are (their pictures with them),
    // nothing chosen, and the page open the same page as before -- or, deleted, the nearest page left (on a tie the one
    // after it, which takes its place); the pages' history the same way
    function pagesGone(gone) {
      const n0 = pageCount(), out = new Set(gone), newOf = new Map();
      for (let n = 1, k = 0; n <= n0; n++) if (!out.has(n)) newOf.set(n, ++k);
      if (!newOf.size) {                                    // EVERY PAGE: a blank page in their place (made by the engine, no
        S.page = 1; S.hist = [1]; S.hpos = 0; S.doc.pages = 1;   // template), shown at once as the grid's one page
        if (S.tags && S.tags.page_tags) S.tags.page_tags = [[]];
        PD.thumbsRenumbered(base + "/library/" + S.doc.id + "/thumb/", newOf);
        S.pp = [];
        $("#" + VIEWER).querySelectorAll(".thumb[data-go]").forEach((t, i) => {
          if (i) { t.remove(); return; }
          t.dataset.go = 1; t.classList.add("here");
          const m = t.querySelector(".meta"), img = t.querySelector("img[data-thumb]");
          if (m) m.textContent = 1;
          if (img) { img.removeAttribute("src"); img.dataset.thumb = 1; }
        });
        paintPagePick(); paintBar();
        return;
      }
      const near = n => {
        if (newOf.has(n)) return newOf.get(n);
        let b = n - 1, a = n + 1;
        while (b >= 1 && !newOf.has(b)) b--;
        while (a <= n0 && !newOf.has(a)) a++;
        return a <= n0 && (b < 1 || a - n <= n - b) ? newOf.get(a) : newOf.get(b);
      };
      S.page = near(S.page);
      const hist = [];
      let hpos = 0;
      S.hist.forEach((n, i) => { const m = near(n); if (hist[hist.length - 1] !== m) hist.push(m); if (i === S.hpos) hpos = hist.length - 1; });
      S.hist = hist; S.hpos = hpos;
      S.doc.pages = newOf.size;
      if (S.tags && S.tags.page_tags) S.tags.page_tags = [...newOf.keys()].map(n => S.tags.page_tags[n - 1] || []);
      PD.thumbsRenumbered(base + "/library/" + S.doc.id + "/thumb/", newOf);
      S.pp = [];
      $("#" + VIEWER).querySelectorAll(".thumb[data-go]").forEach(t => {
        const to = newOf.get(Number(t.dataset.go));
        if (!to) { t.remove(); return; }
        t.dataset.go = to; t.classList.toggle("here", to === S.page);
        const m = t.querySelector(".meta"), img = t.querySelector("img[data-thumb]");
        if (m) m.textContent = to;
        if (img) img.dataset.thumb = to;
      });
      paintPagePick(); paintBar();
    }
    // after a change: the notebook as it is now, the grid drawn anew, nothing chosen
    async function pagesChanged() {
      const x = S.doc.id;
      S.pp = [];
      await load();
      S.doc = byId(x) || S.doc;
      S.page = Math.min(S.page, pageCount());
      const [d] = await PD.safe(api("GET", "/library/" + x));
      if (d) S.tags = d;
      paintBar(); paintBody();
    }
    async function pagePickAct(act) {
      const strip = $("#" + VIEWER + " .page-pick"), msg = strip && strip.querySelector(".pick-name");
      const fail = e => { if (msg) { msg.textContent = PD.errText(e); msg.classList.add("attn"); } };
      if (S.pmove) {
        const P = S.pmove;
        if (act === "moveout") { P.out = true; P.at = 0; $("#" + VIEWER).close(); paintPickMenu(); return; }
        if ((act === "before" || act === "after") && P.at) {
          const [, e] = await PD.safe(api("POST", "/library/" + P.doc + "/pages/move",
            Object.assign({ pages: P.pages, where: act, at: P.at }, S.doc.id !== P.doc ? { to: S.doc.id } : {})));
          if (e) { fail(e); return; }
          S.pmove = null;
          await pagesChanged();
        }
        return;
      }
      if (!S.pp.length) { paintPagePick(); return; }
      const doc = S.doc.id, pages = S.pp.slice();
      const run = async (what, body) => {
        const [, e] = await PD.safe(api("POST", "/library/" + doc + "/pages/" + what, Object.assign({ pages }, body || {})));
        if (e) { fail(e); return; }
        await pagesChanged();
      };
      if (act === "all") { S.pp = Array.from({ length: pageCount() }, (_, i) => i + 1); paintPagePick(); return; }
      if (act === "duplicate") { await run("duplicate"); return; }
      if (act === "delete") {
        if (!await PD.confirm({ title: PD.count("fm.delete_pages_q", pages.length),
                                action: PD.t("common.delete"), danger: true })) return;
        // THE PAGES GO AT ONCE (pagesGone), then the engine is told: refused, the notebook as the engine has it again,
        // the pages chosen again with the reason; done, the page open is the page it opens at next (every page gone:
        // the blank page the engine made in their place, the grid drawn anew with it)
        const every = pages.length >= pageCount();
        pagesGone(pages);
        const [, e] = await PD.safe(api("POST", "/library/" + doc + "/pages/delete", { pages }));
        if (e) {
          await pagesChanged();
          S.pp = pages.filter(n => n <= pageCount()); paintPagePick();
          const m = $("#" + VIEWER + " .page-pick .pick-name"); if (m) { m.textContent = PD.errText(e); m.classList.add("attn"); }
          return;
        }
        if (S.doc && S.doc.id === doc) opened(doc, S.page);
        if (every) { await pagesChanged(); return; }
        PD.safe(api("GET", "/library/" + doc)).then(([d]) => { if (d && S.doc && S.doc.id === doc) { S.tags = d; paintBar(); } });
        return;
      }
      if (act === "tags") {
        const per = (S.tags && S.tags.page_tags) || [];
        tagsDialog(S.doc.name, common(pages.map(n => per[n - 1] || [])), async (add, remove) => {
          await api("POST", "/library/" + doc + "/pages/tags", { pages, add, remove });
          await pagesChanged();
        });
        return;
      }
      if (act === "move") { S.pmove = { doc, name: S.doc.name, pages, at: 0, out: false }; S.pp = []; paintPagePick(); }
    }

    async function load() {
      const [list, e] = await PD.safe(api("GET", "/library"));
      // THE SAME LIBRARY IS NOT DRAWN AGAIN: the false mirror asks every five seconds, and redrawing every cover each
      // time restarted what was moving on them (a job's bar)
      const seen = JSON.stringify([e ? PD.errText(e) : "", list || []]);
      const same = seen === S.libSeen;
      S.libSeen = seen;
      S.err = e ? PD.errText(e) : ""; S.list = list || [];
      if (S.at && !byId(S.at)) { S.at = ""; remember(); }
      if ((S.picked || []).length) { S.picked = S.picked.filter(byId); if (!S.picked.length) unpick(); }
      // (a window made on a new card opens in the folder the window it replaces was showing; a window opened with no
      // address, in the folder this screen last showed)
      if (!PD.firstAt && !PD.firstOpen && PD.firstPane === id && !S.restored) PD.firstAt = lastAt();
      S.restored = true;
      const into = PD.firstAt && byId(PD.firstAt) && PD.firstPane === id;
      if (into) { S.at = PD.firstAt; PD.firstAt = ""; remember(); }
      if (!same || into) paint();
      if (PD.firstOpen && byId(PD.firstOpen) && (!PD.firstPane || PD.firstPane === id)) {
        const x = PD.firstOpen; PD.firstOpen = ""; openDoc(x);
        if (PD.moved) readyWhenShown();
      } else if (PD.moved && PD.firstPane === id) readyWhenShown();
    }
    // A WINDOW MADE ON A NEW CARD says so once its document shows (its page drawn, or fifteen seconds gone by): the shell
    // then puts it in the place of the window it replaces, and lets that one go
    function readyWhenShown() {
      const moved = PD.moved;
      PD.moved = 0;
      let n = 0;
      const look = () => {
        const f = editorFrame(), l = f && f.contentDocument && f.contentDocument.getElementById("loading");
        if ((l && l.hidden) || ++n > 300) PD.safe(PD.api("POST", "/render/window/ready", { moved }));
        else setTimeout(look, 50);
      };
      look();
    }

    // ---- the false mirror's own: making, importing, and the menu of what is selected

    function ask(title, inner, action, onOk) {
      const dlg = PD.sheet(title, inner + '<p class="hint" data-msg role="status"></p><div class="actions"><button type="button" class="btn" data-v="cancel">' +
        esc(PD.t("common.cancel")) + '</button><button type="button" class="btn primary" data-v="ok">' + esc(action) + "</button></div>");
      dlg.addEventListener("click", async e => {
        const b = e.target.closest("button[data-v]"); if (!b) return;
        if (b.dataset.v === "cancel") { dlg.close(); return; }
        const msg = dlg.querySelector("[data-msg]");
        const [, err] = await PD.safe(PD.busy(b, () => onOk(dlg)));
        if (err) { msg.textContent = PD.errText(err); msg.className = "hint attn"; return; }
        dlg.close();
      });
      dlg.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches("input[type=text]")) { e.preventDefault(); dlg.querySelector("[data-v=ok]").click(); } });
      dlg.addEventListener("close", () => dlg.remove());
      document.body.append(dlg);
      dlg.showModal();
      const first = dlg.querySelector("input"); if (first) first.focus();
      return dlg;
    }

    // A DOCUMENT'S SHEET (its title clicked in the viewer): its name, its tags, its cover (the tablet's own setting: the
    // page last visited or the first page) and Export, the whole document. The False Mirror's are written at once; the
    // Mirror's name and cover in place and sent to the tablet, only while Edit the Mirror is on (off: shown, not to be
    // changed), its tags shown. Saved, the library is read again: the cover is drawn anew once the viewer closes
    function docSheet() {
      const d = S.doc; if (!d) return;
      const can = fm || !!PD.getK(PD.settings || {}, "mirror.edit"), now = d.cover === "first" ? "first" : "last", off = can ? "" : " disabled";
      const radio = (v, l) => '<label class="check-label"><input type="radio" name="doc-cover" value="' + v + '"' + (v === now ? " checked" : "") + off + "> " + esc(l) + "</label>";
      const chip = t => '<span class="chip" data-tag="' + esc(t) + '">' + esc(t) + (fm ? '<button type="button" class="chip-x" aria-label="' + esc(PD.t("fm.untag", { tag: t })) + '">×</button>' : "") + "</span>";
      const tags0 = (d.tags || []).slice();
      const dlg = ask(d.name,
        '<label class="field-row"><span>' + esc(PD.t("fm.name")) + '</span><input class="field w-l" type="text" data-doc-name spellcheck="false" value="' + esc(d.name) + '"' + off + "></label>" +
        '<div class="field-row doc-tags"><span>' + esc(PD.t("fm.tag")) + '</span><div class="tag-edit" data-tags>' + tags0.map(chip).join("") + "</div>" +
        (fm ? '<input class="field w-l" type="text" data-new-tag spellcheck="false" placeholder="' + esc(PD.t("fm.tag_add")) + '">' : "") + "</div>" +
        '<fieldset class="field-row nb-cover"><legend>' + esc(PD.t("fm.cover")) + "</legend>" + radio("last", PD.t("fm.cover.last")) + radio("first", PD.t("fm.cover.first")) + "</fieldset>" +
        '<div class="field-row"><button type="button" class="btn" data-doc-export>' + esc(PD.t("fm.export")) + '</button><span class="hint" data-doc-said role="status"></span></div>',
        PD.t("fm.save"), async box => {
          const id = encodeURIComponent(d.id), name = box.querySelector("[data-doc-name]").value.trim();
          if (can && name && name !== d.name) { await api("PUT", "/library/" + id + "/name", { name }); d.name = name; }
          if (fm) {
            const tags = [...box.querySelectorAll("[data-tag]")].map(c => c.dataset.tag), field = box.querySelector("[data-new-tag]");
            const extra = field && field.value.trim() ? knownSpelling(field.value.trim()) : "";
            if (extra && !hasTag(tags, extra)) tags.push(extra);
            if (tags.join("\n") !== tags0.join("\n")) { await api("PUT", "/library/" + id + "/tags", { tags }); d.tags = tags; }
          }
          const v = (box.querySelector("[name=doc-cover]:checked") || {}).value || now;
          if (can && v !== now) { await api("PUT", "/library/" + id + "/cover", { cover: v }); d.cover = v; }
          paintBar(); load();
        });
      dlg.addEventListener("click", async e => {
        const x = e.target.closest(".chip-x"); if (x) { x.closest("[data-tag]").remove(); return; }
        if (!e.target.closest("[data-doc-export]")) return;
        const said = dlg.querySelector("[data-doc-said]");
        said.textContent = PD.t("fm.exporting");
        const [got, err] = await PD.safe(PD.api("POST", "/false-mirror/export", { doc: d.id, name: d.name }));
        said.textContent = err ? PD.errText(err) : PD.t("fm.exported", { name: got.name });
      });
      const add = dlg.querySelector("[data-new-tag]");
      if (add) add.addEventListener("keydown", e => {
        if (e.key !== "Enter" || !e.target.value.trim()) return;
        e.preventDefault(); e.stopPropagation();
        const t = knownSpelling(e.target.value.trim()); e.target.value = "";
        if (hasTag([...dlg.querySelectorAll("[data-tag]")].map(c => c.dataset.tag), t)) return;
        dlg.querySelector("[data-tags]").insertAdjacentHTML("beforeend", chip(t));
      });
    }

    // THE NAME, EMPTY: what it is called when left so ("Notebook") is its placeholder, gone the moment the user types
    const nameField = (placeholder) => '<label class="field-row"><span>' + esc(PD.t("fm.name")) + '</span><input class="field w-l" type="text" data-name value="" placeholder="' +
      esc(placeholder) + '" spellcheck="false"></label>';
    const nameOf = dlg => { const f = dlg.querySelector("[data-name]"); return f.value.trim() || f.placeholder; };

    // A NEW NOTEBOOK, AS THE TABLET MAKES ONE: its name, its cover (the page last visited, or the first page), and with
    // an account signed in its template (the tablet's, from the user's own desktop app: none without one)
    const tplIcon = t => t.icon && t.icon.d ? '<svg class="tpl-ico" viewBox="' + esc(t.icon.viewBox) + '" aria-hidden="true"><path d="' + esc(t.icon.d) + '"/></svg>'
      // an rM Methods icon is a picture with its own colors: drawn as a mask, in the text's color like the rest
      : t.icon && t.icon.svg ? '<span class="tpl-ico tpl-mask" aria-hidden="true" style="--ico: url(&quot;data:image/svg+xml;base64,' + esc(t.icon.svg) + '&quot;)"></span>'
      : '<svg class="tpl-ico" viewBox="0 0 30 40" aria-hidden="true"><rect x="1" y="1" width="28" height="38" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>';
    // A TEMPLATE PAPERDAEMON DRAWS ITSELF (the app keeps no definition of it), marked as the editor's picker marks it
    const approxMark = () => '<span class="tpl-approx" title="' + esc(PD.t("fm.tpl_approx")) + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M12 3.5 21.5 20h-19z"/><path d="M12 10v4.5" stroke-linecap="round"/>' +
      '<circle cx="12" cy="17.2" r="0.6" fill="currentColor"/></svg></span>';
    async function newNotebook() {
      const [tpls] = await PD.safe(PD.api("GET", "/templates"));
      const list = Array.isArray(tpls) ? tpls : [];
      const inner = nameField(PD.t("fm.notebook")) +
        '<fieldset class="field-row nb-cover"><legend>' + esc(PD.t("fm.cover")) + "</legend>" +
        '<label class="check-label"><input type="radio" name="nb-cover" value="last" checked> ' + esc(PD.t("fm.cover.last")) + "</label>" +
        '<label class="check-label"><input type="radio" name="nb-cover" value="first"> ' + esc(PD.t("fm.cover.first")) + "</label></fieldset>" +
        (list.length ? '<div class="field-row"><span>' + esc(PD.t("fm.template")) + '</span><div class="nb-tpls" role="radiogroup">' +
          list.map((t, i) => '<button type="button" class="nb-tpl' + (i ? "" : " here") + '" role="radio" aria-checked="' + (i ? "false" : "true") +
            '" data-tpl="' + esc(t.file) + '" title="' + esc(t.name + (t.approx ? " -- " + PD.t("fm.tpl_approx") : "")) + '">' + tplIcon(t) +
            "<span>" + esc(t.name) + "</span>" + (t.approx ? approxMark() : "") + "</button>").join("") +
          "</div></div>" : "");
      const dlg = ask(PD.t("fm.new_notebook"), inner, PD.t("fm.create"), async d => {
        const cover = (d.querySelector("[name=nb-cover]:checked") || {}).value || "last";
        const tp = d.querySelector(".nb-tpl.here");
        await api("POST", "/library/notebook", Object.assign({ name: nameOf(d), parent: S.at, cover },
                                                             tp ? { template: tp.dataset.tpl } : {}));   // none: the engine's Blank
        await load();
      });
      dlg.addEventListener("click", e => {
        const b = e.target.closest(".nb-tpl"); if (!b) return;
        dlg.querySelectorAll(".nb-tpl").forEach(x => { x.classList.toggle("here", x === b); x.setAttribute("aria-checked", String(x === b)); });
      });
    }

    // QUICK SHEETS, as the tablet's button: the library's one Quick sheets, open on a new page at its end; no name to give
    async function quickSheets() {
      const msg = $("#" + id + "-import", R);
      const [got, e] = await PD.safe(api("POST", "/library/quick-sheets"));
      if (e) { msg.textContent = PD.errText(e); msg.className = "hint import-msg attn"; return; }
      await load();
      openDoc(got.id);
      go(got.page);
    }

    function newFolder() {
      ask(PD.t("fm.new_folder"), nameField(PD.t("fm.folder")), PD.t("fm.create"), async dlg => {
        await api("POST", "/library/folder", { name: nameOf(dlg), parent: S.at });
        await load();
      });
    }

    // IMPORT, MADE EASY: the button opens the file chooser at once (several files at a time), or files are dropped on
    // the screen. PDFs and EPUBs, each named by its file, land in the folder open; the line under the head says how it
    // goes. Nothing to fill in.
    const IMPORTABLE = /\.(pdf|epub)$/i;
    async function importFiles(files) {
      const list = [...files].filter(f => IMPORTABLE.test(f.name));
      const msg = $("#" + id + "-import", R);
      const say = (text, bad) => { msg.textContent = text; msg.className = "hint import-msg" + (bad ? " attn" : ""); };
      if (!list.length) { say(PD.t("fm.import_kinds"), true); return; }
      const into = S.at, failed = [];
      for (const f of list) {
        const name = f.name.replace(IMPORTABLE, "");
        say(PD.t("fm.importing", { name }));
        const [, e] = await PD.safe(PD.apiRaw("POST", base + "/library/import?name=" + encodeURIComponent(name) + "&parent=" + encodeURIComponent(into),
                                               await f.arrayBuffer(), /\.epub$/i.test(f.name) ? "application/epub+zip" : "application/pdf"));
        if (e) failed.push(PD.t("fm.import_failed", { name, why: PD.errText(e) }));
        await load();
      }
      if (failed.length) say(failed.join(" "), true);
      else say(list.length === 1 ? PD.t("fm.imported", { name: list[0].name.replace(IMPORTABLE, "") }) : PD.t("fm.imported_n", { n: list.length }));
    }
    function importFile() {
      const pick = document.createElement("input");
      pick.type = "file"; pick.multiple = true; pick.accept = ".pdf,.epub,application/pdf,application/epub+zip";
      pick.addEventListener("change", () => { if (pick.files.length) importFiles(pick.files); });
      pick.click();
    }

    // THE MENU OF WHAT IS SELECTED slides down over the top of the screen, as the tablet's does: nothing under it moves.
    // SEVERAL AT ONCE, as on the tablet: a long press or a right-click selects, and while anything is selected a click
    // adds an item or takes it away; Esc, or a click on nothing, lets them all go. S.picked: the ids, in the order chosen.
    const picked = () => (S.picked || []).map(byId).filter(Boolean);
    function pick(x) {
      const was = S.picked || [];
      S.picked = was.includes(x) ? was.filter(y => y !== x) : was.concat([x]);
      if (!S.picked.length) { unpick(); return; }
      paint(); paintPickMenu();
    }
    // MOVING, AS THE TABLET MOVES: Move turns the bar into where to (no sheet over the screen); the folders open as ever,
    // and in a folder the items are not all in already the bar offers Move here. Esc lets it go. S.lmove: moving.
    const canMoveHere = its => its.some(it => it.parent !== S.at) && !path(S.at).some(f => its.some(it => it.id === f.id));
    // THE COVER OF THOSE PICKED (documents): the page last visited or the first, theirs if they share one; in the Mirror
    // only while Edit the Mirror is on
    function coverPick(its) {
      const cs = its.map(it => it.cover === "first" ? "first" : "last"), same = cs.every(c => c === cs[0]) ? cs[0] : "";
      const can = fm || !!PD.getK(PD.settings || {}, "mirror.edit");
      const opt = (v, l) => '<option value="' + v + '"' + (same === v ? " selected" : "") + ">" + esc(l) + "</option>";
      return '<span class="select"><select class="field" data-pick-cover aria-label="' + esc(PD.t("fm.cover")) + '"' + (can ? "" : " disabled") + ">" +
        (same ? "" : '<option value="" selected disabled>' + esc(PD.t("fm.cover")) + "</option>") + opt("last", PD.t("fm.cover.last")) + opt("first", PD.t("fm.cover.first")) + "</select></span>";
    }
    async function pickCover(v) {
      const its = picked().filter(it => it.type === "document"), msg = $("#" + id + "-menu .pick-name", R);
      for (const it of its) {
        if ((it.cover === "first" ? "first" : "last") === v) continue;
        const [, e] = await PD.safe(api("PUT", "/library/" + encodeURIComponent(it.id) + "/cover", { cover: v }));
        if (e) { msg.textContent = PD.errText(e); msg.classList.add("attn"); return; }
      }
      const keep = its.map(it => it.id);
      await load(); S.picked = keep.filter(byId); paint(); paintPickMenu();
    }
    function paintPickMenu() {
      const m = $("#" + id + "-menu", R);
      if (S.pmove && S.pmove.out) {                                // pages on their way out of a notebook: open the one they go to
        const n = S.pmove.pages.length;
        m.innerHTML = '<span class="pick-name" role="status">' + esc(PD.t(n === 1 ? "fm.pmove_open_one" : "fm.pmove_open_n", { n, name: S.pmove.name })) + "</span>";
        m.hidden = false; m.parentElement.classList.add("choosing");
        return;
      }
      const its = picked(); if (!its.length) return;
      const docs = its.every(it => it.type === "document");
      const btn = (act, l, cls) => '<button type="button" class="btn' + (cls ? " " + cls : "") + '" data-pick-act="' + act + '">' + esc(l) + "</button>";
      const what = its.length === 1 ? its[0].name : PD.t("fm.selected_n", { n: its.length });
      m.innerHTML = S.lmove
        ? '<span class="pick-name" role="status">' + esc(PD.t(its.length === 1 ? "fm.lmove_one" : "fm.lmove_n", { name: its[0].name, n: its.length })) + '</span><span class="pick-acts">' +
          (canMoveHere(its) ? btn("movehere", PD.t("fm.move_here")) : "") + "</span>"
        : '<span class="pick-name" role="status">' + esc(what) + '</span><span class="pick-acts">' +
          (docs ? coverPick(its) + btn("export", PD.t("fm.export")) + btn("duplicate", PD.t("fm.duplicate")) : "") + btn("move", PD.t("fm.move")) + btn("tags", PD.t("fm.tag")) +
          btn("delete", PD.t("common.delete"), "danger") + "</span>";
      m.hidden = false;
      m.parentElement.classList.add("choosing");
    }

    function unpick() {
      S.picked = []; S.lmove = false;
      const m = R && $("#" + id + "-menu", R);
      if (m) { m.hidden = true; m.parentElement.classList.remove("choosing"); }
      paint();
    }

    // TAGS OF SEVERAL: the tags they all carry, each to take off all of them, and a field to put one on all of them
    // (no case: "Joi" is "joi"); one item: its own tags, as before. -> the dialog
    function tagsDialog(title, current, onSave) {
      const chip = t => '<span class="chip" data-tag="' + esc(t) + '">' + esc(t) + '<button type="button" class="chip-x" aria-label="' + esc(PD.t("fm.untag", { tag: t })) + '">×</button></span>';
      const dlg = ask(title, '<div class="tag-edit" data-tags>' + current.map(chip).join("") +
        '</div><input class="field w-l" type="text" data-new-tag spellcheck="false" placeholder="' + esc(PD.t("fm.tag_add")) + '">', PD.t("fm.save"), async d => {
          const now = [...d.querySelectorAll("[data-tag]")].map(c => c.dataset.tag);
          const extra = knownSpelling(d.querySelector("[data-new-tag]").value.trim());
          if (extra && !hasTag(now, extra)) now.push(extra);
          await onSave(now.filter(t => !hasTag(current, t)), current.filter(t => !hasTag(now, t)));
        });
      dlg.addEventListener("click", e => { const x = e.target.closest(".chip-x"); if (x) x.closest("[data-tag]").remove(); });
      dlg.querySelector("[data-new-tag]").addEventListener("keydown", e => {
        if (e.key !== "Enter" || !e.target.value.trim()) return;
        e.preventDefault(); e.stopPropagation();
        const t = knownSpelling(e.target.value.trim()); e.target.value = "";
        if (hasTag([...dlg.querySelectorAll("[data-tag]")].map(c => c.dataset.tag), t)) return;   // already there, in any case
        dlg.querySelector("[data-tags]").insertAdjacentHTML("beforeend", chip(t));
      });
      return dlg;
    }
    const common = lists => (lists[0] || []).filter(t => lists.every(l => hasTag(l, t)));

    async function pickAct(act) {
      const its = picked(); if (!its.length) return;
      // what happened is said where the bar names the selection: nothing appears under it, nothing moves
      const msg = $("#" + id + "-menu .pick-name", R);
      const say = (text, bad) => { msg.textContent = text; msg.classList.toggle("attn", !!bad); };
      const one = its.length === 1 ? its[0] : null;
      if (act === "export") {
        for (const it of its) {
          say(PD.t("fm.exporting"));
          const [got, e] = await PD.safe(PD.api("POST", "/false-mirror/export", { doc: it.id, name: it.name }));
          if (e) { say(PD.errText(e), true); return; }
          say(PD.t("fm.exported", { name: got.name }));
        }
        return;
      }
      if (act === "duplicate") {
        for (const it of its) {
          const [, e] = await PD.safe(api("POST", "/library/" + it.id + "/duplicate"));
          if (e) { say(PD.errText(e), true); return; }
        }
        unpick(); load();
        return;
      }
      if (act === "delete") {
        if (!await PD.confirm({ title: one ? PD.t("fm.delete_q", { name: one.name }) : PD.t("fm.delete_n_q", { n: its.length }),
                                action: PD.t("common.delete"), danger: true })) return;
        for (const it of its) {
          const [, e] = await PD.safe(api("DELETE", "/library/" + it.id));
          if (e) { say(PD.errText(e), true); load(); return; }
        }
        unpick(); load();
        return;
      }
      if (act === "move") { S.lmove = true; paint(); paintPickMenu(); return; }
      if (act === "movehere") {
        if (!canMoveHere(its)) return;
        for (const it of its) {
          if (it.parent === S.at) continue;
          const [, e] = await PD.safe(api("POST", "/library/" + it.id + "/move", { parent: S.at }));
          if (e) { say(PD.errText(e), true); load(); return; }
        }
        unpick(); await load();
        return;
      }
      if (act === "tags") {
        tagsDialog(one ? one.name : PD.t("fm.selected_n", { n: its.length }), common(its.map(it => it.tags || [])), async (add, remove) => {
          for (const it of its) {
            const now = (it.tags || []).filter(t => !hasTag(remove, t)).concat(add.filter(t => !hasTag(it.tags || [], t)));
            await api("PUT", "/library/" + it.id + "/tags", { tags: now });
          }
          const keep = its.map(it => it.id);
          await load(); S.picked = keep.filter(byId); paint(); paintPickMenu();
        });
      }
    }

    PD.screen(id, {
      label, group: 1,
      hidden: fm ? st => !(st.false_mirror || {}).exists : null,
      rail(st) {
        if (fm) return "";
        const t = st.tablet;
        if (!t) return "";
        const m = PD.mirrorState(st);                  // while the Mirror builds, its meter takes the label's place
        if (m.building) return '<span class="step-meter" title="' + esc(PD.t("su.building_pct", { pct: m.pct })) + '"><span class="bar" aria-hidden="true"><i style="width:' + m.pct + '%"></i></span><span class="pct">' + m.pct + "%</span></span>";
        if (!t.set) return PD.mk("fail") + esc(PD.t("settings.login.none"));     // connected needs no word; a problem does
        return "";
      },
      mount(root) {
        R = root;
        // THE FALSE MIRROR'S ACTIONS under a + at the top right: Quick sheets, New notebook, New folder, Import
        root.innerHTML = '<div class="page-head"><h1>' + esc(label) + "</h1>" + (fm ? '<span class="head-acts"><button type="button" class="icon-btn" data-act="fm-menu" aria-haspopup="menu" aria-expanded="false" title="' +
          esc(PD.t("fm.new_menu")) + '" aria-label="' + esc(PD.t("fm.new_menu")) + '">' + ICON.add + '</button><span class="head-menu" role="menu" hidden>' +
          '<button type="button" role="menuitem" data-act="quick-sheets">' + esc(PD.t("fm.quick_sheets")) + "</button>" +
          '<button type="button" role="menuitem" data-act="new-notebook">' + esc(PD.t("fm.new_notebook")) + "</button>" +
          '<button type="button" role="menuitem" data-act="new-folder">' + esc(PD.t("fm.new_folder")) + "</button>" +
          '<button type="button" role="menuitem" data-act="import">' + esc(PD.t("fm.import")) + "</button></span></span>" +
          '<div class="select-bar" id="' + id + '-menu" role="toolbar" hidden></div>' : "") + "</div>" +
          (fm ? '<p class="hint import-msg" id="' + id + '-import" role="status"></p>' +
                '<div class="drop-here" id="' + id + '-drop" hidden>' + esc(PD.t("fm.drop")) + "</div>" : "") +
          '<div class="lib-box" id="' + id + '-files"></div>';
        // WHILE ANYTHING IS SELECTED a click on a notebook or folder adds it or takes it away; a crumb still goes there.
        // WHILE MOVING the folders open as ever (the bar follows: Move here); pages moving out open a notebook
        const moving = () => S.lmove || !!(S.pmove && S.pmove.out);
        const choosing = () => (S.picked || []).length > 0 && !moving();
        PD.on(root, "click", "[data-at]", (e, el) => {
          if (S.held) { S.held = false; return; }
          if (choosing() && el.dataset.item) { pick(el.dataset.item); return; }
          if (choosing()) unpick();
          S.at = el.dataset.at; remember(); paint();
          if (moving()) paintPickMenu();
        });
        PD.on(root, "click", "[data-open]", (e, el) => {
          if (S.held) { S.held = false; return; }
          if (S.lmove) return;                                // documents are not where things move to
          if (choosing()) { pick(el.dataset.item); return; }
          if (S.pmove && S.pmove.out && (byId(el.dataset.open) || {}).kind !== "notebook") {
            const m = $("#" + id + "-menu .pick-name", R); if (m) { m.textContent = PD.t("fm.pmove_notebooks_only"); m.classList.add("attn"); }
            return;
          }
          openDoc(el.dataset.open);
        });
        root.addEventListener("click", e => {
          if (choosing() && !e.target.closest("[data-item], .select-bar, .head-acts, button, a, input")) unpick();
        });
        if (!fm) return;
        const menu = $(".head-menu", root), menuBtn = $("[data-act=fm-menu]", root);
        const closeMenu = () => { menu.hidden = true; menuBtn.setAttribute("aria-expanded", "false"); };
        PD.on(root, "click", "[data-act=fm-menu]", () => { menu.hidden = !menu.hidden; menuBtn.setAttribute("aria-expanded", String(!menu.hidden)); });
        document.addEventListener("click", e => { if (!menu.hidden && !e.target.closest(".head-acts")) closeMenu(); });
        root.addEventListener("keydown", e => { if (e.key === "Escape" && !menu.hidden) closeMenu(); });
        // Esc puts the selection's menu away (it has no close button)
        document.addEventListener("keydown", e => {
          if (e.key !== "Escape" || R.hidden || document.querySelector("dialog[open]")) return;
          if (S.pmove && S.pmove.out) { S.pmove = null; unpick(); return; }    // the pages stay where they were
          if ((S.picked || []).length) unpick();
        });
        PD.on(root, "click", "[data-act=quick-sheets]", () => { closeMenu(); quickSheets(); });
        PD.on(root, "click", "[data-act=new-notebook]", () => { closeMenu(); newNotebook(); });
        PD.on(root, "click", "[data-act=new-folder]", () => { closeMenu(); newFolder(); });
        PD.on(root, "click", "[data-act=import]", () => { closeMenu(); importFile(); });
        PD.on(root, "click", "[data-pick-act]", (e, el) => pickAct(el.dataset.pickAct));
        PD.on(root, "change", "[data-pick-cover]", (e, el) => { if (el.value) pickCover(el.value); });
        // FILES DROPPED ON THE SCREEN are imported into the folder open
        const drop = $("#" + id + "-drop", root);
        let over = 0;
        const hasFiles = e => [...(e.dataTransfer && e.dataTransfer.types || [])].includes("Files");
        root.addEventListener("dragenter", e => { if (!hasFiles(e)) return; e.preventDefault(); over++; drop.hidden = false; });
        root.addEventListener("dragover", e => { if (hasFiles(e)) e.preventDefault(); });
        root.addEventListener("dragleave", () => { if (--over <= 0) { over = 0; drop.hidden = true; } });
        root.addEventListener("drop", e => {
          if (!hasFiles(e)) return;
          e.preventDefault(); over = 0; drop.hidden = true;
          importFiles(e.dataTransfer.files);
        });
        // A LONG PRESS SELECTS: half a second held on a notebook or folder, and the click that ends it does nothing else
        let timer = 0;
        root.addEventListener("pointerdown", e => {
          // every press starts clean: the click that ended a long press may never have landed (the selection repaints
          // what was under the pointer), and must not swallow this one
          S.held = false;
          const it = e.target.closest("[data-item]"); if (!it || e.button !== 0) return;
          clearTimeout(timer);
          timer = setTimeout(() => { S.held = true; pick(it.dataset.item); }, 500);
        });
        ["pointerup", "pointerleave", "pointercancel"].forEach(t => root.addEventListener(t, () => clearTimeout(timer)));
        // A RIGHT-CLICK SELECTS, as a long press does
        root.addEventListener("contextmenu", e => {
          const it = e.target.closest("[data-item]"); if (!it) return;
          e.preventDefault(); clearTimeout(timer); pick(it.dataset.item);
        });
      },
      show() { load(); loadProgress(); },
      hide() { if ((S.picked || []).length) unpick(); },
      poll(n) {
        loadProgress();
        if (fm) { if (n % 5 === 0 && !(S.picked || []).length) load(); return; }       // the daemon's answers appear as they land
        const b = PD.mirrorState(PD.status).building;
        if ((b && n % 3 === 0) || (!b && S.pulling)) load();
        S.pulling = b;
      },
    });
  }

  library("tablet", { label: PD.t("tablet.label"), base: "", fm: false });
  library("fmirror", { label: PD.t("fm.label"), base: "/fm", fm: true });
})();
