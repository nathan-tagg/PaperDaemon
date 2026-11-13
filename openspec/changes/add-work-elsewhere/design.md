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

The model says. A new page goes `after` a page number, or at the "end"; said nothing, right after the asking page,
behind any page this job has already added. A new notebook goes in `folder`: a name met once in the library, or a path
of names from the top ("Work/Resumes"), each part that does not exist made and sent to the tablet; "/" is the top;
said nothing, the asking notebook's folder. A name several folders share is answered with that, so the model gives
the path. (The first version, 0.2.77, fixed both places; the maintainer: "Why would you place those limitations ...
its not me who would be asking, its the LLM".)

## D3. Reading other notebooks

`notebooks(named)` lists the library's documents not in the trash, the latest changed first, 80 at most, with the
folder path. `read_page(page, notebook)` finds the notebook by its name (exact, case aside; else the one name holding
the words; several are listed back) and reads the page as it reads one of this notebook.
