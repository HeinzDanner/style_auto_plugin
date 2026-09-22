import os
import qgis.utils

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,  # --- FIX: Hier das Kern-Wort für die Log-Level (Critical, Warning, Info) einfügen! ---
    QgsProject,
    QgsFeatureRequest,
    QgsStyle,
    QgsUnitTypes,
    QgsMapLayerType,
    # --- Symbologie & Effekte ---
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsSimpleFillSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsSvgMarkerSymbolLayer,
    QgsDropShadowEffect,
    QgsEffectStack,
    # --- Renderer ---
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    # --- Beschriftung (Labeling) ---
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsTextFormat,
    QgsTextBufferSettings,
    QgsSimpleLineSymbolLayer,
    QgsMessageLog,
    QgsPaintEffectRegistry,
    QgsApplication
)



# ==============================================================================
# GLOBALER GEOFABRIK-ÜBERSETZUNGS-JOKER (Für Straßen, Gebäude und Punkte)
# ==============================================================================
GEOFABRIK_CODE_MAP = {
    # === STRASSEN / WEGE (geom: Line) ===
    "motorway": "5111",        "motorway_link": "5112",
    "trunk": "5113",           "trunk_link": "5114",
    "primary": "5121",         "primary_link": "5123",
    "secondary": "5141",       "secondary_link": "5124",
    "tertiary": "5122",        "tertiary_link": "5125",
    "residential": "5153",     "living_street": "5152",
    "service": "5115",         "unclassified": "5151",
    "track": "5131",           "track_grade1": "5132",
    "track_grade2": "5133",    "track_grade3": "5134",
    "pedestrian": "5114",      "footway": "5121",
    "cycleway": "5122",        "path": "5115",

    # === GEBÄUDE / POLYGONE (geom: Polygon) ===
    "apartments": "1500",      "house": "1501",
    "detached": "1502",        "semidetached_house": "1503",
    "terrace": "1504",         "bungalow": "1505",
    "residential": "1506",     "commercial": "1510",
    "industrial": "1511",      "retail": "1512",
    "school": "1520",          "kindergarten": "1521",
    "hospital": "1522",        "civic": "1523",
    "public": "1524",          "church": "1530", "garage": "1500",
     "garages": "1500",
     "shed": "1500",
     "roof": "1500",
     "carport": "1500",
     "service": "1511",
     "hut": "1500",
     "cabin": "1500",
        "": "1500","none": "1500","null": "1500","NULL": "1500",

    # === POIS / PUNKTE (geom: Point) ===
    "station": "2001",         "subway_entrance": "2002",
    "bus_stop": "2003",        "pier": "2004",
    "airport": "2041",         "airfield": "2042",
    "hospital": "2101",        "pharmacy": "2102",
    "clinic": "2103",          "doctors": "2104",
    "dentist": "2105",         "veterinary": "2106",
    "police": "2111",          "fire_station": "2112",
    "post_office": "2113",     "townhall": "2114",
    "courthouse": "2115",      "embassy": "2116",
    "school": "2121",          "kindergarten": "2122",
    "university": "2123",      "college": "2124",
    "library": "2125",         "theatre": "2181",
    "cinema": "2182",          "museum": "2183",
    "arts_centre": "2184",     "artwork": "2185",
    "hotel": "2201",           "motel": "2202",
    "guesthouse": "2203",      "hostel": "2204",
    "camp_site": "2205",       "restaurant": "2301",
    "cafe": "2302",            "fast_food": "2303",
    "pub": "2304",             "bar": "2305",
    "food_court": "2306",      "biergarten": "2307",
    "supermarket": "2401",     "convenience": "2402",
    "bakery": "2403",          "mall": "2404",
    "bank": "2501",            "atm": "2502"
}

class StyleEngine:
    ROAD_SEMANTIC_VALUES = {
        "motorway", "motorway_link",
        "trunk", "trunk_link",
        "primary", "primary_link",
        "secondary", "secondary_link",
        "tertiary", "tertiary_link",
        "residential", "living_street",
        "pedestrian", "service",
        "track", "track_grade1", "track_grade2", "track_grade3", "track_grade4", "track_grade5",
        "unclassified", "path", "footway", "cycleway", "bridleway", "steps"
    }
    enable_building_labels = True
    enable_labels = True
    enable_building_smoothing = True
    enable_building_shadow = True
    enable_landuse_labels = True
    enable_advanced_road_features = True

    def __init__(self, logger=None, config=None):
        self.logger = logger
        self.config = config
        self._symbol_cache = {}

        # --- ABSOLUT UNABHÄNGIGE FLAGS (Kernelemente) ---
        self.enable_labels = False  # Für Straßen-Beschriftung
        self.enable_building_labels = False  # Für Gebäude-Beschriftung
        self.enable_building_smoothing = True  # Standard: Glättung an
        self.enable_building_shadow = True  # Standard: Schatten an
        self.enable_landuse_labels = True  # Standard: Landuse an

        # Einmalig synchronisieren, falls beim Start eine Config existiert
        if self.config:
            self.sync_runtime_bools_from_config(self.config)

    def log(self, message):
        if self.logger:
            self.logger(message)

    def sync_runtime_bools_from_config(self, config=None):
        cfg = config if config is not None else self.config
        raw = None
        source = "missing"

        if isinstance(cfg, dict) and "enable_building_labels" in cfg:
            raw = cfg["enable_building_labels"]
            source = "dict"
        elif (
                cfg is not None
                and hasattr(cfg, "dict")
                and isinstance(cfg.dict, dict)
                and "enable_building_labels" in cfg.dict
        ):
            raw = cfg.dict["enable_building_labels"]
            source = "dict-container"
        elif cfg is not None and hasattr(cfg, "enable_building_labels"):
            raw = getattr(cfg, "enable_building_labels")
            source = "attr"

        # --- DER RETTENDE FIX: Wenn raw None ist, nimm den bestehenden Zustand! ---
        if raw is None:
            normalized = self.enable_building_labels
        elif isinstance(raw, bool):
            normalized = raw
        elif isinstance(raw, str):
            normalized = raw.strip().lower() in ("1", "true", "yes", "on", "ja")
        else:
            normalized = bool(raw)

        self.enable_building_labels = normalized

        return normalized

    def _result(
        self,
        success,
        message="",
        level="info",
        source="",
        profile_id="",
        ruleset_name="",
        field_name="",
        missing_values=None
    ):
        return {
            "success": bool(success),
            "message": message,
            "level": level,
            "source": source,
            "profile_id": profile_id,
            "ruleset_name": ruleset_name,
            "field_name": field_name,
            "missing_values": missing_values or [],
        }

    def _get_attr(self, obj, *names, default=None):
        for name in names:
            if hasattr(obj, name):
                return getattr(obj, name)
        return default

    def get_layer_geometry_type_name(self, layer):
        if not layer or layer.type() != QgsMapLayerType.VectorLayer:
            return None

        geometry_type = layer.geometryType()
        if geometry_type == 0:
            return "point"
        if geometry_type == 1:
            return "line"
        if geometry_type == 2:
            return "polygon"
        return None

    def get_layer_field_names_lower(self, layer):
        return {field.name().lower() for field in layer.fields()}

    def get_layer_field_name_map(self, layer):
        return {field.name().lower(): field.name() for field in layer.fields()}

    def find_existing_field_name(self, layer, candidate_name):
        if not candidate_name:
            return None

        candidate_lower = str(candidate_name).lower()
        for field in layer.fields():
            if field.name().lower() == candidate_lower:
                return field.name()
        return None

    def get_unique_field_values_lower(self, layer, field_name, limit=50):
        existing_field_name = self.find_existing_field_name(layer, field_name)
        if not existing_field_name:
            return set()

        field_index = layer.fields().indexFromName(existing_field_name)
        if field_index == -1:
            return set()

        try:
            values = layer.uniqueValues(field_index, limit)
        except TypeError:
            values = layer.uniqueValues(field_index)

        return {
            str(value).strip().lower()
            for value in values
            if value is not None and str(value).strip() != ""
        }

    def normalize_list_lower(self, values):
        if not values:
            return []
        return [str(v).strip().lower() for v in values if v is not None and str(v).strip() != ""]

    def resolve_qml_path(self, plugin_dir, qml_path):
        if not qml_path:
            return ""
        if plugin_dir and not str(qml_path).strip():
            return ""
        if plugin_dir and not qml_path.startswith("/") and ":" not in qml_path:
            return os.path.normpath(os.path.join(plugin_dir, qml_path))
        return qml_path

    # ---------------------------------------------------------------------
    # Semantic field detection
    # ---------------------------------------------------------------------

    def find_semantic_field_by_values(self, layer, expected_values, min_hits=4, max_fields=50, value_limit=50):
        expected = {str(v).strip().lower() for v in expected_values if str(v).strip()}
        if not expected:
            return None

        best_field = None
        best_hits = []
        best_ratio = 0.0

        fields = list(layer.fields())[:max_fields]

        for field in fields:
            field_name = field.name()
            values = self.get_unique_field_values_lower(layer, field_name, limit=value_limit)
            if not values:
                continue

            hits = sorted(expected.intersection(values))
            if not hits:
                continue

            ratio = len(hits) / max(1, len(values))

            if len(hits) > len(best_hits):
                best_field = field_name
                best_hits = hits
                best_ratio = ratio
            elif len(hits) == len(best_hits) and ratio > best_ratio:
                best_field = field_name
                best_hits = hits
                best_ratio = ratio

        if best_field and len(best_hits) >= min_hits:
            return {
                "field_name": best_field,
                "hits": best_hits,
                "score": len(best_hits),
                "ratio": best_ratio
            }

        return None

    def detect_best_street_field(self, layer):
        if self.get_layer_geometry_type_name(layer) != "line":
            return None

        return self.find_semantic_field_by_values(
            layer=layer,
            expected_values=self.ROAD_SEMANTIC_VALUES,
            min_hits=4,
            max_fields=50,
            value_limit=50
        )

    # ---------------------------------------------------------------------
    # Match scoring
    # ---------------------------------------------------------------------
    def detect_best_building_field(self, layer, config=None, sample_limit=120):
        if not layer:
            return None

        fields = layer.fields()
        candidates = [name for name in ("type", "building", "code", "fclass") if fields.indexOf(name) >= 0]
        if not candidates:
            return None

        config_mappings = []
        if config:
            if isinstance(config, dict):
                config_mappings = config.get("custom_mappings", [])
            else:
                config_mappings = getattr(config, "custom_mappings", [])

        expected_text_values = set()
        expected_code_values = set()

        if isinstance(config_mappings, list):
            for entry in config_mappings:
                if not isinstance(entry, dict):
                    continue
                if not entry.get("active", True):
                    continue
                if str(entry.get("geom", "")).lower() != "polygon":
                    continue

                gui_value = str(entry.get("value", "")).strip().lower()
                if not gui_value:
                    continue

                expected_text_values.add(gui_value)
                code_val = GEOFABRIK_CODE_MAP.get(gui_value)
                if code_val:
                    expected_code_values.add(str(code_val).strip())

        best_field = None
        best_score = -10 ** 9

        for field_name in candidates:
            idx = fields.indexOf(field_name)
            if idx < 0:
                continue

            try:
                raw_vals = layer.uniqueValues(idx, sample_limit)
            except TypeError:
                raw_vals = layer.uniqueValues(idx)

            values = []
            for v in raw_vals:
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    values.append(s)

            values_lower = {v.lower() for v in values}
            distinct_count = len(values_lower)

            score = 0

            if field_name == "type":
                score += 50
            elif field_name == "building":
                score += 35
            elif field_name == "code":
                score += 20
            elif field_name == "fclass":
                score += 5

            if distinct_count > 1:
                score += min(distinct_count, 20)

            if field_name in ("type", "building", "fclass"):
                text_hits = len(values_lower.intersection(expected_text_values))
                score += text_hits * 10

            if field_name == "code":
                code_hits = len({v for v in values if v in expected_code_values})
                score += code_hits * 12

            if values_lower == {"building"}:
                score -= 100

            if values_lower in ({"yes"}, {"building", "yes"}):
                score -= 40

            semantic_hits = len(values_lower.intersection({
                "apartments", "house", "detached", "residential", "commercial",
                "industrial", "retail", "school", "hospital", "church", "garage",
                "garages", "roof", "shed", "cabin", "hut", "bungalow", "terrace"
            }))
            score += semantic_hits * 6

            if score > best_score:
                best_score = score
                best_field = field_name

        return best_field

    def score_match(self, layer, match):
        if not match:
            return -1, ["missing match config"], None

        score = 0
        reasons = []
        detected_field_name = None

        layer_name = (layer.name() or "").strip().lower()
        layer_fields_lower = self.get_layer_field_names_lower(layer)
        layer_geometry = self.get_layer_geometry_type_name(layer)

        geometry_type = (self._get_attr(match, "geometry_type", "geometrytype", default="") or "").strip().lower()
        if geometry_type:
            if layer_geometry == geometry_type:
                score += 3
                reasons.append("geometry={0}".format(geometry_type))
            else:
                return -1, ["geometry mismatch: {0} != {1}".format(layer_geometry, geometry_type)], None

        field_hints = self.normalize_list_lower(self._get_attr(match, "field_hints", default=[]))
        matching_fields = [field_name for field_name in field_hints if field_name in layer_fields_lower]

        if matching_fields:
            score += 2
            reasons.append("field_hints_bonus={0}".format(matching_fields))
            detected_field_name = matching_fields[0]

        semantic_match = None
        if layer_geometry == "line":
            semantic_match = self.detect_best_street_field(layer)

        if semantic_match:
            semantic_field = semantic_match["field_name"]
            semantic_hits = semantic_match["hits"]
            semantic_score = min(8, semantic_match["score"] + 2)
            score += semantic_score
            reasons.append(
                "semantic_field={0}, hits={1}(+{2})".format(
                    semantic_field, semantic_hits, semantic_score
                )
            )
            detected_field_name = semantic_field
        else:
            if field_hints and not matching_fields:
                reasons.append("no field_hints matched: {0}".format(field_hints))

        preferred_field_order = self.normalize_list_lower(self._get_attr(match, "preferred_field_order", default=[]))
        if preferred_field_order:
            for index, field_name in enumerate(preferred_field_order):
                if field_name in layer_fields_lower:
                    bonus = max(1, len(preferred_field_order) - index)
                    score += bonus
                    reasons.append("preferred_field={0}(+{1})".format(field_name, bonus))
                    if not detected_field_name:
                        detected_field_name = field_name
                    break

        name_hints = self.normalize_list_lower(self._get_attr(match, "name_hints", default=[]))
        if not name_hints:
            legacy_name_pattern = (self._get_attr(match, "layer_name_pattern", "layernamepattern", default="") or "").strip()
            if legacy_name_pattern:
                name_hints = [legacy_name_pattern.lower()]

        if name_hints and any(name_hint in layer_name for name_hint in name_hints):
            score += 1
            reasons.append("name_hint(+1)")

        min_match_score = int(self._get_attr(match, "min_match_score", default=1) or 1)
        if score < min_match_score:
            return -1, reasons + ["score {0} < min_match_score {1}".format(score, min_match_score)], None

        # HIER kommt der neue Block hin:
        if detected_field_name:
            bonus, bonus_reasons = self.score_field_values_for_layer_type(layer, detected_field_name)
            score += bonus
            reasons.extend(bonus_reasons)

        return score, reasons, detected_field_name

    # ---------------------------------------------------------------------
    # Profile matching
    # ---------------------------------------------------------------------

    def find_style_profile(self, layer, config):
        style_profiles = getattr(config, "style_profiles", None)
        if not style_profiles:
            return None, None

        matches = []

        for profile in style_profiles:
            if not getattr(profile, "enabled", False):
                continue

            match = getattr(profile, "match", None)
            if not match:
                continue

            score, reasons, detected_field_name = self.score_match(layer, match)
            if score < 0:
                continue

            total_score = score + int(getattr(profile, "priority", 0) or 0)
            matches.append((total_score, profile, reasons, detected_field_name))

        if not matches:
            return None, None

        matches.sort(key=lambda item: item[0], reverse=True)
        chosen_score, chosen_profile, chosen_reasons, detected_field_name = matches[0]
        return chosen_profile, detected_field_name

    def score_field_values_for_layer_type(self, layer, field_name):
        """
        Bonus-Score für eindeutige Landuse/Building-Fälle basierend auf Attributwerten.
        """
        provider = layer.dataProvider()
        field_index = layer.fields().indexOf(field_name)
        if field_index < 0:
            return 0, []

        unique_values = provider.uniqueValues(field_index)
        reasons = []
        bonus = 0

        # Nur eindeutige Fälle verwenden
        landuse_values = {"forest", "meadow", "farmland", "industrial"}
        building_values = {"school", "church", "hospital", "apartments", "house"}

        if any(v in landuse_values for v in unique_values):
            bonus += 2
            reasons.append("value_hint_landuse(+2)")
        if any(v in building_values for v in unique_values):
            bonus += 2
            reasons.append("value_hint_buildings(+2)")

        return bonus, reasons

    # ---------------------------------------------------------------------
    # Ruleset matching
    # ---------------------------------------------------------------------

    def _build_match_from_legacy_ruleset(self, layerruleset):
        class MatchAdapter:
            pass

        match = MatchAdapter()
        match.geometry_type = self._get_attr(layerruleset, "geometrytype", "geometry_type", default=None)

        field_rulesets = getattr(layerruleset, "fieldrulesets", []) or []
        field_names = [
            self._get_attr(fieldruleset, "fieldname", "field_name", default=None)
            for fieldruleset in field_rulesets
            if getattr(fieldruleset, "enabled", False)
        ]
        field_names = [name for name in field_names if name]

        match.field_hints = field_names
        match.preferred_field_order = field_names
        match.value_hints = []
        legacy_name_pattern = self._get_attr(layerruleset, "layernamepattern", "layer_name_pattern", default="")
        match.name_hints = [legacy_name_pattern.lower()] if legacy_name_pattern else []
        match.min_match_score = 1
        return match

    def find_layer_ruleset(self, layer, config):
        layer_rulesets = getattr(config, "layerrulesets", None) or []
        if not layer_rulesets:
            return None, None

        matches = []

        for layerruleset in layer_rulesets:
            if not getattr(layerruleset, "enabled", False):
                continue

            match = getattr(layerruleset, "match", None)
            used_legacy = False
            if not match:
                match = self._build_match_from_legacy_ruleset(layerruleset)
                used_legacy = True

            score, reasons, detected_field_name = self.score_match(layer, match)

            pattern = self._get_attr(layerruleset, "layernamepattern", "layer_name_pattern", default="")

            if score < 0:
                continue

            total_score = score + int(getattr(layerruleset, "priority", 0) or 0)
            matches.append((total_score, layerruleset, reasons, detected_field_name))

        if not matches:
            return None, None

        matches.sort(key=lambda item: item[0], reverse=True)
        _, chosen_ruleset, chosen_reasons, detected_field_name = matches[0]
        return chosen_ruleset, detected_field_name

    def get_matching_field_ruleset(self, layer, layerruleset, preferred_field_name=None):
        if not layerruleset:
            return None

        if preferred_field_name:
            for fieldruleset in getattr(layerruleset, "fieldrulesets", []):
                if not getattr(fieldruleset, "enabled", False):
                    continue

                field_name = self._get_attr(fieldruleset, "fieldname", "field_name", default=None)
                if field_name and field_name.lower() == preferred_field_name.lower():
                    return fieldruleset

        layer_field_names_lower = self.get_layer_field_names_lower(layer)
        matching_field_rulesets = []

        for fieldruleset in getattr(layerruleset, "fieldrulesets", []):
            if not getattr(fieldruleset, "enabled", False):
                continue

            field_name = self._get_attr(fieldruleset, "fieldname", "field_name", default=None)
            if field_name and field_name.lower() in layer_field_names_lower:
                matching_field_rulesets.append(fieldruleset)

        if matching_field_rulesets:
            matching_field_rulesets.sort(
                key=lambda ruleset: int(getattr(ruleset, "priority", 0) or 0),
                reverse=True
            )
            return matching_field_rulesets[0]

        semantic_match = self.detect_best_street_field(layer)
        if semantic_match:
            semantic_field_name = semantic_match["field_name"]
            fallback = None
            fallback_priority = -999999

            for fieldruleset in getattr(layerruleset, "fieldrulesets", []):
                if not getattr(fieldruleset, "enabled", False):
                    continue

                field_name = self._get_attr(fieldruleset, "fieldname", "field_name", default=None)
                if not field_name:
                    continue

                priority = int(getattr(fieldruleset, "priority", 0) or 0)
                if priority > fallback_priority:
                    fallback = fieldruleset
                    fallback_priority = priority

            if fallback:
                setattr(fallback, "_semantic_target_field_name", semantic_field_name)
                return fallback

        return None

    def create_line_symbol(self, style_def):
        pen_map = {
            "solid": "solid",
            "dash": "dash",
            "dot": "dot"
        }
        key = ("line", style_def.color, style_def.width, style_def.penstyle)
        # aus Cache holen
        symbol = self._symbol_cache.get(key)
        if symbol is not None:
            return symbol.clone()

        # neu bauen und cachen
        symbol = QgsLineSymbol.createSimple({
            "color": style_def.color,
            "width": str(style_def.width),
            "penstyle": pen_map.get(style_def.penstyle, "solid")
        })
        self._symbol_cache[key] = symbol
        return symbol.clone()

    def create_fill_symbol(self, style_def):
        key = ("fill", style_def.color, style_def.width, style_def.penstyle)
        symbol = self._symbol_cache.get(key)
        if symbol is not None:
            return symbol.clone()

        # hier deine bestehende Erzeugung
        symbol = QgsFillSymbol.createSimple({
            "color": style_def.color,
            "outline_width": str(style_def.width),
            "outline_style": style_def.penstyle,
        })
        self._symbol_cache[key] = symbol
        return symbol.clone()

    def set_categorized_renderer(self, layer, field_name, categories):
        renderer = QgsCategorizedSymbolRenderer(field_name, categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return True

    def find_missing_values(self, layer, fieldruleset):
        semantic_field_name = getattr(fieldruleset, "_semantic_target_field_name", None)
        field_name = semantic_field_name or self._get_attr(fieldruleset, "fieldname", "field_name", default=None)

        existing_field_name = self.find_existing_field_name(layer, field_name)
        if not existing_field_name:
            return None

        field_index = layer.fields().indexFromName(existing_field_name)
        if field_index == -1:
            return None

        layer_values = {
            str(value)
            for value in layer.uniqueValues(field_index)
            if value is not None and str(value).strip() != ""
        }

        configured_values = {
            str(rule.value)
            for rule in fieldruleset.rules
            if getattr(rule, "enabled", False)
        }

        return sorted(layer_values - configured_values)

    def get_distinct_field_values(self, layer, field_name):
        idx = layer.fields().indexFromName(field_name)
        if idx < 0:
            return []

        values = set()
        for f in layer.getFeatures():
            v = f[idx]
            # None/NULL ignorieren
            if v is None:
                continue
            values.add(v)

        return list(values)

    def apply_categorized_renderer_with_fallback(self, layer, fieldruleset, detected_field_name=None):
        missing_values=''
        if not fieldruleset or not getattr(fieldruleset, "enabled", False):
            return False

        layer_geometry = self.get_layer_geometry_type_name(layer)

        # WICHTIG: Feldname bestimmen
        existing_field_name = detected_field_name or fieldruleset.field_name
        if not existing_field_name:
            return False

        layer_values = self.get_distinct_field_values(layer, existing_field_name)
        if not layer_values:
            return False

        style_by_value = {
            str(rule.value): rule
            for rule in fieldruleset.rules
            if getattr(rule, "enabled", False)
        }

        compact = getattr(self.config, "compactlegend", True)
        categories = []

        if compact:
            """
            normal_categories = []
            other_values = []
            null_count = 0

            for raw_value in sorted(layer_values, key=lambda x: str(x)):
                if raw_value is None or str(raw_value).strip() == "":
                    null_count += 1
                    continue

                value = str(raw_value)

                if value in style_by_value:
                    value_rule = style_by_value[value]
                    if layer_geometry == "polygon":
                        symbol = self.create_fill_symbol(value_rule.style)
                    else:
                        symbol = self.create_line_symbol(value_rule.style)

                    label = value_rule.label if value_rule.label else value_rule.value
                    cat = QgsRendererCategory(value, symbol, label)
                    normal_categories.append(cat)
                else:
                    other_values.append(value)

            categories = normal_categories

            fallback_style = getattr(fieldruleset, "fallbackstyle", None)
            if fallback_style is not None and (other_values or null_count > 0):
                if layer_geometry == "polygon":
                    fb_symbol = self.create_fill_symbol(fallback_style)
                else:
                    fb_symbol = self.create_line_symbol(fallback_style)

                max_items = 10
                shown_values = other_values[:max_items]
                label_parts = []

                if shown_values:
                    label_parts.append(", ".join(shown_values))
                    if len(other_values) > max_items:
                        label_parts.append("…")

                if null_count > 0:
                    label_parts.append(f"{null_count} × NULL")

                label = "[F] " + "; ".join(label_parts)

                fb_cat = QgsRendererCategory("__fallback__", fb_symbol, label)
                categories.append(fb_cat)
        """
        else:
            for raw_value in sorted(layer_values, key=lambda x: str(x)):
                if raw_value is None or str(raw_value).strip() == "":
                    fallback_style = getattr(fieldruleset, "fallbackstyle", None)
                    if fallback_style is None:
                        continue
                    symbol = self.create_fill_symbol(
                        fallback_style) if layer_geometry == "polygon" else self.create_line_symbol(fallback_style)
                    label = "[F] NULL"
                else:
                    value = str(raw_value)
                    if value in style_by_value:
                        value_rule = style_by_value[value]
                        symbol = self.create_fill_symbol(
                            value_rule.style) if layer_geometry == "polygon" else self.create_line_symbol(
                            value_rule.style)
                        label = value_rule.label if value_rule.label else value_rule.value
                    else:
                        fallback_style = getattr(fieldruleset, "fallbackstyle", None)
                        if fallback_style is None:
                            continue
                        symbol = self.create_fill_symbol(
                            fallback_style) if layer_geometry == "polygon" else self.create_line_symbol(fallback_style)
                        label = f"[F] {value}"

                cat = QgsRendererCategory(str(raw_value) if raw_value is not None else "", symbol, label)
                categories.append(cat)

        if not categories:
            return False

        def _fallback_key(cat):
            # Fallbacks sollen nach hinten:
            # True > False beim Sortieren, also 1 für Fallback, 0 für normal
            is_fallback = cat.label().startswith("[F]")
            return (is_fallback, str(cat.value()))

        categories.sort(key=_fallback_key)
        return self.set_categorized_renderer(layer, existing_field_name, categories)

    def get_symbol_for_value(self, geometry_type, fieldruleset, value):
        value = str(value)
        style_by_value = {
            str(rule.value): rule
            for rule in fieldruleset.rules
            if getattr(rule, "enabled", False)
        }

        if value in style_by_value:
            style_def = style_by_value[value].style
        else:
            style_def = getattr(fieldruleset, "fallbackstyle", None)
            if style_def is None:
                return None

        if geometry_type == "polygon":
            return self.create_fill_symbol(style_def)
        else:
            return self.create_line_symbol(style_def)

    def apply_qml_style(self, layer, qml_path):
        if not qml_path:
            return False, "Kein qml_path angegeben."

        # ==============================================================================
        # --- 1. SCHRITT: BLITZSCHNELLER XML-PRÜFER (Killt die 10 Sekunden Wartezeit) ---
        # ==============================================================================
        if qml_path and os.path.exists(qml_path) and "roads_fclass.qml" in str(qml_path):
            try:
                with open(qml_path, 'r', encoding='utf-8', errors='ignore') as f:
                    erste_zeile = f.readline()

                # Wenn die Datei korrupt ist (Zeile 1 kaputt), erkennen wir das in 0ms!
                if not erste_zeile or "<" not in erste_zeile:
                    # Text-Meldung restlos entfernt – der blitzschnelle Absturzschutz bleibt voll aktiv!
                    return False, "Datei ist korrupt."
            except Exception:
                pass

        # ==============================================================================
        # --- 2. SCHRITT: DIE SAUBERE GUI-REISSLEINE (Falls der Haken AUS ist) ---
        # ==============================================================================
        if qml_path and "roads_fclass.qml" in str(qml_path):
            # Wir prüfen direkt den echten Grafik-Haken aus dem globalen Klassen-RAM
            road_base_aktiv = getattr(StyleEngine, "enable_advanced_road_features", True)

            # Wenn der Schalter im Dialog AUS ist:
            if road_base_aktiv is False:
                # Text-Ausgabe restlos entfernt, die Hänger-Blockade bleibt unzerstörbar!
                return False, "Laden vom Master-Schalter blockiert."
        # ==============================================================================
        # Ab hier läuft dein originaler Code von Page 16 völlig unverändert weiter:
        # ==============================================================================
        result = layer.loadNamedStyle(qml_path)
        success = False
        detail = ""

        if isinstance(result, tuple):
            if len(result) == 2:
                detail, success = result
            elif len(result) == 3:
                detail = result[1] if len(result) > 1 else ""
                success = bool(result[0])
            else:
                success = bool(result[0])
        else:
            success = bool(result)

        if not success:
            if not detail:
                detail = "QML konnte nicht geladen werden."

            # Sicherheitsnetz: Wenn das Laden gewollt blockiert oder wegen Korruption abgebrochen wurde,
            # unterdrücken wir das rote CRITICAL im Log, damit das Plugin sauber weiterläuft.
            if qml_path and "roads_fclass.qml" in str(qml_path):
                return False, detail

            return False, detail

        layer.triggerRepaint()
        return True, detail

    def apply_profile_rules(self, layer, profile, detected_field_name=None):
        field_ruleset = getattr(profile, "field_ruleset", None)
        if not field_ruleset:
            return self._result(
                False,
                message="Profil-Regeln fehlen.",
                level="warning",
                source="profile_rules",
                profile_id=getattr(profile, "id", "")
            )

        if detected_field_name:
            setattr(field_ruleset, "_semantic_target_field_name", detected_field_name)

        field_name = detected_field_name or self._get_attr(field_ruleset, "fieldname", "field_name", default="")
        missing_values = self.find_missing_values(layer, field_ruleset)

        if missing_values is None:
            return self._result(
                False,
                message="Feld '{0}' nicht im Layer gefunden.".format(field_name),
                level="warning",
                source="profile_rules",
                profile_id=getattr(profile, "id", ""),
                field_name=field_name
            )

        success = self.apply_categorized_renderer_with_fallback(layer, field_ruleset)
        if not success:
            return self._result(
                False,
                message="Profil-Regelstil konnte nicht angewendet werden.",
                level="warning",
                source="profile_rules",
                profile_id=getattr(profile, "id", ""),
                field_name=field_name,
                missing_values=missing_values
            )

        msg = "Regelstil aus Profil '{0}' angewendet auf Feld '{1}'.".format(
            getattr(profile, "label", "") or getattr(profile, "id", ""),
            field_name
        )
        if missing_values:
            msg += " {0} nicht konfigurierte Werte mit Fallback.".format(len(missing_values))

        return self._result(
            True,
            message=msg,
            level="info",
            source="profile_rules",
            profile_id=getattr(profile, "id", ""),
            field_name=field_name,
            missing_values=missing_values
        )

    def apply_layer_ruleset_style(self, layer, layerruleset, detected_field_name=None):
        if layerruleset is None:
            return self._result(
                False,
                message="Kein passender Layer-Regelsatz gefunden.",
                level="warning",
                source="ruleset"
            )

        field_ruleset = self.get_matching_field_ruleset(layer, layerruleset, preferred_field_name=detected_field_name)
        if field_ruleset is None:
            return self._result(
                False,
                message="Kein passender Feld-Regelsatz gefunden.",
                level="warning",
                source="ruleset"
            )

        semantic_target = getattr(field_ruleset, "_semantic_target_field_name", None)
        field_name = semantic_target or detected_field_name or self._get_attr(field_ruleset, "fieldname", "field_name", default="")

        missing_values = self.find_missing_values(layer, field_ruleset)

        if missing_values is None:
            return self._result(
                False,
                message="Feld '{0}' nicht im Layer gefunden.".format(field_name),
                level="warning",
                source="ruleset",
                field_name=field_name
            )

        success = self.apply_categorized_renderer_with_fallback(layer, field_ruleset)

        if not success:
            return self._result(
                False,
                message="Regelsatz konnte nicht angewendet werden.",
                level="warning",
                source="ruleset",
                field_name=field_name,
                missing_values=missing_values
            )

        msg = "Regelstil aus Ruleset angewendet auf Feld '{0}'.".format(field_name)
        if missing_values:
            msg += " {0} nicht konfigurierte Werte mit Fallback.".format(len(missing_values))

        return self._result(
            True,
            message=msg,
            level="info",
            source="ruleset",
            field_name=field_name,
            missing_values=missing_values
        )

    def apply_best_style(self, layer, config, plugin_dir=None):
        if layer is None:
            return self._result(False, "Kein Layer übergeben.", level="warning")

        # ==============================================================================
        # --- DIE MASTER-REISSLEINE: Abfang-Logik für den Straßen-Basis-Haken ---
        # ==============================================================================
        geom_type = self.get_layer_geometry_type_name(layer)

        # Wenn der aktuelle Layer eine Linie (Straße) ist:
        if geom_type == "line":
            road_base_aktiv = True
            if config:
                if isinstance(config, dict):
                    road_base_aktiv = config.get("enable_advanced_road_features", True)
                else:
                    road_base_aktiv = getattr(config, "enable_advanced_road_features", True)

            # WENN DER HAKEN "Basis-Straßenstyling aktivieren" AUS IST:
            if road_base_aktiv is False:
                # 1. Alle Texte und Straßennamen sofort komplett löschen
                layer.setLabelsEnabled(False)
                layer.setLabeling(None)

                # 2. Die kaputte QML umgehen und die Straßen per Code auf eine feine graue Linie setzen
                from qgis.core import QgsSingleSymbolRenderer, QgsLineSymbol
                standard_symbol = QgsLineSymbol.createSimple({
                    'color': '#aaaaaa',
                    'width': '0.26',
                    'penstyle': 'solid'
                })
                layer.setRenderer(QgsSingleSymbolRenderer(standard_symbol))

                layer.triggerRepaint()
                return self._result(True, "Straßen im Standard-Look belassen (Basis aus).", level="info")

        # ==============================================================================
        # Hier läuft dein originaler Code von Page 19 (Zeile 11) völlig unverändert weiter:
        # ==============================================================================
        # 1. ZUERST: Den Modus sicher deklarieren (Verhindert den NameError!)
        try:
            mode = int(getattr(config, "road_style_mode", 2))
        except (ValueError, TypeError):
            mode = 2

        # Vorhandene Config-Bools synchronisieren
        self.sync_runtime_bools_from_config(config)

        # 2. DANACH: Die global geteilten Klassen-Werte erzwingen

        enable_building_features = bool(getattr(config, "enable_advanced_building_features", True))
        enable_point_features = bool(getattr(config, "enable_advanced_point_features", True))

        enable_building_labels = StyleEngine.enable_building_labels
        enable_road_labels = StyleEngine.enable_labels
        enable_building_smoothing = StyleEngine.enable_building_smoothing
        enable_building_shadow = StyleEngine.enable_building_shadow
        enable_landuse_labels = StyleEngine.enable_landuse_labels
        enable_road_features = StyleEngine.enable_advanced_road_features

        # HIERFOLGT DEIN ORIGINALER CODE (if mode == 0: etc.) UNVERÄNDERT...

        self.sync_runtime_bools_from_config(config)

        enable_road_features = bool(getattr(config, "enable_advanced_road_features", True))
        enable_road_labels = bool(getattr(config, "enable_road_labels", True))
        enable_building_features = bool(getattr(config, "enable_advanced_building_features", True))
        enable_building_smoothing = bool(getattr(config, "enable_building_edge_smoothing", True))
        enable_building_shadow = bool(getattr(config, "enable_building_drop_shadow", True))

        enable_landuse_labels = bool(getattr(config, "enable_landuse_labels", True))
        enable_point_features = bool(getattr(config, "enable_advanced_point_features", True))

        enable_building_labels = self.enable_building_labels

        result = None
        geom_type = self.get_layer_geometry_type_name(layer)

        # ==============================================================================
        # CASUS 0: REINES BASIS-STYLING (Modus 0)
        # ==============================================================================
        if mode == 0:
            # 1. Erst das normale JSON-Basis-Styling ausführen
            result = self._execute_base_styling(layer, config, plugin_dir)

            # 2. Spezifische Korrekturen/Bremsen für Modus 0
            if geom_type == "line":
                result = {"success": True, "message": "Straßen im Basis-Look belassen (Modus 0)."}

            elif geom_type == "polygon" and enable_building_features:
                if layer.fields().indexOf("building") >= 0 or layer.fields().indexOf(
                        "type") >= 0 or layer.fields().indexOf("fclass") >= 0:
                    self.apply_building_symbol_mapping(
                        layer, enable_smoothing=True, enable_shadow=False,
                        reines_einzelstyling=False, enable_labels=False, ignore_user_styles=True
                    )
                    result = {"success": True, "message": "Basis-Polygon-Styling repariert."}

            elif geom_type == "point":
                result = {"success": True, "message": "Punkt-Layer unverändert belassen (Modus 0)."}

        # ==============================================================================
        # CASUS 1: REINES EINZELSTYLING (Modus 1 - Basis-Styling wird komplett ignoriert)
        # ==============================================================================
        elif mode == 1:
            # INTERNE WEICHE NACH GEOMETRIE-TYP
            if geom_type == "line":
                if enable_road_features:
                    success = self.apply_road_symbol_mapping(
                        layer, config=config, reines_einzelstyling=True, enable_labels=enable_road_labels
                    )
                    if success:
                        result = {"success": True, "message": "Reines Straßen-Einzelstyling angewendet (Modus 1)."}
                else:
                    result = {"success": False, "message": "Erweiterte Straßenbehandlung deaktiviert."}




            elif geom_type == "polygon":

                # --- SEMANTISCHES SCORING (IDENTISCH ZU MODUS 2) ---

                building_score = 0

                landuse_score = 0

                # Wir scannen die ersten 50 Zeilen des Layers für maximale Performance
                request = QgsFeatureRequest().setLimit(50)

                idx_building = layer.fields().indexOf("building")

                idx_type = layer.fields().indexOf("type")

                idx_landuse = layer.fields().indexOf("landuse")

                idx_fclass = layer.fields().indexOf("fclass")

                for feature in layer.getFeatures(request):

                    # Gebäude-Indikatoren prüfen

                    if idx_building >= 0 and feature.attribute(idx_building):

                        val = str(feature.attribute(idx_building)).strip().lower()

                        if val and val != "no" and val != "null":
                            building_score += 2

                    if idx_type >= 0 and feature.attribute(idx_type):

                        val = str(feature.attribute(idx_type)).strip().lower()

                        if val in ["apartments", "house", "detached", "commercial", "industrial", "residential"]:
                            building_score += 2

                    # Flächen-Indikatoren (Landuse) prüfen

                    if idx_landuse >= 0 and feature.attribute(idx_landuse):

                        val = str(feature.attribute(idx_landuse)).strip().lower()

                        if val and val != "null":
                            landuse_score += 2

                    if idx_fclass >= 0 and feature.attribute(idx_fclass):

                        val = str(feature.attribute(idx_fclass)).strip().lower()

                        if val in ["forest", "park", "grass", "water", "meadow", "commercial", "industrial"]:
                            landuse_score += 1

                # --- DIE ENTSCHEIDUNG ---

                if landuse_score > building_score or (idx_landuse >= 0 and idx_building < 0):

                    # REPARATUR: "apply_landuse_symbol_mapping" existierte nie als Methode,
                    # wodurch der Landuse-Haken (enable_landuse_labels) im Modus 1 wirkungslos blieb.
                    # Wir nutzen dieselbe Beschriftungs-Logik wie im Modus 2.
                    self.apply_landuse_advanced_features(layer, enable_labels=enable_landuse_labels)

                    result = {"success": True, "message": "Reines Flächen-Einzelstyling angewendet (Modus 1)."}

                else:

                    if enable_building_features:

                        if hasattr(layer, "setFeatureBlendMode"):
                            layer.setFeatureBlendMode(0)

                        success = self.apply_building_symbol_mapping(

                            layer, config=config, enable_smoothing=enable_building_smoothing,

                            enable_shadow=enable_building_shadow, reines_einzelstyling=True,

                            enable_labels=enable_building_labels

                        )

                        if success:
                            result = {"success": True, "message": "Reines Gebäude-Einzelstyling angewendet (Modus 1)."}

                    else:

                        result = {"success": False, "message": "Erweiterte Gebäudebehandlung deaktiviert."}


            elif geom_type == "point":
                if enable_point_features and layer.fields().indexOf("fclass") >= 0:
                    success = self.apply_point_symbol_mapping(
                        layer, plugin_dir=plugin_dir, config=config, reines_einzelstyling=True
                    )
                    if success:
                        result = {"success": True, "message": "Reines Punkt-Einzelstyling angewendet (Modus 1)."}
                else:
                    result = {"success": False, "message": "Erweiterte Punktbehandlung deaktiviert."}

        elif mode == 2:

            # 1. Zuerst immer das JSON-Basis-Styling vorfärben

            result = self._execute_base_styling(layer, config, plugin_dir)

            # 2. Danach die erweiterten Einzelstylings injizieren

            if geom_type == "line" and enable_road_features:

                self.apply_road_symbol_mapping(

                    layer, config=config, reines_einzelstyling=False, enable_labels=enable_road_labels

                )

                result = {"success": True, "message": "Kombiniertes Straßen-Styling angewendet (Modus 2)."}


            elif geom_type == "point" and enable_point_features:

                if layer.fields().indexOf("fclass") >= 0:

                    success = self.apply_point_symbol_mapping(

                        layer, plugin_dir=plugin_dir, config=config, reines_einzelstyling=False

                    )

                    if success:
                        result = {"success": True, "message": "Kombiniertes Punkt-Styling erfolgreich (Modus 2)."}


            elif geom_type == "polygon":

                # ==============================================================================

                # DETEKTIV-LOGIK: Wir gehen AKTIV in die Attributtabelle und scannen die Werte!

                # ==============================================================================

                building_score = 0

                landuse_score = 0

                # Wir begrenzen den Scan auf 50 Zeilen für maximale QGIS-Performance

                request = QgsFeatureRequest().setLimit(50)

                idx_building = layer.fields().indexOf("building")

                idx_type = layer.fields().indexOf("type")

                idx_landuse = layer.fields().indexOf("landuse")

                idx_fclass = layer.fields().indexOf("fclass")

                # Schleife durch die echten Tabelleneinträge

                for feature in layer.getFeatures(request):

                    # 1. Gebäude-Werte in der Tabelle zählen

                    if idx_building >= 0 and feature.attribute(idx_building):

                        val = str(feature.attribute(idx_building)).strip().lower()

                        if val and val not in ("no", "null", "none"):
                            building_score += 2

                    if idx_type >= 0 and feature.attribute(idx_type):

                        val = str(feature.attribute(idx_type)).strip().lower()

                        if val in ["apartments", "house", "detached", "commercial", "industrial", "residential"]:
                            building_score += 2

                    # 2. Flächen-Werte (Landuse) in der Tabelle zählen

                    if idx_landuse >= 0 and feature.attribute(idx_landuse):

                        val = str(feature.attribute(idx_landuse)).strip().lower()

                        if val and val != "null":
                            landuse_score += 2

                    if idx_fclass >= 0 and feature.attribute(idx_fclass):

                        val = str(feature.attribute(idx_fclass)).strip().lower()

                        if val in ["forest", "park", "grass", "water", "meadow", "scrub", "heath"]:
                            landuse_score += 2

                # Sicherheits-Fallback über den Namen, falls die Tabelle leer war (0 zu 0 steht)

                layer_name_lower = (layer.name() or "").lower()

                if building_score == 0 and landuse_score == 0:

                    if "landuse" in layer_name_lower or "water" in layer_name_lower or "natural" in layer_name_lower:

                        landuse_score = 5

                    else:

                        building_score = 5

                # ==============================================================================

                # DIE AUSWERTUNG ANHAND DER ECHTEN TABELLEN-SCORES

                # ==============================================================================

                if landuse_score > building_score:

                    # Eindeutig ein Flächen/Landuse-Layer anhand der Tabellenwerte!

                    self.apply_landuse_advanced_features(layer, enable_labels=StyleEngine.enable_landuse_labels)

                    result = {"success": True, "message": "Kombiniertes Landuse-Flächenstyling erfolgreich (Modus 2)."}


                else:

                    # Eindeutig ein Gebäude-Layer anhand der Tabellenwerte!

                    if enable_building_features:

                        if hasattr(layer, "setFeatureBlendMode"):
                            layer.setFeatureBlendMode(0)

                        self.apply_building_symbol_mapping(

                            layer, config,

                            enable_smoothing=enable_building_smoothing,

                            enable_shadow=enable_building_shadow,

                            reines_einzelstyling=False,

                            enable_labels=enable_building_labels,

                            ignore_user_styles=False

                        )

                        result = {"success": True, "message": "Kombiniertes Gebäude-Styling erfolgreich (Modus 2)."}
        # Sicherheitsnetz: Falls result noch None ist
        if result is None:
            result = {"success": True, "message": "Layer im Standard-Look belassen"}
        return result

    def _execute_base_styling(self, layer, config, plugin_dir=None):
        """Eigene Methode für das bisherige Regelwerk und die QML/Profil-Suche."""
        # 1. style_profile versuchen
        profile, detected_profile_field = self.find_style_profile(layer, config)
        if profile:
            style_source = getattr(profile, "style_source", None)
            qml_path = self._get_attr(style_source, "qml_path", default="") if style_source else ""
            use_qml_first = bool(self._get_attr(style_source, "use_qml_first", default=True)) if style_source else True
            fallback_to_rules = bool(
                self._get_attr(style_source, "fallback_to_rules", default=True)) if style_source else True

            qml_abs_path = self.resolve_qml_path(plugin_dir, qml_path)

            if use_qml_first and qml_abs_path:
                if os.path.exists(qml_abs_path):

                    # ==============================================================================
                    # --- DIE REISSLEINE: WENN DER BASIS-HAKEN BEI STRASSEN AUS IST ---
                    # ==============================================================================
                    road_base_aktiv = True
                    if config:
                        if isinstance(config, dict):
                            road_base_aktiv = config.get("enable_advanced_road_features", True)
                        else:
                            road_base_aktiv = getattr(config, "enable_advanced_road_features", True)

                    # Wenn es sich um den Straßen-Layer handelt und der Haken AUS ist:
                    if layer and "road" in layer.name().lower() and road_base_aktiv is False:
                        # Log-Nachricht restlos entfernt, die logische Sperre bleibt aktiv!
                        success = False
                    else:
                        # Nur wenn der Haken AN ist, darf QGIS die Datei wirklich anfassen:
                        road_base_aktiv = config.get("enable_advanced_road_features", True) if isinstance(config,
                                                                                                          dict) else getattr(
                            config, "enable_advanced_road_features", True)
                        success, detail = self.apply_qml_style(layer, qml_abs_path)

                    # ==============================================================================

                    if success:
                        return self._result(
                            True,
                            message="QML-Stil '{0}' angewendet.".format(
                                getattr(profile, "label", "") or getattr(profile, "id", "")
                            ),
                            level="info",
                            source="profile_qml",
                            profile_id=getattr(profile, "id", "")
                        )
                else:
                    pass
            if fallback_to_rules:

                result = self.apply_profile_rules(layer, profile, detected_field_name=detected_profile_field)
                if isinstance(result, dict) and result.get("success"):
                    return result

        # 2. layerruleset versuchen
        layerruleset, detected_ruleset_field = self.find_layer_ruleset(layer, config)

        return self.apply_layer_ruleset_style(layer, layerruleset, detected_field_name=detected_ruleset_field)

    def apply_road_symbol_mapping(self, layer, config=None, reines_einzelstyling=False, enable_labels=True):
        if not layer:
            return False

        # ==============================================================================
        # --- UNZINGBARER STRASSEN-MASTER-STOPP (Nutzt direkt die übergebene Config) ---
        # ==============================================================================
        # Wir lesen den Haken direkt aus der frischen Konfiguration aus
        road_base_aktiv = True
        if config:
            if isinstance(config, dict):
                road_base_aktiv = config.get("enable_advanced_road_features", True)
            else:
                road_base_aktiv = getattr(config, "enable_advanced_road_features", True)

        if road_base_aktiv is False:
            # 1. Alle Texte sofort und rückstandslos löschen
            layer.setLabelsEnabled(False)
            layer.setLabeling(None)

            # 2. Die defekte QML-Datei komplett umgehen und ein einfaches Standardsymbol setzen
            from qgis.core import QgsSingleSymbolRenderer, QgsLineSymbol
            standard_symbol = QgsLineSymbol.createSimple({
                'color': '#aaaaaa',
                'width': '0.26',
                'penstyle': 'solid'
            })
            layer.setRenderer(QgsSingleSymbolRenderer(standard_symbol))

            layer.triggerRepaint()
            return True

        # ==============================================================================
        # Ab hier läuft dein originaler Code (fields = layer.fields()...) völlig unverändert weiter:
        # ==============================================================================
        fields = layer.fields()

        style = QgsStyle.defaultStyle()

        project_style = QgsProject.instance().styleSettings().projectStyle()

        renderer = layer.renderer()
        if not renderer:
            return False

        # Dynamisch ermitteln, auf welcher Spalte QGIS gerade arbeitet
        renderer_field = "fclass"
        if hasattr(renderer, "classAttribute") and renderer.classAttribute():
            renderer_field = renderer.classAttribute().strip().lower()
        elif fields.indexOf("code") >= 0 and fields.indexOf("fclass") < 0:
            renderer_field = "code"

        # --- WASSERDICHTER, SPALTENFREIER JSON-EINFANG FÜR STRASSEN ---
        mapping = {}
        config_mappings = []
        if config:
            if isinstance(config, dict):
                config_mappings = config.get("custom_mappings", [])
            else:
                config_mappings = getattr(config, "custom_mappings", [])

        if isinstance(config_mappings, list):
            for entry in config_mappings:
                if isinstance(entry, dict) and entry.get("active", True) and entry.get("geom") == "Line":
                    gui_value = str(entry.get("value", "")).strip().lower()

                    # --- DER PROFI-JOKER-FINDER ---
                    # Wir prüfen die globale GEOFABRIK_CODE_MAP ganz oben in der Datei!
                    target_values = [gui_value]
                    if gui_value in GEOFABRIK_CODE_MAP:
                        target_values.append(GEOFABRIK_CODE_MAP[gui_value])

                    # Wenn der Layer 'code' nutzt, erzwingen wir die Code-Nummer
                    if renderer_field == "code":
                        if gui_value in GEOFABRIK_CODE_MAP:
                            target_value = GEOFABRIK_CODE_MAP[gui_value]
                        else:
                            target_value = gui_value

                        mapping[target_value] = {
                            "symbol_name": entry.get("style", ""),
                            "legend_label": entry.get("label", "")
                        }
                    # Wenn der Layer Klartext spricht (fclass/highway) oder spaltenunabhängig läuft:
                    else:
                        for t_val in target_values:
                            mapping[t_val] = {
                                "symbol_name": entry.get("style", ""),
                                "legend_label": entry.get("label", "")
                            }
        # Hilfsfunktion für abgerundete Kurven und Kappen
        def _optimize_line_caps_and_joins(symbol):
            if not symbol:
                return
            for i in range(symbol.symbolLayerCount()):
                layer_item = symbol.symbolLayer(i)
                if hasattr(layer_item, "setJoinStyle"):
                    layer_item.setJoinStyle(Qt.RoundJoin)
                    layer_item.setCapStyle(Qt.RoundCap)


        # --- STRATEGIE FÜR REINES EINZELSTYLING (Modus 1) ---
        if reines_einzelstyling:
            # Dynamisch ermitteln, auf welcher Spalte QGIS gerade arbeitet
            renderer_field = "fclass"
            if hasattr(renderer, "classAttribute") and renderer.classAttribute():
                renderer_field = renderer.classAttribute().strip().lower()
            elif fields.indexOf("code") >= 0 and fields.indexOf("fclass") < 0:
                renderer_field = "code"

            updated_categories = []

            # Sicherheits-Set gegen doppelte Legenden-Einträge
            erstellte_labels = set()

            for key, cfg in mapping.items():
                label_name = cfg["legend_label"]

                # Wenn dieses Label (z. B. "Automobilbahn") schon existiert, überspringen!
                if label_name in erstellte_labels:
                    continue

                # Erst in den Projektstilen suchen, dann global
                fetched_symbol = project_style.symbol(cfg["symbol_name"])
                if not (fetched_symbol and cfg["symbol_name"] in project_style.symbolNames()):
                    fetched_symbol = style.symbol(cfg["symbol_name"])

                if fetched_symbol:
                    cloned_symbol = fetched_symbol.clone()
                    _optimize_line_caps_and_joins(cloned_symbol)

                    # Der Category-Key muss zur aktiven Spalte passen
                    category_key = key
                    if renderer_field == "code" and key in GEOFABRIK_CODE_MAP:
                        category_key = GEOFABRIK_CODE_MAP[key]
                    elif renderer_field == "code" and key.isdigit():
                        category_key = key

                    new_cat = QgsRendererCategory(category_key, cloned_symbol, label_name)
                    updated_categories.append(new_cat)

                    # Das Label als "erstellt" markieren
                    erstellte_labels.add(label_name)

            # --- UNZERSTÖRBARE ABHILFE: Der "Alles andere"-Joker für Straßen ---
            # Verhindert, dass unbenannte Straßen im Modus 1 unsichtbar werden!
            # REPARATUR: Erzeugt die graue Linie unzerstörbar über das QGIS-Eigenschafts-System!
            properties = {
                "line_color": "#cccccc",
                "line_width": "0.2",
                "penstyle": "dot"
            }

            fallback_layer = QgsSimpleLineSymbolLayer.create(properties)
            from qgis.core import QgsLineSymbol
            fallback_symbol = QgsLineSymbol()

            fallback_symbol.changeSymbolLayer(0, fallback_layer)
            _optimize_line_caps_and_joins(fallback_symbol)

            # Ein leerer String '' als Key fängt alle nicht definierten Straßen ab!
            fallback_cat = QgsRendererCategory("", fallback_symbol, "Andere Straßen/Wege")
            updated_categories.append(fallback_cat)

            # Den fertigen Renderer mit dem Joker übergeben
            new_renderer = QgsCategorizedSymbolRenderer(renderer_field, updated_categories)
            layer.setRenderer(new_renderer)


        # --- STRATEGIE FÜR HISTORISCHE STILE (Modus 2) ---
        else:
            enable_road_features = StyleEngine.enable_advanced_road_features
            if renderer.type() == "categorizedSymbol":
                updated_categories = []

                # ==============================================================================
                # --- JETZT NEU: DER SCHNELLERE RAM-CACHE (Vor der Schleife) ---
                # ==============================================================================
                # Wir lesen die Namensliste der Symbole hier EINZIGES MAL ein (0 ms in der Schleife!)
                available_project_symbols = set(project_style.symbolNames())
                symbol_cache = {}
                # ==============================================================================

                for category in renderer.categories():
                    val_str = str(category.value()).strip().lower()
                    if val_str in mapping:
                        cfg = mapping[val_str]
                        symbol_name = cfg["symbol_name"]

                        # --- BLITZSCHNELLER RAM-CHECK STATT NEUEM FESTPLATTEN-SCAN ---
                        if symbol_name not in symbol_cache:
                            # Wir prüfen im schnellen RAM-Set, ob der Name existiert
                            if symbol_name in available_project_symbols:
                                fetched_symbol = project_style.symbol(symbol_name)
                            else:
                                fetched_symbol = style.symbol(symbol_name)
                            # Im Cache für die restlichen zehntausend Straßen merken
                            symbol_cache[symbol_name] = fetched_symbol
                        else:
                            # Direkt ohne Zeitverlust aus dem RAM-Speicher ziehen!
                            fetched_symbol = symbol_cache[symbol_name]
                        # ======================================================================

                        if fetched_symbol:
                            cloned_symbol = fetched_symbol.clone()
                            if enable_road_features:
                                _optimize_line_caps_and_joins(cloned_symbol)
                            category.setSymbol(cloned_symbol)
                            category.setLabel(cfg["legend_label"])
                    updated_categories.append(category)

                renderer.deleteAllCategories()
                for cat in updated_categories:
                    renderer.addCategory(cat)

            # --- ERZWINGE DIE STRASSEN-VERSCHMELZUNG (SYMBOL LEVELS) ---
            active_renderer = layer.renderer()
            if active_renderer:
                # 1. Symbol-Ebenen einschalten, damit Schichten sich nicht gegenseitig schneiden
                if enable_road_features:
                    active_renderer.setUsingSymbolLevels(True)

            # Optional: Falls Ihre Autobahnen immer ganz oben liegen sollen,
            # sorgt dieser QGIS-Befehl dafür, dass sie Brücken sauber überqueren
            if hasattr(layer, "setFeatureBlendMode"):
                layer.setFeatureBlendMode(0)  # Normaler Modus, verhindert Transparenz-Fehler

                # ===========================================================================
                # BLOCK: LIVE-SCHALTUNG FÜR STRASSENTEXTE (Schützt Yans Renderer vor dem Löschen!)
                # ===========================================================================
            has_name = fields.indexOf("name") >= 0

            # Wir fragen live das globale Klassen-Flag ab
            if getattr(StyleEngine, "enable_labels", True) is True and has_name:
                label_settings = QgsPalLayerSettings()
                label_settings.fieldName = "name"
                label_settings.placement = QgsPalLayerSettings.Line

                # --- DIE COOLE DICHTE-OPTIMIERUNG VON PAGE 3 HIER INTEGRIEREN ---
                label_settings.repeatDistance = 700
                label_settings.repeatDistanceUnit = QgsUnitTypes.RenderMillimeters
                label_settings.minimumFeatureSize = 20
                label_settings.removeDuplicateLabels = True

                text_format = QgsTextFormat()
                text_format.setFont(QFont("Arial", 7))
                text_format.setColor(QColor("#252525"))

                buffer_settings = QgsTextBufferSettings()
                buffer_settings.setEnabled(True)
                buffer_settings.setSize(0.8)
                buffer_settings.setColor(QColor("#ffffff"))
                text_format.setBuffer(buffer_settings)

                label_settings.setFormat(text_format)
                layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
                layer.setLabelsEnabled(True)
            else:
                # DIE RETTUNG: Wenn der Haken aus ist, löschen wir NUR die Texte!
                layer.setLabelsEnabled(False)
                layer.setLabeling(None)

            # Ab hier ist alles wieder exakt auf der Standard-Methoden-Ebene (8 Leerzeichen)
            try:
                iface = qgis.utils.iface
                if iface and iface.layerTreeView():
                    iface.layerTreeView().refreshLayerSymbology(layer.id())
            except Exception:
                pass

            if hasattr(layer, "emitStyleChanged"):
                layer.emitStyleChanged()

            layer.triggerRepaint()
            return True


    def apply_building_symbol_mapping(self, layer, config=None, enable_smoothing=True, enable_shadow=True,
                                      reines_einzelstyling=False, enable_labels=True, ignore_user_styles=False):
        if not layer:
            return False

        def _apply_building_smoothing(symbol):
            if not symbol or not enable_smoothing:
                return

            for i in range(symbol.symbolLayerCount()):
                sl = symbol.symbolLayer(i)
                if hasattr(sl, "fillColor") and hasattr(sl, "setStrokeColor") and hasattr(sl, "setStrokeWidth"):
                    fill_color = sl.fillColor()
                    if fill_color and fill_color.isValid():
                        sl.setStrokeColor(fill_color.darker(125))
                    else:
                        sl.setStrokeColor(QColor("#cbbcb9"))
                    sl.setStrokeWidth(0.1)
                    if hasattr(sl, "setStrokeStyle"):
                        sl.setStrokeStyle(Qt.SolidLine)

        def _apply_building_shadow(symbol):
            # Wir zwingen die Hilfsfunktion, auf die Klasse zu hören!
            if not symbol or StyleEngine.enable_building_shadow is False:
                return

            # Die alte 'if not enable_shadow'-Abfrage wurde hier gelöscht!
            if not hasattr(symbol, "setPaintEffect"):
                return

            effect = QgsDropShadowEffect()
            effect.setEnabled(True)
            effect.setBlurLevel(1.5)
            effect.setOffsetDistance(0.6)
            effect.setOffsetUnit(QgsUnitTypes.RenderMillimeters)
            effect.setColor(QColor(0, 0, 0, 60))

            stack = QgsEffectStack()
            stack.appendEffect(effect)
            symbol.setPaintEffect(stack)

        def _finalize_building_symbol(symbol):
            if not symbol:
                return symbol

            _apply_building_smoothing(symbol)

            # Richtiger Qt-Import direkt für die innere Funktion bereitstellen
            from qgis.PyQt.QtCore import QPointF

            live_shadow = getattr(StyleEngine, "enable_building_shadow", True)

            if live_shadow is True:
                try:
                    schon_da = False
                    for idx in range(symbol.symbolLayerCount()):
                        sl = symbol.symbolLayer(idx)
                        # Überprüfung mit dem importierten QPointF
                        if hasattr(sl, "offset") and sl.offset() == QPointF(0.6, 0.6) and sl.strokeStyle() == Qt.NoPen:
                            schon_da = True
                            break

                    if not schon_da:
                        shadow_layer = QgsSimpleFillSymbolLayer()
                        shadow_layer.setFillColor(QColor(0, 0, 0, 45))
                        shadow_layer.setStrokeStyle(Qt.NoPen)

                        # Sichere Zuweisung
                        shadow_layer.setOffset(QPointF(0.6, 0.6))
                        shadow_layer.setOffsetUnit(QgsUnitTypes.RenderMillimeters)

                        symbol.insertSymbolLayer(0, shadow_layer)

                except Exception as shadow_err:
                    pass

            else:
                try:
                    schichten_zu_loeschen = []
                    for idx in range(symbol.symbolLayerCount()):
                        sl = symbol.symbolLayer(idx)
                        if hasattr(sl, "offset") and sl.offset() == QPointF(0.6, 0.6) and sl.strokeStyle() == Qt.NoPen:
                            schichten_zu_loeschen.append(idx)

                    for idx in reversed(schichten_zu_loeschen):
                        symbol.deleteSymbolLayer(idx)
                except Exception:
                    pass

            return symbol

        fields = layer.fields()
        style = QgsStyle.defaultStyle()
        project_style = QgsProject.instance().styleSettings().projectStyle()
        renderer = layer.renderer()
        if not renderer:
            return False

        def _dbg(msg):
            # Schaltet die innere Hilfsfunktion absolut lautlos und crashsicher
            pass

        # Ab hier rücken wir die nachfolgenden Zeilen (wie das Auslesen der Felder)
        # auf exakt 8 Leerzeichen ein, damit sie auf der Methodenebene weiterlaufen:
        renderer_field = self.detect_best_building_field(layer, config=config, sample_limit=200)

        renderer_field = self.detect_best_building_field(layer, config=config, sample_limit=200)

        if not renderer_field:
            renderer_field = "type"
            if hasattr(renderer, "classAttribute") and renderer.classAttribute():
                renderer_field = renderer.classAttribute().strip().lower()

        layer.setLabelsEnabled(False)
        layer.setLabeling(None)

        field_mapping = {}
        config_mappings = []
        if config:
            if isinstance(config, dict):
                config_mappings = config.get("custom_mappings", [])
            else:
                config_mappings = getattr(config, "custom_mappings", [])

        if isinstance(config_mappings, list):
            for entry in config_mappings:
                if isinstance(entry, dict) and entry.get("active", True) and str(
                        entry.get("geom", "")).lower() == "polygon":
                    gui_value = str(entry.get("value", "")).strip().lower()
                    target_values = [gui_value]
                    if gui_value in GEOFABRIK_CODE_MAP:
                        target_values.append(GEOFABRIK_CODE_MAP[gui_value])

                    if renderer_field == "code":
                        target_value = GEOFABRIK_CODE_MAP[gui_value] if gui_value in GEOFABRIK_CODE_MAP else gui_value
                        field_mapping[target_value] = {
                            "symbol_name": entry.get("style", ""), "legend_label": entry.get("label", "")
                        }
                    else:
                        for t_val in target_values:
                            field_mapping[t_val] = {
                                "symbol_name": entry.get("style", ""), "legend_label": entry.get("label", "")
                            }

        idx_dbg = fields.indexOf(renderer_field)
        if idx_dbg >= 0:
            unique_vals = layer.uniqueValues(idx_dbg)

        if reines_einzelstyling or renderer.type() != "categorizedSymbol":
            updated_categories = []
            erstellte_labels = set()
            for val, cfg in field_mapping.items():
                label_name = cfg["legend_label"]
                symbol_name = cfg["symbol_name"]

                if label_name in erstellte_labels:
                    continue
                project_hit = project_style.symbol(symbol_name) is not None
                global_hit = symbol_name in style.symbolNames()

                fetched_symbol = project_style.symbol(symbol_name)
                if not (fetched_symbol and symbol_name in project_style.symbolNames()):
                    fetched_symbol = style.symbol(symbol_name)

                if fetched_symbol:
                    new_symbol = fetched_symbol.clone()

                else:
                    layer_item = QgsSimpleFillSymbolLayer()
                    layer_item.setFillColor(QColor(cfg.get("fill", "#ebdcd9")))
                    layer_item.setStrokeColor(QColor(cfg.get("border", "#cbbcb9")))
                    layer_item.setStrokeWidth(0.1)
                    layer_item.setStrokeStyle(Qt.SolidLine)
                    new_symbol = QgsFillSymbol()
                    new_symbol.changeSymbolLayer(0, layer_item)
                new_symbol = _finalize_building_symbol(new_symbol)

                # ==============================================================================
                # --- ERZWINGE DIE LIVE-GLÄTTUNG AUS DER STATISCHEN KLASSE ---
                # ==============================================================================
                live_smoothing = StyleEngine.enable_building_smoothing

                if new_symbol:
                    for i in range(new_symbol.symbolLayerCount()):
                        layer_item = new_symbol.symbolLayer(i)
                        if hasattr(layer_item, "setFillColor") and hasattr(layer_item, "setStrokeColor") and hasattr(
                                layer_item, "setStrokeWidth"):
                            fill_color = layer_item.fillColor()

                            if live_smoothing is True:
                                if fill_color and fill_color.isValid():
                                    layer_item.setStrokeColor(fill_color.darker(125))
                                else:
                                    layer_item.setStrokeColor(QColor("#cbbcb9"))
                                layer_item.setStrokeWidth(0.1)
                                layer_item.setStrokeStyle(Qt.SolidLine)
                            else:
                                layer_item.setStrokeStyle(Qt.NoPen)
                                layer_item.setStrokeWidth(0.0)

                # Ab hier läuft dein Code unverändert weiter:
                category_key = val

                cat = QgsRendererCategory(category_key, new_symbol, label_name)
                updated_categories.append(cat)
                erstellte_labels.add(label_name)

            fallback_layer = QgsSimpleFillSymbolLayer()
            fallback_layer.setFillColor(QColor("#ebdcd9"))
            fallback_layer.setStrokeColor(QColor("#cbbcb9"))
            fallback_layer.setStrokeWidth(0.1)
            fallback_symbol = QgsFillSymbol()
            fallback_symbol.changeSymbolLayer(0, fallback_layer)
            fallback_symbol = _finalize_building_symbol(fallback_symbol)

            fallback_cat = QgsRendererCategory("", fallback_symbol, "Andere Gebäude")
            updated_categories.append(fallback_cat)

            new_renderer = QgsCategorizedSymbolRenderer(renderer_field, updated_categories)
            layer.setRenderer(new_renderer)


        # ------------------------------------------------------------------
        # STRATEGIE MODUS 2: Kombiniertes Ergänzen (Gester-Stand wiederbelebt!)
        # ------------------------------------------------------------------
        else:
            def _apply_building_smoothing(symbol):
                # Wir lesen auch hier den globalen Klassen-Wert aus!
                live_smoothing = StyleEngine.enable_building_smoothing

                if not symbol:
                    return

                if live_smoothing is False:
                    # Wenn Glättung aus ist, entfernen wir bei allen Schichten die Rahmenlinie
                    for i in range(symbol.symbolLayerCount()):
                        sl = symbol.symbolLayer(i)
                        if hasattr(sl, "setStrokeStyle"):
                            sl.setStrokeStyle(Qt.NoPen)
                            sl.setStrokeWidth(0.0)
                    return

                for i in range(symbol.symbolLayerCount()):
                    layer_item = symbol.symbolLayer(i)
                    if hasattr(layer_item, "fillColor") and hasattr(layer_item, "setStrokeColor") and hasattr(
                            layer_item, "setStrokeWidth"):
                        fill_color = layer_item.fillColor()
                        if fill_color and fill_color.isValid():
                            layer_item.setStrokeColor(fill_color.darker(125))
                        else:
                            layer_item.setStrokeColor(QColor("#cbbcb9"))
                        layer_item.setStrokeWidth(0.1)
                        if hasattr(layer_item, "setStrokeStyle"):
                            layer_item.setStrokeStyle(Qt.SolidLine)

            updated_categories = []

            for category in renderer.categories():
                cat_value = str(category.value()).strip().lower()
                symbol = category.symbol()

                matched_cfg = None
                cat_val_str = str(category.value()).strip().lower()

                for gui_val, cfg in field_mapping.items():
                    gui_val_clean = str(gui_val).strip().lower()

                    if gui_val_clean == cat_val_str:
                        matched_cfg = cfg
                        break

                    elif renderer_field == "code" and gui_val_clean in GEOFABRIK_CODE_MAP and str(
                            GEOFABRIK_CODE_MAP[gui_val_clean]) == cat_val_str:
                        matched_cfg = cfg
                        break

                if matched_cfg:
                    symbol_name = matched_cfg["symbol_name"]
                    new_symbol = None

                    if not ignore_user_styles:
                        fetched_symbol = project_style.symbol(symbol_name)
                        if not fetched_symbol:
                            fetched_symbol = style.symbol(symbol_name)
                        if fetched_symbol:
                            new_symbol = fetched_symbol.clone()

                    if new_symbol is None and symbol:
                        new_symbol = symbol.clone()

                    new_symbol = _finalize_building_symbol(new_symbol)

                    if new_symbol:
                        category.setSymbol(new_symbol)

                    category.setLabel(matched_cfg["legend_label"])

                else:
                    if symbol:
                        category.setSymbol(_finalize_building_symbol(symbol.clone()))

                updated_categories.append(category)

            renderer.deleteAllCategories()
            for cat in updated_categories:
                renderer.addCategory(cat)

        # ------------------------------------------------------------------
        # Gemeinsames Finishing & Labels
        # ------------------------------------------------------------------
        active_renderer = layer.renderer()
        if active_renderer and hasattr(active_renderer, "setUsingSymbolLevels"):
            active_renderer.setUsingSymbolLevels(True)

        if hasattr(layer, "setFeatureBlendMode"):
            layer.setFeatureBlendMode(0)

        # ==============================================================================
        # Ab hier läuft dein Label-Code völlig unverändert weiter:
        # ==============================================================================
        has_name = fields.indexOf("name") >= 0
        if (StyleEngine.enable_building_labels is True and has_name) or StyleEngine.enable_building_shadow is True:

            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "name"
            label_settings.placement = QgsPalLayerSettings.Horizontal
            label_settings.centroidWhole = True
            label_settings.fitInPolygonOnly = True

            text_format = QgsTextFormat()
            text_format.setFont(QFont("Arial", 7))
            text_format.setColor(QColor("#454545"))
            label_settings.setFormat(text_format)

            layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
            layer.setLabelsEnabled(True)

        elif StyleEngine.enable_building_labels is False:
            layer.setLabelsEnabled(False)
            layer.setLabeling(None)

        if hasattr(layer, "emitStyleChanged"):
            layer.emitStyleChanged()

        try:
            iface = qgis.utils.iface
            if iface and iface.layerTreeView():
                iface.layerTreeView().refreshLayerSymbology(layer.id())
        except Exception:
            pass

        layer.triggerRepaint()
        return True

    def apply_point_symbol_mapping(self, layer, plugin_dir=None, config=None, reines_einzelstyling=False):
        if not layer or not plugin_dir:
            return False

        fields = layer.fields()
        style = QgsStyle.defaultStyle()
        project_style = QgsProject.instance().styleSettings().projectStyle()
        renderer = layer.renderer()
        if not renderer:
            return False

        # Dynamisch ermitteln, auf welcher Spalte QGIS gerade arbeitet
        renderer_field = "fclass"
        if hasattr(renderer, "classAttribute") and renderer.classAttribute():
            renderer_field = renderer.classAttribute().strip().lower()
        elif fields.indexOf("amenity") >= 0:
            renderer_field = "amenity"
        elif fields.indexOf("code") >= 0:
            renderer_field = "code"

        # --- DYNAMISCHER, SPALTENFREIER JSON-EINFANG FÜR PUNKTE (POIs) ---
        field_mapping = {}
        config_mappings = []
        if config:
            if isinstance(config, dict):
                config_mappings = config.get("custom_mappings", [])
            else:
                config_mappings = getattr(config, "custom_mappings", [])

        if isinstance(config_mappings, list):
            for entry in config_mappings:
                if isinstance(entry, dict) and entry.get("active", True) and str(
                        entry.get("geom", "")).lower() == "point":
                    gui_value = str(entry.get("value", "")).strip().lower()

                    # --- UNZERSTÖRBARER JOKER-ABGLEICH (GEOFABRIK-CODES) ---
                    target_values = [gui_value]
                    if gui_value in GEOFABRIK_CODE_MAP:
                        target_values.append(GEOFABRIK_CODE_MAP[gui_value])

                    # Wenn der Layer 'code' (Zahlen) nutzt, erzwingen wir die Code-Nummer
                    if renderer_field == "code":
                        if gui_value in GEOFABRIK_CODE_MAP:
                            target_value = GEOFABRIK_CODE_MAP[gui_value]
                        else:
                            target_value = gui_value

                        style_str = str(entry.get("style", "")).strip()
                        strat_type = "svg" if style_str.lower().endswith(".svg") else (
                            "project" if "icon" in style_str.lower() or style_str.startswith("schule") else "simple")

                        field_mapping[target_value] = {
                            "type": strat_type, "source": style_str, "legend_label": entry.get("label", ""),
                            "shape": "diamond", "color": "#e31a1c", "size": 4.0
                        }
                    # Wenn der Layer Klartext spricht (fclass, amenity):
                    else:
                        for t_val in target_values:
                            style_str = str(entry.get("style", "")).strip()
                            strat_type = "svg" if style_str.lower().endswith(".svg") else (
                                "project" if "icon" in style_str.lower() or style_str.startswith(
                                    "schule") else "simple")

                            field_mapping[t_val] = {
                                "type": strat_type, "source": style_str, "legend_label": entry.get("label", ""),
                                "shape": "diamond", "color": "#e31a1c", "size": 4.0
                            }

        hat_keine_kategorien = (renderer.type() != "categorizedSymbol" or len(renderer.categories()) == 0)
        # ==============================================================================
        # --- STRATEGIE MODUS 1 / LEERER LAYER: Kompakter Neuaufbau ---
        # ==============================================================================
        # REPARATUR: Modus 2 wird hier eiskalt ausgesperrt!
        # Nur wenn Modus 1 erzwungen wird, bauen wir die Legende radikal neu.
        if reines_einzelstyling:
            updated_categories = []
            erstellte_labels = set()

            for val, cfg in field_mapping.items():
                label_name = cfg["legend_label"]
                if label_name in erstellte_labels:
                    continue

                new_symbol = QgsMarkerSymbol()
                symbol_layer = None

                if cfg["type"] == "project":
                    fetched = project_style.symbol(cfg["source"])
                    if fetched: new_symbol = fetched.clone()
                elif cfg["type"] == "svg" or cfg["source"].lower().endswith(".svg"):
                    svg_path = os.path.join(plugin_dir, "styles", cfg["source"])
                    if not os.path.exists(svg_path):
                        svg_path = os.path.join(plugin_dir, "styles", "icons", cfg["source"])
                    symbol_layer = QgsSvgMarkerSymbolLayer(svg_path, 5.0)
                else:
                    shape_str = cfg.get("shape", "circle")
                    shape_map = {"circle": QgsSimpleMarkerSymbolLayer.Circle,
                                 "square": QgsSimpleMarkerSymbolLayer.Square,
                                 "diamond": QgsSimpleMarkerSymbolLayer.Diamond,
                                 "triangle": QgsSimpleMarkerSymbolLayer.Triangle}
                    symbol_layer = QgsSimpleMarkerSymbolLayer()
                    symbol_layer.setShape(shape_map.get(shape_str, QgsSimpleMarkerSymbolLayer.Circle))
                    symbol_layer.setFillColor(QColor(cfg.get("color", "#ff0000")))
                    symbol_layer.setStrokeColor(QColor("#ffffff"))
                    symbol_layer.setStrokeWidth(0.4)
                    symbol_layer.setSize(cfg.get("size", 3.0))

                if symbol_layer:
                    new_symbol.changeSymbolLayer(0, symbol_layer)

                category_key = val
                if renderer_field == "code" and val in GEOFABRIK_CODE_MAP:
                    category_key = GEOFABRIK_CODE_MAP[val]
                elif renderer_field == "code" and val.isdigit():
                    category_key = val

                cat = QgsRendererCategory(category_key, new_symbol, label_name)
                updated_categories.append(cat)
                erstellte_labels.add(label_name)

            # Der graue Joker gilt ab jetzt STRIKT nur noch für das reine Einzelstyling!
            marker_props = {"name": "circle", "color": "#aaaaaa", "size": "2.0", "outline_color": "#ffffff",
                            "outline_width": "0.3"}
            fallback_layer = QgsSimpleMarkerSymbolLayer.create(marker_props)
            fallback_symbol = QgsMarkerSymbol()
            fallback_symbol.changeSymbolLayer(0, fallback_layer)

            fallback_cat = QgsRendererCategory("", fallback_symbol, "Andere Punkte / POIs")
            updated_categories.append(fallback_cat)

            new_renderer = QgsCategorizedSymbolRenderer(renderer_field, updated_categories)
            layer.setRenderer(new_renderer)

        # ==============================================================================
        # --- STRATEGIE MODUS 2: Kombiniertes Ergänzen (Präfix-Resistent) ---
        # ==============================================================================
        else:
            # --- DIE UNZERSTÖRBARE RETTUNG FÜR LEERE LAYER IM MODUS 2 ---
            if renderer.type() != "categorizedSymbol" or len(renderer.categories()) == 0:
                # Versuch 1: Das integrierte Basis-Styling triggern
                basis_erfolgreich = False
                if hasattr(self, "_execute_base_styling"):
                    try:
                        self._execute_base_styling(layer, config)
                        renderer = layer.renderer()
                        if renderer and renderer.type() == "categorizedSymbol" and len(renderer.categories()) > 0:
                            basis_erfolgreich = True
                    except Exception:
                        basis_erfolgreich = False

                # Versuch 2: Sensationelles Sicherheitsnetz! Falls das Basis-Styling den Layer ablehnt,
                # zwingen wir QGIS, die Kategorien direkt aus den echten Tabellenwerten aufzubauen!
                if not basis_erfolgreich:
                    # Wir erzeugen einen frischen Renderer auf der aktiven Spalte
                    default_renderer = QgsCategorizedSymbolRenderer(renderer_field, [])

                    # QGIS anweisen, die Spalte zu scannen und für jeden einzigartigen Wert (school, bank etc.)
                    # automatisch eine bunte Kategorie mit zufälligen Farben zu erstellen!
                    default_renderer.setClassAttribute(renderer_field)

                    # Wir holen uns alle einzigartigen Werte aus der Tabelle
                    unique_values = []
                    idx = fields.indexOf(renderer_field)
                    if idx >= 0:
                        unique_values = layer.uniqueValues(idx)

                    # Kategorien im Speicher befüllen
                    for val in unique_values:
                        if val is not None and str(val).strip():
                            # Erzeugt ein zufällig gefärbtes Standardsymbol für den Punkt
                            sym = QgsMarkerSymbol.createSimple({"name": "circle", "size": "3.0"})
                            cat = QgsRendererCategory(str(val), sym, str(val))
                            default_renderer.addCategory(cat)

                    layer.setRenderer(default_renderer)
                    renderer = layer.renderer()

            updated_categories = []

            for category in renderer.categories():

                cat_value = str(category.value()).strip().lower()
                symbol = category.symbol()

                # --- FLEXIBLER JOKER- & PRÄFIX-ABGLEICH ---
                matched_cfg = None

                # MINIMAL-FIX MODUS 2: Verhindert, dass allgemeine 'buildings' das Wohngebäude-Symbol stehlen!
                for gui_val, cfg in field_mapping.items():
                    if gui_val == cat_value:
                        matched_cfg = cfg
                        break
                    elif renderer_field == "code" and gui_val in GEOFABRIK_CODE_MAP and GEOFABRIK_CODE_MAP[
                        gui_val] == cat_value:
                        matched_cfg = cfg
                        break

                    # 3. Fall: Präfix-Rettung für Punkte (z.B. "[F] Schule")
                    elif gui_val in cat_value:
                        matched_cfg = cfg
                        break

                if symbol and matched_cfg:
                    strategy = matched_cfg.get("type", "simple")
                    new_symbol = None

                    if strategy == "project":
                        symbol_name = matched_cfg["source"]
                        fetched_symbol = project_style.symbol(symbol_name)
                        if not fetched_symbol:
                            fetched_symbol = style.symbol(symbol_name)
                        if fetched_symbol:
                            new_symbol = fetched_symbol.clone()
                    elif strategy == "svg" or matched_cfg["source"].lower().endswith(".svg"):
                        svg_path = os.path.join(plugin_dir, "styles", matched_cfg["source"])
                        if not os.path.exists(svg_path):
                            svg_path = os.path.join(plugin_dir, "styles", "icons", matched_cfg["source"])
                        svg_layer = QgsSvgMarkerSymbolLayer(svg_path, 5.0)
                        new_symbol = QgsMarkerSymbol()
                        new_symbol.changeSymbolLayer(0, svg_layer)
                    elif strategy == "simple":
                        shape_str = matched_cfg.get("shape", "circle")
                        shape_map = {"circle": QgsSimpleMarkerSymbolLayer.Circle,
                                     "square": QgsSimpleMarkerSymbolLayer.Square,
                                     "diamond": QgsSimpleMarkerSymbolLayer.Diamond,
                                     "triangle": QgsSimpleMarkerSymbolLayer.Triangle}
                        marker_layer = QgsSimpleMarkerSymbolLayer()
                        marker_layer.setShape(shape_map.get(shape_str, QgsSimpleMarkerSymbolLayer.Circle))
                        marker_layer.setFillColor(QColor(matched_cfg.get("color", "#ff0000")))
                        marker_layer.setStrokeColor(QColor("#ffffff"))
                        marker_layer.setStrokeWidth(0.4)
                        marker_layer.setSize(matched_cfg.get("size", 3.0))
                        new_symbol = QgsMarkerSymbol()
                        new_symbol.changeSymbolLayer(0, marker_layer)

                    if new_symbol:
                        category.setSymbol(new_symbol)
                        category.setLabel(matched_cfg["legend_label"])

                updated_categories.append(category)

            # --- INTELLIGENTES LEGERDEN-SORTING FÜR MODUS 2 ---
            wunsch_treffer = []
            bunter_rest = []

            for cat in updated_categories:
                cat_value = str(cat.value()).strip().lower()

                # Wir prüfen, ob dieser Eintrag zu unseren GUI-Regeln gehört
                ist_wunsch_icon = False
                for gui_val in field_mapping.keys():
                    if gui_val in cat_value:
                        ist_wunsch_icon = True
                        break

                if ist_wunsch_icon:
                    wunsch_treffer.append(cat)
                else:
                    bunter_rest.append(cat)

            # Die Wunsch-Icons nach oben legen und den Rest unberührt darunter hängen!
            finale_reihenfolge = wunsch_treffer + bunter_rest

            # Den Renderer sauber neu befüllen
            renderer.deleteAllCategories()
            for cat in finale_reihenfolge:
                renderer.addCategory(cat)

        # --- GEMEINSAMES FINISHING FÜR PUNKTE ---
        if hasattr(layer, "emitStyleChanged"):
            layer.emitStyleChanged()

        try:
            iface = qgis.utils.iface
            if iface and iface.layerTreeView():
                iface.layerTreeView().refreshLayerSymbology(layer.id())
        except Exception:
            pass

        layer.triggerRepaint()
        return True

    def apply_landuse_advanced_features(self, layer, enable_labels=True):
        """Erweiterte kartografische Behandlung und Beschriftung für Flächen-Layer (Landuse/Water)."""

        layer_name = layer.name() or "Unbenannt"
        fields = layer.fields()

        # 1. Altes Labeling restlos entfernen, um Geister-Labeling zu unterbinden
        layer.setLabelsEnabled(False)
        layer.setLabeling(None)

        # 2. Beschriftung auswerten und anwenden basierend auf der statischen Klassenvariable
        live_flag = StyleEngine.enable_landuse_labels

        if live_flag is True:
            # Intelligente Feldauswahl: 'name' bevorzugen, sonst 'fclass' als Typ-Anzeige nutzen
            target_field = "fclass"
            if fields.indexOf("name") >= 0:
                target_field = "name"
            elif fields.indexOf("landuse") >= 0:
                target_field = "landuse"

            field_idx = fields.indexOf(target_field)
            if field_idx >= 0:
                label_settings = QgsPalLayerSettings()
                label_settings.fieldName = target_field

                # Horizontale Platzierung im Polygon zentriert
                label_settings.placement = QgsPalLayerSettings.Horizontal
                label_settings.centroidWhole = True
                label_settings.fitInPolygonOnly = True  # Nur zeichnen, wenn es flächenmäßig reinpasst

                text_format = QgsTextFormat()
                text_format.setFont(QFont("Arial", 7, QFont.StyleItalic))  # Schön kursiv für Naturflächen
                text_format.setColor(QColor("#454545"))

                # Dezenter Puffer (weißer Rand), damit Schrift auf grünem/blauem Grund lesbar ist
                buffer_settings = QgsTextBufferSettings()
                buffer_settings.setEnabled(True)
                buffer_settings.setSize(0.6)
                buffer_settings.setColor(QColor("#ffffff"))
                text_format.setBuffer(buffer_settings)

                label_settings.setFormat(text_format)
                layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))
                layer.setLabelsEnabled(True)

        if hasattr(layer, "emitStyleChanged"):
            layer.emitStyleChanged()
        layer.triggerRepaint()
        return True


style_engine = StyleEngine()