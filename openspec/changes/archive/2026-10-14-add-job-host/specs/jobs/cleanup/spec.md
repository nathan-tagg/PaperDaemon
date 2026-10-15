# Spec Delta

## Purpose

Finishes a job by erasing the instruction the job carried out, so the user is not left to clean up,
while keeping every word of the user's that was not that instruction.

## ADDED Requirements

### Requirement: The carried-out request is erased
After a job carries out a request, the host SHALL erase that request from the page, typed or
handwritten.

#### Scenario: A chart request
- **WHEN** a page says "make a bar chart of my steps this week" and the job draws the chart
- **THEN** the request is erased and the chart stays

### Requirement: Questions, notes and other requests stay
The host SHALL NOT erase a question it answered, the user's notes, lists, role-play, or any request
this job did not carry out.

#### Scenario: A question
- **WHEN** a job answers "how far is the moon"
- **THEN** the question stays on the page above its answer

#### Scenario: A to-do beside a request
- **WHEN** a page holds "Fix the sink before Friday." and a chart request, and the job draws the chart
- **THEN** the chart request is erased and "Fix the sink before Friday." stays

### Requirement: The model's erasures pass the same test
When the model plans to erase something as a request, the host SHALL erase it only if it passes the same
carried-out-request test; otherwise it SHALL stay.

#### Scenario: The model reaches too far
- **WHEN** the model plans to erase the user's to-do line as part of a chart job
- **THEN** the host keeps the line

### Requirement: When unsure, keep
The host SHALL keep any line it cannot show was the request this job carried out.

#### Scenario: An ambiguous line
- **WHEN** a line might be a request or a note and the job's steps do not clearly match it
- **THEN** the line stays

### Requirement: What comes off is named by its id, a forced choice
The model SHALL name each thing to erase by the id the page's listing gave it -- a typed paragraph
`para:N`, a line of the user's handwriting `line:N`, an ink mark `mark:N`, a picture `picture:N` -- with
its verdict (request, asked or stale). The tools' schema SHALL make the id a choice from a fixed list of
every id the listing can print, so a description cannot be written in its place (the maintainer's
decision, after a model described a typed request in prose and called typed text ink, and the request
stayed under its answer). The list SHALL be the same for every job, so the prompt the server has cached
stays valid, and the listing SHALL never print an id outside it. The host SHALL check that a chosen id
exists on the page; one that does not SHALL fail its erase, as before, and nothing SHALL be erased by it.
What the model points at in words (an arrow, "this") is erased by pointing, not by an id.

#### Scenario: A typed request
- **WHEN** a page holds the typed request "Draw a sailboat on a calm lake at dawn." as its first paragraph
  and the model plans the picture
- **THEN** the model names `para:1` with because request, and the request comes off once the picture lands

#### Scenario: An id the page does not have
- **WHEN** the model names `para:3` on a page with one typed paragraph
- **THEN** that erase fails, nothing is erased by it, and the job's record says why
