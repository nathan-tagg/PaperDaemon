# Spec Delta

## Purpose

Turns the user's handwriting on a reMarkable page into words with their positions, on this computer,
so the host knows what was written and where, whether or not the text model can see.

## ADDED Requirements

### Requirement: Ink becomes lines of words with positions
The reader SHALL turn a page's handwritten ink into lines of text, each with its words and each word's
bounding box in page coordinates, ordered top to bottom and left to right.

#### Scenario: A handwritten question
- **WHEN** the reader reads a page holding one handwritten line, "what year did the war end"
- **THEN** it returns that line's words, each with a box that encloses its ink on the page

### Requirement: Reading happens on this computer
Every reader engine SHALL read on this computer and SHALL NOT send a page image or ink to any other
host.

#### Scenario: Reading while offline
- **WHEN** the computer has no network and a page is read
- **THEN** the reader returns the page's words as it does online

### Requirement: One interface, a choice of engines
PaperDaemon SHALL read through one reader interface with interchangeable engines. The settings SHALL let
the user pick an engine from those available on this computer, and SHALL default to the best available
one.

#### Scenario: Windows
- **WHEN** PaperDaemon runs on Windows with the default settings
- **THEN** the Windows OCR engine reads handwriting

### Requirement: Windows OCR is the bar
Every engine SHALL be measured on the project's handwriting test set, for word error rate and time per
page on the CPU, beside Windows OCR on the same pages. On each platform the default engine SHALL be the
most accurate one available that adds no more than a few seconds per page, and the reader settings
SHALL show each engine's measured numbers.

#### Scenario: A better engine on Windows
- **WHEN** a portable engine measures a lower word error rate than Windows OCR and reads a page in a
  few seconds on the CPU
- **THEN** it becomes the Windows default, and Windows OCR stays available as the engine that needs no
  download

#### Scenario: A platform without Windows OCR
- **WHEN** PaperDaemon runs on Linux, where only a portable engine is available
- **THEN** that engine is the default, and the settings show its numbers beside Windows OCR's

### Requirement: The host keeps working without a reader
When no reader engine is available, the host SHALL still run jobs from the page's typed text, and from
the page image when the text model can see. The job's record SHALL say that handwriting was not read.

#### Scenario: No engine on this system
- **WHEN** no reader engine is available and a handwritten page is tagged
- **THEN** the job runs, and its record says handwriting was not read

### Requirement: Typed text is never read by the reader
The reader SHALL read only ink. Typed text SHALL come to the host exactly as the page file holds it.

#### Scenario: A page with typed and handwritten lines
- **WHEN** a page holds a typed paragraph and a handwritten line
- **THEN** the host gets the typed paragraph from the file, character for character, and only the
  handwritten line from the reader
