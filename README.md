# Style Auto Plugin

[![Tests](https://github.com/HeinzDanner/style_auto_plugin/actions/workflows/tests.yml/badge.svg)](https://github.com/HeinzDanner/style_auto_plugin/actions/workflows/tests.yml)

*A QGIS Python plugin that automatically applies categorized styling for roads, buildings, land use, and POIs to the active vector layer, driven by a JSON rule configuration and a PyQt settings dialog.*

Style Auto Plugin is a QGIS Python plugin that automatically applies categorized styling to the currently active layer.

Styling rules are loaded efficiently from the configuration. Rulesets are selected by layer name, geometry type, field name, and priority. For values that are not explicitly configured, an optional fallback style can be applied.

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

- QGIS 3.28 or newer
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

## License

This plugin is licensed under the GNU General Public License v2.0 or later (GPL-2.0-or-later). The full license text is available in the `LICENSE` file.