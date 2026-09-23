# Style Auto Plugin - Regression tests for style_auto_plugin.py (run())
#
# These tests require a real QGIS Python environment because
# style_auto_plugin.py imports qgis.gui.QgsMapLayerComboBox, among others.
#
#   "C:\Program Files\QGIS 3.44.9\bin\python-qgis-ltr.bat" -m pytest tests -v
import json
import types

import pytest


class _FakeSignal:
    """Replaces QgsMapCanvas.renderComplete without requiring a real Qt signal object."""

    def connect(self, slot):
        pass

    def disconnect(self, slot):
        pass


class _FakeCanvas:
    renderComplete = _FakeSignal()


class _FakeMessageBar:
    def __init__(self):
        self.messages = []

    def pushMessage(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class _FakeIface:
    def __init__(self):
        self._message_bar = _FakeMessageBar()
        self._canvas = _FakeCanvas()

    def messageBar(self):
        return self._message_bar

    def mapCanvas(self):
        return self._canvas


class _FakeLayerCombo:
    def __init__(self, layer):
        self._layer = layer

    def currentLayer(self):
        return self._layer


@pytest.fixture
def plugin_with_isolated_config(qgis_app, tmp_path, monkeypatch):
    """Build a StyleAutoPlugin instance whose style_config.json lives in a tmp folder
    so tests run independently from the real config file in the plugin directory."""
    from style_auto_plugin.style_auto_plugin import StyleAutoPlugin
    import style_config

    # Minimally valid config file for the constructor (get_config() during __init__).
    base_config_path = tmp_path / "style_config.json"
    base_config_path.write_text(json.dumps({}), encoding="utf-8")

    # style_auto_plugin.py imports get_config directly ("from .style_config import get_config"),
    # so the name must be patched in the style_auto_plugin module itself.
    from style_auto_plugin import style_auto_plugin as sap_module

    def _fake_get_config():
        return style_config._parse_plugin_config({}), None

    monkeypatch.setattr(sap_module, "get_config", _fake_get_config)
    monkeypatch.setattr(sap_module.style_config, "get_config", _fake_get_config)

    plugin = StyleAutoPlugin(_FakeIface())
    plugin.plugin_dir = str(tmp_path)
    return plugin


def _run_with_recorded_config(plugin, layer):
    """Run plugin.run() and return the config passed to apply_best_style()."""
    recorded = {}

    def _fake_apply_best_style(layer, config, plugin_dir=None):
        recorded["config"] = config
        return {"success": True, "message": "ok"}

    plugin.engine.apply_best_style = _fake_apply_best_style
    plugin.layer_combo = _FakeLayerCombo(layer)
    plugin.run()
    return recorded.get("config")


# ----------------------------------------------------------------------
# Regression test for the bug fix: enable_advanced_*_features were written to
# the JSON file (open_config()) but never read back in run(). As a result,
# style_engine.py always used the getattr(..., True) default, regardless of
# what the user selected in the GUI base toggles for roads, buildings, and points.
# ----------------------------------------------------------------------

def test_run_reads_advanced_road_features_false_from_json(plugin_with_isolated_config, monkeypatch):
    import os

    plugin = plugin_with_isolated_config
    json_path = os.path.join(plugin.plugin_dir, "style_config.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"enable_advanced_road_features": False}, f)

    config = _run_with_recorded_config(plugin, layer=object())

    assert config.enable_advanced_road_features is False


def test_run_reads_advanced_road_features_true_from_json(plugin_with_isolated_config):
    import os

    plugin = plugin_with_isolated_config
    json_path = os.path.join(plugin.plugin_dir, "style_config.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"enable_advanced_road_features": True}, f)

    config = _run_with_recorded_config(plugin, layer=object())

    assert config.enable_advanced_road_features is True


def test_run_reads_advanced_building_and_point_features_from_json(plugin_with_isolated_config):
    import os

    plugin = plugin_with_isolated_config
    json_path = os.path.join(plugin.plugin_dir, "style_config.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "enable_advanced_building_features": False,
            "enable_advanced_point_features": False,
        }, f)

    config = _run_with_recorded_config(plugin, layer=object())

    assert config.enable_advanced_building_features is False
    assert config.enable_advanced_point_features is False


def test_run_defaults_advanced_features_to_true_without_json_keys(plugin_with_isolated_config):
    import os

    plugin = plugin_with_isolated_config
    json_path = os.path.join(plugin.plugin_dir, "style_config.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({}, f)

    config = _run_with_recorded_config(plugin, layer=object())

    assert config.enable_advanced_road_features is True
    assert config.enable_advanced_building_features is True
    assert config.enable_advanced_point_features is True
