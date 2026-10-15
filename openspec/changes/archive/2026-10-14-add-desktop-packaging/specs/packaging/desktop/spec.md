# Spec Delta

## Purpose

Makes PaperDaemon installable and livable as a desktop app: installed without a terminal, running in the
background while the tablet is in use, and updated only when the user says so.

## ADDED Requirements

### Requirement: A per-user installer
PaperDaemon SHALL install on Windows for the current user without administrator rights, and SHALL add a
Start menu entry.

#### Scenario: Installing
- **WHEN** a user without administrator rights runs the installer
- **THEN** PaperDaemon installs and appears in the Start menu

### Requirement: Closing the window keeps PaperDaemon running
Closing the window SHALL leave PaperDaemon running in the tray with the daemon working. Quitting from the
tray SHALL stop PaperDaemon and every process it started.

#### Scenario: Closing the window
- **WHEN** the user closes PaperDaemon's window
- **THEN** the tray icon stays, and a page tagged afterward is still answered

#### Scenario: Quitting
- **WHEN** the user chooses Quit from the tray
- **THEN** PaperDaemon and every model server it started are gone

### Requirement: One running PaperDaemon
Starting PaperDaemon while it is already running SHALL bring up the running one's window instead of starting
a second engine.

#### Scenario: Opening it twice
- **WHEN** the user opens PaperDaemon from the Start menu while it runs in the tray
- **THEN** the running PaperDaemon's window appears and no second engine starts

### Requirement: Updates are checked only when asked, and PaperDaemon never starts itself
PaperDaemon SHALL check for updates only when the user asks (the tray or Settings), and SHALL make no network
call for updates otherwise. PaperDaemon SHALL NOT start with Windows, and SHALL offer no option to.

#### Scenario: A fresh install
- **WHEN** PaperDaemon is installed and the user signs in to Windows the next day
- **THEN** PaperDaemon has not started, and it has made no update check

### Requirement: Signed builds
Release builds SHALL be code-signed so the operating system identifies their publisher.

#### Scenario: Downloading a release
- **WHEN** a user runs a downloaded release installer
- **THEN** the operating system shows PaperDaemon's publisher, not an unknown-publisher warning

### Requirement: Uninstalling keeps the user's data by default
Uninstalling SHALL leave PaperDaemon's data folder and credential store entries in place unless the user
chooses to remove them.

#### Scenario: Reinstalling later
- **WHEN** the user uninstalls and later reinstalls PaperDaemon without choosing to remove data
- **THEN** their settings and secrets are still there
