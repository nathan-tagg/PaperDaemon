// Behavior for the mockups only; the real app replaces this file. One state model drives both the live
// pages and the tablet book (book.js), so every control means the same thing in both:
//   state                        key=value pairs. Defaults come from the controls below and from
//                                [data-state="k=v&k=v"] on the page's root element
//   .seg[data-name]              a choice among its buttons' data-value
//   .switch[data-name]           on or off
//   select[data-name]            its options' values
//   [data-set="k=v&k=v"]         a click sets these; while they hold, the element is aria-current
//   [data-flip="k"]              a click turns k on or off
//   [data-open="id"]             opens a dialog; in it, [data-close] closes it and [data-then] sets state
//   [data-when="k=v&k!=w&k=a|b"] shown only while the condition holds
//   [data-class="cls:cond;..."]  a class while its condition holds
//   [data-current="cond"]        aria-current while the condition holds
//   [data-copy="id"]             also copies that field's value to the clipboard
//   .code textarea               keeps its line-number gutter in step
(() => {
  const M = {};
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  M.pairs = (s) => (s || "").split("&").filter(Boolean).map((p) => {
    const i = p.indexOf("=");
    return [p.slice(0, i), p.slice(i + 1)];
  });

  M.holds = (cond, st) => (cond || "").split("&").filter(Boolean).every((c) => {
    const ne = c.includes("!=");
    const [k, v] = ne ? c.split("!=") : [c.slice(0, c.indexOf("=")), c.slice(c.indexOf("=") + 1)];
    const hit = v.split("|").includes(st[k] ?? "");
    return ne ? !hit : hit;
  });

  M.defaults = (root) => {
    const st = {};
    $$(".seg[data-name]", root).forEach((g) => {
      const on = g.querySelector('button[aria-pressed="true"]') || g.querySelector("button[data-value]");
      st[g.dataset.name] = on ? on.dataset.value : "";
    });
    $$("input.switch[data-name]", root).forEach((c) => { st[c.dataset.name] = c.checked ? "on" : "off"; });
    $$("select[data-name]", root).forEach((s) => {
      const o = [...s.options].find((x) => x.selected) || s.options[0];
      st[s.dataset.name] = o ? o.value : "";
    });
    const decl = root.matches?.("[data-state]") ? root : root.querySelector("[data-state]");
    if (decl) M.pairs(decl.dataset.state).forEach(([k, v]) => { if (!(k in st)) st[k] = v; });
    return st;
  };

  M.apply = (root, st) => {
    $$(".seg[data-name]", root).forEach((g) => {
      $$("button[data-value]", g).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.value === st[g.dataset.name])));
    });
    $$("input.switch[data-name]", root).forEach((c) => {
      c.checked = st[c.dataset.name] === "on";
      c.toggleAttribute("checked", c.checked);          // the attribute too, so a clone keeps it
    });
    $$("select[data-name]", root).forEach((s) => {
      [...s.options].forEach((o) => { o.selected = o.value === st[s.dataset.name]; o.toggleAttribute("selected", o.selected); });
    });
    $$("[data-set]", root).forEach((el) => {
      if (el.hasAttribute("data-current")) return;
      const on = M.pairs(el.dataset.set).every(([k, v]) => st[k] === v);
      if (on) el.setAttribute("aria-current", "true"); else el.removeAttribute("aria-current");
    });
    $$("[data-current]", root).forEach((el) => {
      if (M.holds(el.dataset.current, st)) el.setAttribute("aria-current", "true"); else el.removeAttribute("aria-current");
    });
    $$("[data-when]", root).forEach((el) => { el.hidden = !M.holds(el.dataset.when, st); });
    $$("[data-class]", root).forEach((el) => {
      el.dataset.class.split(";").filter(Boolean).forEach((rule) => {
        const i = rule.indexOf(":");
        el.classList.toggle(rule.slice(0, i), M.holds(rule.slice(i + 1), st));
      });
    });
  };

  // What a click on `el` does, as {state, open, close}. `open` names a dialog to open; `close` closes
  // the open one. A navigation link returns {go: "file.html"}. Null when the element does nothing.
  M.act = (el, st) => {
    const next = { ...st };
    const segb = el.closest(".seg[data-name] button[data-value]");
    if (segb) { next[segb.closest(".seg").dataset.name] = segb.dataset.value; return { state: next }; }
    const sw = el.matches("input.switch[data-name]") ? el : el.closest("label")?.querySelector("input.switch[data-name]");
    if (sw && !sw.disabled) { next[sw.dataset.name] = st[sw.dataset.name] === "on" ? "off" : "on"; return { state: next }; }
    const t = el.closest("[data-set],[data-flip],[data-open],[data-close],[data-then]");
    if (t) {
      M.pairs(t.dataset.set).forEach(([k, v]) => { next[k] = v; });
      if (t.dataset.flip) next[t.dataset.flip] = st[t.dataset.flip] === "on" ? "off" : "on";
      M.pairs(t.dataset.then).forEach(([k, v]) => { next[k] = v; });
      return { state: next, open: t.dataset.open || null, close: t.hasAttribute("data-close") };
    }
    const a = el.closest("a[href]");
    if (a && /\.html(#.*)?$/.test(a.getAttribute("href"))) return { go: a.getAttribute("href") };
    return null;
  };

  window.Mockup = M;
  if (window.MOCKUP_BOOK) return;

  // ---- the live pages
  const page = document.body;
  let st = M.defaults(page);
  const q = new URLSearchParams(location.search).get("state");
  if (q) M.pairs(q).forEach(([k, v]) => { st[k] = v; });
  M.apply(page, st);

  document.addEventListener("click", (e) => {
    const el = e.target.closest("button, a, label, li, tr, figure, .drop, [data-set], [data-flip], [data-open]");
    if (!el || el.closest("select")) return;
    const r = M.act(e.target, st);
    if (!r || r.go) return;                              // links navigate as links do
    if (e.target.closest("label")) e.preventDefault();   // the state decides the switch, not the browser
    if (r.close) e.target.closest("dialog")?.close();
    st = r.state;
    M.apply(page, st);
    if (r.open) document.getElementById(r.open)?.showModal();
    const copy = e.target.closest("[data-copy]");
    if (copy) {
      const f = document.getElementById(copy.dataset.copy);
      if (f) navigator.clipboard?.writeText(f.value || f.textContent).catch(() => {});
    }
  });
  document.addEventListener("change", (e) => {
    const s = e.target.closest("select[data-name]");
    if (!s) return;
    st = { ...st, [s.dataset.name]: s.value };
    M.apply(page, st);
  });

  // line numbers for script editors
  $$(".code").forEach((c) => {
    const t = c.querySelector("textarea"), g = c.querySelector(".gutter");
    if (!t || !g) return;
    const n = () => { g.textContent = t.value.split("\n").map((_, i) => i + 1).join("\n"); };
    t.addEventListener("input", n); t.addEventListener("scroll", () => (g.scrollTop = t.scrollTop)); n();
  });
})();
