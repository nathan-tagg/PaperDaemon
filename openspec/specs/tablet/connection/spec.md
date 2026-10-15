# tablet/connection Specification

## Purpose
Connects PaperDaemon to the user's reMarkable cloud account with a device token the user pastes, and
proves that the connection works.

## Requirements

### Requirement: One field for the device token
The tablet settings SHALL offer one field for a device token and SHALL NOT offer a reMarkable
sign-in flow.

#### Scenario: Connecting for the first time
- **WHEN** the user opens the tablet settings with no device token saved
- **THEN** they see a field to paste a device token and a pointer to the README's instructions

### Requirement: The connection can be checked
The user SHALL be able to check the connection. The check SHALL sign in with the device token and read
the library's root, then report either success with the library generation or the error the cloud gave.

#### Scenario: A good token
- **WHEN** the user checks the connection with a valid device token
- **THEN** the answer says the connection works and gives the library generation

#### Scenario: A revoked token
- **WHEN** the device was removed at my.remarkable.com and the user checks the connection
- **THEN** the answer reports the cloud's refusal, and PaperDaemon does not keep retrying in the background

### Requirement: Session tokens stay in memory
PaperDaemon SHALL exchange the device token for a session token when it needs one, keep the session token
in memory only, and get a new one before the old one expires.

#### Scenario: A long run
- **WHEN** PaperDaemon has been running longer than a session token lasts
- **THEN** cloud calls keep working without the user doing anything, and no session token was written
  to disk

### Requirement: The README explains how to get a device token
The README SHALL explain two ways to get a device token: registering PaperDaemon as its own device with a
one-time code, and reusing the reMarkable desktop app's token. It SHALL say what each choice means
for revoking access and for the cloud's change notifications.

#### Scenario: A new user
- **WHEN** a new user reads the README's device token section
- **THEN** they find both ways, with commands for Windows and for other systems, and the consequences
  of each
