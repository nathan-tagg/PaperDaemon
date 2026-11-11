"use strict";
/* One model slot's form, shared by setup and the Models screen: where the model runs (hosted with an API key,
   hosted locally with an optional start script, or -- a text model -- a command-line program on this computer), its
   harness, and a lineup's web search. */
(() => {
  const { $, esc, mk } = PD;
  const HOSTED = {
    text: [{ id: "anthropic", label: "Anthropic", api: "anthropic", at: "https://api.anthropic.com" },
           { id: "openai", label: "OpenAI", api: "openai", at: "https://api.openai.com" },
           { id: "other", label: PD.t("slot.other_provider"), api: "openai", at: "" }],
    image: [{ id: "openai", label: "OpenAI", api: "openai-images", at: "https://api.openai.com" },
            { id: "other", label: PD.t("slot.other_provider"), api: "openai-images", at: "" }],
  };
  const LOCAL_API = { text: "openai", image: "sdapi" };
  // A COMMAND LINE is a source of its own for a text model: a program on this computer, run once a turn. Its slot's
  // location is the command, WHOLE, as typed: the program and the user's own arguments, the model among them. There is
  // no provider, address, key or model field (how a model is named is the program's own syntax), and nothing here
  // names a program -- how one is spoken to is data (models/cli.py).
  const CLI_API = "cli";
  // AN API KEY BELONGS TO A SERVER (or a search service), not to a lineup: every lineup that uses it shares it, and
  // lineups on different servers never overwrite each other's. Its name in the credential store, as the engine makes it
  const keyName = (role, where) => {
    let w = String(where || "").trim();
    if (w.includes("://")) { try { w = new URL(w).hostname || w; } catch (e) { /* not an address: as typed */ } }
    return "key:" + role + ":" + (w.toLowerCase() || "default");
  };
  const keyKept = (role, where) => !!(PD.status && PD.status.secrets && (PD.status.secrets.keys || []).includes(keyName(role, where)));
  /** Where a form's key is for: the hosted server's address, or the search service's name. */
  const keyWhere = (role, f) => {
    if (role === "search") return f.provider || "";
    const pr = HOSTED[role].find(h => h.id === f.provider) || HOSTED[role][0];
    return pr.id === "other" ? f.at : pr.at;
  };

  // THE TEXT MODEL'S HARNESS IS ONE OF THREE BASES, by the model's strength (the slider), and its CAPABILITIES are what
  // the model can do on its own (the checkboxes). A box left as the base has it is not saved: moving the slider then
  // gives the new base's own values.
  const BASES = [["weak-text", "weak"], ["default-text", "medium"], ["lean-default", "strong"]];
  const CAPS = ["vision", "web_search", "image_generation"];
  const LATER = ["image_generation"];                      // shown, and not yet something PaperDaemon can use
  const capsOf = slot => {
    const over = (slot && slot.overrides) || {}, out = {};
    CAPS.forEach(c => { if (c in over) out[c] = !!over[c]; });
    return out;
  };

  /** A lineup's slot -> the form's state. */
  function formOf(role, slot) {
    slot = slot || {};
    const loc = slot.location || "", harness = slot.harness || "default-" + role;
    const caps = capsOf(slot);
    if (role === "text" && slot.api === CLI_API) return { kind: "cli", provider: HOSTED[role][0].id, at: loc, model: "", harness, caps };
    if (!loc) return { kind: role === "image" ? "none" : "hosted", provider: HOSTED[role][0].id, at: "", model: slot.model || "", harness, caps };
    const p = HOSTED[role].filter(h => h.at && loc.startsWith(h.at)).sort((a, b) => b.at.length - a.at.length)[0];   // (the longest address that fits)
    if (p || !PD.isLocal(loc)) return { kind: "hosted", provider: p ? p.id : "other", at: loc, model: slot.model || "", harness, caps };
    return { kind: "local", provider: HOSTED[role][0].id, at: loc, model: slot.model || "", scriptText: slot.script_text || "", harness, caps };
  }

  function select(id, opts, value) {
    return '<span class="select"><select class="field" id="' + id + '">' +
      opts.map(([v, l]) => '<option value="' + esc(v) + '"' + (v === value ? " selected" : "") + ">" + esc(l) + "</option>").join("") + "</select></span>";
  }

  /** The image model's harness: a list of every harness of the kind that is offered, the default first. It always holds
      the one the user picked; PaperDaemon never chooses one. Under it, the picked harness's own description. */
  /** A field's label, opened (the caller closes it after the field): its text and, to its right, a "?" with the
      help. Tied to the field by `for`, so the "?" inside it does not take the label's clicks. */
  const lab = (forId, key, help, cls) => '<label for="' + forId + '"' + (cls ? ' class="' + cls + '"' : "") + '><span class="lab">' +
    esc(PD.t(key)) + PD.helpTip(PD.t(help)) + "</span>";

  function harnessRow(p, role, f, harnesses) {
    if (role === "text") return textHarness(p, f, harnesses);
    const list = (harnesses || []).filter(h => h.kind === role && h.offered !== false);   // (one that only holds what others share is not offered)
    const id = p + "-" + role + "-harness";
    return '<div class="grid2"><div class="field-col"><div class="label-row">' + lab(id, "slot.harness", "slot.harness.help") + "</label>" +
      '<button type="button" class="link-btn" data-act="addharness" data-kind="' + esc(role) + '">' + esc(PD.t("slot.add_harness")) + "</button></div>" +
      select(id, list.map(h => [h.id, h.name]), f.harness) +
      '<p class="harness-note">' + esc(((list.find(h => h.id === f.harness) || list[0] || {}).notes) || "") + "</p>" +
      '<p class="harness-note">' + esc(PD.t("slot.image.instead")) + "</p>" +
      "</div><span></span></div>";
  }

  /** The base a harness is (or is built on): one of BASES' ids, else Medium's. */
  function baseOf(id, harnesses) {
    const by = new Map((harnesses || []).map(h => [h.id, h]));
    for (let h = by.get(id), n = 0; h && n < 20; h = by.get(h.extends), n++) {
      if (BASES.some(b => b[0] === h.id)) return h.id;
    }
    return "default-text";
  }

  /** What the text model can do on its own: the box as the user set it, else as its harness has it. */
  const capValue = (f, c, harnesses) => {
    if (LATER.includes(c)) return false;
    if (f.caps && c in f.caps) return !!f.caps[c];
    const h = (harnesses || []).find(x => x.id === f.harness);
    return !!(h && h.fields && h.fields[c]);
  };

  /** The text model's Harness (a Weak / Medium / Strong slider, the base's description, and the user's own harness files
      when there are any) and its Capabilities (checkboxes, and a line saying what the model can do). */
  function textHarness(p, f, harnesses) {
    const id = p + "-text";
    const list = (harnesses || []).filter(h => h.kind === "text" && h.offered !== false);
    const own = list.filter(h => h.source === "user");
    const mine = own.find(h => h.id === f.harness);
    const base = baseOf(f.harness, list);
    const at = Math.max(0, BASES.findIndex(b => b[0] === base));
    const helpLink = '<button type="button" class="link-btn" data-script-help="harness">' + esc(PD.t("common.help")) + "</button>";
    let out = '<div class="harness-box"><div class="label-row">' + lab(id + "-strength", "slot.harness", "slot.harness.help") + "</label>" +
      '<span class="label-links"><button type="button" class="link-btn" data-act="addharness" data-kind="text">' + esc(PD.t("slot.add_harness")) + "</button>" +
      helpLink + "</span></div>" +
      '<input type="range" class="strength" id="' + id + '-strength" min="0" max="2" step="1" value="' + at + '"' +
      ' aria-valuetext="' + esc(PD.t("slot.base." + BASES[at][1])) + '">' +
      '<div class="strength-ticks">' + BASES.map((b, i) => '<button type="button" class="tick' + (i === at ? " on" : "") + '" data-strength="' + i + '">' +
        esc(PD.t("slot.base." + b[1])) + "</button>").join("") + "</div>" +
      '<p class="harness-note">' + esc(mine ? (mine.notes || "") : PD.t("slot.base." + BASES[at][1] + ".about")) + "</p>";
    if (own.length) {
      out += '<label class="own-harness">' + esc(PD.t("slot.own_harness")) + " " +
        select(id + "-own", [["", PD.t("slot.own_harness.none")]].concat(own.map(h => [h.id, h.name])), mine ? mine.id : "") + "</label>";
    }
    const on = CAPS.filter(c => capValue(f, c, list));
    out += '<div class="label-row caps-head"><span class="lab">' + esc(PD.t("slot.capabilities")) + PD.helpTip(PD.t("slot.capabilities.help")) + "</span>" +
      helpLink + "</div>" +
      '<div class="caps">' + CAPS.map(c => '<label class="check-label"><input type="checkbox" id="' + id + "-cap-" + c + '"' +
        (on.includes(c) ? " checked" : "") + (LATER.includes(c) ? " disabled" : "") + "> " + esc(PD.t("slot.cap." + c)) +
        (LATER.includes(c) ? ' <span class="dim">(' + esc(PD.t("slot.cap.not_yet")) + ")</span>" : "") + "</label>").join("") + "</div>" +
      '<p class="harness-note">' + esc(on.length ? PD.t("slot.can", { list: on.map(c => PD.t("slot.cap." + c)).join(", ") }) : PD.t("slot.can_none")) +
      "</p>" + '<p class="harness-note">' + esc(PD.t("slot.cap.warning")) + "</p></div>";
    return out;
  }

  /** The form for one slot. p: the id prefix; test: the test line's html (hosted only); lineup: the lineup's name, for
      the link to its LoRA folder under the image model's start script (none in the first-run setup). */
  function html(p, role, f, harnesses, test, lineup) {
    const id = p + "-" + role;
    const kinds = (role === "image" ? [["none", PD.t("slot.none")]] : []).concat([["hosted", PD.t("slot.api_key")], ["local", PD.t("slot.local")]])
      .concat(role === "text" ? [["cli", PD.t("slot.cli")]] : []);
    let out = '<div class="grid2">' + lab(id + "-kind", "slot.source", "slot.source.help") + select(id + "-kind", kinds, f.kind) + "</label><span></span></div>";
    if (f.kind === "hosted") {
      const pr = HOSTED[role].find(h => h.id === f.provider) || HOSTED[role][0];
      out += '<div class="grid2">' + lab(id + "-provider", "slot.provider", "slot.provider.help") + select(id + "-provider", HOSTED[role].map(h => [h.id, h.label]), pr.id) + "</label>" +
        (pr.id === "other" ? lab(id + "-at", "slot.address", "slot.address.help_hosted") + '<input class="field" id="' + id + '-at" value="' + esc(f.at) + '" placeholder="https://…"></label>' : "") +
        lab(id + "-model", "slot.model", "slot.model.help") + '<input class="field" id="' + id + '-model" value="' + esc(f.model) + '"></label>' +
        lab(id + "-key", "slot.api_key", "slot.api_key.help") + '<input class="field" type="password" id="' + id + '-key" autocomplete="off" value="' + esc(f.key || "") + '" placeholder="' + (keyKept(role, keyWhere(role, f)) ? esc(PD.t("slot.saved")) : "") + '"></label>' + "</div>" +
        harnessRow(p, role, f, harnesses) +
        '<div class="actions"><button type="button" class="btn small" data-act="test" data-role="' + role + '">' + esc(PD.t("common.test")) + '</button><span id="' + id + '-test">' + (test || "") + "</span></div>";
    } else if (f.kind === "cli") {
      out += '<div class="grid2">' + lab(id + "-at", "slot.command", "slot.command.help") + '<input class="field mono" id="' + id + '-at" value="' + esc(f.at) + '" spellcheck="false" autocomplete="off"></label><span></span></div>' +
        harnessRow(p, role, f, harnesses) +
        '<div class="actions"><button type="button" class="btn small" data-act="test" data-role="' + role + '">' + esc(PD.t("common.test")) + '</button><span id="' + id + '-test">' + (test || "") + "</span></div>";
    } else if (f.kind === "local") {
      out += '<div class="grid2">' + lab(id + "-at", "slot.address", "slot.address.help_local") + '<input class="field" id="' + id + '-at" value="' + esc(f.at) + '" placeholder="http://127.0.0.1:8080"></label><span></span></div>' +
        harnessRow(p, role, f, harnesses) +
        '<div class="script-box"><div class="label-row"><span>' + esc(PD.t("slot.script_label")) + "</span>" +
        PD.scriptHelpLink(role) + "</div>" +
        PD.codeHtml(id + "-scripttext", f.scriptText || "", 14, PD.t("slot.script"), false, "bat") +
        // the lineup's LoRA folder, a small link under the box's right edge, in the space already below it
        (role === "image" && lineup ? '<button type="button" class="script-link" data-act="loras" data-lineup="' + esc(lineup) + '" title="' +
          esc(PD.t("slot.loras_folder.help")) + '">' + esc(PD.t("slot.loras_folder")) + "</button>" : "") + "</div>";
    }
    return out;
  }

  /** What is typed in the form -> f (so a repaint or a tab switch keeps it). */
  function read(root, p, role, f) {
    const v = s => { const el = $("#" + p + "-" + role + s, root); return el ? el.value.trim() : null; };
    for (const [k, s] of [["kind", "-kind"], ["provider", "-provider"], ["at", "-at"], ["model", "-model"], ["key", "-key"]]) {
      const x = v(s); if (x !== null) f[k] = x;
    }
    const h = v("-harness");
    if (h) f.harness = h;
    if (role === "text") {
      // the slider, or the user's own harness when one is picked: a new harness starts from its own capabilities
      const st = $("#" + p + "-text-strength", root), ownEl = $("#" + p + "-text-own", root);
      if (st) {
        const picked = ownEl && ownEl.value ? ownEl.value : BASES[Math.max(0, Math.min(2, Number(st.value) || 0))][0];
        if (picked !== f.harness) { f.harness = picked; f.caps = {}; return f; }
      }
      CAPS.forEach(c => {
        const el = $("#" + p + "-text-cap-" + c, root);
        if (!el || el.disabled) return;
        f.caps = f.caps || {};
        const h0 = (PD.slots.harnesses || []).find(x => x.id === f.harness);
        const dflt = !!(h0 && h0.fields && h0.fields[c]);
        if (el.checked === dflt) delete f.caps[c]; else f.caps[c] = el.checked;
      });
    }
    const st = $("#" + p + "-" + role + "-scripttext", root);
    if (st) f.scriptText = st.value;
    return f;
  }

  /** f -> the lineup's slot (base: the slot as saved). */
  function slotOf(role, f, base) {
    const o = Object.assign({}, base || {}, { harness: f.harness || "default-" + role });
    if (role === "text") {
      // the capabilities the user set apart from the harness's own; the rest come from the harness
      const over = Object.assign({}, (base && base.overrides) || {});
      CAPS.forEach(c => { delete over[c]; });
      o.overrides = Object.assign(over, f.caps || {});
    }
    if (f.kind === "none") return Object.assign(o, { location: "", script: "", script_text: "", model: "" });
    if (f.kind === "local") return Object.assign(o, { location: f.at, script: "", script_text: (f.scriptText || "").replace(/\r?\n/g, "\r\n"), api: LOCAL_API[role], model: f.model || "" });
    if (f.kind === "cli") return Object.assign(o, { location: f.at || "", script: "", script_text: "", api: CLI_API, model: "" });
    const pr = HOSTED[role].find(h => h.id === f.provider) || HOSTED[role][0];
    return Object.assign(o, { location: pr.id === "other" ? f.at : pr.at, script: "", script_text: "", api: pr.api, model: f.model });
  }

  /** The API keys typed into the forms, saved to the credential store; each is cleared once saved. -> error or "". */
  async function saveKeys(forms) {
    for (const role of ["text", "image", "search"]) {
      const f = forms[role];
      if (f && (f.kind === "hosted" || f.kind === "api") && f.key) {
        const where = keyWhere(role, f);
        if (!where) return PD.t("slot.key_where");
        const [, e] = await PD.safe(PD.api("PUT", "/keys/" + role, { where, value: f.key }));
        if (e) return PD.errText(e);
        f.key = "";
      }
    }
    return "";
  }

  const SEARCH_SERVICES = [["brave", "Brave Search"], ["tavily", "Tavily"], ["exa", "Exa"], ["serper", "Serper"]];

  /** A lineup's web search -> the form's state. */
  function searchOf(sr) {
    sr = sr || {};
    const kind = sr.kind === "searxng" ? "local" : (sr.kind || "none");
    return { kind, provider: sr.provider || "brave", at: sr.url || "", scriptText: sr.script_text || "", key: "" };
  }

  /** The Network tab: the lineup's web search (none, a search service with an API key, or a search server hosted
      locally). */
  function searchHtml(p, f, test) {
    return '<h3 class="tab-h">' + esc(PD.t("net.search")) + "</h3>" + '<p class="tab-note">' + esc(PD.t("net.instead")) + "</p>" +
      searchForm(p, f, test);
  }

  function searchForm(p, f, test) {
    const id = p + "-search";
    let out = '<div class="grid2">' + lab(id + "-kind", "slot.source", "net.source.help") + select(id + "-kind", [["none", PD.t("slot.none")], ["api", PD.t("net.service_key")], ["local", PD.t("slot.local")]], f.kind) + "</label><span></span></div>";
    if (f.kind === "api") {
      out += '<div class="grid2">' + lab(id + "-provider", "net.service", "net.service.help") + select(id + "-provider", SEARCH_SERVICES, f.provider) + "</label>" +
        lab(id + "-key", "slot.api_key", "slot.api_key.help") + '<input class="field" type="password" id="' + id + '-key" autocomplete="off" value="' + esc(f.key || "") + '" placeholder="' + (keyKept("search", keyWhere("search", f)) ? esc(PD.t("slot.saved")) : "") + '"></label></div>' +
        '<div class="actions"><button type="button" class="btn small" data-act="test" data-role="search">' + esc(PD.t("common.test")) + '</button><span id="' + id + '-test">' + (test || "") + "</span></div>";
    } else if (f.kind === "local") {
      out += '<div class="grid2">' + lab(id + "-at", "slot.address", "net.address.help") + '<input class="field" id="' + id + '-at" value="' + esc(f.at) + '" placeholder="http://127.0.0.1:8888"></label><span></span></div>' +
        '<div class="script-box"><div class="label-row"><span>' + esc(PD.t("slot.script_label")) + "</span>" +
        PD.scriptHelpLink("search") + "</div>" +
        PD.codeHtml(id + "-scripttext", f.scriptText || "", 14, PD.t("net.script"), false, "bat") + "</div>";
    }
    return out;
  }

  function readSearch(root, p, f) {
    const v = s => { const el = $("#" + p + "-search" + s, root); return el ? el.value.trim() : null; };
    for (const [k, s] of [["kind", "-kind"], ["provider", "-provider"], ["at", "-at"], ["key", "-key"]]) {
      const x = v(s); if (x !== null) f[k] = x;
    }
    const st = $("#" + p + "-search-scripttext", root);
    if (st) f.scriptText = st.value;
    return f;
  }

  /** The search form -> the lineup's search. */
  function searchOut(f) {
    if (f.kind === "api") return { kind: "api", provider: f.provider, url: "", script_text: "" };
    if (f.kind === "local") return { kind: "local", provider: "", url: f.at, script_text: (f.scriptText || "").replace(/\r?\n/g, "\r\n") };
    return { kind: "none", provider: "", url: "", script_text: "" };
  }

  // ---- the Tagging tab: the lineup's tags, in order. Every tag is watched for (a page tagged with it goes to this
  // lineup), and a page gets the prompts of the tags on it, its notebook and its folders, in this order.

  const tagsOf = tg => (Array.isArray(tg) ? tg : []).map(c => ({ name: c.name || "", prompt: c.prompt || "" }));

  const GRIP = '<svg viewBox="0 0 12 12" aria-hidden="true"><g fill="currentColor">' +
    [2, 6, 10].map(y => [2, 6, 10].map(x => '<circle cx="' + x + '" cy="' + y + '" r="1.2"/>').join("")).join("") + "</g></svg>";

  function tagsHtml(p, f) {
    const id = p + "-tags";
    return '<p class="tab-note">' + esc(PD.t("tags.note")) + "</p>" +
      '<div class="custom-tags" id="' + id + '-list">' +
      f.map((c, i) => '<div class="custom-tag tag-card" data-i="' + i + '">' +
        '<button type="button" class="grip" draggable="true" data-i="' + i + '" aria-label="' + esc(PD.t("tags.move", { name: c.name || PD.t("tags.this") })) +
        '" title="' + esc(PD.t("tags.drag")) + '">' + GRIP + "</button>" +
        '<div class="tag-fields"><div class="label-row">' + lab(id + "-name-" + i, "tags.tag", "tags.tag.help", "tag-name") + '<input class="field mono w-m" id="' + id + "-name-" + i + '" value="' + esc(c.name) +
        '" placeholder="PaperDaemon" autocomplete="off" spellcheck="false"></label>' +
        '<button type="button" class="link-btn" data-act="deltag" data-i="' + i + '">' + esc(PD.t("common.remove")) + "</button></div>" +
        lab(id + "-prompt-" + i, "tags.prompt", "tags.prompt.help") + '<textarea class="field" id="' + id + "-prompt-" + i + '" rows="6" placeholder="' + esc(PD.t("tags.prompt_blank")) + '">' + esc(c.prompt) + "</textarea></label></div></div>").join("") +
      "</div>" +
      '<div class="actions"><button type="button" class="link-btn" data-act="addtag">' + esc(PD.t("tags.add")) + "</button></div>";
  }

  function readTags(root, p, f) {
    const id = p + "-tags";
    f.forEach((c, i) => {
      const n = $("#" + id + "-name-" + i, root), t = $("#" + id + "-prompt-" + i, root);
      if (n) c.name = n.value.trim();
      if (t) c.prompt = t.value;
    });
    return f;
  }

  const tagsOut = f => f.filter(c => c.name || c.prompt.trim()).map(c => ({ name: c.name, prompt: c.prompt }));

  /** The tag cards' handles: drag one onto another card, or press the arrow keys on it, to move a tag.
      tags() gives the screen's list; repaint(focusIndex) paints it again after a move. */
  function wireTagSort(root, p, tags, repaint) {
    let from = null;
    const move = (a, b) => {
      const f = tags(); if (!f || a === b || a < 0 || b < 0 || a >= f.length || b >= f.length) return;
      readTags(root, p, f);
      f.splice(b, 0, f.splice(a, 1)[0]);
      repaint(b);
    };
    root.addEventListener("dragstart", e => {
      const g = e.target.closest && e.target.closest(".grip"); if (!g) return;
      from = Number(g.dataset.i);
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", String(from)); } catch (x) { /* some hosts refuse it */ }
      const card = g.closest(".tag-card"); if (card) { card.classList.add("dragging"); e.dataTransfer.setDragImage(card, 16, 16); }
    });
    root.addEventListener("dragover", e => {
      if (from === null) return;
      const card = e.target.closest && e.target.closest(".tag-card"); if (!card) return;
      e.preventDefault();
      root.querySelectorAll(".tag-card.over").forEach(x => x !== card && x.classList.remove("over"));
      card.classList.add("over");
    });
    root.addEventListener("drop", e => {
      if (from === null) return;
      const card = e.target.closest && e.target.closest(".tag-card"); if (!card) return;
      e.preventDefault();
      const a = from; from = null;
      move(a, Number(card.dataset.i));
    });
    root.addEventListener("dragend", () => {
      from = null;
      root.querySelectorAll(".tag-card.dragging, .tag-card.over").forEach(x => x.classList.remove("dragging", "over"));
    });
    root.addEventListener("keydown", e => {
      const g = e.target.closest && e.target.closest(".grip"); if (!g) return;
      const i = Number(g.dataset.i);
      if (e.key === "ArrowUp") { e.preventDefault(); move(i, i - 1); }
      else if (e.key === "ArrowDown") { e.preventDefault(); move(i, i + 1); }
    });
  }

  /** After a move: the moved card's handle has the focus again. */
  function focusGrip(root, i) { const g = root.querySelector('.grip[data-i="' + i + '"]'); if (g) g.focus(); }

  const testHtml = t => t === "testing" ? mk("spin") + esc(PD.t("common.testing")) : t === "ok" ? mk("ok") + esc(PD.t("common.answering")) : t ? mk("fail") + esc(t) : "";

  /** A tick under the slider moves it there. */
  document.addEventListener("click", e => {
    const t = e.target.closest && e.target.closest("[data-strength]");
    if (!t) return;
    const r = t.closest(".harness-box") && t.closest(".harness-box").querySelector("input.strength");
    if (!r || String(r.value) === t.dataset.strength) return;
    r.value = t.dataset.strength;
    r.dispatchEvent(new Event("change", { bubbles: true }));
  });

  PD.slots = { harnesses: [], tagsOf, tagsHtml, readTags, tagsOut, wireTagSort, focusGrip, formOf, html, read, slotOf, saveKeys, searchOf, searchHtml, readSearch, searchOut, testHtml };
})();
