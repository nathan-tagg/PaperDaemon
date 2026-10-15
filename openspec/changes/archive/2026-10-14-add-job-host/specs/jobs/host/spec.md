# Spec Delta

## Purpose

Runs each dispatched job: reads the page, runs the job by the text harness's protocols, carries out
the host's part of each task, and commits what the harness's validate() passes.

## ADDED Requirements

### Requirement: The host reads the page and runs the job by the harness's protocols
For each job the host SHALL read the page (its typed text, the handwriting reader's lines, its pictures
and marks, and an image of it), and gather the notebook's system prompt, its notepad, the date and the
user's location. It SHALL hand these readings to the text slot's harness and run the job by that
harness's protocols:
- the intake protocol builds what the model is shown and told
- the output protocol turns each reply into what the host acts on
- each task's protocol says what the host does for that task

The host SHALL carry out its part of every task as the protocols say.

#### Scenario: A question on a page
- **WHEN** a page asks "what is the tallest mountain in Colorado" and the text slot uses the Qwen 3.6 27B
  harness
- **THEN** the model asks for an answer to be written, and the host writes it on the page

#### Scenario: Another turn after a lookup
- **WHEN** a page asks who won last night's game and the search task's protocol returns results to the
  model
- **THEN** the host runs the search, the model writes the answer from the results in a second turn,
  and the host lays the answer out on the page

### Requirement: The task vocabulary belongs to the host
The host SHALL define the tasks a job can use:
- writing words
- a chart
- a picture
- a coloring page
- a mark-up
- an erasure
- a search or a fetch
- a tag
- a notepad line

A harness's task protocols SHALL say which of these its model is offered and who does which part of
each. The host's part of a task SHALL work the same way whichever harness asks for it.

#### Scenario: The same chart for two harnesses
- **WHEN** two harnesses both leave drawing a chart to the host, and their models ask for a bar chart of
  the same data
- **THEN** the host draws the same chart both times

### Requirement: A harness may hand back a finished page
When a harness's output protocol hands back a finished working copy of the page and a list of what it
erased, the host SHALL check it with the harness's validate() and commit what passes, as for any other
job. A harness SHALL never write to the mirror or the cloud directly.

#### Scenario: A model that does everything
- **WHEN** a harness's model reads the page, makes a picture itself, writes it onto the working copy and
  reports the job done
- **THEN** the host runs the harness's validate(), commits the page, and it syncs as for any other job

### Requirement: Nothing validate() refuses is committed
Before committing any job, the host SHALL run the text harness's validate() on the result, commit only
what passes, and record what was refused and why. A planned place refused for having no content SHALL
go back to the model once, so it can fill it.

#### Scenario: A picture that never came
- **WHEN** a planned picture fails to generate on the base harness
- **THEN** the job records the failed step, and nothing that depended on it is committed

#### Scenario: A result that goes too far
- **WHEN** a harness that uses the base validate() hands back a page with a paragraph of the user's
  notes removed that it did not report as the request
- **THEN** the result is refused, the page stays as it was, and the job records why

### Requirement: The host decides where things go when the protocol leaves it placement
When a task's protocol leaves placement to the host, the model SHALL say what goes on the page and
roughly how big, and the host SHALL decide where. Planned places SHALL NOT overlap each other or
anything already on the page. A plan that does not fit SHALL be refused with the numbers, so the model
can plan again.

#### Scenario: A chart below typed notes
- **WHEN** the model plans a large chart on a page with typed notes at the top
- **THEN** the host places the chart below the notes, clear of them

#### Scenario: A plan that does not fit
- **WHEN** the model plans three large pictures on a nearly full page
- **THEN** the host refuses the plan, says how much room is left, and the model plans again

### Requirement: Everything stays inside the safe area, below the toolbar
Every kind of content the host or a game puts on a page -- words, charts, calendars, pictures, coloring
pages, game pages, the pages of documents it makes -- SHALL stay inside the page's safe area, whose top
clears the tablet's toolbar docked across the top of the screen and whose sides and foot keep a small
margin. The safe area SHALL be defined once, and every placement SHALL take its top from that
definition rather than a number of its own.

#### Scenario: A picture on an empty page
- **WHEN** a job puts a full-size picture on a page whose request was erased
- **THEN** the picture's top is at the safe area's top, below the toolbar, not at the page's top

#### Scenario: A chess page
- **WHEN** a chess game starts on a new page
- **THEN** the opponent's portrait and talk start at the safe area's top

### Requirement: Tasks follow capabilities
Whatever a harness's task protocols say, the host SHALL offer only the tasks the configured slots can
serve: no picture or coloring tasks without an image slot. When the text slot's vision is off, the host
SHALL give the harness's intake no image of the page, so the model gets the page as text: the typed
text exactly, and the handwriting reader's lines with their positions.

#### Scenario: No image slot
- **WHEN** the image slot is empty and a page asks for a picture of a fox
- **THEN** the model is offered no picture task, and the job says pictures are not available

#### Scenario: A model without vision
- **WHEN** the text slot's vision is off
- **THEN** the model receives the page as typed text and positioned handwriting lines, never as an image

### Requirement: Skipping is allowed, inventing work is not
When a page asks for nothing, including a retagged page with nothing new on it, the model SHALL be able
to skip it with a reason, and the host SHALL record the skip and change nothing on the page.

#### Scenario: Notes, not a request
- **WHEN** a tagged page holds only the user's meeting notes
- **THEN** the job is skipped with a reason, and the page is unchanged

### Requirement: Runaway output is stopped by tokens and repetition
The host SHALL stop a model turn that exceeds its token limit or repeats itself, and tell the model. The
host SHALL NOT stop a model turn because of how long it has taken.

#### Scenario: A slow model
- **WHEN** a local model takes several minutes on one turn without repeating itself
- **THEN** the host waits for it

#### Scenario: A reply that loops
- **WHEN** the model's reply starts repeating the same passage
- **THEN** the host stops the turn and tells the model it repeated itself

### Requirement: New documents go only beside the inbox notebook
No task of the host's SHALL create a notebook. A job that makes a new document, such as a calendar as a
PDF, SHALL put it in the folder that holds the inbox notebook and leave a one-line pointer on the page.

#### Scenario: A month calendar
- **WHEN** a page asks for next month's calendar and the host makes it as a document
- **THEN** the document appears beside the inbox notebook, and the page gets one line pointing to it

### Requirement: Every job leaves a record
The host SHALL record each job's outcome, phases, steps and durations.

#### Scenario: After a job
- **WHEN** a job answers a question
- **THEN** its record shows the outcome, the phases, the step kinds and their timings
