"use strict";
/* Jobs: every page a lineup has answered or passed over, newest first, by day: when, which page, how it went,
   what happened, and how long it took. Shown inside the lineup (Lineup > Jobs), for the lineup on screen. */
(() => {
  const { $, esc, line } = PD;
  let R = null;
  const S = { jobs: null, err: "", tag: "", lineup: "" };


  const JOB = [
    [/fail|error|abort|cancel/i, "fail", "job.failed"],
    [/work|run|busy|progress|active|start/i, "busy", "job.working"],
    [/skip/i, "skip", "job.skipped"],
    [/queue|wait|pend/i, "off", "job.waiting"],
    [/done|ok|answer|complete|commit|success|pass|finish/i, "on", "job.done"],
  ];
  // the ledger has four states (pending, working, done, skipped); a job the engine recorded as failed (it did not do
  // what was asked) is shown as one, whatever its state, so it is not lost among the finished jobs
  const jobKind = (status, failed) => {
    if (failed) return { kind: "fail", word: PD.t("job.failed") };
    for (const [re, kind, word] of JOB) if (re.test(String(status || ""))) return { kind, word: PD.t(word) };
    return { kind: "off", word: status ? String(status) : PD.t("job.unknown") };
  };
  PD.jobKind = jobKind;

  const pageText = (nb, pg) => {
    const p = pg == null || pg === "" ? "" : /^\d+$/.test(String(pg)) ? PD.t("job.page", { n: pg }) : String(pg);
    return p ? esc(nb) + " › " + esc(p) : esc(nb);
  };

  function render() {
    if (!R) return;
    const meta = $("#jb-meta", R), box = $("#jb-list", R);
    if (S.err) { meta.textContent = ""; PD.html(box, '<p class="notice attn" role="alert"><strong>' + esc(PD.t("jobs.unreadable")) + "</strong> " + esc(S.err) + "</p>"); return; }
    if (!S.jobs) { meta.textContent = ""; PD.html(box, '<p class="sub">' + esc(PD.t("jobs.reading")) + "</p>"); return; }
    const jobs = S.jobs.slice().sort((a, b) => (PD.date(b.started || b.finished) || 0) - (PD.date(a.started || a.finished) || 0));
    if (!jobs.length) {
      meta.textContent = "";
      PD.html(box, PD.empty("tag", "<strong>" + esc(PD.t("jobs.none")) + "</strong>" +
        (S.tag ? " " + PD.tHtml("jobs.none_hint", { tag: '<span class="tag">' + esc(S.tag) + "</span>" }) : "")));
      return;
    }
    const failed = jobs.filter(j => jobKind(j.status, j.failed).kind === "fail").length, skipped = jobs.filter(j => jobKind(j.status, j.failed).kind === "skip").length;
    meta.textContent = PD.count("count.job", jobs.length) + (failed ? " · " + PD.t("jobs.n_failed", { n: PD.n(failed) }) : "") +
      (skipped ? " · " + PD.t("jobs.n_skipped", { n: PD.n(skipped) }) : "");
    let day = "", rows = "";
    const now = Date.now();
    for (const j of jobs) {
      const t0 = PD.date(j.started), t1 = PD.date(j.finished), k = jobKind(j.status, j.failed), when = t0 || t1;
      const label = when ? PD.dayLabel(when) : PD.t("jobs.earlier");
      if (label !== day) { rows += '<tr class="dayrow"><td colspan="5">' + esc(label) + "</td></tr>"; day = label; }
      let took = "";
      if (t0 && t1) took = PD.dur((t1 - t0) / 1000);
      else if (t0 && k.kind === "busy") took = PD.t("jobs.so_far", { time: PD.dur((now - t0) / 1000) });
      rows += '<tr class="' + (k.kind === "fail" ? "attn" : "") + '"><td class="nowrap">' + (when ? "<time>" + esc(PD.clock(when)) + "</time>" : "") + "</td>" +
        "<td><strong>" + pageText(j.notebook || j.key || PD.t("jobs.a_page"), j.page) + "</strong></td>" +
        '<td class="nowrap">' + line(k.kind, esc(k.word)) + "</td>" +
        '<td class="note">' + (j.note ? esc(j.note) : ('<span class="dim">' + esc(PD.t("jobs.no_note")) + "</span>")) + "</td>" +
        '<td class="r nowrap">' + esc(took) + "</td></tr>";
    }
    const th = k => esc(PD.t(k));
    PD.html(box, '<table class="list jobs"><thead><tr><th>' + th("jobs.col.time") + "</th><th>" + th("jobs.col.page") + "</th><th>" +
      th("jobs.col.status") + "</th><th>" + th("jobs.col.what") + '</th><th class="r">' + th("jobs.col.took") + "</th></tr></thead><tbody>" +
      rows + "</tbody></table>");
  }

  async function load() {
    if (!S.lineup) return;
    const want = S.lineup;
    const [jobs, e] = await PD.safe(PD.api("GET", "/jobs?limit=200&lineup=" + encodeURIComponent(want)));
    if (want !== S.lineup) return;                     // another lineup was picked while this was read
    if (jobs) S.jobs = Array.isArray(jobs) ? jobs : jobs.jobs || [];
    S.err = e && !jobs ? PD.errText(e) : "";
    render();
  }

  PD.screen("jobs", {
    label: PD.t("jobs.label"), group: null,                      // shown inside the lineup (Lineup > Jobs), not in the rail
    mount(root) {
      R = root;
      R.innerHTML = '<p class="meta" id="jb-meta"></p><div id="jb-list"></div>';
    },
    // the lineup on screen, and its first tag (for the empty list's hint)
    use(name, tag) {
      if (name !== S.lineup) { S.lineup = name; S.jobs = null; S.err = ""; }
      S.tag = tag || "";
    },
    show() { render(); load(); },
    async poll() { await load(); },
  });
})();
