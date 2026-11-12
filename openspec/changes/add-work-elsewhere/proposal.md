# Proposal: add-work-elsewhere

## Why

A job could only work on the page that woke it. On 11-12, on a resume notebook tagged for the Opus lineup, the user
asked for a new version of page 2 on a new page they had made. The job said it could only write on its own page, and
told the user to write the request on the new page and tag it themselves. Asked whether it could make a page or a
notebook, or read another notebook, it said no to all three. The maintainer: "everything I asked for that it couldnt
do it should be able to."

## What Changes

- New capability `jobs/elsewhere`: a plan step, `elsewhere`, hands its request to another page: a page of this
  notebook, a new page right after this one, or a new notebook made beside this one. The host makes what is new, tags
  a page no tag reaches for the job's lineup, and files the page in the ledger as asked for, with the request word for
  word and the page it came from. The daemon runs it as any job, though the page is blank; the job there is told where
  its request came from.
- Two looks: `notebooks` lists the user's other notebooks, PDFs and books (name, folder, kind, pages), and `read_page`
  takes a `notebook` name to read a page of another one.
- A feature, `elsewhere`, offers the step and the `notebooks` look; on by default, also for a lineup saved before it.
