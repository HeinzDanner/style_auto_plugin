# Style Auto Plugin

[![Tests](https://github.com/HeinzDanner/style_auto_plugin/actions/workflows/tests.yml/badge.svg)](https://github.com/HeinzDanner/style_auto_plugin/actions/workflows/tests.yml)

*A QGIS Python plugin that automatically applies categorized styling for roads, buildings, land use, and POIs to the active vector layer, driven by a JSON rule configuration and a PyQt settings dialog.*

Style Auto Plugin is a QGIS Python plugin that automatically applies categorized styling to the currently active layer.

Styling rules are loaded efficiently from the configuration. Rulesets are selected by layer name, geometry type, field name, and priority. For values that are not explicitly configured, an optional fallback style can be applied.

## Project Context

This was my first Python project and my first hands-on work with a GIS API (QGIS/PyQt). My background is Java/JVM, so the goal here was to get comfortable with a new language and ecosystem while still applying the engineering habits I use professionally: writing tests against real objects instead of trusting manual clicking, tracking down root causes instead of patching symptoms, and keeping a clean, reviewable commit history.

Several rounds of real-world testing surfaced concrete bugs (checkboxes silently not wired to the logic they were supposed to control, wrong QGIS API method names, config values read in one place but never in another). Each one was fixed with a regression test added alongside it — the `tests/` suite grew out of that process rather than being planned upfront.

## How It Works

The plugin is essentially a small rule engine, not a fixed set of hardcoded styles:

```text
Active layer
   │
   ▼
score_match()          -> scores every configured layer/profile ruleset against the
                           layer's geometry type, name, and field names/values
   │
   ▼
find_layer_ruleset() /
find_style_profile()  -> picks the highest-priority ruleset whose match score clears
                           its configured minimum threshold
   │
   ▼
get_matching_field_ruleset() -> within that ruleset, picks the best-matching field
                                 (by name hints, priority, and detected values)
   │
   ▼
apply_categorized_renderer_with_fallback()
   │                   -> builds a QGIS categorized renderer: one QGIS symbol per
   │                      configured value, with an optional fallback style for any
   │                      value that has no explicit rule
   ▼
Styled layer + (Mode 1/2 only) optional road/building/land-use/label refinements
```

Everything above the QGIS-symbol level is driven entirely by `style_rules.json` /
`style_config.json` — adding a new layer type or value mapping is a config change,
not a code change. The interesting/non-trivial part is the scoring and priority
logic in `score_match()`, `find_layer_ruleset()`, and `find_style_profile()`
(`style_engine.py`), which lets the plugin guess the right ruleset for a layer
even when layer and field names don't match exactly.

## Features

- Automatic selection of the most suitable layer ruleset.
- Priority-based selection of the appropriate field ruleset.
- Three global styling modes (Mode 0, 1, and 2).
- Six optional cartographic settings exposed through the GUI.
- Field-based categorized symbology.
- Duplicate-safe automatic symbol import for testing.
- Fast in-memory caching to avoid repeated disk scans.
- Optional fallback styling for unconfigured values.
- A robust, quiet core without excessive log output.

## Requirements

- QGIS 3.28 or newer, including QGIS 4.x (PyQt6)
- A valid configuration file in the plugin directory

## Plugin Structure

The plugin follows the standard QGIS Python plugin layout, including the extended `styles` resource directory.

```text
style_auto_plugin/
├── __init__.py
├── LICENSE
├── README.md
├── main.py
├── metadata.txt
├── style_auto_plugin.py
├── style_auto_plugin_dialog.py
├── style_config.py
├── style_engine.py
├── style_rules.json
└── styles/
    ├── style_symbols.xml
    ├── roads_fclass.qml
    └── hospital.svg
```

## Installation

### Local Installation

1. Copy the `style_auto_plugin` folder into your local QGIS plugin directory.
2. Restart QGIS.
3. Enable the plugin in the Plugin Manager.

Typical plugin directory on Windows:

```text
C:\Users\<Username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins
```

### Installation from ZIP

1. Package the complete `style_auto_plugin` folder as a ZIP archive.
2. In QGIS, open `Plugins` -> `Manage and Install Plugins...`.
3. Choose `Install from ZIP`.
4. Select the ZIP file and install it.

## Configuration

Rules are loaded from the configuration file by default. The settings window automatically synchronizes tester changes with the local JSON file on each user's machine.

## Tests

The `tests/` directory contains a pytest suite:

- `test_style_config.py` validates only the parsing and coercion logic in `style_config.py` and can run with any regular Python interpreter, as long as `pytest` is installed. These tests also run in GitHub Actions CI (see the badge above).
- `test_style_engine.py` and `test_style_auto_plugin.py` verify the actual styling logic functionally using real in-memory QGIS layers and therefore require the QGIS Python interpreter (`qgis.core`). They are intended for local execution, not CI, because no QGIS runtime image is available there.

Run on Windows, for example, with:

```text
"C:\Program Files\QGIS 3.44.9\bin\python-qgis-ltr.bat" -m pip install pytest
"C:\Program Files\QGIS 3.44.9\bin\python-qgis-ltr.bat" -m pytest tests -v
```

The suite (54 tests) is verified green on both QGIS 3.44 (PyQt5) and QGIS 4.2.2 (PyQt6); on QGIS 4 use `python-qgis.bat` instead of `python-qgis-ltr.bat`:

```text
"C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" -m pip install pytest
"C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" -m pytest tests -v
```

## Usage

1. Load a suitable vector layer in QGIS.
2. Select the desired layer in the legend.
3. Start the plugin from the user interface.
4. Choose the desired global styling mode.
5. Enable any cartographic options you want to use (shadow, smoothing, and so on).
6. Close the window—the style is applied silently and immediately to the configured field.

## Behavior for Missing Values

If the layer contains values for which no explicit rule exists, two cases are possible:

- If a fallback style is defined, that style is used.
- If no fallback style is defined, Mode 1 catches those values with a universal fallback entry.

## Current Status

This plugin is currently a working MVP focused on automated, configurable, and user-driven symbology.

## Known Limitations

- Symbol construction is tailored to the current implementation.

## Planned Expansion

- Additional predefined example configurations.

## Lessons Learned / What I'd Do Differently

Coming from Java, a few things stand out in hindsight that I would design differently on a from-scratch rewrite:

- **State duplication:** boolean settings (e.g. "enable building labels") ended up tracked in three places at once — a class attribute on `StyleEngine`, an instance attribute, and a key in the JSON config dict — synced by ad-hoc helper methods. This caused several of the bugs found during testing (a checkbox reacting to the wrong setting, a toggle only working while the settings dialog was open). In Java I would have modeled this as a single immutable config object passed explicitly through the call chain from the start; here it was retrofitted after the fact via a shared `_get_attr()` accessor instead of eliminating the duplication outright.
- **Module size:** `style_engine.py` grew to roughly 2,400 lines covering roads, buildings, land use, and points in one file/class. A cleaner design would split this into one strategy per geometry/feature type (roads, buildings, land use, points), similar to a Strategy or Visitor pattern in Java, instead of one large method with mode/geometry branching.
- **Defensive "kill switch" guards:** several features had multiple redundant early-return guards added independently over time (sometimes three separate places blocking the same code path for the same condition). Consolidating a boolean's effect into exactly one place would have prevented the "toggle off breaks something else entirely" class of bugs I ran into.
- **Testing came later than it should have:** the pytest suite (54 tests, using real in-memory QGIS layers) was added after the initial feature set existed, once bugs from manual testing started piling up. Writing tests alongside the first working version — even a handful — would have caught the API-name bug (`setJoinStyle`/`setCapStyle` don't exist on `QgsSimpleLineSymbolLayer`; the real methods are `setPenJoinStyle`/`setPenCapStyle`) immediately instead of after real-world use.

## License

This plugin is licensed under the GNU General Public License v2.0 or later (GPL-2.0-or-later). The full license text is available in the `LICENSE` file.