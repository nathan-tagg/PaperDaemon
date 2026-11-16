## MODIFIED Requirements

### Requirement: Jobs start after a page settles, one at a time
The daemon SHALL start a job only after the page has stopped changing. Jobs on different notebooks SHALL run at the
same time, each in a process of its own, and a notebook SHALL have at most one job running; its other pages SHALL wait
for it, in the order they became ready. A LOCAL job -- one whose lineup's text model runs on this computer's graphics card
(served at this computer's address or started by a start script; a command-line program is not one) -- SHALL run only
when no other local job runs, in either library. A picture from an image model on this computer SHALL take its turn on
the graphics card, one picture at a time, without holding any job back. Every job's model calls,
pictures and searches SHALL go to its own lineup's models, whatever other jobs run.

#### Scenario: The user is still writing
- **WHEN** the user keeps writing on a tagged page and the tablet syncs several times
- **THEN** no job starts until the page has stopped changing

#### Scenario: Two notebooks at once
- **WHEN** pages of two notebooks, each tagged for a lineup of cloud or command-line models, become ready together
- **THEN** both jobs run at the same time, each on its own lineup, and each page is answered

#### Scenario: Two pages of one notebook
- **WHEN** two pages of one notebook become ready together
- **THEN** the second page's job starts once the first one's is recorded

#### Scenario: Local jobs take turns
- **WHEN** pages of two notebooks tagged for lineups whose models run on this computer become ready together
- **THEN** one job runs, and the other starts when it is recorded, while jobs of cloud lineups run beside them

## ADDED Requirements

### Requirement: A job's work goes up with its own record
When a job is recorded, what it wrote SHALL be pushed to the tablet, and nothing written by another job still running
SHALL go with it: the notebooks other jobs are working and the documents they made SHALL wait for their own job's
record. Abandoning a job SHALL end that job alone, put back what it wrote to its notebook and remove the documents it
made; the other jobs SHALL run on. An update SHALL wait for every job in progress.

#### Scenario: One job finishes while another works
- **WHEN** a job on notebook A is recorded while a job on notebook B is still working
- **THEN** A's page goes up to the tablet and B's notebook is not pushed until B's job is recorded

#### Scenario: Abandoning one of two jobs
- **WHEN** the user abandons the job on notebook B while A's job works
- **THEN** B's job ends and what it wrote is put back, and A's job goes on to its end

### Requirement: The window shows every job being worked
The window SHALL show a progress bar on the cover of every notebook a job is working, and the job list SHALL show
every job working.

#### Scenario: Two bars
- **WHEN** two notebooks are being worked
- **THEN** each one's cover carries its own job's bar
