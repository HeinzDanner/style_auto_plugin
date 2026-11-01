"""Opt-in benchmark: run with the QGIS Python interpreter, not regular pytest."""
import argparse
import copy
import json
import os
import statistics
import subprocess
import sys
import time
import types

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_DIR)


def main():
    from qgis.core import (
        Qgis, QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsStyle, QgsVectorLayer,
    )
    from qgis.PyQt.QtGui import QColor
    from style_config import _parse_plugin_config

    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=int, default=30000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output")
    parser.add_argument("--engine-ref", help="Benchmark style_engine.py from a Git ref without checkout")
    args = parser.parse_args()
    if args.features < 1 or args.runs < 1:
        parser.error("--features and --runs must be positive")
    if args.engine_ref:
        module = types.ModuleType("benchmark_engine")
        sys.modules[module.__name__] = module
        source = subprocess.check_output([
            os.environ.get("RELEASE_GIT", "git"), "show", args.engine_ref + ":style_engine.py",
        ])
        exec(compile(source, "benchmark_engine", "exec"), module.__dict__)
        StyleEngine = module.StyleEngine
    else:
        from style_engine import StyleEngine
    app = QgsApplication([], False)
    app.initQgis()
    try:
        with open(os.path.join(PLUGIN_DIR, "style_config.json"), encoding="utf-8") as handle:
            raw = json.load(handle)
        if not QgsStyle.defaultStyle().importXml(os.path.join(PLUGIN_DIR, "styles", "style_symbols.xml")):
            raise RuntimeError("Could not load bundled benchmark symbols")
        available = set(QgsStyle.defaultStyle().symbolNames())
        mappings = raw.get("custom_mappings", [])
        raw["custom_mappings"] = [
            entry for entry in raw.get("custom_mappings", [])
            if entry.get("style") in available or entry.get("style", "").endswith(".svg")
        ]
        if len(mappings) != len(raw["custom_mappings"]):
            print("Skipping mappings for unavailable symbols in this benchmark.", file=sys.stderr)
        results = {}
        snapshots = {}
        for kind, geometry, values, wkt in (
            ("roads", "LineString", ("motorway", "primary", "secondary", "tertiary", "residential"),
             "LINESTRING(0 0,1 1,2 1,3 2)"),
            ("buildings", "Polygon", ("apartments", "commercial", "house", "industrial", "yes"),
             "POLYGON((0 0,0 1,1 1,1 0,0 0))"),
            ("landuse", "Polygon", ("forest", "residential", "commercial", "industrial", "meadow"),
             "POLYGON((0 0,0 1,1 1,1 0,0 0))"),
        ):
            fields = ["fclass", "name", "building", "type", "landuse"] + [
                "extra_{0}".format(index) for index in range(10)]
            uri = geometry + "?crs=EPSG:4326&" + "&".join(
                "field={0}:string".format(name) for name in fields)
            layer = QgsVectorLayer(uri, "gis_osm_{0}_free".format(kind), "memory")
            features = []
            shape = QgsGeometry.fromWkt(wkt)
            for index in range(args.features):
                value = values[index % len(values)]
                feature = QgsFeature(layer.fields())
                feature.setGeometry(shape)
                feature.setAttributes([
                    value, "Name", value if kind == "buildings" else None,
                    None, value if kind == "landuse" else None,
                ] + ["unused"] * 10)
                features.append(feature)
            success, _ = layer.dataProvider().addFeatures(features)
            assert success
            del features
            QgsProject.instance().addMapLayer(layer)
            layer.renderer().symbol().setColor(QColor("#808080"))
            initial_renderer = layer.renderer().clone()
            for mode in range(4):
                timings = []
                for run in range(args.runs + 1):
                    config = _parse_plugin_config(copy.deepcopy(raw))
                    for key, value in raw.items():
                        if key.startswith("enable_") or key == "custom_mappings":
                            setattr(config, key, copy.deepcopy(value))
                    config.road_style_mode = mode
                    engine = StyleEngine(config=config)
                    layer.setRenderer(initial_renderer.clone())
                    started = time.perf_counter()
                    result = engine.apply_best_style(layer, config, PLUGIN_DIR)
                    elapsed = time.perf_counter() - started
                    if not result["success"]:
                        raise RuntimeError("{0}/{1}: {2}".format(kind, mode, result))
                    if run:
                        timings.append(elapsed)
                key = "{0}/mode{1}".format(kind, mode)
                results[key] = round(statistics.median(timings) * 1000, 3)
                renderer = layer.renderer()
                snapshots[key] = {
                    "type": renderer.type(),
                    "field": renderer.classAttribute() if hasattr(renderer, "classAttribute") else None,
                    "categories": [{
                        "value": category.value(), "label": category.label(), "enabled": category.renderState(),
                        "symbol": [category.symbol().symbolLayer(index).properties()
                                   for index in range(category.symbol().symbolLayerCount())],
                    } for category in renderer.categories()] if hasattr(renderer, "categories") else [],
                    "labels": layer.labelsEnabled(),
                    "symbol_levels": renderer.usingSymbolLevels(),
                }
                print("{0}: {1} ms".format(key, results[key]), flush=True)
            QgsProject.instance().removeMapLayer(layer.id())
            del layer
        report = {
            "qgis": Qgis.QGIS_VERSION, "features": args.features, "runs": args.runs,
            "median_ms": results, "styles": snapshots,
        }
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    main()
