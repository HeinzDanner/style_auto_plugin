# Style Auto Plugin - Funktionale Tests für style_engine.py
#
# Diese Tests benötigen eine echte QGIS-Python-Umgebung (qgis.core), da sie
# reale QgsVectorLayer-Instanzen anlegen und Renderer/Labeling prüfen.
#
#   "C:\Program Files\QGIS 3.44.9\bin\python-qgis-ltr.bat" -m pytest tests -v
import types

from tests.conftest import add_feature, make_line_layer, make_point_layer, make_polygon_layer


def _simple_config(**overrides):
    """Einfaches, dict-basiertes Config-Objekt wie es apply_best_style() akzeptiert."""
    base = {
        "road_style_mode": 1,
        "enable_advanced_road_features": True,
        "enable_road_labels": True,
        "enable_advanced_building_features": True,
        "enable_building_edge_smoothing": True,
        "enable_building_drop_shadow": True,
        "enable_building_labels": True,
        "enable_landuse_labels": True,
        "enable_advanced_point_features": True,
        "custom_mappings": [
            {"active": True, "geom": "Line", "value": "motorway", "style": "autobahn", "label": "Autobahn"},
            {"active": True, "geom": "Polygon", "value": "apartments", "style": "wohngebaeude", "label": "Wohngebäude"},
            {"active": True, "geom": "Polygon", "value": "commercial", "style": "gewerbegebaeude", "label": "Gewerbe"},
            {"active": True, "geom": "Point", "value": "hospital", "style": "hospital", "label": "Krankenhaus"},
        ],
    }
    base.update(overrides)
    return base


# ----------------------------------------------------------------------
# get_layer_geometry_type_name
# ----------------------------------------------------------------------

def test_get_layer_geometry_type_name_for_each_geometry(engine):
    assert engine.get_layer_geometry_type_name(make_line_layer()) == "line"
    assert engine.get_layer_geometry_type_name(make_polygon_layer()) == "polygon"
    assert engine.get_layer_geometry_type_name(make_point_layer()) == "point"


def test_get_layer_geometry_type_name_none_for_missing_layer(engine):
    assert engine.get_layer_geometry_type_name(None) is None


# ----------------------------------------------------------------------
# sync_runtime_bools_from_config
# ----------------------------------------------------------------------

def test_sync_runtime_bools_from_config_dict_source(engine):
    engine.sync_runtime_bools_from_config({"enable_building_labels": True})
    assert engine.enable_building_labels is True

    engine.sync_runtime_bools_from_config({"enable_building_labels": False})
    assert engine.enable_building_labels is False


def test_sync_runtime_bools_from_config_attr_source(engine):
    config = types.SimpleNamespace(enable_building_labels=True)
    engine.sync_runtime_bools_from_config(config)
    assert engine.enable_building_labels is True


def test_sync_runtime_bools_from_config_string_value_coerced(engine):
    engine.sync_runtime_bools_from_config({"enable_building_labels": "true"})
    assert engine.enable_building_labels is True

    engine.sync_runtime_bools_from_config({"enable_building_labels": "false"})
    assert engine.enable_building_labels is False


def test_sync_runtime_bools_from_config_missing_key_keeps_previous_state(engine):
    engine.enable_building_labels = True
    engine.sync_runtime_bools_from_config({})  # Kein enable_building_labels-Key enthalten
    assert engine.enable_building_labels is True  # Bestehender Zustand bleibt erhalten


# ----------------------------------------------------------------------
# apply_best_style: Modus 1 (reines Einzelstyling) - Straßen
# ----------------------------------------------------------------------

def test_mode1_line_layer_applies_road_styling_when_enabled(engine, symbols_loaded):
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Autobahn 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_road_features=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    assert "Modus 1" in result["message"]


# Regressionstest für den Bugfix in apply_road_symbol_mapping:
# Der Straßennamen-Code (inkl. finalem "return True") lag vorher komplett im
# "else"-Zweig (Modus 2) und wurde im reinen Einzelstyling (Modus 1) nie erreicht.
# Dadurch endete die Funktion in Modus 1 ohne Rückgabewert (None/falsy), und der
# "Show Road Names"-Haken hatte dort keinerlei Wirkung.
def test_mode1_line_layer_respects_road_labels_toggle(engine, symbols_loaded):
    layer_labels_on = make_line_layer()
    add_feature(layer_labels_on, ["motorway", "Autobahn 1"])
    config_on = _simple_config(road_style_mode=1, enable_advanced_road_features=True, enable_road_labels=True)
    result_on = engine.apply_best_style(layer_labels_on, config_on)
    assert result_on["success"] is True
    assert layer_labels_on.labelsEnabled() is True

    layer_labels_off = make_line_layer()
    add_feature(layer_labels_off, ["motorway", "Autobahn 1"])
    config_off = _simple_config(road_style_mode=1, enable_advanced_road_features=True, enable_road_labels=False)
    result_off = engine.apply_best_style(layer_labels_off, config_off)
    assert result_off["success"] is True
    assert layer_labels_off.labelsEnabled() is False


def test_mode1_line_layer_master_switch_off_forces_grey_fallback(engine, symbols_loaded):
    from qgis.core import QgsSingleSymbolRenderer

    layer = make_line_layer()
    add_feature(layer, ["motorway", "Autobahn 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_road_features=False)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    assert isinstance(layer.renderer(), QgsSingleSymbolRenderer)
    assert layer.labelsEnabled() is False


# ----------------------------------------------------------------------
# apply_best_style: Modus 1 - Gebäude (Polygon)
# ----------------------------------------------------------------------

def test_mode1_polygon_building_layer_applies_building_styling(engine, symbols_loaded):
    layer = make_polygon_layer()
    add_feature(layer, ["apartments", None, None, None, "Haus 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_building_features=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    assert "Gebäude-Einzelstyling" in result["message"]


def test_mode1_polygon_building_layer_disabled_reports_failure(engine, symbols_loaded):
    layer = make_polygon_layer()
    add_feature(layer, ["apartments", None, None, None, "Haus 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_building_features=False)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is False


# ----------------------------------------------------------------------
# apply_best_style: Modus 1 - Landuse-Polygone (Regressionstest für den Bugfix)
#
# Vorher rief der Code eine nicht existierende Methode namens
# "apply_landuse_symbol_mapping" auf. Der hasattr()-Check war deshalb immer
# False und Landuse-Layer wurden im Modus 1 stillschweigend übersprungen -
# der Haken "Show Landuse Labels" hatte dadurch keinerlei Wirkung.
# ----------------------------------------------------------------------

def test_mode1_polygon_landuse_layer_is_no_longer_skipped(engine, symbols_loaded):
    layer = make_polygon_layer()
    # Landuse-Indikatoren dominieren gegenüber Gebäude-Indikatoren
    add_feature(layer, [None, None, "forest", "forest", "Wald 1"])
    config = _simple_config(road_style_mode=1, enable_landuse_labels=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    assert "übersprungen" not in result["message"]
    assert "Flächen-Einzelstyling" in result["message"]


def test_mode1_polygon_landuse_layer_respects_label_toggle(engine, symbols_loaded):
    layer = make_polygon_layer()
    add_feature(layer, [None, None, "forest", "forest", "Wald 1"])

    config_labels_on = _simple_config(road_style_mode=1, enable_landuse_labels=True)
    engine.apply_best_style(layer, config_labels_on)
    assert layer.labeling() is not None

    layer2 = make_polygon_layer()
    add_feature(layer2, [None, None, "forest", "forest", "Wald 2"])
    config_labels_off = _simple_config(road_style_mode=1, enable_landuse_labels=False)
    engine.apply_best_style(layer2, config_labels_off)
    assert layer2.labeling() is None


# ----------------------------------------------------------------------
# apply_best_style: Modus 1 - Punkte (POIs)
# ----------------------------------------------------------------------

def test_mode1_point_layer_applies_point_styling_when_enabled(engine, symbols_loaded):
    import os

    layer = make_point_layer()
    add_feature(layer, ["hospital", "Krankenhaus 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_point_features=True)
    plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = engine.apply_best_style(layer, config, plugin_dir=plugin_dir)

    assert result["success"] is True
    assert "Punkt-Einzelstyling" in result["message"]


def test_mode1_point_layer_disabled_reports_failure(engine, symbols_loaded):
    layer = make_point_layer()
    add_feature(layer, ["hospital", "Krankenhaus 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_point_features=False)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is False


def test_mode1_point_layer_without_fclass_field_reports_failure(engine, symbols_loaded):
    layer = make_point_layer(fields="field=name:string")  # kein 'fclass'-Feld vorhanden
    add_feature(layer, ["Krankenhaus 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_point_features=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is False
