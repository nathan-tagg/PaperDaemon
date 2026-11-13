# Spec Delta

## ADDED Requirements

### Requirement: A job hands work to another page
A plan SHALL be able to hand a request to another page with an `elsewhere` step: `page` (a page number of this
notebook, or "new") or `notebook` (the name of a new notebook), and `what` (the request for that page). The model SHALL
say where what is new goes: a new page `after` a page number or at the "end" (right after the asking page when it
says nothing), a new notebook in `folder`, a folder's name or path, "/" for the top of the library (the asking
notebook's folder when it says nothing); a folder that does not exist SHALL be made. The host SHALL make what is new,
tag a page no tag reaches with the job's tag, and file it in the ledger as asked for, with the request word for word
and the page it came from. A step naming the asking page, or a page the notebook does not have, SHALL fail with the
reason.

#### Scenario: A new version of a page on a new page
- **WHEN** the user asks on page 3 for a new version of page 2 on a new page
- **THEN** the job adds page 4 after page 3, tags it for the lineup, and files it with the request; a job runs on
  page 4 with that request, reads page 2 and writes the new version there

#### Scenario: A new notebook
- **WHEN** the user asks for the work in a new notebook named "Resume v2" in a folder "Work/Resumes"
- **THEN** the notebook is made in that folder (the folders made when missing), tagged for the lineup and sent to
  the tablet, and a job runs on its first page with the request

### Requirement: A page handed work is a job though it is blank
The ledger SHALL dispatch a page filed as asked for even while nothing is on it. The job on it SHALL be told where its
request came from and the request, word for word, and the request SHALL be carried out once.

#### Scenario: A blank new page
- **WHEN** a page added for a request has nothing on it
- **THEN** it is dispatched, not left waiting

### Requirement: The user's other notebooks can be read
A job SHALL be able to list the user's notebooks, PDFs and books (name, folder, kind, page count) and read a page of
any of them by the notebook's name. A name that matches nothing, or several, SHALL be answered with what matched.

#### Scenario: A page of another notebook
- **WHEN** the request asks about page 1 of the Garden notebook
- **THEN** read_page(page 1, notebook "Garden") gives that page's typed text and handwriting
