## ADDED Requirements

### Requirement: A harness can work the lean way
A text harness SHALL be able to say it is lean (`lean: true`), for a model that needs little telling and is dear to
call. On a lineup whose harness is lean the host SHALL give the model a short job description that states every
rule the host enforces and names each kind of step it is offered; SHALL send each turn only the calls that turn may
make; SHALL send a page that holds typed text and nothing else as its listing with no picture; and SHALL make a
step from the content its plan gave it (a write step's lines, a sketch's parts, a chart's spec) with no turn of its
own. A write step in a plan that has a search SHALL still be asked for in a turn of its own, with the results. A
sketch SHALL NOT be shown back to the model for a fix on a lean lineup. What
the host checks, refuses, erases and commits SHALL be the same as on any harness. PaperDaemon SHALL ship a lean
harness named "Lean Default (stronger models only)" and, built on it, one harness for each of Claude Opus 5.5,
Claude Sonnet 5.5 and Claude Haiku 5.5, each picked by its model's name. A lineup whose harness is not lean SHALL be
worked exactly as before.

#### Scenario: A job of words and a sketch on a lean lineup
- **WHEN** a page asks for two sentences and a small drawing, on a lineup whose harness is lean
- **THEN** the model's one decision gives the sentences and the drawing's parts in its plan, the host writes and
  draws them from the plan, and no further call is made

#### Scenario: A fact that has to be looked up
- **WHEN** a lean lineup's plan has a search step and a write step
- **THEN** the write step is asked for after the search, with the results, whatever words the plan gave it

#### Scenario: A typed page
- **WHEN** the page holds typed paragraphs and no ink, picture or PDF page
- **THEN** the model on a lean lineup is sent the paragraphs word for word and no picture of the page

#### Scenario: A lineup on the default harness
- **WHEN** a job runs on a lineup whose harness is not lean
- **THEN** its job description, its tool list and its turns are what they were
