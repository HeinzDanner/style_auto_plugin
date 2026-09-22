# Style Auto Plugin

Style Auto Plugin ist ein QGIS-Python-Plugin, das automatisch einen kategorisierten Stil auf den aktuell aktiven Layer anwendet.

Die Styling-Regeln werden hochperformant aus der Konfiguration geladen. Dabei werden Regelsätze nach Layername, Geometrietyp, Feldname und Priorität ausgewählt. Für nicht explizit konfigurierte Werte kann optional ein Fallback-Stil verwendet werden.

## Funktionen

- Automatische Auswahl eines passenden Layer-Regelsatzes.
- Auswahl des passenden Feld-Regelsatzes nach Priorität.
- Drei auswählbare Global Styling Modi (Modus 0, 1 und 2).
- Sechs zuschaltbare kartografische Optionen über die GUI.
- Kategorisierte Symbolisierung auf Basis eines Feldes.
- Duplikatssicherer automatischer Symbol-Import für Tester.
- Schneller RAM-Cache zur Vermeidung von Festplatten-Scans.
- Optionaler Fallback-Stil für nicht konfigurierte Werte.
- Robuster, stummgeschalteter Kern ohne Log-Müllberge.

## Voraussetzungen

- QGIS 3.28 oder neuer
- Eine gültige Konfigurationsdatei im Plugin-Verzeichnis

## Plugin-Struktur

Das Plugin folgt der QGIS-Python-Plugin-Struktur mitsamt dem erweiterten `styles`-Ressourcenordner.

```text
style_auto_plugin/
├── __init__.py
├── LICENSE
├── README.md
├── main.py
├── metadata.txt
├── style_auto_plugin.py
├── style_auto_plugin_dialog.py
├── style_config.py
├── style_engine.py
├── style_rules.json
└── styles/
    ├── style_symbols.xml
    ├── roads_fclass.qml
    └── hospital.svg
```

## Installation

### Lokale Installation

1. Den Ordner `style_auto_plugin` in das lokale QGIS-Plugin-Verzeichnis kopieren.
2. QGIS neu starten.
3. Das Plugin im Plugin-Manager aktivieren.

Typisches Plugin-Verzeichnis unter Windows:

```text
C:\Users\<Benutzername>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins
```

### Installation aus ZIP

1. Den vollständigen Ordner `style_auto_plugin` als ZIP-Datei packen.
2. In QGIS `Plugins` -> `Manage and Install Plugins...` öffnen.
3. `Install from ZIP` auswählen.
4. Die ZIP-Datei auswählen und installieren.

## Konfiguration

Die Regeln werden standardmäßig aus der Konfigurationsdatei geladen. Das Einstellungsfenster synchronisiert Änderungen der Tester automatisch mit der lokalen JSON-Datei auf der Festplatte des jeweiligen Benutzers.

## Verwendung

1. Einen passenden Vektorlayer in QGIS laden.
2. Den gewünschten Layer aktiv in der Legende auswählen.
3. Das Plugin über die Benutzeroberfläche starten.
4. Den gewünschten globalen Styling-Modus festlegen.
5. Gewünschte kartografische Optionen (Schatten, Glättung etc.) anhaken.
6. Das Fenster schließen – der Stil wird lautlos und sofort auf das konfigurierte Feld angewendet.

## Verhalten bei fehlenden Werten

Wenn im Layer Werte vorkommen, für die keine explizite Regel existiert, gibt es zwei mögliche Fälle:

- Ist ein Fallback-Stil definiert, wird dieser Stil verwendet.
- Ist kein Fallback-Stil definiert, werden diese Werte im Modus 1 über einen universellen Joker-Eintrag abgefangen.

## Aktueller Stand

Dieses Plugin ist aktuell ein funktionstüchtiger MVP mit Fokus auf automatisierte, konfigurierbare und benutzergesteuerte Symbolisierung.

## Bekannte Einschränkungen

- Der Symbolaufbau ist auf die vorhandene Implementierung zugeschnitten.
- Das korrekte Anwenden der erweiterten Haken im Modus 0 und Modus 1 wird in kommenden Versionen noch strikter verzahnt.

## Geplanter Ausbau

- Vertiefte Bool-Verdrahtung für die Modi 0 und 1.
- Weitere vordefinierte Beispielkonfigurationen.

## Lizenz

Dieses Plugin steht unter der GNU General Public License v2.0 oder neuer (GPL-2.0-or-later). Die vollständige Lizenz steht in der Datei `LICENSE`.