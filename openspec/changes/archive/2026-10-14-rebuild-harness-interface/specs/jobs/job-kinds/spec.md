# Spec Delta

## Purpose

What a page's work is made of: one enumerated list of job kinds, each with a protocol the host holds, so the
host always knows what to do with a job and the model is asked only for what needs it.

## ADDED Requirements

### Requirement: Jobs are one enumerated list
Every job a harness schedules SHALL be one of: ERASE, SEARCH, WRITE, CHART, CALENDAR, POSTS, DRAW, IMAGE,
COLORING, PICTURE_EDIT, WEB_PICTURE, HIGHLIGHT, CIRCLE, UNDERLINE, STRIKE, GAME_START, GAME_TURN, TAG,
NOTE, REMEMBER, CONFLICT. The host SHALL refuse a job of any other kind, and a job of a kind the capacity
engine has turned off for the lineup, each with its reason.

#### Scenario: A kind that is off
- **WHEN** a lineup has no image model and its model schedules an IMAGE job
- **THEN** the host refuses the job, and the record says the lineup has no image model

### Requirement: The host holds each kind's protocol
Each job kind SHALL have a protocol the host holds: whether the model supplies something in a turn of its own,
what it supplies, what the host does with it, and whether the result goes back to the model. WRITE, CHART,
CALENDAR, DRAW, GAME_TURN and CONFLICT SHALL get a model turn of their own; every other kind SHALL be carried
out by the host from what the plan said, with no model turn. A harness MAY override a kind's protocol.

#### Scenario: An erase needs no model
- **WHEN** a plan erases para:2 because it was the request
- **THEN** the host erases it without asking the model anything more

#### Scenario: A chart gets one turn
- **WHEN** a plan has a CHART job
- **THEN** the model is asked once for the chart's spec, and the host renders and places it

### Requirement: The host works through the jobs one at a time
The host SHALL order a plan's jobs (erasing first, then searches, then the rest as planned) and carry them out
one after another, never two at once. A job MAY ask for a job the plan lacked; the host SHALL insert it and come
back. A failed content job SHALL keep the request it answered on the page.

#### Scenario: A search before the chart it feeds
- **WHEN** a plan lists a chart and then the search for its figures
- **THEN** the search runs first, and its results go into the chart's turn

### Requirement: The host asks the model nothing on its own
The host SHALL NOT compose a prompt or read a model's reply itself. When it must find something on the page,
read handwriting or describe a picture, it SHALL ask through the harness's `locate`, `read_ink` or `describe`.

#### Scenario: Finding the words to circle
- **WHEN** a CIRCLE job names words that are not in the page's typed text
- **THEN** the host asks the harness to locate them, and circles what the harness reads from the reply

### Requirement: A game page goes through intake
A page holding a game SHALL be read by the harness's intake like any page, and the turn on it SHALL be a
GAME_TURN job; the game engine SHALL keep the game's state and its legal moves.

#### Scenario: A move written on a chess page
- **WHEN** the player writes a move on a chess page and tags it
- **THEN** the job is a GAME_TURN: the writing is read through `read_ink`, the engine plays it, and the
  character answers
