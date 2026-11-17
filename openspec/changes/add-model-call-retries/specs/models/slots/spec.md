## ADDED Requirements

### Requirement: A model away from this computer is asked again when it is busy
A text or image slot whose model is reached over the network with an API key (not served on this computer, not started
by a start script, not a command line) SHALL have two settings: Wait for a reply, the seconds one call waits for its
reply (blank or 0: as long as the model takes), and Retries, how many more times the call is made (0 to 20; 3 unless
set). A busy answer (HTTP 429, 502, 503, 504 or 529) or no reply within the wait SHALL be asked again, after a pause:
the time the server asked for, else 5, 10, 20, 40 and then 60 seconds. Any other answer SHALL be the call's answer.
Models on this computer and command lines SHALL keep no wait and no retries of PaperDaemon's.

#### Scenario: A busy server answers on a later try
- **WHEN** a job's call to a hosted model is answered 503 "high demand", then answers on the next try
- **THEN** the job goes on with that answer, and is not skipped

#### Scenario: The server says how long to wait
- **WHEN** a hosted model answers 429 with Retry-After 7
- **THEN** PaperDaemon waits 7 seconds before asking again

#### Scenario: A request the server refuses
- **WHEN** a hosted model answers 400
- **THEN** it is not asked again

#### Scenario: A local model
- **WHEN** a slot's model is served at this computer's address and has Retries set
- **THEN** its calls wait as long as it takes and are not repeated
