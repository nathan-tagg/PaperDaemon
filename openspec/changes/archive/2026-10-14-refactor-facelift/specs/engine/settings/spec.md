# Spec Delta

## ADDED Requirements

### Requirement: One schema describes every setting
PaperDaemon SHALL describe every setting once: its path, type, default, allowed values, label, help text,
and whether it is a secret. Loading defaults, validation, the API and the settings screens SHALL all take
these from that one description. The API SHALL serve the description, and the settings screens SHALL NOT
restate a rule of their own.

#### Scenario: A port out of range
- **WHEN** the user enters 80 as the engine's port
- **THEN** the settings screen shows the schema's message, and the API refuses the same value with the
  same message

#### Scenario: A new setting
- **WHEN** a setting is added to the schema
- **THEN** it takes its default on load, is validated, and appears on its screen, with no other code
  written for it

### Requirement: Settings reach the host only through its run file
The host SHALL read settings only from the run file the engine writes for it. It SHALL NOT read the
settings file itself, and no setting SHALL reach it only through an environment variable.

#### Scenario: A new location
- **WHEN** the user changes the location setting
- **THEN** the run file the next job runs under carries the new location, and the job's forecast is for
  that place
