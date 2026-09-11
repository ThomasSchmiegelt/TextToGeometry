# SPDX-License-Identifier: LGPL-2.1-or-later
"""Command + dialog for TextToGeometry (extended with variant tables and targets).

Variant sources: free text (one variant), CSV file, XLSX file,
FreeCAD Spreadsheet object, or pasted table text.

Targets (optional): mass in g, volume in mm^3, dimension x/y/z in mm
(each with  ==  /  <=  /  >=  and tolerance) or a free-text criterion
handed to the LLM.

Sweep: for every table row the LLM generates code, we measure the shape
(volume/mass/bbox) and check the targets. On a miss the measurement plus
the failure reasons are fed back into the next prompt, up to N iterations.
A Stop button interrupts the sweep between iterations.
"""

from __future__ import annotations

import os

import FreeCAD
import FreeCADGui
from PySide6 import QtCore
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

import T2GCore
import T2GSkills


# ---------------------------------------------------------------------------
# Material density presets
# ---------------------------------------------------------------------------

_MATERIALS = [
    ("Stahl (7850 kg/m^3)", 7850.0),
    ("Aluminium (2700 kg/m^3)", 2700.0),
    ("Kupfer (8960 kg/m^3)", 8960.0),
    ("Kunststoff (1200 kg/m^3)", 1200.0),
    ("Holz (650 kg/m^3)", 650.0),
    ("Titan (4510 kg/m^3)", 4510.0),
    ("Eigene Dichte…", None),
]


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class _SweepWorker(QtCore.QThread):
    """Runs `T2GCore.run_sweep` off the GUI thread."""

    progress = QtCore.Signal(str)
    all_done = QtCore.Signal(object)  # dict {error, results}

    def __init__(self, cfg: "T2GCore.SweepConfig", parent=None) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._cancel = False
        cfg.should_cancel = lambda: self._cancel

    def request_stop(self) -> None:
        self._cancel = True

    def run(self) -> None:
        cfg = self._cfg
        cfg.on_row_start = lambda idx, row, label: self.progress.emit(
            f"Variante {idx + 1}: '{label}'…")
        cfg.on_iteration = lambda idx, row, label, itr, code, meas, fail, ok: self.progress.emit(
            f"  Iteration {itr}: " + ("OK" if ok else f"{len(fail)} Zielverfehlungen"))
        cfg.on_row_done = lambda idx, row, label, res: self.progress.emit(
            f"Variante {idx + 1} fertig.")
        try:
            results = T2GCore.run_sweep(cfg)
            self.all_done.emit({"error": None, "results": results})
        except Exception as e:  # noqa: BLE001
            self.all_done.emit({"error": str(e), "results": []})


# ---------------------------------------------------------------------------
# Goal row widget
# ---------------------------------------------------------------------------

_GOAL_KINDS = [
    ("Masse (g)", "mass"),
    ("Volumen (mm^3)", "volume"),
    ("Kante x (mm)", "dim_x"),
    ("Kante y (mm)", "dim_y"),
    ("Kante z (mm)", "dim_z"),
    ("Freitext-Kriterium", "text"),
]
_GOAL_MODES = ["==", "<=", ">="]


class _GoalWidget(QWidget):
    """One row: kind + mode + value + tolerance + remove button."""

    def __init__(self, on_removed, parent=None) -> None:
        super().__init__(parent)
        self._on_removed = on_removed

        self.kind_combo = QComboBox()
        for label, _key in _GOAL_KINDS:
            self.kind_combo.addItem(label)
        self.mode_combo = QComboBox()
        for mode in _GOAL_MODES:
            self.mode_combo.addItem(mode)
        self.value_edit = QPlainTextEdit()
        self.value_edit.setFixedHeight(28)
        self.value_edit.setPlaceholderText("Wert (oder Freitext)")
        self.tol_spin = QDoubleSpinBox()
        self.tol_spin.setRange(0.0, 1.0e9)
        self.tol_spin.setDecimals(6)
        self.tol_spin.setToolTip("Absolute Toleranz für `==`; 0 = 5 % des Werts")

        remove_btn = QPushButton("Entfernen")
        remove_btn.clicked.connect(self._remove)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.addWidget(self.kind_combo)
        lay.addWidget(self.mode_combo)
        lay.addWidget(self.value_edit, 1)
        lay.addWidget(self.tol_spin)
        lay.addWidget(remove_btn)

        self.kind_combo.currentIndexChanged.connect(self._refresh_state)
        self.mode_combo.currentIndexChanged.connect(self._refresh_state)
        self._refresh_state()

    def _refresh_state(self) -> None:
        is_text = _GOAL_KINDS[self.kind_combo.currentIndex()][1] == "text"
        self.mode_combo.setEnabled(not is_text)
        self.tol_spin.setEnabled(not is_text and self.mode_combo.currentText() == "==")
        self.value_edit.setPlaceholderText(
            "Freitext-Kriterium, z. B. 'kantenübergänge entgraten'"
            if is_text else "Wert"
        )

    def target(self) -> "T2GCore.Target | None":
        kind_key = _GOAL_KINDS[self.kind_combo.currentIndex()][1]
        value_text = self.value_edit.toPlainText().strip()
        if not value_text:
            return None
        if kind_key == "text":
            return T2GCore.Target.text(value_text)
        try:
            value = float(value_text)
        except ValueError:
            return None
        mode = self.mode_combo.currentText()
        tol = self.tol_spin.value() if mode == "==" else None
        return T2GCore.Target(kind_key, mode, value, tol)

    def _remove(self) -> None:
        self._on_removed(self)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class T2GDialog(QDialog):
    """Extended Text to Geometry dialog."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Text to Geometry")
        self.resize(880, 640)

        self._worker: _SweepWorker | None = None
        self._goals: list[_GoalWidget] = []

        root = QVBoxLayout(self)

        self.main_tabs = QTabWidget()

        tab_gen = QWidget()
        gen_v = QVBoxLayout(tab_gen)
        gen_v.setContentsMargins(6, 6, 6, 6)
        gen_v.addWidget(self._build_source_group())
        gen_v.addWidget(self._build_target_group())
        gen_v.addWidget(self._build_material_group())
        gen_v.addWidget(self._build_loop_group())
        gen_v.addWidget(self._build_result_group())
        gen_v.addStretch(1)
        self.main_tabs.addTab(tab_gen, "LLM-Generierung")

        tab_skill = QWidget()
        sk_v = QVBoxLayout(tab_skill)
        sk_v.setContentsMargins(6, 6, 6, 6)
        sk_v.addWidget(self._build_skill_group())
        sk_v.addWidget(self._build_skill_creator_group())
        sk_v.addWidget(self._build_api_group())
        sk_v.addStretch(1)
        self.main_tabs.addTab(tab_skill, "Skill & Backend")

        root.addWidget(self.main_tabs, 1)

        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("Fortschritt / Fehler")
        self.log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self.log_edit)

        self.progress_label = QLabel("lokal: ollama / qwen-gross:latest  (via pi CLI)")
        self.progress_label.setWordWrap(True)
        root.addWidget(self.progress_label)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        self.close_btn.clicked.connect(self.reject)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        self.gen_btn = QPushButton("Generieren")
        self.gen_btn.setDefault(True)
        self.gen_btn.clicked.connect(self._on_generate)
        btns.addWidget(self.close_btn)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.gen_btn)
        root.addLayout(btns)

    # ------------------------------------------------------------------ ui --

    def _build_source_group(self) -> QGroupBox:
        box = QGroupBox("Varianten-Quelle")
        lay = QVBoxLayout(box)

        self.src_group = QButtonGroup(self)
        self.src_prompt_rb = QRadioButton("Freitext (eine Variante)")
        self.src_dwg_rb = QRadioButton("2D-Zeichnung (SVG)")
        self.src_csv_rb = QRadioButton("CSV-Datei")
        self.src_xlsx_rb = QRadioButton("XLSX-Datei")
        self.src_sheet_rb = QRadioButton("FreeCAD-Spreadsheet")
        self.src_paste_rb = QRadioButton("Eingefügte Tabelle")
        for rb, id_ in [
            (self.src_prompt_rb, 0),
            (self.src_dwg_rb, 1),
            (self.src_csv_rb, 2),
            (self.src_xlsx_rb, 3),
            (self.src_sheet_rb, 4),
            (self.src_paste_rb, 5),
        ]:
            self.src_group.addButton(rb, id_)
            lay.addWidget(rb)
        self.src_prompt_rb.setChecked(True)

        self.src_stack = QTabWidget()

        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("Beschreibe die Geometrie (Maße in mm):"))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlaceholderText(
            "z. B.: ein Flansch, Außendurchmesser 80, Bohrung 40, Dicke 12, "
            "4x M8 auf 60 BDK")
        l.addWidget(self.prompt_edit)
        self.src_stack.addTab(w, "Freitext")

        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("2D-Zeichnung (SVG) mit <desc>-Spezifikation:"))
        row = QHBoxLayout()
        self.dwg_path = QLineEdit()
        self.dwg_path.setPlaceholderText(
            os.path.join(os.path.dirname(__file__), "Resources/drawings/bridge.svg"))
        pv = QPushButton("…")
        pv.clicked.connect(self._dwg_pick)
        row.addWidget(self.dwg_path); row.addWidget(pv)
        l.addLayout(row)
        self.dwg_spec_edit = QPlainTextEdit()
        self.dwg_spec_edit.setPlaceholderText(
            "Lade die Datei, um die <desc>-Spezifikation zu sehen "
            "(Einheiten, Koordinaten-Mapping, Elemente mit Koordinaten).")
        self.dwg_spec_edit.setReadOnly(True)
        self.dwg_spec_btn = QPushButton("Zeichnung laden")
        self.dwg_spec_btn.clicked.connect(self._dwg_load_spec)
        l.addWidget(self.dwg_spec_btn)
        l.addWidget(self.dwg_spec_edit, 1)
        self.src_stack.addTab(w, "Zeichnung (SVG)")

        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("CSV-Datei (Zeile 1 = Kopf, weitere Zeilen = Varianten):"))
        row = QHBoxLayout()
        self.csv_path = QLineEdit()
        self.csv_path.setPlaceholderText("/pfad/zu/varianten.csv")
        pv = QPushButton("…")
        pv.clicked.connect(self._csv_pick)
        row.addWidget(self.csv_path); row.addWidget(pv)
        l.addLayout(row)
        self.src_stack.addTab(w, "CSV")

        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("XLSX-Datei (erste Zeile = Kopf):"))
        row = QHBoxLayout()
        self.xlsx_path = QLineEdit()
        self.xlsx_path.setPlaceholderText("/pfad/zu/varianten.xlsx")
        self.xlsx_sheet = QLineEdit()
        self.xlsx_sheet.setPlaceholderText("Sheetname (optional)")
        pv = QPushButton("…")
        pv.clicked.connect(self._xlsx_pick)
        row.addWidget(self.xlsx_path); row.addWidget(pv); row.addWidget(self.xlsx_sheet)
        l.addLayout(row)
        self.src_stack.addTab(w, "XLSX")

        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("Spreadsheet-Objekt (aus dem aktiven Dokument):"))
        self.sheet_combo = QComboBox()
        self.sheet_combo.setEditable(True)
        l.addWidget(self.sheet_combo)
        l.addWidget(QLabel("Tipp: Tabelle in einer Zeile pro Variante ablegen "
                           "(Zeile 1 = Kopf)."))
        self.src_stack.addTab(w, "Spreadsheet")

        w = QWidget()
        l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("Tabelle hier einfügen (Komma, Tab oder Semikolon getrennt):"))
        self.paste_edit = QPlainTextEdit()
        self.paste_edit.setPlaceholderText("kante_x;kante_y;kante_z\n20;20;10\n30;30;15")
        l.addWidget(self.paste_edit)
        self.src_stack.addTab(w, "Einfügen")

        ids = [0, 1, 2, 3, 4, 5]
        for rb in self.src_group.buttons():
            t = self.src_group.id(rb)
            rb.toggled.connect(
                lambda checked, t=t: checked and self.src_stack.setCurrentIndex(t))
        lay.addWidget(self.src_stack)
        return box

    def _build_target_group(self) -> QGroupBox:
        box = QGroupBox("Ziele / Toleranzen (optional)")
        lay = QVBoxLayout(box)
        self.goal_list = QVBoxLayout()
        lay.addLayout(self.goal_list)
        hint_row = QHBoxLayout()
        hint_row.addWidget(QLabel("Ziel pro Zeile; Masse in g, Volumen in mm^3, "
                                  "Kanten in mm. Freitext wird ans Modell weitergegeben."))
        hint_row.addStretch(1)
        add_btn = QPushButton("+ Ziel hinzufügen")
        add_btn.clicked.connect(lambda: self._add_goal())
        hint_row.addWidget(add_btn)
        lay.addLayout(hint_row)
        return box

    def _build_material_group(self) -> QGroupBox:
        box = QGroupBox("Material (Dichte, wirkt auf Massenziele)")
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("Dichte:"))
        self.mat_combo = QComboBox()
        for name, dens in _MATERIALS:
            self.mat_combo.addItem(name, dens)
        self.mat_combo.setCurrentIndex(0)
        self.mat_custom = QDoubleSpinBox()
        self.mat_custom.setRange(1.0, 100000.0)
        self.mat_custom.setDecimals(2)
        self.mat_custom.setValue(2400.0)
        self.mat_custom.setEnabled(False)
        self.mat_unit = QLabel("kg/m^3")
        self.mat_combo.currentIndexChanged.connect(self._refresh_mat)
        lay.addWidget(self.mat_combo)
        lay.addWidget(self.mat_custom)
        lay.addWidget(self.mat_unit)
        lay.addStretch(1)
        return box

    def _refresh_mat(self, _idx: int) -> None:
        selected = _MATERIALS[self.mat_combo.currentIndex()]
        custom_selected = selected[1] is None
        self.mat_custom.setEnabled(custom_selected)
        if custom_selected:
            # pre-fill the custom field with the previously chosen density
            prev = _MATERIALS[max(0, self.mat_combo.currentIndex() - 1)][1]
            self.mat_custom.setValue(prev or 2400.0)

    def _build_loop_group(self) -> QGroupBox:
        box = QGroupBox("Loop (Sweep + Feedback)")
        form = QFormLayout(box)
        self.max_iters_spin = QSpinBox()
        self.max_iters_spin.setRange(1, 20)
        self.max_iters_spin.setValue(3)
        form.addRow("Max. Feedback-Iterationen pro Variante:", self.max_iters_spin)
        self.feedback_check = QCheckBox(
            "Zielverfehlungen + Messwerte als Feedback an das Modell zurückgeben")
        self.feedback_check.setChecked(True)
        form.addRow(self.feedback_check)
        return box

    def _build_result_group(self) -> QGroupBox:
        box = QGroupBox("Ergebnis")
        lay = QHBoxLayout(box)
        self.csv_out_check = QCheckBox("Ergebnisse + Messwerte als CSV exportieren")
        self.csv_out_check.setChecked(True)
        lay.addWidget(self.csv_out_check)
        self.csv_out_path = QLineEdit()
        self.csv_out_path.setPlaceholderText(
            os.path.join(os.path.expanduser("~"), "t2g_ergebnisse.csv"))
        pv = QPushButton("…")
        pv.clicked.connect(self._out_pick)
        lay.addWidget(self.csv_out_path)
        lay.addWidget(pv)
        return box

    # ------------------------------------------------------------ skills --

    def _skills_engine(self) -> T2GSkills.SkillEngine:
        try:
            return T2GSkills.get_engine(T2GSkills.SkillEngine._default_skills_dir())
        except Exception:
            return T2GSkills.SkillEngine().load_all()

    def _build_skill_group(self) -> QGroupBox:
        box = QGroupBox("Skill (deterministischer, parametrischer Generator)")
        lay = QVBoxLayout(box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Skill:"))
        self.skill_combo = QComboBox()
        row.addWidget(self.skill_combo)
        refresh = QPushButton("↻")
        refresh.setToolTip("Skill-Verzeichnis neu laden")
        refresh.clicked.connect(self._skill_refresh)
        row.addWidget(refresh)
        row.addStretch(1)
        self.skill_build_btn = QPushButton("Bauen")
        self.skill_build_btn.setEnabled(False)
        self.skill_build_btn.clicked.connect(self._skill_build)
        row.addWidget(self.skill_build_btn)
        lay.addLayout(row)

        self.skill_param_form = QFormLayout()
        lay.addLayout(self.skill_param_form)
        self.skill_hint = QLabel("")
        self.skill_hint.setWordWrap(True)
        lay.addWidget(self.skill_hint)
        self._skill_params: list = []
        self._skill_loaded = None
        self.skill_combo.currentIndexChanged.connect(self._skill_load)
        self._skill_refresh()
        return box

    def _skill_refresh(self) -> None:
        while self.skill_param_form.count():
            item = self.skill_param_form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            el = item.layout()
            if el is not None:
                el.deleteLater()
        self._skill_params = []
        self._skill_loaded = None
        self.skill_build_btn.setEnabled(False)

        eng = self._skills_engine()
        names = eng.registry.names()
        try:
            cur = self.skill_combo.currentText()
        except Exception:
            cur = ""
        self.skill_combo.blockSignals(True)
        self.skill_combo.clear()
        self.skill_combo.insertItem(0, "<wählen>")
        for n in names:
            self.skill_combo.addItem(n)
        idx = self.skill_combo.findText(cur)
        if idx < 0:
            idx = self.skill_combo.findText("bruecke")
        self.skill_combo.setCurrentIndex(max(0, idx))
        self.skill_combo.blockSignals(False)
        self._skill_load()

    def _skill_load(self) -> None:
        name = self.skill_combo.currentText().strip()
        if name in ("", "<wählen>"):
            self._skill_loaded = None
            self.skill_build_btn.setEnabled(False)
            self.skill_hint.setText(
                "Kein Skill gewählt. Verfügbare: " +
                (", ".join(self._skills_engine().registry.names()) or "–"))
            return
        try:
            eng = self._skills_engine()
            loaded = eng.registry.get(name)
        except Exception as e:
            self.skill_hint.setText(f"Skill konnte nicht geladen werden: {e}")
            self.skill_build_btn.setEnabled(False)
            self._skill_loaded = None
            return
        self._skill_loaded = loaded
        self._skill_params = []
        for p in loaded.definition.params:
            sp = QDoubleSpinBox()
            sp.setRange(-1e12, 1e12)
            sp.setDecimals(6)
            if p.kind == "int":
                sp.setDecimals(0)
                sp.setSingleStep(1)
            sp.setValue(float(p.default) if p.default is not None else 0.0)
            self.skill_param_form.addRow(p.label + (f" [{p.unit}]" if p.unit else ""), sp)
            self._skill_params.append((p, sp))
            p_name = p
            if p_name.min is not None:
                sp.setMinimum(float(p_name.min))
            if p_name.max is not None:
                sp.setMaximum(float(p_name.max))
        rules = ", ".join(loaded.definition.pruefregeln) or "–"
        self.skill_hint.setText(
            f"{loaded.definition.description}\nPrüfregeln: {rules}")
        self.skill_build_btn.setEnabled(True)

    def _skill_params_values(self) -> dict:
        out = {}
        for p, sp in self._skill_params:
            out[p.name] = sp.value()
        return out

    def _skill_build(self) -> None:
        if self._skill_loaded is None:
            QMessageBox.warning(self, "Skill", "Bitte zuerst einen Skill wählen.")
            return
        name = self._skill_loaded.name
        try:
            eng = self._skills_engine()
            shapes, vals, problems = eng.build(name, self._skill_params_values())
        except T2GSkills.SkillError as e:
            QMessageBox.critical(self, "Skill", f"Parameter ungültig:\n{e}")
            return
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Skill", f"Build fehlgeschlagen:\n{e}")
            return
        if problems:
            self.log_edit.appendPlainText(
                "Skill " + name + " – Prüfwarnungen:\n"
                + "\n".join(problems))
        self._add_skill_shapes(name, shapes, problems)
        self.progress_label.setText(
            f"Skill {name}: {len(shapes)} Solid(s) gebaut, Parameter: "
            + ", ".join(f"{k}={v:g}" for k, v in vals.items()))

    def _add_skill_shapes(self, name: str, shapes: list, problems: list) -> None:
        doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument("T2G")
        base = len(doc.Objects)
        added = 0
        for j, shp in enumerate(shapes):
            try:
                obj = doc.addObject("Part::Feature", f"T2G_SKILL_{base + added:03d}")
            except Exception:
                obj = doc.addObject("App::FeaturePython", f"T2G_SKILL_{base + added:03d}")
            try:
                obj.Shape = shp
            except Exception:
                pass
            obj.Label = f"T2G {name} [{j + 1}/{len(shapes)}]"
            added += 1
        if added:
            doc.recompute()
            try:
                FreeCADGui.SendMsgToActiveView("ViewFit")
            except Exception:
                pass
        status = "OK" if not problems else "WITH WARNINGS"
        FreeCAD.Console.PrintMessage(
            f"TextToGeometry: Skill {name}: {added} Solid(s) ({status}).\n")

    def _build_skill_creator_group(self) -> QGroupBox:
        box = QGroupBox("Skill-Designer (neuen Skill erzeugen)")
        lay = QFormLayout(box)
        self.sc_name = QLineEdit("meine_kiste")
        self.sc_desc = QLineEdit("Einfache Kiste mit parametrischen Maßen.")
        lay.addRow("Name:", self.sc_name)
        lay.addRow("Beschreibung:", self.sc_desc)
        self.sc_params = QPlainTextEdit(
            "w;Breite;mm;100;1;1000\nh;Höhe;mm;50;1;1000\nd;Dicke;mm;20;1;500")
        self.sc_params.setPlaceholderText(
            "pro Zeile: name;label;einheit;default;min;max")
        lay.addRow("Parameter:", self.sc_params)
        self.sc_code = QPlainTextEdit()
        self.sc_code.setPlaceholderText(
            "def build(params):\n"
            "    import Part, FreeCAD\n"
            "    w = params['w']; h = params['h']; d = params['d']\n"
            "    return [Part.makeBox(w, h, d, FreeCAD.Vector(0, 0, 0))]\n")
        lay.addRow("build-Code:", self.sc_code)
        row = QHBoxLayout()
        btn = QPushButton("Speichern unter…")
        btn.clicked.connect(self._skill_create)
        row.addStretch(1)
        row.addWidget(btn)
        self.sc_status = QLabel("")
        row.addWidget(self.sc_status)
        lay.addRow(row)
        return box

    def _skill_create(self) -> None:
        name = self.sc_name.text().strip()
        desc = self.sc_desc.text().strip()
        code = self.sc_code.toPlainText()
        params = []
        for ln in self.sc_params.toPlainText().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = [c.strip() for c in ln.split(";")]
            if len(parts) < 4:
                self.sc_status.setText(f"Zeile unvollständig: {ln!r}")
                continue
            nm, lb, unit, df = parts[0], parts[1], parts[2], parts[3]
            lo = float(parts[4]) if len(parts) > 4 and parts[4] else None
            hi = float(parts[5]) if len(parts) > 5 and parts[5] else None
            try:
                dflt = int(df) if "." not in df else float(df)
            except ValueError:
                self.sc_status.setText(f"Default ungültig bei {nm!r}: {df!r}")
                return
            params.append((nm, lb, unit, dflt, lo, hi))
        if not params:
            self.sc_status.setText("Mindestens ein Parameter fehlt.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Skill-Verzeichnis")
        if not out_dir:
            return
        try:
            path = T2GSkills.create_skill(
                name, desc or "Benutzerdefinierte Skill", params, code,
                out_dir=out_dir)
        except T2GSkills.SkillError as e:
            QMessageBox.critical(self, "Skill-Designer", str(e))
            return
        self.sc_status.setText("Erstellt: " + path)
        self._skill_refresh()
        self.skill_combo.setCurrentText(name)
        QMessageBox.information(self, "Skill-Designer",
                                "Skill gespeichert:\n" + path)

    # --------------------------------------------------------------- api --

    def _build_api_group(self) -> QGroupBox:
        box = QGroupBox("LLM / Backend")
        form = QFormLayout(box)
        self.api_kind = QComboBox()
        self.api_kind.addItem("pi CLI (Standard, T2G_PI_BIN)", "pi")
        self.api_kind.addItem("OpenAI-kompatibel (HTTP)", "openai")
        self.api_kind.addItem("Ollama (nativ)", "ollama")
        form.addRow("Backend:", self.api_kind)
        self.api_kind.currentIndexChanged.connect(self._api_kind_changed)

        self.api_base = QLineEdit("http://localhost:11434/v1")
        self.api_base.setPlaceholderText("http://host:port/v1  (OpenAI-kompatibel)")
        form.addRow("Base-URL:", self.api_base)
        self.api_model = QLineEdit("qwen-gross:latest")
        form.addRow("Modell:", self.api_model)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("API-Schlüssel (optional, z. B. Ollama=NONE)")
        form.addRow("API-Key:", self.api_key)
        row = QHBoxLayout()
        self.api_test_btn = QPushButton("Verbindung testen")
        self.api_test_btn.clicked.connect(self._api_test)
        row.addWidget(self.api_test_btn)
        row.addStretch(1)
        form.addRow(row)
        self._current_api_kind = "pi"
        self._api_kind_changed(0)
        return box

    _API_BASE_DEFAULTS = {
        "pi": "",
        "openai": "http://localhost:11434/v1",
        "ollama": "http://localhost:11434",
    }

    def _api_kind_changed(self, _idx: int) -> None:
        kind = self.api_kind.currentData()
        self._current_api_kind = kind
        show_http = kind in ("openai", "ollama")
        cur = self.api_base.text().strip()
        if cur == "" or cur in self._API_BASE_DEFAULTS.values():
            self.api_base.setText(self._API_BASE_DEFAULTS.get(kind, ""))
        self.api_base.setEnabled(show_http)
        self.api_model.setEnabled(show_http)
        self.api_key.setEnabled(show_http)
        self.api_test_btn.setEnabled(show_http)

    def _api_config(self) -> T2GCore.APIConfig:
        return T2GCore.APIConfig(
            kind=self._current_api_kind,
            base_url=self.api_base.text().strip(),
            model=self.api_model.text().strip(),
            api_key=self.api_key.text().strip(),
        )

    def _api_test(self) -> None:
        import T2GCore as _c
        cfg = self._api_config()
        if cfg.kind == "pi":
            self.api_test_result("pi-CLI: kein HTTP-Test, nutzt T2G_PI_BIN / --model")
            return
        self.progress_label.setText("Teste Backend…")
        FreeCADGui.updateGui()
        try:
            _c._t2g_api_call(cfg, "You are a helpful assistant.",
                             "Reply with exactly the two letters: OK")
            self.api_test_result("Backend-Test erfolgreich")
        except Exception as e:  # noqa: BLE001
            self.api_test_result(f"Backend-Test fehlgeschlagen: {e}")

    def api_test_result(self, msg: str) -> None:
        self.progress_label.setText(msg)
        FreeCAD.Console.PrintMessage("TextToGeometry: " + msg + "\n")

    # ---------------------------------------------------------------- data --

    def _csv_pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "CSV öffnen", os.path.expanduser("~"), "CSV (*.csv *.txt)")
        if path:
            self.csv_path.setText(path)

    def _xlsx_pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "XLSX öffnen", os.path.expanduser("~"), "Excel (*.xlsx)")
        if path:
            self.xlsx_path.setText(path)

    def _dwg_pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Zeichnung öffnen", os.path.expanduser("~"),
            "SVG (*.svg);;Zeichnungen (bridge.svg)")
        if path:
            self.dwg_path.setText(path)
            self._dwg_load_spec()

    def _dwg_load_spec(self) -> None:
        path = self.dwg_path.text().strip()
        if not path:
            return
        spec = T2GCore.load_drawing_spec(path)
        self.dwg_spec_edit.setPlainText(spec)
        self.log_edit.appendPlainText(f"Zeichnung geladen: {path}")

    def _out_pick(self) -> None:
        default = self.csv_out_path.text().strip() or os.path.join(
            os.path.expanduser("~"), "t2g_ergebnisse.csv")
        path, _ = QFileDialog.getSaveFileName(
            self, "Ergebnis-CSV speichern", default, "CSV (*.csv)")
        if path:
            self.csv_out_path.setText(path)

    def _current_sheet_ref(self) -> "str | None":
        text = self.sheet_combo.currentText().strip()
        if not text:
            return None
        return text.split("(")[0].strip()

    def _collect_rows(self) -> list:
        if self.src_csv_rb.isChecked():
            hdr, rows = T2GCore.read_table_csv(self.csv_path.text().strip())
        elif self.src_xlsx_rb.isChecked():
            hdr, rows = T2GCore.read_table_xlsx(
                self.xlsx_path.text().strip(),
                self.xlsx_sheet.text().strip() or None)
        elif self.src_sheet_rb.isChecked():
            doc = FreeCAD.ActiveDocument
            if doc is None:
                raise T2GCore.T2GError("Kein aktives Dokument für die Spreadsheet-Quelle.")
            ref = self._current_sheet_ref()
            obj = doc.getObject(ref) if ref else None
            if obj is None:
                raise T2GCore.T2GError(f"Spreadsheet-Objekt {ref!r} nicht gefunden.")
            hdr, rows = T2GCore.read_table_ssheet(obj)
        elif self.src_paste_rb.isChecked():
            hdr, rows = T2GCore.read_table_paste(self.paste_edit.toPlainText())
        else:  # prompt or drawing: single variant, no table
            if not self.src_dwg_rb.isChecked() and not self.prompt_edit.toPlainText().strip():
                raise T2GCore.T2GError("Bitte zuerst einen Freitext-Prompt eingeben.")
            return [{}]
        if not rows:
            raise T2GCore.T2GError("Tabelle enthält keine Datenzeilen.")
        return [dict(zip(hdr, r)) for r in rows]

    def _collect_targets(self) -> list:
        out = []
        for g in self._goals:
            t = g.target()
            if t is not None:
                out.append(t)
        return out

    def _collect_density(self) -> float:
        dens = _MATERIALS[self.mat_combo.currentIndex()][1]
        return self.mat_custom.value() if dens is None else float(dens)

    def _add_goal(self) -> None:
        g = _GoalWidget(self._remove_goal)
        self._goals.append(g)
        self.goal_list.addWidget(g)

    def _remove_goal(self, goal: _GoalWidget) -> None:
        if goal in self._goals:
            self._goals.remove(goal)
        goal.setParent(None)
        goal.hide()
        goal.deleteLater()

    # --------------------------------------------------------------- sweep --

    def _on_generate(self) -> None:
        self._set_busy(True)
        self.log_edit.clear()
        QtCore.QCoreApplication.processEvents()
        try:
            rows = self._collect_rows()
            targets = self._collect_targets()
            density = self._collect_density()
            feedback = self.feedback_check.isChecked()
            max_itr = max(1, self.max_iters_spin.value()) if feedback else 1
            if self.src_dwg_rb.isChecked():
                spec = self.dwg_spec_edit.toPlainText().strip()
                if not spec:
                    raise T2GCore.T2GError(
                        "Bitte zuerst die SVG-Zeichnung laden (Zeichnung lädt die "
                        "<desc>-Spezifikation).")
                base_prompt = T2GCore.build_drawing_prompt(spec)
            else:
                base_prompt = self.prompt_edit.toPlainText().strip() or (
                    "Baue die beschriebene Geometrie; nutze die Varianten-Werte "
                    "und erfülle die angegebenen Zielen.")
            cfg = T2GCore.SweepConfig(
                base_prompt=base_prompt,
                rows=rows,
                targets=targets,
                density_kg_m3=density,
                max_iterations=max_itr,
                generate_fn=self._make_gen_fn(),
            )
        except Exception as e:  # noqa: BLE001
            self._set_busy(False)
            self.log_edit.setPlainText(f"Konfiguration fehlerhaft:\n{e}")
            QMessageBox.critical(self, "Text to Geometry",
                                 "Konfiguration fehlerhaft:\n" + str(e))
            return

        self.progress_label.setText(
            f"{len(rows)} Variante(n) · {len(targets)} Ziel(e) · "
            f"{max_itr} Iteration(en)/Variante · Dichte {density:g} kg/m^3")
        self._worker = _SweepWorker(cfg, parent=None)
        self._worker.progress.connect(self.progress_label.setText)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _make_gen_fn(self):
        kind = getattr(self, "_current_api_kind", "pi")
        api_cfg = (self._api_config()
                   if hasattr(self, "api_kind") and kind in ("openai", "ollama")
                   else None)
        pi = None if api_cfg is not None else T2GCore.find_pi_binary()

        def _gen(prompt: str) -> "tuple[str, object]":
            if api_cfg is not None:
                code, shapes = T2GCore.generate_via_api(prompt, cfg=api_cfg)
            else:
                raw = T2GCore.run_backend(prompt, pi_binary=pi)
                code = T2GCore.extract_code_block(raw)
                shapes = T2GCore.exec_code_in_sandbox(code)
            return code, shapes

        return _gen

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            self.progress_label.setText(
                "Stop angefordert – läuft nach aktueller Iteration aus…")

    def _on_all_done(self, payload: dict) -> None:
        self._set_busy(False)
        error = payload.get("error")
        results = payload.get("results") or []
        if error is not None:
            self.log_edit.appendPlainText("Fehler:\n" + error)
            QMessageBox.critical(self, "Text to Geometry", "Fehler:\n" + error)
            return
        self._add_results(results)
        out_path = self.csv_out_path.text().strip() if self.csv_out_check.isChecked() else ""
        if out_path:
            try:
                T2GCore.export_results_csv(results, out_path)
                self.progress_label.setText(
                    f"CSV exportiert nach {out_path}")
            except Exception as e:  # noqa: BLE001
                self.progress_label.setText(f"CSV-Export fehlgeschlagen: {e}")
        ok_count = sum(1 for r in results if r.ok)
        self.log_edit.appendPlainText(
            f"\nFertig: {ok_count}/{len(results)} Variante(n) erfüllen alle Ziele.")
        if results:
            QMessageBox.information(
                self, "Text to Geometry",
                f"{ok_count}/{len(results)} Variante(n) erfüllen alle Ziele.\n"
                "Die Geometrien wurden in das Dokument gelegt.")

    def _add_results(self, results: list) -> None:
        doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument("T2G")
        base = len(doc.Objects)
        added = 0
        for i, r in enumerate(results):
            if r.shapes is None:
                continue
            shapes = r.shapes if isinstance(r.shapes, (list, tuple)) else [r.shapes]
            for j, shp in enumerate(shapes):
                name = f"T2G_{base + added:03d}"
                try:
                    obj = doc.addObject("Part::Feature", name)
                except Exception:
                    obj = doc.addObject("App::FeaturePython", name)
                try:
                    obj.Shape = shp
                except Exception:
                    pass
                obj.Label = f"T2G {r.label} [{'OK' if r.ok else 'MISS'}]"
                added += 1
        if added:
            doc.recompute()
            try:
                FreeCADGui.SendMsgToActiveView("ViewFit")
            except Exception:
                pass
        FreeCAD.Console.PrintMessage(
            f"TextToGeometry: {added} Objekt(e) aus {len(results)} Variante(n) hinzugefügt.\n")

    def _set_busy(self, busy: bool) -> None:
        self.gen_btn.setEnabled(not busy)
        self.close_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        self.src_group.setExclusive(not busy)
        for rb in self.src_group.buttons():
            rb.setEnabled(not busy)
        self.src_stack.setEnabled(not busy)
        self.mat_combo.setEnabled(not busy)
        self.max_iters_spin.setEnabled(not busy)
        self.feedback_check.setEnabled(not busy)

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(3000)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class T2GGenerateCommand:
    """Command registered via FreeCADGui.addCommand in InitGui.py."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Generate geometry",
            "ToolTip": "Freitext oder Varianten-Tabelle (CSV/XLSX/Spreadsheet) "
                       "-> 3D FreeCAD-Geometrie (lokales LLM, mit Zielen + Feedback-Loop)",
            "Pixmap": "Resources/icons/text-to-geometry.svg",
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        from PySide6.QtWidgets import QApplication

        parent = QApplication.activeWindow()
        T2GDialog(parent).exec()


# Register the command (FreeCADGui is already imported above).
FreeCADGui.addCommand("T2G_Generate", T2GGenerateCommand())
