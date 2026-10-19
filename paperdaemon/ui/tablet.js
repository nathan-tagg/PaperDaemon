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
    }

    // ---- the viewer, as the tablet has it: one page at a time, a grid of all the pages, the chapters

    const pageCount = () => Math.max(1, (S.doc && S.doc.pages) || 1);

    function paintBar() {
      const dlg = $("#" + VIEWER); if (!dlg || !S.doc) return;
      const n = pageCount();
      $(".viewer-title", dlg).textContent = S.doc.name;
      const pt = S.view === "page" ? ((S.tags && S.tags.page_tags && S.tags.page_tags[S.page - 1]) || []) : [];
      // the false mirror's page tags are its own to change: a cross on each, and a box for a new one
      $(".viewer-tags", dlg).innerHTML = pt.map(t => '<span class="chip">' + esc(t) + (fm && S.view === "page"
        ? '<button type="button" class="chip-x" data-untag="' + esc(t) + '" aria-label="' + esc(PD.t("fm.untag", { tag: t })) + '">×</button>' : "") + "</span>").join("") +
        (fm && S.view === "page" ? '<input class="field tag-add" data-tag-add spellcheck="false" placeholder="' + esc(PD.t("fm.tag_add")) + '" aria-label="' + esc(PD.t("fm.tag_add")) + '">' : "");
      const tool = (v, l) => '<button type="button" class="icon-btn" data-v="' + v + '" aria-pressed="' + (S.view === v) + '" title="' + l + '" aria-label="' + l + '">' + ICON[v] + "</button>";
      $(".viewer-tools", dlg).innerHTML = tool("pages", PD.t("viewer.pages")) + ((S.chapters || []).length ? tool("chapters", PD.t("viewer.chapters")) : "") +
        (S.view !== "page" ? '<label class="viewer-goto">' + esc(PD.t("viewer.goto", { last: PD.n(n) })) +
          '<input class="field num" type="number" data-goto min="1" max="' + n + '" step="1" value="' + S.page + '" aria-label="' +
          esc(PD.t("viewer.goto_aria", { last: n })) + '"></label>' : "");
      $(".viewer-nav", dlg).innerHTML = S.view === "page"
        ? '<button type="button" class="btn small" data-v="prev" aria-label="' + esc(PD.t("viewer.prev")) + '"' + (S.page <= 1 ? " disabled" : "") + ">‹</button>" +
          '<span class="viewer-count">' + esc(PD.t("tablet.page_of", { page: S.page, pages: n })) + "</span>" +
          '<button type="button" class="btn small" data-v="next" aria-label="' + esc(PD.t("viewer.next")) + '"' + (S.page >= n ? " disabled" : "") + ">›</button>" +
          (fm && S.doc.kind === "notebook" ? '<button type="button" class="btn small" data-v="newpage" title="' + esc(PD.t("fm.new_page")) + '">' + esc(PD.t("fm.new_page")) + "</button>" : "")
        : "";
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
      if (fm && S.doc.kind === "notebook") {
        body.className = "viewer-page editing";
        body.innerHTML = '<iframe class="page-editor" title="' + esc(PD.t("viewer.page", { n: S.page })) + '" src="/ui/editor.html#doc=' +
          encodeURIComponent(S.doc.id) + "&page=" + S.page + "&base=" + encodeURIComponent(base) + '"></iframe>';
        return;
      }
      body.className = "viewer-page";
      body.innerHTML = '<span class="page-frame"><img alt=""></span>';
      const img = $("img", body), frame = $(".page-frame", body), want = S.page, d = S.doc.id;
      const stale = () => want !== S.page || !S.doc || S.doc.id !== d || S.view !== "page";
      const shown = await PD.loadImage(img, base + "/library/" + d + "/page/" + want + ".png", { holder: body, stale,
        giveUp: h => { h.innerHTML = '<p class="sub viewer-wait">' + esc(PD.t("viewer.not_drawn")) + ' <button type="button" class="link-btn" data-v="retry">' +
          esc(PD.t("common.try_again")) + "</button></p>"; } });
      if (!shown || stale()) return;
      img.alt = PD.t("viewer.page", { n: want });
      const h = body.clientHeight - 32, w = body.clientWidth - 32;
      img.style.width = Math.min(w, h * 0.75, img.naturalWidth) + "px";
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
      if (d) { S.tags = d; paintBar(); }
    }

    function openDoc(x) {
      S.doc = byId(x); S.page = 1; S.tags = null; S.chapters = null; S.hist = [1]; S.hpos = 0;
      S.view = PD.firstTab === "pages" || PD.firstTab === "chapters" ? PD.firstTab : "page"; PD.firstTab = "";
      let dlg = $("#" + VIEWER);
      if (!dlg) {
        dlg = document.createElement("dialog");
        dlg.id = VIEWER; dlg.className = "viewer";
        dlg.innerHTML = '<div class="viewer-head"><span class="viewer-title"></span><button type="button" class="link-btn" data-v="close">' + esc(PD.t("common.close")) + "</button></div>" +
          '<div class="viewer-bar"><span class="viewer-tools"></span><span class="viewer-tags"></span><span class="viewer-nav"></span></div>' +
          '<div class="viewer-page" tabindex="-1" autofocus></div>';
        dlg.addEventListener("click", async e => {
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
          else if (v === "newpage") {
            const [got] = await PD.safe(api("POST", "/library/" + S.doc.id + "/pages", { after: S.page }));
            if (got) { S.doc.pages = (S.doc.pages || 1) + 1; go(got.page); }
          }
          else if (v === "pages" || v === "chapters") { S.view = S.view === v ? "page" : v; paintBar(); paintBody(); }
        });
        dlg.addEventListener("keydown", e => {
          if (e.target.matches("[data-tag-add]")) {
            if (e.key === "Enter" && e.target.value.trim()) { const t = e.target.value.trim(); e.preventDefault(); pageTags(now => now.concat([t])); }
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
        dlg.addEventListener("close", () => { if (fm) load(); });
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

    // IMPORT: one button; its dialog holds what there is to choose. What it imports lands in the folder open.
    function importFile() {
      const here = S.at ? (byId(S.at) || {}).name : PD.t("tablet.my_files");
      const dlg = ask(PD.t("fm.import"), '<p>' + esc(PD.t("fm.import_into", { folder: here })) + '</p><label class="field-row"><span>' + esc(PD.t("fm.file")) +
        '</span><input class="field" type="file" accept=".pdf,application/pdf" data-file></label>' + nameField(""), PD.t("fm.import"), async d => {
        const f = d.querySelector("[data-file]").files[0];
        if (!f) throw new Error(PD.t("fm.choose_file"));
        await PD.apiRaw("POST", base + "/library/import?name=" + encodeURIComponent(d.querySelector("[data-name]").value || f.name.replace(/\.pdf$/i, "")) +
          "&parent=" + encodeURIComponent(S.at), await f.arrayBuffer(), "application/pdf");
        await load();
      });
      dlg.querySelector("[data-file]").addEventListener("change", e => {
        const f = e.target.files[0], n = dlg.querySelector("[data-name]");
        if (f && !n.value) n.value = f.name.replace(/\.pdf$/i, "");
      });
    }

    // THE MENU OF WHAT IS SELECTED slides down over the top of the screen, as the tablet's does: nothing under it moves
    function pick(x) {
      S.picked = x; paint();
      const it = byId(x); if (!it) return;
      const m = $("#" + id + "-menu", R);
      const btn = (act, l, cls) => '<button type="button" class="btn' + (cls ? " " + cls : "") + '" data-pick-act="' + act + '">' + esc(l) + "</button>";
      m.innerHTML = '<span class="pick-name">' + esc(it.name) + '</span><span class="pick-acts">' +
        (it.type === "document" ? btn("export", PD.t("fm.export")) : "") + btn("move", PD.t("fm.move")) + btn("tags", PD.t("fm.tags")) +
        btn("delete", PD.t("common.delete"), "danger") + '<button type="button" class="link-btn" data-pick-act="close">' + esc(PD.t("common.close")) + "</button></span>" +
        '<p class="hint pick-msg" role="status"></p>';
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
        root.innerHTML = '<div class="page-head"><h1>' + esc(label) + "</h1>" + (fm ? '<span class="head-acts">' +
          '<button type="button" class="btn" data-act="new-notebook">' + esc(PD.t("fm.new_notebook")) + "</button>" +
          '<button type="button" class="btn" data-act="new-folder">' + esc(PD.t("fm.new_folder")) + "</button>" +
          '<button type="button" class="btn" data-act="import">' + esc(PD.t("fm.import")) + "</button></span>" : "") + "</div>" +
          (fm ? '<div class="pick-menu" id="' + id + '-menu" role="toolbar"></div>' : "") +
          '<div class="lib-box" id="' + id + '-files"></div>';
        PD.on(root, "click", "[data-at]", (e, el) => { if (S.held) { S.held = false; return; } if (S.picked) { unpick(); } S.at = el.dataset.at; paint(); });
        PD.on(root, "click", "[data-open]", (e, el) => { if (S.held) { S.held = false; return; } if (S.picked) { unpick(); return; } openDoc(el.dataset.open); });
        if (!fm) return;
        PD.on(root, "click", "[data-act=new-notebook]", () => newNotebook());
        PD.on(root, "click", "[data-act=new-folder]", () => newFolder());
        PD.on(root, "click", "[data-act=import]", () => importFile());
        PD.on(root, "click", "[data-pick-act]", (e, el) => pickAct(el.dataset.pickAct));
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
      show() { load(); },
      hide() { if (S.picked) unpick(); },
      poll(n) {
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
