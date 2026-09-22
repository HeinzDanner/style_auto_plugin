# Style Auto Plugin - Test Configuration
#
# Diese Tests benötigen eine echte QGIS-Python-Umgebung (qgis.core), da sie
# reale QgsVectorLayer-Instanzen anlegen und Renderer/Labeling prüfen.
# Ausführen mit dem QGIS-eigenen Python-Interpreter, z.B. unter Windows:
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
    """Startet eine minimale, headless QGIS-Anwendung für die gesamte Testsession."""
    from qgis.core import QgsApplication

    app = QgsApplication([], False)
    app.initQgis()
    yield app
    app.exitQgis()


@pytest.fixture(scope="session")
def symbols_loaded(qgis_app):
    """Importiert die mitgelieferten Standard-Symbole (autobahn, wohngebaeude, ...)
    einmalig in den QgsStyle.defaultStyle(), damit Styling-Tests echte Symbole finden."""
    from qgis.core import QgsStyle

    xml_path = os.path.join(PLUGIN_DIR, "styles", "style_symbols.xml")
    style = QgsStyle.defaultStyle()
    if os.path.exists(xml_path):
        style.importXml(xml_path)
    return style


@pytest.fixture
def engine(qgis_app):
    """Frische StyleEngine-Instanz pro Test (verhindert Seiteneffekte über Klassenattribute)."""
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
