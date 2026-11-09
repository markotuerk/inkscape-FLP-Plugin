# Flucht- und Rettungsplan-Toolkit – Projektübergabe

Dieses Dokument beschreibt das vollständige Projekt für die Weiterarbeit mit
GitHub Copilot. Es enthält Kontext, Architektur, Dateistruktur und offene
Aufgaben. Die Quelldateien liegen als Canvases vor und müssen in ein
Git-Repository übertragen werden.

## 1. Projektziel

Werkzeugkette zur Erstellung normgerechter Flucht- und Rettungspläne nach
DIN ISO 23601 (unterstützt durch ASR A1.3, ASR A2.3, ArbStättV §4 Abs. 4):

- **Master je Geschoss:** A3-Vorlage (420 × 297 mm, quer) als Inkscape-SVG mit
  Ebenenstruktur (`Kopf`, `Grundriss`, `Fluchtwege`, `Symbole`, `Legende`,
  `Verhalten im Gefahrenfall`, `Übersichtsplan`, `Fußzeile`)
- **Batch-Erzeugung:** je Aushangort eine lagerichtig gedrehte Fassung mit
  versetztem Standortpunkt („Sie sind hier"), exportiert als PDF
- **Fluchtweg-Zeichnung:** Wege mit wählbarer Breite über mehrere
  Stützpunkte, Sicherheitsgrün #009639 (ISO 3864-1), Pfeilspitze am Ende

Zielvolumen: 4 Gebäudegeschosse × 4 Aushangorte = **16 Pläne** aus nur
4 Master-Dateien.

## 2. Repository-Struktur (vorgeschlagen)

```text
fluchtplan-toolkit/
├── README.md                    # diese Struktur ausrollen
├── template/
│   └── fluchtplan_vorlage_A3.svg    # A3-Grundvorlage (Canvas: „A3-Vorlage“)
├── master/                      # pro Geschoss ein gefüllter Master
│   ├── EG.svg
│   ├── OG1.svg
│   ├── OG2.svg
│   └── OG3.svg
├── plugin/                      # Inkscape-Erweiterung
│   ├── fluchtplan_batch.py      # Kernlogik (Canvas: „Inkscape-Erweiterung“)
│   ├── fluchtplan_batch.inx     # Menü: Aushangfassungen erzeugen
│   └── fluchtweg_auswahl.inx    # Menü: Fluchtweg aus Auswahl zeichnen
├── gui/
│   └── fluchtplan_gui.py        # Standalone-tkinter-GUI (Canvas: „GUI“)
├── config/
│   └── standorte.json           # Beispielkonfiguration 16 Orte
└── output/                      # generierte Aushangfassungen (gitignore)
```

## 3. Kernkomponenten

### 3.1 SVG-Vorlage (Master)

- Maße: 420 mm × 297 mm, viewBox `0 0 420 297`, Einheiten = mm
- Pflicht-IDs für die Automatisierung:
  - `standort-punkt` – `<use href="#sym-location">`, Standort des Betrachters
  - `standort-text` – zugehöriger Text „Sie sind hier"
  - Ebene `Fluchtwege` – `inkscape:groupmode="layer"` + `inkscape:label`
- Symbole in `<defs>` (IDs): `sym-exit`, `sym-extinguisher`, `sym-firstaid`,
  `sym-alarm`, `sym-assembly`, `sym-location`, `sym-escape-arrow`
  (vereinfachte ISO-7010-Nachbauten; für Produktivpläne offizielle
  ISO-7010-SVGs einsetzen)

### 3.2 Inkscape-Erweiterung `plugin/fluchtplan_batch.py`

- Menü: *Erweiterungen → Flucht- und Rettungsplan*
- Zwei Modi (Umschaltung über versteckten inx-Parameter `modus`):
  - `batch`: Hauptdialog mit Tabs „Aushangorte" (Name, x, y, Winkel 0/90/180/270)
    und „Fluchtwege" (Name, Breite mm, Stützpunkte) → erzeugt Fassungen und
    exportiert PDFs per Inkscape-CLI nach `Aushangfassungen/`
  - `auswahl`: ausgewählte Marker-Objekte im Dokument werden als Stützpunkte
    übernommen (Mittelpunkt von circle/rect, sonst Bounding-Box), Weg wird
    direkt ins offene Dokument auf Ebene „Fluchtwege" gezeichnet
- Konfiguration pro Master: Sidecar `<master>.svg.standorte.json`
  mit `{"orte": [...], "wege": [...]}` (rückwärtskompatibel zu reinen Listen)
- Erzeugte Wege: ID-Präfix `fluchtweg-`, Marker `fluchtweg-spitze`
- Batch-Modus ersetzt nur generierte Wege (Präfix), manuelle bleiben erhalten
- Rotation: gesamter Inhalt wird in eine Gruppe `lagerichtig-rotation` um den
  Seitenmittelpunkt gedreht; Standortpunkt wird vorher versetzt

### 3.3 Standalone-GUI `gui/fluchtplan_gui.py`

- tkinter, nur Standardbibliothek; ruft `fluchtplan_batch.py` als Subprozess auf
- Verwaltung von Geschossen/Mastern, Standorttabelle mit Inline-Edit,
  JSON laden/speichern, Master-Existenzprüfung, Live-Log des Batchlaufs

### 3.4 Konfiguration `config/standorte.json`

```json
{
  "workdir": "output",
  "master": { "EG": "master/EG.svg", "OG1": "master/OG1.svg" },
  "standorte": {
    "EG": [
      { "name": "EG-Foyer", "x": 200, "y": 80, "winkel": 90 }
    ]
  }
}
```

## 4. Offene Aufgaben (geeignet für Copilot-Issues)

1. **Plugin-Batch mit Standalone-GUI vereinheitlichen:** Die tkinter-GUI ruft
   noch die alte rein CLI-basierte `fluchtplan_batch.py`-Variante auf. Sie
   sollte auf das Plugin-Modul (Import von `verarbeite`/Dialogen) umgestellt
   oder auf die Inkscape-Erweiterung verweisen.
2. **ISO-7010-Symbole ersetzen:** Offizielle SVG-Versionen der Sicherheitszeichen
   einbinden (lizenzrechtlich prüfen, Quellen dokumentieren).
3. **Tests:** pytest für `wege_in_root_schreiben`,
   `stuetzpunkte_aus_auswahl`, `lade_config` (Backward-Kompatibilität),
   Roundtrip SVG lesen/schreiben.
4. **Koordinaten-Validierung:** Stützpunkte/Standorte auf Planbereich
   (10…310 × 28…287 mm) prüfen, Warnung bei außerhalb liegenden Punkten.
5. **Smoothing-Option:** optional kurvig geglättete Wegverläufe
   (Catmull-Rom → Bezier) statt gerader Segmente, per Konfigurationsschalter.
6. **CI:** GitHub Actions mit `inkscape` im Container (vgl.
   Docker-Ansatz für inkmcp), Export aller Beispielfassungen als Artefakt.
7. **Dokumentation:** README mit Screenshots, Norm-Kurzreferenz
   (Mindestgrößen: Zeichen ≥ 7 mm, Schrift ≥ 2 mm, Überschrift ≈ 7 % der
   kürzeren Blattseite, Außenwand 1,6 mm / Innenwand 0,6 mm Strichstärke).

## 5. Copilot-Prompt (Einstieg)

> Lies `README.md`, `plugin/fluchtplan_batch.py` und
> `template/fluchtplan_vorlage_A3.svg`. Das Projekt erzeugt
> Flucht- und Rettungspläne nach DIN ISO 23601 aus Inkscape-Mastern.
> Beginne mit Issue „Plugin-Batch mit Standalone-GUI vereinheitlichen:
> Die GUI in `gui/fluchtplan_gui.py` soll das Plugin-Modul importieren
> (statt Subprocess auf eine alte Skriptversion) und die Tabs
> „Aushangorte" + „Fluchtwege" der Plugin-Dialoge wiederverwenden.
> Achte auf die Pflicht-IDs (`standort-punkt`, `standort-text`) und das
> Sidecar-Format (`orte` + `wege`).

## 6. Rechtliche Hinweise

- Normen (DIN ISO 23601, ASR) sind urheberrechtlich geschützt; nur die
  Anforderungen umsetzen, keine Normtexte kopieren.
- Pläne müssen von fachkundiger Person geprüft und nach ASR A2.3 aktuell
  gehalten werden; Aushang lagerichtig, mindestens 50 lx beleuchtet.
