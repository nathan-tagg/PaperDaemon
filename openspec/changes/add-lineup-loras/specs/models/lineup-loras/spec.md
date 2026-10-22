# Spec Delta

## ADDED Requirements

### Requirement: Each lineup has a LoRA folder
PaperDaemon SHALL keep a LoRA folder for each lineup, open it from a link under the image model's start script, and
give the lineup's start scripts its path in `PAPERDAEMON_LORAS`. A renamed lineup SHALL keep its folder.

#### Scenario: Renaming a lineup
- **WHEN** a lineup with LoRAs in its folder is renamed
- **THEN** its LoRAs are in the folder of its new name

### Requirement: The harness says how they are applied
Every picture a lineup makes SHALL carry the LoRAs in its folder, applied as its image harness's `loras` says: in the
request's list (`"request"`) or as prompt tags (`"prompt"`), at its strength. A harness that says nothing SHALL apply
none, and the job SHALL report them left out. A LoRA the server does not list SHALL be left out and reported.

#### Scenario: Two LoRAs on Z-Image
- **WHEN** a lineup on Z-Image Turbo has two LoRAs in its folder and makes a picture
- **THEN** the request names both, each at the harness's strength

#### Scenario: A server that does not load the folder
- **WHEN** the server's own list does not name the folder's LoRAs
- **THEN** the picture is made without them and the job's log names them
