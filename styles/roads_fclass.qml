{
  "enabled": true,
  "priority": 60,
  "match": {
    "geometry_type": "polygon",
    "field_hints": ["type", "building", "fclass"],
    "preferred_field_order": ["type", "building", "fclass"],
    "name_hints": ["building", "buildings", "gebäude", "gebaeude"],
    "min_match_score": 4
  },
  "fieldrulesets": [
    {
      "enabled": true,
      "field_name": "type",
      "priority": 60,
      "rules": [
        {
          "enabled": true,
          "value_list": ["apartments"],
          "label": "Test Apartments",
          "style": {
            "fill_color": "#ff0000",
            "fill_opacity": 1.0,
            "outline_color": "#000000",
            "outline_width": 0.80
          }
        }
      ]
    }
  ]
}