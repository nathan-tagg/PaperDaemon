# extensions/tools Specification

## Purpose
Lets new abilities be added to PaperDaemon as tools the host can offer, without changing the host, and keeps
tools that act outside the tablet under the user's explicit control.

## Requirements

### Requirement: Every tool plugs in the same way
Every tool the host offers SHALL be a feature. It SHALL declare its name, the description the model is
given, its input, its hard and optional requirements (other features among them), and the action the host
runs. Built-in tools SHALL use the same interface as added ones.

#### Scenario: A new tool
- **WHEN** a developer adds a tool that meets the interface
- **THEN** the host can offer it without any change to the host's code

#### Scenario: A tool that needs another
- **WHEN** a developer adds a tool that requires the search feature, and search is off
- **THEN** the tool is off, and its reason names search and why search is off

### Requirement: A tool is offered only when its needs are met
The host SHALL offer a tool only when its feature is on or degraded in the host's run file
(jobs/features).

#### Scenario: Pictures without an image slot
- **WHEN** the image slot is empty
- **THEN** the picture and coloring-page tools are not offered, and the Models screen says why

### Requirement: The user can switch tools off
The settings SHALL let the user switch any tool off, and the Models screen SHALL show each tool's state
and what it needs. A tool that is off SHALL never be offered to the model.

#### Scenario: Social cards off
- **WHEN** the user switches social cards off
- **THEN** no job is offered the social cards tool

### Requirement: Outside-world tools need explicit direction
A tool that acts outside the tablet (running a command, controlling a device, sending a message) SHALL
be off by default, SHALL be marked as acting outside the tablet on the capabilities screen, and SHALL
run only when the notebook's system prompt or the page names that action, checked by the host as the
tag step's direction is checked.

#### Scenario: A garage door tool
- **WHEN** a garage door tool is switched on and a page says "it's cold in here"
- **THEN** the tool does not run, because no page or prompt named opening or closing the garage door

### Requirement: A failing tool does not stop the job
When a tool fails, the host SHALL record the failure in the job and carry on with the rest of the plan
where it can.

#### Scenario: A tool raises an error
- **WHEN** a tool fails while a job also writes an answer
- **THEN** the answer is written, and the job's record names the failed tool
