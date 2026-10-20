"use strict";
/* Help for the start script boxes: what a start script is, when PaperDaemon runs it and stops it, the mistakes that
   bite, and a ready-made prompt to paste into any AI chat to get help writing one. */
(() => {
  const { esc } = PD;

  /** Help text is plain words with two marks a translation keeps: `code` and **bold**. */
  const rich = name => esc(PD.t(name)).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  const list = (tag, names) => "<" + tag + ">" + names.map(n => "<li>" + rich(n) + "</li>").join("") + "</" + tag + ">";
  const h3 = name => "<h3>" + esc(PD.t(name)) + "</h3>";
  const p = name => "<p>" + rich(name) + "</p>";

  const MODEL = {
    title: "help.model.title",
    body: () => [
      p("help.model.intro"),
      h3("help.h_do"), list("ol", ["help.model.do1", "help.model.do2", "help.do_output"]),
      h3("help.h_runs"), list("ul", ["help.model.runs1", "help.model.runs2", "help.model.runs3"]),
      h3("help.h_stops"), p("help.model.stops"),
      h3("help.h_wrong"), list("ul", ["help.model.wrong_vram", "help.model.wrong_own_vram", "help.model.wrong_two", "help.model.wrong_port", "help.wrong_spaces", "help.model.wrong_keys"]),
      h3("help.h_try"), p("help.model.try"),
    ],
    prompt: kind => PD.t(kind === "image" ? "help.model.prompt_image" : "help.model.prompt_text"),
  };

  const SEARCH = {
    title: "help.search.title",
    body: () => [
      p("help.search.intro"),
      h3("help.h_do"), list("ol", ["help.search.do1", "help.search.do2", "help.do_output"]),
      h3("help.h_runs"), p("help.search.runs"),
      h3("help.h_stops"), p("help.search.stops"),
      h3("help.h_wrong"), list("ul", ["help.search.wrong_json", "help.search.wrong_docker", "help.search.wrong_port", "help.wrong_spaces"]),
      h3("help.h_try"), p("help.search.try"),
    ],
    prompt: () => PD.t("help.search.prompt"),
  };

  /** The Help link, right-aligned above a start script box. kind: "text" | "image" | "search". */
  PD.scriptHelpLink = kind => '<button type="button" class="link-btn script-help" data-script-help="' + esc(kind) + '">' + esc(PD.t("common.help")) + "</button>";

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall back below */ }
    const t = document.createElement("textarea");
    t.value = text; t.style.position = "fixed"; t.style.opacity = "0";
    document.body.append(t); t.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    t.remove();
    return ok;
  }

  /** A small note where the pointer is, that fades away. */
  PD.toastAt = (x, y, text) => {
    const el = document.createElement("div");
    el.className = "cursor-toast"; el.setAttribute("role", "status"); el.textContent = text;
    el.style.left = Math.min(x + 12, window.innerWidth - 220) + "px";
    el.style.top = Math.max(8, y - 36) + "px";
    // inside an open modal when there is one: a modal is drawn above everything else on the page
    const dlgs = document.querySelectorAll("dialog[open]");
    (dlgs.length ? dlgs[dlgs.length - 1] : document.body).append(el);
    setTimeout(() => el.classList.add("gone"), 1400);
    setTimeout(() => el.remove(), 1900);
  };

  function open(kind) {
    const h = kind === "search" ? SEARCH : MODEL;
    const dlg = PD.sheet(PD.t(h.title), '<div class="script-help-body">' + h.body().join("") + "</div>" +
      '<div class="actions"><button type="button" class="link-btn" data-v="ask">' + esc(PD.t("help.ask")) + "</button>" +
      '<button type="button" class="btn primary" data-v="close" autofocus>' + esc(PD.t("common.close")) + "</button></div>");
    dlg.classList.add("wide");
    dlg.addEventListener("click", async e => {
      const b = e.target.closest("button[data-v]"); if (!b) return;
      if (b.dataset.v === "close") { dlg.close(); return; }
      const ok = await copy(h.prompt(kind));
      PD.toastAt(e.clientX, e.clientY, PD.t(ok ? "help.copied" : "help.copy_failed"));
    });
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
  }

  document.addEventListener("click", e => {
    const b = e.target.closest && e.target.closest("[data-script-help]");
    if (b) { e.preventDefault(); open(b.dataset.scriptHelp); }
  });
})();
