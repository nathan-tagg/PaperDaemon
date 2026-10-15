# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: The host reads the page and runs the job by the harness's protocols
**Reason**: A harness is data, not a set of protocols in code. One host runs every job the same way.
**Migration**: Replaced by "The host runs every job by the harness's data and the resolved features".

### Requirement: A harness may hand back a finished page
**Reason**: No harness carries code that runs a job, so no harness hands back a page of its own making.
**Migration**: A stronger model works through the same features, with more looks and its own drawing
through the draw feature. A future interpreter mode that accepts a finished page is an open question in
design.md.

### Requirement: Nothing validate() refuses is committed
**Reason**: There is no per-harness validate(). The host's validity rules apply to every job.
**Migration**: Replaced by "Nothing invalid is committed".

### Requirement: The host decides where things go when the protocol leaves it placement
**Reason**: There are no task protocols to leave placement to the host; the host always places.
**Migration**: Replaced by "The host decides where things go", with the same rules and scenarios.
