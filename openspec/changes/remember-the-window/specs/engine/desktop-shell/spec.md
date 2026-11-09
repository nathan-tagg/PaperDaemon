## ADDED Requirements

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

#### Scenario: The False Mirror's Dogfood folder
- **WHEN** the window last showed the False Mirror inside the Dogfood folder and PaperDaemon restarts
- **THEN** the window opens on the False Mirror inside the Dogfood folder

#### Scenario: A link straight to a document
- **WHEN** the window is opened by an address that names a document
- **THEN** that document opens, whatever screen and folder were remembered
