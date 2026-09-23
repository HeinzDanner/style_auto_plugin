# Style Auto Plugin - Test Configuration
#
# These tests require a real QGIS Python environment (qgis.core), because they
# create real QgsVectorLayer instances and verify renderers and labeling.
# Run them with the QGIS-provided Python interpreter, for example on Windows:
#
#   "C:\Program Files\QGIS 3.44.9\bin\python-qgis-ltr.bat" -m pytest tests -v
#
import os
import sys

import pytest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)


@pytest.fixture(scope="session")
def qgis_app():
    """Start a minimal headless QGIS application for the full test session."""
    from qgis.core import QgsApplication

    app = QgsApplication([], False)
    app.initQgis()
    yield app
    app.exitQgis()


@pytest.fixture(scope="session")
def symbols_loaded(qgis_app):
    """Import the bundled default symbols (autobahn, wohngebaeude, ...)
    into QgsStyle.defaultStyle() once so styling tests can resolve real symbols."""
    from qgis.core import QgsStyle

    xml_path = os.path.join(PLUGIN_DIR, "styles", "style_symbols.xml")
    style = QgsStyle.defaultStyle()
    if os.path.exists(xml_path):
        style.importXml(xml_path)
    return style


@pytest.fixture
def engine(qgis_app):
    """Fresh StyleEngine instance per test to prevent class-attribute side effects."""
    from style_engine import StyleEngine

    return StyleEngine()


def make_line_layer(name="test_lines", fields="field=fclass:string&field=name:string"):
    from qgis.core import QgsVectorLayer

    layer = QgsVectorLayer(f"LineString?crs=EPSG:4326&{fields}", name, "memory")
    assert layer.isValid()
    return layer


def make_polygon_layer(name="test_polygons",
                        fields="field=building:string&field=type:string&field=fclass:string"
                                "&field=landuse:string&field=name:string"):
    from qgis.core import QgsVectorLayer

    layer = QgsVectorLayer(f"Polygon?crs=EPSG:4326&{fields}", name, "memory")
    assert layer.isValid()
    return layer


def make_point_layer(name="test_points", fields="field=fclass:string&field=name:string"):
    from qgis.core import QgsVectorLayer

    layer = QgsVectorLayer(f"Point?crs=EPSG:4326&{fields}", name, "memory")
    assert layer.isValid()
    return layer


def add_feature(layer, attributes, geometry=None):
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY

    feature = QgsFeature(layer.fields())
    feature.setAttributes(attributes)

    if geometry is None:
        geom_type = layer.geometryType()
        if geom_type == 0:  # Point
            geometry = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        elif geom_type == 1:  # Line
            geometry = QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(1, 1)])
        elif geom_type == 2:  # Polygon
            geometry = QgsGeometry.fromPolygonXY(
                [[QgsPointXY(0, 0), QgsPointXY(0, 1), QgsPointXY(1, 1), QgsPointXY(1, 0), QgsPointXY(0, 0)]]
            )

    feature.setGeometry(geometry)
    layer.dataProvider().addFeatures([feature])
    layer.updateExtents()
    return feature
