# Architecture Decision Log

Use this file to record decisions that would otherwise be lost between development sessions.

Format:

## YYYY-MM-DD — Decision title

**Decision:**

**Reason:**

**Alternatives considered:**

**Consequences:**

## 2026-09-22 — Desktop UI stack: GTK 3 via PyGObject, with Ayatana AppIndicator for the tray

**Decision:**
The graphical interface is GTK 3 accessed from Python through PyGObject (`gi`), and the Ubuntu MATE tray icon uses the `AyatanaAppIndicator3` GObject-Introspection namespace. This confirms the stack already suggested in `README.md` and `specs/04-roadmap.md` (Phase 6); it is recorded here so it is not re-litigated.

**Reason:**
- MATE is a GTK 3 desktop, so GTK 3 is the native toolkit for the target platform and needs no extra runtime.
- The whole stack is already present on the development machine as distribution packages (see Consequences), so Phase 6 requires no installation step.
- PyGObject exposes both the window toolkit and the tray indicator through one binding, so there is no second GUI dependency.

**Alternatives considered:**
- *GTK 4* — not available on this machine (`Gtk 4.0` namespace is absent; only 3.24.41 is installed) and not the MATE-native version. Would require pulling in a newer toolkit for no benefit to a province-map view.
- *Legacy `AppIndicator3` (Canonical libappindicator)* — the namespace is **not** installed here; Ubuntu 24.04 ships the Ayatana fork instead. Code must require `AyatanaAppIndicator3`, not `AppIndicator3`.
- *Qt/PySide, Tk, or a web UI* — would add a large dependency, and a browser/Electron shell conflicts with the low-attention, tray-resident design pillar in `specs/00-project-brief.md`.

**Consequences:**
- No installation is required for development on this machine. Verified present:
  - `python3-gi` 3.48.2 (PyGObject, `gi` importable from system `python3` 3.12.3)
  - `gir1.2-gtk-3.0` / `libgtk-3-0t64` 3.24.41-4ubuntu1.3 (`Gtk 3.0` namespace imports)
  - `gir1.2-ayatanaappindicator3-0.1` 0.5.93-1build3 (`AyatanaAppIndicator3 0.1` namespace imports)
  - Session is `XDG_CURRENT_DESKTOP=MATE`, `XDG_SESSION_TYPE=x11`.
- On a fresh machine the equivalent is:
  `sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1`
- **PyGObject is a system dist-package, not a wheel.** A plain `python3 -m venv` cannot see it (`ModuleNotFoundError: No module named 'gi'`). Any virtualenv used for UI work must be created with `python3 -m venv --system-site-packages` (verified working). A plain venv is fine for headless simulation and test work.
- `ui/` code must pin namespace versions with `gi.require_version(...)` before importing from `gi.repository`, and must stay import-isolated from the simulation core per `architecture.md`.
