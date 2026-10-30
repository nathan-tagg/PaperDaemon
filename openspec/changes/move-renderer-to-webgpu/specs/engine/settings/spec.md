## ADDED Requirements

### Requirement: The renderer is chosen in Settings
Settings SHALL offer a Renderer row with two tick boxes, GPU (ticked by default) and CPU, one of them ticked at a
time. With GPU ticked, a list SHALL name the machine's graphics cards and the one pages are drawn on; it SHALL
start on the card with Direct3D 12 that has the most memory of its own. A card in the list that cannot run WebGPU
at all SHALL show a "!" beside the list, whose hover says that card cannot run WebGPU and pages will be drawn on
the processor, which is slower. A card that runs WebGPU only in its compatibility mode (Direct3D 11) SHALL show
nothing. With CPU ticked, the engine SHALL draw its pages on the processor. The card chosen SHALL be used by the
engine from its next job and by the window from the next time PaperDaemon starts.

#### Scenario: Two cards
- **WHEN** the user opens Settings on a machine with a discrete card and an integrated one, both with Direct3D 12
- **THEN** Renderer has GPU ticked, and the list shows the discrete card, the one with more memory of its own

#### Scenario: A card without WebGPU
- **WHEN** the user picks a card in the list that has neither Direct3D 12 nor Direct3D 11
- **THEN** a "!" appears beside the list, and its hover says pages will be drawn on the processor
