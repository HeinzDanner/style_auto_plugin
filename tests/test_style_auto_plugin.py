# Style Auto Plugin - Regressionstests für style_auto_plugin.py (run())
#
# Diese Tests benötigen eine echte QGIS-Python-Umgebung, da style_auto_plugin.py
# u.a. qgis.gui.QgsMapLayerComboBox importiert.
#
#   "C:\Program Files\QGIS 3.44.9\bin\python-qgis-ltr.bat" -m pytest tests -v
import json
import types

import pytest


class _FakeSignal:
    """Ersetzt QgsMapCanvas.renderComplete, ohne eine echte Qt-Signal-Instanz zu brauchen."""

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
    """Baut eine StyleAutoPlugin-Instanz, deren style_config.json in einem tmp-Ordner liegt,
    damit Tests unabhängig von der echten Konfigurationsdatei im Plugin-Verzeichnis laufen."""
    from style_auto_plugin.style_auto_plugin import StyleAutoPlugin
    import style_config

    # Minimal gültige Konfigurationsdatei für den Konstruktor (get_config() beim __init__).
    base_config_path = tmp_path / "style_config.json"
    base_config_path.write_text(json.dumps({}), encoding="utf-8")

    # style_auto_plugin.py importiert get_config direkt ("from .style_config import get_config"),
    # daher muss der Name im style_auto_plugin-Modul selbst gepatcht werden.
    from style_auto_plugin import style_auto_plugin as sap_module

    def _fake_get_config():
        return style_config._parse_plugin_config({}), None

    monkeypatch.setattr(sap_module, "get_config", _fake_get_config)
    monkeypatch.setattr(sap_module.style_config, "get_config", _fake_get_config)

    plugin = StyleAutoPlugin(_FakeIface())
    plugin.plugin_dir = str(tmp_path)
    return plugin


def _run_with_recorded_config(plugin, layer):
    """Führt plugin.run() aus und gibt die Config zurück, mit der apply_best_style() aufgerufen wurde."""
    recorded = {}

    def _fake_apply_best_style(layer, config, plugin_dir=None):
        recorded["config"] = config
        return {"success": True, "message": "ok"}

    plugin.engine.apply_best_style = _fake_apply_best_style
    plugin.layer_combo = _FakeLayerCombo(layer)
    plugin.run()
    return recorded.get("config")


# ----------------------------------------------------------------------
# Regressionstest für den Bugfix: enable_advanced_*_features wurden aus der
# JSON-Datei geschrieben (open_config()), aber in run() nie wieder eingelesen.
# Dadurch griff in style_engine.py immer der getattr()-Default True, egal was
# der Nutzer in der GUI (Straßen-/Gebäude-/Punkt-"Basis"-Haken) eingestellt hatte.
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
