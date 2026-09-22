# Style Auto Plugin
# Copyright (C) 2026 Heinz Danner
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# See the LICENSE file for more details.

from dataclasses import dataclass, field
import os


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------

@dataclass
class LineStyleDef:
    color: str = "#808080"
    width: float = 0.6
    penstyle: str = "solid"


@dataclass
class ValueRule:
    enabled: bool = True
    value: str = ""
    label: str = ""
    style: LineStyleDef = field(default_factory=LineStyleDef)


@dataclass
class FieldRuleSet:
    enabled: bool = True
    field_name: str = ""
    priority: int = 0
    rules: list = field(default_factory=list)
    fallbackstyle: LineStyleDef | None = None


@dataclass
class MatchConfig:
    geometry_type: str | None = None
    field_hints: list = field(default_factory=list)
    preferred_field_order: list = field(default_factory=list)
    value_hints: list = field(default_factory=list)
    name_hints: list = field(default_factory=list)
    min_match_score: int = 1

    # legacy compatibility
    layer_name_pattern: str = ""


@dataclass
class LayerRuleSet:
    enabled: bool = True
    priority: int = 0
    match: MatchConfig | None = None
    fieldrulesets: list = field(default_factory=list)


@dataclass
class StyleSource:
    qml_path: str = ""
    use_qml_first: bool = True
    fallback_to_rules: bool = True


@dataclass
class StyleProfile:
    enabled: bool = True
    id: str = ""
    label: str = ""
    priority: int = 0
    match: MatchConfig | None = None
    style_source: StyleSource | None = None
    field_ruleset: FieldRuleSet | None = None


@dataclass
class PluginConfig:
    usefallbackstyleforunknownvalues: bool = True
    allownamemismatchfallback: bool = True
    compactlegend: bool = True 
    style_profiles: list = field(default_factory=list)
    layerrulesets: list = field(default_factory=list)


# ----------------------------------------------------------------------
# Low-level helpers
# ----------------------------------------------------------------------

def _plugin_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _config_path():
    return os.path.join(_plugin_dir(), "style_config.json")


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "ja", "on")
    return bool(value)


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get_first(data, *keys, default=None):
    for key in keys:
        if key in data:
            return data[key]
    return default


# ----------------------------------------------------------------------
# Parsers
# ----------------------------------------------------------------------

def _parse_line_style_def(data):
    if not isinstance(data, dict):
        return LineStyleDef()

    return LineStyleDef(
        color=str(data.get("color", "#808080")),
        width=_as_float(data.get("width", 0.6), 0.6),
        penstyle=str(data.get("penstyle", "solid"))
    )


def _parse_value_rule(data):
    if not isinstance(data, dict):
        return ValueRule()

    return ValueRule(
        enabled=_as_bool(data.get("enabled", True), True),
        value=str(data.get("value", "")),
        label=str(data.get("label", "")),
        style=_parse_line_style_def(data.get("style", {}))
    )


def _parse_field_ruleset(data):
    if not isinstance(data, dict):
        return FieldRuleSet()

    rules = [
        _parse_value_rule(item)
        for item in _as_list(data.get("rules", []))
        if isinstance(item, dict)
    ]

    fallbackstyle_raw = _get_first(data, "fallbackstyle", "fallback_style", default=None)
    fallbackstyle = _parse_line_style_def(fallbackstyle_raw) if isinstance(fallbackstyle_raw, dict) else None

    field_name = _get_first(data, "field_name", "fieldname", default="")

    return FieldRuleSet(
        enabled=_as_bool(data.get("enabled", True), True),
        field_name=str(field_name),
        priority=_as_int(data.get("priority", 0), 0),
        rules=rules,
        fallbackstyle=fallbackstyle
    )


def _parse_match_config(data):
    if not isinstance(data, dict):
        return MatchConfig()

    geometry_type = _get_first(data, "geometry_type", "geometrytype", default=None)
    layer_name_pattern = _get_first(data, "layer_name_pattern", "layernamepattern", default="")

    field_hints = _as_list(_get_first(data, "field_hints", default=[]))
    preferred_field_order = _as_list(_get_first(data, "preferred_field_order", default=[]))
    value_hints = _as_list(_get_first(data, "value_hints", default=[]))
    name_hints = _as_list(_get_first(data, "name_hints", default=[]))

    # legacy fallback: if only layer_name_pattern exists, keep it also as a weak name hint
    if layer_name_pattern and not name_hints:
        name_hints = [layer_name_pattern]

    return MatchConfig(
        geometry_type=str(geometry_type).strip().lower() if geometry_type else None,
        field_hints=[str(v).strip() for v in field_hints if str(v).strip()],
        preferred_field_order=[str(v).strip() for v in preferred_field_order if str(v).strip()],
        value_hints=[str(v).strip() for v in value_hints if str(v).strip()],
        name_hints=[str(v).strip() for v in name_hints if str(v).strip()],
        min_match_score=_as_int(data.get("min_match_score", 1), 1),
        layer_name_pattern=str(layer_name_pattern).strip()
    )


def _parse_style_source(data):
    if not isinstance(data, dict):
        return StyleSource()

    return StyleSource(
        qml_path=str(data.get("qml_path", "")),
        use_qml_first=_as_bool(data.get("use_qml_first", True), True),
        fallback_to_rules=_as_bool(data.get("fallback_to_rules", True), True)
    )


def _parse_layer_ruleset(data):
    if not isinstance(data, dict):
        return LayerRuleSet()

    match_raw = data.get("match", None)

    # legacy support: top-level keys instead of nested "match"
    if not isinstance(match_raw, dict):
        match_raw = {
            "layer_name_pattern": _get_first(data, "layer_name_pattern", "layernamepattern", default=""),
            "geometry_type": _get_first(data, "geometry_type", "geometrytype", default=None),
        }

    fieldrulesets_raw = _get_first(data, "fieldrulesets", "field_rulesets", default=[])

    return LayerRuleSet(
        enabled=_as_bool(data.get("enabled", True), True),
        priority=_as_int(data.get("priority", 0), 0),
        match=_parse_match_config(match_raw),
        fieldrulesets=[
            _parse_field_ruleset(item)
            for item in _as_list(fieldrulesets_raw)
            if isinstance(item, dict)
        ]
    )


def _parse_style_profile(data):
    if not isinstance(data, dict):
        return StyleProfile()

    match_raw = data.get("match", {})
    style_source_raw = data.get("style_source", {})
    field_ruleset_raw = _get_first(data, "field_ruleset", "fieldruleset", default=None)

    field_ruleset = None
    if isinstance(field_ruleset_raw, dict):
        field_ruleset = _parse_field_ruleset(field_ruleset_raw)

    return StyleProfile(
        enabled=_as_bool(data.get("enabled", True), True),
        id=str(data.get("id", "")),
        label=str(data.get("label", "")),
        priority=_as_int(data.get("priority", 0), 0),
        match=_parse_match_config(match_raw),
        style_source=_parse_style_source(style_source_raw),
        field_ruleset=field_ruleset
    )


def _parse_plugin_config(data):
    if not isinstance(data, dict):
        return PluginConfig()

    style_profiles_raw = _get_first(data, "style_profiles", "styleProfiles", default=[])
    layerrulesets_raw = _get_first(data, "layerrulesets", "layer_rulesets", default=[])

    return PluginConfig(
        usefallbackstyleforunknownvalues=_as_bool(
            _get_first(data, "usefallbackstyleforunknownvalues", "use_fallback_style_for_unknown_values", default=True),
            True
        ),
        allownamemismatchfallback=_as_bool(
            _get_first(data, "allownamemismatchfallback", "allow_name_mismatch_fallback", default=True),
            True
        ),
        compactlegend=_as_bool(                       # NEU
            _get_first(
                data,"compactlegend","compact_legend",default=True,
            ),
            True,
        ),
        style_profiles=[
            _parse_style_profile(item)
            for item in _as_list(style_profiles_raw)
            if isinstance(item, dict)
        ],
        layerrulesets=[
            _parse_layer_ruleset(item)
            for item in _as_list(layerrulesets_raw)
            if isinstance(item, dict)
        ]
    )


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def get_config():
    import json # REPARATUR: Steht jetzt sicher hier drin für alle nachfolgenden Zeilen!
    config_file = _config_path()

    if not os.path.exists(config_file):
        return None, f"Konfigurationsdatei nicht gefunden: {config_file}"

    try:
        with open(config_file, "r", encoding="utf-8") as handle:
            raw_data = json.load(handle)
    except json.JSONDecodeError as exc:
        return None, f"JSON-Fehler in Konfiguration: {exc}"
    except OSError as exc:
        return None, f"Konfigurationsdatei konnte nicht gelesen werden: {exc}"

    try:
        config = _parse_plugin_config(raw_data)
        return config, None
    except Exception as exc:
        return None, f"Konfiguration konnte nicht verarbeitet werden: {exc}"
