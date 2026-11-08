## ADDED Requirements

### Requirement: A game turn leaves the job's instructions in the text model's memory
After a game turn (chess, the adventure, the messages, talk after a match), the host SHALL send the text model one
request holding a job's own system message and tools, one token out, in the background once the turn is done, so the
model's memory (a llama.cpp slot, and what a start script saves of it across a picture swap) holds PaperDaemon's
instructions again and the next job does not read them cold. It SHALL be sent only to a server on this computer that
says it keeps slots; a hosted model SHALL never be sent a request of PaperDaemon's own.

#### Scenario: A job after an adventure turn that painted a picture
- **WHEN** an adventure turn paints its scene (the image script saves the text model's memory) and a normal job comes
  next
- **THEN** the job's first turn finds PaperDaemon's instructions already read

#### Scenario: A hosted text model
- **WHEN** the lineup's text model is a hosted API
- **THEN** no request is sent after a game turn
