# Tasks

## 1. The window

- [x] 1.1 The shell keeps the window's position, size and maximized state in a file of its own (placement.json beside
      its data) on every move, size and maximize, and opens the window so; a place on no screen is ignored (0.2.36;
      on his machine 11-09: a nudge and the move back were both recorded, and the 0.2.37 restart opened at his place)

## 2. The screen and the folder

- [x] 2.1 The UI keeps the screen shown (never setup or pairing) and the folder of each library screen, and opens there
      when the address names nothing (0.2.36)
- [x] 2.2 On his machine after the next update: the window back on his monitor at his size, the False Mirror open in
      the Dogfood folder, with no hand (0.2.37 came back on the Overview: 2.3; the 0.2.38 update, 11-09 12:3x: the
      window at -1447,-1063 1454x1727, the False Mirror inside Dogfood, nothing touched)
- [x] 2.3 The UI's memory lives on the engine (ui_memory.py, GET/PUT /ui/memory; PD.memory, PD.remember), not in the
      web view's storage: on his machine that store's log drops its tail at every restart ("Corruption: checksum
      mismatch ... dropping 8247 bytes", then "Reusing old log") and so forgets everything written since; the screen,
      the folder, the Decompose page size and the settings note moved; the language and the zoom still sit in the web
      view's storage (read before the engine answers; defaults on his machine)
