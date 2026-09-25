import os
import qgis.utils

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,  # --- FIX: Import the core enum for log levels (Critical, Warning, Info). ---
    QgsProject,
    QgsFeatureRequest,
    QgsStyle,
    QgsUnitTypes,
    QgsMapLayerType,
    # --- Symbology and effects ---
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
    # --- Labeling ---
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
# Global Geofabrik translation lookup for roads, buildings, and points
# ==============================================================================
GEOFABRIK_CODE_MAP = {
    # === ROADS / PATHS (geom: Line) ===
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

    # === BUILDINGS / POLYGONS (geom: Polygon) ===
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

    # === POIS / POINTS (geom: Point) ===
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

        # --- Independent runtime flags (core features) ---
        self.enable_labels = False  # For road labeling
        self.enable_building_labels = False  # For building labeling
        self.enable_building_smoothing = True  # Default: smoothing enabled
        self.enable_building_shadow = True  # Default: shadow enabled
        self.enable_landuse_labels = True  # Default: landuse labels enabled

        # Synchronize once if a config already exists at startup
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

        # FIX: If raw is None, keep the existing state.
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
        """Read a value from either dict-based or object-based configs
        (for example PluginConfig) using one or more possible keys.
        Consolidates the previously duplicated
        'isinstance(config, dict) -> .get() else getattr()' logic."""
        if isinstance(obj, dict):
            for name in names:
                if name in obj:
                    return obj[name]
            return default

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
            config_mappings = self._get_attr(config, "custom_mappings", default=[])

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

        # Additional value-based scoring is applied here.
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
        Bonus score for clear landuse/building cases based on attribute values.
        """
        provider = layer.dataProvider()
        field_index = layer.fields().indexOf(field_name)
        if field_index < 0:
            return 0, []

        unique_values = provider.uniqueValues(field_index)
        reasons = []
        bonus = 0

        # Use only unambiguous cases
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
        # Load from cache
        symbol = self._symbol_cache.get(key)
        if symbol is not None:
            return symbol.clone()

        # Rebuild and cache
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

        # Existing symbol creation logic
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
            # Ignore None/NULL
            if v is None:
                continue
            values.add(v)

        return list(values)

    def apply_categorized_renderer_with_fallback(self, layer, fieldruleset, detected_field_name=None):
        missing_values=''
        if not fieldruleset or not getattr(fieldruleset, "enabled", False):
            return False

        layer_geometry = self.get_layer_geometry_type_name(layer)

        # IMPORTANT: determine the field name
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
            # Keep fallback entries at the end:
            # True > False when sorting, so 1 for fallback, 0 for normal
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
        # --- Step 1: fast XML sanity check (avoids the 10-second wait) ---
        # ==============================================================================
        if qml_path and os.path.exists(qml_path) and "roads_fclass.qml" in str(qml_path):
            try:
                with open(qml_path, 'r', encoding='utf-8', errors='ignore') as f:
                    erste_zeile = f.readline()

                # If the file is corrupt (broken from line 1), detect it immediately.
                if not erste_zeile or "<" not in erste_zeile:
                    # Keep the fast crash guard, but without extra log noise.
                    return False, "Datei ist korrupt."
            except Exception as sanity_err:
                QgsMessageLog.logMessage(
                    f"Sanity-Check für qml_path fehlgeschlagen: {sanity_err}",
                    "Style Auto Plugin", Qgis.Warning)

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

            # Safety net: if loading is intentionally blocked or aborted due to corruption,
            # suppress the red CRITICAL log entry so the plugin can continue cleanly.
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
        # ==============================================================================
        geom_type = self.get_layer_geometry_type_name(layer)

        # ==============================================================================
        # Determine the mode and cartographic booleans once (previously duplicated here)
        # FIX: road_style_mode was previously read only via getattr(), causing a
        # dict-based config object (for example from the dialog GUI) to fall back to mode 2.
        # ==============================================================================
        try:
            mode = int(self._get_attr(config, "road_style_mode", default=2))
        except (ValueError, TypeError):
            mode = 2

        self.sync_runtime_bools_from_config(config)

        enable_road_features = bool(self._get_attr(config, "enable_advanced_road_features", default=True))
        enable_road_labels = bool(self._get_attr(config, "enable_road_labels", default=True))
        enable_building_features = bool(self._get_attr(config, "enable_advanced_building_features", default=True))
        enable_building_smoothing = bool(self._get_attr(config, "enable_building_edge_smoothing", default=True))
        enable_building_shadow = bool(self._get_attr(config, "enable_building_drop_shadow", default=True))
        enable_landuse_labels = bool(self._get_attr(config, "enable_landuse_labels", default=True))
        enable_point_features = bool(self._get_attr(config, "enable_advanced_point_features", default=True))
        enable_building_labels = self.enable_building_labels

        result = None
        # ==============================================================================
        # CASE 0: pure base styling (mode 0)
        # ==============================================================================
        if mode == 0:
            # 1. First apply the normal JSON base styling
            result = self._execute_base_styling(layer, config, plugin_dir)

            # 2. Apply mode-0-specific corrections/constraints
            if geom_type == "line":
                result = {"success": True, "message": "Basis-Straßen-Styling angewendet (Modus 0)."}

            elif geom_type == "polygon" and enable_building_features:
                if layer.fields().indexOf("building") >= 0 or layer.fields().indexOf(
                        "type") >= 0 or layer.fields().indexOf("fclass") >= 0:
                    self.apply_building_symbol_mapping(
                        layer, enable_smoothing=True, enable_shadow=False,
                        reines_einzelstyling=False, enable_labels=False, ignore_user_styles=True
                    )
                    result = {"success": True, "message": "Basis-Gebäude-Styling angewendet (Modus 0)."}

            elif geom_type == "point":
                result = {"success": True, "message": "Basis-Punkt-Styling angewendet (Modus 0)."}

        # ==============================================================================
        # CASE 1: pure single-symbol styling (mode 1 - base styling is fully ignored)
        # ==============================================================================
        elif mode == 1:
            # Internal branch by geometry type
            if geom_type == "line":
                # FIX: enable_road_features ("Enable road hierarchy & thick line designs")
                # now controls only the hierarchy extras (symbol-level merging and round
                # caps/joins) inside apply_road_symbol_mapping itself. The custom mappings
                # (colors/symbols per road type) must always be applied independently.
                # Previously, disabling the toggle skipped the full road styling and forced
                # a plain gray line instead.
                success = self.apply_road_symbol_mapping(
                    layer, config=config, reines_einzelstyling=True, enable_labels=enable_road_labels
                )
                if success:
                    result = {"success": True, "message": "Reines Straßen-Einzelstyling angewendet (Modus 1)."}

            elif geom_type == "polygon":

                # --- Semantic scoring (identical to mode 2) ---

                building_score = 0

                landuse_score = 0

                # Scan the first 50 features for best performance
                request = QgsFeatureRequest().setLimit(50)

                idx_building = layer.fields().indexOf("building")

                idx_type = layer.fields().indexOf("type")

                idx_landuse = layer.fields().indexOf("landuse")

                idx_fclass = layer.fields().indexOf("fclass")

                for feature in layer.getFeatures(request):

                    # Check building indicators

                    if idx_building >= 0 and feature.attribute(idx_building):

                        val = str(feature.attribute(idx_building)).strip().lower()

                        if val and val != "no" and val != "null":
                            building_score += 2

                    if idx_type >= 0 and feature.attribute(idx_type):

                        val = str(feature.attribute(idx_type)).strip().lower()

                        if val in ["apartments", "house", "detached", "commercial", "industrial", "residential"]:
                            building_score += 2

                    # Check area indicators (landuse)

                    if idx_landuse >= 0 and feature.attribute(idx_landuse):

                        val = str(feature.attribute(idx_landuse)).strip().lower()

                        if val and val != "null":
                            landuse_score += 2

                    if idx_fclass >= 0 and feature.attribute(idx_fclass):

                        val = str(feature.attribute(idx_fclass)).strip().lower()

                        if val in ["forest", "park", "grass", "water", "meadow", "commercial", "industrial"]:
                            landuse_score += 1

                # --- Decision ---

                if landuse_score > building_score or (idx_landuse >= 0 and idx_building < 0):

                    # FIX: "apply_landuse_symbol_mapping" never existed as a method,
                    # which made the landuse toggle (enable_landuse_labels) ineffective
                    # in mode 1. Reuse the same labeling logic as in mode 2.
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

            # 1. Always pre-apply the JSON base styling first

            result = self._execute_base_styling(layer, config, plugin_dir)

            # 2. Then inject the advanced single-symbol styling

            # FIX: enable_road_features must no longer prevent the custom mappings
            # from being called here; within apply_road_symbol_mapping it controls
            # only the hierarchy extras (symbol levels plus round caps/joins).

            if geom_type == "line":

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

                # Detection logic: inspect the attribute table directly and scan values

                # ==============================================================================

                building_score = 0

                landuse_score = 0

                # Limit the scan to 50 features for best QGIS performance

                request = QgsFeatureRequest().setLimit(50)

                idx_building = layer.fields().indexOf("building")

                idx_type = layer.fields().indexOf("type")

                idx_landuse = layer.fields().indexOf("landuse")

                idx_fclass = layer.fields().indexOf("fclass")

                # Loop through the real table entries

                for feature in layer.getFeatures(request):

                    # 1. Count building values in the table

                    if idx_building >= 0 and feature.attribute(idx_building):

                        val = str(feature.attribute(idx_building)).strip().lower()

                        if val and val not in ("no", "null", "none"):
                            building_score += 2

                    if idx_type >= 0 and feature.attribute(idx_type):

                        val = str(feature.attribute(idx_type)).strip().lower()

                        if val in ["apartments", "house", "detached", "commercial", "industrial", "residential"]:
                            building_score += 2

                    # 2. Count area values (landuse) in the table

                    if idx_landuse >= 0 and feature.attribute(idx_landuse):

                        val = str(feature.attribute(idx_landuse)).strip().lower()

                        if val and val != "null":
                            landuse_score += 2

                    if idx_fclass >= 0 and feature.attribute(idx_fclass):

                        val = str(feature.attribute(idx_fclass)).strip().lower()

                        if val in ["forest", "park", "grass", "water", "meadow", "scrub", "heath"]:
                            landuse_score += 2

                # Safety fallback based on the layer name if the table was empty (0 vs. 0)

                layer_name_lower = (layer.name() or "").lower()

                if building_score == 0 and landuse_score == 0:

                    if "landuse" in layer_name_lower or "water" in layer_name_lower or "natural" in layer_name_lower:

                        landuse_score = 5

                    else:

                        building_score = 5

                # ==============================================================================

                # Evaluate using the actual table-based scores

                # ==============================================================================

                if landuse_score > building_score:

                    # Clearly a landuse/area layer based on the table values

                    # FIX: this previously used "StyleEngine.enable_landuse_labels"
                    # (a stale class attribute updated only while the dialog was open)
                    # instead of the local variable correctly derived from config above—
                    # the same bug pattern seen with the building booleans.
                    self.apply_landuse_advanced_features(layer, enable_labels=enable_landuse_labels)

                    result = {"success": True, "message": "Kombiniertes Landuse-Flächenstyling erfolgreich (Modus 2)."}


                else:

                    # Clearly a building layer based on the table values

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
        # Safety net: if result is still None
        if result is None:
            result = {"success": True, "message": "Layer im Standard-Look belassen"}
        return result

    def _execute_base_styling(self, layer, config, plugin_dir=None):
        """Internal helper for the existing ruleset flow and QML/profile lookup."""
        # 1. Try style_profile
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
                    # --- Hard stop: when the road base toggle is disabled ---
                    # ==============================================================================
                    road_base_aktiv = True
                    if config:
                        road_base_aktiv = self._get_attr(config, "enable_advanced_road_features", default=True)

                    # If this is the road layer and the toggle is OFF:
                    if layer and "road" in layer.name().lower() and road_base_aktiv is False:
                        # Keep the logical block, but without extra log output.
                        success = False
                    else:
                        # Only when the toggle is ON may QGIS actually load the file:
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

        # 2. Try layerruleset
        layerruleset, detected_ruleset_field = self.find_layer_ruleset(layer, config)

        return self.apply_layer_ruleset_style(layer, layerruleset, detected_field_name=detected_ruleset_field)

    def apply_road_symbol_mapping(self, layer, config=None, reines_einzelstyling=False, enable_labels=True):
        if not layer:
            return False

        # ==============================================================================
        # --- Road hierarchy toggle (uses the passed config directly) ---
        # ==============================================================================
        # FIX: road_base_aktiv previously acted as a full master stop, replacing all
        # road styling—including custom mappings—with a plain gray line when disabled.
        # In the GUI, however, the toggle is labeled "Enable road hierarchy & thick
        # line designs" and is intended to control only hierarchy extras (symbol-level
        # merging plus round caps/joins), not road styling as a whole. It is therefore
        # used below only as an on/off switch for _optimize_line_caps_and_joins() and
        # setUsingSymbolLevels().
        road_base_aktiv = True
        if config:
            road_base_aktiv = self._get_attr(config, "enable_advanced_road_features", default=True)

        fields = layer.fields()

        style = QgsStyle.defaultStyle()

        project_style = QgsProject.instance().styleSettings().projectStyle()

        renderer = layer.renderer()
        if not renderer:
            return False

        # Determine dynamically which field QGIS is currently using
        renderer_field = "fclass"
        if hasattr(renderer, "classAttribute") and renderer.classAttribute():
            renderer_field = renderer.classAttribute().strip().lower()
        elif fields.indexOf("code") >= 0 and fields.indexOf("fclass") < 0:
            renderer_field = "code"

        # --- Robust field-agnostic JSON mapping for roads ---
        mapping = {}
        config_mappings = []
        if config:
            config_mappings = self._get_attr(config, "custom_mappings", default=[])

        if isinstance(config_mappings, list):
            for entry in config_mappings:
                if isinstance(entry, dict) and entry.get("active", True) and entry.get("geom") == "Line":
                    gui_value = str(entry.get("value", "")).strip().lower()

                    # --- Match through the global GEOFABRIK_CODE_MAP defined above ---
                    target_values = [gui_value]
                    if gui_value in GEOFABRIK_CODE_MAP:
                        target_values.append(GEOFABRIK_CODE_MAP[gui_value])

                    # If the layer uses 'code', force the numeric code
                    if renderer_field == "code":
                        if gui_value in GEOFABRIK_CODE_MAP:
                            target_value = GEOFABRIK_CODE_MAP[gui_value]
                        else:
                            target_value = gui_value

                        mapping[target_value] = {
                            "symbol_name": entry.get("style", ""),
                            "legend_label": entry.get("label", "")
                        }
                    # If the layer uses clear-text values (fclass/highway) or is field-agnostic:
                    else:
                        for t_val in target_values:
                            mapping[t_val] = {
                                "symbol_name": entry.get("style", ""),
                                "legend_label": entry.get("label", "")
                            }
        # Helper for rounded joins and line caps
        # FIX: In the QGIS API, QgsSimpleLineSymbolLayer and related classes use
        # setPenJoinStyle()/setPenCapStyle(), not setJoinStyle()/setCapStyle().
        # The previous hasattr() check was therefore always False, so round
        # caps/joins were never actually applied in either mode 1 or mode 2.
        def _optimize_line_caps_and_joins(symbol):
            if not symbol:
                return
            for i in range(symbol.symbolLayerCount()):
                layer_item = symbol.symbolLayer(i)
                if hasattr(layer_item, "setPenJoinStyle"):
                    layer_item.setPenJoinStyle(Qt.RoundJoin)
                if hasattr(layer_item, "setPenCapStyle"):
                    layer_item.setPenCapStyle(Qt.RoundCap)


        # --- Strategy for pure single-symbol styling (mode 1) ---
        if reines_einzelstyling:
            # Determine dynamically which field QGIS is currently using
            renderer_field = "fclass"
            if hasattr(renderer, "classAttribute") and renderer.classAttribute():
                renderer_field = renderer.classAttribute().strip().lower()
            elif fields.indexOf("code") >= 0 and fields.indexOf("fclass") < 0:
                renderer_field = "code"

            updated_categories = []

            # Safety set against duplicate legend entries
            erstellte_labels = set()

            for key, cfg in mapping.items():
                label_name = cfg["legend_label"]

                # If this label (for example "Automobilbahn") already exists, skip it
                if label_name in erstellte_labels:
                    continue

                # Search project styles first, then the global style library
                fetched_symbol = project_style.symbol(cfg["symbol_name"])
                if not (fetched_symbol and cfg["symbol_name"] in project_style.symbolNames()):
                    fetched_symbol = style.symbol(cfg["symbol_name"])

                if fetched_symbol:
                    cloned_symbol = fetched_symbol.clone()
                    if road_base_aktiv:
                        _optimize_line_caps_and_joins(cloned_symbol)

                    # The category key must match the active field
                    category_key = key
                    if renderer_field == "code" and key in GEOFABRIK_CODE_MAP:
                        category_key = GEOFABRIK_CODE_MAP[key]
                    elif renderer_field == "code" and key.isdigit():
                        category_key = key

                    new_cat = QgsRendererCategory(category_key, cloned_symbol, label_name)
                    updated_categories.append(new_cat)

                    # Mark the label as created
                    erstellte_labels.add(label_name)

            # --- Fallback catch-all: the "everything else" road category ---
            # Prevents unnamed roads from becoming invisible in mode 1.
            # FIX: Creates the gray line reliably through the QGIS property system.
            properties = {
                "line_color": "#cccccc",
                "line_width": "0.2",
                "penstyle": "dot"
            }

            fallback_layer = QgsSimpleLineSymbolLayer.create(properties)
            from qgis.core import QgsLineSymbol
            fallback_symbol = QgsLineSymbol()

            fallback_symbol.changeSymbolLayer(0, fallback_layer)
            if road_base_aktiv:
                _optimize_line_caps_and_joins(fallback_symbol)

            # An empty string '' as the key catches all undefined roads
            fallback_cat = QgsRendererCategory("", fallback_symbol, "Andere Straßen/Wege")
            updated_categories.append(fallback_cat)

            # Apply the completed renderer including the fallback category
            new_renderer = QgsCategorizedSymbolRenderer(renderer_field, updated_categories)
            layer.setRenderer(new_renderer)


        # --- Strategy for existing/historic styles (mode 2) ---
        else:
            # FIX: This previously read the class variable
            # StyleEngine.enable_advanced_road_features instead of road_base_aktiv,
            # which had already been derived from the passed config above. The two
            # could drift apart (for example with dict configs or in tests).
            enable_road_features = road_base_aktiv
            if renderer.type() == "categorizedSymbol":
                updated_categories = []

                # ==============================================================================
                # --- Faster in-memory cache (before the loop) ---
                # ==============================================================================
                # Read the symbol-name list only once here (0 ms inside the loop)
                available_project_symbols = set(project_style.symbolNames())
                symbol_cache = {}
                # ==============================================================================

                for category in renderer.categories():
                    val_str = str(category.value()).strip().lower()
                    if val_str in mapping:
                        cfg = mapping[val_str]
                        symbol_name = cfg["symbol_name"]

                        # --- Fast in-memory check instead of a new disk scan ---
                        if symbol_name not in symbol_cache:
                            # Check in the in-memory set whether the name exists
                            if symbol_name in available_project_symbols:
                                fetched_symbol = project_style.symbol(symbol_name)
                            else:
                                fetched_symbol = style.symbol(symbol_name)
                            # Cache it for the remaining thousands of roads
                            symbol_cache[symbol_name] = fetched_symbol
                        else:
                            # Fetch directly from memory without further overhead
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

        # ==============================================================================
        # --- Enforce road stacking (symbol levels) - applies to modes 1 and 2 ---
        # FIX: This block previously lived entirely inside the "else" branch (mode 2)
        # and therefore never ran in pure single-symbol styling (mode 1). As a result,
        # symbol levels stayed disabled in mode 1, so thicker roads (for example
        # motorways) did not stack cleanly above thinner roads, and cap/join behavior
        # differed from mode 2.
        # ==============================================================================
        active_renderer = layer.renderer()
        if active_renderer:
            # 1. Enable symbol levels so layers do not cut across each other
            if road_base_aktiv:
                active_renderer.setUsingSymbolLevels(True)

        # Optional: if motorways should always appear on top,
        # this QGIS setting helps them cross bridges cleanly
        if hasattr(layer, "setFeatureBlendMode"):
            layer.setFeatureBlendMode(0)  # Normal mode; avoids transparency artifacts

        # ==============================================================================
        # Road-name labeling and finalization - applies to modes 1 and 2
        # FIX: This section previously lived entirely inside the "else" branch (mode 2)
        # and therefore never ran in pure single-symbol styling (mode 1). That caused
        # the function to end in mode 1 without "return True" (implicit None), so the
        # caller received a false fallback status. The "Show Road Names" toggle also
        # had no effect in mode 1 because the code always read StyleEngine.enable_labels
        # instead of the passed enable_labels parameter.
        # ==============================================================================
        has_name = fields.indexOf("name") >= 0

        if bool(enable_labels) and has_name:
            label_settings = QgsPalLayerSettings()
            label_settings.fieldName = "name"
            label_settings.placement = QgsPalLayerSettings.Line

            # Density optimization for repeated road labels
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
            # If the toggle is off, remove only the labels
            layer.setLabelsEnabled(False)
            layer.setLabeling(None)

        try:
            iface = qgis.utils.iface
            if iface and iface.layerTreeView():
                iface.layerTreeView().refreshLayerSymbology(layer.id())
        except Exception as refresh_err:
            QgsMessageLog.logMessage(
                f"Konnte Layer-Symbologie nicht aktualisieren: {refresh_err}",
                "Style Auto Plugin", Qgis.Warning)

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
            # FIX: this previously always read the global class attribute
            # StyleEngine.enable_building_shadow (stale and updated only by the
            # most recently opened dialog). The config-driven function parameter
            # enable_shadow now decides consistently, including in headless runs.
            if not symbol or not enable_shadow:
                return

            # The old 'if not enable_shadow' guard was removed here.
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

            # Import the correct Qt type directly for the inner function
            from qgis.PyQt.QtCore import QPointF

            # FIX: this previously used "getattr(StyleEngine, 'enable_building_shadow', True)"
            # (a stale class attribute instead of the config-driven enable_shadow parameter).
            live_shadow = bool(enable_shadow)

            if live_shadow is True:
                try:
                    schon_da = False
                    for idx in range(symbol.symbolLayerCount()):
                        sl = symbol.symbolLayer(idx)
                        # Check using the imported QPointF
                        if hasattr(sl, "offset") and sl.offset() == QPointF(0.6, 0.6) and sl.strokeStyle() == Qt.NoPen:
                            schon_da = True
                            break

                    if not schon_da:
                        shadow_layer = QgsSimpleFillSymbolLayer()
                        shadow_layer.setFillColor(QColor(0, 0, 0, 45))
                        shadow_layer.setStrokeStyle(Qt.NoPen)

                        # Safe assignment
                        shadow_layer.setOffset(QPointF(0.6, 0.6))
                        shadow_layer.setOffsetUnit(QgsUnitTypes.RenderMillimeters)

                        symbol.insertSymbolLayer(0, shadow_layer)

                except Exception as shadow_err:
                    QgsMessageLog.logMessage(
                        f"Konnte Schatten-Effekt nicht anwenden: {shadow_err}",
                        "Style Auto Plugin", Qgis.Warning)

            else:
                try:
                    schichten_zu_loeschen = []
                    for idx in range(symbol.symbolLayerCount()):
                        sl = symbol.symbolLayer(idx)
                        if hasattr(sl, "offset") and sl.offset() == QPointF(0.6, 0.6) and sl.strokeStyle() == Qt.NoPen:
                            schichten_zu_loeschen.append(idx)

                    for idx in reversed(schichten_zu_loeschen):
                        symbol.deleteSymbolLayer(idx)
                except Exception as remove_err:
                    QgsMessageLog.logMessage(
                        f"Konnte Schatten-Symbolebene nicht entfernen: {remove_err}",
                        "Style Auto Plugin", Qgis.Warning)

            return symbol

        fields = layer.fields()
        style = QgsStyle.defaultStyle()
        project_style = QgsProject.instance().styleSettings().projectStyle()
        renderer = layer.renderer()
        if not renderer:
            return False

        def _dbg(msg):
            # Keep the inner helper completely silent and crash-safe
            pass

        # The following lines stay at method scope with the intended indentation.
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
            config_mappings = self._get_attr(config, "custom_mappings", default=[])

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
                # FIX: this previously read StyleEngine.enable_building_smoothing
                # (a stale class attribute) instead of the config-driven parameter
                # enable_smoothing, so smoothing did not respond reliably to the checkbox.
                # ==============================================================================
                live_smoothing = enable_smoothing

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

                # Continue with the existing code path unchanged:
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
        # Mode 2 strategy: combined enhancement of the existing renderer
        # ------------------------------------------------------------------
        else:
            def _apply_building_smoothing(symbol):
                # FIX: this previously read StyleEngine.enable_building_smoothing
                # (a stale class attribute) instead of the config-driven
                # enable_smoothing parameter.
                live_smoothing = enable_smoothing

                if not symbol:
                    return

                if live_smoothing is False:
                    # If smoothing is off, remove the outline from all symbol layers
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
        # Shared finalization and labels
        # ------------------------------------------------------------------
        active_renderer = layer.renderer()
        if active_renderer and hasattr(active_renderer, "setUsingSymbolLevels"):
            active_renderer.setUsingSymbolLevels(True)

        if hasattr(layer, "setFeatureBlendMode"):
            layer.setFeatureBlendMode(0)

        # ==============================================================================
        # FIX: this previously read "StyleEngine.enable_building_labels" and
        # "StyleEngine.enable_building_shadow"—two stale class attributes that
        # were updated only while the dialog was open and checkbox clicks occurred.
        # In a headless run(), they were never synchronized from config. In addition,
        # "or StyleEngine.enable_building_shadow is True" forced labels on whenever
        # the 2.5D shadow toggle was active, regardless of the labeling toggle.
        # Only the config-driven enable_labels parameter should matter here.
        # ==============================================================================
        has_name = fields.indexOf("name") >= 0
        if bool(enable_labels) and has_name:

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

        else:
            layer.setLabelsEnabled(False)
            layer.setLabeling(None)

        if hasattr(layer, "emitStyleChanged"):
            layer.emitStyleChanged()

        try:
            iface = qgis.utils.iface
            if iface and iface.layerTreeView():
                iface.layerTreeView().refreshLayerSymbology(layer.id())
        except Exception as refresh_err:
            QgsMessageLog.logMessage(
                f"Konnte Layer-Symbologie nicht aktualisieren: {refresh_err}",
                "Style Auto Plugin", Qgis.Warning)

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

        # Determine dynamically which field QGIS is currently using
        renderer_field = "fclass"
        if hasattr(renderer, "classAttribute") and renderer.classAttribute():
            renderer_field = renderer.classAttribute().strip().lower()
        elif fields.indexOf("amenity") >= 0:
            renderer_field = "amenity"
        elif fields.indexOf("code") >= 0:
            renderer_field = "code"

        # --- Dynamic field-agnostic JSON mapping for points (POIs) ---
        field_mapping = {}
        config_mappings = []
        if config:
            config_mappings = self._get_attr(config, "custom_mappings", default=[])

        if isinstance(config_mappings, list):
            for entry in config_mappings:
                if isinstance(entry, dict) and entry.get("active", True) and str(
                        entry.get("geom", "")).lower() == "point":
                    gui_value = str(entry.get("value", "")).strip().lower()

                    # --- Robust fallback matching via GEOFABRIK codes ---
                    target_values = [gui_value]
                    if gui_value in GEOFABRIK_CODE_MAP:
                        target_values.append(GEOFABRIK_CODE_MAP[gui_value])

                    # If the layer uses 'code' (numeric values), force the code number
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
                    # If the layer uses clear-text values (fclass, amenity):
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
        # --- Mode 1 / empty-layer strategy: compact rebuild ---
        # ==============================================================================
        # FIX: mode 2 is intentionally excluded here.
        # Rebuild the legend from scratch only when mode 1 is forced.
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

            # The gray fallback now applies strictly only to pure single-symbol styling.
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
        # --- Mode 2 strategy: combined enhancement with prefix-tolerant matching ---
        # ==============================================================================
        else:
            # --- Fallback rescue for empty layers in mode 2 ---
            if renderer.type() != "categorizedSymbol" or len(renderer.categories()) == 0:
                # Attempt 1: trigger the built-in base styling
                basis_erfolgreich = False
                if hasattr(self, "_execute_base_styling"):
                    try:
                        self._execute_base_styling(layer, config)
                        renderer = layer.renderer()
                        if renderer and renderer.type() == "categorizedSymbol" and len(renderer.categories()) > 0:
                            basis_erfolgreich = True
                    except Exception:
                        basis_erfolgreich = False

                # Attempt 2: if base styling rejects the layer, force QGIS to build
                # categories directly from the actual attribute values.
                if not basis_erfolgreich:
                    # Create a fresh renderer on the active field
                    default_renderer = QgsCategorizedSymbolRenderer(renderer_field, [])

                    # Tell QGIS to scan the field and create a colored category with
                    # random styling for each unique value (school, bank, etc.).
                    default_renderer.setClassAttribute(renderer_field)

                    # Retrieve all unique values from the table
                    unique_values = []
                    idx = fields.indexOf(renderer_field)
                    if idx >= 0:
                        unique_values = layer.uniqueValues(idx)

                    # Populate categories in memory
                    for val in unique_values:
                        if val is not None and str(val).strip():
                            # Create a default point symbol with a random color
                            sym = QgsMarkerSymbol.createSimple({"name": "circle", "size": "3.0"})
                            cat = QgsRendererCategory(str(val), sym, str(val))
                            default_renderer.addCategory(cat)

                    layer.setRenderer(default_renderer)
                    renderer = layer.renderer()

            updated_categories = []

            for category in renderer.categories():

                cat_value = str(category.value()).strip().lower()
                symbol = category.symbol()

                # --- Flexible fallback and prefix matching ---
                matched_cfg = None

                # Minimal mode-2 fix: prevent generic 'buildings' from taking the residential-building symbol
                for gui_val, cfg in field_mapping.items():
                    if gui_val == cat_value:
                        matched_cfg = cfg
                        break
                    elif renderer_field == "code" and gui_val in GEOFABRIK_CODE_MAP and GEOFABRIK_CODE_MAP[
                        gui_val] == cat_value:
                        matched_cfg = cfg
                        break

                    # Case 3: prefix-based recovery for points (for example "[F] School")
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

            # --- Intelligent legend sorting for mode 2 ---
            wunsch_treffer = []
            bunter_rest = []

            for cat in updated_categories:
                cat_value = str(cat.value()).strip().lower()

                # Check whether this entry belongs to one of the GUI rules
                ist_wunsch_icon = False
                for gui_val in field_mapping.keys():
                    if gui_val in cat_value:
                        ist_wunsch_icon = True
                        break

                if ist_wunsch_icon:
                    wunsch_treffer.append(cat)
                else:
                    bunter_rest.append(cat)

            # Put the preferred icons first and keep the remaining entries below them
            finale_reihenfolge = wunsch_treffer + bunter_rest

            # Rebuild the renderer in the desired order
            renderer.deleteAllCategories()
            for cat in finale_reihenfolge:
                renderer.addCategory(cat)

        # --- Shared finalization for points ---
        if hasattr(layer, "emitStyleChanged"):
            layer.emitStyleChanged()

        try:
            iface = qgis.utils.iface
            if iface and iface.layerTreeView():
                iface.layerTreeView().refreshLayerSymbology(layer.id())
        except Exception as refresh_err:
            QgsMessageLog.logMessage(
                f"Konnte Layer-Symbologie nicht aktualisieren: {refresh_err}",
                "Style Auto Plugin", Qgis.Warning)

        layer.triggerRepaint()
        return True

    def apply_landuse_advanced_features(self, layer, enable_labels=True):
        """Advanced cartographic treatment and labeling for area layers (landuse/water)."""

        layer_name = layer.name() or "Unbenannt"
        fields = layer.fields()

        # 1. Fully remove old labeling to avoid ghost labels
        layer.setLabelsEnabled(False)
        layer.setLabeling(None)

        # 2. Evaluate labeling based on the passed parameter
        #    (FIX: this previously always read StyleEngine.enable_landuse_labels
        #    and ignored the passed enable_labels parameter entirely)
        live_flag = bool(enable_labels)

        if live_flag is True:
            # Smart field selection: prefer 'name', otherwise use 'fclass' as the type label
            target_field = "fclass"
            if fields.indexOf("name") >= 0:
                target_field = "name"
            elif fields.indexOf("landuse") >= 0:
                target_field = "landuse"

            field_idx = fields.indexOf(target_field)
            if field_idx >= 0:
                label_settings = QgsPalLayerSettings()
                label_settings.fieldName = target_field

                # Centered horizontal placement inside the polygon
                label_settings.placement = QgsPalLayerSettings.Horizontal
                label_settings.centroidWhole = True
                label_settings.fitInPolygonOnly = True  # Draw only when it fits within the area

                text_format = QgsTextFormat()
                text_format.setFont(QFont("Arial", 7, QFont.StyleItalic))  # Italic styling for natural areas
                text_format.setColor(QColor("#454545"))

                # Subtle white buffer to keep text readable on green/blue backgrounds
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