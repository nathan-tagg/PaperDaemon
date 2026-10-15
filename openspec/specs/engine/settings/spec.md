# engine/settings Specification

## Purpose
Holds everything the user can configure in PaperDaemon, apart from secrets, in one file that survives
restarts and can never be left half-written.

## Requirements

### Requirement: Settings live in PaperDaemon's own data folder
PaperDaemon SHALL keep its settings in one file inside its own data folder: `%APPDATA%\PaperDaemon` on
Windows, `~/.local/share/paperdaemon` elsewhere, or the folder named by the `PAPERDAEMON_HOME` environment
variable when it is set.

#### Scenario: Default location on Windows
- **WHEN** PaperDaemon starts on Windows with `PAPERDAEMON_HOME` unset
- **THEN** it reads and writes its settings under `%APPDATA%\PaperDaemon`

#### Scenario: Overridden location
- **WHEN** `PAPERDAEMON_HOME` names a folder
- **THEN** PaperDaemon keeps its settings, its mirror and all its other data in that folder

### Requirement: Missing settings take their defaults
PaperDaemon SHALL give every setting the file lacks its default value, and SHALL start on defaults when
the file is missing or unreadable.

#### Scenario: First start
- **WHEN** PaperDaemon starts and no settings file exists
- **THEN** every setting has its default value and PaperDaemon runs

#### Scenario: A file from an older version
- **WHEN** the settings file lacks a setting that a later version added
- **THEN** that setting takes its default and every setting the file does hold is kept

### Requirement: Invalid settings are refused whole
PaperDaemon SHALL validate settings before saving them and SHALL save none of them when any is invalid,
naming every problem. The rules include: the trigger tag and the inbox are not empty, and the trigger
tag is neither of the fixed tag names "ignore" and "sprompt", ignoring case; the API port is a whole
number from 1024 to 65535; the listen addresses include 127.0.0.1.

#### Scenario: A trigger tag named like a fixed tag
- **WHEN** the user saves settings whose trigger tag is "Ignore"
- **THEN** nothing is saved and the answer says "ignore" and "sprompt" are tag names of their own

#### Scenario: Loopback left out
- **WHEN** the user saves listen addresses without 127.0.0.1
- **THEN** nothing is saved and the answer says 127.0.0.1 is required

### Requirement: Saves are atomic
PaperDaemon SHALL write the settings file so that a crash or power loss during a save leaves either the
old file or the new one, never a partial file.

#### Scenario: Stopped mid-save
- **WHEN** PaperDaemon stops in the middle of saving settings
- **THEN** the next start reads a complete settings file, old or new

### Requirement: No secret is ever in the settings file
The settings file SHALL NOT contain any secret: no device token, no API key, no pairing token.

#### Scenario: Saving a key
- **WHEN** the user saves an API key for a model slot
- **THEN** the settings file does not contain the key, and the credential store does

### Requirement: The tablet settings name the trigger tag and the inbox
The settings SHALL hold:
- the trigger tag, which marks a page for PaperDaemon, defaulting to the app's name;
- the inbox, the notebook on the tablet (by path) that receives pictures sent from the desktop,
  defaulting to the app's name followed by "inbox".

The user SHALL be able to change both. The two other tags PaperDaemon reads are NOT settings: their
names are fixed and universal, the same for every user and every lineup, and matched ignoring case (the
maintainer's decision): "ignore", which keeps PaperDaemon away from whatever carries it, and "sprompt",
which marks the page holding a notebook's standing instructions. A settings file from an earlier version
that holds a mute tag or a system prompt tag SHALL load with those keys dropped. Nothing SHALL assume
there is only ever one trigger tag: per-lineup trigger tags may follow.

#### Scenario: The user renames the trigger tag
- **WHEN** the user sets the trigger tag to "the pipeline" and saves
- **THEN** the settings hold "the pipeline" as the trigger tag after a restart

#### Scenario: An older file names its own mute tag
- **WHEN** PaperDaemon loads a settings file that sets the mute tag to "quiet"
- **THEN** the setting is dropped, and "ignore" is the tag that keeps PaperDaemon away

#### Scenario: The user picks an inbox notebook
- **WHEN** the user sets the inbox to "Projects/Coloring inbox" and saves
- **THEN** the settings hold that notebook path after a restart

### Requirement: Local facts come from the user's location setting
The settings SHALL hold an optional location (a place name with its latitude and longitude, and a
holiday region) that jobs use for weather, holidays and sunrise times, and SHALL be empty by default.
No location SHALL be built into PaperDaemon.

#### Scenario: No location set
- **WHEN** the location is empty and a page asks for this week's calendar
- **THEN** the calendar is made without weather or local holidays, and says a location can be set

#### Scenario: A location set
- **WHEN** the user sets their town and holiday region
- **THEN** calendars and forecasts use that town's weather and that region's holidays

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
