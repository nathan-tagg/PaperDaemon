# Spec Delta

## Purpose

Lets two local model servers that cannot fit on the graphics card together take turns, with PaperDaemon
starting and stopping the servers it launched as each job step needs them.

## ADDED Requirements

### Requirement: Hot swapping is offered only for two local slots
The models screen SHALL offer the hot swapping switch only when both slots run on this computer, and
SHALL require a launch script for each slot before hot swapping can be turned on. The switch SHALL come
with a plain notice that other programs using the graphics card can leave too little memory for a
model to load.

#### Scenario: The notice
- **WHEN** the user turns hot swapping on
- **THEN** the screen says that other programs using the graphics card can stop a model from loading

#### Scenario: One slot is remote
- **WHEN** the image slot points at a cloud provider
- **THEN** the hot swapping switch is not offered

#### Scenario: A launch script is missing
- **WHEN** both slots are local but the image slot has no launch script and the user turns hot swapping on
- **THEN** nothing is saved and the answer says the image slot needs a launch script

### Requirement: Start scripts are editable in the UI
Each local slot SHALL have a start script, editable as text on the lineup's screen and stored with the settings,
and PaperDaemon SHALL run it as written on this computer. There SHALL be no stop script: PaperDaemon ends the
server a start script started by ending that script's process and everything it started; any other stopping
(another program's server holding the graphics card) is the script's to do.

#### Scenario: Editing a launch argument
- **WHEN** the user changes a context-size argument in the text slot's start script and saves
- **THEN** the next start of the text server uses the changed script

### Requirement: The needed server is brought up before a step
With hot swapping on, before a job step uses a slot whose server is not answering, PaperDaemon SHALL stop
the other slot's server if PaperDaemon started it, then run this slot's launch script, and wait until the
server answers. The wait SHALL last as long as the server process is alive; if the process exits
before answering, the step SHALL fail with the process's exit reported.

#### Scenario: A picture during a text job
- **WHEN** a job needs a picture while the text server PaperDaemon started holds the card
- **THEN** PaperDaemon stops the text server, starts the image server, waits until it answers, and makes the picture

#### Scenario: The image server crashes while loading
- **WHEN** the image server's process exits before it ever answers
- **THEN** the step fails, and the job reports that the image server stopped while loading

### Requirement: PaperDaemon stops only what it started
PaperDaemon SHALL stop only processes it started itself, identified by the process it launched and that
process's children, and SHALL NOT stop any other process, whatever its name or port.

#### Scenario: The user's own server holds the port
- **WHEN** a server PaperDaemon did not start is answering on the other slot's port
- **THEN** PaperDaemon leaves it running, and the step reports that a server it did not start is in the way

### Requirement: The text server comes back after a job
With hot swapping on, when a job ends with the image server up, PaperDaemon SHALL bring the text server
back up, so that the next job can start at once.

#### Scenario: After a coloring page
- **WHEN** a job that made a coloring page finishes
- **THEN** PaperDaemon stops the image server it started and starts the text server

### Requirement: The user can start and stop local servers
The models screen SHALL show whether each local slot's server is answering and whether PaperDaemon started
it, and SHALL let the user start or stop a server PaperDaemon launched.

#### Scenario: Freeing the card by hand
- **WHEN** the user stops the text server PaperDaemon started
- **THEN** that server process and its children end, and the screen shows the slot as stopped

### Requirement: Servers PaperDaemon started end with PaperDaemon
When PaperDaemon exits, every server process it started SHALL end with it, including when PaperDaemon crashes.

#### Scenario: PaperDaemon is closed
- **WHEN** the user quits PaperDaemon while a server it started is loaded
- **THEN** that server's processes are gone and the card's memory is free

### Requirement: With hot swapping off, PaperDaemon leaves servers alone
With hot swapping off, PaperDaemon SHALL NOT start or stop any model server on its own; it SHALL use the
endpoints as they are and report a slot that does not answer.

#### Scenario: A server the user runs by hand
- **WHEN** hot swapping is off and the text server is not running when a job starts
- **THEN** the job fails with "the text model is not answering", and PaperDaemon starts nothing
