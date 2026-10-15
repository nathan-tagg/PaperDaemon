# Tasks

## 1. Interface and registry

- [x] 1.1 Write the tool declaration and action interface and the registry; verify with a test tool that the host offers it without host changes Superseded by the feature catalog (`pipeline/features.py`, facelift 5.2-5.4 and 4.3): each feature declares its steps and tools and what it needs; what is off is not offered and its steps are refused with the reason; the Lineup's Tests tab shows what a lineup can do.
- [x] 1.2 Generate the brief's tool section and the plan tool's schema from the tools on offer; verify the static part stays byte-identical when the tool set is unchanged Superseded by the feature catalog (`pipeline/features.py`, facelift 5.2-5.4 and 4.3): each feature declares its steps and tools and what it needs; what is off is not offered and its steps are refused with the reason; the Lineup's Tests tab shows what a lineup can do.
- [x] 1.3 Offer a tool only when its needs are met and its switch is on; verify with each missing capability Superseded by the feature catalog (`pipeline/features.py`, facelift 5.2-5.4 and 4.3): each feature declares its steps and tools and what it needs; what is off is not offered and its steps are refused with the reason; the Lineup's Tests tab shows what a lineup can do.

## 2. Built-in tools and outside-world rule

- [x] 2.1 Move the drawing and search tools behind the interface; verify the host's case table passes unchanged Superseded by the feature catalog (`pipeline/features.py`, facelift 5.2-5.4 and 4.3): each feature declares its steps and tools and what it needs; what is off is not offered and its steps are refused with the reason; the Lineup's Tests tab shows what a lineup can do.
- [x] 2.2 Gate outside-world tools with the explicit-direction check and keep them off by default; verify with a test tool that a loose match does not run it Superseded by the feature catalog (`pipeline/features.py`, facelift 5.2-5.4 and 4.3): each feature declares its steps and tools and what it needs; what is off is not offered and its steps are refused with the reason; the Lineup's Tests tab shows what a lineup can do.
- [x] 2.3 Build the capabilities screen with needs, switches and the outside-world mark; verify by rendering it headless Superseded by the feature catalog (`pipeline/features.py`, facelift 5.2-5.4 and 4.3): each feature declares its steps and tools and what it needs; what is off is not offered and its steps are refused with the reason; the Lineup's Tests tab shows what a lineup can do.

## 3. Real-run evidence

- [ ] 3.1 With the maintainer's go-ahead, run the host's dogfood cases with the tools behind the interface and record that results match the run before the move
