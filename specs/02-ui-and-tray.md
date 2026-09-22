# UI and Tray Specification

## Tray behavior
Closing the main window returns the game to the system tray instead of exiting.

Suggested tray summary:

- current simulated date
- player faction
- territory percentage
- manpower
- treasury
- war support
- front summaries
- latest major event

Suggested actions:

- Open War Room
- Pause/Resume
- Simulation Speed
- Front Priorities
- National Policy
- Save
- Quit

## Main window
Initial tabs/panels:

1. Strategic Map
2. Fronts
3. Faction Overview
4. Economy
5. Military
6. History
7. Policies
8. Settings

## Map
First prototype may use rectangles, a grid, or simple province polygons.

Map must communicate:

- owner
- contested state
- armies
- front lines
- capitals
- supply problems

Do not delay simulation development for sophisticated map graphics.

## Notifications
Only surface events that matter.

Priority examples:

- capital lost
- front collapse
- army encircled
- peace signed
- declaration of war
- civil war
- severe supply crisis

Notifications should be configurable later.
