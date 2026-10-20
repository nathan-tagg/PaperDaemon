"use strict";
/* Settings: the window's language and the preferences for the pages (how they write temperatures, times and weeks,
   the decompose inboxes, the location, the ignore and standing instructions tags) -- one set for every tablet, since
   they all share one library -- then PaperDaemon's own settings (the reMarkable login, network access), and tools (checking for an update, sending the logs to the inbox).

   THE FALSE MIRROR IS FOUND BY WAITING: a minute on this screen without leaving it, and its setting fades in at the
   bottom. Once there is a false mirror the setting shows at once, to delete it; deleting it turns it back into
   Create False Mirror, and the next visit waits the minute again. */
(() => {
  const { $, esc, line } = PD;
  const t = PD.t;
  let R = null;
  const S = { s: null, places: new Map(), books: null, fmBooks: null, revealed: false, timer: 0 };
  const BULB = '<svg viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="M8 1.5a4.5 4.5 0 0 0-2.6 8.2c.4.3.6.7.6 1.1V12h4v-1.2c0-.4.2-.8.6-1.1A4.5 4.5 0 0 0 8 1.5z"/><path pathLength="1" d="M6 13.5h4M6.8 15h2.4"/></svg>';
  const fmExists = () => !!((PD.status || {}).false_mirror || {}).exists;
  async function save(path, value, msgEl) {
    const [s, e] = await PD.safe(PD.saveSettings(st => { PD.setK(st, path, value); }));
    if (s) S.s = s;
    if (msgEl) { msgEl.textContent = e ? PD.errText(e) : ""; msgEl.className = "hint" + (e ? " attn" : ""); }
    PD.paintRail();
    return !e;
  }

  // ---- the reMarkable login: borrowed (the app's own, shared; it can be stolen instead) or stolen (PaperDaemon's
  // own, so there is no going back to borrowing here; setup offers both)
  function paintLogin(msg, bad) {
    const box = $("#st-login", R); if (!box) return;
    const tb = (PD.status && PD.status.tablet) || {};
    let html;
    if (!tb.set) html = line("off", esc(t("settings.login.none"))) + PD.loginButtons();
    // connected needs no mark (a dot beside it says nothing); only a problem gets one
    else if (tb.method === "borrowed") html = '<span class="login-state"><span>' + esc(t("settings.login.borrowing")) + "</span>" +
      '<button type="button" class="link-btn" data-act="steal">' + esc(t("settings.login.steal")) + "</button></span>";
    else if (tb.method === "stolen") html = "<span>" + esc(t("settings.login.stolen")) + "</span>";
    else html = "<span>" + esc(t("settings.login.connected")) + "</span>";
    PD.html(box, html + (msg ? '<p class="hint' + (bad ? " attn" : "") + '" role="status">' + esc(msg) + "</p>" : ""));
  }

  async function takeLogin(mode) {
    const [d, e] = await PD.safe(PD.takeLogin(mode));
    if (!d && !e) return;                                   // canceled
    const r = e ? { text: PD.errText(e), bad: true } : PD.loginResult(d, mode);
    await PD.refreshStatus();
    paintLogin(r.text, r.bad);
  }

  // a row: its label, with a "?" to the label's right when there is more to say, and its control
  const row = (label, help, control) => '<div class="row"><div class="label">' + esc(label) + (help ? PD.helpTip(help) : "") +
    '</div><div class="control">' + control + "</div></div>";

  // ---- the language type-ahead

  function wireLookups() {
    PD.wireTypeahead(R, async (q, input) => {
      const el = input || document.activeElement;
      if (el && el.id === "st-lang") {              // by its own name, or its name in the window's language
        const k = q.toLowerCase(), all = PD.LANGUAGES.map(PD.languageLabel);
        return all.includes(q) ? all : all.filter(l => !k || l.toLowerCase().includes(k));
      }
      if (el && (el.id === "st-inbox" || el.id === "st-fm-inbox")) {
        const k = q.toLowerCase();
        return (await notebooks(el.id === "st-fm-inbox" ? "/fm" : "")).filter(p => !k || p.toLowerCase().includes(k));
      }
      if (el && el.id === "st-loc") {
        if (q.trim().length < 2) return [];
        const [list] = await PD.safe(PD.api("GET", "/places?q=" + encodeURIComponent(q)));
        (list || []).forEach(p => S.places.set(p.label, p));
        return (list || []).map(p => p.label);
      }
      return [];
    });
    $("#st-lang", R).addEventListener("change", async e => {
      const msg = $("#st-lang-msg", R), was = PD.getK(S.s, "prefs.language") || "en";
      const code = PD.LANGUAGES.find(c => PD.languageLabel(c) === e.target.value.trim());
      if (!code) { e.target.value = PD.languageLabel(was); msg.textContent = t("settings.language.pick"); msg.className = "hint attn"; return; }
      msg.textContent = "";
      if (code !== was && await save("prefs.language", code, msg)) PD.useLanguage(code);
    });
  }

  // ---- the Language label: the word in every language the window speaks, one after another, landing on English and
  // the window's own (so whoever opens Settings in a language they cannot read still finds where to change it)

  let words = null, cycling = 0;
  async function languageWords() {
    if (words) return words;
    const got = await Promise.all(PD.LANGUAGES.map(async code => {
      try {
        const r = await fetch("/ui/strings/strings-" + code + ".xml");
        const doc = new DOMParser().parseFromString(await r.text(), "application/xml");
        const s = doc.querySelector('string[name="settings.language"]');
        return s ? s.textContent : "";
      } catch (e) { return ""; }
    }));
    words = got.filter((w, i) => w && got.indexOf(w) === i);
    return words;
  }

  function landed() {
    const en = PD.LANGUAGES.length && words ? words[0] : t("settings.language"), here = t("settings.language");
    return here === en ? en : en + " · " + here;
  }

  /** For as long as Settings is open: English and the window's own language, held, then the next few of the others,
      then back; over a few rounds every language comes by. */
  async function cycleLanguageLabel() {
    const el = $("#st-lang-label", R); if (!el) return;
    const run = ++cycling;
    // ONE WIDTH, whatever word shows: the resting label's, measured once its font is in, so the "?" beside it never
    // moves; a longer word fades out at the edge, a shorter one leaves room
    el.style.width = "";
    el.textContent = landed();
    try { await document.fonts.ready; } catch (e) { /* the width as it is */ }
    el.style.width = Math.ceil(el.getBoundingClientRect().width) + "px";
    const show = w => { el.textContent = w; el.classList.toggle("fade", el.scrollWidth > el.clientWidth + 1); };
    const list = await languageWords();
    const others = list.filter(w => w !== list[0] && w !== t("settings.language"));
    const live = () => run === cycling && el.isConnected && !R.hidden;
    const wait = ms => new Promise(r => setTimeout(r, ms));
    // the window's own language for 5 seconds, then three others for 2 seconds each, each word fading out and the
    // next fading in, then back; over a few rounds every language comes by
    const swap = async w => {
      el.classList.add("out"); await wait(350);
      if (!live()) return;
      show(w); el.classList.remove("out"); await wait(350);
    };
    for (let i = 0; live(); ) {
      await wait(5000 - 350);
      for (let k = 0; k < 3 && others.length && live(); k++, i = (i + 1) % others.length) {
        await swap(others[i]);
        await wait(2000 - 700);
      }
      if (live()) await swap(landed());
    }
    if (el.isConnected) { el.classList.remove("out"); show(landed()); }
  }

  // ---- the preferences for the pages (they were the tablet's gear; one set for every tablet now)

  const choice = (id, path, opts) => '<span class="select"><select class="field" id="' + id + '" data-path="' + path + '">' +
    '<option value="">' + esc(t("common.choose")) + "</option>" +
    opts.map(([v, l]) => '<option value="' + v + '">' + esc(l) + "</option>").join("") + "</select></span>";

  /** The notebooks of a library as paths ("Folder/Notebook"): the Mirror's, or the false mirror's (base "/fm"). */
  async function notebooks(base) {
    const key = base ? "fmBooks" : "books";
    if (S[key]) return S[key];
    const [list] = await PD.safe(PD.api("GET", base + "/library"));
    const by = new Map((list || []).map(d => [d.id, d]));
    const name = d => { const n = [d.name]; for (let p = by.get(d.parent), k = 0; p && k < 64; p = by.get(p.parent), k++) n.unshift(p.name); return n.join("/"); };
    S[key] = (list || []).filter(d => d.type === "document" && d.kind === "notebook" && !String(d.parent).startsWith("trash")).map(name).sort((a, b) => a.localeCompare(b));
    return S[key];
  }

  function prefsRows() {
    return row(t("settings.temperature"), t("settings.temperature.help"), choice("st-temp", "prefs.temperature",
        [["fahrenheit", t("settings.temperature.f")], ["celsius", t("settings.temperature.c")]])) +
      row(t("settings.clock"), "", choice("st-clock", "prefs.clock", [["12", t("settings.clock.12")], ["24", t("settings.clock.24")]])) +
      row(t("settings.week"), "", choice("st-week", "prefs.week_start", [["sunday", t("day.sunday")], ["monday", t("day.monday")], ["saturday", t("day.saturday")]])) +
      row(t("settings.inbox"), t("settings.inbox.help"),
        '<input class="field w-l" id="st-inbox" data-ta="[]" spellcheck="false" placeholder="' + esc(t("settings.inbox.placeholder")) +
        '"><p class="hint" id="st-inbox-msg" role="status"></p>') +
      // the false mirror's own inbox, right under the Mirror's: the same control; Send to Tablet lands in both
      '<div id="st-fm-inbox-row"' + (fmExists() ? "" : " hidden") + ">" + row(t("fm.inbox"), t("fm.inbox.help"),
        '<input class="field w-l" id="st-fm-inbox" data-ta="[]" spellcheck="false" placeholder="' + esc(t("settings.inbox.placeholder")) +
        '"><p class="hint" id="st-fm-inbox-msg" role="status"></p>') + "</div>" +
      row(t("settings.location"), t("settings.location.help"),
        '<input class="field w-l" id="st-loc" data-ta="[]" spellcheck="false" placeholder="' + esc(t("settings.location.placeholder")) +
        '"><p class="hint" id="st-loc-msg" role="status"></p>') +
      row(t("settings.ignore"), t("settings.ignore.help"),
        '<input class="field mono w-m" id="st-ignore" spellcheck="false" autocomplete="off"><p class="hint" id="st-ignore-msg" role="status"></p>') +
      row(t("settings.sprompt"), t("settings.sprompt.help"),
        '<input class="field mono w-m" id="st-sprompt" spellcheck="false" autocomplete="off"><p class="hint" id="st-sprompt-msg" role="status"></p>');
  }

  function wirePrefs() {
    ["prefs.temperature", "prefs.clock", "prefs.week_start"].forEach(p =>
      R.querySelector('[data-path="' + p + '"]').addEventListener("change", e => save(p, e.target.value).then(() => paintNote())));
    const pickBook = (inp, path, base) => inp.addEventListener("change", async e => {
      const val = e.target.value.trim(), msg = $("#" + inp.id + "-msg", R), was = PD.getK(S.s, path) || "";
      if (val === was) return;
      if (val && !(await notebooks(base)).includes(val)) { e.target.value = was; msg.textContent = t("settings.inbox.pick"); msg.className = "hint attn"; return; }
      await save(path, val, msg);
      paintTools();
    });
    pickBook($("#st-inbox", R), "tablet.inbox", "");
    pickBook($("#st-fm-inbox", R), "false_mirror.inbox", "/fm");
    $("#st-loc", R).addEventListener("change", async e => {
      const val = e.target.value.trim(), msg = $("#st-loc-msg", R), was = PD.getK(S.s, "location.name") || "";
      if (val === was) return;
      const p = S.places.get(val);
      if (!p) { e.target.value = was; msg.textContent = t("settings.location.pick"); msg.className = "hint attn"; return; }
      const [s2, err] = await PD.safe(PD.saveSettings(st => {
        PD.setK(st, "location.name", p.label); PD.setK(st, "location.lat", p.lat);
        PD.setK(st, "location.lon", p.lon); PD.setK(st, "location.holidays", p.holidays);
      }));
      if (s2) S.s = s2;
      if (err) e.target.value = was;
      msg.textContent = err ? PD.errText(err) : ""; msg.className = "hint" + (err ? " attn" : "");
    });
    [["st-ignore", "tags.ignore", "ignore"], ["st-sprompt", "tags.sprompt", "sprompt"]].forEach(([el, path, dflt]) =>
      $("#" + el, R).addEventListener("change", async e => {
        const val = e.target.value.trim();
        if (!val) e.target.value = PD.getK(S.s, path) || dflt;
        else if (!await save(path, val, $("#" + el + "-msg", R))) e.target.value = PD.getK(S.s, path) || dflt;
      }));
  }

  function fillPrefs() {
    const v = S.s || {};
    ["prefs.temperature", "prefs.clock", "prefs.week_start"].forEach(p => {
      R.querySelector('[data-path="' + p + '"]').value = PD.getK(v, p) || (PD.regionDefaults || {})[p.split(".")[1]] || "";
    });
    $("#st-inbox", R).value = PD.getK(v, "tablet.inbox") || "";
    $("#st-fm-inbox", R).value = PD.getK(v, "false_mirror.inbox") || "";
    $("#st-fm-inbox-row", R).hidden = !fmExists();
    $("#st-loc", R).value = PD.getK(v, "location.name") || "";
    $("#st-ignore", R).value = PD.getK(v, "tags.ignore") || "ignore";
    $("#st-sprompt", R).value = PD.getK(v, "tags.sprompt") || "sprompt";
  }

  // THE REMINDER: once the Mirror is built and until every preference is chosen, the rail item carries a lightbulb and
  // the page a note asking for a moment. THE NOTE EXPIRES: a bar along its bottom edge runs down over 20 seconds while
  // the screen is open; when it is gone, so is the note (and the lightbulb, for good). Leaving the screen takes the
  // note away, so the next visit starts the 20 seconds again.
  const NOTE_SEEN = "pd.prefs-note-seen";
  function noteSeen() {
    try { return localStorage.getItem(NOTE_SEEN) === "1"; } catch (e) { return !!PD.prefsNoteSeen; }
  }
  PD.needsPrefs = (st, settings) => {
    const p = (settings || S.s || PD.settings || {}).prefs || {};
    const m = PD.mirrorState(st || PD.status);
    const built = !!((st || PD.status || {}).mirror || {}).complete && !m.first;
    return built && !(p.temperature && p.clock && p.week_start) && !noteSeen();
  };

  function paintNote() {
    const box = R && $("#st-note", R); if (!box) return;
    if (!PD.needsPrefs(PD.status, S.s)) { box.innerHTML = ""; PD.paintRail(); return; }
    if (box.querySelector(".notice")) return;
    box.innerHTML = '<div class="notice soft" role="status"><span class="bulb draw">' + BULB + "</span><span>" + esc(t("settings.note")) +
      '</span><i class="notice-timer" aria-hidden="true"></i></div>';
    box.querySelector(".notice-timer").addEventListener("animationend", () => {
      try { localStorage.setItem(NOTE_SEEN, "1"); } catch (e) { PD.prefsNoteSeen = true; }
      paintNote(); PD.paintRail();
    });
  }

  // ---- the false mirror (found by waiting)

  function paintFalseMirror() {
    const box = $("#st-fm", R); if (!box) return;
    const exists = fmExists();
    if (!exists && !S.revealed) { box.hidden = true; box.classList.remove("haunt"); return; }
    box.hidden = false;
    // with an account: the faces its pages are set in; with a built Mirror too: converting its books with the tablet
    const signed = !!((PD.status || {}).tablet || {}).set, built = !!((PD.status || {}).mirror || {}).complete;
    const v = S.s || PD.settings || {};
    box.innerHTML = '<h2 id="st-h-fm">' + esc(t("fm.label")) + "</h2>" + row(t("fm.label"), t("fm.help"),
      exists ? '<button type="button" class="btn danger" data-act="fm-delete">' + esc(t("fm.delete")) + "</button>"
             : '<button type="button" class="btn" data-act="fm-create">' + esc(t("fm.create_mirror")) + "</button>") +
      '<p class="hint" id="st-fm-msg" role="status"></p>' +
      (exists && signed ? row(t("fm.faces"), t("fm.faces.help"),
        choice("st-fm-faces", "false_mirror.faces", [["tablet", t("fm.faces.tablet")], ["own", t("fm.faces.own")]]) +
        '<p class="hint" id="st-fm-faces-msg" role="status"></p>') : "") +
      (exists && signed && built ? row(t("fm.convert"), t("fm.convert.help"),
        '<label class="check-label"><input type="checkbox" id="st-fm-convert"> ' + esc(t("fm.convert")) +
        '</label><p class="hint" id="st-fm-convert-msg" role="status"></p>') : "");
    const faces = $("#st-fm-faces", R);
    if (faces) {
      faces.value = PD.getK(v, "false_mirror.faces") || "tablet";
      faces.addEventListener("change", e => save("false_mirror.faces", e.target.value, $("#st-fm-faces-msg", R)));
    }
    const conv = $("#st-fm-convert", R);
    if (conv) {
      conv.checked = !!PD.getK(v, "false_mirror.convert");
      conv.addEventListener("change", async e => {
        if (e.target.checked && !await PD.confirm({ title: t("fm.convert_q"), body: [esc(t("fm.convert_body1")), esc(t("fm.convert_body2"))],
                                                    action: t("fm.convert_on"), danger: false })) { e.target.checked = false; return; }
        if (!await save("false_mirror.convert", e.target.checked, $("#st-fm-convert-msg", R))) e.target.checked = !e.target.checked;
      });
    }
  }

  function haunt() {
    // a minute without leaving: the setting comes up out of nothing, slowly
    if (R.hidden || fmExists()) return;
    S.revealed = true;
    paintFalseMirror();
    $("#st-fm", R).classList.add("haunt");
  }

  async function createFalseMirror(btn) {
    const ok = await PD.confirm({ title: t("fm.create_q"), body: [esc(t("fm.create_body1")), esc(t("fm.create_body2"))],
                                  action: t("fm.create_mirror"), danger: false });
    if (!ok) return;
    const msg = $("#st-fm-msg", R);
    const [st, e] = await PD.safe(PD.busy(btn, () => PD.api("POST", "/false-mirror")));
    if (e) { msg.textContent = PD.errText(e); msg.className = "hint attn"; return; }
    PD.status = st; PD.paintRail(); document.dispatchEvent(new CustomEvent("pd:status", { detail: st }));
    S.fmBooks = null;
    paintFalseMirror(); fillPrefs();
  }

  async function deleteFalseMirror(btn) {
    const ok = await PD.confirm({ title: t("fm.delete_mirror_q"), body: [esc(t("fm.delete_mirror_body"))], action: t("fm.delete"), danger: true });
    if (!ok) return;
    const msg = $("#st-fm-msg", R);
    const [st, e] = await PD.safe(PD.busy(btn, () => PD.api("DELETE", "/false-mirror")));
    if (e) { msg.textContent = PD.errText(e); msg.className = "hint attn"; return; }
    PD.status = st; PD.paintRail(); document.dispatchEvent(new CustomEvent("pd:status", { detail: st }));
    const [s] = await PD.safe(PD.loadSettings()); if (s) S.s = s;
    S.revealed = true;                       // back to Create False Mirror, for the rest of this visit
    S.fmBooks = null;
    paintFalseMirror(); fillPrefs();
  }

  // ---- tools

  function paintTools() {
    const inbox = PD.getK(S.s, "tablet.inbox") || "";
    const b = $("[data-act=logs]", R);
    b.disabled = !inbox;
    b.title = inbox ? "" : t("settings.logs.no_inbox");
    $("#st-ver", R).textContent = (PD.status && PD.status.version) || "";
  }

  // the check runs in the desktop window, which shows what it finds in a window of its own: here, only a spinner
  // beside the button for a moment, and words only when the check could not be asked for
  async function checkUpdates(btn) {
    const out = $("#st-upd-msg", R), spin = $("#st-upd-spin", R);
    out.textContent = "";
    spin.hidden = false;
    await PD.busy(btn, async () => {
      const [d, e] = await PD.safe(PD.api("POST", "/updates/check"));
      if (e || !d.asked) {
        out.className = "hint attn";
        out.textContent = e ? PD.errText(e) : t("settings.updates.installed_only");
      }
    });
    setTimeout(() => { spin.hidden = true; }, 2500);
  }

  async function sendLogs(btn) {
    const out = $("#st-logs-msg", R);
    await PD.busy(btn, async () => {
      const [d, e] = await PD.safe(PD.api("POST", "/logs/send"));
      out.className = "hint" + (e ? " attn" : "");
      out.textContent = e ? PD.errText(e) : t("settings.logs.sent", { pages: PD.count("count.page", d.pages),
        inbox: PD.getK(S.s, "tablet.inbox") || t("settings.logs.the_inbox"), first: d.first });
    });
  }

  function fill() {
    const s = S.s || {};
    $("#st-lang", R).value = PD.languageLabel(PD.getK(s, "prefs.language") || "en");
    $("#st-net", R).checked = PD.getK(s, "network.allowed") !== false;
    paintTools(); paintLogin();
  }

  PD.screen("settings", {
    label: t("settings.label"), group: 1,
    rail(st) {
      return PD.needsPrefs(st) ? '<span class="bulb draw" title="' + esc(t("settings.prefs_to_set")) + '">' + BULB + "</span>" : "";
    },
    mount(root) {
      R = root;
      R.innerHTML = '<header class="page-head"><h1>' + esc(t("settings.label")) + '</h1></header><div id="st-note"></div>' +
        '<section class="section" aria-labelledby="st-h-prefs"><h2 id="st-h-prefs">' + esc(t("settings.prefs")) + "</h2>" +
        row("", t("settings.language.help"), '<input class="field w-l" id="st-lang" data-ta="[]" spellcheck="false"><p class="hint" id="st-lang-msg" role="status"></p>') +
        prefsRows() +
        "</section>" +
        '<section class="section" aria-labelledby="st-h-set"><h2 id="st-h-set">' + esc(t("settings.label")) + "</h2>" +
        row(t("settings.remarkable"), "", '<div id="st-login"></div>') +
        row(t("settings.network"), t("settings.network.help"),
          '<label class="check-label"><input type="checkbox" id="st-net"> ' + esc(t("settings.network.allow")) +
          '</label><p class="hint" id="st-net-msg" role="status"></p>') +
        "</section>" +
        '<section class="section" aria-labelledby="st-h-tools"><h2 id="st-h-tools">' + esc(t("settings.tools")) + "</h2>" +
        row(t("settings.updates"), t("settings.updates.help"),
          '<span class="value num">' + PD.tHtml("settings.version", { version: '<span id="st-ver"></span>' }) +
          '</span><button type="button" class="btn" data-act="update">' + esc(t("settings.updates.check")) +
          '</button><span class="upd-spin" id="st-upd-spin" hidden><i class="mk spin"></i></span>' +
          '<p class="hint" id="st-upd-msg" role="status"></p>') +
        row(t("settings.logs"), t("settings.logs.help"),
          '<button type="button" class="btn" data-act="logs">' + esc(t("settings.logs.send")) + '</button><p class="hint" id="st-logs-msg" role="status"></p>') +
        "</section>" +
        '<section class="section fm-section" id="st-fm" aria-labelledby="st-h-fm" hidden></section>';
      wirePrefs();
      PD.on(R, "click", "[data-act=fm-create]", (e, el) => createFalseMirror(el));
      PD.on(R, "click", "[data-act=fm-delete]", (e, el) => deleteFalseMirror(el));
      $("#st-net", R).addEventListener("change", e => save("network.allowed", e.target.checked, $("#st-net-msg", R)));
      PD.on(R, "click", "[data-act=update]", (e, el) => checkUpdates(el));
      PD.on(R, "click", "#st-login [data-act=borrow], #st-login [data-act=steal]", (e, el) => PD.busy(el, () => takeLogin(el.dataset.act)));
      PD.on(R, "click", "[data-act=logs]", (e, el) => sendLogs(el));
      wireLookups();
      // the Language row's label is the cycling word, beside its "?" (row() was given no label of its own)
      const lr = $("#st-lang", R).closest(".row").querySelector(".label");
      lr.insertAdjacentHTML("afterbegin", '<span id="st-lang-label">' + esc(t("settings.language")) + "</span>");
    },
    async show() {
      // the minute starts now; leaving the screen stops it (hide)
      clearTimeout(S.timer);
      S.revealed = false;
      S.timer = setTimeout(haunt, 60000);
      S.books = S.fmBooks = null;
      const [s] = await PD.safe(PD.loadSettings());
      S.s = s || PD.settings;
      fill(); fillPrefs(); paintNote(); paintFalseMirror();
      cycleLanguageLabel();
    },
    hide() {
      clearTimeout(S.timer);
      S.revealed = false;
      const box = R && $("#st-note", R); if (box) box.innerHTML = "";        // away from the screen: the note's 20 seconds start over
    },
    poll() { if (!R.querySelector("#st-login .hint")) paintLogin(); },
  });
})();
