# Style Auto Plugin
# Copyright (C) 2026 Heinz Danner
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

import os
import time
import json

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QToolBar, QToolButton

# FIX: Import the automatic layer drop-down widget from the QGIS GUI module.
from qgis.gui import QgsMapLayerComboBox

# Core classes for logging and layer types
from qgis.core import Qgis, QgsMessageLog, QgsProject, QgsMapLayerType, QgsMapLayerProxyModel, QgsSettings, QgsStyle

# Internal plugin modules
from . import style_config
from .style_config import get_config
from .style_engine import StyleEngine
from .style_auto_plugin_dialog import StyleAutoPluginDialog


def _get_cfg(config, key, default=None):
    """Read a value from config, whether it is a dict or an attribute-based object."""
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _set_cfg(config, key, value):
    """Write a value to config, whether it is a dict or an attribute-based object."""
    if isinstance(config, dict):
        config[key] = value
    else:
        setattr(config, key, value)


class StyleAutoPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.config_action = None
        self.toolbar = None
        self.layer_combo = None
        self.plugin_dir = os.path.dirname(__file__)

        # --- Strategic language loader for the release ---
        # The plugin uses the in-memory switch directly in the dialog module.
        self.translator = None

        # --- Initialize runtime values ---
        config, err = get_config()
        if config is not None:
            if not hasattr(config, "road_style_mode") or config.road_style_mode is None:
                config.road_style_mode = 2

        self._timing_start = None
        self._timing_connected = False
        self.config = config
        # Direct access to the QGIS core logger via a lambda bridge.
        # ==============================================================================
        # --- Global muting: suppress every engine log message in the background ---
        # ==============================================================================
        self.engine = StyleEngine(
            logger=lambda msg, lvl=Qgis.Info: None,  # Silently absorbs every text message in memory.
            config=config
        )
        # self.engine = StyleEngine(
        #    logger=lambda msg, lvl=Qgis.Info: QgsMessageLog.logMessage(str(msg), "Style Auto Plugin", lvl),
        #    config=config)

    def tr(self, message):
        """Helper for translation in the main plugin context."""
        return QCoreApplication.translate('StyleAutoPlugin', message)

    def push_message(self, text, level=Qgis.Info, duration=5):
        self.iface.messageBar().pushMessage("Style Auto Plugin", str(text), level=level, duration=duration)

    # ------------------------------------------------------------------
    # QGIS plugin lifecycle
    # ------------------------------------------------------------------
    def initGui(self):
        self.import_missing_single_symbols_from_xml()

        # 1. Create the plugin's own toolbar in QGIS
        self.toolbar = self.iface.addToolBar("Style Auto Plugin Toolbar")
        self.toolbar.setObjectName("StyleAutoPluginToolbar")

        # 2. Add the smart layer drop-down menu
        self.layer_combo = QgsMapLayerComboBox(self.iface.mainWindow())
        self.layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.layer_combo.setMinimumWidth(200)

        self.iface.currentLayerChanged.connect(self._sync_combo_with_canvas)
        self.toolbar.addWidget(self.layer_combo)

        # --- Shared visual style for the buttons ---
        # Gives the buttons a gray border, light rounding, and a hover effect
        button_css = """
            QToolButton {
                border: 1px solid #999999;
                border-radius: 3px;
                background-color: #f5f5f5;
                font-weight: bold;
                padding: 2px;
                min-width: 17px;
                min-height: 17px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
                border: 1px solid #666666;
            }
            QToolButton:pressed {
                background-color: #cccccc;
            }
        """

        # 3. The framed "S" start button
        self.action = QAction("S", self.iface.mainWindow())
        self.action.setToolTip(self.tr("Ausgewählten Layer stylen"))
        self.action.triggered.connect(self.run)

        btn_s = QToolButton()
        btn_s.setDefaultAction(self.action)
        btn_s.setStyleSheet(button_css)
        self.toolbar.addWidget(btn_s)

        # 4. The framed "C" configuration button
        self.config_action = QAction("C", self.iface.mainWindow())
        self.config_action.setToolTip(self.tr("Konfigurieren"))
        self.config_action.triggered.connect(self.open_config)

        btn_c = QToolButton()
        btn_c.setDefaultAction(self.config_action)
        btn_c.setStyleSheet(button_css)
        self.toolbar.addWidget(btn_c)

        # 5. Add classic menu entries under "Plugins"
        self.iface.addPluginToMenu("&Style Auto Plugin", self.action)
        self.iface.addPluginToMenu("&Style Auto Plugin", self.config_action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Style Auto Plugin", self.action)
            self.action = None
        if self.config_action:
            self.iface.removePluginMenu("&Style Auto Plugin", self.config_action)
            self.config_action = None
        if self.layer_combo:
            try:
                self.iface.currentLayerChanged.disconnect(self._sync_combo_with_canvas)
            except (TypeError, RuntimeError) as disconnect_err:
                QgsMessageLog.logMessage(
                    f"currentLayerChanged war nicht verbunden: {disconnect_err}",
                    "Style Auto Plugin", Qgis.Info)
            self.layer_combo = None
        if self.toolbar:
            del self.toolbar

    def _sync_combo_with_canvas(self, layer):
        try:
            if self.layer_combo and layer and layer.type() == QgsMapLayerType.VectorLayer:
                self.layer_combo.setLayer(layer)
        except (RuntimeError, SystemError) as sync_err:
            QgsMessageLog.logMessage(
                f"Layer-Combo konnte nicht synchronisiert werden: {sync_err}",
                "Style Auto Plugin", Qgis.Info)

    # ------------------------------------------------------------------
    # Result handling
    # ------------------------------------------------------------------
    def handle_engine_result(self, result):
        if not result:
            self.push_message("Unbekanntes Ergebnis der Style-Engine.", level=Qgis.Warning, duration=6)
            return
        success = bool(result.get("success", False))
        message = result.get("message", "")
        level_name = result.get("level", "info")
        missing_values = result.get("missing_values", []) or []

        if level_name == "critical":
            level = Qgis.Critical
        elif level_name == "warning":
            level = Qgis.Warning
        else:
            level = Qgis.Info

        if message:
            self.push_message(message, level=level, duration=6)

    # ------------------------------------------------------------------
    # Timing: callback after rendering completes
    # ------------------------------------------------------------------
    def _on_canvas_render_complete(self, painter):
        if self._timing_start is None:
            return
        duration_ms = (time.perf_counter() - self._timing_start) * 1000.0
       # QgsMessageLog.logMessage(f"TIMING: Gesamtzeit Style-Auto (Engine + Renderer): {duration_ms:.0f} ms","Style Auto Plugin", Qgis.Info)
        canvas = self.iface.mapCanvas()
        try:
            canvas.renderComplete.disconnect(self._on_canvas_render_complete)
        except TypeError as disconnect_err:
            QgsMessageLog.logMessage(
                f"renderComplete war nicht verbunden: {disconnect_err}",
                "Style Auto Plugin", Qgis.Info)
        self._timing_connected = False
        self._timing_start = None

    # ------------------------------------------------------------------
    # Main entry point (start button)
    # ------------------------------------------------------------------
    def run(self):
        self._timing_start = time.perf_counter()
        config, config_error = style_config.get_config()
        if config_error:
            self.push_message(config_error, level=Qgis.Critical, duration=8)
            self._timing_start = None
            return

        if config is None:
            self.push_message("Konfiguration konnte nicht geladen werden.", level=Qgis.Critical, duration=8)
            self._timing_start = None
            return

        layer = None
        if self.layer_combo:
            layer = self.layer_combo.currentLayer()

        if layer is None:
            self.push_message("Kein Layer im Dropdown ausgewählt.", level=Qgis.Warning, duration=4)
            self._timing_start = None
            return

        # 1. Load data from disk
        json_path = os.path.join(self.plugin_dir, "style_config.json")
        mappings_geladen = False

        # Define default values as a safety net
        config.enable_building_labels = True
        config.enable_road_labels = True
        config.enable_building_edge_smoothing = True
        config.enable_building_drop_shadow = True
        config.enable_landuse_labels = True
        # FIX: These three base toggles (road/building/point hierarchy) were written
        # to JSON by the dialog (see open_config()), but were never read back here.
        # As a result, style_engine.py always fell back to getattr(..., True),
        # regardless of the actual checkbox state in the GUI.
        config.enable_advanced_road_features = True
        config.enable_advanced_building_features = True
        config.enable_advanced_point_features = True

        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)

                    if isinstance(file_data, dict):
                        # Read the actual checkbox values back from the file.
                        if "enable_building_labels" in file_data:
                            config.enable_building_labels = bool(file_data["enable_building_labels"])
                        if "enable_road_labels" in file_data:
                            config.enable_road_labels = bool(file_data["enable_road_labels"])
                        if "enable_building_edge_smoothing" in file_data:
                            config.enable_building_edge_smoothing = bool(file_data["enable_building_edge_smoothing"])
                        if "enable_building_drop_shadow" in file_data:
                            config.enable_building_drop_shadow = bool(file_data["enable_building_drop_shadow"])
                        if "enable_landuse_labels" in file_data:
                            config.enable_landuse_labels = bool(file_data["enable_landuse_labels"])
                        if "enable_advanced_road_features" in file_data:
                            config.enable_advanced_road_features = bool(file_data["enable_advanced_road_features"])
                        if "enable_advanced_building_features" in file_data:
                            config.enable_advanced_building_features = bool(file_data["enable_advanced_building_features"])
                        if "enable_advanced_point_features" in file_data:
                            config.enable_advanced_point_features = bool(file_data["enable_advanced_point_features"])

                        if "road_style_mode" in file_data:
                            setattr(config, "road_style_mode", int(file_data["road_style_mode"]))
                        if "custom_mappings" in file_data:
                            setattr(config, "custom_mappings", file_data["custom_mappings"])
                            mappings_geladen = True
            except Exception as read_err:
                QgsMessageLog.logMessage(
                    f"Konnte custom_mappings nicht aus style_config.json lesen: {read_err}",
                    "Style Auto Plugin", Qgis.Warning)


        # Set fallback mappings if the JSON file was empty
        if not mappings_geladen or not getattr(config, "custom_mappings", None):
            config.custom_mappings = [
                {"active": True, "geom": "Line", "value": "motorway", "style": "autobahn", "label": "Automobilbahn"},
                {"active": True, "geom": "Line", "value": "tertiary", "style": "nebenstrasse", "label": "Nebenstraße"},
                {"active": True, "geom": "Polygon", "value": "apartments", "style": "wohngebaeude",
                 "label": "Wohngebäude"},
                {"active": True, "geom": "Polygon", "value": "commercial", "style": "gewerbegebaeude",
                 "label": "Gewerbe / Industrie"},
                {"active": True, "geom": "Point", "value": "school", "style": "schule_icon", "label": "Schule"},
                {"active": True, "geom": "Point", "value": "hospital", "style": "hospital.svg", "label": "Krankenhaus"}
            ]

        # Connect the canvas timing callback
        canvas = self.iface.mapCanvas()
        if canvas is not None and not self._timing_connected:
            try:
                canvas.renderComplete.connect(self._on_canvas_render_complete)
                self._timing_connected = True
            except TypeError:
                self._timing_connected = True

        # 2. Finally, call the engine with the values enforced from the file
        result = self.engine.apply_best_style(layer=layer, config=config, plugin_dir=self.plugin_dir)
        self.handle_engine_result(result)

    # ------------------------------------------------------------------
    # Open the settings window (config dialog)
    # ------------------------------------------------------------------
    def open_config(self):
        json_path = os.path.join(self.plugin_dir, "style_config.json")

        bestehende_daten = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    bestehende_daten = json.load(f)
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Konnte style_config.json nicht lesen: {e}",
                    "Style Auto Plugin", Qgis.Warning)

        # self.import_missing_single_symbols_from_xml()
        dialog = StyleAutoPluginDialog(self.iface.mainWindow(), active_config=bestehende_daten)
        if dialog.exec_():
            bestehende_daten["road_style_mode"] = dialog.mode_combo.currentIndex()
            bestehende_daten["enable_advanced_road_features"] = dialog.cb_road_base.isChecked()
            bestehende_daten["enable_advanced_building_features"] = dialog.cb_building_base.isChecked()
            bestehende_daten["enable_advanced_point_features"] = dialog.cb_point_base.isChecked()
            bestehende_daten["enable_road_labels"] = dialog.cb_road_labels.isChecked()
            bestehende_daten["enable_building_edge_smoothing"] = dialog.cb_building_smoothing.isChecked()
            bestehende_daten["enable_building_drop_shadow"] = dialog.cb_building_shadow.isChecked()
            bestehende_daten["enable_building_labels"] = dialog.cb_building_labels.isChecked()
            bestehende_daten["enable_landuse_labels"] = dialog.cb_landuse_labels.isChecked()

            if "custom_mappings" in dialog.config:
                bestehende_daten["custom_mappings"] = dialog.config["custom_mappings"]

            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(bestehende_daten, f, ensure_ascii=False, indent=4)

                # Reset the loader cache so QGIS picks up the changes immediately
                if hasattr(style_config, "load_config"):
                    try:
                        style_config.load_config()
                    except Exception as reload_err:
                        QgsMessageLog.logMessage(
                            f"Konnte style_config nicht neu laden: {reload_err}",
                            "Style Auto Plugin", Qgis.Warning)
            except Exception as json_err:
                QgsMessageLog.logMessage(
                    f"Konnte style_config.json nicht schreiben: {json_err}",
                    "Style Auto Plugin", Qgis.Warning)

    def _ensure_default_single_symbol_mappings(self):

        # The five required default entries that must remain visible for testers
        defaults = [
            {"key": "motorway", "value": "autobahn", "label": "Autobahn"},
            {"key": "tertiary", "value": "nebenstrasse", "label": "Nebenstraße"},  # Intentionally built in.
            {"key": "apartments", "value": "wohngebaeude", "label": "Wohngebäude"},
            {"key": "commercial", "value": "gewerbegebaeude", "label": "Gewerbegebäude"},
            {"key": "hospital", "value": "hospital", "label": "Krankenhaus"},
        ]

        # Read config safely, whether it is a dict or an object
        mappings = _get_cfg(self.config, "custom_mappings", [])

        if not isinstance(mappings, list):
            mappings = []


        # Build a list of all keys that are already present in the GUI table
        hinterlegte_keys = [str(m.get("key", "")).strip().lower() for m in mappings if isinstance(m, dict)]

        added = 0
        for entry in defaults:
            such_key = str(entry["key"]).strip().lower()

            # If the key (for example 'tertiary') is not yet present in the table:
            if such_key not in hinterlegte_keys:
                mappings.append(entry)
                added += 1

        # Write the extended list back into the config object
        _set_cfg(self.config, "custom_mappings", mappings)


        if hasattr(self, "save_settings"):
            try:
                # If the main class provides its own save function, run it
                self.save_settings()
            except Exception as save_err:
                QgsMessageLog.logMessage(
                    f"Konnte Einstellungen nicht speichern: {save_err}",
                    "Style Auto Plugin", Qgis.Warning)


    def import_missing_single_symbols_from_xml(self):
        xml_path = os.path.join(self.plugin_dir, "styles", "style_symbols.xml")
        if not os.path.exists(xml_path):
            QgsMessageLog.logMessage(
                f"[SYMBOL-IMPORT] style_symbols.xml nicht gefunden: {xml_path}",
                "Style Auto Plugin",
                Qgis.Warning
            )
            return

        style = QgsStyle.defaultStyle()

        self._ensure_default_single_symbol_mappings()
        style.importXml(xml_path)

