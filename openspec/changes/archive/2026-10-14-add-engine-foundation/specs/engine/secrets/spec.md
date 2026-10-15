# Spec Delta

## Purpose

Keeps PaperDaemon's secrets (the reMarkable device token, the model and search API keys, and the pairing
token) in the operating system's credential store and nowhere else.

## ADDED Requirements

### Requirement: Secrets live only in the credential store
PaperDaemon SHALL store every secret in the operating system's credential store (Windows Credential
Manager, the macOS Keychain, or the Secret Service on Linux) under PaperDaemon's own service name, and
SHALL NOT write a secret to any file, log or console.

#### Scenario: Device token saved
- **WHEN** the user saves a device token
- **THEN** the credential store holds it and no file under PaperDaemon's data folder contains it

#### Scenario: Engine log after a cloud call
- **WHEN** the engine signs in to the reMarkable cloud and logs the call
- **THEN** the log line contains neither the device token nor the session token

### Requirement: The API reports secrets as set or not set
The local API SHALL report only whether each secret is set, never its value. The one exception is the
pairing token, which the network settings show on request so that another device can be paired.

#### Scenario: Reading the settings
- **WHEN** the UI asks for the settings
- **THEN** the answer says which secrets are set and contains none of their values

### Requirement: Secrets can be replaced and removed
The user SHALL be able to replace or remove each secret from the UI. Removing the device token SHALL
also end any cloud session made with it.

#### Scenario: Removing the device token
- **WHEN** the user removes the device token
- **THEN** the credential store no longer holds it, and the next cloud call reports that PaperDaemon is not
  connected until a new token is saved

### Requirement: A pasted device token is cleaned before it is stored
PaperDaemon SHALL trim surrounding whitespace and remove the `@ByteArray(...)` wrapper that the reMarkable
desktop app puts around its token before storing a device token.

#### Scenario: Token copied from the desktop app's registry value
- **WHEN** the user pastes a token wrapped as `@ByteArray(...)`
- **THEN** PaperDaemon stores the token without the wrapper
