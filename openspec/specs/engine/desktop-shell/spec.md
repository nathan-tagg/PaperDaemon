# engine/desktop-shell Specification

## Purpose
Gives PaperDaemon a desktop window of its own that shows its UI without a web browser, and a headless mode
for machines reached over the network.

## Requirements

### Requirement: The UI opens in PaperDaemon's own window
Starting PaperDaemon SHALL open one native window that shows the UI served by the local API, and SHALL NOT
open a web browser.

#### Scenario: Start
- **WHEN** the user starts PaperDaemon
- **THEN** one PaperDaemon window opens showing the UI, and no browser window or tab opens

### Requirement: The window opens once the engine answers
The window SHALL open only after the local API answers on 127.0.0.1, so the UI never starts on a
connection error.

#### Scenario: Slow engine start
- **WHEN** the engine takes a few seconds to start listening
- **THEN** the window appears after the API answers and shows the UI, not an error page

### Requirement: Headless mode
PaperDaemon SHALL run without a window when started with `--headless`, serving the API until it is stopped.

#### Scenario: Headless start
- **WHEN** PaperDaemon starts with `--headless`
- **THEN** no window opens and the API answers paired clients

### Requirement: The window opens where it was
The shell SHALL remember the window's position, size and whether it was maximized whenever the user moves, sizes or
maximizes it, and SHALL open the window so next time, an update's restart included. A remembered place that lies on
no screen any more SHALL be ignored, and the window SHALL open as it would without one.

#### Scenario: An update restarts PaperDaemon
- **WHEN** the window stood on a second monitor at the user's own size and PaperDaemon restarts after an update
- **THEN** the window opens on that monitor at that size

#### Scenario: The monitor is gone
- **WHEN** the remembered place was on a monitor that is no longer attached
- **THEN** the window opens at its ordinary size on the main screen

### Requirement: The UI opens on the screen and in the folder it showed
The UI SHALL remember the screen it was showing and, on the Mirror and False Mirror screens, the folder it was in, and
SHALL open there next time when nothing in the window's address says where to open. An address that names a screen,
a folder or a document SHALL win over what is remembered. The setup and pairing screens SHALL never be remembered.
What the window keeps for itself between starts (the screen, the folder, a list's page size, a note seen) SHALL be
kept by the engine in its data folder, read once as the window boots and written as it changes, never in the web
view's own storage: that storage does not survive a restart in every install.

#### Scenario: The web view's storage comes back empty
- **WHEN** the web view's own storage has lost everything over a restart
- **THEN** the window still opens on the remembered screen and in the remembered folder

#### Scenario: The False Mirror's Dogfood folder
- **WHEN** the window last showed the False Mirror inside the Dogfood folder and PaperDaemon restarts
- **THEN** the window opens on the False Mirror inside the Dogfood folder

#### Scenario: A link straight to a document
- **WHEN** the window is opened by an address that names a document
- **THEN** that document opens, whatever screen and folder were remembered
