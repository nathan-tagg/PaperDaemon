// The tablet book: every screen of the mockups, in each state its controls reach, as pages of one PDF,
// with every control a link to the page that shows what it does. tools/mockup_book.py writes book.html
// with each screen inlined as a <template data-screen>, loads mockup.js in book mode, and prints it.
//
//   states   from each screen's defaults, every control's effect first and combinations after, up to
//            CAP. A control whose result is past the cap links to the nearest state that shows it.
//   parts    a screen taller than a page runs over consecutive pages, broken between elements, with
//            scroll links above and below, so swiping to the next page scrolls. Each part keeps only
//            its own elements, so print lays it out afresh
//   overlays a dialog or an open menu is its own page over its screen, dimmed
//   links    a transparent link inside each control, so it lands wherever print puts the control
(async () => {
  const M = window.Mockup;
  const W = 1160, H = 1547;                 // a page: the tablet's 3:4 at the mockups' window width
  const PAD = 40;                           // the strip above or below a part, for its scroll link
  const CAP = 26;                           // states per screen
  const OVERLAY_CAP = 36;                   // dialog and menu pages per screen
  const ATOMS = [".page-head", ".section > h2", ".section > header", ".section-note", ".row", "tr", ".result",
    ".entry", ".day", ".cut", ".facts > dt", ".facts > dd", ".actions", ".notice", ".drop", ".figure", "pre",
    ".code", ".empty", ".now", ".booklist li", ".padhead", ".spread", ".step > *", ".run-steps li", ".addr",
    ".how", "p", "h1", "h2", "h3", "table thead"].join(",");
  const KEEP = ".section > h2, .section > header, .section-note, table thead, .day, h3, .step > h2";
  const CLICK = "button, a[href], a[data-href], input.switch, select[data-name], [data-set], [data-flip], [data-open], [data-close]";
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const key = (st) => Object.keys(st).sort().map((k) => k + "=" + st[k]).join("&");
  const visible = (el) => el.getClientRects().length > 0;

  await document.fonts.ready;
  const book = document.getElementById("book");
  const stage = document.createElement("div");
  stage.className = "bk-stage";
  document.body.append(stage);

  // ---- screens, each laid out once in the stage and then re-dressed for every state
  const screens = $$("template[data-screen]").map((t, i) => {
    const master = document.createElement("div");
    master.append(t.content.cloneNode(true));
    stage.append(master);
    let n = 0;
    master.querySelectorAll("*").forEach((el) => { el.dataset.bk = String(n++); });
    $$(".code", master).forEach((c) => {           // mockup.js numbers these in the live pages
      const ta = c.querySelector("textarea"), g = c.querySelector(".gutter");
      if (ta && g) g.textContent = ta.value.split("\n").map((_, j) => j + 1).join("\n");
    });
    const app = master.querySelector(".app, .firstrun");
    return {
      id: t.dataset.screen, title: t.dataset.title, file: t.dataset.file, index: i, master, app,
      main: app.querySelector("main"), def: M.defaults(master),
      dialogs: Object.fromEntries($$("dialog", master).map((d) => [d.id, d])),
      states: new Map(), order: [], layouts: new Map(), overlays: new Map(),
    };
  });
  const byFile = Object.fromEntries(screens.map((s) => [s.file, s]));
  const dead = [];
  let nextId = 1;

  // ---- which states each screen reaches
  const shown = (el, root) => { for (let e = el; e && e !== root; e = e.parentElement) if (e.hidden) return false; return true; };

  function nextsOf(scr, st) {
    M.apply(scr.master, st);
    const out = [];
    for (const el of clickables(scr.app)) {
      if (el.matches("select[data-name]")) {
        [...el.options].filter((o) => !o.disabled).forEach((o) => out.push({ ...st, [el.dataset.name]: o.value }));
        continue;
      }
      const r = M.act(el, st);
      if (!r || r.go || !r.state) continue;
      if (!r.open) { out.push(r.state); continue; }
      const dlg = scr.dialogs[r.open];
      if (!dlg) continue;
      M.apply(scr.master, r.state);
      $$(CLICK, dlg).filter((b) => shown(b, dlg)).forEach((b) => {
        const rr = M.act(b, r.state);
        if (rr?.state && rr.close && b.hasAttribute("data-then")) out.push(rr.state);
      });
      M.apply(scr.master, st);
    }
    return out;
  }

  // Every control's effect first, combinations after: the next state taken is the one showing the most
  // key=value pairs no page shows yet, and among equals the one closest to the defaults.
  function explore(scr) {
    const seen = new Set();
    const add = (st) => {
      const k = key(st);
      scr.states.set(k, { st, i: scr.order.length });
      scr.order.push(k);
      Object.entries(st).forEach(([a, b]) => seen.add(a + "=" + b));
    };
    const novel = (st) => Object.entries(st).filter(([a, b]) => !seen.has(a + "=" + b)).length;
    const frontier = new Map();
    const offer = (from, depth) => {
      for (const n of nextsOf(scr, from)) {
        const k = key(n);
        if (!scr.states.has(k) && !frontier.has(k)) frontier.set(k, { st: n, depth, n: frontier.size });
      }
    };
    const before = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i]; return false; };
    add(scr.def);
    offer(scr.def, 1);
    while (frontier.size) {
      let best = null;
      for (const c of frontier.values()) {
        c.score = [-novel(c.st), c.depth, c.n];
        if (!best || before(c.score, best.score)) best = c;
      }
      frontier.delete(key(best.st));
      if (scr.states.size >= CAP) break;
      add(best.st);
      offer(best.st, best.depth + 1);
    }
  }

  // the state that stands in when `want` was never reached: it must show every key the click changed
  function resolve(scr, from, want) {
    const k = key(want);
    if (scr.states.has(k)) return want;
    const changed = Object.keys(want).filter((x) => want[x] !== from[x]);
    let best = null, bestScore = -1;
    for (const kk of scr.order) {
      const c = scr.states.get(kk).st;
      if (!changed.every((x) => c[x] === want[x])) continue;
      const score = Object.keys(want).filter((x) => c[x] === want[x]).length;
      if (score > bestScore) { best = c; bestScore = score; }
    }
    return best;
  }

  // ---- layout and parts
  function clickables(root) {
    const out = [];
    for (let el of $$(CLICK, root)) {
      if (el.matches("input.switch")) {
        if (el.disabled) continue;
        el = el.closest("label") || el;
      }
      if (el.matches("button:disabled") || !visible(el) || out.includes(el)) continue;
      out.push(el);
    }
    return out;
  }

  function layoutOf(scr, st) {
    const k = key(st);
    if (scr.layouts.has(k)) return scr.layouts.get(k);
    M.apply(scr.master, st);
    const top = scr.main.getBoundingClientRect().top;
    const atoms = $$(ATOMS, scr.main).filter(visible).map((el) => {
      const r = el.getBoundingClientRect();
      return [r.top - top, r.bottom - top, el.matches(KEEP)];
    });
    const items = [...scr.main.children].filter(visible);
    const bottom = Math.max(...items.map((el) => el.getBoundingClientRect().bottom - top), 0);
    const height = bottom + parseFloat(getComputedStyle(scr.main).paddingBottom || "0");
    const L = { height, parts: split(height, atoms), bkPart: new Map() };
    scr.layouts.set(k, L);
    return L;
  }

  // a break never cuts an element, and never falls right after a heading, a note or a table's header
  function split(height, atoms) {
    const inside = (y) => atoms.some(([a, b, keep]) => (a < y - 0.5 && b > y + 0.5) || (keep && a < y - 0.5 && y <= b + 28));
    const ys = [...new Set(atoms.flatMap(([a, b]) => [a, b]).map((y) => Math.round(y)))].sort((a, b) => a - b);
    const parts = [];
    let s = 0;
    for (;;) {
      const room = H - (parts.length ? PAD + 72 : 0);          // a continued part starts lower: its scroll link, and padding
      if (height - s <= room) { parts.push([s, height]); break; }
      const limit = s + room - PAD;
      let best = -1;
      for (const y of ys) if (y > s + 120 && y <= limit && !inside(y)) best = y;
      if (best < 0) best = limit;
      parts.push([s, best]);
      s = best;
    }
    return parts;
  }

  function partOf(scr, st, bk) {
    const L = layoutOf(scr, st);
    if (L.parts.length === 1 || bk == null) return 0;
    if (L.bkPart.has(bk)) return L.bkPart.get(bk);
    M.apply(scr.master, st);
    const el = scr.master.querySelector(`[data-bk="${bk}"]`);
    let part = 0;
    if (el && visible(el) && scr.main.contains(el)) {
      const y = el.getBoundingClientRect().top - scr.main.getBoundingClientRect().top;
      part = Math.max(0, L.parts.findIndex(([a, b]) => y >= a - 1 && y < b));
    }
    L.bkPart.set(bk, part);
    return part;
  }

  // ---- page ids, known before any page is built
  const ids = new Map();
  function pageId(scr, st, part) {
    const k = scr.id + "|" + key(st) + "|" + part;
    if (!ids.has(k)) ids.set(k, (key(st) === key(scr.def) && part === 0) ? "s-" + scr.id : "p" + nextId++);
    return ids.get(k);
  }

  // ---- building pages
  // A part keeps only its own elements, so print lays it out from the top by itself: screen and print
  // measure text a little differently, and nothing here depends on where screen put anything.
  function frame(scr, st, part, id) {
    const L = layoutOf(scr, st);
    part = Math.min(part, L.parts.length - 1);
    M.apply(scr.master, st);
    const page = document.createElement("section");
    page.className = "bk-page";
    page.id = id;
    const app = scr.app.cloneNode(true);
    page.append(app);
    book.append(page);
    app.querySelectorAll("a[href]").forEach((a) => { a.dataset.href = a.getAttribute("href"); a.removeAttribute("href"); });
    const main = app.querySelector("main");
    if (L.parts.length > 1) {
      const [s, e] = L.parts[part];
      const top = main.getBoundingClientRect().top;
      const drop = [];
      const sort = (el) => {                         // measure everything first: hiding moves the rest
        for (const k of [...el.children].filter(visible)) {
          const r = k.getBoundingClientRect(), a = r.top - top, b = r.bottom - top;
          if (b <= s + 0.5 || a >= e - 0.5) drop.push(k);
          else if ((a < s - 0.5 || b > e + 0.5) && k.children.length) sort(k);
        }
      };
      sort(main);
      drop.forEach((k) => { k.style.display = "none"; });
      if (part > 0) main.style.paddingTop = PAD + 16 + "px";
    }
    return { page, app, L, part };
  }

  // a link inside the control, so it goes wherever print puts the control
  function attach(el, to) {
    const hit = (host) => {
      if (getComputedStyle(host).position === "static") host.style.position = "relative";
      const a = document.createElement("a");
      a.className = "bk-hit";
      a.href = "#" + to;
      host.append(a);
    };
    if (el.tagName === "A") { el.setAttribute("href", "#" + to); return; }
    if (el.tagName === "TR") {                         // a row: every cell but one holding its own control
      [...el.children].forEach((td) => { if (!td.querySelector(CLICK)) hit(td); });
      return;
    }
    if (el.matches("input, select")) {
      let host = el.closest(".select");
      if (!host) {
        host = document.createElement("span");
        host.className = "bk-wrap";
        el.replaceWith(host);
        host.append(el);
      }
      hit(host);
      return;
    }
    hit(el);
  }
  const say = (el) => (el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 48);

  function targetOf(scr, st, el, part) {
    if (el.matches("select[data-name]")) return overlay(scr, st, { type: "menu", name: el.dataset.name, bk: el.dataset.bk, part, origin: st });
    let r = M.act(el, st);
    const bare = el.closest("a[data-href]");                  // a page's links lose href so only ours print
    if (!r && bare) r = { go: bare.dataset.href };
    if (!r) return null;
    if (r.go) {
      const file = r.go.split("#")[0];
      if (file === "index.html" || file === "") return "contents";
      const to = byFile[file];
      if (!to) return null;
      return pageId(to, to.def, 0);
    }
    if (r.open) {
      const p = partOf(scr, r.state, el.dataset.bk);
      return overlay(scr, r.state, { type: "dialog", id: r.open, bk: el.dataset.bk, part: p, origin: st });
    }
    const t = resolve(scr, st, r.state);
    if (!t) return null;
    return pageId(scr, t, partOf(scr, t, el.dataset.bk));
  }

  function basePage(scr, st, part) {
    const f = frame(scr, st, part, pageId(scr, st, part));
    const n = f.L.parts.length;
    const targets = clickables(f.app).map((el) => [el, targetOf(scr, st, el, f.part)]);
    for (const [el, to] of targets) {
      if (to) attach(el, to);
      else dead.push({ screen: scr.id, state: key(st), control: say(el) });
    }
    if (n > 1) {
      const strip = (cls, text, to) => {
        const d = document.createElement("div");
        d.className = "bk-scroll " + cls;
        d.style.left = f.app.querySelector(".rail").offsetWidth + "px";
        d.textContent = text;
        f.page.append(d);
        attach(d, to);
      };
      if (f.part > 0) strip("up", "↑  Scroll up  ·  part " + (f.part + 1) + " of " + n, pageId(scr, st, f.part - 1));
      if (f.part < n - 1) strip("down", "↓  Scroll down for the rest of this screen  ·  part " + (f.part + 1) + " of " + n, pageId(scr, st, f.part + 1));
    }
  }

  // the keys a dialog's own content shows: an overlay page past the cap may stand in only if they match
  function keysIn(root) {
    const ks = new Set();
    $$("[data-when],[data-class]", root).forEach((el) => {
      [el.dataset.when, ...(el.dataset.class || "").split(";").map((r) => r.slice(r.indexOf(":") + 1))]
        .filter(Boolean).join("&").split("&").forEach((c) => { const m = c.match(/^([^!=]+)/); if (m) ks.add(m[1]); });
    });
    return [...ks];
  }

  const overlayQueue = [];
  function overlay(scr, st, ov) {
    const what = ov.type === "menu" ? "menu:" + ov.name : "dialog:" + ov.id;
    const k = what + "|" + key(st) + "|" + ov.part;
    if (scr.overlays.has(k)) return scr.overlays.get(k).id;
    if (scr.overlays.size >= OVERLAY_CAP) {
      const need = ov.type === "menu" ? [ov.name] : keysIn(scr.dialogs[ov.id]);
      let best = null, bestScore = -1;
      for (const o of scr.overlays.values()) {
        if (o.what !== what || !need.every((x) => o.st[x] === st[x])) continue;
        const score = Object.keys(st).filter((x) => o.st[x] === st[x]).length;
        if (score > bestScore) { best = o; bestScore = score; }
      }
      if (best) return best.id;
    }
    const id = "p" + nextId++;
    scr.overlays.set(k, { id, what, st, ov });
    overlayQueue.push({ scr, st, ov, id });
    return id;
  }

  function overlayPage({ scr, st, ov, id }) {
    const f = frame(scr, st, ov.part, id);
    const shade = document.createElement("div");
    shade.className = "bk-shade";
    f.page.append(shade);
    if (ov.type === "menu") {
      // the menu hangs from its field, so it sits under it wherever print puts the field;
      // a tap on the field again closes it
      const sel = f.app.querySelector(`select[data-name="${ov.name}"]`);
      const host = sel.closest(".select") || sel.parentElement;
      const menu = document.createElement("div");
      menu.className = "bk-menu";
      menu.style.cssText = `left:0;top:calc(100% + 3px);min-width:${sel.offsetWidth}px`;
      const fill = [];
      for (const o of sel.options) {
        const d = document.createElement("div");
        d.textContent = o.textContent;
        if (o.value === st[ov.name]) d.setAttribute("aria-selected", "true");
        if (o.disabled) d.className = "off";
        menu.append(d);
        const t = o.disabled ? null : resolve(scr, st, { ...st, [ov.name]: o.value });
        if (t) fill.push([d, pageId(scr, t, partOf(scr, t, ov.bk))]);
      }
      attach(sel, pageId(scr, resolve(scr, st, ov.origin) || scr.def, ov.part));
      host.append(menu);
      fill.forEach(([d, to]) => attach(d, to));
      return;
    }
    const dlg = scr.dialogs[ov.id];
    M.apply(scr.master, st);
    const sheet = document.createElement("div");
    // the dialog's own classes come along (a "wide" dialog stays wide), and it is centered at its own width
    sheet.className = ["bk-sheet", ...[...dlg.classList].filter((c) => c !== "sheet")].join(" ");
    [...dlg.children].forEach((c) => sheet.append(c.cloneNode(true)));
    sheet.style.top = Math.round(H * 0.24) + "px";
    f.page.append(sheet);
    sheet.style.left = Math.round((W - sheet.offsetWidth) / 2) + "px";
    for (const el of clickables(sheet)) {
      const rr = M.act(el, st);
      if (!rr?.state) { dead.push({ screen: scr.id, state: "dialog " + ov.id, control: say(el) }); continue; }
      const t = el.hasAttribute("data-then") ? resolve(scr, st, rr.state) : (resolve(scr, ov.origin, ov.origin) || scr.def);
      if (t) attach(el, pageId(scr, t, partOf(scr, t, ov.bk)));
    }
  }

  // ---- the first page
  function cover(total) {
    const page = document.createElement("section");
    page.className = "bk-page bk-cover";
    page.id = "contents";
    const rows = screens.map((s, i) => `<li><a href="#s-${s.id}"><span class="n">${String(i + 1).padStart(2, "0")}</span><span><span class="t">${s.title}</span><span class="d">${s.blurb || ""}</span></span><span class="go">›</span></a></li>`).join("");
    page.innerHTML = `<span class="wordmark">PaperDaemon</span>
      <h1>The whole app, as a mockup</h1>
      <p class="lead">Every button, switch, tab, menu and link here is a link. Tap one and the page turns to what it does. Tap PaperDaemon at the top left of a screen to come back to this page.</p>
      <p class="lead">A long screen runs over two pages, so swiping to the next page scrolls it. Everything here is invented example data; nothing talks to an engine.</p>
      <ol class="toc">${rows}</ol>
      <p class="meta foot num">${total.pages} pages · ${total.links} links · built from docs/design/mockups</p>`;
    book.prepend(page);
    return page;
  }

  // ---- build
  screens.forEach(explore);
  screens.forEach((scr) => scr.order.forEach((k) => {
    const st = scr.states.get(k).st;
    layoutOf(scr, st).parts.forEach((_, p) => pageId(scr, st, p));
  }));
  for (const scr of screens) {
    scr.blurb = scr.master.querySelector("main .page-head p, main > p.sub")?.textContent.replace(/\s+/g, " ").trim() || "";
    for (const k of scr.order) {
      const st = scr.states.get(k).st;
      layoutOf(scr, st).parts.forEach((_, p) => basePage(scr, st, p));
    }
    while (overlayQueue.length) overlayPage(overlayQueue.shift());
  }
  stage.remove();
  const total = { pages: book.children.length + 1, links: 0 };
  cover(total);
  total.links = $$("a[href^='#']", book).length;
  book.querySelector("#contents .foot").textContent = `${total.pages} pages · ${total.links} links · built from docs/design/mockups`;

  const map = document.createElement("script");
  map.type = "application/json";
  map.id = "bk-map";
  map.textContent = JSON.stringify({
    pages: total.pages, links: total.links,
    screens: screens.map((s) => ({ id: s.id, title: s.title, states: s.order.length, overlays: s.overlays.size })),
    outline: [{ title: "Contents", id: "contents" }, ...screens.map((s) => ({ title: s.title, id: "s-" + s.id }))],
    dead,
  });
  document.body.append(map);
  document.documentElement.dataset.built = "yes";
})();
