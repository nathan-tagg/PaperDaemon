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
