# Spec Delta

## MODIFIED Requirements

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
