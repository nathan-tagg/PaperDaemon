## REMOVED Requirements

### Requirement: PaperDaemon guesses the harness and says why
**Reason**: the maintainer's ruling, 11-10: no automatic harness, "ZERO inference". The harness is the user's pick.
**Migration**: a slot saved as automatic is given, once, the harness the earlier version ran it on.

### Requirement: The user can pick the harness
**Reason**: it offered "automatic" beside the harnesses and spoke of a pick winning over a guess; there is no guess.
**Migration**: replaced by "A slot's harness is the one its user picked".

### Requirement: Variants that change parameters are told apart
**Reason**: it ruled which model names a guess might match; nothing is matched any more.
**Migration**: none; the user picks the harness made for the variant they run.

### Requirement: Shipped harnesses
**Reason**: it named a harness that is guessed from a start script, and shipped lineups that no longer ship.
**Migration**: replaced by "PaperDaemon's own harnesses".

## ADDED Requirements

### Requirement: A slot's harness is the one its user picked
Each slot's harness SHALL be the one its user picked from the harnesses of that slot's kind, PaperDaemon's own or
the user's; a slot whose user has picked none SHALL use the default harness of its kind, named "Default".
PaperDaemon SHALL NOT choose a harness from a model's name, from what a server reports, from a start script or from
a command, and SHALL offer no automatic choice. A slot that names a harness which is no longer there SHALL use the
default of its kind. A slot saved as automatic by an earlier version SHALL be read, once, as naming the harness that
version ran it on, and a slot that named a harness since removed (Claude Opus 5.5, Claude Sonnet 5.5, Claude Haiku
5.5) as naming Lean Default.

#### Scenario: A new lineup
- **WHEN** the user makes a lineup and types a model's name that an earlier version had a harness for
- **THEN** its Harness box reads "Default", and jobs use the default harness until the user picks another

#### Scenario: Picking a harness
- **WHEN** the user picks Z-Image Turbo in an image slot's Harness box
- **THEN** jobs use the Z-Image Turbo harness until the user changes it

#### Scenario: A lineup saved as automatic
- **WHEN** settings saved by an earlier version hold a slot whose harness is automatic and whose start script names
  a Qwen 3.8 27B file
- **THEN** the slot's Harness box reads "llama.cpp - Qwen 3.8 27B", the harness it had been running on, and nothing
  chooses for it again

### Requirement: PaperDaemon's own harnesses
PaperDaemon SHALL ship, as data files, the default text and image harnesses, each named "Default"; "Lean Default
(stronger models only)" for text; and harnesses for Qwen 3.6 27B (text), Qwen 3.8 27B (text), FLUX.2 Klein 9B
(image) and Z-Image Turbo (image). Each harness SHALL state the capabilities and parameters it sets.

#### Scenario: Klein's steps
- **WHEN** the image slot uses the FLUX.2 Klein 9B harness
- **THEN** a picture defaults to 4 steps, the model may choose from 4 to 12, and a coloring page uses 12
