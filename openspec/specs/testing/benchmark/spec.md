# testing/benchmark Specification

## Purpose
Tells the user what their configuration can do in PaperDaemon, by running the whole pipeline (daemon, host,
harnesses, text model, image model, hot swapping) on a mirror of its own, through the same cases every
time, and reporting the results page by page and stage by stage.

## Requirements

### Requirement: The benchmark runs on its own mirror
The benchmark SHALL open a mirror of its own, copied from the benchmark library bundled with PaperDaemon,
and SHALL NOT read the user's library or write to the cloud. The copy SHALL be deleted when the run
ends.

#### Scenario: Running the benchmark
- **WHEN** the user runs the benchmark
- **THEN** no page of the user's library is read, no cloud write happens, and the benchmark's mirror is
  gone after the run

### Requirement: The whole pipeline, as for real jobs
The benchmark SHALL deliver each case's page states into its mirror the way a sync delivers them, and
SHALL run its own daemon on that mirror. The daemon SHALL notice and dispatch them, and the same host,
harnesses, slots and hot swapping that real jobs use SHALL carry them out.

#### Scenario: A local pair with hot swapping
- **WHEN** the benchmark reaches a coloring-page case with hot swapping on
- **THEN** the image server is swapped in as it would be for a real job, and the report gives the
  swap's time

#### Scenario: An ignored page
- **WHEN** a case delivers a page that carries the ignore tag inside a tagged notebook
- **THEN** the report says whether the daemon left it alone

### Requirement: The user's jobs wait for the benchmark
A run asked for during a job SHALL begin when that job ends. While the benchmark runs, the user's
daemon SHALL hold new jobs and dispatch them, in order, when the run ends or is stopped.

#### Scenario: A page tagged during a run
- **WHEN** the user tags a page on the tablet while the benchmark runs
- **THEN** that page's job starts after the benchmark ends

### Requirement: The same cases every time
Every run of one benchmark version SHALL use the same cases, in the same order, with the same seed for
every picture, and the report SHALL name the version.

The cases SHALL cover:
- the daemon: dispatch, the ignore tag, a retag, the system prompt page, and a fresh ledger's baseline
- reading typed text and handwriting
- answers, charts, pictures, coloring pages, mark-ups, erasing and documents
- the notebook prompt, the notepad and tags
- search and fetch

#### Scenario: Two configurations
- **WHEN** the user runs the benchmark with one text model, then with another
- **THEN** both reports list the same cases, with the same pages and seeds, under the same version

### Requirement: Each case states and checks its outcome
Each case SHALL state what should happen, checked from the daemon's and the host's records and the
resulting page: for example, the answer placed below the question with nothing overlapping, the request
erased and the question kept, a chart drawn with its categories in order.

#### Scenario: A chart case
- **WHEN** the chart case runs
- **THEN** the report says whether a chart was drawn, whether its categories kept their order, and
  whether the request was erased

### Requirement: What the configuration cannot serve is not a failure
The benchmark SHALL run each slot's model test before the cases. A case that needs a slot or a
provider the configuration lacks, such as a picture with no image slot or a search with no search
provider, SHALL be reported as not available, with the reason, and SHALL NOT count as a failure.

#### Scenario: No search provider
- **WHEN** the benchmark runs with no search provider set
- **THEN** the search cases are reported as not available because no search provider is set

### Requirement: A report on what the configuration can do
The report SHALL record the configuration it ran on: each slot's model, harness and why, capability
overrides, hot swapping, the search provider, and PaperDaemon's and the benchmark's versions. It SHALL give:
- by capability, what passed, what failed and what was not available
- for each case, the rendered result page, pass or fail, what went wrong, and its time
- the time spent in each stage: the daemon's dispatch, reading the page, each model turn, pictures,
  decomposing, hot swaps and the commit, with the model's speed where its server reports it

The report SHALL fill in as cases finish, and the user SHALL be able to stop a run at any point.

#### Scenario: A model without vision
- **WHEN** the benchmark runs with a text model that cannot see
- **THEN** the summary shows which capabilities still pass, and each failed case shows its page and
  reason

#### Scenario: Where the time went
- **WHEN** a run with hot swapping ends
- **THEN** the report shows how long the text and image servers took to swap in each direction, next
  to the time the model turns and the pictures took

### Requirement: Only the latest report is kept
PaperDaemon SHALL keep only the latest benchmark report and its pages, and SHALL let the user delete it.

#### Scenario: Running twice
- **WHEN** the user runs the benchmark a second time
- **THEN** the first report is replaced by the second
