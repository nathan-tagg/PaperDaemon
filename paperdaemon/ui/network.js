"use strict";
/* Network: the engine's port, the addresses it listens on, and the pairing token. */
(() => {
  const { $, esc } = PD;
  let R = null;
  const S = { listen: ["127.0.0.1"], port: 8770, token: null, shown: false, rotated: "" };

  const isAddress = v => {
    if (/^(\d{1,3})(\.\d{1,3}){3}$/.test(v)) return v.split(".").every(n => Number(n) <= 255);
    return v.includes(":") && /^[0-9a-f:]+$/i.test(v);
  };
  const loopback = a => a === "127.0.0.1" || a === "::1";

  const msg = (id, text, bad) => { const el = $("#" + id, R); if (!el) return; el.textContent = text || ""; el.className = "hint" + (bad ? " attn" : ""); el.hidden = !text; };

  function paintAddresses() {
    const rows = S.listen.map(a => loopback(a)
      ? '<div class="addr"><span><code>' + esc(a) + '</code> <span class="sub">' + esc(PD.t("nw.this_computer")) + '</span></span><span class="meta">' + esc(PD.t("nw.cannot_remove")) + "</span></div>"
      : '<div class="addr"><span><code>' + esc(a) + '</code></span><button type="button" class="btn quiet small" data-remove="' + esc(a) + '" aria-label="' + esc(PD.t("nw.remove_addr", { address: a })) + '">' + esc(PD.t("common.remove")) + "</button></div>").join("");
    PD.html($("#nw-addrs", R), rows);
    const other = S.listen.find(a => !loopback(a));
    PD.html($("#nw-reach", R), other
      ? '<input class="field mono w-m" readonly id="nw-url" value="http://' + esc(other.includes(":") ? "[" + other + "]" : other) + ":" + esc(S.port) + '" aria-label="' + esc(PD.t("nw.url_label")) + '">' +
        '<button type="button" class="btn quiet" data-act="copy-url">' + esc(PD.t("common.copy")) + "</button>"
      : '<span class="value sub">' + esc(PD.t("nw.local_only")) + "</span>");
    const n = $("#nw-count", R); if (n) n.textContent = "";
  }

  function paintToken() {
    const dots = "••••••••••••••••••••";
    PD.html($("#nw-token", R),
      '<input class="field mono w-m" readonly id="nw-pair" type="' + (S.shown && S.token ? "text" : "password") + '" value="' + esc(S.shown && S.token ? S.token : dots) + '" aria-label="' + esc(PD.t("nw.token")) + '">' +
      '<button type="button" class="btn" data-act="toggle">' + esc(PD.t(S.shown ? "nw.hide" : "nw.show")) + "</button>" +
      '<button type="button" class="btn" data-act="copy-token">' + esc(PD.t("common.copy")) + "</button>" +
      '<button type="button" class="btn danger" data-act="rotate">' + esc(PD.t("nw.rotate")) + "</button>" +
      (S.rotated ? '<p class="notice" style="flex-basis:100%"><strong>' + esc(PD.t("nw.rotated_at", { time: S.rotated })) + "</strong> " + esc(PD.t("nw.rotated_body")) + "</p>"
        : '<p class="hint">' + esc(PD.t("nw.token_kept")) + "</p>"));
  }

  async function token() {
    if (S.token) return S.token;
    const [d, e] = await PD.safe(PD.api("GET", "/pairing"));
    if (e) { msg("nw-token-msg", PD.errText(e), true); return null; }
    S.token = d.token; return S.token;
  }

  async function saveListen(next, port) {
    msg("nw-listen-msg", "");
    const [s, e] = await PD.safe(PD.saveSettings(st => { PD.setK(st, "server.listen", next); if (port != null) PD.setK(st, "server.port", port); }));
    if (e) { msg("nw-listen-msg", PD.errText(e), true); return false; }
    S.listen = PD.getK(s, "server.listen") || next; S.port = PD.getK(s, "server.port") || S.port;
    paintAddresses(); PD.paintRail();
    msg("nw-listen-msg", PD.t("nw.saved_restart", { time: PD.clock(new Date()) }));
    return true;
  }

  async function rotate() {
    const ok = await PD.confirm({ title: PD.t("nw.rotate_q"), body: [esc(PD.t("nw.rotate_body"))], action: PD.t("nw.rotate_action") });
    if (!ok) return;
    const [d, e] = await PD.safe(PD.api("POST", "/pairing/rotate"));
    if (e) { msg("nw-token-msg", PD.errText(e), true); return; }
    PD.pairing.set(d.token); S.token = d.token; S.shown = false; S.rotated = PD.clock(new Date());
    paintToken();
  }

  PD.screen("network", {
    label: PD.t("nw.label"), group: 1, railNum: true,
    rail() { const n = PD.getK(PD.settings, "server.listen"); return Array.isArray(n) ? esc(PD.count("count.address", n.length)) : ""; },
    mount(root) {
      R = root;
      S.token = null; S.shown = false; S.rotated = "";
      R.innerHTML =
        '<header class="page-head"><h1>' + esc(PD.t("nw.label")) + "</h1><p>" + esc(PD.t("nw.intro")) + "</p></header>" +
        '<section class="section" aria-labelledby="nw-h1"><h2 id="nw-h1">' + esc(PD.t("nw.listens")) + "</h2>" +
        '<div class="row"><div class="label"><label for="nw-port">' + esc(PD.t("nw.port")) + '</label></div><div class="control">' +
        '<input class="field num w-xs" id="nw-port" type="number" autocomplete="off">' +
        '<button type="button" class="btn" data-act="port">' + esc(PD.t("nw.save_port")) + "</button>" +
        '<p class="hint">' + esc(PD.t("nw.port_hint")) + '</p><p class="hint" id="nw-port-msg" role="status" hidden></p></div></div>' +
        '<div class="row"><div class="label">' + esc(PD.t("nw.addresses")) + "<small>" + esc(PD.t("nw.addresses_hint")) + '</small></div><div class="control stack">' +
        '<div id="nw-addrs" style="width:100%"></div>' +
        '<div class="actions" style="margin-top: var(--s2)"><input class="field mono w-s" id="nw-add" placeholder="' + esc(PD.t("nw.another")) + '" aria-label="' + esc(PD.t("nw.to_add")) +
        '" autocomplete="off" spellcheck="false"><button type="button" class="btn" data-act="add">' + esc(PD.t("nw.add")) + "</button></div>" +
        '<p class="hint" id="nw-listen-msg" role="status" hidden></p>' +
        '<p class="hint">' + esc(PD.t("nw.trust")) + "</p></div></div>" +
        '<div class="row"><div class="label">' + esc(PD.t("nw.reach")) + '</div><div class="control" id="nw-reach"></div></div></section>' +
        '<section class="section" aria-labelledby="nw-h2"><h2 id="nw-h2">' + esc(PD.t("nw.pairing")) + "</h2>" +
        '<div class="row"><div class="label">' + esc(PD.t("nw.token")) + "<small>" + esc(PD.t("nw.token_hint")) + '</small></div><div class="control" id="nw-token"></div></div>' +
        '<p class="hint err" id="nw-token-msg" role="alert" hidden></p></section>';
      PD.on(R, "click", "[data-remove]", (e, el) => saveListen(S.listen.filter(a => a !== el.dataset.remove)));
      PD.on(R, "click", "[data-act]", async (e, el) => {
        const a = el.dataset.act;
        if (a === "port") {
          const n = Number($("#nw-port", R).value);
          const bad = await PD.checkField("server.port", n);
          if (bad) { $("#nw-port", R).setAttribute("aria-invalid", "true"); msg("nw-port-msg", bad, true); return; }
          $("#nw-port", R).removeAttribute("aria-invalid");
          const [s, err] = await PD.safe(PD.saveSettings(st => PD.setK(st, "server.port", n)));
          if (err) msg("nw-port-msg", PD.errText(err), true);
          else { S.port = PD.getK(s, "server.port") || n; msg("nw-port-msg", PD.t("nw.saved_restart", { time: PD.clock(new Date()) })); paintAddresses(); }
        } else if (a === "add") {
          const inp = $("#nw-add", R), v = inp.value.trim();
          if (!isAddress(v)) { inp.setAttribute("aria-invalid", "true"); msg("nw-listen-msg", PD.t("nw.bad_address"), true); return; }
          inp.removeAttribute("aria-invalid");
          if (S.listen.includes(v)) { msg("nw-listen-msg", PD.t("nw.listed", { address: v }), true); return; }
          if (await saveListen(S.listen.concat([v]))) inp.value = "";
        } else if (a === "copy-url") { const ok = await PD.copy($("#nw-url", R).value); el.textContent = PD.t(ok ? "common.copied" : "common.copy_failed"); setTimeout(() => { el.textContent = PD.t("common.copy"); }, 1500); }
        else if (a === "toggle") { if (!S.shown && !(await token())) return; S.shown = !S.shown; paintToken(); }
        else if (a === "copy-token") { const t = await token(); if (!t) return; const ok = await PD.copy(t); el.textContent = PD.t(ok ? "common.copied" : "common.copy_failed"); setTimeout(() => { el.textContent = PD.t("common.copy"); }, 1500); }
        else if (a === "rotate") rotate();
      });
      $("#nw-add", R).addEventListener("keydown", e => { if (e.key === "Enter") $('[data-act="add"]', R).click(); });
    },
    async show() {
      paintToken(); paintAddresses();
      const [s, e] = await PD.safe(PD.loadSettings());
      if (!s) { msg("nw-listen-msg", PD.errText(e), true); return; }
      S.listen = PD.getK(s, "server.listen") || ["127.0.0.1"]; S.port = PD.getK(s, "server.port") || 8770;
      $("#nw-port", R).value = S.port;
      paintAddresses(); PD.paintRail();
    },
  });
})();
