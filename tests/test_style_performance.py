"""Behavioral regressions for operation-local value caching and reduced queries."""
import pytest

from tests.conftest import add_feature, make_line_layer, make_polygon_layer


def test_options_reuses_full_field_values_and_clears_cache(engine, symbols_loaded, monkeypatch):
    from qgis.core import QgsProject

    project = QgsProject.instance()
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])
    add_feature(layer, ["path", "Path"])
    original = layer.uniqueValues
    calls = []

    def unique_values(index, limit=-1):
        calls.append((index, limit))
        return original(index, limit)

    monkeypatch.setattr(layer, "uniqueValues", unique_values)
    project.addMapLayer(layer)
    try:
        config = {
            "road_style_mode": 3,
            "custom_mappings": [
                {"geom": "Line", "value": "motorway", "style": "autobahn", "label": "Motorway"}
            ],
        }
        assert engine.apply_best_style(layer, config)["success"]
        assert calls == [(layer.fields().indexOf("fclass"), -1)]
        assert engine._value_cache is None
        add_feature(layer, ["new_value", "New"])
        calls.clear()
        assert engine.apply_best_style(layer, config)["success"]
        assert calls == [(layer.fields().indexOf("fclass"), -1)]
        assert "new_value" in engine.get_distinct_field_values(layer, "fclass")
    finally:
        project.removeMapLayer(layer.id())


def test_cache_is_cleared_after_exception(engine, monkeypatch):
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])

    def failing_base(layer, config, plugin_dir=None):
        engine.get_distinct_field_values(layer, "fclass")
        assert engine._value_cache
        raise RuntimeError("Expected regression test failure")

    monkeypatch.setattr(engine, "_execute_base_styling", failing_base)
    with pytest.raises(RuntimeError, match="Expected regression"):
        engine.apply_best_style(layer, {"road_style_mode": 0})
    assert engine._value_cache is None
    add_feature(layer, ["new_value", "New"])
    assert "new_value" in engine.get_distinct_field_values(layer, "fclass")


def test_distinct_values_include_unsaved_edits_and_nulls(engine):
    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])
    add_feature(layer, [None, "Missing"])
    add_feature(layer, ["", "Empty"])
    assert layer.startEditing()
    feature_id = next(feature.id() for feature in layer.getFeatures() if feature["fclass"] == "motorway")
    assert layer.changeAttributeValue(feature_id, 0, "edited")
    expected = {feature["fclass"] for feature in layer.getFeatures() if feature["fclass"] is not None}
    assert set(engine.get_distinct_field_values(layer, "fclass")) == expected
    assert "edited" in expected
    assert layer.rollBack()
    assert "motorway" in engine.get_distinct_field_values(layer, "fclass")


@pytest.mark.parametrize("edit", ["change", "add", "delete"])
def test_field_classifier_respects_edit_buffer(engine, edit):
    from qgis.core import QgsFeature

    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])
    feature = next(layer.getFeatures())
    assert layer.startEditing()
    if edit == "change":
        assert layer.changeAttributeValue(feature.id(), 0, "edited")
    elif edit == "add":
        added = QgsFeature(layer.fields())
        added.setAttributes(["added", "Added"])
        added.setGeometry(feature.geometry())
        assert layer.addFeature(added)
    else:
        assert layer.deleteFeature(feature.id())
    values, ok = engine._classification_values(layer, "fclass")
    assert ok
    assert set(values) == {current["fclass"] for current in layer.getFeatures()}
    assert layer.rollBack()


def test_edited_classification_is_cached_with_minimal_request(engine, monkeypatch):
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsFeatureRequest, QgsLineSymbol,
        QgsProject, QgsRendererCategory,
    )

    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])
    layer.setRenderer(QgsCategorizedSymbolRenderer("fclass", [
        QgsRendererCategory("motorway", QgsLineSymbol(), "Road"),
    ]))
    assert layer.startEditing()
    requests = []
    original = layer.getFeatures

    def get_features(request):
        requests.append(request)
        return original(request)

    monkeypatch.setattr(layer, "getFeatures", get_features)
    project = QgsProject.instance()
    project.addMapLayer(layer)
    try:
        assert engine.apply_options(layer, {"custom_mappings": []})["success"]
        assert len(requests) == 1
        assert requests[0].flags() & QgsFeatureRequest.Flag.NoGeometry
        assert requests[0].subsetOfAttributes() == [0]
        assert engine._value_cache is None
    finally:
        project.removeMapLayer(layer.id())


def test_expression_classifier_keeps_expression_semantics(engine, monkeypatch):
    from qgis.core import QgsProject, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsLineSymbol

    layer = make_line_layer()
    add_feature(layer, ["motorway", "Road"])
    add_feature(layer, ["path", "Path"])
    expression = 'upper("fclass")'
    layer.setRenderer(QgsCategorizedSymbolRenderer(expression, [
        QgsRendererCategory(value, QgsLineSymbol(), value) for value in ("MOTORWAY", "PATH")
    ]))
    from style_engine import QgsVectorLayerUtils

    original = QgsVectorLayerUtils.getValues
    calls = []

    def get_values(layer, field_or_expression):
        calls.append(field_or_expression)
        return original(layer, field_or_expression)

    monkeypatch.setattr(QgsVectorLayerUtils, "getValues", get_values)
    project = QgsProject.instance()
    project.addMapLayer(layer)
    try:
        assert engine.apply_options(layer, {"custom_mappings": [
            {"geom": "Line", "value": "motorway", "style": "__missing__", "active": False}
        ]})["success"]
        assert calls == [expression]
        values, ok = engine._classification_values(layer, expression)
        assert ok and set(values) == {"MOTORWAY", "PATH"}
    finally:
        project.removeMapLayer(layer.id())


def test_landuse_detection_requests_only_required_attributes_without_geometry(engine, monkeypatch):
    from qgis.core import QgsFeatureRequest

    layer = make_polygon_layer("landuse", fields="field=fclass:string&field=name:string&field=unused:string")
    add_feature(layer, ["forest", "Forest", "Not needed"])
    original = layer.getFeatures
    requests = []

    def get_features(request):
        requests.append(request)
        return original(request)

    monkeypatch.setattr(layer, "getFeatures", get_features)
    assert engine._is_landuse_layer(layer)
    assert len(requests) == 1
    request = requests[0]
    assert request.flags() & QgsFeatureRequest.Flag.NoGeometry
    assert request.subsetOfAttributes() == [0]
    assert request.limit() == 50


def test_mode3_classifies_polygon_only_once(engine, monkeypatch):
    layer = make_polygon_layer("landuse")
    original = engine._is_landuse_layer
    calls = []

    def classify(layer):
        calls.append(layer.id())
        return original(layer)

    monkeypatch.setattr(engine, "_is_landuse_layer", classify)
    assert engine.apply_best_style(layer, {"road_style_mode": 3, "custom_mappings": []})["success"]
    assert calls == [layer.id()]
