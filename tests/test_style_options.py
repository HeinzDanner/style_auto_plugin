import os

import pytest

from tests.conftest import add_feature, make_line_layer, make_point_layer, make_polygon_layer


@pytest.mark.parametrize("mode", [0, 1, 2, "ignored"])
@pytest.mark.parametrize("geometry", ["line", "polygon", "point", "landuse"])
def test_options_never_load_base_style_or_replace_unmapped_symbols(engine, monkeypatch, mode, geometry):
    from qgis.core import QgsRenderContext

    layer = {
        "line": make_line_layer,
        "polygon": make_polygon_layer,
        "point": make_point_layer,
        "landuse": lambda: make_polygon_layer("landuse"),
    }[geometry]()
    original = layer.renderer().symbol().symbolLayer(0).properties()

    def forbidden(*args, **kwargs):
        pytest.fail("Options-only must not load base styles")

    monkeypatch.setattr(engine, "_execute_base_styling", forbidden)
    result = engine.apply_options(layer, {
        "road_style_mode": mode, "custom_mappings": [],
        "enable_advanced_road_features": False,
        "enable_advanced_building_features": False,
        "enable_road_labels": False, "enable_building_labels": False, "enable_landuse_labels": False,
    })
    assert result["success"] is True
    assert layer.renderer().type() == "singleSymbol"
    symbol = layer.renderer().symbols(QgsRenderContext())[0]
    actual = symbol.symbolLayer(0).properties()
    assert actual == original
    assert layer.labelsEnabled() is False


@pytest.mark.parametrize("geometry,value,style_name", [
    ("line", "motorway", "autobahn"),
    ("polygon", "apartments", "wohngebaeude"),
    ("point", "hospital", "hospital.svg"),
])
def test_options_replace_only_matching_values_and_update_legend(engine, symbols_loaded,
                                                               geometry, value, style_name):
    from qgis.core import QgsRenderContext

    layer = {"line": make_line_layer, "polygon": make_polygon_layer, "point": make_point_layer}[geometry](
        fields="field=fclass:string&field=name:string")
    add_feature(layer, [value, "Matched"])
    add_feature(layer, ["unmapped", "Unmatched"])
    original = layer.renderer().symbol().symbolLayer(0).properties()
    result = engine.apply_options(layer, {
        "custom_mappings": [{"geom": geometry.title(), "value": value, "style": style_name, "label": "Custom"}],
        "enable_advanced_road_features": False, "enable_advanced_building_features": False,
    }, plugin_dir=os.path.dirname(os.path.dirname(__file__)))
    assert result["success"] is True
    categories = {str(category.value()): category for category in layer.renderer().categories()}
    assert categories[value].label() == "Custom"
    assert categories["unmapped"].symbol().symbolLayer(0).properties() == original
    assert categories[""].symbol().symbolLayer(0).properties() == original
    assert layer.renderer().symbols(QgsRenderContext())


def test_options_invalid_symbol_does_not_change_renderer(engine):
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])
    renderer = layer.renderer()
    result = engine.apply_options(layer, {"custom_mappings": [
        {"geom": "Line", "value": "motorway", "style": "__missing__"}
    ]})
    assert result["success"] is False
    assert layer.renderer() is renderer
    assert "__missing__" in result["message"]


def test_options_rule_renderer_is_unchanged(engine):
    from qgis.core import QgsRuleBasedRenderer, QgsFillSymbol

    layer = make_polygon_layer()
    layer.setRenderer(QgsRuleBasedRenderer(QgsFillSymbol.createSimple({"color": "#123456"})))
    renderer = layer.renderer()
    result = engine.apply_options(layer, {})
    assert result["success"] is False
    assert layer.renderer() is renderer


def test_options_building_effects_and_labels_can_be_toggled_repeatedly(engine):
    from qgis.PyQt.QtCore import Qt

    layer = make_polygon_layer()
    add_feature(layer, ["apartments", None, None, None, "House"])
    color = layer.renderer().symbol().color().name()
    for enabled in (True, True, False, True, False):
        result = engine.apply_options(layer, {
            "custom_mappings": [], "enable_building_edge_smoothing": enabled,
            "enable_building_drop_shadow": enabled, "enable_building_labels": enabled,
        })
        assert result["success"] is True
        symbol = layer.renderer().symbol()
        assert symbol.symbolLayerCount() == (2 if enabled else 1)
        assert symbol.symbolLayer(symbol.symbolLayerCount() - 1).fillColor().name() == color
        assert symbol.symbolLayer(symbol.symbolLayerCount() - 1).strokeStyle() == (
            Qt.PenStyle.SolidLine if enabled else Qt.PenStyle.NoPen)
        assert layer.labelsEnabled() is enabled


def test_options_road_hierarchy_and_labels_can_be_disabled(engine):
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])
    for enabled in (True, False):
        result = engine.apply_options(layer, {
            "custom_mappings": [], "enable_advanced_road_features": enabled, "enable_road_labels": enabled,
        })
        assert result["success"] is True
        assert layer.renderer().usingSymbolLevels() is enabled
        assert layer.labelsEnabled() is enabled


def test_options_preserve_categorized_field_order_flags_and_unmatched_symbols(engine, symbols_loaded):
    from qgis.core import QgsCategorizedSymbolRenderer, QgsLineSymbol, QgsRendererCategory

    layer = make_line_layer(fields="field=custom_class:string&field=name:string")
    categories = [
        QgsRendererCategory("unmapped", QgsLineSymbol.createSimple({"line_color": "#123456"}), "Keep", False),
        QgsRendererCategory("motorway", QgsLineSymbol.createSimple({"line_color": "#654321"}), "Old"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("custom_class", categories))
    add_feature(layer, ["motorway", "Road"])
    result = engine.apply_options(layer, {
        "custom_mappings": [{"geom": "Line", "value": "motorway", "style": "autobahn", "label": "New"}],
        "enable_advanced_road_features": False,
    })
    assert result["success"] is True
    assert layer.renderer().classAttribute() == "custom_class"
    updated = layer.renderer().categories()
    assert [category.value() for category in updated] == ["unmapped", "motorway"]
    assert updated[0].renderState() is False
    assert updated[0].label() == "Keep"
    assert updated[0].symbol().color().name() == "#123456"
    assert updated[1].label() == "New"


def test_options_single_symbol_uses_field_with_matching_values(engine, symbols_loaded):
    layer = make_polygon_layer()
    add_feature(layer, ["apartments", None, "unrelated", None, "House"])
    result = engine.apply_options(layer, {
        "custom_mappings": [{"geom": "Polygon", "value": "apartments", "style": "wohngebaeude", "label": "House"}]
    })
    assert result["success"] is True
    assert layer.renderer().classAttribute() == "building"


def test_options_numeric_code_mapping(engine, symbols_loaded):
    layer = make_line_layer(fields="field=code:integer&field=name:string")
    add_feature(layer, [5111, "Road"])
    result = engine.apply_options(layer, {
        "custom_mappings": [{"geom": "Line", "value": "motorway", "style": "autobahn", "label": "Mapped"}]
    })
    assert result["success"] is True
    categories = layer.renderer().categories()
    assert categories[0].value() == 5111
    assert categories[0].label() == "Mapped"


@pytest.mark.parametrize("active", [False, True])
def test_options_point_feature_switch_controls_mapping(engine, active):
    layer = make_point_layer()
    add_feature(layer, ["hospital", "Hospital"])
    result = engine.apply_options(layer, {
        "enable_advanced_point_features": active,
        "custom_mappings": [{"geom": "Point", "value": "hospital", "style": "__missing__"}],
    })
    assert result["success"] is (not active)
    assert layer.renderer().type() == "singleSymbol"


def test_options_landuse_label_switch_keeps_existing_fill(engine):
    layer = make_polygon_layer("landuse")
    add_feature(layer, [None, None, "forest", "forest", "Forest"])
    color = layer.renderer().symbol().color().name()
    for enabled in (True, False):
        result = engine.apply_options(layer, {"custom_mappings": [], "enable_landuse_labels": enabled})
        assert result["success"] is True
        assert layer.labelsEnabled() is enabled
        assert layer.renderer().symbol().color().name() == color


@pytest.mark.parametrize("mode", [3])
def test_mode3_routes_style_action_to_options_only(engine, monkeypatch, mode):
    layer = make_line_layer()
    recorded = []

    def apply_options(layer, config, plugin_dir=None):
        recorded.append(layer)
        return {"success": True}

    monkeypatch.setattr(engine, "apply_options", apply_options)
    assert engine.apply_best_style(layer, {"road_style_mode": mode})["success"]
    assert recorded == [layer]


def test_mode3_legend_only_shows_present_gui_matches_and_one_rest_entry(engine, symbols_loaded):
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsLineSymbol, QgsRendererCategory,
        QgsMapLayerLegendUtils, QgsProject, QgsLayerTreeModel,
    )

    project = QgsProject.instance()
    layer = make_line_layer()
    for value in ("motorway", "path", "track"):
        add_feature(layer, [value, value])
    layer.setRenderer(QgsCategorizedSymbolRenderer("fclass", [
        QgsRendererCategory(value, QgsLineSymbol.createSimple({"line_color": color}), value)
        for value, color in (
            ("path", "#123456"), ("motorway", "#654321"), ("track", "#abcdef"), ("tertiary", "#999999"))
    ]))
    project.addMapLayer(layer)
    try:
        config = {"road_style_mode": 3, "enable_advanced_road_features": False,
                  "custom_mappings": [
                      {"geom": "Line", "value": "motorway", "style": "autobahn", "label": "Autobahn"},
                      {"geom": "Line", "value": "tertiary", "style": "__absent_not_required__", "label": "Absent"},
                  ]}
        for _ in range(2):
            assert engine.apply_best_style(layer, config)["success"]
            node = project.layerTreeRoot().findLayer(layer.id())
            assert QgsMapLayerLegendUtils.legendNodeOrder(node) == [1, 0]
            assert QgsMapLayerLegendUtils.legendNodeUserLabel(node, 0) == "Andere Werte"
            categories = layer.renderer().categories()
            assert len(categories) == 4
            assert categories[1].label() == "Autobahn"
            assert categories[0].symbol().color().name() == "#123456"
            assert categories[2].symbol().color().name() == "#abcdef"
        model = QgsLayerTreeModel(project.layerTreeRoot())
        from qgis.PyQt.QtCore import Qt
        assert [item.data(Qt.ItemDataRole.DisplayRole) for item in model.layerLegendNodes(node)] == [
            "Autobahn", "Andere Werte"]
        gui_node, rest_node = model.layerLegendNodes(node)
        for checked in (False, True, False, True):
            rest_node.setData(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked,
                              Qt.ItemDataRole.CheckStateRole)
            states = [category.renderState() for category in layer.renderer().categories()]
            assert states == [checked, True, checked, checked]
        gui_node.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
        assert [category.renderState() for category in layer.renderer().categories()] == [
            True, False, True, True]
        del gui_node, rest_node
        from qgis.PyQt import sip
        sip.delete(model)
        engine._restore_options_legend(layer)
        assert not QgsMapLayerLegendUtils.hasLegendNodeOrder(node)
        assert not QgsMapLayerLegendUtils.hasLegendNodeUserLabel(node, 0)
    finally:
        project.removeMapLayer(layer.id())


def test_mode3_legend_restores_previous_user_legend_customizations(engine):
    from qgis.core import QgsMapLayerLegendUtils, QgsProject

    project = QgsProject.instance()
    layer = make_line_layer()
    project.addMapLayer(layer)
    try:
        node = project.layerTreeRoot().findLayer(layer.id())
        QgsMapLayerLegendUtils.setLegendNodeUserLabel(node, 0, "My label")
        QgsMapLayerLegendUtils.setLegendNodeOrder(node, [0])
        assert engine.apply_best_style(layer, {"road_style_mode": 3, "custom_mappings": []})["success"]
        assert QgsMapLayerLegendUtils.legendNodeUserLabel(node, 0) == "Andere Werte"
        engine._restore_options_legend(layer)
        assert QgsMapLayerLegendUtils.legendNodeUserLabel(node, 0) == "My label"
        assert QgsMapLayerLegendUtils.legendNodeOrder(node) == [0]
    finally:
        project.removeMapLayer(layer.id())


def test_rest_checkbox_with_empty_representative_and_rebound_handler(engine, symbols_loaded):
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import Qt
    from qgis.core import QgsCategorizedSymbolRenderer, QgsLineSymbol, QgsRendererCategory, QgsProject, QgsLayerTreeModel

    project = QgsProject.instance()
    layer = make_line_layer()
    for value in ("", "path", "track", "motorway"):
        add_feature(layer, [value, value])
    layer.setRenderer(QgsCategorizedSymbolRenderer("fclass", [
        QgsRendererCategory(value, QgsLineSymbol(), value)
        for value in ("", "path", "track", "motorway")
    ]))
    project.addMapLayer(layer)
    model = None
    try:
        assert engine.apply_best_style(layer, {
            "road_style_mode": 3, "custom_mappings": [
                {"geom": "Line", "value": "motorway", "style": "autobahn", "label": "Autobahn"}
            ],
        })["success"]
        engine.bind_legend_groups([layer])
        engine.bind_legend_groups([layer])
        handler = layer._style_auto_rest_handler
        assert handler.__defaults__ == (layer.id(),)
        node = project.layerTreeRoot().findLayer(layer.id())
        model = QgsLayerTreeModel(project.layerTreeRoot())
        for checked in (False, True):
            items = model.layerLegendNodes(node)
            items[-1].setData(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked,
                              Qt.ItemDataRole.CheckStateRole)
            assert [category.renderState() for category in layer.renderer().categories()] == [
                checked, checked, checked, True]
            assert node.customProperty("style_auto_plugin/rest_categories")["checked"] is checked
            del items
    finally:
        if model is not None:
            sip.delete(model)
        project.removeMapLayer(layer.id())


def test_config_dialog_offers_mode3_without_changing_saved_mode(qgis_app):
    from style_auto_plugin.style_auto_plugin_dialog import StyleAutoPluginDialog

    dialog = StyleAutoPluginDialog(active_config={"road_style_mode": 3, "custom_mappings": []})
    try:
        assert dialog.mode_combo.count() == 4
        assert dialog.mode_combo.currentIndex() == 3
    finally:
        dialog.close()
        from qgis.PyQt import sip
        sip.delete(dialog)


@pytest.mark.parametrize("initial_checked", [False, True])
def test_rest_checkbox_survives_project_save_reload(engine, monkeypatch, tmp_path, initial_checked):
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import Qt
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsLineSymbol, QgsRendererCategory,
        QgsProject, QgsLayerTreeModel,
    )

    project = QgsProject()
    monkeypatch.setattr(QgsProject, "instance", staticmethod(lambda: project))
    project.layersAdded.connect(engine.bind_legend_groups)
    project.readProject.connect(engine.bind_project_legend_groups)
    layer = make_line_layer()
    for value in ("path", "track"):
        add_feature(layer, [value, value])
    layer.setRenderer(QgsCategorizedSymbolRenderer("fclass", [
        QgsRendererCategory(value, QgsLineSymbol.createSimple({"line_color": color}), value)
        for value, color in (("path", "#123456"), ("track", "#abcdef"))
    ]))
    project.addMapLayer(layer)
    model = None
    try:
        assert engine.apply_best_style(layer, {
            "road_style_mode": 3, "custom_mappings": [],
            "enable_advanced_road_features": False,
        })["success"]
        node = project.layerTreeRoot().findLayer(layer.id())
        model = QgsLayerTreeModel(project.layerTreeRoot())
        items = model.layerLegendNodes(node)
        items[0].setData(Qt.CheckState.Checked if initial_checked else Qt.CheckState.Unchecked,
                         Qt.ItemDataRole.CheckStateRole)
        del items
        sip.delete(model)
        model = None
        layer_id = layer.id()
        path = str(tmp_path / "legend.qgs")
        assert project.write(path)
        project.clear()
        assert project.read(path)
        reloaded = project.mapLayer(layer_id)
        assert reloaded is not None
        categories = reloaded.renderer().categories()
        assert [category.renderState() for category in categories] == [initial_checked] * 2
        assert [category.symbol().color().name() for category in categories] == ["#123456", "#abcdef"]
        node = project.layerTreeRoot().findLayer(layer_id)
        model = QgsLayerTreeModel(project.layerTreeRoot())
        items = model.layerLegendNodes(node)
        assert [item.data(Qt.ItemDataRole.DisplayRole) for item in items] == ["Andere Werte"]
        for checked in (not initial_checked, initial_checked):
            items[0].setData(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked,
                             Qt.ItemDataRole.CheckStateRole)
            assert [category.renderState() for category in reloaded.renderer().categories()] == [checked] * 2
        del items
    finally:
        if model is not None:
            sip.delete(model)
        project.layersAdded.disconnect(engine.bind_legend_groups)
        project.readProject.disconnect(engine.bind_project_legend_groups)
        project.clear()


def test_rest_handler_stops_grouping_after_legend_restored(engine):
    from qgis.core import QgsCategorizedSymbolRenderer, QgsLineSymbol, QgsRendererCategory, QgsProject

    project = QgsProject.instance()
    layer = make_line_layer()
    for value in ("path", "track"):
        add_feature(layer, [value, value])
    layer.setRenderer(QgsCategorizedSymbolRenderer("fclass", [
        QgsRendererCategory(value, QgsLineSymbol(), value) for value in ("path", "track")
    ]))
    project.addMapLayer(layer)
    try:
        assert engine.apply_best_style(layer, {"road_style_mode": 3, "custom_mappings": []})["success"]
        engine._restore_options_legend(layer)
        layer.renderer().updateCategoryRenderState(0, False)
        layer.emitStyleChanged()
        assert [category.renderState() for category in layer.renderer().categories()] == [False, True]
    finally:
        project.removeMapLayer(layer.id())
