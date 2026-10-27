# Style Auto Plugin - Functional tests for style_engine.py
#
# These tests require a real QGIS Python environment (qgis.core), because they
# create real QgsVectorLayer instances and verify renderers and labeling.
#
#   "C:\Program Files\QGIS 3.44.9\bin\python-qgis-ltr.bat" -m pytest tests -v
import types
import pytest

from tests.conftest import add_feature, make_line_layer, make_point_layer, make_polygon_layer


def _simple_config(**overrides):
    """Simple dict-based config object in the format accepted by apply_best_style()."""
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


def _landuse_config(**overrides):
    from style_config import FieldRuleSet, LayerRuleSet, LineStyleDef, MatchConfig, ValueRule

    config = _simple_config(**overrides)
    config["layerrulesets"] = [
        LayerRuleSet(
            match=MatchConfig(geometry_type="polygon", field_hints=["fclass"]),
            fieldrulesets=[FieldRuleSet(
                field_name="fclass",
                rules=[
                    ValueRule(value=value, label=value, style=LineStyleDef(
                        color=color, width=0.0, penstyle="nopen"))
                    for value, color in (("forest", "#add19e"), ("residential", "#f2eae2"))
                ],
            )],
        )
    ]
    return types.SimpleNamespace(**config)


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
    engine.sync_runtime_bools_from_config({})  # No enable_building_labels key present
    assert engine.enable_building_labels is True  # Existing state remains unchanged


# ----------------------------------------------------------------------
# apply_best_style: mode 1 (pure single-symbol styling) - roads
# ----------------------------------------------------------------------

def test_mode1_line_layer_applies_road_styling_when_enabled(engine, symbols_loaded):
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Autobahn 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_road_features=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    assert "Modus 1" in result["message"]


# Regression test for the bug fix in apply_road_symbol_mapping:
# The road-name code path (including the final "return True") previously lived
# entirely inside the "else" branch (mode 2) and was never reached in pure
# single-symbol styling (mode 1). As a result, the function ended in mode 1
# without a return value (None/falsy), and the "Show Road Names" toggle had no effect.
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


# Regression test for the bug fix in apply_road_symbol_mapping:
# The block that enables symbol levels (setUsingSymbolLevels) and enforces round
# cap/join styles previously lived entirely inside the "else" branch (mode 2)
# and never ran in pure single-symbol styling (mode 1). As a result, road
# categories with different widths did not stack cleanly in mode 1.
def test_mode1_line_layer_enables_symbol_levels_and_round_caps(engine, symbols_loaded):
    from qgis.PyQt.QtCore import Qt

    layer = make_line_layer()
    add_feature(layer, ["motorway", "Autobahn 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_road_features=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    renderer = layer.renderer()
    assert renderer.usingSymbolLevels() is True

    # At least one category must have a symbol layer with round joins/caps
    found_round_join = False
    for category in renderer.categories():
        symbol = category.symbol()
        for i in range(symbol.symbolLayerCount()):
            sl = symbol.symbolLayer(i)
            if hasattr(sl, "penJoinStyle"):
                qt_round_join = getattr(getattr(Qt, "PenJoinStyle", Qt), "RoundJoin")
                if sl.penJoinStyle() == qt_round_join:
                    found_round_join = True
    assert found_round_join is True


def test_mode1_line_layer_hierarchy_toggle_off_keeps_custom_mapping_but_disables_symbol_levels(engine, symbols_loaded):
    # FIX: According to the GUI label, the "Enable road hierarchy & thick line
    # designs" toggle (enable_advanced_road_features) is responsible only for
    # hierarchy extras (symbol-level merging plus round caps/joins), not for
    # disabling the complete road styling. Previously, disabling it skipped the
    # custom mapping entirely and forced a plain gray line instead.
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Autobahn 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_road_features=False)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    renderer = layer.renderer()
    # Custom mapping stays active: the renderer remains categorized, not flat gray.
    assert renderer.type() == "categorizedSymbol"
    # But the hierarchy extras are disabled:
    assert renderer.usingSymbolLevels() is False


# ----------------------------------------------------------------------
# apply_best_style: mode 1 - buildings (polygon)
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
# apply_best_style: mode 1 - building labels follow only their own
# toggle (enable_building_labels), not the 2.5D shadow toggle.
#
# Previously, apply_building_symbol_mapping() checked:
#   "(StyleEngine.enable_building_labels is True and has_name)
#    or StyleEngine.enable_building_shadow is True"
# However, the global class attribute StyleEngine.enable_building_shadow was
# updated only while the dialog was open and the user clicked the shadow toggle.
# During a headless run(), it could remain at its last, potentially stale value.
# In addition, the "or" condition forced labeling on whenever the shadow toggle
# was active, regardless of the actual labeling toggle.
# ----------------------------------------------------------------------

def test_mode1_building_labels_follow_only_their_own_toggle(engine, symbols_loaded):
    layer_labels_on = make_polygon_layer()
    add_feature(layer_labels_on, ["apartments", None, None, None, "Haus 1"])
    config_on = _simple_config(
        road_style_mode=1, enable_advanced_building_features=True,
        enable_building_labels=True, enable_building_drop_shadow=False,
    )

    result_on = engine.apply_best_style(layer_labels_on, config_on)

    assert result_on["success"] is True
    assert layer_labels_on.labelsEnabled() is True

    layer_labels_off = make_polygon_layer()
    add_feature(layer_labels_off, ["apartments", None, None, None, "Haus 1"])
    config_off = _simple_config(
        road_style_mode=1, enable_advanced_building_features=True,
        enable_building_labels=False, enable_building_drop_shadow=True,
    )

    result_off = engine.apply_best_style(layer_labels_off, config_off)

    assert result_off["success"] is True
    assert layer_labels_off.labelsEnabled() is False


# ----------------------------------------------------------------------
# apply_best_style: mode 1 - landuse polygons must style fills as well as labels.
# ----------------------------------------------------------------------

def test_mode1_polygon_landuse_layer_is_no_longer_skipped(engine, symbols_loaded):
    engine.config = types.SimpleNamespace(compactlegend=False)
    layer = make_polygon_layer()
    # Landuse indicators outweigh building indicators
    add_feature(layer, [None, None, "forest", "forest", "Wald 1"])
    config = _landuse_config(road_style_mode=1, enable_landuse_labels=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is True
    assert "übersprungen" not in result["message"]
    assert "Flächen-Einzelstyling" in result["message"]


def test_mode1_polygon_landuse_layer_respects_label_toggle(engine, symbols_loaded):
    engine.config = types.SimpleNamespace(compactlegend=False)
    layer = make_polygon_layer()
    add_feature(layer, [None, None, "forest", "forest", "Wald 1"])

    config_labels_on = _landuse_config(road_style_mode=1, enable_landuse_labels=True)
    engine.apply_best_style(layer, config_labels_on)
    assert layer.labeling() is not None

    layer2 = make_polygon_layer()
    add_feature(layer2, [None, None, "forest", "forest", "Wald 2"])
    config_labels_off = _landuse_config(road_style_mode=1, enable_landuse_labels=False)
    engine.apply_best_style(layer2, config_labels_off)
    assert layer2.labeling() is None


# ----------------------------------------------------------------------
# apply_best_style: mode 2 - landuse labeling follows the config toggle
# (regression test for the same bug pattern as the building booleans):
# previously, this used "StyleEngine.enable_landuse_labels" (a stale class
# attribute) instead of the variable derived locally from config.
# ----------------------------------------------------------------------

def test_mode2_polygon_landuse_layer_respects_label_toggle(engine, symbols_loaded):
    engine.config = types.SimpleNamespace(compactlegend=False)
    layer_on = make_polygon_layer()
    add_feature(layer_on, [None, None, "forest", "forest", "Wald 1"])
    config_on = _landuse_config(road_style_mode=2, enable_landuse_labels=True)
    engine.apply_best_style(layer_on, config_on)
    assert layer_on.labeling() is not None

    layer_off = make_polygon_layer()
    add_feature(layer_off, [None, None, "forest", "forest", "Wald 2"])
    config_off = _landuse_config(road_style_mode=2, enable_landuse_labels=False)
    engine.apply_best_style(layer_off, config_off)
    assert layer_off.labeling() is None


@pytest.mark.parametrize("mode", [0, 1, 2])
def test_landuse_modes_apply_base_colors_without_building_outlines(engine, mode):
    engine.config = types.SimpleNamespace(compactlegend=False)
    from qgis.PyQt.QtCore import Qt

    layer = make_polygon_layer("gis_osm_landuse_a_free",
                               fields="field=fclass:string&field=name:string")
    add_feature(layer, ["forest", "Forest"])
    add_feature(layer, ["residential", "Residential"])

    result = engine.apply_best_style(layer, _landuse_config(road_style_mode=mode))

    assert result["success"] is True
    renderer = layer.renderer()
    assert renderer.type() == "categorizedSymbol"
    categories = {str(category.value()): category for category in renderer.categories()}
    assert categories["forest"].symbol().color().name() == "#add19e"
    assert categories["residential"].symbol().color().name() == "#f2eae2"
    for value in ("forest", "residential"):
        symbol_layer = categories[value].symbol().symbolLayer(0)
        assert symbol_layer.strokeStyle() == Qt.PenStyle.NoPen


@pytest.mark.parametrize("mode", [1, 2])
def test_landuse_gui_symbols_override_base_without_affecting_other_categories(engine, mode):
    engine.config = types.SimpleNamespace(compactlegend=False)
    from qgis.core import QgsFillSymbol, QgsStyle

    style = QgsStyle.defaultStyle()
    symbol_name = "__landuse_regression_test__"
    style.addSymbol(symbol_name, QgsFillSymbol.createSimple({"color": "#123456"}))
    try:
        layer = make_polygon_layer("landuse", fields="field=fclass:string&field=name:string")
        add_feature(layer, ["forest", "Forest"])
        add_feature(layer, ["residential", "Residential"])
        config = _landuse_config(road_style_mode=mode, custom_mappings=[
            {"geom": "Polygon", "value": "forest", "style": symbol_name, "label": "Custom forest"}
        ])
        legend_updates = []
        layer.rendererChanged.connect(lambda: legend_updates.append(
            [category.label() for category in layer.renderer().categories()]))
        result = engine.apply_best_style(layer, config)
        assert result["success"] is True
        categories = {str(category.value()): category for category in layer.renderer().categories()}
        assert categories["forest"].symbol().color().name() == "#123456"
        assert categories["forest"].label() == "Custom forest"
        assert categories["residential"].symbol().color().name() == "#f2eae2"
        assert "Custom forest" in legend_updates[-1]
    finally:
        style.removeSymbol(symbol_name)


@pytest.mark.parametrize("mode", [1, 2])
def test_landuse_missing_base_rules_report_failure(engine, mode):
    layer = make_polygon_layer("landuse", fields="field=fclass:string")
    add_feature(layer, ["forest"])
    result = engine.apply_best_style(layer, _simple_config(road_style_mode=mode))
    assert result["success"] is False
    assert result["message"]


@pytest.mark.parametrize("custom_mapping", [False, True])
def test_landuse_mode1_compacts_legend_and_other_modes_restore_it(engine, custom_mapping):
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import Qt
    from qgis.core import QgsFillSymbol, QgsLayerTreeModel, QgsProject, QgsStyle

    engine.config = types.SimpleNamespace(compactlegend=False)
    project = QgsProject.instance()
    style = QgsStyle.defaultStyle()
    symbol_name = "__landuse_compact_legend_test__"
    style.addSymbol(symbol_name, QgsFillSymbol.createSimple({"color": "#123456"}))
    layer = make_polygon_layer("landuse", fields="field=fclass:string&field=name:string")
    add_feature(layer, ["forest", "Forest"])
    add_feature(layer, ["residential", "Residential"])
    project.addMapLayer(layer)
    model = QgsLayerTreeModel(project.layerTreeRoot())
    try:
        node = project.layerTreeRoot().findLayer(layer.id())
        mappings = [{
            "geom": "Polygon", "value": "forest", "style": symbol_name, "label": "Custom forest"
        }] if custom_mapping else []
        for mode in (1, 1, 2, 1, 0):
            result = engine.apply_best_style(layer, _landuse_config(
                road_style_mode=mode, custom_mappings=mappings))
            assert result["success"] is True
            model.refreshLayerLegend(node)
            labels = [item.data(Qt.ItemDataRole.DisplayRole) for item in model.layerLegendNodes(node)]
            if mode == 1:
                assert labels == (["Custom forest", "Andere Werte"] if custom_mapping else ["Andere Werte"])
            elif mode == 2 and custom_mapping:
                assert set(labels) == {"Custom forest", "residential"}
            else:
                assert set(labels) == {"forest", "residential"}
            categories = {str(category.value()): category for category in layer.renderer().categories()}
            assert len(categories) == 2
            assert categories["residential"].symbol().color().name() == "#f2eae2"
            assert categories["forest"].symbol().color().name() == (
                "#123456" if custom_mapping and mode != 0 else "#add19e")
    finally:
        sip.delete(model)
        project.removeMapLayer(layer.id())
        style.removeSymbol(symbol_name)


def test_landuse_missing_custom_symbol_reports_failure(engine):
    engine.config = types.SimpleNamespace(compactlegend=False)
    layer = make_polygon_layer("landuse", fields="field=fclass:string")
    add_feature(layer, ["forest"])
    result = engine.apply_best_style(layer, _landuse_config(custom_mappings=[
        {"geom": "Polygon", "value": "forest", "style": "__missing_symbol__"}
    ]))
    assert result["success"] is False
    assert "__missing_symbol__" in result["message"]


def test_landuse_switching_modes_resets_labels_and_keeps_base_symbols(engine):
    engine.config = types.SimpleNamespace(compactlegend=False)
    layer = make_polygon_layer("landuse", fields="field=fclass:string&field=name:string")
    add_feature(layer, ["forest", "Forest"])
    for mode in (2, 0, 1, 0):
        result = engine.apply_best_style(layer, _landuse_config(
            road_style_mode=mode, custom_mappings=[]))
        assert result["success"] is True
        assert layer.labelsEnabled() is (mode != 0)
        categories = layer.renderer().categories()
        assert categories[0].symbol().color().name() == "#add19e"


def test_landuse_mode0_ignores_gui_symbols(engine):
    engine.config = types.SimpleNamespace(compactlegend=False)
    layer = make_polygon_layer("landuse", fields="field=fclass:string")
    add_feature(layer, ["forest"])
    result = engine.apply_best_style(layer, _landuse_config(
        road_style_mode=0, custom_mappings=[
            {"geom": "Polygon", "value": "forest", "style": "__missing_symbol__"}
        ]))
    assert result["success"] is True
    categories = layer.renderer().categories()
    assert categories[0].symbol().color().name() == "#add19e"


@pytest.mark.parametrize("penstyle, expected", [("nopen", "NoPen"), ("solid", "SolidLine")])
def test_fill_symbol_respects_outline_style(engine, penstyle, expected):
    from qgis.PyQt.QtCore import Qt
    from style_config import LineStyleDef

    symbol = engine.create_fill_symbol(LineStyleDef(penstyle=penstyle))
    assert symbol.symbolLayer(0).strokeStyle() == getattr(Qt.PenStyle, expected)


@pytest.mark.parametrize("value", ["residential", "commercial", "industrial", "retail"])
def test_landuse_name_identifies_layers_without_natural_classes(engine, value):
    layer = make_polygon_layer("gis_osm_landuse_a_free", fields="field=fclass:string")
    add_feature(layer, [value])
    assert engine._is_landuse_layer(layer) is True


# ----------------------------------------------------------------------
# apply_best_style: mode 1 - points (POIs)
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
    layer = make_point_layer(fields="field=name:string")  # No 'fclass' field present
    add_feature(layer, ["Krankenhaus 1"])
    config = _simple_config(road_style_mode=1, enable_advanced_point_features=True)

    result = engine.apply_best_style(layer, config)

    assert result["success"] is False
