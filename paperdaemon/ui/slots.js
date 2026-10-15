"use strict";
/* One model slot's form, shared by setup and the Models screen: where the model runs (hosted with an API key, or
   hosted locally with an optional start script), its harness, and a lineup's web search. */
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

  /** A lineup's slot -> the form's state. */
  function formOf(role, slot) {
    slot = slot || {};
    const loc = slot.location || "", harness = slot.harness || "auto";
    if (!loc) return { kind: role === "image" ? "none" : "hosted", provider: HOSTED[role][0].id, at: "", model: slot.model || "", harness };
    const p = HOSTED[role].find(h => h.at && loc.startsWith(h.at));
    if (p || !PD.isLocal(loc)) return { kind: "hosted", provider: p ? p.id : "other", at: loc, model: slot.model || "", harness };
    return { kind: "local", provider: HOSTED[role][0].id, at: loc, model: slot.model || "", scriptText: slot.script_text || "", harness };
  }

  function select(id, opts, value) {
    return '<span class="select"><select class="field" id="' + id + '">' +
      opts.map(([v, l]) => '<option value="' + esc(v) + '"' + (v === value ? " selected" : "") + ">" + esc(l) + "</option>").join("") + "</select></span>";
  }

  const AUTO = PD.t("slot.harness_auto");

  /** The harness, typed ahead: the box suggests every harness of the kind by name; empty means automatic. */
  /** A field's label, opened (the caller closes it after the field): its text and, to its right, a "?" with the
      help. Tied to the field by `for`, so the "?" inside it does not take the label's clicks. */
  const lab = (forId, key, help, cls) => '<label for="' + forId + '"' + (cls ? ' class="' + cls + '"' : "") + '><span class="lab">' +
    esc(PD.t(key)) + PD.helpTip(PD.t(help)) + "</span>";

  function harnessRow(p, role, f, harnesses) {
    const list = (harnesses || []).filter(h => h.kind === role);
    const cur = f.harness && f.harness !== "auto" ? ((list.find(h => h.id === f.harness) || {}).name || f.harness) : "";
    const id = p + "-" + role + "-harness";
    return '<div class="grid2"><div class="field-col"><div class="label-row">' + lab(id, "slot.harness", "slot.harness.help") + "</label>" +
      '<button type="button" class="link-btn" data-act="addharness" data-kind="' + esc(role) + '">' + esc(PD.t("slot.add_harness")) + "</button></div>" +
      '<input class="field" id="' + id + '" data-ta="' + esc(JSON.stringify(list.map(h => h.name))) + '" value="' + esc(cur) + '" placeholder="' + esc(AUTO) + '" spellcheck="false">' +
      "</div><span></span></div>";
  }

  /** What the harness box holds -> a harness id ("auto" when empty or not a harness's name). */
  function harnessId(text, role, harnesses) {
    const t = String(text || "").trim().toLowerCase();
    if (!t || t === AUTO.toLowerCase()) return "auto";
    const h = (harnesses || []).find(x => x.kind === role && (x.name.toLowerCase() === t || x.id.toLowerCase() === t));
    return h ? h.id : "auto";
  }

  /** The form for one slot. p: the id prefix; test: the test line's html (hosted only). */
  function html(p, role, f, harnesses, test) {
    const id = p + "-" + role;
    const kinds = (role === "image" ? [["none", PD.t("slot.none")]] : []).concat([["hosted", PD.t("slot.api_key")], ["local", PD.t("slot.local")]]);
    let out = '<div class="grid2">' + lab(id + "-kind", "slot.source", "slot.source.help") + select(id + "-kind", kinds, f.kind) + "</label><span></span></div>";
    if (f.kind === "hosted") {
      const pr = HOSTED[role].find(h => h.id === f.provider) || HOSTED[role][0];
      out += '<div class="grid2">' + lab(id + "-provider", "slot.provider", "slot.provider.help") + select(id + "-provider", HOSTED[role].map(h => [h.id, h.label]), pr.id) + "</label>" +
        (pr.id === "other" ? lab(id + "-at", "slot.address", "slot.address.help_hosted") + '<input class="field" id="' + id + '-at" value="' + esc(f.at) + '" placeholder="https://…"></label>' : "") +
        lab(id + "-model", "slot.model", "slot.model.help") + '<input class="field" id="' + id + '-model" value="' + esc(f.model) + '"></label>' +
        lab(id + "-key", "slot.api_key", "slot.api_key.help") + '<input class="field" type="password" id="' + id + '-key" autocomplete="off" value="' + esc(f.key || "") + '" placeholder="' + (keyKept(role, keyWhere(role, f)) ? esc(PD.t("slot.saved")) : "") + '"></label></div>' +
        harnessRow(p, role, f, harnesses) +
        '<div class="actions"><button type="button" class="btn small" data-act="test" data-role="' + role + '">' + esc(PD.t("common.test")) + '</button><span id="' + id + '-test">' + (test || "") + "</span></div>";
    } else if (f.kind === "local") {
      out += '<div class="grid2">' + lab(id + "-at", "slot.address", "slot.address.help_local") + '<input class="field" id="' + id + '-at" value="' + esc(f.at) + '" placeholder="http://127.0.0.1:8080"></label><span></span></div>' +
        harnessRow(p, role, f, harnesses) +
        '<div class="script-box"><div class="label-row"><span>' + esc(PD.t("slot.script_label")) + "</span>" +
        PD.scriptHelpLink(role) + "</div>" +
        PD.codeHtml(id + "-scripttext", f.scriptText || "", 14, PD.t("slot.script"), false, "bat") + "</div>";
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
    if (h !== null) f.harness = harnessId(h, role, PD.slots.harnesses);
    const st = $("#" + p + "-" + role + "-scripttext", root);
    if (st) f.scriptText = st.value;
    return f;
  }

  /** f -> the lineup's slot (base: the slot as saved). */
  function slotOf(role, f, base) {
    const o = Object.assign({}, base || {}, { harness: f.harness || "auto" });
    if (f.kind === "none") return Object.assign(o, { location: "", script: "", script_text: "", model: "" });
    if (f.kind === "local") return Object.assign(o, { location: f.at, script: "", script_text: (f.scriptText || "").replace(/\r?\n/g, "\r\n"), api: LOCAL_API[role], model: f.model || "" });
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
    return '<h3 class="tab-h">' + esc(PD.t("net.search")) + "</h3>" + searchForm(p, f, test);
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

  PD.slots = { harnesses: [], tagsOf, tagsHtml, readTags, tagsOut, wireTagSort, focusGrip, formOf, html, read, slotOf, saveKeys, searchOf, searchHtml, readSearch, searchOut, testHtml };
})();
