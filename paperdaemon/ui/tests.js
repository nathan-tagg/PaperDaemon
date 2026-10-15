"use strict";
/* Test: run the whole pipeline with a lineup's models and read what it can do, as one table: the models (do they
   answer), the pages (answer, handwriting, charts, drawing, pictures) and the network. The engine keeps one result
   per lineup, and only while the lineup is unchanged. */
(() => {
  const { $, esc, line, mk } = PD;
  let R = null;
  const S = { choose: "", result: null, changed: false, plan: [], run: null, err: "", runErr: "", starting: false, looping: false };

  // a row's state -> its mark and word
  const STATE = { pass: ["ok", "ts.passed"], partly: ["half", "ts.partly"], fail: ["fail", "ts.failed"],
                  busy: ["busy", "ts.running"], wait: ["off", "ts.waiting"], off: ["off", ""] };

  /** The run in progress, when it is this lineup's. */
  const live = () => (S.run && S.run.running && S.run.lineup === S.choose ? S.run : null);

  // what the engine said, in the user's language: a row carries its strings' names and values beside the English
  const told = m => !m ? null : m[0] === "list" ? m[1].map(([k, v]) => PD.t(k, v)).join(" · ") : PD.t(m[0], m[1]);
  const rowName = r => (r.id ? PD.t("ts.row." + r.id) : r.name);

  function rowsHtml(rows) {
    return '<table class="list test-table"><thead><tr><th class="mark-col"><span class="sr">' + esc(PD.t("ts.result")) + "</span></th><th>" +
      esc(PD.t("ts.what")) + "</th><th>" + esc(PD.t("ts.result")) + "</th><th>" + esc(PD.t("ts.details")) + "</th></tr></thead><tbody>" +
      rows.map(r => {
        const [kind, word] = STATE[r.state] || ["off", ""];
        return '<tr class="' + esc(r.state || "") + '"><td class="mark-col">' + mk(kind) + (word ? '<span class="sr">' + esc(PD.t(word)) + "</span>" : "") +
          "</td><td><strong>" + esc(rowName(r)) + '</strong></td><td class="num">' + esc(told(r.m) ?? r.metric ?? "") +
          '</td><td class="sub case-note">' + esc(told(r.d) ?? r.detail ?? "") + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  function headHtml() {
    const run = live();
    if (run) {
      const rows = run.rows || [], done = rows.filter(r => !["wait", "busy"].includes(r.state)).length;
      return '<div class="test-head">' + line("busy", esc(PD.t("ts.testing", { n: done, total: rows.length }))) +
        '<button type="button" class="btn" data-act="cancel">' + esc(PD.t("ts.stop")) + "</button></div>" +
        '<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="' + rows.length + '" aria-valuenow="' + done + '" aria-label="' +
        esc(PD.t("ts.cases_done")) + '"><i style="width: ' + (rows.length ? Math.round(100 * done / rows.length) : 0) + '%"></i></div>';
    }
    const busy = S.starting || !!(S.run && S.run.running);   // another lineup's run is under way
    const btn = '<button type="button" class="btn primary" data-act="run"' + (busy ? " disabled" : "") + ">" + esc(PD.t("ts.run")) + "</button>";
    let said;
    if (S.result) {
      const when = PD.date(S.result.finished);
      said = line(S.result.passed === S.result.total ? "on" : "fail", esc(PD.t("ts.passed_of", { n: PD.n(S.result.passed), total: PD.n(S.result.total) }))) +
        (when ? '<span class="meta num">' + esc(PD.stamp(when)) + "</span>" : "");
    } else said = '<span class="sub">' + esc(PD.t(S.changed ? "ts.changed" : "ts.never")) + "</span>";
    return '<div class="test-head">' + said + btn + "</div>" +
      (S.runErr ? '<p class="notice attn" role="alert"><strong>' + esc(PD.t("ts.not_started")) + "</strong> " + esc(S.runErr) + "</p>" : "");
  }

  function render() {
    if (!R) return;
    const run = live();
    const rows = run ? run.rows || [] : S.result ? S.result.rows || [] : S.plan;
    PD.html($("#ts-note", R), esc(PD.t("ts.whole", { name: S.choose })) + " " + esc(PD.t("ts.intro")));
    PD.html($("#ts-head", R), headHtml());
    PD.html($("#ts-table", R), S.err ? '<p class="notice attn" role="alert"><strong>' + esc(PD.t("ts.unreadable")) + "</strong> " + esc(S.err) + "</p>" : rowsHtml(rows));
  }

  // ---- loading

  async function loadResult() {
    const [d, e] = await PD.safe(PD.api("GET", "/tests?lineup=" + encodeURIComponent(S.choose || "")));
    if (d) { S.result = d.result; S.changed = !!d.changed; S.plan = d.plan || []; S.err = ""; } else S.err = PD.errText(e);
  }

  async function loadStatus() {
    const was = !!live();
    const [d] = await PD.safe(PD.api("GET", "/tests/status"));
    if (d) S.run = d;
    if (was && !live()) await loadResult();        // the finished run is this lineup's result now
  }

  async function watch() {
    if (S.looping) return;
    S.looping = true;
    try {
      while (R && R.isConnected && !R.hidden) {
        await loadStatus(); render();
        if (!(S.run && S.run.running)) break;
        await new Promise(r => setTimeout(r, 1500));
      }
    } finally { S.looping = false; }
  }

  async function run() {
    S.runErr = ""; S.starting = true; render();
    const [, e] = await PD.safe(PD.api("POST", "/tests/run", { lineup: S.choose }));
    S.starting = false;
    if (e) S.runErr = PD.errText(e);
    await loadStatus(); render();
    if (!e) watch();
  }

  PD.screen("tests", {
    label: PD.t("tab.tests"), group: null,          // shown inside the lineup (Lineup > Test), not in the rail
    mount(root) {
      R = root;
      R.innerHTML = '<p class="tab-note" id="ts-note"></p><div id="ts-head" aria-live="polite"></div><div id="ts-table"></div>';
      PD.on(R, "click", "button[data-act]", async (e, el) => {
        if (el.dataset.act === "run") run();
        else if (el.dataset.act === "cancel") { await PD.safe(PD.api("POST", "/tests/cancel")); await loadStatus(); render(); }
      });
    },
    /** Inside the Lineup screen: the lineup it shows. */
    use(name) { if (name !== S.choose) { S.choose = name; S.result = null; S.changed = false; S.plan = []; } },
    async show() {
      render();
      await Promise.all([loadResult(), loadStatus()]);
      render();
      if (S.run && S.run.running) watch();
    },
    async poll() { if (S.run && S.run.running) return; await Promise.all([loadResult(), loadStatus()]); render(); },
  });
})();
