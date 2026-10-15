# packaging/desktop Specification

## Purpose
Makes PaperDaemon installable and livable as a desktop app: installed without a terminal, running in the
background while the tablet is in use, and updated only when the user says so.

## Requirements

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

### Requirement: The app build compiles the decomposer first
Building the desktop app SHALL first compile the C decomposer: for any x86-64 processor when the build is
to be shared or published, for the building machine's processor otherwise. A failed compile SHALL stop the
build.

#### Scenario: A compile error
- **WHEN** the C decomposer fails to compile
- **THEN** no app is built, and the build's error names the compile step

#### Scenario: A shared build
- **WHEN** the app is built to be shared
- **THEN** its decomposer library runs on an x86-64 processor other than the building machine's

### Requirement: The app ships only what it runs
Once nothing the app runs imports them, the packaged app SHALL NOT include the decomposer's Python
reference dependencies (OpenCV, numba with llvmlite, SciPy, scikit-image, Shapely). They SHALL stay
pinned, at the exact versions the reference's results depend on, in a test-only dependency group.

#### Scenario: A built app
- **WHEN** the app is built
- **THEN** its folder holds none of those packages, and a picture sent from the desktop still becomes
  strokes
