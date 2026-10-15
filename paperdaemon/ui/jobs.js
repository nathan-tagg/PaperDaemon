"use strict";
/* Jobs: every page a lineup has answered or passed over, newest first: how it went (an icon) and when, which page,
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

  // HOW A JOB WENT, as a small line icon at the left of its time (drawn like the app's other icons; a dot said
  // nothing): done a check, failed a cross, skipped an arrow going past, waiting a clock, working the spinner
  const ICON = {
    on: '<path d="M3.5 8.5l3 3 6-7"/>',
    fail: '<path d="M4.5 4.5l7 7M11.5 4.5l-7 7"/>',
    skip: '<path d="M2.5 8h9M8.5 4.5 12 8l-3.5 3.5"/>',
    off: '<circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5"/>',
  };
  const icon = k => k.kind === "busy"
    ? '<i class="mk spin ji" role="img" aria-label="' + esc(k.word) + '" title="' + esc(k.word) + '"></i>'
    : '<svg class="ji ji-' + k.kind + '" viewBox="0 0 16 16" role="img" aria-label="' + esc(k.word) + '"><title>' + esc(k.word) +
      "</title>" + (ICON[k.kind] || ICON.off) + "</svg>";

  function render() {
    if (!R) return;
    const box = $("#jb-list", R);
    if (S.err) { PD.html(box, '<p class="notice attn" role="alert"><strong>' + esc(PD.t("jobs.unreadable")) + "</strong> " + esc(S.err) + "</p>"); return; }
    if (!S.jobs) { PD.html(box, '<p class="sub">' + esc(PD.t("jobs.reading")) + "</p>"); return; }
    const jobs = S.jobs.slice().sort((a, b) => (PD.date(b.started || b.finished) || 0) - (PD.date(a.started || a.finished) || 0));
    if (!jobs.length) {
      PD.html(box, PD.empty("tag", "<strong>" + esc(PD.t("jobs.none")) + "</strong>" +
        (S.tag ? " " + PD.tHtml("jobs.none_hint", { tag: '<span class="tag">' + esc(S.tag) + "</span>" }) : "")));
      return;
    }
    // NO SUMMARY, NO HEADINGS, NO "TODAY": a row is its icon, time, page, what happened and how long. An earlier day
    // still gets its date above its jobs, so a time is never read as today's.
    const today = PD.dayLabel(new Date());
    let day = today, rows = "";
    const now = Date.now();
    for (const j of jobs) {
      const t0 = PD.date(j.started), t1 = PD.date(j.finished), k = jobKind(j.status, j.failed), when = t0 || t1;
      const label = when ? PD.dayLabel(when) : PD.t("jobs.earlier");
      if (label !== day) { rows += '<tr class="dayrow"><td colspan="4">' + esc(label) + "</td></tr>"; day = label; }
      let took = "";
      if (t0 && t1) took = PD.dur((t1 - t0) / 1000);
      else if (t0 && k.kind === "busy") took = PD.t("jobs.so_far", { time: PD.dur((now - t0) / 1000) });
      rows += '<tr class="' + (k.kind === "fail" ? "attn" : "") + '"><td class="jt">' + icon(k) +
        (when ? "<time>" + esc(PD.clock(when)) + "</time>" : "") + "</td>" +
        '<td class="jp"><strong>' + pageText(j.notebook || j.key || PD.t("jobs.a_page"), j.page) + "</strong></td>" +
        '<td class="note">' + (j.note ? esc(j.note) : ('<span class="dim">' + esc(PD.t("jobs.no_note")) + "</span>")) + "</td>" +
        '<td class="r jd">' + esc(took) + "</td></tr>";
    }
    // FIXED COLUMNS: set by the table, not by what is in them, so nothing moves as a job runs or a note fills in
    PD.html(box, '<table class="list jobs"><colgroup><col class="c-time"><col class="c-page"><col><col class="c-took">' +
      "</colgroup><tbody>" + rows + "</tbody></table>");
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
      R.innerHTML = '<div id="jb-list"></div>';
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
