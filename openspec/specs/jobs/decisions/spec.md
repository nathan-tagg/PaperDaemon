# jobs/decisions Specification

## Purpose
Puts the decisions about a page in the model's hands: what each new thing on the page is, what comes
off, and what each step answers and replaces. The model gets turns to look before it rules, and the host
enforces only validity.

## Requirements

### Requirement: The model rules on everything new on the page
Every plan and every answer SHALL carry a ruling for each item of the page's listing that is new since
this system last worked on the page: what the item is (a request, a command, something the user asked to
remove, this system's stale work, a question, conversation, a note, or other) and whether it comes off.
The host SHALL return a plan or an answer that leaves a new item unruled to the model, naming the items,
before anything runs.

#### Scenario: An unruled to-do line
- **WHEN** a page holds a new typed request and a new to-do line, and the model rules only the request
- **THEN** the host asks the model to rule the to-do line, and nothing runs until it has

### Requirement: The host checks validity, never intent
The host SHALL accept or refuse the model's decision on validity alone:
- every id it names exists on the page;
- every new item is ruled;
- the rulings are consistent: an item comes off only when ruled a request, a command, something the user
  asked to remove, or stale work, and only this system's own items are ruled stale work;
- each step belongs to an enabled feature and carries only that feature's fields;
- moves are legal;
- places fit the safe area without overlapping;
- a quoted citation is found in the notebook's system prompt or on the page;
- a replaced picture is one this system made, and no two steps replace it.

The host SHALL NOT change a step's kind, a ruling or a step's target because of the words on the page. A
refusal SHALL go back to the model as a turn that says what to fix.

#### Scenario: A question ruled to come off
- **WHEN** the model rules a question as a question that comes off
- **THEN** the host refuses the ruling as inconsistent and asks the model again

#### Scenario: A generated picture of something on the web
- **WHEN** the model plans an image step for "the best photos from a photo-sharing site"
- **THEN** the host has the picture generated as planned, and does not turn the step into a web picture

### Requirement: A request comes off once the work that answers it has landed
Each step SHALL name the listing ids it carries out. A request ruled to come off SHALL come off at commit
only when every step that names it has succeeded. If one of them failed, the request SHALL stay on the
page and the job's record SHALL say why.

#### Scenario: A picture that failed
- **WHEN** a plan's picture step answers para:1 and the picture fails to generate
- **THEN** para:1 stays on the page, and the job's record says the work it asked for did not land

### Requirement: Redoing a picture is the model's choice
A step that redoes a picture this system made SHALL name that picture in the field for what it replaces.
The host SHALL put the new picture in the old one's place and take the old one off. The host SHALL NOT
infer a redo from the words of a step or of a request.

#### Scenario: A calendar redone
- **WHEN** the model plans a calendar step that replaces picture:1, the calendar it made earlier
- **THEN** the new calendar takes the old one's place, and the old one comes off

#### Scenario: A calendar not marked as a redo
- **WHEN** the model plans a calendar step without naming a picture it replaces, on a page that holds a
  calendar it made earlier
- **THEN** the new calendar is placed clear of the earlier one, and the earlier one stays

### Requirement: The model may look before it rules
In the decision turn the model SHALL be offered, as far as the enabled features allow: a closer look at
an item or a region of the page, the page with its marks numbered, the page as an earlier job found it,
what changed since the last job, and the notebook's notepad beyond the part the intake shows. A model
without vision SHALL get these in text form. The host SHALL bound these turns by the text harness's token
budget and SHALL refuse a look identical to one already given; it SHALL NOT bound them by time. Once the
budget is spent, only the decision tools SHALL remain on offer.

#### Scenario: Two looks, then a decision
- **WHEN** the model asks for a closer look at line:2 and then for the page as the last job found it
- **THEN** it gets each, and its decision follows

#### Scenario: The same look twice
- **WHEN** the model asks for the same look with the same arguments a second time
- **THEN** the second is refused as already shown

#### Scenario: The budget is spent
- **WHEN** the looks have used the harness's token budget
- **THEN** the next turn offers only skip, answer and plan

### Requirement: Fields the model fills, in place of the request's words
What the host used to read out of a step's or a request's words SHALL be fields the model fills:
- the step's kind, from a fixed list
- a social posts step's source, search words, sort, period, whether it wants picture posts, and count
- a web picture's site and count
- a calendar's month, as year and month, or the week
- a mark-up's target id and the exact words within it
- a chess game's color, strength and opponent, and a chat's members
- whether a character's picture is of itself

The host SHALL check each field's form, and SHALL NOT fill or change a field from the words.

#### Scenario: A social posts step
- **WHEN** the model plans a posts step with source r/gardening, search "tomato blight", sort top and
  period week
- **THEN** the host asks for exactly that search, sort and period, and adds no words of its own

#### Scenario: A calendar month in words
- **WHEN** the model plans a calendar step whose month is "next October" instead of a year and a month
- **THEN** the host refuses the step's form and asks for the year and the month

### Requirement: Keyword assists come only from a harness's data
A harness MAY carry keyword assists, each named for one decision. After the model's decision the host
SHALL apply them:
- a hint that fires and disagrees with the model's value SHALL go back to the model as one turn within
  the decision's budget, and the model's answer to it SHALL stand;
- an override SHALL set the value, and the job's record SHALL name the assist that set it.

With no assists in the harness, no keyword SHALL change or question any decision. The shipped harnesses
SHALL carry none.

#### Scenario: A hint
- **WHEN** a harness's assist hints that a step naming "online" is a web picture, and the model planned
  an image step that names it
- **THEN** the model is shown the hint once, and the step it settles on is carried out

#### Scenario: The default harness
- **WHEN** a job runs on a shipped harness
- **THEN** no keyword changes or questions any of the model's decisions
