# Design: add-work-elsewhere

## D1. A job of its own on the other page

The work goes to the other page as a job of its own, not as strokes this job writes there. Everything a job does on
its page -- the layout of what is already there, the steps, the commit, the check from the file, the Daemon's note
and the retry box -- then holds on that page with nothing new. This job's step only makes the page (or the notebook)
when it is new, tags it when no tag reaches it, and files it: a ledger entry, status pending, why "asked", with
`asked` = {from: "<notebook>, page N", what: the request}. The ledger dispatches a page with `asked` even while it is
blank (a blank page otherwise waits). The host puts the request in the job's first message, before a retry's note,
and the entry's `asked` is dropped once that job is done.

## D2. Where a new page and a new notebook go

A new page goes right after the asking page, behind any page this job has already added (as a coloring book's pages
do). A new notebook is made in the asking notebook's folder, tagged with the job's tag, and sent to the tablet at once
(the Mirror; in the False Mirror it stays there).

## D3. Reading other notebooks

`notebooks(named)` lists the library's documents not in the trash, the latest changed first, 80 at most, with the
folder path. `read_page(page, notebook)` finds the notebook by its name (exact, case aside; else the one name holding
the words; several are listed back) and reads the page as it reads one of this notebook.
