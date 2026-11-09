#!/usr/bin/env python3
"""
Fluchtplan-Batch als Inkscape-Erweiterung
==========================================

Menü: Erweiterungen -> Flucht- und Rettungsplan ->
      "Fluchtplan: Aushangfassungen erzeugen"

Features:
- Aushangorte pro Master verwalten (Standortpunkt + lagerichtige Rotation)
- Fluchtwege zeichnen: wählbare Breite, mehrere Stützpunkte,
  grüner Verlauf mit Pfeilspitze, Speicherung im Master auf der
  Ebene "Fluchtwege"
- Batch-Export aller Fassungen als PDF per Inkscape-CLI

Installation: fluchtplan_batch.py + fluchtplan_batch.inx in den
Inkscape-Erweiterungsordner legen, Inkscape neu starten.
  Windows: C:\Users\<name>\AppData\Roaming\inkscape\extensions\
  Linux:   ~/.config/inkscape/extensions/
  macOS:   ~/Library/Application Support/org.inkscape.Inkscape/extensions/
"""

import json
import subprocess
import sys
import tkinter as tk
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

try:
    import inkex
except ImportError:
    inkex = None

SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
GRUEN = "#009639"          # Sicherheitsgrün nach ISO 3864-1
WINKEL = ("0", "90", "180", "270")
PAGE_W, PAGE_H = 420.0, 297.0  # A3 quer (mm), Fallback
WEG_ID_PREFIX = "fluchtweg-"


def seite_des_dokuments(root) -> tuple[float, float]:
    """Tatsächliche Seitengröße aus width/height bzw. viewBox lesen."""
    def mm(v):
        if not v:
            return None
        try:
            s = v.strip()
            return float(s[:-2]) if s.endswith("mm") else float(s)
        except ValueError:
            return None
    w, h = mm(root.get("width")), mm(root.get("height"))
    if not w or not h:
        vb = (root.get("viewbox") or root.get("viewBox") or "").split()
        if len(vb) == 4:
            try:
                w, h = float(vb[2]), float(vb[3])
            except ValueError:
                pass
    return (w, h) if w and h else (PAGE_W, PAGE_H)


def verschiebe_standort(root, x: float, y: float) -> None:
    """Standortpunkt + Text an Aushang-Position setzen."""
    for elem in root.iter(f"{{{SVG_NS}}}use"):
        if elem.get("id") == "standort-punkt":
            elem.set("x", f"{x - 5:.1f}")   # Symbol 10x10 mm
            elem.set("y", f"{y - 5:.1f}")
            elem.attrib.pop("transform", None)
    for elem in root.iter(f"{{{SVG_NS}}}text"):
        if elem.get("id") == "standort-text":
            elem.set("x", f"{x:.1f}")
            elem.set("y", f"{y + 16:.1f}")


def drehe_lagerichtig(tree, angle: float) -> None:
    """Gesamten Inhalt um den Seitenmittelpunkt drehen (Gruppe als Wrapper)."""
    root = tree.getroot()
    w, h = seite_des_dokuments(root)
    group = root.makeelement(f"{{{SVG_NS}}}g", {
        "id": "lagerichtig-rotation",
        "transform": f"rotate({angle:.1f} {w / 2:.1f} {h / 2:.1f})",
    })
    kinder = [c for c in root if c.tag != f"{{{SVG_NS}}}defs"]
    for k in kinder:
        root.remove(k)
        group.append(k)
    root.append(group)


def exportiere_pdf(svg_pfad: Path, pdf_pfad: Path) -> None:
    subprocess.run(
        ["inkscape", str(svg_pfad), "--export-type=pdf",
         f"--export-filename={pdf_pfad}"],
        check=True, capture_output=True)


# ------------------------------------------------- Fluchtwege im SVG
def finde_oder_lege_ebene(root, label: str):
    """Inkscape-Ebene nach inkscape:label finden (oder null zurückgeben)."""
    for g in root.iter(f"{{{SVG_NS}}}g"):
        if g.get(f"{{{INKSCAPE_NS}}}groupmode") == "layer" \
                and g.get(f"{{{INKSCAPE_NS}}}label") == label:
            return g
    return None


def weg_marker_einfuegen(defs) -> None:
    """Pfeilspitzen-Marker für Fluchtwege (id=fluchtweg-spitze)."""
    if defs is None:
        return
    for m in defs.iter(f"{{{SVG_NS}}}marker"):
        if m.get("id") == "fluchtweg-spitze":
            return
    marker = defs.makeelement(f"{{{SVG_NS}}}marker", {
        "id": "fluchtweg-spitze",
        "viewBox": "0 0 10 10",
        "refX": "8.5", "refY": "5",
        "markerWidth": "5", "markerHeight": "5",
        "orient": "auto-start-reverse",
    })
    dreieck = defs.makeelement(f"{{{SVG_NS}}}polygon",
                               {"points": "0,0 10,5 0,10", "fill": GRUEN})
    marker.append(dreieck)
    defs.append(marker)


def weg_pfad_daten(punkte: list[list[float]]) -> str:
    """Stützpunkte -> 'M x,y L x,y ...'-Pfad."""
    teile = [f"M {punkte[0][0]:.1f} {punkte[0][1]:.1f}"]
    teile += [f"L {x:.1f} {y:.1f}" for x, y in punkte[1:]]
    return " ".join(teile)


def wege_in_svg_schreiben(tree, wege: list[dict]) -> None:
    """Alle generierten Fluchtwege ersetzen (Batch-Modus)."""
    wege_in_root_schreiben(tree.getroot(), wege, ersetzen=True)


def wege_in_root_schreiben(root, wege: list[dict], ersetzen: bool = True) -> None:
    """
    Fluchtwege in Ebene "Fluchtwege" des Master-Dokuments schreiben.
    Bei ersetzen=True werden vorher alle generierten Wege (id-Prefix)
    entfernt; bei False (Anklick-Modus) wird nur angehängt.
    """
    defs = root.find(f"{{{SVG_NS}}}defs")
    weg_marker_einfuegen(defs)

    ebene = finde_oder_lege_ebene(root, "Fluchtwege")
    if ebene is None:
        raise RuntimeError(
            'Ebene "Fluchtwege" nicht gefunden – bitte die A3-Vorlage verwenden.')

    if ersetzen:
        for el in list(ebene):
            if (el.get("id") or "").startswith(WEG_ID_PREFIX):
                ebene.remove(el)

    for weg in wege:
        punkte = weg.get("punkte", [])
        if len(punkte) < 2:
            continue
        pfad = ebene.makeelement(f"{{{SVG_NS}}}path", {
            "id": f"{WEG_ID_PREFIX}{weg.get('name', 'weg').replace(' ', '-')}",
            "d": weg_pfad_daten(punkte),
            "fill": "none",
            "stroke": GRUEN,
            "stroke-width": f"{float(weg.get('breite', 4)):.1f}",
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            "marker-end": "url(#fluchtweg-spitze)",
            f"{{{INKSCAPE_NS}}}label": f"Fluchtweg {weg.get('name', '')}",
        })
        ebene.append(pfad)


# ------------------------------------------------ Auswahl -> Stützpunkte
def punkt_aus_element(el) -> tuple[float, float] | None:
    """Mittelpunkt eines Elements (mm/user units) bestimmen."""
    tag = el.tag.replace(f"{{{SVG_NS}}}", "")
    if tag == "circle" or tag == "ellipse":
        try:
            return float(el.get("cx")), float(el.get("cy"))
        except (TypeError, ValueError):
            pass
    if tag == "rect":
        try:
            x, y = float(el.get("x", 0)), float(el.get("y", 0))
            w = float(el.get("width", 0)) or float(el.get("rx", 0)) * 2
            h = float(el.get("height", 0)) or float(el.get("ry", 0)) * 2
            return x + w / 2, y + h / 2
        except (TypeError, ValueError):
            pass
    try:
        bb = el.bounding_box()
        return float(bb.center.x), float(bb.center.y)
    except Exception:
        return None


def stuetzpunkte_aus_auswahl(auswahl) -> list[list[float]]:
    """Ausgewählte Elemente -> Stützpunkte (in Auswahl-Reihenfolge)."""
    punkte = []
    for el in auswahl:
        p = punkt_aus_element(el)
        if p:
            punkte.append([round(p[0], 2), round(p[1], 2)])
    return punkte


# ------------------------------------------------------------------ Dialog
class WegDialog(tk.Toplevel):
    """Einzelnen Fluchtweg bearbeiten: Breite + Stützpunkte."""

    def __init__(self, master_tk, weg: dict) -> None:
        super().__init__(master_tk)
        self.title(f"Fluchtweg: {weg.get('name', 'neu')}")
        self.weg = weg
        self.ok = False

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="Name:").pack(side="left")
        self.name_var = tk.StringVar(value=weg.get("name", "Weg 1"))
        ttk.Entry(top, textvariable=self.name_var, width=18).pack(side="left", padx=6)
        ttk.Label(top, text="Breite (mm):").pack(side="left", padx=(12, 0))
        self.breite_var = tk.StringVar(value=str(weg.get("breite", 4)))
        ttk.Spinbox(top, textvariable=self.breite_var, from_=1.0, to=20.0,
                    increment=0.5, width=6).pack(side="left", padx=6)

        ttk.Label(self, text="Stützpunkte (x/y in mm, Reihenfolge = Wegverlauf)"
                  ).pack(padx=8, anchor="w")
        self.tree = ttk.Treeview(self, columns=("x", "y"), show="headings")
        self.tree.heading("x", text="x (mm)")
        self.tree.heading("y", text="y (mm)")
        self.tree.column("x", width=100)
        self.tree.column("y", width=100)
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)
        self.tree.bind("<Double-1>", self._edit_punkt)
        for x, y in weg.get("punkte", []):
            self.tree.insert("", "end", values=(x, y))

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="Stützpunkt hinzufügen",
                   command=self._add_punkt).pack(side="left")
        ttk.Button(bar, text="Stützpunkt entfernen",
                   command=self._del_punkt).pack(side="left", padx=6)
        ttk.Button(bar, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Übernehmen", command=self._fertig).pack(
            side="right", padx=6)

    def _punkte(self) -> list[list[float]]:
        return [list(map(float, self.tree.item(i)["values"]))
                for i in self.tree.get_children()]

    def _add_punkt(self) -> None:
        self.tree.insert("", "end", values=(100, 100))

    def _del_punkt(self) -> None:
        sel = self.tree.selection()
        if sel:
            self.tree.delete(sel[0])

    def _edit_punkt(self, event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        col = self.tree.identify_column(event.x)
        if col not in ("#1", "#2"):
            return
        feld = "x (mm)" if col == "#1" else "y (mm)"
        wert = self.tree.set(sel[0], col)
        neu = simpledialog.askstring("Stützpunkt", f"{feld}:", initialvalue=wert,
                                     parent=self)
        if neu is None:
            return
        try:
            self.tree.set(sel[0], col, float(neu))
        except ValueError:
            messagebox.showwarning("Ungültig", "Bitte Zahl eingeben.", parent=self)

    def _fertig(self) -> None:
        punkte = self._punkte()
        if len(punkte) < 2:
            messagebox.showwarning("Zu wenig", "Mindestens 2 Stützpunkte nötig.",
                                   parent=self)
            return
        try:
            breite = float(self.breite_var.get())
        except ValueError:
            messagebox.showwarning("Breite", "Breite in mm als Zahl.", parent=self)
            return
        self.weg.update({"name": self.name_var.get().strip() or "Weg",
                         "breite": breite, "punkte": punkte})
        self.ok = True
        self.destroy()


class StandortDialog(tk.Toplevel):
    """Hauptdialog: Tab "Aushangorte" + Tab "Fluchtwege"."""

    def __init__(self, master_tk, config: dict) -> None:
        super().__init__(master_tk)
        self.title("Fluchtplan-Batch – Aushangfassungen & Fluchtwege")
        self.geometry("700x520")
        self.config = config
        self.orte: list[dict] = config.setdefault("orte", [])
        self.wege: list[dict] = config.setdefault("wege", [])
        self.ok = False

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        tab1 = ttk.Frame(nb)
        nb.add(tab1, text="Aushangorte")
        bar1 = ttk.Frame(tab1)
        bar1.pack(fill="x", padx=6, pady=4)
        ttk.Button(bar1, text="Ort hinzufügen", command=self._add_ort).pack(side="left")
        ttk.Button(bar1, text="Ort entfernen", command=self._del_ort).pack(side="left", padx=6)
        self.tree_orte = ttk.Treeview(tab1, columns=("name", "x", "y", "winkel"),
                                      show="headings")
        for col, text, w in (("name", "Name", 220), ("x", "x (mm)", 90),
                             ("y", "y (mm)", 90), ("winkel", "Winkel (°)", 100)):
            self.tree_orte.heading(col, text=text)
            self.tree_orte.column(col, width=w)
        self.tree_orte.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.tree_orte.bind("<Double-1>", self._edit_ort)
        self._refresh_orte()

        tab2 = ttk.Frame(nb)
        nb.add(tab2, text="Fluchtwege")
        bar2 = ttk.Frame(tab2)
        bar2.pack(fill="x", padx=6, pady=4)
        ttk.Button(bar2, text="Weg hinzufügen", command=self._add_weg).pack(side="left")
        ttk.Button(bar2, text="Weg bearbeiten", command=self._edit_weg).pack(side="left", padx=6)
        ttk.Button(bar2, text="Weg entfernen", command=self._del_weg).pack(side="left")
        self.tree_wege = ttk.Treeview(tab2, columns=("name", "breite", "punkte"),
                                      show="headings")
        self.tree_wege.heading("name", text="Name")
        self.tree_wege.heading("breite", text="Breite (mm)")
        self.tree_wege.heading("punkte", text="Stützpunkte")
        self.tree_wege.column("name", width=180)
        self.tree_wege.column("breite", width=100)
        self.tree_wege.column("punkte", width=280)
        self.tree_wege.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.tree_wege.bind("<Double-1>", lambda e: self._edit_weg())
        self._refresh_wege()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=8)
        ttk.Button(bar, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(bar, text="Übernehmen & PDFs erzeugen",
                   command=self._fertig).pack(side="right", padx=6)

    def _refresh_orte(self) -> None:
        self.tree_orte.delete(*self.tree_orte.get_children())
        for o in self.orte:
            self.tree_orte.insert("", "end", values=(
                o.get("name", ""), o.get("x", ""), o.get("y", ""),
                str(o.get("winkel", 0))))

    def _add_ort(self) -> None:
        name = simpledialog.askstring("Neuer Aushangort",
                                      "Bezeichnung (z. B. EG-Flur-Nord):",
                                      parent=self)
        if name:
            self.orte.append({"name": name, "x": 100, "y": 100, "winkel": 0})
            self._refresh_orte()

    def _del_ort(self) -> None:
        sel = self.tree_orte.selection()
        if sel:
            del self.orte[self.tree_orte.index(sel[0])]
            self._refresh_orte()

    def _edit_ort(self, event) -> None:
        sel = self.tree_orte.selection()
        if not sel:
            return
        col = self.tree_orte.identify_column(event.x)
        if col not in ("#1", "#2", "#3", "#4"):
            return
        idx_spalte = int(col.replace("#", "")) - 1
        feld = ("name", "x", "y", "winkel")[idx_spalte]
        wert = self.tree_orte.set(sel[0], col)
        neu = simpledialog.askstring("Bearbeiten", f"{feld}:", initialvalue=wert,
                                     parent=self)
        if neu is None:
            return
        ort = self.orte[self.tree_orte.index(sel[0])]
        try:
            if feld == "name":
                ort["name"] = neu.strip()
            elif feld in ("x", "y"):
                ort[feld] = float(neu)
            else:
                w = int(neu)
                if w not in (0, 90, 180, 270):
                    raise ValueError
                ort["winkel"] = w
        except ValueError:
            messagebox.showwarning("Ungültig",
                                   "Zahl bzw. Winkel 0/90/180/270 erwartet.",
                                   parent=self)
            return
        self._refresh_orte()

    def _refresh_wege(self) -> None:
        self.tree_wege.delete(*self.tree_wege.get_children())
        for w in self.wege:
            pts = " -> ".join(f"({x:.0f}/{y:.0f})"
                              for x, y in w.get("punkte", []))
            self.tree_wege.insert("", "end", values=(
                w.get("name", ""), w.get("breite", 4), pts))

    def _add_weg(self) -> None:
        weg = {"name": f"Weg {len(self.wege) + 1}", "breite": 4,
               "punkte": [[100, 100], [200, 100]]}
        dlg = WegDialog(self, weg)
        dlg.transient(self)
        dlg.grab_set()
        self.wait_window(dlg)
        if dlg.ok:
            self.wege.append(dlg.weg)
            self._refresh_wege()

    def _edit_weg(self) -> None:
        sel = self.tree_wege.selection()
        if not sel:
            return
        idx = self.tree_wege.index(sel[0])
        dlg = WegDialog(self, self.wege[idx])
        dlg.transient(self)
        dlg.grab_set()
        self.wait_window(dlg)
        self._refresh_wege()

    def _del_weg(self) -> None:
        sel = self.tree_wege.selection()
        if sel:
            del self.wege[self.tree_wege.index(sel[0])]
            self._refresh_wege()

    def _fertig(self) -> None:
        self.ok = True
        self.destroy()


# ------------------------------------------------------- Verarbeitung
def lade_config(sidecar: Path) -> dict:
    """Sidecar laden (abwärtskompatibel mit alter, reiner Ortliste)."""
    if sidecar.exists():
        daten = json.loads(sidecar.read_text(encoding="utf-8"))
        if isinstance(daten, list):
            return {"orte": daten, "wege": []}
        daten.setdefault("orte", [])
        daten.setdefault("wege", [])
        return daten
    return {"orte": [], "wege": []}


def resolve_path(base_dir: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    return candidate


def exportiere_fassungen_fuer_master(svg_pfad: Path, orte: list[dict], output_root: Path) -> list[Path]:
    import xml.etree.ElementTree as ET
    output_root.mkdir(parents=True, exist_ok=True)
    base_tree = ET.parse(svg_pfad)
    erzeugt: list[Path] = []
    for ort in orte:
        tree = deepcopy(base_tree)
        root = tree.getroot()
        verschiebe_standort(root, float(ort["x"]), float(ort["y"]))
        drehe_lagerichtig(tree, float(ort.get("winkel", 0)))
        master_out_dir = output_root / svg_pfad.stem
        master_out_dir.mkdir(parents=True, exist_ok=True)
        tmp = master_out_dir / f"{svg_pfad.stem}_{ort['name']}.svg"
        tree.write(tmp, encoding="unicode", xml_declaration=True)
        pdf = tmp.with_suffix(".pdf")
        try:
            exportiere_pdf(tmp, pdf)
            erzeugt.append(pdf)
        except subprocess.CalledProcessError as e:
            print(f"!! Export fehlgeschlagen für {ort['name']}: {e}", file=sys.stderr)
    return erzeugt


def verarbeite_json(config_pfad: Path) -> list[Path]:
    config = json.loads(config_pfad.read_text(encoding="utf-8"))
    workdir = Path(config.get("workdir", "output"))
    if not workdir.is_absolute():
        workdir = (config_pfad.parent / workdir).resolve()

    master_cfg = config.get("master") or {}
    standorte_cfg = config.get("standorte") or {}
    erzeugt: list[Path] = []

    if not master_cfg:
        raise ValueError("Keine master-Dateien in der Konfiguration gefunden.")

    for name, master_rel in master_cfg.items():
        svg_pfad = resolve_path(config_pfad.parent, master_rel)
        if not svg_pfad.exists():
            print(f"!! Master-Datei fehlt: {svg_pfad}", file=sys.stderr)
            continue
        orte = standorte_cfg.get(name, [])
        if not orte:
            print(f"!! Keine Standorte für Geschoss {name}", file=sys.stderr)
            continue
        erzeugt.extend(exportiere_fassungen_fuer_master(svg_pfad, orte, workdir))

    return erzeugt


def verarbeite(svg_pfad: Path) -> list[Path]:
    """Dialog öffnen, Wege in Master schreiben, Fassungen exportieren."""
    import xml.etree.ElementTree as ET

    sidecar = svg_pfad.with_name(svg_pfad.name + ".standorte.json")
    config = lade_config(sidecar)

    root_tk = tk.Tk()
    root_tk.withdraw()
    dlg = StandortDialog(root_tk, config)
    dlg.transient(root_tk)
    dlg.grab_set()
    root_tk.wait_window(dlg)

    if not dlg.ok:
        root_tk.destroy()
        return []

    sidecar.write_text(json.dumps(dlg.config, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)

    master_tree = ET.parse(svg_pfad)
    wege_in_svg_schreiben(master_tree, dlg.wege)
    master_tree.write(svg_pfad, encoding="unicode", xml_declaration=True)

    out_dir = svg_pfad.parent / "Aushangfassungen"
    out_dir.mkdir(exist_ok=True)
    base_tree = ET.parse(svg_pfad)

    erzeugt: list[Path] = []
    for ort in dlg.orte:
        tree = deepcopy(base_tree)
        root = tree.getroot()
        verschiebe_standort(root, float(ort["x"]), float(ort["y"]))
        drehe_lagerichtig(tree, float(ort.get("winkel", 0)))
        tmp = out_dir / f"{svg_pfad.stem}_{ort['name']}.svg"
        tree.write(tmp, encoding="unicode", xml_declaration=True)
        pdf = tmp.with_suffix(".pdf")
        try:
            exportiere_pdf(tmp, pdf)
            erzeugt.append(pdf)
        except subprocess.CalledProcessError as e:
            print(f"!! Export fehlgeschlagen für {ort['name']}: {e}",
                  file=sys.stderr)

    root_tk.destroy()
    return erzeugt


def main_offline() -> int:
    """Ohne Inkscape starten (Test): Datei als Argument."""
    if len(sys.argv) < 2:
        print("Nutzung:\n  python fluchtplan_batch.py master.svg\n  python fluchtplan_batch.py standorte.json")
        return 2

    target = Path(sys.argv[1])
    if target.suffix.lower() == ".json":
        try:
            erzeugt = verarbeite_json(target)
            print(f"{len(erzeugt)} PDFs erzeugt.")
            return 0
        except Exception as exc:
            print(f"Fehler: {exc}", file=sys.stderr)
            return 1

    verarbeite(target)
    return 0


if inkex is not None:
    class FluchtplanErweiterung(inkex.Effect):
        """
        Ein Einstiegspunkt für zwei Menübefehle (gesteuert über den
        versteckten inx-Parameter "modus"):
          - batch  : Hauptdialog (Aushangorte + Fluchtwege) + PDF-Export
          - auswahl: Fluchtweg aus aktuell ausgewählten Punkten zeichnen
        """

        def _auswahl_workflow(self) -> None:
            auswahl = list(self.svg.selection)
            punkte = stuetzpunkte_aus_auswahl(auswahl)
            if len(punkte) < 2:
                inkex.utils.errormsg(
                    "Bitte mindestens 2 Punkte/Objekte auswählen.\n\n"
                    "Tipp: Einzelne kleine Kreise als Stützpunkt-Marker "
                    "setzen, in Wegreihenfolge auswählen und den Befehl "
                    "erneut starten. Die Reihenfolge entspricht der "
                    "Stacking-Reihenfolge (oben = zuerst).")
                return

            weg = {"name": f"Weg {len(punkte)}", "breite": 4, "punkte": punkte}
            root_tk = tk.Tk()
            root_tk.withdraw()
            dlg = WegDialog(root_tk, weg)
            dlg.transient(root_tk)
            dlg.grab_set()
            root_tk.wait_window(dlg)
            if not dlg.ok:
                root_tk.destroy()
                return

            try:
                sidecar = Path(self.svg_path).with_name(
                    Path(self.svg_path).name + ".standorte.json")
                config = lade_config(sidecar)
            except Exception:
                sidecar, config = None, {"orte": [], "wege": []}
            config.setdefault("wege", []).append(dlg.weg)
            if sidecar:
                sidecar.write_text(
                    json.dumps(config, indent=2, ensure_ascii=False),
                    encoding="utf-8")

            wege_in_root_schreiben(self.svg, [dlg.weg], ersetzen=False)
            root_tk.destroy()
            inkex.utils.errormsg(
                f'Fluchtweg "{dlg.weg["name"]}" mit {len(punkte)} '
                f"Stützpunkten eingefügt (Ebene „Fluchtwege“).\n"
                "Die ausgewählten Marker-Objekte kannst du jetzt löschen.")

        def _batch_workflow(self) -> None:
            try:
                svg_pfad = Path(self.svg_path)
            except Exception:
                svg_pfad = Path(sys.argv[-1])
            pdfs = verarbeite(svg_pfad)
            inkex.utils.errormsg(
                f"{len(pdfs)} Aushangfassungen erzeugt unter: "
                f"{svg_pfad.parent / 'Aushangfassungen'}\n"
                f"Fluchtwege im Master gespeichert.")

        def effect(self) -> None:
            modus = getattr(self.options, "modus", "batch")
            if modus == "auswahl":
                self._auswahl_workflow()
            else:
                self._batch_workflow()

        def save(self, *args, **kwargs):
            """Ausgaben erfolgen als separate Dateien bzw. direkt im Dokument."""
            pass

    if __name__ == "__main__":
        FluchtplanErweiterung().run()
else:
    if __name__ == "__main__":
        sys.exit(main_offline())
