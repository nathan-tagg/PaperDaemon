"use strict";
/* Tablet: the library as the tablet shows it. My files at the root, the breadcrumb of the open folder, its folders,
   then its notebooks and documents as covers. A notebook opens in a viewer the height of the window, one page at
   a time. Everything is drawn from the Mirror. */
(() => {
  const { $, esc } = PD;
  let R = null, seen = null;
  const S = { list: null, err: "", at: "", doc: null, page: 1, view: "page", tags: null, chapters: null, hist: [1], hpos: 0 };

  const byId = id => (S.list || []).find(x => x.id === id);

  function path(id) {
    const out = [];
    for (let x = byId(id), n = 0; x && n < 20; x = byId(x.parent), n++) out.unshift(x);
    return out;
  }

  /** Where the reader is: a book's share read (its last open page of its pages), a PDF's or a notebook's page. */
  function where(b) {
    const n = b.pages || 0, at = b.at_page || 1;
    if (!n) return "";
    // as the tablet shows it: a book (EPUB) by the share read, a PDF or a notebook by its page
    if (b.kind === "epub") return PD.t("tablet.read", { pct: n > 1 ? Math.round(100 * (at - 1) / (n - 1)) : 100 });
    return PD.t("tablet.page_of", { page: PD.n(at), pages: PD.n(n) });
  }

  function cover(img) {
    return PD.loadImage(img, "/library/" + img.dataset.id + "/cover.png",
                        { tries: 4, giveUp: () => img.closest(".doc-card").classList.add("nocover") });
  }

  function paint() {
    const box = $("#tb-files", R); if (!box) return;
    if (S.err) { box.innerHTML = '<p class="msg err">' + esc(S.err) + "</p>"; return; }
    if (!S.list) { box.innerHTML = '<p class="sub">' + esc(PD.t("common.reading")) + "</p>"; return; }
    const crumbs = [{ id: "", name: PD.t("tablet.my_files") }].concat(path(S.at));
    const here = S.list.filter(x => x.parent === S.at && x.parent !== "trash");
    const folders = here.filter(x => x.type === "folder"), docs = here.filter(x => x.type === "document");
    box.innerHTML =
      '<nav class="crumbs" aria-label="' + esc(PD.t("tablet.folder")) + '">' + crumbs.map((c, i) => i === crumbs.length - 1
        ? '<span aria-current="page">' + esc(c.name) + "</span>"
        : '<button type="button" class="link-btn crumb" data-at="' + esc(c.id) + '">' + esc(c.name) + "</button>").join('<span class="sep">›</span>') + "</nav>" +
      (folders.length ? '<div class="folders">' + folders.map(f =>
        '<button type="button" class="folder" data-at="' + esc(f.id) + '"><svg viewBox="0 0 24 20" aria-hidden="true"><path d="M1 3a2 2 0 0 1 2-2h6l2 3h10a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2z"/></svg>' +
        "<span>" + esc(f.name) + "</span></button>").join("") + "</div>" : "") +
      (docs.length ? '<div class="doc-grid">' + docs.map(b =>
        '<button type="button" class="doc-card" data-open="' + esc(b.id) + '"><span class="cover"><img alt="" data-id="' + esc(b.id) + '">' +
        ((b.tags || []).length ? '<span class="cover-tags">' + b.tags.map(t => '<span class="chip">' + esc(t) + "</span>").join("") + "</span>" : "") + "</span>" +
        '<span class="name">' + esc(b.name) + '</span><span class="meta">' + esc(where(b)) + "</span></button>").join("") + "</div>" : "") +
      (!folders.length && !docs.length ? '<p class="sub">' + esc(PD.t(PD.mirrorState(PD.status).building ? "tablet.arriving" : "tablet.empty")) + "</p>" : "");
    if (seen) seen.disconnect();
    seen = new IntersectionObserver(es => es.forEach(x => { if (x.isIntersecting) { seen.unobserve(x.target); cover(x.target); } }), { rootMargin: "400px" });
    box.querySelectorAll("img[data-id]").forEach(img => seen.observe(img));
  }

  // ---- the notebook viewer, as the tablet has it: one page at a time, a grid of all the pages, the chapters

  const ICON = {
    pages: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="1.5" width="5.5" height="5.5"/><rect x="9" y="1.5" width="5.5" height="5.5"/><rect x="1.5" y="9" width="5.5" height="5.5"/><rect x="9" y="9" width="5.5" height="5.5"/></svg>',
    chapters: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="2.5" cy="3.5" r="1.2"/><circle cx="2.5" cy="8" r="1.2"/><circle cx="2.5" cy="12.5" r="1.2"/><path d="M6 3.5h8.5M6 8h8.5M6 12.5h8.5"/></svg>',
  };
  const pageCount = () => Math.max(1, (S.doc && S.doc.pages) || 1);

  function paintBar() {
    const dlg = $("#tb-viewer"); if (!dlg || !S.doc) return;
    const n = pageCount();
    $(".viewer-title", dlg).textContent = S.doc.name;
    const pt = S.view === "page" ? ((S.tags && S.tags.page_tags && S.tags.page_tags[S.page - 1]) || []) : [];
    $(".viewer-tags", dlg).innerHTML = pt.map(t => '<span class="chip">' + esc(t) + "</span>").join("");
    const tool = (v, label) => '<button type="button" class="icon-btn" data-v="' + v + '" aria-pressed="' + (S.view === v) + '" title="' + label + '" aria-label="' + label + '">' + ICON[v] + "</button>";
    // pages, then chapters, at the left; over the grid or the chapters, the page to go to; over a page, the paginator
    $(".viewer-tools", dlg).innerHTML = tool("pages", PD.t("viewer.pages")) + ((S.chapters || []).length ? tool("chapters", PD.t("viewer.chapters")) : "") +
      (S.view !== "page" ? '<label class="viewer-goto">' + esc(PD.t("viewer.goto", { last: PD.n(n) })) +
        '<input class="field num" type="number" data-goto min="1" max="' + n + '" step="1" value="' + S.page + '" aria-label="' +
        esc(PD.t("viewer.goto_aria", { last: n })) + '"></label>' : "");
    $(".viewer-nav", dlg).innerHTML = S.view === "page"
      ? '<button type="button" class="btn small" data-v="prev" aria-label="' + esc(PD.t("viewer.prev")) + '"' + (S.page <= 1 ? " disabled" : "") + ">‹</button>" +
        '<span class="viewer-count">' + esc(PD.t("tablet.page_of", { page: S.page, pages: n })) + "</span>" +
        '<button type="button" class="btn small" data-v="next" aria-label="' + esc(PD.t("viewer.next")) + '"' + (S.page >= n ? " disabled" : "") + ">›</button>"
      : "";
  }

  /** The page typed into Go to page, held to the document's range: Enter goes there, anything else is marked. */
  function goTyped(input) {
    const n = pageCount(), k = Number(input.value);
    if (Number.isInteger(k) && k >= 1 && k <= n) { go(k); return; }
    input.setAttribute("aria-invalid", "true");
    input.select();
  }

  async function paintBody() {
    const dlg = $("#tb-viewer"); if (!dlg || !S.doc) return;
    const body = $(".viewer-page", dlg), n = pageCount();
    body.scrollTop = 0;
    if (S.view === "pages") {
      body.className = "viewer-page grid";
      body.innerHTML = Array.from({ length: n }, (_, i) => '<button type="button" class="thumb' + (i + 1 === S.page ? " here" : "") + '" data-go="' + (i + 1) + '">' +
        '<span class="cover"><img alt="" data-thumb="' + (i + 1) + '"></span><span class="meta">' + (i + 1) + "</span></button>").join("");
      const id = S.doc.id, io = new IntersectionObserver(es => es.forEach(x => {
        if (!x.isIntersecting) return;
        io.unobserve(x.target);
        PD.loadImage(x.target, "/library/" + id + "/thumb/" + x.target.dataset.thumb + ".png",
                     { stale: () => !S.doc || S.doc.id !== id || S.view !== "pages" });
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
    body.className = "viewer-page";
    body.innerHTML = '<span class="page-frame"><img alt=""></span>';
    const img = $("img", body), frame = $(".page-frame", body), want = S.page, id = S.doc.id;
    const stale = () => want !== S.page || !S.doc || S.doc.id !== id || S.view !== "page";
    const shown = await PD.loadImage(img, "/library/" + id + "/page/" + want + ".png", { holder: body, stale,
      giveUp: h => { h.innerHTML = '<p class="sub viewer-wait">' + esc(PD.t("viewer.not_drawn")) + ' <button type="button" class="link-btn" data-v="retry">' +
        esc(PD.t("common.try_again")) + "</button></p>"; } });
    if (!shown || stale()) return;
    img.alt = PD.t("viewer.page", { n: want });
    // every page at the size a standard page fills the viewer; a taller page runs on below and scrolls
    const h = body.clientHeight - 32, w = body.clientWidth - 32;
    img.style.width = Math.min(w, h * 0.75, img.naturalWidth) + "px";
    // THE PAGE'S LINKS, as the tablet follows them: a link to another page goes there, a web link opens the browser
    const [got] = await PD.safe(PD.api("GET", "/library/" + id + "/links/" + want));
    if (stale() || !got || !got.links || !got.links.length) return;
    // the file's page is the picture's full width and its top; ink written past its foot makes the picture taller
    const k = got.aspect ? Math.min(1, img.naturalWidth * got.aspect / img.naturalHeight) : 1;
    frame.insertAdjacentHTML("beforeend", got.links.map(l => {
      const [x0, a, x1, b] = l.box, y0 = a * k, y1 = b * k;
      const where = 'style="left:' + (x0 * 100) + "%;top:" + (y0 * 100) + "%;width:" + ((x1 - x0) * 100) + "%;height:" + ((y1 - y0) * 100) + '%"';
      return l.go ? '<button type="button" class="page-link" data-go="' + l.go + '" title="' + esc(PD.t("viewer.page", { n: l.go })) + '" aria-label="' + esc(PD.t("viewer.go_to", { n: l.go })) + '" ' + where + "></button>"
        : '<button type="button" class="page-link" data-uri="' + esc(l.uri) + '" title="' + esc(l.uri) + '" aria-label="Open ' + esc(l.uri) + '" ' + where + "></button>";
    }).join(""));
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
    paintBar(); paintBody();
  }

  function walk(step) {
    const dlg = $("#tb-viewer");
    if (!dlg || !dlg.open) return false;
    const at = S.hpos + step;
    if (at < 0) { dlg.close(); return true; }                // back from the first page opened leaves the notebook
    if (at >= S.hist.length) return true;                     // nothing ahead: stay
    S.hpos = at;
    go(S.hist[at], true);
    return true;
  }

  function openDoc(id) {
    S.doc = byId(id); S.page = 1; S.tags = null; S.chapters = null; S.hist = [1]; S.hpos = 0;
    S.view = PD.firstTab === "pages" || PD.firstTab === "chapters" ? PD.firstTab : "page"; PD.firstTab = "";
    let dlg = $("#tb-viewer");
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "tb-viewer"; dlg.className = "viewer";
      dlg.innerHTML = '<div class="viewer-head"><span class="viewer-title"></span><button type="button" class="link-btn" data-v="close">' + esc(PD.t("common.close")) + "</button></div>" +
        '<div class="viewer-bar"><span class="viewer-tools"></span><span class="viewer-tags"></span><span class="viewer-nav"></span></div>' +
        '<div class="viewer-page" tabindex="-1" autofocus></div>';
      dlg.addEventListener("click", e => {
        const g = e.target.closest("[data-go]");
        if (g) { go(Number(g.dataset.go)); return; }
        const u = e.target.closest("[data-uri]");
        if (u) { PD.api("POST", "/open-link", { url: u.dataset.uri }); return; }
        const b = e.target.closest("[data-v]");
        if (!b) { if (e.target === dlg) dlg.close(); return; }
        const v = b.dataset.v;
        if (v === "close") dlg.close();
        else if (v === "prev" || v === "next") go(S.page + (v === "next" ? 1 : -1));
        else if (v === "retry") paintBody();
        else if (v === "pages" || v === "chapters") { S.view = S.view === v ? "page" : v; paintBar(); paintBody(); }
      });
      dlg.addEventListener("keydown", e => {
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
    paintBar(); paintBody();
    PD.safe(PD.api("GET", "/library/" + id)).then(([d]) => { if (S.doc && S.doc.id === id) { S.tags = d; paintBar(); } });
    PD.safe(PD.api("GET", "/library/" + id + "/chapters")).then(([c]) => {
      if (!S.doc || S.doc.id !== id) return;
      S.chapters = Array.isArray(c) ? c : [];
      paintBar();
      if (S.view === "chapters") paintBody();       // the list was waiting for them
    });
  }

  async function load() {
    const [list, e] = await PD.safe(PD.api("GET", "/library"));
    S.err = e ? PD.errText(e) : ""; S.list = list || [];
    if (S.at && !byId(S.at)) S.at = "";
    paint();
    if (PD.firstOpen && byId(PD.firstOpen)) { const id = PD.firstOpen; PD.firstOpen = ""; openDoc(id); }
  }

  PD.screen("tablet", {
    label: PD.t("tablet.label"), group: 1,
    rail(st) {
      const t = st.tablet;
      if (!t) return "";
      const m = PD.mirrorState(st);                  // while the Mirror builds, its meter takes the label's place
      if (m.building) return '<span class="step-meter" title="' + esc(PD.t("su.building_pct", { pct: m.pct })) + '"><span class="bar" aria-hidden="true"><i style="width:' + m.pct + '%"></i></span><span class="pct">' + m.pct + "%</span></span>";
      return t.set ? esc(PD.t("settings.login.connected")) : PD.mk("fail") + esc(PD.t("settings.login.none"));     // connected needs no mark; a problem does
    },
    mount(root) {
      R = root;
      root.innerHTML = '<div class="page-head"><h1>' + esc(PD.t("tablet.label")) + '</h1></div><div id="tb-files"></div>';
      PD.on(root, "click", "[data-at]", (e, el) => { S.at = el.dataset.at; paint(); });
      PD.on(root, "click", "[data-open]", (e, el) => openDoc(el.dataset.open));
    },
    show() { load(); },
    poll(n) {
      // notebooks appear as they arrive, and once more when the update is done, so its last changes show too
      const b = PD.mirrorState(PD.status).building;
      if ((b && n % 3 === 0) || (!b && S.pulling)) load();
      S.pulling = b;
    },
  });
})();
