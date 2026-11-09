#!/usr/bin/env python3
"""
Fluchtplan-GUI (tkinter)
========================

Grafische Oberfläche für fluchtplan_batch.py:
- Geschosse/Master-Dateien verwalten (hinzufügen, entfernen)
- Aushangorte pro Geschoss in einer Tabelle pflegen
  (Name, x, y in mm, Drehwinkel 0/90/180/270)
- Konfiguration als standorte.json speichern/laden
- Batch mit einem Klick starten, Live-Ausgabe im Log-Fenster

Nur Standardbibliothek (tkinter) – kein pip-Install nötig.
Start:  python fluchtplan_gui.py
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

WINKEL = ["0", "90", "180", "270"]
SPALTEN = ("name", "x", "y", "winkel")


class BatchLogReader(threading.Thread):
    """Liest stdout des Batch-Prozesses und stellt Zeilen in eine Queue."""

    def __init__(self, proc: subprocess.Popen, q: "queue.Queue[str]") -> None:
        super().__init__(daemon=True)
        self.proc = proc
        self.q = q

    def run(self) -> None:
        for line in self.proc.stdout or []:
            self.q.put(line.rstrip())
        self.q.put(f"__ENDE__ rc={self.proc.wait()}")


class FluchtplanGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Fluchtplan-Batch – Aushangfassungen verwalten")
        self.root.geometry("980x640")

        self.config: dict = {"workdir": "output", "master": {}, "standorte": {}}
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.batch_proc: subprocess.Popen | None = None

        self._build_ui()
        self._poll_log()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # Kopfzeile: Master-Dateien
        top = ttk.LabelFrame(self.root, text="Geschosse & Master-SVGs")
        top.pack(fill="x", padx=8, pady=6)
        self.master_tree = ttk.Treeview(top, columns=("geschoss", "datei"),
                                        show="headings", height=4)
        self.master_tree.heading("geschoss", text="Geschoss")
        self.master_tree.heading("datei", text="Master-SVG")
        self.master_tree.column("geschoss", width=100)
        self.master_tree.column("datei", width=520)
        self.master_tree.pack(side="left", padx=6, pady=6, fill="x", expand=True)
        btns = ttk.Frame(top)
        btns.pack(side="right", fill="y", padx=6, pady=6)
        ttk.Button(btns, text="Geschoss + Master…",
                   command=self.add_geschoss).pack(fill="x", pady=2)
        ttk.Button(btns, text="Master ändern…",
                   command=self.change_master).pack(fill="x", pady=2)
        ttk.Button(btns, text="Geschoss entfernen",
                   command=self.remove_geschoss).pack(fill="x", pady=2)

        # Mitte: Standorttabelle des gewählten Geschosses
        mid = ttk.LabelFrame(self.root, text="Aushangorte (x/y in mm, Drehwinkel)")
        mid.pack(fill="both", expand=True, padx=8, pady=6)
        bar = ttk.Frame(mid)
        bar.pack(fill="x", padx=6, pady=4)
        ttk.Label(bar, text="Geschoss:").pack(side="left")
        self.geschoss_var = tk.StringVar()
        self.geschoss_combo = ttk.Combobox(bar, textvariable=self.geschoss_var,
                                           state="readonly", width=12)
        self.geschoss_combo.pack(side="left", padx=6)
        self.geschoss_combo.bind("<<ComboboxSelected>>", self.load_orte)
        ttk.Button(bar, text="Ort hinzufügen",
                   command=self.add_ort).pack(side="left", padx=4)
        ttk.Button(bar, text="Ort entfernen",
                   command=self.remove_ort).pack(side="left", padx=4)

        self.ort_tree = ttk.Treeview(mid, columns=SPALTEN, show="headings")
        for col, w in zip(SPALTEN, (200, 90, 90, 100)):
            self.ort_tree.heading(col, text={"name": "Name", "x": "x (mm)",
                                            "y": "y (mm)", "winkel": "Winkel (°)"}[col])
            self.ort_tree.column(col, width=w)
        self.ort_tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Live-Edit der ausgewählten Zelle
        self.ort_tree.bind("<Double-1>", self._edit_zelle)
        self.ort_tree.bind("<Return>", self._edit_zelle)

        # Fuß: Aktionen + Log
        bottom = ttk.LabelFrame(self.root, text="Batch & Log")
        bottom.pack(fill="both", padx=8, pady=6)
        abar = ttk.Frame(bottom)
        abar.pack(fill="x", padx=6, pady=4)
        ttk.Button(abar, text="JSON öffnen…", command=self.load_json).pack(side="left")
        ttk.Button(abar, text="JSON speichern", command=self.save_json).pack(side="left", padx=4)
        ttk.Button(abar, text="Master prüfen", command=self.check_masters).pack(side="left", padx=4)
        ttk.Button(abar, text="▶ Batch starten", command=self.run_batch).pack(side="right")
        self.status = ttk.Label(abar, text="bereit")
        self.status.pack(side="right", padx=8)

        self.log = tk.Text(bottom, height=8, state="disabled",
                           font=("Courier", 9), background="#111", foreground="#9f9")
        self.log.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    # ------------------------------------------------------- Geschosse
    def add_geschoss(self) -> None:
        from tkinter import simpledialog
        name = simpledialog.askstring("Geschoss", "Bezeichnung (z. B. EG, OG1):")
        if not name:
            return
        datei = filedialog.askopenfilename(
            title=f"Master-SVG für {name} wählen",
            filetypes=[("Inkscape SVG", "*.svg"), ("Alle Dateien", "*.*")])
        if not datei:
            return
        self.config["master"][name] = datei
        self.config["standorte"].setdefault(name, [])
        self._refresh_geschosse()
        self.geschoss_var.set(name)
        self.load_orte()

    def change_master(self) -> None:
        sel = self.master_tree.selection()
        if not sel:
            return
        geschoss = self.master_tree.item(sel[0])["values"][0]
        datei = filedialog.askopenfilename(filetypes=[("Inkscape SVG", "*.svg")])
        if datei:
            self.config["master"][geschoss] = datei
            self._refresh_geschosse()

    def remove_geschoss(self) -> None:
        sel = self.master_tree.selection()
        if not sel:
            return
        geschoss = self.master_tree.item(sel[0])["values"][0]
        self.config["master"].pop(geschoss, None)
        self.config["standorte"].pop(geschoss, None)
        self._refresh_geschosse()

    def _refresh_geschosse(self) -> None:
        self.master_tree.delete(*self.master_tree.get_children())
        for g, d in self.config["master"].items():
            self.master_tree.insert("", "end", values=(g, d))
        self.geschoss_combo["values"] = list(self.config["master"])
        self.load_orte()

    # ------------------------------------------------------------- Orte
    def load_orte(self, *_):
        self.ort_tree.delete(*self.ort_tree.get_children())
        g = self.geschoss_var.get()
        for ort in self.config["standorte"].get(g, []):
            self.ort_tree.insert("", "end", values=(
                ort.get("name", ""), ort.get("x", ""), ort.get("y", ""),
                str(ort.get("winkel", 0))))

    def add_ort(self) -> None:
        g = self.geschoss_var.get()
        if not g:
            messagebox.showinfo("Hinweis", "Erst ein Geschoss mit Master anlegen.")
            return
        self.config["standorte"].setdefault(g, []).append(
            {"name": "NEU", "x": 100, "y": 100, "winkel": 0})
        self.load_orte()

    def remove_ort(self) -> None:
        g = self.geschoss_var.get()
        sel = self.ort_tree.selection()
        if not sel:
            return
        idx = self.ort_tree.index(sel[0])
        del self.config["standorte"][g][idx]
        self.load_orte()

    def _edit_zelle(self, event):
        """Doppelklick auf Zelle -> Inline-Eingabefeld."""
        sel = self.ort_tree.selection()
        if not sel:
            return
        col = self.ort_tree.identify_column(event.x)
        row = self.ort_tree.identify_row(event.y)
        if col not in ("#1", "#2", "#3", "#4"):
            return
        item = self.ort_tree.item(sel[0])
        values = list(item["values"])
        spalten_idx = int(col.replace("#", "")) - 1

        bbox = self.ort_tree.bbox(sel[0], col)
        if not bbox:
            return
        entry = ttk.Entry(self.ort_tree)
        entry.insert(0, str(values[spalten_idx]))
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.focus_set()

        def commit(_e=None):
            neu = entry.get().strip()
            entry.destroy()
            g = self.geschoss_var.get()
            idx = self.ort_tree.index(sel[0])
            ort = self.config["standorte"][g][idx]
            feld = SPALTEN[spalten_idx]
            if feld == "name":
                ort["name"] = neu
            else:
                try:
                    wert = float(neu) if feld in ("x", "y") else int(neu)
                    if feld == "winkel" and wert not in (0, 90, 180, 270):
                        messagebox.showwarning("Winkel", "Nur 0, 90, 180, 270 erlaubt.")
                        return
                    ort[feld] = wert
                except ValueError:
                    messagebox.showwarning("Ungültig", "Bitte Zahl eingeben.")
                    return
            self.load_orte()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda _e: entry.destroy())

    # ------------------------------------------------------- JSON / Batch
    def load_json(self) -> None:
        datei = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not datei:
            return
        self.config = json.loads(Path(datei).read_text(encoding="utf-8"))
        self.config.setdefault("master", {})
        self.config.setdefault("standorte", {})
        self._refresh_geschosse()
        if self.config["master"]:
            self.geschoss_var.set(next(iter(self.config["master"])))
            self.load_orte()

    def save_json(self) -> None:
        datei = filedialog.asksaveasfilename(defaultextension=".json",
                                            initialfile="standorte.json",
                                            filetypes=[("JSON", "*.json")])
        if not datei:
            return
        Path(datei).write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8")
        self.status.config(text=f"gespeichert: {datei}")

    def check_masters(self) -> None:
        fehlen = [g for g, d in self.config["master"].items() if not Path(d).exists()]
        orte = sum(len(v) for v in self.config["standorte"].values())
        msg = (f"{len(self.config['master'])} Master, {orte} Aushangorte. "
               + (f"Fehlende Master: {', '.join(fehlen)}" if fehlen
                  else "Alle Master-Dateien gefunden."))
        messagebox.showinfo("Prüfung", msg)

    def run_batch(self) -> None:
        if self.batch_proc and self.batch_proc.poll() is None:
            messagebox.showinfo("Läuft", "Batch läuft bereits.")
            return
        if not self.config["master"]:
            messagebox.showwarning("Leer", "Keine Geschosse/Master konfiguriert.")
            return
        datei = Path("standorte.json")
        datei.write_text(json.dumps(self.config, indent=2, ensure_ascii=False),
                         encoding="utf-8")
        skript = Path(__file__).with_name("fluchtplan_batch.py")
        if not skript.exists():
            messagebox.showerror("Fehler", f"fluchtplan_batch.py nicht gefunden:\n{skript}")
            return
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")
        self.status.config(text="Batch läuft…")
        self.batch_proc = subprocess.Popen(
            [sys.executable, str(skript), str(datei)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=str(Path(__file__).parent))
        BatchLogReader(self.batch_proc, self.log_queue).start()

    def _poll_log(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log.config(state="normal")
                if line.startswith("__ENDE__"):
                    rc = line.split("rc=")[-1]
                    self.status.config(
                        text=f"beendet (Code {rc})" + (" – ✔ Erfolg" if rc == "0" else " – ⚠ Fehler"))
                else:
                    self.log.insert("end", line + "\n")
                self.log.see("end")
                self.log.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(200, self._poll_log)


def main() -> None:
    root = tk.Tk()
    FluchtplanGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
