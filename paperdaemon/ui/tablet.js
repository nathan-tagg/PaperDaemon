"use strict";
/* Mirror and False Mirror: the library as the tablet shows it. My files at the root, the breadcrumb of the open folder,
   its folders, then its notebooks and documents as covers. A notebook opens in a viewer the height of the window, one
   page at a time.

   One screen, made twice: MIRROR over the tablet's library (read only: tags shown, never changed), and FALSE MIRROR over
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
    menu: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 4h12M2 8h12M2 12h12"/></svg>',
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
                picked: null, held: false };
    const api = (m, p, b) => PD.api(m, base + p, b);
    const byId = x => (S.list || []).find(d => d.id === x);
    const VIEWER = id + "-viewer";

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
      return PD.loadImage(img, base + "/library/" + img.dataset.id + "/cover.png",
                          { tries: 4, giveUp: () => img.closest(".doc-card").classList.add("nocover") });
    }

    function paint() {
      const box = $("#" + id + "-files", R); if (!box) return;
      if (S.err) { box.innerHTML = '<p class="msg err">' + esc(S.err) + "</p>"; return; }
      if (!S.list) { box.innerHTML = '<p class="sub">' + esc(PD.t("common.reading")) + "</p>"; return; }
      const crumbs = [{ id: "", name: PD.t("tablet.my_files") }].concat(path(S.at));
      const here = S.list.filter(x => x.parent === S.at && x.parent !== "trash");
      const folders = here.filter(x => x.type === "folder"), docs = here.filter(x => x.type === "document");
      const on = x => S.picked === x ? " picked" : "";
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
    }

    // ---- the viewer, as the tablet has it: one page at a time, a grid of all the pages, the chapters

    const pageCount = () => Math.max(1, (S.doc && S.doc.pages) || 1);

    function paintBar() {
      const dlg = $("#" + VIEWER); if (!dlg || !S.doc) return;
      const n = pageCount();
      $(".viewer-title", dlg).textContent = S.doc.name;
      // THE BAR, LAID OUT AS THE TABLET'S TOOLBAR. A page: on the left the page editor's tools in the false mirror (pen,
      // pen, text, eraser, layers; the editor sends them; selection and capture will go between eraser and layers), then on the right
      // the tag, the page grid and the page arrows. The grid: on the right the chapters, the grid and Go to page. The
      // page's tags are in the tag button's menu, not in the bar.
      $(".viewer-tags", dlg).innerHTML = "";
      const tool = (v, l) => '<button type="button" class="icon-btn" data-v="' + v + '" aria-pressed="' + (S.view === v) + '" title="' + l + '" aria-label="' + l + '">' + ICON[v] + "</button>";
      const edHere = fm && ["notebook", "pdf", "epub"].includes(S.doc.kind) && S.view === "page";
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

    async function paintBody() {
      const dlg = $("#" + VIEWER); if (!dlg || !S.doc) return;
      const body = $(".viewer-page", dlg), n = pageCount();
      body.scrollTop = 0;
      if (S.view === "pages") {
        body.className = "viewer-page grid";
        body.innerHTML = Array.from({ length: n }, (_, i) => '<button type="button" class="thumb' + (i + 1 === S.page ? " here" : "") + '" data-go="' + (i + 1) + '">' +
          '<span class="cover"><img alt="" data-thumb="' + (i + 1) + '"></span><span class="meta">' + (i + 1) + "</span></button>").join("");
        const d = S.doc.id, io = new IntersectionObserver(es => es.forEach(x => {
          if (!x.isIntersecting) return;
          io.unobserve(x.target);
          PD.loadImage(x.target, base + "/library/" + d + "/thumb/" + x.target.dataset.thumb + ".png",
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
      // A FALSE-MIRROR NOTEBOOK PAGE OPENS IN THE PAGE EDITOR (editor.html, in a frame: it draws with PaperDaemon's own
      // renderer and saves the page as it goes)
      if (fm && ["notebook", "pdf", "epub"].includes(S.doc.kind)) {
        body.className = "viewer-page editing";
        body.innerHTML = '<iframe class="page-editor" allow="clipboard-read; clipboard-write" title="' + esc(PD.t("viewer.page", { n: S.page })) + '" src="/ui/editor.html#doc=' +
          encodeURIComponent(S.doc.id) + "&page=" + S.page + "&base=" + encodeURIComponent(base) + '"></iframe>';
        const efr = $("iframe.page-editor", body);
        efr.addEventListener("load", () => efr.focus());      // the keys go to the page from the start, no click first
        return;
      }
      body.className = "viewer-page";
      body.innerHTML = '<div class="page-port"><div class="page-stage"><div class="page-paper"></div><span class="page-frame"><img alt=""></span></div></div>';
      const img = $("img", body), frame = $(".page-frame", body), want = S.page, d = S.doc.id;
      const stale = () => want !== S.page || !S.doc || S.doc.id !== d || S.view !== "page";
      const [fr] = await PD.safe(api("GET", "/library/" + d + "/page/" + want + "/frame"));
      if (stale()) return;
      const shown = await PD.loadImage(img, base + "/library/" + d + "/page/" + want + ".png?square=1", { holder: body, stale,
        giveUp: h => { h.innerHTML = '<p class="sub viewer-wait">' + esc(PD.t("viewer.not_drawn")) + ' <button type="button" class="link-btn" data-v="retry">' +
          esc(PD.t("common.try_again")) + "</button></p>"; } });
      if (!shown || stale()) return;
      img.alt = PD.t("viewer.page", { n: want });
      S.frame = fr && fr.w ? fr : { w: SCREEN_W, h: SCREEN_H };
      placePage(true);
      // THE PAGE'S LINKS, as the tablet follows them: a link to another page goes there, a web link opens the browser
      const [got] = await PD.safe(api("GET", "/library/" + d + "/links/" + want));
      if (stale() || !got || !got.links || !got.links.length) return;
      const k = got.aspect ? Math.min(1, img.naturalWidth * got.aspect / img.naturalHeight) : 1;
      frame.insertAdjacentHTML("beforeend", got.links.map(l => {
        const [x0, a, x1, b] = l.box, y0 = a * k, y1 = b * k;
        const at = 'style="left:' + (x0 * 100) + "%;top:" + (y0 * 100) + "%;width:" + ((x1 - x0) * 100) + "%;height:" + ((y1 - y0) * 100) + '%"';
        return l.go ? '<button type="button" class="page-link" data-go="' + l.go + '" title="' + esc(PD.t("viewer.page", { n: l.go })) + '" aria-label="' + esc(PD.t("viewer.go_to", { n: l.go })) + '" ' + at + "></button>"
          : '<button type="button" class="page-link" data-uri="' + esc(l.uri) + '" title="' + esc(l.uri) + '" aria-label="Open ' + esc(l.uri) + '" ' + at + "></button>";
      }).join(""));
    }

    // THE PAGE ON THE TABLET'S SCREEN. The page area holds a port the Paper Pro's screen's shape (3:4, as big as the
    // viewer allows, never smaller) and shows in it what the Paper Pro shows: at 1x, 1620 page units across, centered on
    // the page's middle (x 0). The paper is as wide as the page is tall (the drawable square measured on the tablet) and
    // runs on down, as the page does; beside it, the tablet's gray (the page editor's 142). The page picture is exactly the frame
    // wide. A page longer than the screen stretches the port down (the chin) to the viewer's foot, and then the viewer
    // scrolls, its scrollbar in the margin beside the port. Ctrl + scroll zooms the page from 0.5x to 5x around the
    // pointer's height, always centered across (always opening at 1x); Shift + scroll moves across a zoomed page until
    // the zoom changes, and the pill says the zoom (click: 1x). The view opens on the page's top as the tablet shows it.
    const SCREEN_W = 1620, SCREEN_H = 2160, ZMIN = 0.5, ZMAX = 5;
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
    function placePage(fresh, anchor) {
      const dlg = $("#" + VIEWER); if (!dlg || S.view !== "page") return;
      const body = $(".viewer-page", dlg), port = $(".page-port", body), img = $(".page-frame img", body);
      if (!port || !img || !img.naturalWidth || !S.frame) return;
      const stage = $(".page-stage", port), paper = $(".page-paper", port), frame = $(".page-frame", port);
      const bw = body.clientWidth, bh = body.clientHeight;      // the scrollbar has its own room, beside the port
      const vw = Math.max(120, Math.min(bw, bh * 0.75)), vh = vw * 4 / 3;
      const z = S.zoom || 1, s = vw * z / SCREEN_W;                                            // CSS pixels per page unit
      // the picture is the drawable square wide (as wide as the page is tall) and starts at `top` (0, or above the page's
      // top where ink was written there)
      const fw = S.frame.w, top = Math.min(0, S.frame.top || 0), paperW = Math.max(fw, S.frame.h);
      const imgH = img.naturalHeight * paperW / img.naturalWidth, downTo = Math.max(S.frame.h - top, imgH);
      const U = Math.max(paperW, SCREEN_W / z);                                                // the stage's width in units
      // THE TOP OF THE VIEW IS THE PAGE'S TOP AS THE TABLET SHOWS IT: a small page shows above its file's y 0 (measured:
      // the frame box of a 200 x 266 page starts at y -61), so the view opens at the picture's top
      // THE PAGE ALWAYS SCROLLS, as on the tablet: on down until the view's top reaches the page's foot (or a screen down,
      // for a page shorter than the screen), whether or not anything is written there
      const stageH = Math.max(vh, downTo * s) + vh;
      // what was under the pointer, in page units, to keep it there
      let keep = null;
      if (anchor) {
        const r = port.getBoundingClientRect(), k = port.offsetWidth ? r.width / port.offsetWidth : 1;
        const px = (anchor.x - r.left) / k, py = (anchor.y - r.top) / k, old = S.placed;
        if (old) keep = { py, uy: py / old.s, top: body.scrollTop };
      }
      port.style.width = vw + "px"; port.style.height = stageH + "px";
      stage.style.width = U * s + "px"; stage.style.height = stageH + "px";
      paper.style.left = (U - paperW) / 2 * s + "px"; paper.style.width = paperW * s + "px"; paper.style.height = stageH + "px";
      frame.style.left = (U - paperW) / 2 * s + "px";
      img.style.width = paperW * s + "px";
      S.placed = { s, U };
      // ACROSS, always centered on the page's middle (x 0), at every zoom; DOWN, the point under the pointer stays put
      port.scrollLeft = (U * s - vw) / 2;
      if (keep) body.scrollTop = keep.top + keep.uy * s - keep.py;
      else if (fresh) body.scrollTop = 0;
    }
    function showZoom() {
      const dlg = $("#" + VIEWER); if (!dlg) return;
      let pill = $(".page-zoom", dlg);
      if (!pill) {
        pill = document.createElement("button");
        pill.type = "button"; pill.className = "page-zoom"; pill.dataset.v = "zoom1";
        dlg.append(pill);
      }
      pill.textContent = (Math.round((S.zoom || 1) * 10) / 10).toFixed(1) + "×";
      pill.title = PD.t("viewer.zoom_reset");
      pill.style.top = $(".viewer-page", dlg).offsetTop + 10 + "px";
      pill.classList.add("on");
      clearTimeout(S.zoomTimer);
      S.zoomTimer = setTimeout(() => pill.classList.remove("on"), 2500);
    }
    function wheelPage(e) {
      if (S.view !== "page") { if (e.ctrlKey) e.preventDefault(); return; }
      const port = e.target.closest && e.target.closest(".viewer-page") && $(".page-port", $("#" + VIEWER));
      if (!port) return;
      if (e.ctrlKey) {
        e.preventDefault();
        S.zoom = Math.max(ZMIN, Math.min(ZMAX, (S.zoom || 1) * Math.exp(-e.deltaY * 0.0015)));
        const r = port.getBoundingClientRect(), over = e.clientX >= r.left && e.clientX <= r.right;
        // around the pointer over the page; from the top middle when the pointer is beside it
        placePage(false, over ? { x: e.clientX, y: Math.max(e.clientY, r.top) } : { x: r.left + r.width / 2, y: Math.max(r.top, 0) });
        showZoom();
      } else if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();
        port.scrollLeft += e.deltaX || e.deltaY;
      }
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
      const used = new Set(here);
      (S.list || []).forEach(d => (d.tags || []).forEach(t => used.add(t)));
      ((S.tags && S.tags.page_tags) || []).forEach(ts => (ts || []).forEach(t => used.add(t)));
      const all = [...used].sort((a, b) => a.localeCompare(b));
      const pill = t => fm ? '<button type="button" class="chip tag-pill" data-tagtoggle="' + esc(t) + '" aria-pressed="' + here.includes(t) + '">' + esc(t) + "</button>"
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
      const inp = $("#" + VIEWER + " [data-tag-add]"); const t = inp && inp.value.trim(); if (!t) return;
      pageTags(now => now.includes(t) ? now : now.concat([t])).then(paintTagPop);
    }
    // THE PAGE EDITOR'S TOOLS LIVE IN THE BAR: the editor (in its frame) sends its buttons, and a press here goes back
    // to it with where the button is, so its menu opens right under it
    const editorFrame = () => $("#" + VIEWER + " iframe.page-editor");
    window.addEventListener("message", e => {
      const d = e.data, fr = editorFrame();
      if (!d || !fr || e.source !== fr.contentWindow) return;
      if (d.pd === "editor-menu") { S.edMenu = !!d.open; return; }                       // a menu of the editor's is open
      if (d.pd === "viewer-menu-close") { S.tagPop = false; paintBar(); paintTagPop(); return; }   // Esc pressed in the page
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
    function paintProgress() {
      if (!R) return;
      const p = S.progress;
      R.querySelectorAll(".cover .job-bar").forEach(b => { if (!p || b.closest(".doc-card").dataset.open !== p.doc) b.remove(); });
      if (p) {
        const card = R.querySelector('.doc-card[data-open="' + p.doc + '"] .cover');
        if (card) { const old = card.querySelector(".job-bar"); if (old) old.outerHTML = progressBar(p); else card.insertAdjacentHTML("beforeend", progressBar(p)); }
      }
      const dlg = $("#" + VIEWER);
      if (dlg) {
        const old = dlg.querySelector(":scope > .job-bar");
        if (p && dlg.open && S.doc && S.doc.id === p.doc) { if (old) old.outerHTML = progressBar(p); else dlg.insertAdjacentHTML("beforeend", progressBar(p)); }
        else if (old) old.remove();
      }
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

    function walk(step) {
      const dlg = $("#" + VIEWER);
      if (!dlg || !dlg.open) return false;
      const at = S.hpos + step;
      if (at < 0) { dlg.close(); return true; }
      if (at >= S.hist.length) return true;
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

    function openDoc(x) {
      S.doc = byId(x); S.page = 1; S.tags = null; S.chapters = null; S.hist = [1]; S.hpos = 0; S.zoom = 1; S.placed = null;
      S.view = PD.firstTab === "pages" || PD.firstTab === "chapters" ? PD.firstTab : "page"; PD.firstTab = "";
      let dlg = $("#" + VIEWER);
      if (!dlg) {
        dlg = document.createElement("dialog");
        dlg.id = VIEWER; dlg.className = "viewer";
        dlg.innerHTML = '<div class="viewer-head"><span class="viewer-name"><span class="viewer-title"></span><button type="button" class="keys-q" data-v="keys" title="' +
          esc(PD.t("keys.open")) + '" aria-label="' + esc(PD.t("keys.open")) + '">?</button></span><button type="button" class="link-btn" data-v="close">' + esc(PD.t("common.close")) + "</button></div>" +
          '<div class="viewer-bar"><span class="viewer-tools"></span><span class="viewer-tags"></span><span class="viewer-nav"></span></div>' +
          '<div class="viewer-page" tabindex="-1" autofocus></div>';
        dlg.addEventListener("click", async e => {
          const et = e.target.closest(".ed-tools [data-tool]");
          if (et) { pressEditorTool(et); return; }
          const efr = editorFrame();                      // a press anywhere else closes the editor's open menu
          if (efr && efr.contentWindow) efr.contentWindow.postMessage({ pd: "editor-close" }, location.origin);
          if (S.tagPop && !e.target.closest(".tag-pop") && !e.target.closest('[data-v="tagpop"]')) { S.tagPop = false; paintBar(); paintTagPop(); }
          const tg = e.target.closest("[data-tagtoggle]");
          if (tg) { const t = tg.dataset.tagtoggle; pageTags(now => now.includes(t) ? now.filter(x => x !== t) : now.concat([t])); return; }
          const g = e.target.closest("[data-go]");
          if (g) { go(Number(g.dataset.go)); return; }
          const u = e.target.closest("[data-uri]");
          if (u) { PD.api("POST", "/open-link", { url: u.dataset.uri }); return; }
          const x = e.target.closest("[data-untag]");
          if (x) { pageTags(now => now.filter(t => t !== x.dataset.untag)); return; }
          const b = e.target.closest("[data-v]");
          if (!b) { if (e.target === dlg) dlg.close(); return; }
          const v = b.dataset.v;
          if (v === "close") dlg.close();
          else if (v === "prev" || v === "next") go(S.page + (v === "next" ? 1 : -1));
          else if (v === "retry") paintBody();
          else if (v === "zoom1") {                       // back to 1x where it is: the middle of the view stays put
            const br = $(".viewer-page", dlg).getBoundingClientRect();
            S.zoom = 1; placePage(false, { x: br.left + br.width / 2, y: br.top + br.height / 2 }); showZoom();
          }
          else if (v === "tagpop") { S.tagPop = !S.tagPop; paintBar(); paintTagPop(); }
          else if (v === "keys") PD.openShortcuts(!!editorFrame());
          else if (v === "tagadd") addTypedTag();
          else if (v === "newpage") {
            const [got] = await PD.safe(api("POST", "/library/" + S.doc.id + "/pages", { after: S.page }));
            if (got) { S.doc.pages = (S.doc.pages || 1) + 1; go(got.page); }
          }
          else if (v === "pages" || v === "chapters") { S.view = S.view === v ? "page" : v; paintBar(); paintBody(); }
        });
        dlg.addEventListener("wheel", wheelPage, { passive: false });
        new ResizeObserver(() => placePage(false)).observe($(".viewer-page", dlg));
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
          if (S.view !== "page" || e.target.closest("input")) return;
          if (e.key === "ArrowRight" || e.key === "PageDown") go(S.page + 1);
          if (e.key === "ArrowLeft" || e.key === "PageUp") go(S.page - 1);
        });
        // back from the editor: the covers and the page pictures show what was drawn
        // CLOSING A FALSE-MIRROR DOCUMENT SYNCS it, as on the tablet: the page editor saves and tells the daemon to look
        // ESC CLOSES WHAT IS OPEN FIRST: the tags' menu, then the editor's menus, and only then the viewer
        dlg.addEventListener("cancel", e => {
          if (S.tagPop) { e.preventDefault(); S.tagPop = false; paintBar(); paintTagPop(); return; }
          const fr = editorFrame();
          if (S.edMenu && fr && fr.contentWindow) { e.preventDefault(); S.edMenu = false; fr.contentWindow.postMessage({ pd: "editor-close" }, location.origin); }
        });
        dlg.addEventListener("close", () => {
          if (!fm) return;
          const fr = editorFrame();
          if (fr && fr.contentWindow) fr.contentWindow.postMessage({ pd: "editor-commit" }, location.origin);
          else PD.safe(api("POST", "/library/sync"));
          load();
        });
        document.body.append(dlg);
        // the mouse's back (button 3) and forward (button 4) buttons, while a notebook is open: its pages, not the
        // app's screens. The press and the release are both taken, or the window would also go back a screen.
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

    async function load() {
      const [list, e] = await PD.safe(api("GET", "/library"));
      S.err = e ? PD.errText(e) : ""; S.list = list || [];
      if (S.at && !byId(S.at)) S.at = "";
      if (S.picked && !byId(S.picked)) unpick();
      paint();
      if (!fm && PD.firstOpen && byId(PD.firstOpen)) { const x = PD.firstOpen; PD.firstOpen = ""; openDoc(x); }
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

    const nameField = (value) => '<label class="field-row"><span>' + esc(PD.t("fm.name")) + '</span><input class="field w-l" type="text" data-name value="' + esc(value) + '" spellcheck="false"></label>';

    function newNotebook() {
      ask(PD.t("fm.new_notebook"), nameField(PD.t("fm.notebook")), PD.t("fm.create"), async dlg => {
        await api("POST", "/library/notebook", { name: dlg.querySelector("[data-name]").value, parent: S.at });
        await load();
      });
    }

    function newFolder() {
      ask(PD.t("fm.new_folder"), nameField(PD.t("fm.folder")), PD.t("fm.create"), async dlg => {
        await api("POST", "/library/folder", { name: dlg.querySelector("[data-name]").value, parent: S.at });
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

    // THE MENU OF WHAT IS SELECTED slides down over the top of the screen, as the tablet's does: nothing under it moves
    function pick(x) {
      S.picked = x; paint();
      const it = byId(x); if (!it) return;
      const m = $("#" + id + "-menu", R);
      const btn = (act, l, cls) => '<button type="button" class="btn' + (cls ? " " + cls : "") + '" data-pick-act="' + act + '">' + esc(l) + "</button>";
      m.innerHTML = '<span class="pick-name">' + esc(it.name) + '</span><span class="pick-acts">' +
        (it.type === "document" ? btn("export", PD.t("fm.export")) : "") + btn("move", PD.t("fm.move")) + btn("tags", PD.t("fm.tags")) +
        btn("delete", PD.t("common.delete"), "danger") + "</span>" +
        '<p class="hint pick-msg" role="status"></p>';
      // as tall as the rail's foot beside it (the version), from the same rule down, and as wide as the page
      const rail = document.querySelector(".rail"), foot = rail && rail.querySelector(".rail-foot");
      if (rail && foot && foot.offsetParent) {
        m.style.height = (rail.offsetHeight - foot.offsetTop) + "px";
        m.style.insetInlineStart = rail.offsetWidth + "px";
      } else { m.style.height = ""; m.style.insetInlineStart = "0px"; }
      m.classList.add("open");
    }

    function unpick() {
      S.picked = null;
      const m = R && $("#" + id + "-menu", R);
      if (m) m.classList.remove("open");
      paint();
    }

    function folderChoices(skip) {
      // every folder but the one being moved and those inside it, as the path the user knows
      const inside = f => { for (let d = f, n = 0; d && n < 30; d = byId(d.parent), n++) if (d.id === skip) return true; return false; };
      const folders = (S.list || []).filter(f => f.type === "folder" && !inside(f));
      const name = f => path(f.id).map(d => d.name).join(" / ");
      return [{ id: "", label: PD.t("tablet.my_files") }].concat(folders.map(f => ({ id: f.id, label: name(f) })).sort((a, b) => a.label.localeCompare(b.label)));
    }

    async function pickAct(act) {
      const it = byId(S.picked); if (!it) return;
      const msg = $("#" + id + "-menu .pick-msg", R);
      if (act === "close") { unpick(); return; }
      if (act === "export") {
        msg.textContent = PD.t("fm.exporting"); msg.className = "hint pick-msg";
        const [got, e] = await PD.safe(PD.api("POST", "/false-mirror/export", { doc: it.id, name: it.name }));
        msg.textContent = e ? PD.errText(e) : PD.t("fm.exported", { name: got.name });
        msg.className = "hint pick-msg" + (e ? " attn" : "");
        return;
      }
      if (act === "delete") {
        if (!await PD.confirm({ title: PD.t("fm.delete_q", { name: it.name }), body: [esc(PD.t(it.type === "folder" ? "fm.delete_folder_body" : "fm.delete_body"))],
                                action: PD.t("common.delete"), danger: true })) return;
        const [, e] = await PD.safe(api("DELETE", "/library/" + it.id));
        if (e) { msg.textContent = PD.errText(e); msg.className = "hint pick-msg attn"; return; }
        unpick(); load();
        return;
      }
      if (act === "move") {
        const opts = folderChoices(it.id);
        ask(PD.t("fm.move_q", { name: it.name }), '<div class="move-list" role="radiogroup">' + opts.map(o =>
          '<label class="check-label"><input type="radio" name="dest" value="' + esc(o.id) + '"' + (o.id === it.parent ? " checked" : "") + "> " + esc(o.label) + "</label>").join("") + "</div>",
          PD.t("fm.move"), async d => {
            const c = d.querySelector("input[name=dest]:checked");
            await api("POST", "/library/" + it.id + "/move", { parent: c ? c.value : "" });
            unpick(); await load();
          });
        return;
      }
      if (act === "tags") {
        const dlg = ask(PD.t("fm.tags_of", { name: it.name }), '<div class="tag-edit" data-tags>' + (it.tags || []).map(t =>
          '<span class="chip" data-tag="' + esc(t) + '">' + esc(t) + '<button type="button" class="chip-x" aria-label="' + esc(PD.t("fm.untag", { tag: t })) + '">×</button></span>').join("") +
          '</div><input class="field w-l" type="text" data-new-tag spellcheck="false" placeholder="' + esc(PD.t("fm.tag_add")) + '">', PD.t("fm.save"), async d => {
            const tags = [...d.querySelectorAll("[data-tag]")].map(c => c.dataset.tag);
            const extra = d.querySelector("[data-new-tag]").value.trim();
            await api("PUT", "/library/" + it.id + "/tags", { tags: extra ? tags.concat([extra]) : tags });
            await load(); pick(it.id);
          });
        dlg.addEventListener("click", e => { const x = e.target.closest(".chip-x"); if (x) x.closest("[data-tag]").remove(); });
        dlg.querySelector("[data-new-tag]").addEventListener("keydown", e => {
          if (e.key !== "Enter" || !e.target.value.trim()) return;
          e.preventDefault(); e.stopPropagation();
          const t = e.target.value.trim(); e.target.value = "";
          dlg.querySelector("[data-tags]").insertAdjacentHTML("beforeend", '<span class="chip" data-tag="' + esc(t) + '">' + esc(t) +
            '<button type="button" class="chip-x" aria-label="' + esc(PD.t("fm.untag", { tag: t })) + '">×</button></span>');
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
        // THE FALSE MIRROR'S ACTIONS in a menu at the top right: New notebook, New folder, Import
        root.innerHTML = '<div class="page-head"><h1>' + esc(label) + "</h1>" + (fm ? '<span class="head-acts"><button type="button" class="icon-btn" data-act="fm-menu" aria-haspopup="menu" aria-expanded="false" title="' +
          esc(PD.t("fm.menu")) + '" aria-label="' + esc(PD.t("fm.menu")) + '">' + ICON.menu + '</button><span class="head-menu" role="menu" hidden>' +
          '<button type="button" role="menuitem" data-act="new-notebook">' + esc(PD.t("fm.new_notebook")) + "</button>" +
          '<button type="button" role="menuitem" data-act="new-folder">' + esc(PD.t("fm.new_folder")) + "</button>" +
          '<button type="button" role="menuitem" data-act="import">' + esc(PD.t("fm.import")) + "</button></span></span>" : "") + "</div>" +
          (fm ? '<p class="hint import-msg" id="' + id + '-import" role="status"></p><div class="pick-menu" id="' + id + '-menu" role="toolbar"></div>' +
                '<div class="drop-here" id="' + id + '-drop" hidden>' + esc(PD.t("fm.drop")) + "</div>" : "") +
          '<div class="lib-box" id="' + id + '-files"></div>';
        PD.on(root, "click", "[data-at]", (e, el) => { if (S.held) { S.held = false; return; } if (S.picked) { unpick(); } S.at = el.dataset.at; paint(); });
        PD.on(root, "click", "[data-open]", (e, el) => { if (S.held) { S.held = false; return; } if (S.picked) { unpick(); return; } openDoc(el.dataset.open); });
        if (!fm) return;
        const menu = $(".head-menu", root), menuBtn = $("[data-act=fm-menu]", root);
        const closeMenu = () => { menu.hidden = true; menuBtn.setAttribute("aria-expanded", "false"); };
        PD.on(root, "click", "[data-act=fm-menu]", () => { menu.hidden = !menu.hidden; menuBtn.setAttribute("aria-expanded", String(!menu.hidden)); });
        document.addEventListener("click", e => { if (!menu.hidden && !e.target.closest(".head-acts")) closeMenu(); });
        root.addEventListener("keydown", e => { if (e.key === "Escape" && !menu.hidden) closeMenu(); });
        // Esc puts the selection's menu away (it has no close button)
        document.addEventListener("keydown", e => {
          if (e.key === "Escape" && S.picked && !R.hidden && !document.querySelector("dialog[open]")) unpick();
        });
        PD.on(root, "click", "[data-act=new-notebook]", () => { closeMenu(); newNotebook(); });
        PD.on(root, "click", "[data-act=new-folder]", () => { closeMenu(); newFolder(); });
        PD.on(root, "click", "[data-act=import]", () => { closeMenu(); importFile(); });
        PD.on(root, "click", "[data-pick-act]", (e, el) => pickAct(el.dataset.pickAct));
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
        root.addEventListener("contextmenu", e => { if (e.target.closest("[data-item]")) e.preventDefault(); });
      },
      show() { load(); loadProgress(); },
      hide() { if (S.picked) unpick(); },
      poll(n) {
        loadProgress();
        if (fm) { if (n % 5 === 0 && !S.picked) load(); return; }       // the daemon's answers appear as they land
        const b = PD.mirrorState(PD.status).building;
        if ((b && n % 3 === 0) || (!b && S.pulling)) load();
        S.pulling = b;
      },
    });
  }

  library("tablet", { label: PD.t("tablet.label"), base: "", fm: false });
  library("fmirror", { label: PD.t("fm.label"), base: "/fm", fm: true });
})();
