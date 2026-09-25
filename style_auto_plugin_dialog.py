from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
                                 QComboBox, QLabel, QPushButton, QScrollArea,
                                 QWidget, QGroupBox, QLineEdit, QRadioButton, QButtonGroup)
from qgis.PyQt.QtCore import Qt, QLocale,QCoreApplication
from qgis.core import QgsSettings, QgsMessageLog, Qgis, QgsProject, QgsStyle
from .style_engine import style_engine


def _qt_alignment(member):
    scoped_enum = getattr(Qt, "AlignmentFlag", None)
    if scoped_enum is not None:
        return getattr(scoped_enum, member)
    return getattr(Qt, member)


class StyleAutoPluginDialog(QDialog):
    def __init__(self, parent=None, active_config=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Style Auto Plugin - Configuration"))
        self.setMinimumWidth(550)  # Slightly narrower width because one column was removed.
        self.setMinimumHeight(550)

        self.config = active_config if active_config is not None else {}
        self.style_engine = style_engine
        self.style_engine.config = self.config  # Pass through the loaded configuration.

        # Important: synchronize the booleans once with the real config.
        self.style_engine.sync_runtime_bools_from_config(self.config)

        self.main_layout = QVBoxLayout(self)

        # ==============================================================================
        # MAIN SECTION: global styling mode (at the top for all layers)
        # ==============================================================================
        global_mode_layout = QHBoxLayout()
        lbl_mode = QLabel(self.tr("Global Styling Mode (All Layers):"), self)
        lbl_mode.setStyleSheet("font-weight: bold; font-size: 11px;")  # Make it stand out visually.
        global_mode_layout.addWidget(lbl_mode)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems([
            self.tr("Mode 0: Pure Base Styling (JSON Rules)"),
            self.tr("Mode 1: Pure Custom Single Styling (GUI List)"),
            self.tr("Mode 2: Combined Styling (Base + GUI List)")
        ])

        # --- Fix: capture the current mode when opening the dialog ---
        if isinstance(self.config, dict):
            aktueller_modus = self.config.get("road_style_mode", 2)
        else:
            aktueller_modus = getattr(self.config, "road_style_mode", 2)

        self.mode_combo.setCurrentIndex(int(aktueller_modus))
        self.mode_combo.currentIndexChanged.connect(self.auto_save_settings)
        global_mode_layout.addWidget(self.mode_combo)

        self.main_layout.addLayout(global_mode_layout)
        self.main_layout.addWidget(
            QLabel("----------------------------------------------------------------------------------------", self))

        # --- GRUPPE 1 & 2 VERSCHMOLZEN: REINE KARTOGRAFISCHE EFFEKTE ---
        englischer_text = "Cartographic Options (active in Mode 1 and Mode 2)"
        self.group_effects = QGroupBox(self.tr(englischer_text), self)

        # Safety net: translation fallback for testers
        if self.group_effects.title() == englischer_text:
            self.group_effects.setTitle("Kartografische Optionen (aktiv in Modus 1 und Modus 2)")

        effects_layout = QVBoxLayout(self.group_effects)

        # ==============================================================================
        # Toggle 1 (formerly road base): renamed and moved lower in the layout
        # ==============================================================================
        self.cb_road_base = QCheckBox(self.tr("Straßen-Hierarchie & dicke Liniendesigns aktivieren"), self)
        self.cb_road_base.setChecked(self.config.get("enable_advanced_road_features", True))
        self.cb_road_base.stateChanged.connect(self.auto_save_settings)
        effects_layout.addWidget(self.cb_road_base)

        # ==============================================================================
        # Toggle 2: road names (density-optimized)
        # ==============================================================================
        self.cb_road_labels = QCheckBox(self.tr("Show Road Names (Density-Optimized)"), self)
        self.cb_road_labels.setChecked(self.config.get("enable_road_labels", True))
        self.cb_road_labels.stateChanged.connect(self.auto_save_settings)
        effects_layout.addWidget(self.cb_road_labels)

        # ==============================================================================
        # Toggle 3: building edge smoothing
        # ==============================================================================
        self.cb_building_smoothing = QCheckBox(self.tr("Enable Building Edge Smoothing"), self)
        self.cb_building_smoothing.setChecked(self.config.get("enable_building_edge_smoothing", True))
        self.cb_building_smoothing.stateChanged.connect(self.auto_save_settings)
        effects_layout.addWidget(self.cb_building_smoothing)

        # ==============================================================================
        # Toggle 4: 2.5D building drop shadow
        # ==============================================================================
        self.cb_building_shadow = QCheckBox(self.tr("Enable 2.5D Building Drop Shadows"), self)
        self.cb_building_shadow.setChecked(self.config.get("enable_building_drop_shadow", True))
        self.cb_building_shadow.stateChanged.connect(self.auto_save_settings)
        effects_layout.addWidget(self.cb_building_shadow)

        # ==============================================================================
        # Toggle 5: building labels (house numbers)
        # ==============================================================================
        self.cb_building_labels = QCheckBox(self.tr("Show Building Labels (House Numbers/Names)"), self)
        self.cb_building_labels.setChecked(self.config.get("enable_building_labels", True))
        self.cb_building_labels.stateChanged.connect(self.auto_save_settings)
        effects_layout.addWidget(self.cb_building_labels)

        # ==============================================================================
        # Toggle 6: area labels (forest/water)
        # ==============================================================================
        self.cb_landuse_labels = QCheckBox(self.tr("Show Landuse Labels (Forest/Water Spaced)"), self)
        self.cb_landuse_labels.setChecked(self.config.get("enable_landuse_labels", True))
        self.cb_landuse_labels.stateChanged.connect(self.auto_save_settings)
        effects_layout.addWidget(self.cb_landuse_labels)

        # Add the widget group to the main view
        self.main_layout.addWidget(self.group_effects)

        # ==============================================================================
        # --- Hidden engine housekeeping: force these to True in the background ---
        # ==============================================================================
        # Declare building base in memory, set it to True, and hide it completely
        self.cb_building_base = QCheckBox(self)
        self.cb_building_base.setChecked(True)
        self.cb_building_base.hide()

        # Declare point base in memory, set it to True, and hide it completely
        self.cb_point_base = QCheckBox(self)
        self.cb_point_base.setChecked(True)
        self.cb_point_base.hide()
        # ==============================================================================

        # --- Group 3: modular single-symbol styling (without extra columns) ---
        self.group_single = QGroupBox(self.tr("Custom Single Symbol Mappings"), self)
        single_main_layout = QVBoxLayout(self.group_single)

        control_layout = QHBoxLayout()
        self.btn_add = QPushButton("+", self)
        self.btn_add.setFixedWidth(40)
        self.btn_add.clicked.connect(self.add_mapping_row)
        control_layout.addWidget(self.btn_add)

        self.btn_remove = QPushButton("-", self)
        self.btn_remove.setFixedWidth(40)
        self.btn_remove.clicked.connect(self.remove_selected_row)
        control_layout.addWidget(self.btn_remove)
        control_layout.addStretch()
        single_main_layout.addLayout(control_layout)

        # --- Precisely aligned column header ---
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 2, 0, 2)

        lbl_sel = QLabel("", self);
        lbl_sel.setFixedWidth(25);
        header_layout.addWidget(lbl_sel)
        lbl_act = QLabel(self.tr("Active"), self);
        lbl_act.setFixedWidth(45);
        header_layout.addWidget(lbl_act)
        lbl_geom = QLabel(self.tr("Geometry"), self);
        lbl_geom.setFixedWidth(80);
        header_layout.addWidget(lbl_geom)
        lbl_val = QLabel(self.tr("OSM Value / Code"), self);
        lbl_val.setFixedWidth(120);
        header_layout.addWidget(lbl_val)
        lbl_sty = QLabel(self.tr("Style Name / SVG"), self);
        lbl_sty.setFixedWidth(120);
        header_layout.addWidget(lbl_sty)
        lbl_leg = QLabel(self.tr("Legend Label"), self);
        header_layout.addWidget(lbl_leg)
        single_main_layout.addLayout(header_layout)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(_qt_alignment("AlignTop"))
        self.scroll_area.setWidget(self.scroll_widget)
        single_main_layout.addWidget(self.scroll_area)

        self.main_layout.addWidget(self.group_single)

        self.mapping_rows = []
        self.radio_group = QButtonGroup(self)

        # ==============================================================================
        # Prepare and extend default values for custom single-symbol mappings
        # ==============================================================================
        import os
        dialog_dir = os.path.dirname(os.path.abspath(__file__))
        xml_test_pfad = os.path.join(dialog_dir, "styles", "style_symbols.xml")

        # The five fixed defaults that should always be present
        hardcoded_defaults = [
            {"active": True, "geom": "Line", "value": "motorway", "style": "autobahn", "label": "Autobahn"},
            {"active": True, "geom": "Line", "value": "tertiary", "style": "nebenstrasse", "label": "Nebenstraße"},
            {"active": True, "geom": "Polygon", "value": "apartments", "style": "wohngebaeude", "label": "Wohngebäude"},
            {"active": True, "geom": "Polygon", "value": "commercial", "style": "gewerbegebaeude",
             "label": "Gewerbe / Industrie"},
            {"active": True, "geom": "Point", "value": "hospital", "style": "hospital.svg", "label": "Krankenhaus"}
        ]

        # Load the current state from config.json
        initial_entries = self.config.get("custom_mappings", [])

        # Only add missing rows if the test XML exists:
        if os.path.exists(xml_test_pfad):
            if not isinstance(initial_entries, list) or len(initial_entries) == 0:
                initial_entries = hardcoded_defaults
            else:
                # Collect the OSM values that are already present in the config
                aktuell_vorhandene_values = []
                for m in initial_entries:
                    if isinstance(m, dict) and "value" in m:
                        # Normalize aggressively for whitespace and letter case
                        aktuell_vorhandene_values.append(str(m["value"]).strip().lower())

                # Now loop through the five defaults and add only what is truly missing
                for standard_zeile in hardcoded_defaults:
                    such_value = str(standard_zeile["value"]).strip().lower()

                    # If the OSM value (for example 'tertiary') is not yet in the list:
                    if such_value not in aktuell_vorhandene_values:
                        initial_entries.append(standard_zeile)

            self.config["custom_mappings"] = initial_entries
        else:
            # Fallback: if no XML is available, keep the last user state as-is
            if not isinstance(initial_entries, list) or len(initial_entries) == 0:
                initial_entries = hardcoded_defaults

        for entry in initial_entries:
            self.create_row_widget(entry)

        self.btn_close = QPushButton(self.tr("Close"), self)
        self.btn_close.clicked.connect(self.accept)
        self.main_layout.addWidget(self.btn_close)

        self.cb_point_base.setChecked(True)
        self.cb_point_base.hide()

        # Save once initially so the structure exists in memory
        self.auto_save_settings()

    def create_row_widget(self, data=None):
        project_style = QgsProject.instance().styleSettings().projectStyle()
        style_library = QgsStyle.defaultStyle()

        row_container = QWidget(self.scroll_widget)
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 2, 0, 2)

        radio_select = QRadioButton(row_container)
        radio_select.setFixedWidth(25)
        self.radio_group.addButton(radio_select)
        row_layout.addWidget(radio_select)

        is_active = data.get("active", True) if data else True
        style_name = data.get("style", "").strip() if data else ""

        style_exists = True
        if style_name and not style_name.lower().endswith(".svg"):
            in_project = (style_name in project_style.symbolNames()) if hasattr(project_style, "symbolNames") else False
            in_library = style_name in style_library.symbolNames()
            if not in_project and not in_library:
                style_exists = False
                is_active = False

        cb_active = QCheckBox(row_container)
        cb_active.setFixedWidth(45)
        cb_active.setChecked(is_active)
        cb_active.stateChanged.connect(self.auto_save_settings)
        row_layout.addWidget(cb_active)

        combo_geom = QComboBox(row_container)
        combo_geom.addItems(["Point", "Line", "Polygon"])
        combo_geom.setFixedWidth(80)
        if data: combo_geom.setCurrentText(data.get("geom", "Point"))
        combo_geom.currentTextChanged.connect(self.auto_save_settings)
        row_layout.addWidget(combo_geom)

        edit_value = QLineEdit(row_container)
        edit_value.setFixedWidth(120)
        if data: edit_value.setText(data.get("value", ""))
        edit_value.textChanged.connect(self.auto_save_settings)
        row_layout.addWidget(edit_value)

        edit_style = QLineEdit(row_container)
        edit_style.setFixedWidth(120)
        if data: edit_style.setText(style_name)
        edit_style.textChanged.connect(self.auto_save_settings)
        row_layout.addWidget(edit_style)

        edit_label = QLineEdit(row_container)
        if data: edit_label.setText(data.get("label", ""))
        edit_label.textChanged.connect(self.auto_save_settings)
        row_layout.addWidget(edit_label)

        if not style_exists:
            cb_active.setEnabled(False)
            combo_geom.setEnabled(False)
            edit_value.setEnabled(False)
            edit_style.setEnabled(False)
            edit_label.setEnabled(False)
            row_container.setToolTip(self.tr(f"Style '{style_name}' missing in QGIS! Row locked."))

        row_data = {
            "container": row_container, "radio": radio_select, "active": cb_active,
            "geom": combo_geom, "value": edit_value, "style": edit_style, "label": edit_label
        }
        self.mapping_rows.append(row_data)
        self.scroll_layout.addWidget(row_container)

    def add_mapping_row(self):
        self.create_row_widget()
        self.auto_save_settings()

    def remove_selected_row(self):
        target_row = None
        for row in self.mapping_rows:
            if row["radio"].isChecked():
                target_row = row
                break
        if target_row:
            self.mapping_rows.remove(target_row)
            self.radio_group.removeButton(target_row["radio"])
            self.scroll_layout.removeWidget(target_row["container"])
            target_row["container"].deleteLater()
            self.auto_save_settings()

    def auto_save_settings(self):
        if hasattr(self, 'style_engine') and self.style_engine:
            self.style_engine.enable_building_labels = self.cb_building_labels.isChecked()
            self.style_engine.enable_labels = self.cb_road_labels.isChecked()
            self.style_engine.enable_building_smoothing = self.cb_building_smoothing.isChecked()
            self.style_engine.enable_building_shadow = self.cb_building_shadow.isChecked()
            self.style_engine.enable_landuse_labels = self.cb_landuse_labels.isChecked()

            # ==============================================================================
            # --- Mirror the road-name flag to the class-level state ---
            # ==============================================================================
            from .style_engine import StyleEngine
            StyleEngine.enable_labels = self.cb_road_labels.isChecked()
            # Keep the remaining working building/landuse class-level guards in sync.
            StyleEngine.enable_landuse_labels = self.cb_landuse_labels.isChecked()
            StyleEngine.enable_building_labels = self.cb_building_labels.isChecked()
            StyleEngine.enable_building_smoothing = self.cb_building_smoothing.isChecked()
            StyleEngine.enable_building_shadow = self.cb_building_shadow.isChecked()
            StyleEngine.enable_advanced_road_features = self.cb_road_base.isChecked()

        # 2. Persist values into the config dict for QGIS
        self.config["road_style_mode"] = self.mode_combo.currentIndex()
        self.config["enable_advanced_road_features"] = self.cb_road_base.isChecked()
        self.config["enable_advanced_building_features"] = self.cb_building_base.isChecked()
        self.config["enable_advanced_point_features"] = self.cb_point_base.isChecked()
        self.config["enable_road_labels"] = self.cb_road_labels.isChecked()
        self.config["enable_building_edge_smoothing"] = self.cb_building_smoothing.isChecked()
        self.config["enable_building_drop_shadow"] = self.cb_building_shadow.isChecked()
        self.config["enable_building_labels"] = self.cb_building_labels.isChecked()
        self.config["enable_landuse_labels"] = self.cb_landuse_labels.isChecked()

        # 3. Read mappings from the GUI table
        extracted_mappings = []
        for row in self.mapping_rows:
            extracted_mappings.append({
                "active": row["active"].isChecked(),
                "geom": row["geom"].currentText(),
                "value": row["value"].text().strip(),
                "style": row["style"].text().strip(),
                "label": row["label"].text().strip()
            })
        self.config["custom_mappings"] = extracted_mappings

    def tr(self, message):
        # Use the in-memory switch directly in this dialog so no file access can block it.
        de_dict = {
            "Style Auto Plugin - Configuration": "Style Auto Plugin - Konfiguration",
            "Global Styling Mode (All Layers):": "Globaler Styling-Modus (Alle Layer):",
            "Mode 0: Pure Base Styling (JSON Rules)": "Modus 0: Reines Basis-Styling (JSON-Regeln)",
            "Mode 1: Pure Custom Single Styling (GUI List)": "Modus 1: Reines benutzerdefiniertes Einzelstyling (GUI-Liste)",
            "Mode 2: Combined Styling (Base + GUI List)": "Modus 2: Kombiniertes Styling (Basis + GUI-Liste)",
            "Base Styling Layers": "Basis-Styling-Layer",
            "Enable Base Roads Styling": "Basis-Straßenstyling aktivieren",
            "Enable Base Buildings Styling": "Basis-Gebäudestyling aktivieren",
            "Enable Base Points Styling (POIs)": "Basis-Punktstyling (POIs) aktivieren",
            "Cartographic Options (active in Mode 1 and Mode 2)": "Kartografische Optionen (aktiv in Modus 1 und Modus 2)",
            "Show Road Names (Density-Optimized)": "Straßennamen anzeigen (Dichte-optimiert)",
            "Cartographic Options": "Kartografische Optionen",
            "Enable Building Edge Smoothing": "Gebäudekanten-Glättung aktivieren",
            "Enable 2.5D Building Drop Shadows": "2.5D Gebäude-Schlagschatten aktivieren",
            "Show Building Labels (House Numbers/Names)": "Gebäudebeschriftung anzeigen (Hausnummern/Namen)",
            "Show Landuse Labels (Forest/Water Spaced)": "Flächenbeschriftung anzeigen (Wald/Wasser mit Abstand)",
            "Custom Single Symbol Mappings": "Benutzerdefinierte Einzelstil-Zuweisungen",
            "Active": "Aktiv",
            "Geometry": "Geometrie",
            "OSM Value / Code": "OSM-Wert / Code",
            "Style Name / SVG": "Stilname / SVG",
            "Legend Label": "Legendentext",
            "Style missing in QGIS! Row locked.": "Stil fehlt in QGIS! Zeile gesperrt.",
            "Close": "Schließen"
        }
        system_lang = QLocale.system().name().lower()
        if system_lang.startswith("de") or "de_" in system_lang:
            return de_dict.get(message, message)
        return QCoreApplication.translate('StyleAutoPluginDialog', message)
