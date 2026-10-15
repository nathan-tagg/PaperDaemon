"use strict";
/* Settings: the user's preferences (language, and how temperatures, times and weeks are written), PaperDaemon's own
   settings (the reMarkable login, the decompose inbox, the location, how often the tablet is checked, the ignore and
   standing instructions tags, network access, the social sites), and tools (checking for an update, sending the logs
   to the inbox). Once the Mirror is built and until every preference is chosen, the rail item carries a lightbulb
   and the page a note asking for a moment. */
(() => {
  const { $, esc, line } = PD;
  const t = PD.t;
  let R = null;
  const S = { s: null, notebooks: null, places: new Map() };
  const SITES = [["reddit", "Reddit"], ["hackernews", "Hacker News"], ["bluesky", "Bluesky"], ["4chan", "4chan"], ["mastodon", "Mastodon"]];
  // pathLength="1" on each line: the bulb can draw itself, stroke by stroke, the first time it appears (.draw)
  const BULB = '<svg viewBox="0 0 16 16" aria-hidden="true"><path pathLength="1" d="M8 1.5a4.5 4.5 0 0 0-2.6 8.2c.4.3.6.7.6 1.1V12h4v-1.2c0-.4.2-.8.6-1.1A4.5 4.5 0 0 0 8 1.5z"/><path pathLength="1" d="M6 13.5h4M6.8 15h2.4"/></svg>';

  /** A preference not chosen yet, and the Mirror is built: time to ask (softly). */
  PD.needsPrefs = (st, settings) => {
    const p = (settings || PD.settings || {}).prefs || {};
    const m = PD.mirrorState(st || PD.status);
    const built = !!((st || PD.status || {}).mirror || {}).complete && !m.first;      // the FIRST copy only
    return built && !(p.temperature && p.clock && p.week_start) && !noteSeen();   // until all three are chosen
  };
  // the note has been read: it stayed on screen its whole 20 seconds once (see paintNote); then it, and the rail's
  // lightbulb, are gone for good
  const NOTE_SEEN = "pd.prefs-note-seen";
  function noteSeen() {
    try { return localStorage.getItem(NOTE_SEEN) === "1"; } catch (e) { return !!PD.prefsNoteSeen; }
  }

  async function save(path, value, msgEl) {
    const [s, e] = await PD.safe(PD.saveSettings(st => { PD.setK(st, path, value); }));
    if (s) S.s = s;
    if (msgEl) { msgEl.textContent = e ? PD.errText(e) : ""; msgEl.className = "hint" + (e ? " attn" : ""); }
    paintNote(); PD.paintRail();
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

  // THE NOTE EXPIRES: a bar along its bottom edge runs down over 20 seconds while Settings is open; when it is gone,
  // so is the note. Leaving Settings takes the note away, so the next visit starts the 20 seconds again.
  // `arriving`: it appears while Settings is open (the first copy of the library just finished), so it slides down
  // into place and its bulb draws itself; on opening Settings it is simply there
  function paintNote(arriving) {
    const box = $("#st-note", R); if (!box) return;
    if (!PD.needsPrefs(PD.status, S.s)) { box.innerHTML = ""; return; }
    if (box.querySelector(".notice")) return;                  // already showing: its bar keeps running
    box.innerHTML = '<div class="notice soft' + (arriving ? " arriving" : "") + '" role="status"><span class="bulb draw">' +
      BULB + "</span><span>" + esc(t("settings.note")) +
      '</span><i class="notice-timer" aria-hidden="true"></i></div>';
    box.querySelector(".notice-timer").addEventListener("animationend", () => {
      try { localStorage.setItem(NOTE_SEEN, "1"); } catch (e) { PD.prefsNoteSeen = true; }
      paintNote(); PD.paintRail();
    });
  }

  const choice = (id, path, opts, none = true) => '<span class="select"><select class="field" id="' + id + '" data-path="' + path + '">' +
    (none ? '<option value="">' + esc(t("common.choose")) + "</option>" : "") +
    opts.map(([v, l]) => '<option value="' + v + '">' + esc(l) + "</option>").join("") + "</select></span>";
  // a row: its label, with a "?" to the label's right when there is more to say, and its control
  const row = (label, help, control) => '<div class="row"><div class="label">' + esc(label) + (help ? PD.helpTip(help) : "") +
    '</div><div class="control">' + control + "</div></div>";

  // ---- the two type-aheads: an existing notebook for the inbox, a city of the world for the location

  async function notebooks() {
    if (S.notebooks) return S.notebooks;
    const [all] = await PD.safe(PD.api("GET", "/library"));
    const by = new Map((all || []).map(d => [d.id, d]));
    const path = d => { const n = [d.name]; for (let p = by.get(d.parent), k = 0; p && k < 64; p = by.get(p.parent), k++) n.unshift(p.name); return n.join("/"); };
    S.notebooks = (all || []).filter(d => d.type === "document" && d.kind === "notebook" && !String(d.parent).startsWith("trash")).map(path).sort((a, b) => a.localeCompare(b));
    return S.notebooks;
  }

  function wireLookups() {
    PD.wireTypeahead(R, async (q, input) => {
      const el = input || document.activeElement;
      if (el && el.id === "st-lang") {              // by its own name, or its name in the window's language
        const k = q.toLowerCase(), all = PD.LANGUAGES.map(PD.languageLabel);
        return all.includes(q) ? all : all.filter(l => !k || l.toLowerCase().includes(k));
      }
      if (el && el.id === "st-inbox") {
        const k = q.toLowerCase();
        return (await notebooks()).filter(p => !k || p.toLowerCase().includes(k));
      }
      if (q.trim().length < 2) return [];
      const [list] = await PD.safe(PD.api("GET", "/places?q=" + encodeURIComponent(q)));
      (list || []).forEach(p => S.places.set(p.label, p));
      return (list || []).map(p => p.label);
    });
    $("#st-lang", R).addEventListener("change", async e => {
      const msg = $("#st-lang-msg", R), was = PD.getK(S.s, "prefs.language") || "en";
      const code = PD.LANGUAGES.find(c => PD.languageLabel(c) === e.target.value.trim());
      if (!code) { e.target.value = PD.languageLabel(was); msg.textContent = t("settings.language.pick"); msg.className = "hint attn"; return; }
      msg.textContent = "";
      if (code !== was && await save("prefs.language", code, msg)) PD.useLanguage(code);
    });
    $("#st-inbox", R).addEventListener("change", async e => {
      const v = e.target.value.trim(), msg = $("#st-inbox-msg", R), was = PD.getK(S.s, "tablet.inbox") || "";
      if (v === was) return;
      if (!(await notebooks()).includes(v)) { e.target.value = was; msg.textContent = t("settings.inbox.pick"); msg.className = "hint attn"; return; }
      if (await save("tablet.inbox", v, msg)) paintTools();
    });
    $("#st-loc", R).addEventListener("change", async e => {
      const v = e.target.value.trim(), msg = $("#st-loc-msg", R), was = PD.getK(S.s, "location.name") || "";
      if (v === was) return;
      const p = S.places.get(v);
      if (!p) { e.target.value = was; msg.textContent = t("settings.location.pick"); msg.className = "hint attn"; return; }
      const [s, err] = await PD.safe(PD.saveSettings(st => {
        PD.setK(st, "location.name", p.label); PD.setK(st, "location.lat", p.lat);
        PD.setK(st, "location.lon", p.lon); PD.setK(st, "location.holidays", p.holidays);
      }));
      if (s) S.s = s;
      if (err) e.target.value = was;
      msg.textContent = err ? PD.errText(err) : ""; msg.className = "hint" + (err ? " attn" : "");
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
    ["prefs.temperature", "prefs.clock", "prefs.week_start"].forEach(p => { const el = R.querySelector('[data-path="' + p + '"]'); if (el) el.value = PD.getK(s, p) || (PD.regionDefaults || {})[p.split(".")[1]] || ""; });
    $("#st-lang", R).value = PD.languageLabel(PD.getK(s, "prefs.language") || "en");
    $("#st-inbox", R).value = PD.getK(s, "tablet.inbox") || "";
    $("#st-loc", R).value = PD.getK(s, "location.name") || "";
    $("#st-net", R).checked = PD.getK(s, "network.allowed") !== false;
    $("#st-ignore", R).value = PD.getK(s, "tags.ignore") || "ignore";
    $("#st-sprompt", R).value = PD.getK(s, "tags.sprompt") || "sprompt";
    const sites = PD.getK(s, "social.sites") || [];
    R.querySelectorAll("[data-site]").forEach(el => { el.checked = sites.includes(el.dataset.site); el.disabled = !$("#st-net", R).checked; });
    paintNote(); paintTools(); paintLogin();
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
        row(t("settings.temperature"), t("settings.temperature.help"), choice("st-temp", "prefs.temperature",
          [["fahrenheit", t("settings.temperature.f")], ["celsius", t("settings.temperature.c")]])) +
        row(t("settings.clock"), "", choice("st-clock", "prefs.clock", [["12", t("settings.clock.12")], ["24", t("settings.clock.24")]])) +
        row(t("settings.week"), "", choice("st-week", "prefs.week_start", [["sunday", t("day.sunday")], ["monday", t("day.monday")], ["saturday", t("day.saturday")]])) +
        "</section>" +
        '<section class="section" aria-labelledby="st-h-set"><h2 id="st-h-set">' + esc(t("settings.label")) + "</h2>" +
        row(t("settings.remarkable"), "", '<div id="st-login"></div>') +
        row(t("settings.inbox"), t("settings.inbox.help"),
          '<input class="field w-l" id="st-inbox" data-ta="[]" spellcheck="false" placeholder="' + esc(t("settings.inbox.placeholder")) +
          '"><p class="hint" id="st-inbox-msg" role="status"></p>') +
        row(t("settings.location"), t("settings.location.help"),
          '<input class="field w-l" id="st-loc" data-ta="[]" spellcheck="false" placeholder="' + esc(t("settings.location.placeholder")) +
          '"><p class="hint" id="st-loc-msg" role="status"></p>') +
        row(t("settings.ignore"), t("settings.ignore.help"),
          '<input class="field mono w-m" id="st-ignore" spellcheck="false" autocomplete="off"><p class="hint" id="st-ignore-msg" role="status"></p>') +
        row(t("settings.sprompt"), t("settings.sprompt.help"),
          '<input class="field mono w-m" id="st-sprompt" spellcheck="false" autocomplete="off"><p class="hint" id="st-sprompt-msg" role="status"></p>') +
        row(t("settings.network"), t("settings.network.help"),
          '<label class="check-label"><input type="checkbox" id="st-net"> ' + esc(t("settings.network.allow")) +
          '</label><p class="hint" id="st-net-msg" role="status"></p>') +
        row(t("settings.social"), t("settings.social.help"),
          '<div class="checks-row">' + SITES.map(([v, l]) => '<label class="check-label"><input type="checkbox" data-site="' + v + '"> ' + esc(l) + "</label>").join("") +
          '</div><p class="hint" id="st-sites-msg" role="status"></p>') +
        "</section>" +
        '<section class="section" aria-labelledby="st-h-tools"><h2 id="st-h-tools">' + esc(t("settings.tools")) + "</h2>" +
        row(t("settings.updates"), t("settings.updates.help"),
          '<span class="value num">' + PD.tHtml("settings.version", { version: '<span id="st-ver"></span>' }) +
          '</span><button type="button" class="btn" data-act="update">' + esc(t("settings.updates.check")) +
          '</button><span class="upd-spin" id="st-upd-spin" hidden><i class="mk spin"></i></span>' +
          '<p class="hint" id="st-upd-msg" role="status"></p>') +
        row(t("settings.logs"), t("settings.logs.help"),
          '<button type="button" class="btn" data-act="logs">' + esc(t("settings.logs.send")) + '</button><p class="hint" id="st-logs-msg" role="status"></p>') +
        "</section>";
      R.querySelectorAll("select[data-path]").forEach(el => el.addEventListener("change", async () => {
        await save(el.dataset.path, el.value);
      }));
      [["st-ignore", "tags.ignore", "ignore"], ["st-sprompt", "tags.sprompt", "sprompt"]].forEach(([id, path, dflt]) =>
        $("#" + id, R).addEventListener("change", async e => {
          const v = e.target.value.trim();
          if (!v) e.target.value = PD.getK(S.s, path) || dflt;
          else if (!await save(path, v, $("#" + id + "-msg", R))) e.target.value = PD.getK(S.s, path) || dflt;
        }));
      $("#st-net", R).addEventListener("change", async e => {
        await save("network.allowed", e.target.checked, $("#st-net-msg", R));
        R.querySelectorAll("[data-site]").forEach(el => { el.disabled = !e.target.checked; });
      });
      R.querySelectorAll("[data-site]").forEach(el => el.addEventListener("change", () =>
        save("social.sites", [...R.querySelectorAll("[data-site]:checked")].map(x => x.dataset.site), $("#st-sites-msg", R))));
      PD.on(R, "click", "[data-act=update]", (e, el) => checkUpdates(el));
      PD.on(R, "click", "#st-login [data-act=borrow], #st-login [data-act=steal]", (e, el) => PD.busy(el, () => takeLogin(el.dataset.act)));
      PD.on(R, "click", "[data-act=logs]", (e, el) => sendLogs(el));
      wireLookups();
      // the Language row's label is the cycling word, beside its "?" (row() was given no label of its own)
      const lr = $("#st-lang", R).closest(".row").querySelector(".label");
      lr.insertAdjacentHTML("afterbegin", '<span id="st-lang-label">' + esc(t("settings.language")) + "</span>");
    },
    async show() {
      S.notebooks = null;
      const [s] = await PD.safe(PD.loadSettings());
      S.s = s || PD.settings;
      fill();
      cycleLanguageLabel();
    },
    poll() { paintNote(true); if (!R.querySelector("#st-login .hint")) paintLogin(); },
    hide() { const box = $("#st-note", R); if (box) box.innerHTML = ""; },     // away from Settings: the timer starts over
  });
})();
