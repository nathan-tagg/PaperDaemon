"use strict";
/* THE SHORTCUTS SHEET: every key and click the notebook viewer and its page editor answer to, a list per kind, each
   item's bullet the icon of what it does (the editor's own icons where it has one: the pen, the erasers, the text),
   then the keys, then the action and a line on it. Opened from the ? by the document's name, over the viewer. */
(() => {
  const { esc } = PD;
  const svg = body => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + body + "</svg>";
  const COLLAR = '<path d="M6 21v-2.6c0-2 2.7-3.2 6-3.2s6 1.2 6 3.2V21"/>';
  const ICON = {
    scroll: svg('<rect x="7.5" y="3" width="9" height="15" rx="4.5"/><path d="M12 6v3"/><path d="M9.5 20.5 12 22l2.5-1.5"/>'),
    zoom: svg('<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5M8 10.5h5M10.5 8v5"/>'),
    across: svg('<path d="M4 12h16M7 9l-3 3 3 3M17 9l3 3-3 3"/>'),
    auto: svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="1" fill="currentColor"/><path d="M12 4.8 14 7.5h-4zM12 19.2 14 16.5h-4z" fill="currentColor"/>'),
    turn: svg('<path d="M6 3.5h8l4 4v13H6z"/><path d="M9.5 14h5M12.5 11.5 15 14l-2.5 2.5"/>'),
    history: svg('<path d="M9 7 4 12l5 5M15 7l5 5-5 5"/>'),
    close: svg('<path d="M6 6l12 12M18 6 6 18"/>'),
    sync: svg('<path d="M19 8.5a7.5 7.5 0 0 0-13.6 1M5 15.5a7.5 7.5 0 0 0 13.6-1"/><path d="M19 4v4.5h-4.5M5 20v-4.5h4.5"/>'),
    undo: svg('<path d="M9 6.5 4.5 11 9 15.5"/><path d="M4.5 11H14a5 5 0 0 1 0 10h-2.5"/>'),
    fill: svg('<path d="M4.6 10.4 11 4l7.5 7.5-6.4 6.4a1.4 1.4 0 0 1-2 0l-5.5-5.5a1.4 1.4 0 0 1 0-2z"/><path d="M4.5 11.5h13.6"/><path d="M20.5 16.5c0 1.4-.8 2.5-1.7 2.5s-1.7-1.1-1.7-2.5c0-1 1.7-3 1.7-3s1.7 2 1.7 3z"/>'),
    corners: svg('<path d="M4.5 18 9 5.5l10.5 4-5 9z"/><circle cx="4.5" cy="18" r="1.3" fill="currentColor"/><circle cx="9" cy="5.5" r="1.3" fill="currentColor"/><circle cx="19.5" cy="9.5" r="1.3" fill="currentColor"/>'),
    snap: svg('<path d="M4 19h16M4 19 16.5 6.5"/><path d="M12 19a8 8 0 0 0-2.3-5.7"/>'),
    pen: svg(COLLAR + '<path d="M8.5 15.2V10.5h7v4.7"/><path d="M11 10.5V3.5h2v7"/>'),
    circle: svg('<circle cx="12" cy="12" r="8"/>'),
    triangle: svg('<path d="M12 4l8.5 15h-17z"/>'),
    square: svg('<rect x="5" y="5" width="14" height="14"/>'),
    rect: svg('<rect x="3" y="7" width="18" height="10"/>'),
    arrow: svg('<path d="M5 19 19 5M19 5h-7M19 5v7"/>'),
    ePass: svg('<path d="M3 16c3-7 6.5-9.5 9.5-5.5S17.5 13 21 7" stroke-dasharray="1.6 2.6"/><circle cx="12.3" cy="11" r="3.6"/>'),
    eStrokes: svg('<path d="M3 16c3-7 6.5-9.5 9.5-5.5S17.5 13 21 7"/><path d="M13 3.5l5 5M18 3.5l-5 5" stroke-width="1.7"/>'),
    eZone: svg('<path d="M5 9c0-3.5 3.5-5.5 7.5-5.5S20 6 20 10s-3 7.5-8 7.5S5 13.5 5 9z" stroke-dasharray="2 2.4"/><path d="M8 11c2-2.5 3.5-2.5 5 0s3 2.5 4 0"/>'),
    type: svg('<path d="M9 4h2c.6 0 1 .4 1 1v14c0 .6-.4 1-1 1H9M15 4h-2c-.6 0-1 .4-1 1v14c0 .6.4 1 1 1h2"/>'),
    extend: svg('<path d="M5 4.5v15"/><rect x="7" y="8" width="12" height="8" rx="1" fill="currentColor" stroke="none" opacity=".35"/><path d="M19 4.5v15"/>'),
    menu: svg('<rect x="5" y="4" width="14" height="16" rx="1.5"/><path d="M8.5 8.5h7M8.5 12h7M8.5 15.5h5"/>'),
    back: svg('<path d="M8.5 5.5H20v13H8.5L3.5 12z"/><path d="M11 9.5l5 5M16 9.5l-5 5"/>'),
    letgo: svg('<path d="M8.5 4.5h3M8.5 19.5h3M10 4.5v15"/><path d="M15 9.5l4 4M19 9.5l-4 4"/>'),
    styles: svg('<path d="M4 5.5h11" stroke-width="2.6"/><path d="M4 10.5h8" stroke-width="2"/><path d="M4 15h12M4 19h12"/>'),
    bold: svg('<path d="M7 4.5h5.5a3.5 3.5 0 0 1 0 7H7zM7 11.5h6.5a4 4 0 0 1 0 8H7z"/>'),
    move: svg('<path d="M4 8h9M4 12h9M4 16h9"/><path d="M18 5v14M15.5 7.5 18 5l2.5 2.5M15.5 16.5 18 19l2.5-2.5"/>'),
    select: svg('<path d="M6 10c0-3.3 3-5.5 7-5.5s7 2.2 7 5.5-3 5.5-7 5.5c-1.2 0-2.4-.2-3.4-.6" stroke-dasharray="2 2.2"/><path d="M9.6 14.9C8 15.8 7.3 17.4 8 19"/><circle cx="8.2" cy="19.6" r="1.1"/>'),
    capture: svg('<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><circle cx="12" cy="12" r="3.2"/>'),
    delete: svg('<path d="M5 7h14M9.5 7V4.5h5V7M7 7l1 12.5h8L17 7"/><path d="M10.5 10.5v6M13.5 10.5v6"/>'),
    copy: svg('<rect x="8.5" y="8.5" width="11" height="11" rx="1.5"/><path d="M15.5 8.5V6A1.5 1.5 0 0 0 14 4.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>'),
    paste: svg('<rect x="5" y="5" width="14" height="16" rx="1.5"/><path d="M9 5V3.5h6V5M9 11h6M9 15h4"/>'),
    pasteStrokes: svg('<rect x="5" y="5" width="14" height="16" rx="1.5"/><path d="M9 5V3.5h6V5"/><path d="M8.5 15c1.5-3.5 3-4 4-2s2 1.5 3-1.5"/>'),
    cursors: svg('<path d="M5.5 5h4M5.5 19h4M7.5 5v14M14.5 5h4M14.5 19h4M16.5 5v14"/>'),
  };
  // the keys, each combination a list: a word the window says in its own language, or a symbol as printed on a key
  const WORD = { ctrl: "keys.k_ctrl", shift: "keys.k_shift", alt: "keys.k_alt", esc: "keys.k_esc", backspace: "keys.k_backspace",
                 click: "keys.k_click", loop: "keys.k_loop", delete: "keys.k_delete", wheel: "keys.k_wheel", middle: "keys.k_middle", right: "keys.k_right", drag: "keys.k_drag", type: "keys.k_type" };
  const keyOf = k => WORD[k] ? PD.t(WORD[k]) : k;
  const combo = c => '<span class="kc">' + c.map(k => "<kbd>" + esc(keyOf(k)) + "</kbd>").join('<span class="kplus">+</span>') + "</span>";
  // [icon, combinations, action, line]; `editor` sections only where the page editor is open
  const SHEET = [
    { title: "keys.s_move", items: [
      ["scroll", [["wheel"]], "keys.scroll", "keys.scroll_d"],
      ["zoom", [["ctrl", "wheel"]], "keys.zoom", "keys.zoom_d"],
      ["across", [["shift", "wheel"]], "keys.across", "keys.across_d"],
      ["auto", [["middle"]], "keys.auto", "keys.auto_d"]] },
    { title: "keys.s_pages", items: [
      ["turn", [["←", "→"]], "keys.turn", "keys.turn_d", "viewer"],
      ["history", [["alt", "←"], ["alt", "→"]], "keys.history", "keys.history_d"],
      ["close", [["esc"]], "keys.close", "keys.close_d"]] },
    { title: "keys.s_draw", editor: true, items: [
      ["sync", [["ctrl", "S"]], "keys.sync", "keys.sync_d"],
      ["undo", [["ctrl", "Z"], ["ctrl", "Y"]], "keys.undo", "keys.undo_d"],
      ["fill", [["alt", "click"]], "keys.fill", "keys.fill_d"],
      ["corners", [["ctrl", "click"]], "keys.corners", "keys.corners_d"],
      ["snap", [["ctrl", "alt", "click"]], "keys.snap_corners", "keys.snap_corners_d"]] },
    { title: "keys.s_shapes", editor: true, items: [
      ["pen", [["1"]], "keys.pen", "keys.pen_d"],
      ["circle", [["2"]], "keys.circle", "keys.circle_d"],
      ["triangle", [["3"]], "keys.triangle", "keys.triangle_d"],
      ["square", [["4"]], "keys.square", "keys.square_d"],
      ["rect", [["5"]], "keys.rect", "keys.rect_d"],
      ["arrow", [["6"]], "keys.arrow", "keys.arrow_d"],
      ["snap", [["alt", "drag"], ["alt", "click"]], "keys.snap", "keys.snap_d"]] },
    { title: "keys.s_erase", editor: true, items: [
      ["ePass", [["shift", "drag"]], "keys.e_pass", "keys.e_pass_d"],
      ["eStrokes", [["ctrl", "shift", "drag"]], "keys.e_strokes", "keys.e_strokes_d"],
      ["eZone", [["ctrl", "shift", "alt", "drag"]], "keys.e_zone", "keys.e_zone_d"]] },
    { title: "keys.s_pick", editor: true, items: [
      ["select", [["loop"]], "keys.select", "keys.select_d"],
      ["capture", [["loop"], ["click"]], "keys.capture", "keys.capture_d"],
      ["delete", [["delete"], ["backspace"]], "keys.delete", "keys.delete_d"],
      ["copy", [["ctrl", "C"], ["ctrl", "X"]], "keys.copy", "keys.copy_d"],
      ["paste", [["ctrl", "V"]], "keys.paste", "keys.paste_d"],
      ["pasteStrokes", [["ctrl", "shift", "V"]], "keys.paste_strokes", "keys.paste_strokes_d"]] },
    { title: "keys.s_type", editor: true, items: [
      ["type", [["type"]], "keys.type", "keys.type_d"],
      ["back", [["backspace"]], "keys.back", "keys.back_d"],
      ["letgo", [["esc"]], "keys.letgo", "keys.letgo_d"],
      ["styles", [["ctrl", "1–4"]], "keys.styles", "keys.styles_d"],
      ["bold", [["ctrl", "B"], ["ctrl", "I"]], "keys.bold", "keys.bold_d"],
      ["move", [["alt", "↑"], ["alt", "↓"]], "keys.move", "keys.move_d"],
      ["cursors", [["ctrl", "alt", "↑"], ["ctrl", "alt", "↓"], ["ctrl", "alt", "click"]], "keys.cursors", "keys.cursors_d"],
      ["extend", [["shift", "click"]], "keys.extend", "keys.extend_d"],
      ["menu", [["right"]], "keys.menu", "keys.menu_d"]] },
  ];

  // over the viewer (a dialog over a dialog: the top one takes the keys, and Esc closes only it)
  PD.openShortcuts = withEditor => {
    let dlg = document.getElementById("keys-sheet");
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "keys-sheet"; dlg.className = "keys-sheet";
      dlg.addEventListener("click", e => { if (e.target === dlg || e.target.closest("[data-keys-close]")) dlg.close(); });
      document.body.append(dlg);
    }
    const body = SHEET.filter(s => withEditor || !s.editor).map(s =>
      '<section><h3>' + esc(PD.t(s.title)) + '</h3><ul class="keys">' +
      s.items.filter(it => !(withEditor && it[4] === "viewer")).map(([icon, combos, name, line]) =>
        '<li><span class="ki">' + ICON[icon] + '</span><span class="kk">' + combos.map(combo).join('<span class="kor">/</span>') + "</span>" +
        '<span class="kn"><strong>' + esc(PD.t(name)) + "</strong> " + esc(PD.t(line)) + "</span></li>").join("") + "</ul></section>").join("");
    dlg.setAttribute("aria-label", PD.t("keys.title"));
    dlg.innerHTML = '<div class="keys-head"><span class="keys-title">' + esc(PD.t("keys.title")) + '</span><button type="button" class="link-btn" data-keys-close>' +
      esc(PD.t("common.close")) + '</button></div><div class="keys-body">' + body + "</div>";
    // EXACTLY THE VIEWER'S SIZE: both are centered, so the sheet lies right over it
    fit(dlg);
    dlg.showModal();
  };
  function fit(dlg) {
    const viewer = document.querySelector("dialog.viewer[open]");
    if (viewer) { dlg.style.width = viewer.offsetWidth + "px"; dlg.style.height = viewer.offsetHeight + "px"; }
    else { dlg.style.width = ""; dlg.style.height = ""; }
  }
  // and kept so as the window or the zoom changes the viewer (after it has taken its new size)
  const refit = () => requestAnimationFrame(() => { const d = document.querySelector("#keys-sheet[open]"); if (d) fit(d); });
  window.addEventListener("resize", refit);
  window.addEventListener("pd-zoom", refit);
})();
