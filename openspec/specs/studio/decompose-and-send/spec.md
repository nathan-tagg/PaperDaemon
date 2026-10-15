# studio/decompose-and-send Specification

## Purpose
Lets the user turn any image into pen strokes and send it to the tablet from the desktop app, as a new
page of the inbox notebook, without writing a request on a page.

## Requirements

### Requirement: Drop an image, see its strokes
The screen SHALL accept an image by dropping it or choosing a file, decompose it at the size the user
set, and show a preview of the strokes as the tablet will draw them, with the stroke count. The size
SHALL be from 200 to 1,400 of the page's pixels, 1,200 by default, clamped to what fits in the page's
safe area below the caption.

#### Scenario: Dropping a photo
- **WHEN** the user drops a photo on the screen
- **THEN** the preview shows the photo as strokes and the number of strokes

#### Scenario: A smaller size
- **WHEN** the user sets the size to 600 and drops an image
- **THEN** the strokes fit a 600-pixel square centered on the page

### Requirement: Sending adds a page to the inbox notebook
Sending SHALL append one new page to the inbox notebook named in the settings, holding a small caption
(the image's file name, the seconds the decomposing took, the date and time) with the strokes below
it. Sending SHALL NOT change any existing page.

#### Scenario: A second picture
- **WHEN** the inbox notebook has three pages and the user sends an image
- **THEN** the notebook has a fourth page holding the caption and the strokes, and its other pages are
  unchanged

### Requirement: The first send makes the inbox
When no notebook matches the inbox path, or only one in the trash does, sending SHALL create the
notebook, and any folder on its path that is missing. When two notebooks (or folders) on the path share a name,
sending SHALL use the one made first, and SHALL NOT be refused.

#### Scenario: A fresh tablet
- **WHEN** the inbox is set to "Projects/Coloring inbox", there is no "Projects" folder, and the user sends an
  image
- **THEN** the "Projects" folder and the "Coloring inbox" notebook are created, holding one page

#### Scenario: Two notebooks with the inbox's name
- **WHEN** two notebooks named "PaperDaemon inbox" sit at the top level and the user sends an image
- **THEN** the page goes to the one made first

### Requirement: The inbox is never answered as a job
The daemon SHALL dispatch no page of the inbox notebook, whatever tags it or its folders carry. The inbox SHALL
NOT need an ignore tag, and sending SHALL add none.

#### Scenario: A sent picture comes back from the tablet
- **WHEN** a sent page syncs back from the tablet inside a folder that carries a watched tag
- **THEN** the daemon dispatches no job for it

### Requirement: The image is not kept
PaperDaemon SHALL hold a dropped image and its preview in memory only and SHALL release them when the image is
sent or the user leaves the screen. The decomposer reads its picture from a temporary file in the data folder's
`tmp`, removed as soon as the strokes are made; nothing else is written.

#### Scenario: After sending
- **WHEN** the user sends an image and leaves the screen
- **THEN** no copy of the image or its preview exists in PaperDaemon's data folder
