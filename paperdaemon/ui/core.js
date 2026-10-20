"use strict";
/* The core of the PaperDaemon window: the API client, formatting, dialogs, and the registry the screens
   plug into. Plain JavaScript, no build step, nothing from the network. */
(() => {
  const PD = (window.PD = { screens: {}, order: [], prefetch: [], missing: new Set(), status: null, settings: null });

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  Object.assign(PD, { $, $$, esc });

  // NOTHING DRAGS BUT WHAT IS MADE TO: a press that moves on a link, a picture or text already selected would start the
  // browser's own drag, which nothing in the window takes -- a crossed-out circle for a cursor instead of a selection.
  // Only an element marked draggable="true" (the grips that reorder) starts one; files dragged in from outside still drop.
  document.addEventListener("dragstart", e => {
    if (!(e.target instanceof Element && e.target.closest('[draggable="true"]'))) e.preventDefault();
  });

  // ---- THE INTERFACE'S WORDS: every piece of text the window shows comes from ui/strings/strings-<language>.xml
  // through PD.t(name, values). English is the source; a string a translation lacks falls back to it. They are read
  // before any screen's script runs (the screens build some of their text as they load), from this same engine.
  const LANG_KEY = "pd-lang";
  PD.lang = (() => { try { return localStorage.getItem(LANG_KEY) || "en"; } catch (e) { return "en"; } })();
  const readStrings = code => {
    const out = {};
    try {
      const x = new XMLHttpRequest();
      x.open("GET", "/ui/strings/strings-" + code + ".xml", false);
      x.send();
      if (x.status !== 200) return out;
      const doc = new DOMParser().parseFromString(x.responseText, "application/xml");
      doc.querySelectorAll("string").forEach(s => { out[s.getAttribute("name")] = s.textContent; });
    } catch (e) { /* that language is not there: English shows */ }
    return out;
  };
  const EN = readStrings("en");
  const LOCAL = PD.lang === "en" ? EN : readStrings(PD.lang);
  document.documentElement.lang = PD.lang;
  // the languages the window speaks, each named in itself (the engine's settings.LANGUAGES), and those written right
  // to left
  const OWN = { en: "English", es: "Español", pt: "Português", fr: "Français", de: "Deutsch", cy: "Cymraeg", ja: "日本語",
    nb: "Norsk bokmål", zh: "简体中文", ko: "한국어", ar: "العربية", hi: "हिन्दी", bn: "বাংলা", ru: "Русский", ur: "اردو",
    id: "Bahasa Indonesia", it: "Italiano", tr: "Türkçe", vi: "Tiếng Việt" };
  PD.LANGUAGES = Object.keys(OWN);
  document.documentElement.dir = ["ar", "ur"].includes(PD.lang) ? "rtl" : "ltr";
  /** How the language picker shows a language: its own name, then its name in the window's language (from the
      browser's own data, when it has some) where that differs. */
  PD.languageLabel = code => {
    const own = OWN[code] || code, tag = code === "zh" ? "zh-Hans" : code;
    let here = "";
    try { here = new Intl.DisplayNames([PD.lang], { type: "language", fallback: "none" }).of(tag) || ""; } catch (e) { /* none */ }
    here = here && here.charAt(0).toLocaleUpperCase(PD.lang) + here.slice(1);
    return !here || here === own ? own : own + " · " + here;
  };
  /** The interface text `name`, in the user's language, with {placeholders} filled from `values`. */
  PD.t = (name, values) => {
    let s = LOCAL[name] ?? EN[name];
    if (s === undefined) { console.warn("no string named " + name); s = name; }
    return values ? s.replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m)) : s;
  };
  /** The interface text `name` as HTML: the text escaped, then each {placeholder} filled with the ready-made HTML
      in `html` (escape what you put there). */
  PD.tHtml = (name, html) => {
    const s = esc(PD.t(name));
    return html ? s.replace(/\{(\w+)\}/g, (m, k) => (k in html ? String(html[k]) : m)) : s;
  };
  /** A "?" to the right of a label that shows `text` when pointed at or focused (a keyboard reaches it too). */
  /** An empty place: a small line icon for what is missing (what to do about it, where there is something), then the
      words, as ready-made HTML. */
  const EMPTY_ICON = {
    tag: '<path d="M1.5 2.5v5l7 7 6-6-7-7z"/><circle cx="4.5" cy="5.5" r="1"/>',
    notepad: '<rect x="2.5" y="2.5" width="11" height="12" rx="1"/><path d="M5 1v3M8 1v3M11 1v3M5 7.5h6M5 10h6M5 12.5h3.5"/>',
    script: '<path d="M3 1.5h7l3 3v10H3z"/><path d="M10 1.5v3h3M6.5 8 5 9.5 6.5 11M9.5 8 11 9.5 9.5 11"/>',
    checklist: '<path d="M1.5 3.5l1.2 1.2L5 2.4M1.5 8l1.2 1.2L5 6.9M1.5 12.5l1.2 1.2L5 11.4M7.5 3.6h7M7.5 8.1h7M7.5 12.6h7"/>',
    bulb: '<path d="M8 1.5a4.5 4.5 0 0 0-2.6 8.2c.4.3.6.7.6 1.1V12h4v-1.2c0-.4.2-.8.6-1.1A4.5 4.5 0 0 0 8 1.5z"/><path d="M6 13.5h4M6.8 15h2.4"/>',
  };
  PD.empty = (icon, html) => '<div class="empty">' + (EMPTY_ICON[icon] ? '<svg viewBox="0 0 16 16" aria-hidden="true">' + EMPTY_ICON[icon] + "</svg>" : "") +
    "<p>" + html + "</p></div>";
  /** The "needs you" mark: an exclamation in outline, bubble-lettered -- a rounded, tapering bar and a round dot,
      drawn in lines like the lightbulb, never filled. */
  PD.WARN = '<svg viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="M5 3.8a3 3 0 0 1 6 0l-1 5a2 2 0 0 1-4 0z"/>' +
    '<circle pathLength="1" cx="8" cy="13.6" r="1.7"/></svg>';
  PD.helpTip = text => '<button type="button" class="qhelp" aria-label="' + esc(PD.t("common.help")) + ": " + esc(text) +
    '" data-tip="' + esc(text) + '">' + QMARK + "</button>";
  // drawn, so it is centered in its ring whatever the font
  const QMARK = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1.2"/>' +
    '<path d="M6 6.3a2 2 0 1 1 2.9 1.8c-.55.3-.9.7-.9 1.3v.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>' +
    '<circle cx="8" cy="11.9" r=".85" fill="currentColor"/></svg>';
  /** The language chosen in Settings: remembered for the next start, and the window reloaded when it changed. */
  PD.useLanguage = code => {
    code = code || "en";
    if (code === PD.lang) return false;
    try { localStorage.setItem(LANG_KEY, code); } catch (e) { /* kept for this window only */ }
    location.reload();
    return true;
  };

  // ---- the pairing token: it arrives in the URL fragment (never sent to the server) and is kept for this session

  let pair = "";
  const keep = t => { pair = t; try { sessionStorage.setItem("pair", t); } catch (e) { /* kept in memory only */ } };
  (() => {
    const m = location.hash.match(/pair=([^&]+)/);
    if (m) keep(decodeURIComponent(m[1]));
    else { try { pair = sessionStorage.getItem("pair") || ""; } catch (e) { /* none */ } }
    const pane = (location.hash.match(/pane=([a-z0-9-]+)/) || location.hash.match(/^#\/?([a-z0-9-]+)$/) || [])[1] || "";
    PD.firstPane = pane;
    PD.firstOpen = (location.hash.match(/open=([0-9a-fA-F-]{36})/) || [])[1] || "";   // a link straight to a document
    PD.firstTab = (location.hash.match(/tab=([a-z]+)/) || [])[1] || "";               // ... or to a tab of a screen
    if (m) history.replaceState(null, "", location.pathname + (pane ? "#" + pane : ""));
  })();
  PD.pairing = { get token() { return pair; }, set: keep };

  // ---- the API

  class ApiError extends Error {
    constructor(message, status, route, missing) { super(message); this.status = status; this.route = route; this.missing = !!missing; }
  }
  PD.ApiError = ApiError;

  const reason = d => {
    if (!d || typeof d !== "object") return "";
    if (typeof d.error === "string") return d.error;
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.detail)) return d.detail.map(x => (x && x.msg) || x).join("; ");
    if (typeof d.message === "string") return d.message;
    return "";
  };

  PD.api = async (method, path, body) => {
    const route = method + " " + path.split("?")[0];
    const headers = { "Authorization": "Bearer " + pair };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    let r;
    try {
      r = await fetch("/api/v1" + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
      throw new ApiError(PD.t("api.no_answer"), 0, route);
    }
    const text = await r.text();
    let d = {};
    try { d = text ? JSON.parse(text) : {}; } catch (e) { d = { raw: text }; }
    if (r.ok) return d;
    const why = reason(d);
    if (r.status === 401) {
      document.dispatchEvent(new CustomEvent("pd:unpaired"));
      throw new ApiError(PD.t("api.unpaired"), 401, route);
    }
    if ((r.status === 404 || r.status === 405) && (!why || /^(not found|method not allowed)$/i.test(why))) {
      PD.missing.add(route);
      throw new ApiError(PD.t("api.not_offered", { route }), r.status, route, true);
    }
    throw new ApiError(why || (r.status + " " + r.statusText), r.status, route);
  };

  /** A request whose body is raw bytes (an imported file), answered in JSON like PD.api. */
  PD.apiRaw = async (method, path, bytes, type) => {
    const r = await fetch("/api/v1" + path, { method, body: bytes,
      headers: { "Authorization": "Bearer " + pair, "Content-Type": type || "application/octet-stream" } });
    const text = await r.text();
    let d = {};
    try { d = text ? JSON.parse(text) : {}; } catch (e) { d = { raw: text }; }
    if (r.ok) return d;
    throw new ApiError(reason(d) || (r.status + " " + r.statusText), r.status, method + " " + path.split("?")[0]);
  };

  /** [value, error]: never throws, so a screen can show what failed where it failed. */
  PD.safe = async p => { try { return [await p, null]; } catch (e) { return [null, e]; } };
  PD.errText = e => (e && e.message) || String(e || "");

  // ---- settings, fetched when a screen needs them and saved whole (the engine merges over its defaults)

  const unwrap = d => (d && d.settings) || d || {};
  PD.loadSettings = async () => {
    const d = await PD.api("GET", "/settings");
    PD.regionDefaults = (d && d.defaults) || {};               // what the computer's region settings say
    PD.settings = unwrap(d);
    PD.useLanguage(PD.getK(PD.settings, "prefs.language"));     // a language set elsewhere: this window follows it
    return PD.settings;
  };
  PD.saveSettings = async change => {
    const next = structuredClone(await PD.loadSettings());
    change(next);
    PD.settings = unwrap(await PD.api("PUT", "/settings", next));
    return PD.settings;
  };
  PD.getK = (o, k) => k.split(".").reduce((a, p) => (a == null ? a : a[p]), o);

  // the settings schema (GET /settings/schema): every rule and message the screens show comes from it
  PD.loadSchema = async () => {
    if (!PD.schema) PD.schema = Object.fromEntries((await PD.api("GET", "/settings/schema")).fields.map(f => [f.path, f]));
    return PD.schema;
  };
  /** The schema's message when `v` breaks the rule of the setting at `path`, else "". */
  PD.checkField = async (path, v) => {
    const f = (await PD.loadSchema())[path];
    if (!f) return "";
    const bad = (f.type === "text" && (typeof v !== "string" || (f.required && !v.trim()))) ||
      (f.type === "number" && v !== null && (!Number.isFinite(v) || v < f.min || v > f.max)) ||
      (f.type === "integer" && (!Number.isInteger(v) || v < f.min || v > f.max)) ||
      (f.type === "choice" && !f.choices.includes(v)) ||
      (f.not && typeof v === "string" && f.not.includes(v.trim().toLowerCase()));
    return bad ? (f.message || f.path + " is not valid") : "";
  };
  PD.setK = (o, k, v) => {
    const ps = k.split("."); const last = ps.pop();
    ps.reduce((a, p) => (a[p] = a[p] && typeof a[p] === "object" ? a[p] : {}), o)[last] = v;
  };


  // ---- time, durations, sizes

  PD.date = v => {
    if (v == null || v === "") return null;
    if (typeof v === "string" && /^\d+(\.\d+)?$/.test(v)) v = Number(v);
    const d = typeof v === "number" ? new Date(v < 1e11 ? v * 1000 : v) : new Date(v);
    return isNaN(d) ? null : d;
  };
  PD.clock = d => d.toLocaleTimeString(PD.lang, { hour: "numeric", minute: "2-digit" });
  const sameDay = (a, b) => a.toDateString() === b.toDateString();
  PD.dayLabel = d => {
    const now = new Date(), yest = new Date(now.getTime() - 864e5);
    if (sameDay(d, now)) return PD.t("day.today");
    if (sameDay(d, yest)) return PD.t("day.yesterday");
    return d.toLocaleDateString(PD.lang, d.getFullYear() === now.getFullYear() ? { month: "short", day: "numeric" } : { year: "numeric", month: "short", day: "numeric" });
  };
  PD.stamp = d => (sameDay(d, new Date()) ? PD.clock(d) : d.toLocaleDateString(PD.lang, { month: "short", day: "numeric" }) + ", " + PD.clock(d));
  PD.dur = s => {
    if (s == null || isNaN(s)) return "";
    s = Number(s);
    const sec = v => PD.t("unit.seconds", { n: v.toLocaleString(PD.lang) });
    if (s < 10) return sec(Math.round(s * 10) / 10);
    if (s < 60) return sec(Math.round(s));
    const m = Math.floor(s / 60), r = Math.round(s - m * 60);
    if (m < 60) return PD.t("unit.minutes", { n: m }) + (r ? " " + sec(r) : "");
    return PD.t("unit.hours", { n: Math.floor(m / 60) }) + " " + PD.t("unit.minutes", { n: String(m % 60).padStart(2, "0") });
  };
  PD.bytes = n => {
    n = Number(n) || 0;
    if (n < 1e3) return n + " B";
    if (n < 1e6) return Math.round(n / 1e3) + " KB";
    if (n < 1e9) return Math.round(n / 1e6) + " MB";
    return (n / 1e9).toFixed(1) + " GB";
  };
  PD.n = n => Number(n || 0).toLocaleString(PD.lang);
  /** "{n} things" in the window's language: the plural form its rules pick (one, two, few, many...) where the strings
      have it, else .other. A .one written without {n} ("one file") is used for exactly one only. */
  const PLURAL = (() => { try { return new Intl.PluralRules(PD.lang); } catch (e) { return null; } })();
  PD.count = (name, n) => {
    const form = PLURAL ? PLURAL.select(Number(n)) : Number(n) === 1 ? "one" : "other";
    const s = LOCAL[name + "." + form] ?? EN[name + "." + form];
    const fits = s !== undefined && (form !== "one" || Number(n) === 1 || s.includes("{n}"));
    return PD.t(name + (fits ? "." + form : ".other"), { n: PD.n(n) });
  };
  /** The Mirror while it fills -> {building, pct}; the rail's little bar and anything marked data-needs-mirror
      (grayed, with "Mirror building, N%" on hover, its clicks stopped) follow it on every status. */
  PD.mirrorState = st => {
    const p = (st && st.pull) || {}, total = p.documents_total || 0;
    const building = !!p.running;
    // `first`: the library has never been copied whole yet -- the only time what needs the Mirror waits for it; an
    // update after that shows its bar and blocks nothing
    const first = building && !(st && st.mirror && st.mirror.complete);
    // the share of the BYTES that has arrived: a few big books are most of a library, and counted by documents
    // the bar would sit still for minutes while gigabytes come in
    const bytes = p.bytes_total || 0;
    const done = bytes ? (p.bytes || 0) / bytes : total ? (p.documents || 0) / total : 0;
    return { building, first, pct: building ? Math.min(99, Math.floor(100 * done)) : 100 };
  };
  document.addEventListener("pd:status", e => {
    const m = PD.mirrorState(e.detail);
    document.querySelectorAll(".rail-mirror").forEach(el => {
      if (el.closest(".steplist")) return;            // setup's Mirror step draws its own bar and percentage
      el.hidden = !m.building;
      el.title = PD.t("mirror.building_pct", { pct: m.pct });
      el.innerHTML = '<span class="meta">' + esc(PD.t("mirror.pct", { pct: m.pct })) + '</span><div class="progress" aria-hidden="true"><i style="width: ' + m.pct + '%"></i></div>';
    });
    document.querySelectorAll("[data-needs-mirror]").forEach(el => {
      el.classList.toggle("mirror-wait", m.first);
      if (m.first) { el.setAttribute("aria-disabled", "true"); el.title = PD.t("mirror.building_pct", { pct: m.pct }); }
      else { el.removeAttribute("aria-disabled"); el.removeAttribute("title"); }
    });
  });
  document.addEventListener("click", e => {
    const el = e.target.closest && e.target.closest("[data-needs-mirror][aria-disabled=true]");
    if (el) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);
  /** The mirror's pull while it runs: notebooks done of the total the cloud's index listed, and the bytes. */
  PD.mirrorBar = p => {
    const total = p.documents_total || 0, done = Math.min(p.documents || 0, total);
    const pct = total ? Math.min(100, Math.round(100 * done / total)) : 0;
    return '<p class="num">' + esc(total ? PD.t("mirror.bar", { done: PD.n(done), total: PD.count("count.document", total), bytes: PD.bytes(p.bytes || 0),
                                                         bytes_total: PD.bytes(p.bytes_total || 0), pct })
        : PD.t("mirror.bar_start", { files: PD.count("count.file", p.files || 0), bytes: PD.bytes(p.bytes || 0) })) + "</p>" +
      '<div class="progress" role="progressbar" aria-valuemin="0"' + (total ? ' aria-valuemax="' + total + '" aria-valuenow="' + done + '"' : "") +
      ' aria-label="' + esc(PD.t("mirror.name")) + '"><i style="width: ' + pct + '%"></i></div>';
  };

  // ---- marks and small pieces of markup

  PD.mk = kind => '<i class="mk ' + kind + '"></i>';
  PD.line = (kind, html, cls) => '<span class="state-line' + (cls ? " " + cls : "") + '">' + PD.mk(kind) + "<span>" + html + "</span></span>";

  /** Set an element's HTML only when it changed, so polling never steals focus from a button. */
  PD.html = (el, html) => { if (el && el.__html !== html) { el.innerHTML = html; el.__html = html; } };

  // ANYWHERE in the app, a picture that fails to load is hidden: a broken image is never shown (a web picture dropped
  // into Decompose whose site refuses it, say). Pictures from the engine go through PD.loadImage, which tries again.
  document.addEventListener("error", e => {
    const t = e.target;
    if (t && t.tagName === "IMG" && t.getAttribute("src")) t.style.visibility = "hidden";
  }, true);
  document.addEventListener("load", e => {
    const t = e.target;
    if (t && t.tagName === "IMG" && t.style.visibility === "hidden") t.style.visibility = "";
  }, true);

  /** An engine picture into `img`, NEVER a broken image: `holder` (the img's parent by default) shows a spinner until
      the picture has arrived and decoded; a failed fetch or decode is tried again, waiting longer each time, for as
      long as the img is on screen and `stale()` is false. After `tries` failures `giveUp(holder)` is called (when given)
      and the spinner stays otherwise. -> a promise of true once shown. */
  PD.loadImage = async (img, path, { holder = img.parentElement, stale = () => false, tries = 8, giveUp = null } = {}) => {
    if (holder) holder.classList.add("img-wait");
    for (let k = 0; ; k++) {
      if (!img.isConnected || stale()) return false;
      try {
        const r = await fetch("/api/v1" + path, { headers: { Authorization: "Bearer " + PD.pairing.token } });
        if (r.ok) {
          const url = URL.createObjectURL(await r.blob());
          if (!img.isConnected || stale()) { URL.revokeObjectURL(url); return false; }
          const ok = await new Promise(res => { img.onload = () => res(true); img.onerror = () => res(false); img.src = url; });
          if (ok) { if (holder) holder.classList.remove("img-wait"); return true; }
          img.removeAttribute("src");
          URL.revokeObjectURL(url);
        }
      } catch (e) { /* the engine is busy or restarting: try again */ }
      if (k + 1 >= tries && giveUp) { if (holder) holder.classList.remove("img-wait"); giveUp(holder); return false; }
      await new Promise(res => setTimeout(res, Math.min(15000, 500 * 2 ** k)));
    }
  };

  PD.hostOf = url => {
    try { return new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(url) ? url : "http://" + url).hostname.replace(/^\[|\]$/g, ""); } catch (e) { return ""; }
  };
  /** True when the address is on this computer (or empty, so nothing is sent anywhere). */
  PD.isLocal = url => {
    if (!String(url || "").trim()) return true;
    const h = PD.hostOf(url).toLowerCase();
    return h === "localhost" || h === "::1" || /^127\./.test(h);
  };

  PD.copy = async text => {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall through */ }
    const t = document.createElement("textarea");
    t.value = text; t.setAttribute("readonly", ""); t.style.position = "fixed"; t.style.opacity = "0";
    document.body.append(t); t.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    t.remove();
    return ok;
  };

  /** Run an async action behind a button: busy while it runs, restored after. */
  PD.busy = async (btn, fn) => {
    if (btn) { btn.setAttribute("aria-busy", "true"); btn.disabled = true; }
    try { return await fn(); }
    finally { if (btn) { btn.removeAttribute("aria-busy"); btn.disabled = false; } }
  };

  /** Delegated events: PD.on(root, "click", "[data-act]", (e, el) => ...). */
  PD.on = (root, type, sel, fn) => root.addEventListener(type, e => {
    const el = e.target.closest(sel);
    if (el && root.contains(el)) fn(e, el);
  });

  // ---- script editor: a gutter of line numbers beside a plain textarea

  /** Type-ahead boxes: an <input data-ta='["option", ...]'> gets a dropdown list under it that filters as the user
      types (arrow keys, Enter and Escape work; a click picks). `source(text)` may replace the fixed options with
      ones fetched as the user types (it returns a promise of strings). Wired once per input. */
  PD.wireTypeahead = (root, source) => $$("input[data-ta]", root).forEach(inp => {
    if (inp.__ta) return;
    inp.__ta = true;
    const fixed = (() => { try { return JSON.parse(inp.dataset.ta || "[]"); } catch (e) { return []; } })();
    const wrap = document.createElement("span");
    wrap.className = "ta";
    inp.parentNode.insertBefore(wrap, inp);
    wrap.append(inp);
    const list = document.createElement("ul");
    list.className = "ta-list"; list.setAttribute("role", "listbox"); list.hidden = true;
    wrap.append(list);
    inp.setAttribute("role", "combobox"); inp.setAttribute("aria-autocomplete", "list"); inp.autocomplete = "off";
    let items = [], at = -1, gen = 0;
    const close = () => { list.hidden = true; at = -1; inp.setAttribute("aria-expanded", "false"); };
    const show = opts => {
      items = opts.slice(0, 50); at = -1;
      list.innerHTML = items.map((o, i) => '<li role="option" data-i="' + i + '">' + esc(o) + "</li>").join("");
      list.hidden = !items.length; inp.setAttribute("aria-expanded", String(!!items.length));
    };
    const mark = () => list.querySelectorAll("li").forEach((li, i) => { li.classList.toggle("on", i === at); if (i === at) li.scrollIntoView({ block: "nearest" }); });
    const pick = i => { if (items[i] == null) return; inp.value = items[i]; close(); inp.dispatchEvent(new Event("change", { bubbles: true })); };
    const refresh = async () => {
      const q = inp.value.trim().toLowerCase(), g = ++gen;
      const opts = source ? await source(inp.value.trim(), inp) : fixed.filter(o => !q || o.toLowerCase().includes(q));
      if (g === gen && document.activeElement === inp) show(opts || []);
    };
    inp.addEventListener("focus", refresh);
    inp.addEventListener("input", refresh);
    inp.addEventListener("blur", () => setTimeout(close, 150));
    inp.addEventListener("keydown", e => {
      if (list.hidden && (e.key === "ArrowDown" || e.key === "ArrowUp")) { refresh(); return; }
      if (e.key === "ArrowDown") { at = Math.min(items.length - 1, at + 1); mark(); e.preventDefault(); }
      else if (e.key === "ArrowUp") { at = Math.max(0, at - 1); mark(); e.preventDefault(); }
      else if (e.key === "Enter" && !list.hidden && at >= 0) { pick(at); e.preventDefault(); }
      else if (e.key === "Escape") close();
    });
    list.addEventListener("mousedown", e => { const li = e.target.closest("li"); if (li) { e.preventDefault(); pick(Number(li.dataset.i)); } });
  });

  /** A Windows batch file, colored: comments, labels, strings, variables, keywords and switches. */
  const BAT_KEYWORDS = /^(echo|set|setlocal|endlocal|if|else|not|exist|defined|errorlevel|goto|call|exit|for|in|do|start|cd|pushd|popd|timeout|taskkill|title|pause|shift|cls|equ|neq|lss|leq|gtr|geq)$/i;
  PD.highlightBat = text => text.split("\n").map(lineText => {
    const t = lineText.replace(/\r$/, "");
    if (/^\s*(@?rem(\s|$)|::)/i.test(t)) return '<span class="tok-c">' + esc(t) + "</span>";
    if (/^\s*:[^:]/.test(t)) return '<span class="tok-l">' + esc(t) + "</span>";
    let out = "", rest = t;
    const rx = /("[^"]*"?)|(%%~?[a-z]|%~[a-z0-9]+|%[^%\s]+%|![^!\s]+!)|((?:^|(?<=\s))--?[a-z][\w-]*|(?:^|(?<=\s))\/[a-z?]\b)|(@)|([a-z_][\w.-]*)/gi;
    let m, last = 0;
    while ((m = rx.exec(rest))) {
      out += esc(rest.slice(last, m.index));
      const cls = m[1] ? "tok-s" : m[2] ? "tok-v" : m[3] ? "tok-f" : m[4] ? "tok-k" : BAT_KEYWORDS.test(m[5]) ? "tok-k" : "";
      out += cls ? '<span class="' + cls + '">' + esc(m[0]) + "</span>" : esc(m[0]);
      last = m.index + m[0].length;
    }
    return out + esc(rest.slice(last));
  }).join("\n");

  PD.codeHtml = (id, text, rows, label, readonly, lang) =>
    '<div class="code' + (lang ? " lang-" + lang : "") + '"><div class="gutter" aria-hidden="true"></div><div class="code-body">' +
    (lang ? '<pre class="code-hl" aria-hidden="true"></pre>' : "") +
    '<textarea id="' + id + '" rows="' + rows + '" wrap="off" spellcheck="false" ' +
    'autocomplete="off" autocapitalize="off" aria-label="' + esc(label) + '"' + (readonly ? " readonly" : "") + ">" + esc(text) + "</textarea></div></div>";
  PD.wireCode = root => $$(".code", root).forEach(c => {
    const t = $("textarea", c), g = $(".gutter", c), hl = $(".code-hl", c);
    if (!t || !g || t.__wired) return;
    t.__wired = true;
    const paint = () => {
      g.textContent = Array.from({ length: t.value.split("\n").length }, (_, i) => i + 1).join("\n");
      if (hl) hl.innerHTML = PD.highlightBat(t.value) + "\n";
    };
    const sync = () => { g.scrollTop = t.scrollTop; if (hl) { hl.scrollTop = t.scrollTop; hl.scrollLeft = t.scrollLeft; } };
    t.addEventListener("input", () => { paint(); sync(); });
    t.addEventListener("scroll", sync);
    paint();
  });

  // ---- dialogs: a confirm (a question, its consequences, Cancel and the action) and a small form

  const sheet = (title, inner) => {
    const dlg = document.createElement("dialog");
    dlg.className = "sheet";
    dlg.setAttribute("aria-labelledby", "dlg-title");
    dlg.innerHTML = '<h2 id="dlg-title">' + esc(title) + "</h2>" + inner;
    return dlg;
  };
  PD.sheet = sheet;

  /** Resolves true when the action is chosen. `body` is a list of HTML paragraphs; escape what you put in. */
  PD.confirm = ({ title, body = [], action, danger = true, disclaimer = "" }) => new Promise(resolve => {
    const dlg = sheet(title, body.map(p => "<p>" + p + "</p>").join("") +
      (disclaimer ? '<div class="disclaimer"><span class="disclaimer-label">' + esc(PD.t("common.disclaimer")) + "</span><p>" + esc(disclaimer) + "</p></div>" : "") +
      '<div class="actions"><button type="button" class="btn" data-v="cancel" autofocus>' + esc(PD.t("common.cancel")) + "</button>" +
      '<button type="button" class="btn ' + (danger ? "danger" : "primary") + '" data-v="ok">' + esc(action) + "</button></div>");
    dlg.addEventListener("click", e => { const b = e.target.closest("button[data-v]"); if (b) dlg.close(b.dataset.v); });
    dlg.addEventListener("close", () => { resolve(dlg.returnValue === "ok"); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
  });

  // ---- taking the reMarkable desktop app's login: PaperDaemon's only way to a device token

  // the privacy note and the two ways to take the desktop app's login, in the user's language
  Object.defineProperty(PD, "PRIVACY", { get: () => PD.t("login.privacy") });
  const LOGIN = {
    borrow: { title: "login.borrow.title", body: "login.borrow.body", action: "login.borrow.action", danger: false },
    steal: { title: "login.steal.title", body: "login.steal.body", action: "login.steal.action", danger: true },
  };

  /** Ask, then take the desktop app's login. -> the API's answer ({found, set, removed?}), or null when canceled. */
  PD.takeLogin = async mode => {
    const m = LOGIN[mode];
    // with a False Mirror, signing in moves its typed text into the tablet's faces: said before, not after
    const fm = !!((PD.status || {}).false_mirror || {}).exists;
    const ok = await PD.confirm({ title: PD.t(m.title), body: [esc(PD.t(m.body))].concat(fm ? [esc(PD.t("fm.signin_shift"))] : []),
                                  disclaimer: PD.PRIVACY, action: PD.t(m.action), danger: m.danger });
    return ok ? PD.api("POST", "/tablet/desktop-token", { mode }) : null;
  };

  /** The two buttons, as HTML; a screen wires data-act="borrow" and data-act="steal" to PD.takeLogin. */
  PD.loginButtons = (busy = false) => {
    const b = busy ? ' aria-busy="true" disabled' : "";
    return '<div class="actions"><button type="button" class="btn" data-act="borrow"' + b + ">" + esc(PD.t("login.borrow.title")) + "</button>" +
      '<button type="button" class="btn" data-act="steal"' + b + ">" + esc(PD.t("login.steal.title")) + "</button></div>";
  };

  /** One line about how a take went, for the screens. -> {text, bad} */
  PD.loginResult = (d, mode) => {
    if (!d.found) return { text: PD.t("login.not_found"), bad: true };
    if (!d.set) return { text: d.error ? PD.t("login.not_kept_why", { why: d.error }) : PD.t("login.not_kept"), bad: true };
    return { text: PD.t(mode === "steal" ? "login.stolen" : "login.borrowed"), bad: false };
  };

  /** A form in a sheet. fields: [{name, label, kind: "text"|"select", value, options: [{value, label}], mono, hint}].
      onSubmit(values) may throw: its message shows in the sheet and the sheet stays. Resolves the values, or null. */
  PD.ask = ({ title, intro, fields, action, onSubmit }) => new Promise(resolve => {
    const rows = fields.map((f, i) => {
      const id = "ask-" + i;
      const ctl = f.kind === "select"
        ? '<span class="select"><select class="field" id="' + id + '" name="' + f.name + '">' +
          f.options.map(o => '<option value="' + esc(o.value) + '"' + (o.value === f.value ? " selected" : "") + ">" + esc(o.label) + "</option>").join("") + "</select></span>"
        : '<input class="field' + (f.mono ? " mono" : "") + '" id="' + id + '" name="' + f.name + '" value="' + esc(f.value || "") +
          '" autocomplete="off" spellcheck="false"' + (f.placeholder ? ' placeholder="' + esc(f.placeholder) + '"' : "") +
          (f.kind === "number" ? ' type="number" inputmode="numeric" step="1"' + (f.min != null ? ' min="' + f.min + '"' : "") + (f.max != null ? ' max="' + f.max + '"' : "") : "") + ">";
      return '<div class="stack-field" style="margin-top: var(--s3)"><label for="' + id + '" class="meta" style="display:block;margin-bottom:4px">' + esc(f.label) + "</label>" + ctl +
        (f.hint ? '<p class="meta" style="margin-top:4px">' + esc(f.hint) + "</p>" : "") + "</div>";
    }).join("");
    const dlg = sheet(title, '<form novalidate>' + (intro ? "<p>" + intro + "</p>" : "") + rows +
      '<p class="msg err" role="alert" style="margin-top: var(--s3)"></p>' +
      '<div class="actions"><button type="button" class="btn" data-v="cancel">' + esc(PD.t("common.cancel")) + '</button><button type="submit" class="btn primary">' + esc(action) + "</button></div></form>");
    let result = null;
    const form = $("form", dlg), msg = $(".msg", dlg), go = $('button[type="submit"]', dlg);
    $("[name]", dlg)?.setAttribute("autofocus", "");
    dlg.addEventListener("click", e => { if (e.target.closest("button[data-v=cancel]")) dlg.close("cancel"); });
    form.addEventListener("submit", async e => {
      e.preventDefault();
      const values = {};
      $$("[name]", form).forEach(el => { values[el.name] = el.value.trim(); });
      msg.textContent = "";
      go.disabled = true; go.setAttribute("aria-busy", "true");
      try { if (onSubmit) await onSubmit(values); result = values; dlg.close("ok"); }
      catch (err) { msg.textContent = PD.errText(err); go.disabled = false; go.removeAttribute("aria-busy"); }
    });
    dlg.addEventListener("close", () => { resolve(result); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
    const first = $("[name]", dlg); if (first) first.focus();
  });

  // ---- the screens plug in here

  /** def: {label, group, mount(root), show(), hide(), poll(tick), rail() -> html of the state beside its name} */
  PD.screen = (id, def) => { def.id = id; PD.screens[id] = def; PD.order.push(id); };
  PD.go = id => { if (location.hash !== "#" + id) location.hash = id; else window.dispatchEvent(new HashChangeEvent("hashchange")); };
})();

// ---- zoom: Ctrl + scroll, Ctrl + = / -, Ctrl + 0 -- the whole window, remembered, and nothing shown when it changes
(() => {
  const STEPS = [0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];
  let at = 1;
  try { at = Number(localStorage.getItem("pd.zoom")) || 1; } catch (e) { /* the default */ }
  // CSS zoom multiplies the window's own units (vh, vw) too: what is sized against the window divides by --pd-zoom, so
  // the notebook viewer fills the same share of the window at every zoom and only its controls and words grow
  const apply = z => {
    at = z;
    PD.uiZoom = z;
    document.documentElement.style.zoom = z === 1 ? "" : String(z);
    document.documentElement.style.setProperty("--pd-zoom", String(z));
    window.dispatchEvent(new Event("pd-zoom"));                  // what is sized in script against the window, again
    try { localStorage.setItem("pd.zoom", String(z)); } catch (e) { /* this window only */ }
  };
  const step = dir => {
    const i = STEPS.findIndex(s => s >= at - 0.001);
    const here = i < 0 ? STEPS.length - 1 : i;
    apply(STEPS[Math.min(STEPS.length - 1, Math.max(0, here + dir))]);
  };
  apply(STEPS.includes(at) ? at : 1);
  window.addEventListener("keydown", e => {
    if (!e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key === "=" || e.key === "+" || e.code === "NumpadAdd") { e.preventDefault(); step(1); }
    else if (e.key === "-" || e.key === "_" || e.code === "NumpadSubtract") { e.preventDefault(); step(-1); }
    else if (e.key === "0" || e.code === "Numpad0") { e.preventDefault(); apply(1); }
  }, true);
  window.addEventListener("wheel", e => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    // over the open notebook viewer, Ctrl + scroll zooms the PAGE (tablet.js), never the window
    if (e.target && e.target.closest && e.target.closest("dialog.viewer[open]")) return;
    step(e.deltaY < 0 ? 1 : -1);
  }, { passive: false, capture: true });
})();
