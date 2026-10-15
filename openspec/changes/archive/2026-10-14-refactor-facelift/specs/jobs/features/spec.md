# Spec Delta

## Purpose

Says which features PaperDaemon offers with each lineup. Each feature declares what it requires,
the engine resolves the features for every lineup, and the host offers the model only what is
on.

## ADDED Requirements

### Requirement: Every feature declares what it requires
Each feature SHALL declare its requirements, each either hard or optional, from these kinds: text
capabilities, image abilities and workflows, a search provider, installed content, a filled setting, and
other features. A feature with an unmet hard requirement SHALL be off. A feature whose only unmet
requirements are optional SHALL be degraded, and SHALL work without what it lacks.

#### Scenario: No image slot
- **WHEN** a lineup's image slot has no location
- **THEN** the image, coloring and picture edit features are off, each with its reason

#### Scenario: A missing workflow
- **WHEN** the image harness has no coloring book workflow
- **THEN** the coloring feature is degraded, a coloring page is made from the plain subject, and the job's
  log says the workflow was missing

### Requirement: Features may require other features
A feature MAY require another feature, as a hard or an optional requirement. A feature that hard-requires
a feature that is off SHALL be off, and its reason SHALL name the chain of features down to the unmet
requirement.

#### Scenario: No search provider
- **WHEN** no search provider is configured
- **THEN** the search feature is off because no search provider is configured, and the web picture
  feature is off because search is off because no search provider is configured

### Requirement: A cycle of requirements is refused at startup
PaperDaemon SHALL check the feature list when it starts. A cycle of requirements among features SHALL
stop the engine from starting, with an error that names every feature in the cycle.

#### Scenario: Two features that require each other
- **WHEN** a feature A requires B and B requires A
- **THEN** the engine does not start, and its error names A and B

### Requirement: The engine resolves the features when a lineup is activated
When a lineup is activated, and whenever the engine starts, the engine SHALL resolve every feature
against that lineup's slots, the settings and the installed content, and SHALL write the result into the
host's run file: each feature's state (on, degraded or off) with its reasons. The host SHALL be restarted
between jobs when the result changes.

#### Scenario: Switching to a lineup without pictures
- **WHEN** the user activates a lineup whose image slot is empty
- **THEN** the run file lists the picture features as off with their reasons, and the host restarts
  before the next job

### Requirement: The host offers only the enabled features
The host SHALL build the model's instructions and tools only from the features that are on or degraded,
and SHALL leave out of a degraded feature what it lacks. While the run file is unchanged, the
instructions and the tools SHALL stay byte-identical from job to job.

#### Scenario: Coloring is off
- **WHEN** the coloring feature is off
- **THEN** the model's instructions say nothing about coloring pages, and coloring is not among the
  plan's step kinds

#### Scenario: The same lineup, two jobs
- **WHEN** two jobs run under the same run file
- **THEN** their instructions and tool schemas are byte-identical

### Requirement: A step of a disabled feature is refused
The host SHALL refuse a step whose kind belongs to a feature that is off before running any of it, SHALL
tell the model the feature's reason, and SHALL keep the refusal in the job's record.

#### Scenario: A model that ignores the schema
- **WHEN** the image feature is off and a model on a server that does not enforce the tool schema plans
  an image step
- **THEN** the step is refused with the reason, nothing is sent to an image server, and the job's record
  keeps the refusal

### Requirement: The user and the harness can switch features off
The user SHALL be able to switch any feature off in the settings, and a harness's data MAY switch
features off. A feature switched off SHALL be off with that reason. Neither SHALL turn on a feature whose
hard requirements are unmet.

#### Scenario: Social posts switched off
- **WHEN** the user switches the posts feature off
- **THEN** the feature is off because it is switched off in the settings, and no job is offered social
  posts

### Requirement: The Models screen shows each lineup's features
The Models screen SHALL show, for each lineup, every feature with its state, and for each feature that
is off or degraded, its reasons.

#### Scenario: A lineup with no search provider
- **WHEN** the user opens the Models screen and no search provider is configured
- **THEN** each lineup lists search and web picture as off, each with its chain of reasons
