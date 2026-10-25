# jobs/host Specification

## Purpose
Runs each dispatched job: reads the page, runs the job by the text harness's protocols, carries out
the host's part of each task, and commits what the harness's validate() passes.

## Requirements

### Requirement: The task vocabulary belongs to the host
The host SHALL define the tasks a job can use, each as a feature:
- writing words
- a chart, a calendar, social posts
- a picture, a coloring page, a picture edit, a picture found on the web
- a mark-up
- an erasure
- a search
- a drawing
- a game
- a tag
- a notepad line

Which of these a model is offered SHALL follow from the resolved features. The host's part of a task
SHALL work the same way for every harness.

#### Scenario: The same chart for two harnesses
- **WHEN** two text models ask for a bar chart of the same data
- **THEN** the host draws the same chart both times

### Requirement: Every tablet's page is laid out in its own frame
A page SHALL be laid out in the frame its tablet wrote into it: a Paper Pro's 1620 x 2160, a Paper Pro
Move's 954 x 1696, a reMarkable 2's or a Paper Pure's 1404 x 1872. The model SHALL be told the page's own
size, and nothing about the tablet: a frame does not say which tablet made the page (a Paper Pro has
written a 1404 x 1872 page). The safe area's margins SHALL
scale with the tablet's pixel density, and a PDF page's with its width, since it is shown fitted. A page
drawn as one picture (a chat, an adventure, the Decompose inbox) SHALL be fitted to the page's width from
its top. A page PaperDaemon adds SHALL be in its notebook's frame, and a notebook it makes from nothing in
the frame of the user's own library.

#### Scenario: A chess game on a Paper Pro Move
- **WHEN** a game starts on a Paper Pro Move's page
- **THEN** the board is square, inside that page's safe area with its labels, and below its toolbar

### Requirement: Everything stays inside the safe area, below the toolbar
Every kind of content the host or a game puts on a page -- words, charts, calendars, pictures, game pages,
the pages of documents it makes -- SHALL stay inside the page's safe area, whose top clears the tablet's
toolbar docked across the top of the screen and whose sides and foot keep a small margin. The safe area's
top is y 115 on a 1620 x 2160 page, measured on the tablet. The safe area SHALL be defined once, and every
placement SHALL take its top from that definition rather than a number of its own. Content may run below
the foot and the page scrolls.

A full coloring page alone on its page is the exception: it SHALL take the whole screen, the page frame the
tablet shows without scrolling (x -810..810, y 0..2160 on a notebook page), and SHALL be generated in that
frame's exact shape.

#### Scenario: A coloring book page
- **WHEN** a job makes a full coloring page and nothing else on its page
- **THEN** the picture fills the screen from its top edge to its bottom edge, side to side, with no white bands

#### Scenario: A picture on an empty page
- **WHEN** a job puts a full-size picture on a page whose request was erased
- **THEN** the picture's top is at the safe area's top, below the toolbar, not at the page's top

#### Scenario: A chess page
- **WHEN** a chess game starts on a new page
- **THEN** the opponent's portrait and talk start at the safe area's top

### Requirement: Tasks follow capabilities
The host SHALL offer only the steps and tools of the features that are on or degraded in its run file
(jobs/features). When the text slot's vision is off, the host SHALL give the model no image of the page,
so the model gets the page as text: the typed text exactly, and the handwriting reader's lines with
their positions.

#### Scenario: No image slot
- **WHEN** the image slot is empty and a page asks for a picture of a fox
- **THEN** the model is offered no picture or coloring step, and the job says pictures are not available

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

### Requirement: The host runs every job by the harness's data and the resolved features
For each job the host SHALL read the page (its typed text, the handwriting reader's lines, its pictures
and marks, and an image of it), and gather the notebook's system prompt, its notepad, the date and the
user's location. It SHALL run every job the same way: one decision turn with the looks the enabled
features allow, each step by its feature, the validity checks, then the commit. What differs between
models SHALL come only from the harness's data and the resolved features. The host SHALL NOT branch on
which model or harness runs.

#### Scenario: A question on a page
- **WHEN** a page asks "what is the tallest mountain in Colorado"
- **THEN** the model answers in words, and the host writes them on the page

#### Scenario: Another turn after a lookup
- **WHEN** a page asks who won last night's game and the model plans a search and a write step
- **THEN** the host runs the search, the model writes the answer from the results in its write step's
  turn, and the host lays the answer out on the page

#### Scenario: Two harnesses, one host
- **WHEN** two text harnesses differ only in their data and run the same page
- **THEN** the same code runs both jobs, and every difference in what is sent to the models comes from
  the two harnesses' data

### Requirement: Nothing invalid is committed
Before committing any job, the host SHALL apply its validity rules (jobs/decisions), commit only what
passes, and record what was refused and why. A planned place that received no content SHALL go back to
the model once, so it can fill it.

#### Scenario: A picture that never came
- **WHEN** a planned picture fails to generate
- **THEN** the job records the failed step, and nothing that depended on it is committed

#### Scenario: A plan that goes too far
- **WHEN** the model's plan rules a paragraph of the user's notes a note that comes off
- **THEN** the ruling is refused as inconsistent, the job records why, and the note stays

### Requirement: The host decides where things go
The model SHALL say what goes on the page and roughly how big, and the host SHALL decide where. Planned
places SHALL NOT overlap each other or anything already on the page. A plan that does not fit SHALL be
refused with the numbers, so the model can plan again.

#### Scenario: A chart below typed notes
- **WHEN** the model plans a large chart on a page with typed notes at the top
- **THEN** the host places the chart below the notes, clear of them

#### Scenario: A plan that does not fit
- **WHEN** the model plans three large pictures on a nearly full page
- **THEN** the host refuses the plan, says how much room is left, and the model plans again

### Requirement: What a job writes is the tablet's own author's
Everything a job writes on a page (its strokes, typed text and pictures) SHALL carry the tablet's own author id (1),
numbered after every id the page already holds. The tablet does not open a page holding an item of an author it does
not know: a page written under an author of PaperDaemon's own (219, tried in 0.1.79) would not open, and the same
answer under the tablet's author on a fresh page did. Another author SHALL NOT be used until a page under it is shown
to open on the device. A picture's ids SHALL be written with their author in one byte, as the format has it.

#### Scenario: An answer lettered on a page
- **WHEN** a job writes its answer on a page
- **THEN** every new item is of author 1, numbered past every id already there, and the page's author table is
  unchanged
