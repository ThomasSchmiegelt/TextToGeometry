# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
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
import re
import shutil

import FreeCAD
import FreeCADGui
from PySide6 import QtCore
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QLineEdit,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QRadioButton,
    QScrollArea,
    QToolBar,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

import T2GAgent
import T2GCore
import T2GProject
import T2GSkills
import T2GTools

_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "Resources", "icons")


def _icon(basename: str) -> str:
    """Absolute path of a toolbar icon (FreeCAD resolves those reliably)."""
    return os.path.join(_ICON_DIR, basename)


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


class _ChatWorker(QtCore.QThread):
    """One conversational turn off the GUI thread (the LLM call is slow)."""

    done = QtCore.Signal(object)  # dict {kind, text, error}

    def __init__(self, prompt: str, cfg, pi_binary, parent=None) -> None:
        super().__init__(parent)
        self._prompt = prompt
        self._cfg = cfg
        self._pi = pi_binary

    def run(self) -> None:
        try:
            raw, thinking = T2GCore.call_model_verbose(
                self._prompt, T2GCore.CHAT_SYSTEM_PROMPT, self._cfg, self._pi)
            reply = T2GCore.parse_chat_reply(raw)
            self.done.emit({"kind": reply.kind, "text": reply.text,
                            "thinking": thinking, "error": None, "raw": raw})
        except Exception as e:  # noqa: BLE001
            self.done.emit({"kind": None, "text": "", "error": str(e)})


class _TextWorker(QtCore.QThread):
    """Any single LLM call off the GUI thread; emits the raw answer."""

    done = QtCore.Signal(object)  # dict {text, error, tag}

    def __init__(self, prompt: str, system_prompt: str, cfg, pi_binary,
                 tag: str = "", parent=None) -> None:
        super().__init__(parent)
        self._prompt = prompt
        self._system = system_prompt
        self._cfg = cfg
        self._pi = pi_binary
        self._tag = tag

    def run(self) -> None:
        try:
            raw, thinking = T2GCore.call_model_verbose(
                self._prompt, self._system, self._cfg, self._pi)
            self.done.emit({"text": raw, "thinking": thinking,
                            "error": None, "tag": self._tag})
        except Exception as e:  # noqa: BLE001
            self.done.emit({"text": "", "error": str(e), "tag": self._tag})


class _CallWorker(QtCore.QThread):
    """Runs any blocking callable off the GUI thread.

    Anything that talks to a network or starts a process belongs here: a pi
    call spawns Node and then thinks for minutes, and doing that in the GUI
    thread freezes FreeCAD solid.
    """

    done = QtCore.Signal(object)   # {"result", "error", "tag"}

    def __init__(self, fn, tag: str = "", parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._tag = tag
        self.tag = tag

    def run(self) -> None:
        try:
            self.done.emit({"result": self._fn(), "error": None,
                            "tag": self._tag})
        except Exception as e:  # noqa: BLE001
            self.done.emit({"result": None, "error": str(e), "tag": self._tag})


def _slugify(text: str) -> str:
    """A valid Python identifier from a German topic line."""
    umlaut = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
              "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
    out = "".join(umlaut.get(c, c) for c in (text or "").strip().lower())
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in out)
    out = "_".join(filter(None, out.split("_")))[:40]
    if not out or out[0].isdigit():
        out = "skill_" + out
    return out


# ---------------------------------------------------------------------------
# Document context + applying the operations the model asked for
# ---------------------------------------------------------------------------

# E [MPa], Poisson, density [kg/m^3]
_FEM_MATERIALS = {
    "stahl": ("Steel-Generic", 210000.0, 0.30, 7900.0),
    "steel": ("Steel-Generic", 210000.0, 0.30, 7900.0),
    "aluminium": ("AlMg3F24", 70000.0, 0.33, 2700.0),
    "aluminum": ("AlMg3F24", 70000.0, 0.33, 2700.0),
    "kupfer": ("Copper-Generic", 110000.0, 0.35, 8960.0),
    "titan": ("Titanium-Generic", 105000.0, 0.34, 4510.0),
    "kunststoff": ("PA6-Generic", 3000.0, 0.39, 1150.0),
}

_SIDES = ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")


def _active_doc(create: bool = False):
    doc = FreeCAD.ActiveDocument
    if doc is None and create:
        doc = FreeCAD.newDocument("T2G")
    return doc


def _doc_objects(doc=None) -> list:
    """Describe the document as plain dicts (prompt context + OpRecorder)."""
    doc = doc or _active_doc()
    out: list = []
    if doc is None:
        return out
    for o in doc.Objects:
        entry = {"name": o.Name, "label": getattr(o, "Label", o.Name),
                 "type": o.TypeId}
        shp = getattr(o, "Shape", None)
        if shp is not None and getattr(shp, "isNull", lambda: True)() is False:
            try:
                bb = shp.BoundBox
                entry["bbox"] = {"xmin": bb.XMin, "xmax": bb.XMax,
                                 "ymin": bb.YMin, "ymax": bb.YMax,
                                 "zmin": bb.ZMin, "zmax": bb.ZMax}
                entry["volume"] = float(shp.Volume)
                entry["solids"] = len(shp.Solids)
                entry["faces"] = len(shp.Faces)
            except Exception:  # noqa: BLE001  -- non-geometric objects
                pass
        out.append(entry)
    return out


def _selection_names() -> list:
    try:
        return [o.Name for o in FreeCADGui.Selection.getSelection()]
    except Exception:  # noqa: BLE001
        return []


def _find_object(doc, name: str):
    obj = doc.getObject(name)
    if obj is not None:
        return obj
    for o in doc.Objects:  # allow the model to use a Label
        if getattr(o, "Label", None) == name:
            return o
    raise T2GCore.T2GError(f"Objekt {name!r} nicht im Dokument.")


def _faces_on_side(shape, side: str) -> list:
    """Names of the faces lying flat on one side of the bounding box.

    The model addresses faces as "zmin"/"xmax"/... because it cannot know
    FreeCAD's face numbering; this resolves that to real face names.
    """
    side = (side or "").strip().lower()
    if side not in _SIDES:
        raise T2GCore.T2GError(
            f"Unbekannte Flächenangabe {side!r}; erlaubt: {', '.join(_SIDES)}")
    axis, lim = side[0].upper(), side[1:]
    bb = shape.BoundBox
    span = max(bb.XLength, bb.YLength, bb.ZLength) or 1.0
    tol = max(1e-6, span * 1e-4)
    target = getattr(bb, axis + ("Min" if lim == "min" else "Max"))
    out = []
    for i, f in enumerate(shape.Faces, 1):
        fb = f.BoundBox
        lo = getattr(fb, axis + "Min")
        hi = getattr(fb, axis + "Max")
        if abs(hi - lo) <= tol and abs(lo - target) <= tol:
            out.append("Face%d" % i)
    if not out:
        raise T2GCore.T2GError(
            f"Keine ebene Fläche auf Seite {side!r} gefunden.")
    return out


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


class T2GPanel(QWidget):
    """Text to Geometry panel (embedded widget).

    Hosted in a QDockWidget of FreeCAD's main window, so it can be docked
    on any side, tabbed with other panels or floated. The ``T2G-Panel``
    toolbar/menu button re-shows it after it was closed.
    """

    def __init__(self) -> None:
        super().__init__(None)
        self.setObjectName("T2G_Panel")

        self._worker: _SweepWorker | None = None
        self._goals: list[_GoalWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Built first: several group builders already report through these.
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("Fortschritt / Fehler")
        self.log_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # One tab per step instead of one long scroll of group boxes: the
        # panel is usually docked at ~420 px width, where five stacked groups
        # squash each other into unreadable rows.
        self.main_tabs = QTabWidget()
        self.main_tabs.setDocumentMode(True)

        # Order follows the way the work actually goes: a guided start, the
        # conversation, then the places to inspect and correct what came out.
        self.tab_start = self._make_tab(self._build_start_group())
        self.main_tabs.addTab(self.tab_start, "Start")
        self.main_tabs.setTabToolTip(0, "Geführter Ablauf und Automatik")

        self.tab_chat = self._build_chat_group()
        self.main_tabs.addTab(self.tab_chat, "Dialog")
        self.main_tabs.setTabToolTip(
            1, "Anweisungen am offenen Dokument und an das Projekt")

        self.tab_project = self._make_tab(self._build_project_group(),
                                          self._build_project_plan_group(),
                                          self._build_project_skills_group(),
                                          self._build_project_pairs_group())
        self.main_tabs.addTab(self.tab_project, "Projekt")
        self.main_tabs.setTabToolTip(
            2, "Projektverzeichnis, Auftrag, agent.d, Bauteilliste, Gewichtung")

        self.tab_skill = self._make_tab(self._build_skill_group())
        self.main_tabs.addTab(self.tab_skill, "Skills")
        self.main_tabs.setTabToolTip(
            3, "Vorhandene Generatoren: Parameter einstellen und bauen")

        self.tab_learn = self._make_tab(self._build_skill_learn_group(),
                                        self._build_skill_refine_group(),
                                        self._build_skill_creator_group())
        self.main_tabs.addTab(self.tab_learn, "Lernen")
        self.main_tabs.setTabToolTip(
            4, "Neue Skills lernen, vorhandene verfeinern, von Hand anlegen")

        self.tab_tools = self._make_tab(self._build_tools_group(),
                                        self._build_project_tools_group())
        self.main_tabs.addTab(self.tab_tools, "Werkzeuge")
        self.main_tabs.setTabToolTip(
            5, "Makros, Add-ons und Python-Module dieser Installation")

        self.tab_sweep = self._make_tab(self._build_source_group(),
                                        self._build_target_group(),
                                        self._build_material_group(),
                                        self._build_loop_group(),
                                        self._build_result_group())
        self.main_tabs.addTab(self.tab_sweep, "Serie")
        self.main_tabs.setTabToolTip(
            6, "Variantenserie aus Tabelle oder Zeichnung, mit Zielen")
        self.tab_gen = self.tab_sweep
        self.tab_goals = self.tab_sweep

        self.tab_api = self._make_tab(self._build_api_group())
        self.main_tabs.addTab(self.tab_api, "Backend")
        self.main_tabs.setTabToolTip(7, "LLM-Backend (Ollama / API / pi-CLI)")

        try:
            self._restore_last_project()
        except Exception as e:  # noqa: BLE001
            FreeCAD.Console.PrintWarning(
                "TextToGeometry: Wiederherstellung fehlgeschlagen: %s\n" % e)
        self._refresh_start()
        QtCore.QTimer.singleShot(400, self._tools_scan)

        log_box = QWidget()
        log_v = QVBoxLayout(log_box)
        log_v.setContentsMargins(0, 0, 0, 0)
        log_v.setSpacing(2)
        log_head = QLabel("Protokoll")
        log_head.setStyleSheet("color: palette(mid);")
        log_v.addWidget(log_head)
        log_v.addWidget(self.log_edit, 1)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.main_tabs)
        split.addWidget(log_box)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 1)
        split.setSizes([560, 120])
        split.setChildrenCollapsible(True)
        root.addWidget(split, 1)

        root.addWidget(self.progress_label)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.close_btn = QPushButton("Schließen")
        self.close_btn.clicked.connect(self._close_window)
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

    def _reveal(self, widget) -> None:
        """Scroll a group into view.

        Switching to a tab is not enough when the group sits below the fold --
        the Skill-Designer button looked broken because nothing visibly moved.
        """
        if widget is None:
            return
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(widget, 0, 40)
                return
            parent = parent.parentWidget()

    @staticmethod
    def _make_tab(*groups) -> QWidget:
        """Put the given group boxes on a scrollable page.

        The scroll area is what keeps a narrow dock usable: groups keep their
        natural height and the page scrolls instead of squeezing every row.
        """
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        for g in groups:
            v.addWidget(g)
        v.addStretch(1)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(inner)
        return area

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

    def _skills_engine(self, reload: bool = False) -> T2GSkills.SkillEngine:
        """The shared skill engine; ``reload`` re-scans the directory.

        ``get_engine`` caches, so a freshly written skill only shows up when
        the directory is scanned again.
        """
        try:
            eng = T2GSkills.get_engine(T2GSkills.SkillEngine._default_skills_dir())
        except Exception:  # noqa: BLE001
            eng = T2GSkills.SkillEngine()
            reload = True
        if reload:
            eng.load_all()
        return eng

    def _build_skill_group(self) -> QGroupBox:
        box = QGroupBox("Vorhandene Skills – auswählen, einstellen, bauen")
        self._grp_skill = box
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

        eng = self._skills_engine(reload=True)
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
        while self.skill_param_form.count():
            item = self.skill_param_form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
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
        self._grp_creator = box
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

        # Which backend actually works on this machine? Ollama when its server
        # answers, otherwise a saved HTTP API, otherwise the pi CLI. The old
        # hard-coded "pi" default failed with a pi/npm error whenever FreeCAD
        # was started outside start.sh (no T2G_PI_BIN, `pi` not on PATH).
        saved = self._api_settings_load()
        try:
            detected, detect_msg = T2GCore.detect_backend(saved)
        except Exception as e:  # noqa: BLE001
            detected, detect_msg = "ollama", f"Backend-Erkennung fehlgeschlagen: {e}"
        if saved is not None and saved.kind:
            detected = saved.kind

        self.api_kind = QComboBox()
        self.api_kind.addItem("Ollama (nativ, lokal)", "ollama")
        self.api_kind.addItem("API / OpenAI-kompatibel (HTTP)", "openai")
        self.api_kind.addItem("pi CLI (T2G_PI_BIN)", "pi")
        form.addRow("Backend:", self.api_kind)

        self.api_base = QLineEdit(
            (saved.base_url if saved else "") or T2GCore.OLLAMA_DEFAULT_URL)
        self.api_base.setPlaceholderText(
            "z. B. https://api.openai.com/v1 oder http://host:port")
        form.addRow("Base-URL:", self.api_base)

        # pi knows its providers by name and has no base URL of its own.
        self.api_provider = QComboBox()
        self.api_provider.setEditable(True)
        for name in ("ollama", "openai", "anthropic", "google", "openrouter",
                     "groq", "mistral", "deepseek", "xai", "together"):
            self.api_provider.addItem(name)
        self.api_provider.setCurrentText(
            (saved.provider if saved and saved.provider else "ollama"))
        self.api_provider.setToolTip(
            "Provider der pi-CLI. „ollama“ ist lokal; jeder andere braucht "
            "den API-Schlüssel unten.")
        form.addRow("pi-Provider:", self.api_provider)
        self._api_form = form

        self.api_model = QComboBox()
        self.api_model.setEditable(True)
        self.api_model.addItem((saved.model if saved and saved.model
                                else "qwen-gross:latest"))
        form.addRow("Modell:", self.api_model)

        self.api_key = QLineEdit(saved.api_key if saved else "")
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-…  (nur für externe Endpunkte)")
        form.addRow("API-Key:", self.api_key)

        self.api_remember = QCheckBox(
            "Zugang merken (Adresse, Modell und Schlüssel im Klartext in "
            "FreeCADs Einstellungen)")
        self.api_remember.setChecked(bool(saved and saved.api_key))
        self.api_remember.toggled.connect(lambda _c: self._api_settings_save())
        form.addRow("", self.api_remember)

        self.api_thinking = QComboBox()
        for label, value in (("automatisch (Servervorgabe)", "auto"),
                             ("aus – am schnellsten", "off"),
                             ("niedrig (empfohlen)", "low"),
                             ("mittel", "medium"),
                             ("hoch – langsam, für schwierige Geometrie", "high")):
            self.api_thinking.addItem(label, value)
        idx = self.api_thinking.findData(
            (saved.thinking if saved and saved.thinking else "low"))
        self.api_thinking.setCurrentIndex(max(0, idx))
        self.api_thinking.setToolTip(
            "Gilt für die kurzen Schritte des Agenten. Code für Skills und "
            "Werkzeuge denkt immer gründlich, unabhängig davon.\n"
            "Gemessen an qwen-gross, ein Agentenschritt: aus 1,2 s · "
            "niedrig 2,0 s · hoch 3,9 s.")
        self.api_thinking.currentIndexChanged.connect(
            lambda _i: self._api_settings_save())
        form.addRow("Denktiefe:", self.api_thinking)

        self.api_timeout = QSpinBox()
        self.api_timeout.setRange(30, 3600)
        self.api_timeout.setSingleStep(30)
        self.api_timeout.setValue(900)
        self.api_timeout.setSuffix(" s")
        self.api_timeout.setToolTip(
            "Zeitlimit je Modellantwort. Ein 27B-Modell braucht für ein "
            "komplettes parametrisches Bauteil schnell 3–5 Minuten.")
        form.addRow("Zeitlimit:", self.api_timeout)

        row = QHBoxLayout()
        self.api_test_btn = QPushButton("Verbindung testen")
        self.api_test_btn.setToolTip("Prüft Erreichbarkeit und schickt einen Mini-Prompt")
        self.api_test_btn.clicked.connect(self._api_test)
        row.addWidget(self.api_test_btn)
        self.api_start_btn = QPushButton("Ollama starten")
        self.api_start_btn.setToolTip(
            "Startet den lokalen Ollama-Server (systemd-Unit oder `ollama serve`)")
        self.api_start_btn.clicked.connect(self._ollama_start)
        row.addWidget(self.api_start_btn)
        self.api_models_btn = QPushButton("Modelle laden")
        self.api_models_btn.setToolTip(
            "Fragt die Modell-Liste beim Server ab (Ollama /api/tags, "
            "API /v1/models)")
        self.api_models_btn.clicked.connect(self._refresh_models)
        row.addWidget(self.api_models_btn)
        row.addStretch(1)
        form.addRow(row)

        self.api_status = QLabel(detect_msg)
        self.api_status.setWordWrap(True)
        form.addRow("Status:", self.api_status)

        self.api_kind.currentIndexChanged.connect(self._api_kind_changed)
        idx = self.api_kind.findData(detected)
        self._current_api_kind = detected
        self.api_kind.setCurrentIndex(max(0, idx))
        self._api_kind_changed(self.api_kind.currentIndex())
        if detected in ("ollama", "openai"):
            self._refresh_models(quiet=True)
        self.progress_label.setText(detect_msg)
        return box

    # ---- remembering the access across FreeCAD restarts -------------------

    _PREF_PATH = "User parameter:BaseApp/Preferences/Mod/TextToGeometry"

    def _api_settings_load(self) -> "T2GCore.APIConfig | None":
        try:
            prm = FreeCAD.ParamGet(self._PREF_PATH)
        except Exception:  # noqa: BLE001
            return None
        kind = prm.GetString("backend", "")
        base = prm.GetString("base_url", "")
        model = prm.GetString("model", "")
        key = prm.GetString("api_key", "")
        provider = prm.GetString("provider", "")
        thinking = prm.GetString("thinking", "")
        timeout = prm.GetInt("timeout_s", 0)
        if not (kind or base or model or key or provider):
            return None
        return T2GCore.APIConfig(kind=kind or "ollama", base_url=base,
                                 model=model, api_key=key,
                                 provider=provider or "ollama",
                                 thinking=thinking or "low",
                                 timeout_s=timeout or 900)

    def _api_settings_save(self) -> None:
        """Persist the backend settings; the key only when asked for."""
        try:
            prm = FreeCAD.ParamGet(self._PREF_PATH)
        except Exception:  # noqa: BLE001
            return
        prm.SetString("backend", self._current_api_kind or "")
        prm.SetString("base_url", self.api_base.text().strip())
        prm.SetString("model", self.api_model.currentText().strip())
        prm.SetString("provider", (self.api_provider.currentText().strip()
                                   if hasattr(self, "api_provider") else ""))
        prm.SetString("thinking", (self.api_thinking.currentData()
                                   if hasattr(self, "api_thinking") else ""))
        prm.SetInt("timeout_s", int(self.api_timeout.value()))
        if getattr(self, "api_remember", None) is not None and self.api_remember.isChecked():
            prm.SetString("api_key", self.api_key.text())
        else:
            prm.SetString("api_key", "")

    _API_BASE_DEFAULTS = {
        "pi": "",
        "openai": "http://localhost:11434/v1",
        "ollama": "http://localhost:11434",
    }

    def _api_kind_changed(self, _idx: int) -> None:
        kind = self.api_kind.currentData()
        self._current_api_kind = kind
        http = kind in ("openai", "ollama")
        cur = self.api_base.text().strip()
        if cur == "" or cur in self._API_BASE_DEFAULTS.values():
            self.api_base.setText(self._API_BASE_DEFAULTS.get(kind, ""))
        self.api_base.setEnabled(http)
        # pi reaches hosted providers too -- it just needs the key handed on
        self.api_key.setEnabled(kind in ("openai", "pi"))
        if getattr(self, "api_remember", None) is not None:
            self.api_remember.setEnabled(True)
        self.api_models_btn.setEnabled(True)
        form = getattr(self, "_api_form", None)
        if form is not None:
            try:
                form.setRowVisible(self.api_base, http)
                form.setRowVisible(self.api_provider, kind == "pi")
            except Exception:  # noqa: BLE001  -- Qt < 6.4
                self.api_provider.setEnabled(kind == "pi")
        # A connection test must stay available for every backend -- that it
        # was disabled for "pi" left the user with no way to see what was wrong.
        self.api_test_btn.setEnabled(True)
        self.api_start_btn.setEnabled(kind in ("ollama", "pi"))
        self._refresh_backend_status()

    def _refresh_backend_status(self) -> None:
        """Probe the backend in a thread -- /v1/models can take seconds."""
        cfg = self._api_config()
        pi = T2GCore.find_pi_binary_or_none()

        def _work():
            if cfg.kind == "pi":
                if not pi:
                    return "pi-CLI nicht gefunden."
                return "pi-CLI: %s · Provider %s · Modell %s" % (
                    pi, cfg.provider or "ollama", cfg.model or "–")
            return T2GCore.backend_status(cfg)

        self.api_status.setText("Prüfe Backend …")
        self._spawn(_work, "status", self._refresh_backend_status_done)

    def _refresh_backend_status_done(self, payload: dict) -> None:
        msg = (payload.get("error") and ("Status unbekannt: " + payload["error"])
               or str(payload.get("result") or ""))
        self.api_status.setText(msg)
        self.progress_label.setText(msg)

    def _api_config(self) -> T2GCore.APIConfig:
        return T2GCore.APIConfig(
            kind=self._current_api_kind,
            base_url=self.api_base.text().strip(),
            model=self.api_model.currentText().strip(),
            api_key=self.api_key.text().strip(),
            provider=(self.api_provider.currentText().strip()
                      if hasattr(self, "api_provider") else "ollama"),
            thinking=(self.api_thinking.currentData()
                      if hasattr(self, "api_thinking") else "low"),
            timeout_s=int(self.api_timeout.value()) if hasattr(self, "api_timeout") else 900,
        )

    def _refresh_models(self, quiet: bool = False) -> None:
        """Fill the model combo from whichever backend is configured.

        Asking pi means starting the CLI, so this never runs inline.
        """
        cfg = self._api_config()
        pi = T2GCore.find_pi_binary_or_none()
        if not quiet:
            self.progress_label.setText("Frage Modelle ab …")
        started = self._spawn(lambda: T2GCore.list_models(cfg, pi), "modelle",
                              lambda payload, q=quiet:
                              self._refresh_models_done(payload, q))
        if started is not None:
            self.api_models_btn.setEnabled(False)

    def _refresh_models_done(self, payload: dict, quiet: bool) -> None:
        self.api_models_btn.setEnabled(True)
        if payload.get("error"):
            if not quiet:
                self.api_test_result("Modell-Liste nicht abrufbar: "
                                     + payload["error"])
            return
        models = payload.get("result") or []
        keep = self.api_model.currentText().strip()
        self.api_model.blockSignals(True)
        self.api_model.clear()
        for m in models:
            if m:
                self.api_model.addItem(m)
        if keep:
            i = self.api_model.findText(keep)
            if i >= 0:
                self.api_model.setCurrentIndex(i)
            else:
                self.api_model.setEditText(keep)
        self.api_model.blockSignals(False)
        self._api_settings_save()
        if not quiet:
            self.api_test_result(f"{len(models)} Modell(e) geladen.")

    def _ollama_start(self) -> None:
        base = self.api_base.text().strip() or T2GCore.OLLAMA_DEFAULT_URL
        self.progress_label.setText("Starte Ollama …")
        if self._spawn(lambda: T2GCore.start_ollama(base), "ollama",
                       self._ollama_start_done) is not None:
            self.api_start_btn.setEnabled(False)

    def _ollama_start_done(self, payload: dict) -> None:
        self.api_start_btn.setEnabled(True)
        if payload.get("error"):
            self.api_test_result("Ollama-Start fehlgeschlagen: "
                                 + payload["error"])
        else:
            self.api_test_result(str(payload.get("result") or ""))
            self._refresh_models(quiet=True)
        self._refresh_backend_status()

    def _api_test(self) -> None:
        """Check the backend -- in a thread, because pi takes its time."""
        cfg = self._api_config()
        pi = T2GCore.find_pi_binary_or_none()

        def _work():
            if cfg.kind == "pi":
                if not pi:
                    raise T2GCore.BackendError(
                        "pi-CLI nicht gefunden. Entweder T2G_PI_BIN setzen "
                        "oder oben ein anderes Backend wählen.")
                if cfg.provider == "ollama" and not T2GCore.ollama_running():
                    raise T2GCore.BackendError(
                        "pi gefunden (%s), aber Ollama läuft nicht – erst "
                        "„Ollama starten“ drücken oder einen anderen "
                        "pi-Provider wählen." % pi)
                reply = T2GCore.call_model(
                    "Reply with exactly the two letters: OK",
                    "You are terse.", cfg, pi)
                return ("pi ok: %s · %s/%s: %s"
                        % (os.path.basename(pi), cfg.provider, cfg.model,
                           reply.strip()[:30]))
            if cfg.kind == "ollama" and not T2GCore.ollama_running(cfg.base_url):
                raise T2GCore.BackendError(
                    "Ollama unter %s nicht erreichbar – „Ollama starten“ "
                    "drücken." % cfg.base_url)
            reply = T2GCore._t2g_api_call(
                cfg, "You are a helpful assistant.",
                "Reply with exactly the two letters: OK")
            return ("Backend-Test erfolgreich (%s): %s"
                    % (cfg.model, reply.strip()[:40]))

        self.progress_label.setText("Teste Backend …")
        if self._spawn(_work, "test", self._api_test_done) is not None:
            self.api_test_btn.setEnabled(False)

    def _api_test_done(self, payload: dict) -> None:
        self.api_test_btn.setEnabled(True)
        if payload.get("error"):
            self.api_test_result("Backend-Test fehlgeschlagen: "
                                 + payload["error"])
            return
        self.api_test_result(str(payload.get("result") or "ok"))
        self._api_settings_save()

    def api_test_result(self, msg: str) -> None:
        self.progress_label.setText(msg)
        self.log_edit.appendPlainText(msg)
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
            kind = ("Backend nicht bereit"
                    if isinstance(e, T2GCore.BackendError)
                    else "Konfiguration fehlerhaft")
            self.log_edit.setPlainText(f"{kind}:\n{e}")
            self.progress_label.setText(f"{kind}: {e}")
            QMessageBox.critical(self, "Text to Geometry", f"{kind}:\n{e}")
            return

        self.progress_label.setText(
            f"{len(rows)} Variante(n) · {len(targets)} Ziel(e) · "
            f"{max_itr} Iteration(en)/Variante · Dichte {density:g} kg/m^3")
        self._worker = _SweepWorker(cfg, parent=None)
        self._worker.progress.connect(self.progress_label.setText)
        self._worker.all_done.connect(self._on_all_done)
        self._worker.start()

    def _make_gen_fn(self):
        api_cfg = self._api_config() if hasattr(self, "api_kind") else None
        pi = None
        if api_cfg is not None and api_cfg.kind == "pi":
            pi = T2GCore.find_pi_binary()
        elif api_cfg is not None:
            if api_cfg.kind == "ollama" and not T2GCore.ollama_running(api_cfg.base_url):
                raise T2GCore.BackendError(
                    f"Ollama ist unter {api_cfg.base_url} nicht erreichbar. "
                    "Im Tab „Backend“ auf „Ollama starten“ drücken.")
            if not api_cfg.model:
                raise T2GCore.BackendError(
                    "Kein Modell gewählt (Tab „Backend“ → Modelle laden).")

        gen_cfg = T2GCore.with_thinking(api_cfg, "high")

        def _gen(prompt: str) -> "tuple[str, object]":
            if gen_cfg is not None and gen_cfg.kind in ("openai", "ollama"):
                code, shapes = T2GCore.generate_via_api(prompt, cfg=gen_cfg)
            else:
                raw = T2GCore.call_model(prompt, T2GCore.SYSTEM_PROMPT,
                                         gen_cfg, pi)
                code = T2GCore._strip_fenced_python(raw) or raw.strip()
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

    # ------------------------------------------------------------- dialog --

    def _build_chat_group(self) -> QGroupBox:
        box = QGroupBox("Dialog – verändert das aktive Dokument")
        v = QVBoxLayout(box)
        self.chat_view = QPlainTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setPlaceholderText(
            "Beispiele:\n"
            "  Ergänze eine Bohrung mit 10 mm Durchmesser in der Mitte.\n"
            "  Lege ein neues Bauteil mit dem Namen Grundplatte an, 100x60x8.\n"
            "  Baue diese beiden Bauteile in eine Baugruppe ein.\n"
            "  Führe eine Festigkeitsanalyse durch: unten fest, oben 500 N.\n\n"
            "Fehlt eine Angabe, stellt das Modell eine Rückfrage.")
        v.addWidget(self.chat_view, 1)

        self.chat_ctx = QLabel("")
        self.chat_ctx.setWordWrap(True)
        self.chat_ctx.setStyleSheet("color: palette(mid);")
        v.addWidget(self.chat_ctx)

        # Eingabemaske für Zahlenfragen des Agenten (normalerweise verborgen)
        self.chat_mask_box = QGroupBox("Angaben")
        mask_v = QVBoxLayout(self.chat_mask_box)
        self.chat_mask_form = QFormLayout()
        mask_v.addLayout(self.chat_mask_form)
        mask_row = QHBoxLayout()
        self.chat_mask_hint = QLabel("")
        self.chat_mask_hint.setWordWrap(True)
        mask_row.addWidget(self.chat_mask_hint, 1)
        self.chat_mask_btn = QPushButton("Übernehmen und weiter")
        self.chat_mask_btn.clicked.connect(self._agent_mask_submit)
        mask_row.addWidget(self.chat_mask_btn)
        mask_v.addLayout(mask_row)
        self.chat_mask_box.setVisible(False)
        self._chat_mask_rows: list = []
        v.addWidget(self.chat_mask_box)

        self.chat_input = QPlainTextEdit()
        self.chat_input.setPlaceholderText(
            "z. B. „neues Zylinderkopfprojekt“ – oder Antwort auf die "
            "Rückfrage (Strg+Enter sendet)")
        self.chat_input.setMaximumHeight(72)
        self.chat_input.installEventFilter(self)
        v.addWidget(self.chat_input)

        row = QHBoxLayout()
        self.chat_reset_btn = QPushButton("Verlauf zurücksetzen")
        self.chat_reset_btn.clicked.connect(self._chat_reset)
        row.addWidget(self.chat_reset_btn)
        self.chat_thinking = QCheckBox("Denken zeigen")
        self.chat_thinking.setToolTip(
            "Zeigt die Überlegungen des Modells im Verlauf (immer im "
            "Protokoll unten)")
        row.addWidget(self.chat_thinking)
        self.chat_agent_mode = QCheckBox("Agent")
        self.chat_agent_mode.setChecked(True)
        self.chat_agent_mode.setToolTip(
            "An: der Agent arbeitet mehrschrittig (Projekt, Recherche, "
            "Parameter, Skills). Aus: einzelne Anweisung am Dokument.")
        row.addWidget(self.chat_agent_mode)
        self.chat_steps = QSpinBox()
        self.chat_steps.setRange(1, 30)
        self.chat_steps.setValue(T2GAgent.MAX_STEPS_DEFAULT)
        self.chat_steps.setPrefix("max. ")
        self.chat_steps.setSuffix(" Schritte")
        row.addWidget(self.chat_steps)
        self.chat_stop_btn = QPushButton("Stop")
        self.chat_stop_btn.setEnabled(False)
        self.chat_stop_btn.clicked.connect(self._agent_stop)
        row.addWidget(self.chat_stop_btn)
        self.chat_ctx_btn = QPushButton("Kontext aktualisieren")
        self.chat_ctx_btn.setToolTip(
            "Objekte und Auswahl neu einlesen (passiert vor jedem Senden automatisch)")
        self.chat_ctx_btn.clicked.connect(self._chat_refresh_context)
        row.addWidget(self.chat_ctx_btn)
        row.addStretch(1)
        self.chat_send_btn = QPushButton("Senden")
        self.chat_send_btn.setDefault(True)
        self.chat_send_btn.clicked.connect(self._chat_send)
        row.addWidget(self.chat_send_btn)
        v.addLayout(row)

        self._chat = T2GCore.ChatSession()
        self._chat_worker = None
        self._agent_run = None
        self._agent_job_done = None
        self._chat_refresh_context()
        return box

    def eventFilter(self, obj, event):  # noqa: N802  (Qt naming)
        if obj is getattr(self, "chat_input", None) and event.type() == QtCore.QEvent.Type.KeyPress:
            if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                    and event.modifiers() & Qt.ControlModifier):
                self._chat_send()
                return True
        return super().eventFilter(obj, event)

    def _chat_refresh_context(self) -> None:
        doc = _active_doc()
        objs = _doc_objects(doc)
        sel = _selection_names()
        self.chat_ctx.setText(
            "Dokument: %s · %d Objekt(e) · Auswahl: %s"
            % (doc.Name if doc else "– keines –", len(objs),
               ", ".join(sel) if sel else "nichts"))

    def _chat_append(self, who: str, text: str) -> None:
        self.chat_view.appendPlainText(f"{who}: {text.strip()}\n")
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())
        # written straight through: closing FreeCAD must not lose the thread
        if self._project is not None:
            try:
                self._project.add_chat(who, text)
                self._project.save()
            except Exception:  # noqa: BLE001
                pass

    def _chat_reset(self) -> None:
        self._chat.reset()
        self.chat_view.clear()
        self.progress_label.setText("Dialogverlauf zurückgesetzt.")

    def _start_elapsed(self, prefix: str, setter=None) -> None:
        """Show a running second count while the model works."""
        self._elapsed_prefix = prefix
        self._elapsed_setter = setter or self.progress_label.setText
        self._elapsed_s = 0
        timer = getattr(self, "_elapsed_timer", None)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setInterval(1000)
            timer.timeout.connect(self._tick_elapsed)
            self._elapsed_timer = timer
        self._elapsed_setter(prefix)
        timer.start()

    def _tick_elapsed(self) -> None:
        self._elapsed_s += 1
        self._elapsed_setter("%s (%d s)" % (self._elapsed_prefix, self._elapsed_s))

    def _stop_elapsed(self) -> None:
        timer = getattr(self, "_elapsed_timer", None)
        if timer is not None:
            timer.stop()

    def _chat_busy(self, busy: bool) -> None:
        self.chat_send_btn.setEnabled(not busy)
        self.chat_input.setEnabled(not busy)
        self.chat_reset_btn.setEnabled(not busy)
        line = _toolbar_input()
        if line is not None:
            line.setEnabled(not busy)
            line.setPlaceholderText(
                "Der Agent arbeitet …" if busy else
                "Anweisung an TextToGeometry – z. B. „neues "
                "Zylinderkopfprojekt“ (Enter)")

    def _chat_send(self) -> None:
        msg = self.chat_input.toPlainText().strip()
        if not msg:
            return
        if self._chat_worker is not None and self._chat_worker.isRunning():
            return
        try:
            cfg = self._api_config()
            pi = None
            if cfg.kind == "pi":
                pi = T2GCore.find_pi_binary()
            elif cfg.kind == "ollama" and not T2GCore.ollama_running(cfg.base_url):
                raise T2GCore.BackendError(
                    f"Ollama unter {cfg.base_url} nicht erreichbar – "
                    "Tab „Backend“ → „Ollama starten“.")
        except Exception as e:  # noqa: BLE001
            self._chat_append("Fehler", str(e))
            self.progress_label.setText(str(e))
            return

        self._chat_refresh_context()
        self._chat_append("Du", msg)
        self.chat_input.clear()
        self._chat_cfg, self._chat_pi = cfg, pi

        if not self.chat_agent_mode.isChecked():
            doc = _active_doc()
            ctx = T2GCore.describe_document(_doc_objects(doc), _selection_names())
            prompt = self._chat.build_prompt(msg, ctx)
            self._chat.add_user(msg)
            self._chat_busy(True)
            self._start_elapsed("Modell denkt nach …")
            self._chat_worker = _ChatWorker(prompt, cfg, pi, parent=None)
            self._chat_worker.done.connect(self._chat_reply)
            self._chat_worker.start()
            return

        run = self._agent_run
        if run is not None and run.waiting:
            # the user is answering a pending question
            run.waiting = ""
            run.answered = msg
            run.note("benutzer", msg)
            self._agent_step()
            return
        run = self._agent_run
        if run is not None and not run.finished and run.transcript:
            # follow-up in the same conversation: keep what was already said
            run.goal = msg
            run.step = 0
            run.max_steps = self.chat_steps.value()
            run.finished = False
            run.stop_requested = False
            run.did_work = False
            run.answered = ""
            run.note("benutzer", msg)
            self._agent_step()
            return
        self._agent_run = T2GAgent.AgentRun(goal=msg,
                                            max_steps=self.chat_steps.value())
        self._agent_run.answered = ""
        self._agent_run.solids_at_start = self._doc_solid_count()
        if self._project is not None:
            # after a restart the thread continues where it left off
            self._agent_run.summary = self._project.chat_summary
            for role, txt in self._project.chat_transcript(12):
                kind = ("benutzer" if role.lower().startswith("du")
                        else "system" if role.lower().startswith(("system",
                                                                  "fehler"))
                        else "agent")
                self._agent_run.note(kind, txt)
        self._agent_run.note("benutzer", msg)
        self._agent_step()

    def _chat_reply(self, payload: dict) -> None:
        self._stop_elapsed()
        self._show_thinking(payload)
        self._chat_busy(False)
        err = payload.get("error")
        if err:
            self._chat_append("Fehler", err)
            self.progress_label.setText("Dialog-Fehler: " + err)
            return

        if payload.get("kind") == "question":
            q = payload["text"]
            self._chat.pending_question = q
            self._chat.add_assistant("(Rückfrage) " + q)
            self._chat_append("Modell fragt", q)
            self.progress_label.setText("Rückfrage – bitte antworten.")
            self.chat_input.setFocus()
            return

        code = payload["text"]
        self._chat.pending_question = None
        self._chat.add_assistant(code)
        try:
            report = self._run_chat_code(code)
        except Exception as e:  # noqa: BLE001
            self._chat_append("Fehler", str(e))
            self.log_edit.appendPlainText("Code war:\n" + code)
            self.progress_label.setText("Ausführung fehlgeschlagen: " + str(e))
            return
        self._chat_append("Modell", report)
        self.log_edit.appendPlainText("--- ausgeführter Code ---\n" + code)
        self.progress_label.setText(report.splitlines()[0] if report else "Fertig.")
        self._chat_refresh_context()

    # ---- what the agent is allowed to do ----------------------------------

    def _agent_registry(self) -> "T2GAgent.ActionRegistry":
        reg = T2GAgent.ActionRegistry()
        r = reg.register
        r("projekt_anlegen", self._act_projekt, "Titel")
        r("auftrag", self._act_auftrag, "<Freitext, was gebaut wird>")
        r("recherche", self._act_recherche, "Suchbegriff; wiki|web|beides")
        r("parameter", self._act_parameter,
          "name;Label;Einheit;Wert oder leer;min;max")
        r("kriterium", self._act_kriterium, "name;Bedeutung")
        r("skill_bedarf", self._act_skill_bedarf, "name;Zweck")
        r("werkzeug_bedarf", self._act_werkzeug_bedarf, "name;Zweck")
        r("abhaengigkeit", self._act_abhaengigkeit,
          "Quelle;Ziel;nutzt|abgeleitet|passt_an;Anmerkung")
        r("skills_kopieren", self._act_skills_kopieren, "(ohne Argumente)")
        r("paarvergleich", self._act_paarvergleich,
          "KriteriumA;KriteriumB;Wert (9,7,5,3,1,1/3,1/5,1/7,1/9)")
        r("agent_d", self._act_agent_d, "(ohne Argumente) schreibt agent.d")
        r("makro", self._act_makro, "Name eines FreeCAD-Makros")
        r("befehl", self._act_befehl,
          "FreeCAD-Befehl auslösen, z. B. FCGear_InvoluteGear")
        r("werkzeug_aufrufen", self._act_werkzeug_aufrufen,
          "modul.funktion;arg=wert  (Python-Werkzeug)")
        r("verbindungen", self._act_verbindungen,
          "(ohne Argumente) Verbindungen im Dokument erkennen")
        r("baugruppe", self._act_baugruppe,
          "Name;Teil1;Teil2;…  legt die Baugruppe samt Platzhaltern an")
        r("skill_bauen", self._act_skill_bauen, "name;param=wert;param=wert")
        r("skill_lernen", lambda a: "", "name  (dauert Minuten)")
        r("werkzeug_erzeugen", lambda a: "", "name  (dauert Minuten)")
        r("skill_verfeinern", lambda a: "", "name;Auftrag  (dauert Minuten)")
        return reg

    def _act_projekt(self, action) -> str:
        title = action.arg(0)
        if not title:
            raise T2GProject.ProjectError("Kein Titel angegeben.")
        before = self._project.path if self._project else None
        p = self._open_or_create_project(title)
        msg = ("Projekt geöffnet: " if p.path == before else "Projekt angelegt: ")
        return msg + p.path

    def _act_auftrag(self, action) -> str:
        p = self._prj_require()
        p.brief = "; ".join(action.args) if action.args else ""
        p.save()
        return "Auftrag notiert (%d Zeichen)." % len(p.brief)

    def _act_recherche(self, action) -> str:
        # handled asynchronously via _LONG_ACTIONS / _agent_job_research
        return "wird im Hintergrund ausgeführt"

    def _act_parameter(self, action) -> str:
        p = self._prj_require()
        rows = T2GCore.parse_param_lines(";".join(action.args))
        if not rows:
            raise T2GProject.ProjectError(
                "Zeile nicht lesbar: erwartet name;Label;Einheit;Wert;min;max")
        pp = T2GProject.param_from_row(rows[0])
        # "leer" or "?" means: still open, do not invent a value
        if len(action.args) > 3 and action.arg(3).strip().lower() in (
                "", "leer", "offen", "?", "-"):
            pp.value = None
        p.set_param(pp)
        p.save()
        return "Parameter %s = %s" % (pp.name,
                                      "offen" if pp.value is None else pp.value)

    def _act_kriterium(self, action) -> str:
        p = self._prj_require()
        name = action.arg(0)
        if not name:
            raise T2GProject.ProjectError("Kein Kriterienname.")
        crit = [c for c in p.criteria if c["name"] != name]
        crit.append({"name": name, "description": action.arg(1)})
        p.set_criteria(crit)
        p.save()
        return "Kriterium %s (%d insgesamt)" % (name, len(p.criteria))

    def _act_skill_bedarf(self, action) -> str:
        p = self._prj_require()
        name = T2GProject.slugify(action.arg(0), fallback="bauteil")
        if not any(x.name == name for x in p.skills):
            p.skills.append(T2GProject.SkillNeed(name=name,
                                                 description=action.arg(1)))
        p.save()
        self._prj_show_skill_status()
        return "Skill-Bedarf %s (%d insgesamt)" % (name, len(p.skills))

    def _act_werkzeug_bedarf(self, action) -> str:
        p = self._prj_require()
        name = T2GProject.slugify(action.arg(0), fallback="werkzeug")
        if not any(t["name"] == name for t in p.tools):
            p.tools.append({"name": name, "purpose": action.arg(1), "file": ""})
        p.save()
        self._prj_tool_refresh()
        return "Werkzeug-Bedarf %s (%d insgesamt)" % (name, len(p.tools))

    def _act_abhaengigkeit(self, action) -> str:
        p = self._prj_require()
        src, dst = action.arg(0), action.arg(1)
        kind = (action.arg(2, "nutzt") or "nutzt").lower()
        if not src or not dst:
            raise T2GProject.ProjectError("Quelle oder Ziel fehlt.")
        known_params = {x.name for x in p.params}
        known_skills = {x.name for x in p.skills}

        def _node(name: str, prefer: str) -> str:
            if name in known_params:
                return T2GProject.pnode(name)
            if name in known_skills:
                return T2GProject.snode(name)
            return (T2GProject.pnode if prefer == "p" else T2GProject.snode)(name)

        if kind == "abgeleitet":
            a, b = _node(src, "p"), _node(dst, "p")
        elif kind == "passt_an":
            a, b = _node(src, "s"), _node(dst, "s")
        else:
            kind = "nutzt"
            a, b = _node(src, "p"), _node(dst, "s")
        p.graph.add(a, b, kind, action.arg(3))
        p.save()
        hinweis = ""
        ziel = T2GProject.node_label(b)
        if b.startswith("s:") and ziel not in known_skills:
            # linking nozzle parameters to an unrelated existing skill is a
            # mistake worth naming, not silently recording
            hinweis = (" — Achtung: „%s“ gehört nicht zu diesem Projekt "
                       "(vorhanden: %s). Falls gemeint war, ein neues Bauteil "
                       "zu verknüpfen, erst `skill_bedarf: %s;<Zweck>`."
                       % (ziel, ", ".join(sorted(known_skills)) or "keine",
                          ziel))
        return "%s -> %s (%s), %d Kante(n)%s" % (
            T2GProject.node_label(a), ziel, kind, len(p.graph.edges), hinweis)

    def _act_skills_kopieren(self, action) -> str:
        self._prj_copy_skills()
        return self.prj_status.text()

    def _act_paarvergleich(self, action) -> str:
        p = self._prj_require()
        names = list(p.matrix.criteria)
        a, b = action.arg(0), action.arg(1)
        val = T2GCore._parse_ratio(action.arg(2, "1"))
        if a not in names or b not in names:
            raise T2GProject.ProjectError(
                "Unbekanntes Kriterium (%r/%r); vorhanden: %s"
                % (a, b, ", ".join(names) or "keine"))
        if val is None:
            raise T2GProject.ProjectError("Wert nicht lesbar: %r" % action.arg(2))
        p.matrix.set_pair(names.index(a), names.index(b), val)
        p.save()
        self._prj_rebuild_pairs()
        offen = len(p.matrix.missing_pairs())
        return "%s vs. %s = %.3g (noch %d Paar(e) offen)" % (a, b, val, offen)

    def _act_agent_d(self, action) -> str:
        p = self._prj_require()
        files = p.write_agent_d()
        p.write_matrix_csv()
        p.save()
        return "agent.d geschrieben: " + ", ".join(
            os.path.basename(f) for f in files)

    def _act_baugruppe(self, action) -> str:
        """Create the assembly with one placeholder per part, right away.

        The structure should exist before the parts do: the skills grow into
        it later, and the project immediately knows what is still missing.
        """
        name = action.arg(0)
        teile = [t for t in action.args[1:] if t.strip()]
        if not name:
            raise T2GProject.ProjectError("Kein Name für die Baugruppe.")
        if not teile:
            raise T2GProject.ProjectError(
                "Keine Bauteile genannt (baugruppe: Name;Teil1;Teil2;…).")
        doc = _active_doc(create=True)
        safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in name)
        try:
            asm = doc.addObject("Assembly::AssemblyObject", safe or "Baugruppe")
        except Exception:  # noqa: BLE001  -- Assembly workbench missing
            asm = doc.addObject("App::Part", safe or "Baugruppe")
        asm.Label = name
        angelegt = []
        for teil in teile:
            slug = T2GProject.slugify(teil, fallback="bauteil")
            holder = doc.addObject("App::Part", slug)
            holder.Label = teil
            asm.addObject(holder)
            angelegt.append(teil)
            if self._project is not None:
                if not any(x.name == slug for x in self._project.skills):
                    self._project.skills.append(T2GProject.SkillNeed(
                        name=slug, description="Teil der Baugruppe " + name))
        doc.recompute()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:  # noqa: BLE001
            pass
        if self._project is not None:
            self._project.save()
            self._prj_show_skill_status()
        return ("Baugruppe „%s“ mit %d Platzhalter(n) im Dokument: %s. "
                "Jedes Teil wird gefüllt, sobald sein Skill steht."
                % (name, len(angelegt), ", ".join(angelegt)))

    def _external(self, name: str):
        if not getattr(self, "_tools", None):
            self._tools_scan()
        tool = T2GTools.find_tool(self._tools, name)
        if tool is None:
            vorhanden = ", ".join(sorted({t.name for t in self._tools})[:15])
            raise T2GTools.ToolError(
                "Kein Werkzeug %r. Vorhanden u. a.: %s" % (name, vorhanden))
        return tool

    def _act_makro(self, action) -> str:
        tool = self._external(action.arg(0))
        if tool.kind != "makro":
            raise T2GTools.ToolError("%s ist kein Makro." % tool.name)
        return self.run_external_tool(tool)

    def _act_befehl(self, action) -> str:
        name = action.arg(0)
        try:
            tool = self._external(name)
        except T2GTools.ToolError:
            # a command FreeCAD knows but no add-on folder advertised
            tool = T2GTools.ExternalTool(kind="befehl", name=name, command=name)
        return self.run_external_tool(tool)

    def _act_werkzeug_aufrufen(self, action) -> str:
        tool = self._external(action.arg(0))
        if tool.kind != "python":
            raise T2GTools.ToolError(
                "%s ist kein aufrufbares Python-Werkzeug." % tool.name)
        return self.run_external_tool(tool, ";".join(action.args[1:]))

    def _act_verbindungen(self, action) -> str:
        """Run the connection_detection add-on over the open document."""
        doc = _active_doc()
        if doc is None:
            raise T2GProject.ProjectError("Kein Dokument offen.")
        fehler = []
        for pfad in self._extra_tool_paths() + [
                os.path.expanduser("~/ai-workspace/connection_detection")]:
            try:
                mod = T2GTools.import_from_path("connection_detection", pfad)
            except Exception as e:  # noqa: BLE001
                fehler.append("%s: %s" % (pfad, e))
                continue
            graph = mod.detect_connections_in_document(doc)
            teile = len(getattr(graph, "parts", []) or [])
            kandidaten = list(getattr(graph, "candidates", []) or [])
            if self._project is not None:
                self._project.notes.append(
                    "Prüfung Verbindungen: %d Teil(e), %d Kandidat(en)"
                    % (teile, len(kandidaten)))
                self._project.save()
                self._refresh_start()
            zeilen = []
            for k in kandidaten[:10]:
                zeilen.append("  %s" % str(k)[:120])
            return ("Verbindungsprüfung: %d Teil(e), %d Kandidat(en)%s"
                    % (teile, len(kandidaten),
                       ("\n" + "\n".join(zeilen)) if zeilen else ""))
        raise T2GTools.ToolError(
            "connection_detection nicht gefunden. Ordner im Tab „Werkzeuge“ "
            "über „Python-Ordner hinzufügen …“ einbinden. Versuche: "
            + "; ".join(fehler))

    def _act_skill_bauen(self, action) -> str:
        name = action.arg(0)
        eng = self._skills_engine(reload=True)
        values = {}
        for raw in action.args[1:]:
            if "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            try:
                values[k.strip()] = float(v.strip().replace(",", "."))
            except ValueError:
                values[k.strip()] = v.strip()
        # project parameters fill in whatever the agent did not name
        if self._project is not None:
            for pname, pval in self._project.param_values().items():
                values.setdefault(pname, pval)
        loaded = eng.registry.get(name)
        known = {q.name for q in loaded.definition.params}
        values = {k: v for k, v in values.items() if k in known}
        shapes, vals, problems = eng.build(name, values)
        self._add_skill_shapes(name, shapes, problems)
        if self._project is not None:
            for sneed in self._project.skills:
                if sneed.name == name and sneed.status in ("offen", "zu pruefen"):
                    sneed.status = "gebaut"
            self._project.save()
        return "%s gebaut: %s%s" % (
            name, self._describe_build(shapes),
            (" · Hinweise: " + "; ".join(problems)) if problems else "")

    # ------------------------------------------------------------- agent --

    def _job_finished(self, ok: bool, text: str) -> bool:
        """Report a long job back to the agent loop, if one is waiting."""
        cb = getattr(self, "_agent_job_done", None)
        if cb is None:
            return False
        cb(ok, text)
        return True

    def _agent_stop(self) -> None:
        if self._agent_run is not None:
            self._agent_run.stop_requested = True
            self._chat_append("System", "Stop angefordert – der Agent hält nach "
                                        "dem laufenden Schritt an.")

    def _agent_busy(self, busy: bool) -> None:
        self._chat_busy(busy)
        self.chat_stop_btn.setEnabled(busy)

    def _agent_step(self) -> None:
        try:
            self._agent_step_inner()
        except Exception as e:  # noqa: BLE001
            self._agent_busy(False)
            self._chat_append("Fehler", "Agentenschritt: %s" % e)
            FreeCAD.Console.PrintError("TextToGeometry Agent: %s\n" % e)

    def _agent_step_inner(self) -> None:
        run = self._agent_run
        if run is None:
            return
        if run.stop_requested:
            return self._agent_finish("Angehalten.")
        if run.needs_compression():
            return self._agent_compress()
        if run.budget_left() <= 0:
            return self._agent_finish(
                "Schrittbudget aufgebraucht – mit einer neuen Anweisung "
                "weitermachen oder oben mehr Schritte erlauben.")
        doc = _active_doc()
        ctx = T2GCore.describe_document(_doc_objects(doc), _selection_names())
        pblock = self._project.as_prompt_block() if self._project else ""
        skills = self._skills_engine().registry.names()
        T2GPanel._known_skills_hint = list(skills)
        if not getattr(self, "_tools", None):
            try:
                self._tools_scan()
            except Exception:  # noqa: BLE001
                pass
        werkzeuge = T2GTools.describe_tools(
            [t for t in (self._tools or []) if t.kind != "addon"], limit=25)
        prompt = T2GAgent.build_agent_prompt(
            run, pblock, ctx, skills=skills,
            answered=getattr(run, "answered", ""), tools=werkzeuge)
        run.answered = ""
        self._agent_busy(True)
        self._start_elapsed("Schritt %d/%d – Modell denkt …"
                            % (run.step + 1, run.max_steps))
        system = T2GCore.build_agent_system_prompt(
            self._agent_registry().help_block())
        self._chat_worker = _TextWorker(prompt, system, self._chat_cfg,
                                        self._chat_pi, tag="agent")
        self._chat_worker.done.connect(self._agent_reply)
        self._chat_worker.start()

    def _agent_compress(self) -> None:
        """Condense the older conversation instead of cutting it off.

        Plain truncation loses precisely what matters later -- the list of
        parts named ten turns ago. So the old half is summarised first.
        """
        run = self._agent_run
        text, keep = run.split_for_compression()
        if not text.strip():
            run.transcript = keep
            return self._agent_step_inner()
        self._agent_busy(True)
        self._start_elapsed("Fasse den Verlauf zusammen …")
        prompt = T2GCore.build_summary_prompt(text, run.summary)
        # condensing is clerical work -- no need to ponder it
        self._chat_worker = _TextWorker(prompt, T2GCore.SUMMARY_PROMPT,
                                        T2GCore.with_thinking(self._chat_cfg, "off"),
                                        self._chat_pi, tag="zusammenfassung")
        self._chat_worker.done.connect(
            lambda payload, keep=keep: self._agent_compress_done(payload, keep))
        self._chat_worker.start()

    def _agent_compress_done(self, payload: dict, keep: list) -> None:
        self._stop_elapsed()
        run = self._agent_run
        if run is None:
            return self._agent_busy(False)
        if payload.get("error") or not (payload.get("text") or "").strip():
            # keep going rather than stall: drop the oldest, lose the least
            run.transcript = keep
            self.log_edit.appendPlainText(
                "Verdichtung fehlgeschlagen: %s" % payload.get("error", "leer"))
        else:
            summary = payload["text"].strip()
            run.apply_summary(summary, keep)
            self._chat_append("System",
                              "Verlauf verdichtet auf %d Zeile(n)."
                              % len(summary.splitlines()))
            self.log_edit.appendPlainText("--- Verdichteter Verlauf ---\n" + summary)
            if self._project is not None:
                self._project.chat_summary = summary
                self._project.save()
        self._agent_step()

    def _show_thinking(self, payload: dict) -> None:
        """Put the model's reasoning where the user can follow it."""
        thinking = (payload.get("thinking") or "").strip()
        if not thinking:
            return
        self.log_edit.appendPlainText("--- Überlegung ---\n" + thinking)
        if self.chat_thinking.isChecked():
            kurz = " ".join(thinking.split())
            self._chat_append("Denkt", kurz[:600]
                              + ("…" if len(kurz) > 600 else ""))

    def _agent_reply(self, payload: dict) -> None:
        self._stop_elapsed()
        self._show_thinking(payload)
        run = self._agent_run
        if run is None:
            self._agent_busy(False)
            return
        run.step += 1
        if payload.get("error"):
            self._agent_busy(False)
            self._chat_append("Fehler", payload["error"])
            return
        try:
            reply = T2GAgent.parse_agent_reply(payload["text"],
                                               T2GCore.parse_param_lines)
        except T2GAgent.AgentError as e:
            run.add_observations([T2GAgent.Observation(
                "antwort", False, "Format nicht erkannt: %s" % e)])
            self.log_edit.appendPlainText("Rohantwort:\n" + payload["text"][:1500])
            if run.should_continue():
                return self._agent_step()
            self._agent_busy(False)
            return self._chat_append("Fehler", str(e))

        if reply.kind == "frage":
            vorige = getattr(run, "last_question", "")
            if vorige and self._same_question(vorige, reply.text) \
                    and run.budget_left() > 0:
                # asked and answered already -- repeating it is the loop the
                # user ran into; push the answer back instead
                antwort = next((t for k, t in reversed(run.transcript)
                                if k == "benutzer"), "")
                run.add_observations([T2GAgent.Observation(
                    "frage", False,
                    "Diese Frage war schon gestellt und ist beantwortet: "
                    "„%s“. Nicht erneut fragen – handle jetzt, notfalls mit "
                    "einer klar benannten Annahme." % antwort[:200])])
                self._chat_append("System",
                                  "Frage wiederholt – verweise auf die Antwort.")
                return self._agent_step()
            run.last_question = reply.text
            run.note("agent", "Rückfrage: " + reply.text)
            self._agent_busy(False)
            self._chat_append("Agent fragt", reply.text)
            self.chat_input.setFocus()
            return
        if reply.kind == "maske":
            run.waiting = "maske"
            run.note("agent", "Eingabemaske: "
                     + ", ".join(str(r[0]) for r in reply.params))
            self._agent_busy(False)
            self._agent_show_mask(reply.params)
            return
        if reply.kind == "fertig":
            # A small model likes to *narrate* the work instead of emitting
            # actions ("Testklotz wurde angelegt." with no block at all).
            # Nothing may end the run that has not actually executed anything.
            if not run.did_work and run.budget_left() > 0:
                run.rejections = getattr(run, "rejections", 0) + 1
                if run.rejections > self._MAX_REJECTIONS:
                    # Nine rounds of "please actually act" helped nobody.
                    vorschlag = self._agent_example(run)
                    self._chat_append(
                        "System",
                        "Der Agent kommt nicht ins Handeln (%d Versuche). "
                        "Ich halte an. Vorschlag – bitte bestätigen oder "
                        "ändern:\n%s" % (run.rejections, vorschlag))
                    return self._agent_finish(
                        "Abgebrochen: keine ausführbare Antwort. "
                        "Schick die Anweisung konkreter, z. B. "
                        "„%s“." % vorschlag.replace("\n", " · "))
                hinweis = (
                    "Es wurde nichts ausgeführt – Prosa bewirkt nichts. "
                    "Antworte mit einem ```aktion-Block, z. B.:\n"
                    "```aktion\n%s\n```" % self._agent_example(run))
                if run.rejections >= 2:
                    hinweis += ("\nAntworte AUSSCHLIESSLICH mit diesem Block, "
                                "ohne einleitenden Satz und ohne Erklärung.")
                run.add_observations([T2GAgent.Observation("fertig", False,
                                                           hinweis)])
                self._chat_append(
                    "System", "Der Agent hat nur beschrieben statt gehandelt "
                              "(%d.) – fordere die Ausführung an."
                              % run.rejections)
                return self._agent_step()
            return self._agent_finish(reply.text)
        if reply.kind == "python":
            try:
                report = self._run_chat_code(reply.text)
                ok, text = True, report
            except Exception as e:  # noqa: BLE001
                ok = False
                text = ("%s — Schick den korrigierten ```python-Block: nur "
                        "Part/FreeCAD/math, Änderungen über add()/replace()."
                        % e)
            self._chat_append("Agent", text)
            run.add_observations([T2GAgent.Observation("dokument", ok, text)])
            run.did_work = run.did_work or ok
            self._chat_refresh_context()
            return self._agent_step() if run.should_continue() else self._agent_busy(False)

        # kind == "aktion"
        reg = self._agent_registry()
        obs, long_job = [], None
        for act in reply.actions:
            if act.name in self._LONG_ACTIONS:
                long_job = act
                break
            o = reg.run(act)
            if not o.ok:
                o.text = self._repair_hint(act, o.text)
            obs.append(o)
            run.did_work = run.did_work or o.ok
            run.note("agent", "%s %s" % (act.name, "OK" if o.ok else "FEHLER"))
            self._chat_append("Agent", o.render())
        run.add_observations(obs)
        self._prj_show()
        if long_job is not None:
            return self._agent_start_job(long_job)
        if run.should_continue():
            return self._agent_step()
        self._agent_busy(False)

    #: Filler that turns "bitte lege eine baugruppe an" into "baugruppe".
    _TITLE_NOISE = {
        "bitte", "mal", "doch", "mir", "uns", "ein", "eine", "einen", "einem",
        "der", "die", "das", "den", "dem", "neues", "neue", "neuer", "neu",
        "lege", "leg", "legen", "mach", "mache", "machen", "erstelle",
        "erstellen", "baue", "bau", "bauen", "an", "auf", "los", "starte",
        "starten", "anlegen", "erzeuge", "erzeugen", "und", "mit", "fuer",
        "für", "von", "zum", "zur", "im", "in", "projekt",
    }

    @classmethod
    def _clean_title(cls, text: str, fallback: str = "Projekt") -> str:
        """A usable project name from a spoken instruction."""
        words = re.findall(r"[A-Za-zÄÖÜäöüß0-9_]+", text or "")
        kept = [w for w in words
                if w.lower() not in cls._TITLE_NOISE and not w.isdigit()]
        # "6 modellen" and friends add nothing to a name
        kept = [w for w in kept if w.lower() not in ("modellen", "modelle",
                                                     "modell", "teilen",
                                                     "teile", "stück")]
        title = " ".join(kept[:4]).strip()
        return title if len(title) >= 3 else fallback

    @staticmethod
    def _same_question(a: str, b: str) -> bool:
        """Two questions that differ only in wording count as the same."""
        import difflib

        def norm(t):
            return " ".join(re.findall(r"[a-zäöüß0-9]+", (t or "").lower()))
        x, y = norm(a), norm(b)
        if not x or not y:
            return False
        return difflib.SequenceMatcher(None, x, y).ratio() >= 0.75

    @staticmethod
    def _agent_example(run) -> str:
        """A ready-to-copy action block built from what the user actually said.

        A generic "use an action block" was ignored several rounds in a row;
        showing the concrete line with the user's own words is what got the
        model to act.
        """
        said = " ".join(t for k, t in run.transcript if k == "benutzer")
        titel = T2GPanel._clean_title(run.goal or "")[:48]
        teile = []
        for line in reversed([t for k, t in run.transcript if k == "benutzer"]):
            if "," in line and len(line.split(",")) >= 3:
                teile = [x.strip() for x in line.split(",") if x.strip()]
                break
        # Numbers for a skill that already exists -> build it, do not chat
        zahlen = re.findall(r"(\d+(?:[.,]\d+)?)\s*(mm|grad|°|stk|stück)?",
                            said.lower())
        bekannt = getattr(T2GPanel, "_known_skills_hint", []) or []
        treffer = [k for k in bekannt if k.lower() in said.lower()]
        if treffer and zahlen:
            werte = ";".join("param%d=%s" % (i + 1, z[0].replace(",", "."))
                             for i, z in enumerate(zahlen[:3]))
            return ("skill_bauen: %s;%s   (Parameternamen des Skills "
                    "einsetzen)" % (treffer[0], werte))
        lines = ["projekt_anlegen: " + titel]
        if teile:
            lines.append("baugruppe: " + titel + ";" + ";".join(teile[:12]))
        elif any(w in said.lower() for w in ("bohrung", "kanal", "ventil",
                                             "kopf", "motor", "bruecke",
                                             "brücke")):
            lines.append("recherche: " + titel + "; beides")
        return "\n".join(lines)

    @staticmethod
    def _repair_hint(action, fehler: str) -> str:
        """Turn a failure into an instruction the model can act on."""
        if action.name == "skill_bauen":
            return (fehler + " — Korrigiere das: entweder die Parameter "
                    "anpassen (`skill_bauen: name;param=wert`) oder den Skill "
                    "selbst reparieren (`skill_verfeinern: name;<was der "
                    "Fehler sagt>`).")
        if action.name in ("baugruppe", "abhaengigkeit", "parameter"):
            return fehler + " — Argumente prüfen und die Zeile berichtigt "\
                            "erneut senden."
        return fehler

    @staticmethod
    def _doc_solid_count() -> int:
        doc = _active_doc()
        if doc is None:
            return 0
        n = 0
        for o in doc.Objects:
            shp = getattr(o, "Shape", None)
            if shp is not None and not shp.isNull() and shp.Solids:
                n += 1
        return n

    _BUILD_WORDS = ("angelegt", "gebaut", "erzeugt", "erstellt", "steht",
                    "hinzugefügt", "eingefügt")

    #: Announcing the next step is not finishing. "Ich lerne ihn jetzt" ended
    #: a run with an empty document and a promise.
    _PROMISE_WORDS = ("ich lerne", "ich baue", "ich erzeuge", "ich erstelle",
                      "ich lege", "ich setze", "ich starte", "werde ich",
                      "als nächstes", "als naechstes", "im nächsten schritt",
                      "im naechsten schritt", "danach baue", "danach lerne")
    _MAX_PROMISES = 2
    #: How often a false "it is built" claim is sent back. Once was not
    #: enough: the second claim slipped through on the same run.
    _MAX_BUILD_CHECKS = 3

    def _agent_finish(self, text: str) -> None:
        run = self._agent_run
        # "Ich lerne den Skill jetzt" is an announcement, not a result.
        low = (text or "").lower()
        if run is not None and run.budget_left() > 0 \
                and getattr(run, "promises", 0) < self._MAX_PROMISES \
                and any(w in low for w in self._PROMISE_WORDS):
            run.promises = getattr(run, "promises", 0) + 1
            run.add_observations([T2GAgent.Observation(
                "fertig", False,
                "Du kündigst an, statt zu handeln. Kündige nichts an – gib "
                "die Aktion JETZT aus, z. B. `skill_lernen: <name>` oder "
                "`skill_bauen: <name>;param=wert`. ```fertig ist erst dran, "
                "wenn es getan ist.")])
            self._chat_append("System",
                              "Ankündigung statt Ausführung – fordere die "
                              "Aktion an.")
            return self._agent_step()
        # Claims geometry but the document did not grow? Say so and let the
        # agent put it right instead of ending on a false note.
        if run is not None and run.budget_left() > 0 \
                and getattr(run, "build_checks", 0) < self._MAX_BUILD_CHECKS \
                and any(w in text.lower() for w in self._BUILD_WORDS) \
                and self._doc_solid_count() <= getattr(run, "solids_at_start", 0):
            run.build_checks = getattr(run, "build_checks", 0) + 1
            run.add_observations([T2GAgent.Observation(
                "pruefung", False,
                "Im Dokument ist kein neuer Körper entstanden, obwohl deine "
                "Antwort das behauptet. Bau es jetzt wirklich: `skill_bauen: "
                "<name>;param=wert` oder einen ```python-Block mit add(). "
                "Schlägt der Code fehl, korrigiere ihn anhand der "
                "Fehlermeldung.")])
            self._chat_append("System",
                              "Nichts gebaut – fordere die Ausführung an.")
            return self._agent_step()
        self._agent_busy(False)
        if run is not None:
            run.finished = True
            run.note("agent", text)
        self._chat_append("Agent", text)
        # What the model says happened, and what actually did -- the two have
        # drifted apart before, so the facts get their own line.
        if run is not None and run.observations:
            ok = [o.action for o in run.observations if o.ok]
            fail = [o.action for o in run.observations if not o.ok]
            teile = []
            if ok:
                teile.append("ausgeführt: " + ", ".join(sorted(set(ok))))
            if fail:
                teile.append("fehlgeschlagen: " + ", ".join(sorted(set(fail))))
            self._chat_append("Tatsächlich", " · ".join(teile) or "nichts")
        self.progress_label.setText("Agent fertig.")
        self._prj_show()
        self._chat_refresh_context()

    # ---- the parameter mask ----------------------------------------------

    def _agent_show_mask(self, params: list) -> None:
        while self.chat_mask_form.count():
            item = self.chat_mask_form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._chat_mask_rows = []
        p = self._project
        for row in params:
            pp = T2GProject.param_from_row(row)
            known = p.param(pp.name) if p is not None else None
            if pp.kind in ("int", "float"):
                w = QDoubleSpinBox()
                w.setDecimals(0 if pp.kind == "int" else 3)
                w.setRange(float(pp.minimum) if pp.minimum is not None else -1e9,
                           float(pp.maximum) if pp.maximum is not None else 1e9)
                start = (known.value if known is not None and known.value is not None
                         else pp.value)
                w.setValue(float(start if start is not None else 0.0))
                if pp.unit and pp.unit != "-":
                    w.setSuffix(" " + pp.unit)
            else:
                w = QLineEdit()
                start = (known.value if known is not None and known.value is not None
                         else pp.value)
                w.setText("" if start is None else str(start))
            label = pp.label + (f" [{pp.unit}]" if pp.unit and pp.unit != "-" else "")
            self.chat_mask_form.addRow(label + ":", w)
            self._chat_mask_rows.append((pp, w))
            if p is not None:
                p.set_param(pp)
        self.chat_mask_hint.setText(
            "%d Angabe(n) – Werte prüfen, dann übernehmen. Sie gelten danach "
            "projektweit." % len(self._chat_mask_rows))
        self.chat_mask_box.setVisible(True)
        self._chat_append("Agent bittet um Angaben",
                          ", ".join(pp.label for pp, _ in self._chat_mask_rows))

    def _agent_mask_submit(self) -> None:
        """Take the filled-in form into the project and let the agent go on."""
        run = self._agent_run
        try:
            answers, specs = {}, {}
            for pp, w in self._chat_mask_rows:
                answers[pp.name] = (w.value() if isinstance(w, QDoubleSpinBox)
                                    else w.text().strip())
                specs[pp.name] = pp
            self.chat_mask_box.setVisible(False)

            parts = []
            for name, value in answers.items():
                unit = specs[name].unit if specs.get(name) else ""
                parts.append(("%s = %s %s" % (name, value, unit)).strip())
            text = ", ".join(parts)

            problems = []
            if self._project is None:
                # The agent asked before creating a project. Make one from the
                # goal rather than leaving the answers in limbo -- they used to
                # pile up in _pending_params and, worse, each new form replaced
                # the previous one.
                title = self._clean_title(
                    (self._agent_run.goal if self._agent_run else ""))
                try:
                    self._project = self._open_or_create_project(title[:60])
                    text += " · Projekt „%s“ angelegt" % self._project.title
                except Exception as e:  # noqa: BLE001
                    pending = list(getattr(self, "_pending_params", []) or [])
                    pending += [(specs[n], answers[n]) for n in answers]
                    self._pending_params = pending
                    text += " (kein Projekt: %s – %d Angabe(n) gemerkt)" % (
                        e, len(pending))
            if self._project is not None:
                for name in answers:
                    self._project.set_param(specs[name])
                problems = self._project.answer_mask(answers)
                affected = self._project.mark_affected(list(answers))
                self._project.write_agent_d()
                self._project.save()
                self._prj_show()
                if affected:
                    text += " · betroffen: " + ", ".join(affected)
            if problems:
                text += " · Hinweise: " + "; ".join(problems)
            self._chat_append("Du", text)
        except Exception as e:  # noqa: BLE001
            # never leave the loop hanging on a UI error
            self._chat_append("Fehler", "Maske: %s" % e)
            FreeCAD.Console.PrintError("TextToGeometry Maske: %s\n" % e)
            text, problems = "Maske konnte nicht übernommen werden: %s" % e, [str(e)]
        if run is None:
            return
        run.waiting = ""
        run.answered = text
        run.note("benutzer", text)
        run.add_observations([T2GAgent.Observation("maske", not problems, text)])
        # The user filling in a form is input, not the agent doing something --
        # counting it as work let a purely narrated "fertig" through afterwards.
        self._agent_step()

    def _flush_pending_params(self) -> str:
        """Apply answers given before the project existed."""
        pending = getattr(self, "_pending_params", None)
        if not pending or self._project is None:
            return ""
        for spec, value in pending:
            self._project.set_param(spec)
            self._project.answer_mask({spec.name: value})
        self._pending_params = []
        self._project.save()
        return " · %d vorab beantwortete Angabe(n) übernommen" % len(pending)

    # ---- long-running jobs started by the agent ---------------------------

    #: How often a claimed-but-empty answer is sent back before giving up.
    _MAX_REJECTIONS = 3

    #: Actions that must not run inline: they reach the network or start
    #: another model call, and the GUI thread would freeze meanwhile.
    _LONG_ACTIONS = ("skill_lernen", "werkzeug_erzeugen", "skill_verfeinern",
                     "recherche")

    def _agent_start_job(self, action) -> None:
        """Hand a minutes-long job to the existing machinery and resume after."""
        run = self._agent_run
        name = action.arg(0)
        kind = action.name
        self._chat_append("Agent", "startet %s: %s (dauert einige Minuten)"
                          % (kind, name))

        def _done(ok: bool, text: str) -> None:
            self._agent_job_done = None
            run.add_observations([T2GAgent.Observation(kind, ok, text)])
            run.did_work = run.did_work or ok
            self._chat_append("Agent", ("OK " if ok else "FEHLER ") + text)
            self._prj_show()
            if run.should_continue():
                self._agent_step()
            else:
                self._agent_busy(False)

        self._agent_job_done = _done
        try:
            if kind == "skill_lernen":
                self._agent_job_learn(name, action.arg(1))
            elif kind == "werkzeug_erzeugen":
                self._agent_job_tool(name)
            elif kind == "recherche":
                self._agent_job_research(name, action.arg(1, "beides"))
            else:
                self._agent_job_refine(name, action.arg(1))
        except Exception as e:  # noqa: BLE001
            self._agent_job_done = None
            _done(False, str(e))

    def _agent_job_research(self, query: str, mode: str = "beides") -> None:
        """Web access in a thread; the document is untouched either way."""
        if not query:
            raise T2GCore.T2GError("Kein Suchbegriff.")
        mode = (mode or "beides").lower()
        self._start_elapsed("Recherchiere „%s“ …" % query[:40])
        self._spawn(lambda: T2GCore.research_topic(
            query, use_wikipedia=mode in ("wiki", "beides"),
            use_web=mode in ("web", "beides"), web_pages=2),
            "recherche",
            lambda payload, q=query: self._agent_research_done(payload, q))

    def _agent_research_done(self, payload: dict, query: str) -> None:
        self._stop_elapsed()
        cb = getattr(self, "_agent_job_done", None)
        if payload.get("error"):
            return cb(False, "Recherche fehlgeschlagen: " + payload["error"]) \
                if cb else None
        res = payload["result"]
        if self._project is not None:
            self._project.notes.append(
                "Recherche %r: %s" % (query,
                                      ", ".join(u for _, u in res.sources)
                                      or "ohne Treffer"))
            self._project.save()
        self.log_edit.appendPlainText(
            "Recherche %r:\n%s" % (query, res.text[:3000]))
        if not res.text.strip():
            text = "keine Treffer (%s)" % ("; ".join(res.errors) or "leer")
            ok = False
        else:
            quellen = ", ".join("%s <%s>" % (t, u) for t, u in res.sources)
            text = "%d Quelle(n): %s\n%s" % (len(res.sources), quellen,
                                              res.text[:1800])
            ok = True
        if cb:
            cb(ok, text)

    def _agent_job_learn(self, name: str, hint: str = "") -> None:
        p = self._project
        need = None
        if p is not None:
            need = next((x for x in p.skills if x.name == name), None)
        self.lrn_topic.setText(name)
        notes = hint or (need.description if need else "")
        if p is not None:
            notes = (notes + "\n\n" if notes else "") + p.as_prompt_block()
        self.lrn_notes.setPlainText(notes)
        self.lrn_web.setChecked(False)
        self._learn_analyse()

    def _agent_job_tool(self, name: str) -> None:
        idx = self.prj_tool_combo.findData(name)
        if idx < 0:
            raise T2GProject.ProjectError(
                "Werkzeug %r ist im Projekt nicht geplant." % name)
        self.prj_tool_combo.setCurrentIndex(idx)
        self._prj_tool_generate()

    def _agent_job_refine(self, name: str, goal: str = "") -> None:
        idx = self.skill_combo.findText(name)
        if idx < 0:
            raise T2GSkills.SkillError("Skill %r ist nicht geladen." % name)
        self.skill_combo.setCurrentIndex(idx)
        self.ref_goal.setPlainText(goal)
        self.ref_use_project.setChecked(self._project is not None)
        self._skill_refine()

    def _run_chat_code(self, code: str) -> str:
        """Execute model code against the document and apply what it asked for."""
        doc = _active_doc(create=True)
        objs = _doc_objects(doc)

        def _lookup(name: str):
            return _find_object(doc, name).Shape.copy()

        rec = T2GCore.OpRecorder(objs, _selection_names(), shape_lookup=_lookup)
        T2GCore.exec_chat_code(code, rec)
        if not rec.ops and not rec.notes:
            return ("Der Code hat nichts am Dokument verändert "
                    "(kein add/replace/part/assembly/fem).")
        lines = self._apply_ops(doc, rec)
        return "\n".join(lines)

    # ---- applying the recorded operations (GUI thread only) --------------

    def _apply_ops(self, doc, rec) -> list:
        lines: list = []
        for op in rec.ops:
            kind = op.get("op")
            try:
                if kind == "add":
                    lines.append(self._op_add(doc, op))
                elif kind == "replace":
                    lines.append(self._op_replace(doc, op))
                elif kind == "part":
                    lines.append(self._op_container(doc, op, "App::Part"))
                elif kind == "assembly":
                    lines.append(self._op_container(doc, op, "Assembly::AssemblyObject"))
                elif kind == "fem":
                    lines.extend(self._op_fem(doc, op))
                else:
                    lines.append(f"Unbekannte Operation: {kind}")
            except Exception as e:  # noqa: BLE001
                lines.append(f"{kind} fehlgeschlagen: {e}")
        doc.recompute()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:  # noqa: BLE001
            pass
        lines.extend(rec.notes)
        return lines

    def _op_add(self, doc, op) -> str:
        name = (op.get("name") or "T2G_Objekt").strip()
        safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in name) or "T2G"
        obj = doc.addObject("Part::Feature", safe)
        obj.Shape = op["shape"]
        obj.Label = op.get("label") or name
        return f"Neues Bauteil „{obj.Label}“ ({obj.Name}) angelegt."

    def _op_replace(self, doc, op) -> str:
        obj = _find_object(doc, op["name"])
        old = float(getattr(obj.Shape, "Volume", 0.0) or 0.0)
        obj.Shape = op["shape"]
        new = float(obj.Shape.Volume)
        delta = old - new
        how = ("Material abgetragen: %.1f mm^3" % delta if delta > 0 else
               "Material ergänzt: %.1f mm^3" % -delta if delta < 0 else
               "Volumen unverändert")
        return f"„{obj.Label}“ geändert ({how}, jetzt {new:.1f} mm^3)."

    def _op_container(self, doc, op, type_id: str) -> str:
        name = (op.get("name") or "Baugruppe").strip()
        safe = "".join(c if (c.isalnum() or c == "_") else "_" for c in name) or "Gruppe"
        members = op.get("members") or []
        if not members:
            raise T2GCore.T2GError("Keine Bauteile angegeben.")
        try:
            box = doc.addObject(type_id, safe)
        except Exception as e:  # noqa: BLE001  -- Assembly WB may be absent
            if type_id != "App::Part":
                box = doc.addObject("App::Part", safe)
                type_id = "App::Part (Assembly nicht verfügbar: %s)" % e
            else:
                raise
        box.Label = name
        added = []
        for m in members:
            obj = _find_object(doc, m)
            # A Link keeps the original object in place and allows the same
            # part to appear more than once.
            link = doc.addObject("App::Link", obj.Name + "_Link")
            link.LinkedObject = obj
            link.Label = obj.Label
            box.addObject(link)
            added.append(obj.Label)
        what = "Baugruppe" if "Assembly" in type_id else "Bauteil-Gruppe"
        return f"{what} „{name}“ mit {len(added)} Teil(en): {', '.join(added)}."

    def _op_fem(self, doc, op) -> list:
        import ObjectsFem

        target = _find_object(doc, op["target"])
        shp = getattr(target, "Shape", None)
        if shp is None or shp.isNull():
            raise T2GCore.T2GError(f"{op['target']!r} hat keine Geometrie.")
        lines = []
        name = op.get("name") or "Festigkeitsanalyse"

        analysis = ObjectsFem.makeAnalysis(doc, name)
        solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
        analysis.addObject(solver)

        key = str(op.get("material") or "stahl").strip().lower()
        matname, e_mod, nu, rho = _FEM_MATERIALS.get(key, _FEM_MATERIALS["stahl"])
        mat = ObjectsFem.makeMaterialSolid(doc, "Werkstoff")
        md = mat.Material
        md["Name"] = matname
        md["YoungsModulus"] = "%g MPa" % e_mod
        md["PoissonRatio"] = "%g" % nu
        md["Density"] = "%g kg/m^3" % rho
        mat.Material = md
        analysis.addObject(mat)

        fixed_side = op.get("fixed") or "zmin"
        faces = _faces_on_side(shp, fixed_side)
        fix = ObjectsFem.makeConstraintFixed(doc, "Fixierung")
        fix.References = [(target, f) for f in faces]
        analysis.addObject(fix)
        lines.append(f"Analyse „{name}“ auf {target.Label}: fest auf {fixed_side} "
                     f"({len(faces)} Fläche(n)), Werkstoff {matname}.")

        force_n = float(op.get("force_n") or 0.0)
        load_side = op.get("load")
        if load_side and force_n:
            lfaces = _faces_on_side(shp, load_side)
            frc = ObjectsFem.makeConstraintForce(doc, "Kraft")
            frc.References = [(target, f) for f in lfaces]
            frc.Force = "%g N" % force_n
            frc.Reversed = True
            analysis.addObject(frc)
            lines.append(f"Last: {force_n:g} N auf {load_side} "
                         f"({len(lfaces)} Fläche(n)).")
        else:
            lines.append("Keine Last gesetzt – nur Aufbau und Vernetzung.")

        mesh = ObjectsFem.makeMeshGmsh(doc, "Netz")
        mesh.Shape = target
        bb = shp.BoundBox
        clen = max(bb.XLength, bb.YLength, bb.ZLength) / 12.0
        if clen > 0:
            mesh.CharacteristicLengthMax = FreeCAD.Units.Quantity("%g mm" % clen)
        analysis.addObject(mesh)
        doc.recompute()

        self.progress_label.setText("Vernetze mit gmsh …")
        FreeCADGui.updateGui()
        if not shutil.which("gmsh"):
            lines.append("gmsh nicht gefunden – Netz nicht erzeugt "
                         "(Installation: sudo apt install gmsh).")
            return lines
        try:
            from femmesh.gmshtools import GmshTools
            GmshTools(mesh).create_mesh()
            fm = mesh.FemMesh
            lines.append("Netz: %d Knoten, %d Volumenelemente."
                         % (fm.NodeCount, fm.VolumeCount))
        except Exception as e:  # noqa: BLE001
            lines.append(f"Vernetzung fehlgeschlagen: {e}")
            return lines

        lines.extend(self._run_ccx(analysis, solver))
        return lines

    #: Where a CalculiX binary usually sits, including a user-local install
    #: (`dpkg -x calculix-ccx*.deb ~/.local/ccx` needs no root).
    _CCX_CANDIDATES = ("ccx", "ccx_2.21", "ccx_2.19")
    _CCX_EXTRA_PATHS = ("~/.local/bin/ccx", "~/.local/ccx/usr/bin/ccx",
                        "/usr/bin/ccx", "/usr/local/bin/ccx")

    @staticmethod
    def _find_ccx() -> "str | None":
        """Locate ccx and make sure FreeCAD's FEM module uses the same one."""
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx")
        configured = param.GetString("ccxBinaryPath", "")
        found = None
        for name in T2GPanel._CCX_CANDIDATES:
            found = shutil.which(name)
            if found:
                break
        if not found:
            for cand in T2GPanel._CCX_EXTRA_PATHS:
                cand = os.path.expanduser(cand)
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    found = cand
                    break
        if not found and configured and os.path.isfile(configured):
            found = configured
        if found and configured != found:
            # FemToolsCcx reads this preference, not our PATH lookup.
            param.SetString("ccxBinaryPath", found)
            param.SetBool("UseStandardCcxLocation", False)
        return found

    def _run_ccx(self, analysis, solver) -> list:
        """Solve with CalculiX when it is installed; say so clearly if not."""
        ccx = self._find_ccx()
        if not ccx:
            return ["Solver CalculiX (ccx) ist nicht installiert – Aufbau und Netz "
                    "stehen, gerechnet wurde nicht. Installation: "
                    "`sudo apt install calculix-ccx` (oder ohne root: "
                    "`apt-get download calculix-ccx libspooles2.2t64` und "
                    "`dpkg -x` nach ~/.local/ccx), danach die Analyse erneut "
                    "starten."]
        self.progress_label.setText("Rechne mit CalculiX …")
        FreeCADGui.updateGui()
        try:
            from femtools import ccxtools
            fea = ccxtools.FemToolsCcx(analysis, solver)
            fea.update_objects()
            fea.setup_working_dir()
            msgs = fea.check_prerequisites()
            if msgs:
                return ["CalculiX-Vorbedingungen nicht erfüllt: " + str(msgs)]
            fea.run()
            fea.load_results()
        except Exception as e:  # noqa: BLE001
            return [f"CalculiX-Lauf fehlgeschlagen: {e}"]
        out = []
        seen = set()
        for o in analysis.Group:
            if not o.isDerivedFrom("Fem::FemResultObject"):
                continue
            try:
                vm = list(o.vonMises or [])
                dl = list(o.DisplacementLengths or [])
                key = (round(max(vm), 6) if vm else 0, round(max(dl), 9) if dl else 0)
                if key in seen:      # FreeCAD adds one result object per step
                    continue
                seen.add(key)
                out.append(
                    "Ergebnis (%s): von-Mises max %.3f MPa (Mittel %.3f), "
                    "Verschiebung max %.4f mm."
                    % (o.Name, max(vm) if vm else 0.0,
                       (sum(vm) / len(vm)) if vm else 0.0,
                       max(dl) if dl else 0.0))
            except Exception:  # noqa: BLE001
                out.append("Ergebnisobjekt %s erzeugt." % o.Name)
        if out:
            out.append("Gerechnet mit %s." % ccx)
        return out or ["CalculiX gelaufen, kein Ergebnisobjekt gefunden."]

    # --------------------------------------------------------- skill lernen --

    def _build_skill_learn_group(self) -> QGroupBox:
        box = QGroupBox("Skill lernen (komplexes Bauteil → wiederverwendbarer Generator)")
        self._grp_learn = box
        v = QVBoxLayout(box)
        form = QFormLayout()
        self.lrn_topic = QLineEdit()
        self.lrn_topic.setPlaceholderText("z. B. Einlasskanal, Schneckenwelle, Lagerbock")
        form.addRow("Bauteil:", self.lrn_topic)
        self.lrn_notes = QPlainTextEdit()
        self.lrn_notes.setPlaceholderText(
            "Eigene Angaben: Einsatzzweck, bekannte Maße, Randbedingungen …")
        self.lrn_notes.setMaximumHeight(60)
        form.addRow("Angaben:", self.lrn_notes)

        web_row = QHBoxLayout()
        self.lrn_web = QCheckBox("Webrecherche (Wikipedia)")
        self.lrn_web.setToolTip(
            "Aus: es verlässt nichts den Rechner. An: der Bauteilname wird an "
            "die Wikipedia-API geschickt; die gefundenen Quellen werden angezeigt.")
        web_row.addWidget(self.lrn_web)
        self.lrn_url = QLineEdit()
        self.lrn_url.setPlaceholderText("zusätzliche URL (optional, http/https)")
        web_row.addWidget(self.lrn_url, 1)
        form.addRow("Recherche:", web_row)
        v.addLayout(form)

        self.lrn_sources = QLabel("")
        self.lrn_sources.setWordWrap(True)
        self.lrn_sources.setStyleSheet("color: palette(mid);")
        v.addWidget(self.lrn_sources)

        row1 = QHBoxLayout()
        self.lrn_analyse_btn = QPushButton("1. Analysieren")
        self.lrn_analyse_btn.setToolTip(
            "Recherchiert (falls erlaubt) und lässt das Modell Parameter und "
            "offene Fragen vorschlagen")
        self.lrn_analyse_btn.clicked.connect(self._learn_analyse)
        row1.addWidget(self.lrn_analyse_btn)
        row1.addStretch(1)
        v.addLayout(row1)

        self.lrn_questions = QPlainTextEdit()
        self.lrn_questions.setReadOnly(True)
        self.lrn_questions.setPlaceholderText("Rückfragen des Modells erscheinen hier")
        self.lrn_questions.setMaximumHeight(70)
        v.addWidget(QLabel("Rückfragen:"))
        v.addWidget(self.lrn_questions)

        self.lrn_answers = QPlainTextEdit()
        self.lrn_answers.setPlaceholderText("Antworten auf die Rückfragen …")
        self.lrn_answers.setMaximumHeight(60)
        v.addWidget(QLabel("Antworten:"))
        v.addWidget(self.lrn_answers)

        v.addWidget(QLabel("Parameter (bearbeitbar: name;label;einheit;default;min;max):"))
        self.lrn_params = QPlainTextEdit()
        self.lrn_params.setPlaceholderText(
            "wird von der Analyse gefüllt – Zeilen dürfen geändert werden")
        self.lrn_params.setMaximumHeight(110)
        v.addWidget(self.lrn_params)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Versuche:"))
        self.lrn_tries = QSpinBox()
        self.lrn_tries.setRange(1, 6)
        self.lrn_tries.setValue(3)
        self.lrn_tries.setToolTip(
            "Schlägt die Prüfung fehl, bekommt das Modell den Fehler zurück")
        row2.addWidget(self.lrn_tries)
        row2.addStretch(1)
        self.lrn_build_btn = QPushButton("2. Skill erzeugen")
        self.lrn_build_btn.setEnabled(False)
        self.lrn_build_btn.clicked.connect(self._learn_build)
        row2.addWidget(self.lrn_build_btn)
        v.addLayout(row2)

        self.lrn_status = QLabel("")
        self.lrn_status.setWordWrap(True)
        v.addWidget(self.lrn_status)

        self._learn_worker = None
        self._learn_state: dict = {}
        return box

    # ---- background jobs ---------------------------------------------------

    def _spawn(self, fn, tag: str, on_done) -> "_CallWorker | None":
        """Start a background call and keep it alive until it is finished.

        Assigning a new worker over a still-running one frees the QThread and
        Qt aborts the process ("Destroyed while thread is still running"), so
        every worker is held in a list and only dropped once it has ended.
        """
        running = [w for w in getattr(self, "_workers", []) if w.isRunning()]
        self._workers = running
        if any(w.tag == tag for w in running):
            self.progress_label.setText(
                "„%s“ läuft bereits – bitte abwarten." % tag)
            return None
        worker = _CallWorker(fn, tag)
        self._workers.append(worker)
        worker.done.connect(on_done)
        worker.finished.connect(lambda w=worker: self._reap_worker(w))
        worker.start()
        return worker

    def _reap_worker(self, worker) -> None:
        self._workers = [w for w in getattr(self, "_workers", [])
                         if w is not worker]

    def _learn_backend(self):
        """(cfg, pi) for the long calls, or raise with a clear message."""
        cfg = self._api_config()
        if cfg.kind == "pi":
            return cfg, T2GCore.find_pi_binary()
        if cfg.kind == "ollama" and not T2GCore.ollama_running(cfg.base_url):
            raise T2GCore.BackendError(
                f"Ollama unter {cfg.base_url} nicht erreichbar – "
                "Tab „Backend“ → „Ollama starten“.")
        return cfg, None

    def _learn_busy(self, busy: bool) -> None:
        self.lrn_analyse_btn.setEnabled(not busy)
        self.lrn_build_btn.setEnabled(not busy and bool(self._learn_state.get("params")))

    def _learn_analyse(self) -> None:
        topic = self.lrn_topic.text().strip()
        if not topic:
            self.lrn_status.setText("Bitte zuerst ein Bauteil benennen.")
            return
        try:
            cfg, pi = self._learn_backend()
        except Exception as e:  # noqa: BLE001
            self.lrn_status.setText(str(e))
            return

        research = None
        if self.lrn_web.isChecked() or self.lrn_url.text().strip():
            self.lrn_status.setText("Recherchiere …")
            FreeCADGui.updateGui()
            urls = [u for u in [self.lrn_url.text().strip()] if u]
            research = T2GCore.research_topic(
                topic, urls=urls, use_wikipedia=self.lrn_web.isChecked())
            if research.sources:
                self.lrn_sources.setText(
                    "Quellen: " + " · ".join(f"{t} ({u})" for t, u in research.sources))
            else:
                self.lrn_sources.setText("Keine Quellen gefunden.")
            for err in research.errors:
                self.log_edit.appendPlainText("Recherche: " + err)
        else:
            self.lrn_sources.setText("Webrecherche aus – nur eigene Angaben.")

        self._learn_state = {"topic": topic, "research": research,
                             "cfg": cfg, "pi": pi}
        prompt = T2GCore.build_skill_analyse_prompt(
            topic, research, self.lrn_notes.toPlainText())
        self._learn_busy(True)
        self._start_elapsed("Modell analysiert das Bauteil …",
                            self.lrn_status.setText)
        self._learn_worker = _TextWorker(prompt, T2GCore.SKILL_ANALYSE_PROMPT,
                                         cfg, pi, tag="analyse")
        self._learn_worker.done.connect(self._learn_analyse_done)
        self._learn_worker.start()

    def _learn_analyse_done(self, payload: dict) -> None:
        self._stop_elapsed()
        self._learn_busy(False)
        if payload.get("error"):
            self.lrn_status.setText("Analyse fehlgeschlagen: " + payload["error"])
            self._job_finished(False, "Analyse fehlgeschlagen: " + payload["error"])
            return
        try:
            questions, params = T2GCore.parse_skill_analysis(payload["text"])
        except Exception as e:  # noqa: BLE001
            self.lrn_status.setText("Antwort unbrauchbar: " + str(e))
            self.log_edit.appendPlainText("Rohantwort:\n" + payload["text"][:2000])
            self._job_finished(False, "Analyse unbrauchbar: " + str(e))
            return
        self.lrn_questions.setPlainText("\n".join(questions)
                                        or "(keine Rückfragen)")
        self.lrn_params.setPlainText("\n".join(
            ";".join(str(x) for x in p) for p in params))
        self._learn_state["params"] = params
        self.lrn_build_btn.setEnabled(True)
        self.lrn_status.setText(
            f"{len(params)} Parameter vorgeschlagen, {len(questions)} Rückfrage(n). "
            "Antworten ergänzen, Parameter anpassen, dann „2. Skill erzeugen“.")
        if getattr(self, "_agent_job_done", None) is not None:
            # agent-driven: go straight on with the proposed parameters
            self.lrn_answers.setPlainText(
                "\n".join(questions) and
                "Offene Punkte nach bestem Wissen annehmen und im Code "
                "kommentieren." or "")
            return self._learn_build()
        if questions:
            self.lrn_answers.setFocus()

    def _learn_build(self) -> None:
        # the user may have edited the table -- that text wins
        params = T2GCore.parse_param_lines(self.lrn_params.toPlainText())
        if not params:
            self.lrn_status.setText("Keine gültige Parameterzeile.")
            return
        try:
            cfg, pi = self._learn_backend()
        except Exception as e:  # noqa: BLE001
            self.lrn_status.setText(str(e))
            return
        st = self._learn_state
        st.update({"params": params, "cfg": cfg, "pi": pi,
                   "attempt": 1, "max_tries": self.lrn_tries.value(),
                   "code": "", "problems": []})
        self._learn_request_code()

    def _learn_request_code(self) -> None:
        st = self._learn_state
        prompt = T2GCore.build_skill_code_prompt(
            st["topic"], st["params"], self.lrn_answers.toPlainText(),
            st.get("research"), st.get("code", ""), st.get("problems") or None)
        self._learn_busy(True)
        self._start_elapsed(
            f"Versuch {st['attempt']}/{st['max_tries']}: Modell schreibt build() …",
            self.lrn_status.setText)
        FreeCADGui.updateGui()
        # geometry code is worth the extra thinking, whatever the panel says
        self._learn_worker = _TextWorker(prompt, T2GCore.SKILL_CODE_PROMPT,
                                         T2GCore.with_thinking(st["cfg"], "high"),
                                         st["pi"], tag="code")
        self._learn_worker.done.connect(self._learn_build_done)
        self._learn_worker.start()

    def _learn_build_done(self, payload: dict) -> None:
        self._stop_elapsed()
        st = self._learn_state
        if payload.get("error"):
            self._learn_busy(False)
            self.lrn_status.setText("Erzeugung fehlgeschlagen: " + payload["error"])
            return
        try:
            code = T2GCore.parse_skill_code(payload["text"])
        except Exception as e:  # noqa: BLE001
            problems = [str(e)]
            code = payload["text"][:2000]
        else:
            name = _slugify(st["topic"])
            problems, shapes = T2GSkills.validate_skill_source(
                name, st["params"], code,
                pruefregeln=["kollision", "konnektivitaet"])
            if not problems:
                return self._learn_save(name, code, shapes)

        st["code"] = code
        st["problems"] = problems
        self.log_edit.appendPlainText(
            "Skill-Lernen Versuch %d fehlgeschlagen:\n  - %s"
            % (st["attempt"], "\n  - ".join(problems)))
        if st["attempt"] >= st["max_tries"]:
            self._learn_busy(False)
            msg = ("Nach %d Versuchen nicht gelungen: %s"
                   % (st["attempt"], "; ".join(problems[:2])))
            self.lrn_status.setText(msg)
            self._job_finished(False, "skill_lernen %s: %s" % (st["topic"], msg))
            if getattr(self, "_learn_queue", None):
                self.log_edit.appendPlainText(
                    "„%s“ übersprungen, weiter mit der Warteschlange."
                    % st["topic"])
                QtCore.QTimer.singleShot(500, self._learn_next_in_queue)
            return
        st["attempt"] += 1
        self._learn_request_code()

    def _learn_save(self, name: str, code: str, shapes: list) -> None:
        st = self._learn_state
        desc = f"Gelernter Generator: {st['topic']}"
        if st.get("research") and st["research"].sources:
            desc += " (Recherche: " + ", ".join(
                t for t, _ in st["research"].sources[:3]) + ")"
        try:
            path = T2GSkills.create_skill(name, desc, st["params"], code)
        except Exception as e:  # noqa: BLE001
            self._learn_busy(False)
            self.lrn_status.setText("Speichern fehlgeschlagen: " + str(e))
            return
        self._learn_busy(False)
        self._skill_refresh()
        idx = self.skill_combo.findText(name)
        if idx >= 0:
            self.skill_combo.setCurrentIndex(idx)
        msg = ("Skill „%s“ gelernt und gespeichert (%d Solid(s), Versuch %d/%d).\n%s"
               % (name, len(shapes), st["attempt"], st["max_tries"], path))
        self.lrn_status.setText(msg)
        self.log_edit.appendPlainText(msg + "\n--- build() ---\n" + code)
        self.progress_label.setText(f"Skill „{name}“ gelernt – oben mit „Bauen“ einsetzbar.")
        if getattr(self, "_learn_queue", None):
            QtCore.QTimer.singleShot(500, self._learn_next_in_queue)
        if self._project is not None:
            for sneed in self._project.skills:
                if sneed.name == name:
                    sneed.status = "gelernt"
            self._project.save()
        built = ""
        if getattr(self, "_agent_job_done", None) is not None:
            # a skill nobody can look at cannot be judged -- put it in the
            # document straight away
            try:
                eng = self._skills_engine(reload=True)
                vals = (self._project.param_values() if self._project else {})
                known = {q.name for q in eng.registry.get(name).definition.params}
                shp, used, probs = eng.build(
                    name, {k: v for k, v in vals.items() if k in known})
                self._add_skill_shapes(name, shp, probs)
                built = " · im Dokument gebaut: " + self._describe_build(shp)
                if probs:
                    built += " · Hinweise: " + "; ".join(probs)
            except Exception as e:  # noqa: BLE001
                built = " · Bauen fehlgeschlagen: %s" % e
        self._job_finished(True, "Skill %s gelernt (%d Solid(s))%s"
                           % (name, len(shapes), built))

    # --------------------------------------------------------------- start --

    #: The guided path, in the order it is meant to be walked.
    _STEPS = (
        ("projekt", "1 · Projekt anlegen",
         "Ein Projekt hält Auftrag, Maße, Bauteile und Prüfungen zusammen."),
        ("auftrag", "2 · Auftrag beschreiben",
         "Was soll gebaut werden? Das Modell gliedert es und fragt nach."),
        ("angaben", "3 · Maße festlegen",
         "Offene Zahlenwerte ausfüllen – sie gelten dann projektweit."),
        ("skills", "4 · Bauteile erzeugen",
         "Vorhandene Generatoren kopieren, fehlende lernen."),
        ("bauen", "5 · Ins Dokument bauen",
         "Jeden fertigen Generator ausführen und ansehen."),
        ("pruefen", "6 · Prüfen",
         "Verbindungen, Kollisionen, Festigkeit."),
    )

    def _build_start_group(self) -> QGroupBox:
        box = QGroupBox("Geführter Ablauf")
        v = QVBoxLayout(box)
        einleitung = QLabel(
            "Der übliche Weg von oben nach unten. Jeder Schritt sagt, ob er "
            "erledigt ist, und bringt Sie an die passende Stelle. "
            "Alles lässt sich später einzeln nachbessern.")
        einleitung.setWordWrap(True)
        v.addWidget(einleitung)

        self._step_labels = {}
        self._step_buttons = {}
        for key, titel, erklaerung in self._STEPS:
            zeile = QHBoxLayout()
            status = QLabel("○")
            status.setMinimumWidth(20)
            self._step_labels[key] = status
            zeile.addWidget(status)
            text = QLabel("<b>%s</b><br><span style='color:gray'>%s</span>"
                          % (titel, erklaerung))
            text.setWordWrap(True)
            zeile.addWidget(text, 1)
            knopf = QPushButton("öffnen")
            knopf.setMaximumWidth(120)
            knopf.clicked.connect(lambda _c=False, k=key: self._step_go(k))
            self._step_buttons[key] = knopf
            zeile.addWidget(knopf)
            v.addLayout(zeile)

        v.addSpacing(6)
        auto = QHBoxLayout()
        self.start_auto_text = QLineEdit()
        self.start_auto_text.setPlaceholderText(
            "Alles auf einmal: „Zylinderkopf für einen Vierzylinder“ …")
        auto.addWidget(self.start_auto_text, 1)
        self.start_auto_steps = QSpinBox()
        self.start_auto_steps.setRange(3, 40)
        self.start_auto_steps.setValue(20)
        self.start_auto_steps.setPrefix("max. ")
        self.start_auto_steps.setSuffix(" Schritte")
        auto.addWidget(self.start_auto_steps)
        self.start_auto_btn = QPushButton("Automatik starten")
        self.start_auto_btn.setToolTip(
            "Der Agent arbeitet den ganzen Ablauf selbstständig ab und fragt "
            "nur nach, wo es ohne Sie nicht geht. Jeder Schritt bleibt danach "
            "editierbar.")
        self.start_auto_btn.clicked.connect(self._start_automatik)
        auto.addWidget(self.start_auto_btn)
        v.addLayout(auto)

        self.start_status = QLabel("")
        self.start_status.setWordWrap(True)
        v.addWidget(self.start_status)
        return box

    def _step_go(self, key: str) -> None:
        """Take the user to where that step happens."""
        if key == "projekt":
            self.main_tabs.setCurrentWidget(self.tab_project)
            self.prj_title.setFocus()
        elif key == "auftrag":
            self.main_tabs.setCurrentWidget(self.tab_project)
            self._reveal(getattr(self, "_grp_plan", None))
            self.prj_desc.setFocus()
        elif key == "angaben":
            offen = [p.name for p in (self._project.open_questions()
                                      if self._project else [])]
            self.main_tabs.setCurrentWidget(self.tab_chat)
            if offen:
                self.chat_input.setPlainText(
                    "Frag mich nach den noch offenen Maßen: "
                    + ", ".join(offen))
                self.chat_input.setFocus()
            else:
                self._chat_append("System", "Keine offenen Maße.")
        elif key == "skills":
            self.main_tabs.setCurrentWidget(self.tab_project)
            self._reveal(getattr(self, "_grp_prj_skills", None))
        elif key == "bauen":
            self.main_tabs.setCurrentWidget(self.tab_skill)
            self._reveal(getattr(self, "_grp_skill", None))
        else:
            self.main_tabs.setCurrentWidget(self.tab_tools)
        self._refresh_start()

    def _refresh_start(self) -> None:
        """Tick off what is done, from the project state."""
        p = self._project
        zustand = {k: False for k, _t, _e in self._STEPS}
        hinweis = []
        if p is not None:
            zustand["projekt"] = True
            zustand["auftrag"] = bool(p.brief.strip())
            zustand["angaben"] = bool(p.params) and not p.open_questions()
            fertig = [x for x in p.skills
                      if x.status in ("kopiert", "gelernt", "gebaut")]
            zustand["skills"] = bool(p.skills) and len(fertig) == len(p.skills)
            zustand["bauen"] = any(x.status == "gebaut" for x in p.skills)
            zustand["pruefen"] = any("Prüfung" in n or "Analyse" in n
                                     for n in p.notes)
            offen = p.open_questions()
            if offen:
                hinweis.append("%d offene(s) Maß(e)" % len(offen))
            fehlt = [x.name for x in p.skills if x not in fertig]
            if fehlt:
                hinweis.append("%d Bauteil(e) offen: %s"
                               % (len(fehlt), ", ".join(fehlt[:4])))
        else:
            hinweis.append("Noch kein Projekt – mit Schritt 1 beginnen.")
        naechster = None
        for key, _t, _e in self._STEPS:
            lab = self._step_labels.get(key)
            if lab is None:
                continue
            if zustand[key]:
                lab.setText("✓")
                lab.setStyleSheet("color: #2f9e68; font-weight: bold;")
                self._step_buttons[key].setText("ansehen")
            else:
                if naechster is None:
                    naechster = key
                    lab.setText("▶")
                    lab.setStyleSheet("color: #d08000; font-weight: bold;")
                    self._step_buttons[key].setText("hier weiter")
                else:
                    lab.setText("○")
                    lab.setStyleSheet("color: gray;")
                    self._step_buttons[key].setText("öffnen")
        self.start_status.setText(" · ".join(hinweis) if hinweis
                                  else "Alle Schritte erledigt.")

    def _start_automatik(self) -> None:
        """Hand the whole job to the agent in one go."""
        auftrag = self.start_auto_text.text().strip()
        if not auftrag:
            self.start_status.setText("Bitte zuerst beschreiben, was gebaut "
                                      "werden soll.")
            return
        self.chat_steps.setValue(self.start_auto_steps.value())
        self.chat_agent_mode.setChecked(True)
        self.main_tabs.setCurrentWidget(self.tab_chat)
        self.chat_input.setPlainText(
            "%s. Arbeite den ganzen Ablauf selbstständig ab: Projekt anlegen, "
            "recherchieren, Auftrag festhalten, Parameter und Kriterien "
            "setzen, Abhängigkeiten eintragen, vorhandene Skills kopieren, "
            "fehlende lernen und jeden fertigen Skill ins Dokument bauen. "
            "Frag nur nach, wo es ohne mich nicht geht." % auftrag)
        self._chat_send()

    # ------------------------------------------------------------- projekt --

    def _build_project_group(self) -> QGroupBox:
        box = QGroupBox("Projekt")
        form = QFormLayout(box)

        row = QHBoxLayout()
        self.prj_base = QLineEdit(os.path.join(os.path.expanduser("~"),
                                               "T2G-Projekte"))
        row.addWidget(self.prj_base, 1)
        pick = QPushButton("…")
        pick.setMaximumWidth(32)
        pick.clicked.connect(self._prj_pick_base)
        row.addWidget(pick)
        form.addRow("Verzeichnis:", row)

        self.prj_title = QLineEdit()
        self.prj_title.setPlaceholderText("z. B. Zylinderkopf V2")
        form.addRow("Titel:", self.prj_title)

        row2 = QHBoxLayout()
        self.prj_new_btn = QPushButton("Neu anlegen")
        self.prj_new_btn.clicked.connect(self._prj_create)
        row2.addWidget(self.prj_new_btn)
        self.prj_open_combo = QComboBox()
        row2.addWidget(self.prj_open_combo, 1)
        self.prj_open_btn = QPushButton("Öffnen")
        self.prj_open_btn.clicked.connect(self._prj_open)
        row2.addWidget(self.prj_open_btn)
        refresh = QPushButton("↻")
        refresh.setMaximumWidth(32)
        refresh.clicked.connect(self._prj_scan)
        row2.addWidget(refresh)
        form.addRow(row2)

        self.prj_status = QLabel("Kein Projekt geöffnet.")
        self.prj_status.setWordWrap(True)
        form.addRow("Status:", self.prj_status)

        self._project = None
        self._prj_worker = None
        self._prj_pair_rows: list = []
        self._prj_scan()
        return box

    def _build_project_plan_group(self) -> QGroupBox:
        box = QGroupBox("Auftrag und Planung")
        self._grp_plan = box
        v = QVBoxLayout(box)
        v.addWidget(QLabel("Was soll gebaut werden?"))
        self.prj_desc = QPlainTextEdit()
        self.prj_desc.setPlaceholderText(
            "Freie Beschreibung des Vorhabens – Zweck, Baugruppen, "
            "bekannte Randbedingungen …")
        self.prj_desc.setMaximumHeight(80)
        v.addWidget(self.prj_desc)

        row = QHBoxLayout()
        self.prj_web = QCheckBox("Webrecherche (Wikipedia)")
        row.addWidget(self.prj_web)
        row.addStretch(1)
        self.prj_plan_btn = QPushButton("Projekt planen")
        self.prj_plan_btn.setToolTip(
            "Modell gliedert das Vorhaben: Auftrag, Rückfragen, Skills, "
            "Werkzeuge, Bewertungskriterien")
        self.prj_plan_btn.clicked.connect(self._prj_plan)
        row.addWidget(self.prj_plan_btn)
        v.addLayout(row)

        v.addWidget(QLabel("Auftrag (bearbeitbar):"))
        self.prj_brief = QPlainTextEdit()
        self.prj_brief.setMaximumHeight(80)
        v.addWidget(self.prj_brief)

        v.addWidget(QLabel("Rückfragen:"))
        self.prj_questions = QPlainTextEdit()
        self.prj_questions.setReadOnly(True)
        self.prj_questions.setMaximumHeight(60)
        v.addWidget(self.prj_questions)

        v.addWidget(QLabel("Antworten:"))
        self.prj_answers = QPlainTextEdit()
        self.prj_answers.setMaximumHeight(60)
        v.addWidget(self.prj_answers)

        v.addWidget(QLabel("Skills (name;zweck):"))
        self.prj_skills = QPlainTextEdit()
        self.prj_skills.setMaximumHeight(80)
        v.addWidget(self.prj_skills)

        v.addWidget(QLabel("Werkzeuge (name;zweck):"))
        self.prj_tools = QPlainTextEdit()
        self.prj_tools.setMaximumHeight(60)
        v.addWidget(self.prj_tools)

        v.addWidget(QLabel("Kriterien (name;bedeutung):"))
        self.prj_criteria = QPlainTextEdit()
        self.prj_criteria.setMaximumHeight(80)
        v.addWidget(self.prj_criteria)

        row2 = QHBoxLayout()
        self.prj_save_btn = QPushButton("Übernehmen + agent.d schreiben")
        self.prj_save_btn.clicked.connect(self._prj_apply)
        row2.addWidget(self.prj_save_btn)
        row2.addStretch(1)
        v.addLayout(row2)
        return box

    def _build_project_skills_group(self) -> QGroupBox:
        box = QGroupBox("Skills des Projekts")
        self._grp_prj_skills = box
        v = QVBoxLayout(box)
        self.prj_skill_view = QPlainTextEdit()
        self.prj_skill_view.setReadOnly(True)
        self.prj_skill_view.setPlaceholderText(
            "Nach „Übernehmen“ steht hier, welcher Skill schon existiert "
            "und welcher noch gebaut werden muss.")
        self.prj_skill_view.setMaximumHeight(90)
        v.addWidget(self.prj_skill_view)
        row = QHBoxLayout()
        self.prj_copy_btn = QPushButton("Vorhandene kopieren")
        self.prj_copy_btn.setToolTip(
            "Passende vorhandene Skills in das Projektverzeichnis kopieren")
        self.prj_copy_btn.clicked.connect(self._prj_copy_skills)
        row.addWidget(self.prj_copy_btn)
        self.prj_learn_btn = QPushButton("Nächsten fehlenden lernen →")
        self.prj_learn_btn.setToolTip(
            "Den ersten offenen Skill in den Lern-Dialog übernehmen "
            "(Tab „Skills“), mit dem Projektkontext als Vorgabe")
        self.prj_learn_btn.clicked.connect(self._prj_learn_missing)
        row.addWidget(self.prj_learn_btn)
        self.prj_learn_all_btn = QPushButton("Alle fehlenden lernen")
        self.prj_learn_all_btn.setToolTip(
            "Arbeitet alle offenen Skills nacheinander ab (je einige Minuten). "
            "„Stop“ im Dialog-Tab hält nach dem laufenden an.")
        self.prj_learn_all_btn.clicked.connect(self._prj_learn_all)
        row.addWidget(self.prj_learn_all_btn)
        row.addStretch(1)
        v.addLayout(row)
        return box

    def _build_project_pairs_group(self) -> QGroupBox:
        box = QGroupBox("Paarvergleich der Kriterien (Gewichtung)")
        v = QVBoxLayout(box)
        row = QHBoxLayout()
        self.prj_pairs_btn = QPushButton("Vorschlag vom Modell")
        self.prj_pairs_btn.clicked.connect(self._prj_suggest_pairs)
        row.addWidget(self.prj_pairs_btn)
        self.prj_eval_btn = QPushButton("Auswerten + speichern")
        self.prj_eval_btn.clicked.connect(self._prj_evaluate)
        row.addWidget(self.prj_eval_btn)
        row.addStretch(1)
        v.addLayout(row)

        self.prj_pair_form = QFormLayout()
        v.addLayout(self.prj_pair_form)

        self.prj_result = QLabel("")
        self.prj_result.setWordWrap(True)
        self.prj_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.prj_result)
        return box

    # ---- project lifecycle ------------------------------------------------

    def _prj_pick_base(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Projektverzeichnis", self.prj_base.text().strip()
            or os.path.expanduser("~"))
        if d:
            self.prj_base.setText(d)
            self._prj_scan()

    def _prj_scan(self) -> None:
        base = self.prj_base.text().strip()
        self.prj_open_combo.clear()
        for path in T2GProject.list_projects(base):
            self.prj_open_combo.addItem(os.path.basename(path), path)
        if self.prj_open_combo.count() == 0:
            self.prj_open_combo.addItem("– keine Projekte gefunden –", "")

    def _prj_create(self) -> None:
        base = self.prj_base.text().strip()
        title = self.prj_title.text().strip()
        if not title:
            self.prj_status.setText("Bitte einen Titel angeben.")
            return
        try:
            os.makedirs(base, exist_ok=True)
            self._project = T2GProject.Project.create(base, title)
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText("Anlegen fehlgeschlagen: " + str(e))
            return
        self._reset_session()
        self._prj_scan()
        self._prj_show()
        self._remember_project()
        self.log_edit.appendPlainText("Projekt angelegt: " + self._project.path)

    def _prj_open(self) -> None:
        path = self.prj_open_combo.currentData()
        if not path:
            return
        try:
            self._project = T2GProject.Project.load(path)
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText("Öffnen fehlgeschlagen: " + str(e))
            return
        self._remember_project()
        self._prj_show()

    def _reset_session(self) -> None:
        """A new project starts clean -- no leftovers from the last one."""
        self.chat_view.clear()
        self._chat = T2GCore.ChatSession()
        self._agent_run = None
        self._agent_job_done = None
        self._pending_params = []
        self._learn_queue = []
        self._learn_state = {}
        self._refine_state = {}
        self._prj_tool_state = {}
        self.chat_mask_box.setVisible(False)
        self._chat_mask_rows = []
        self.lrn_topic.clear()
        self.lrn_notes.clear()
        self.lrn_questions.clear()
        self.lrn_answers.clear()
        self.lrn_params.clear()
        self.lrn_sources.clear()
        self.lrn_status.clear()
        self.ref_goal.clear()
        self.ref_status.clear()
        self.prj_desc.clear()
        self.prj_result.clear()
        self.prj_tool_status.clear()
        self.prj_skill_view.clear()
        self.log_edit.clear()
        self.progress_label.setText("Neues Projekt – alles zurückgesetzt.")

    def _prj_show(self) -> None:
        p = self._project
        if p is None:
            self.prj_status.setText("Kein Projekt geöffnet.")
            return
        self.prj_title.setText(p.title)
        self.prj_brief.setPlainText(p.brief)
        self.prj_questions.setPlainText("\n".join(p.questions))
        self.prj_answers.setPlainText(p.answers)
        self.prj_skills.setPlainText(
            "\n".join(f"{s.name};{s.description}" for s in p.skills))
        self.prj_tools.setPlainText(
            "\n".join(f"{t['name']};{t.get('purpose', '')}" for t in p.tools))
        self.prj_criteria.setPlainText(
            "\n".join(f"{c['name']};{c.get('description', '')}"
                      for c in p.criteria))
        self.prj_status.setText(
            "%s · %d Skill(s) · %d Kriterium/Kriterien · %s"
            % (p.path, len(p.skills), len(p.criteria), p.updated))
        self._prj_rebuild_pairs()
        self._prj_show_skill_status()
        self._prj_tool_refresh()
        self._refresh_start()

    def _open_or_create_project(self, title: str) -> "T2GProject.Project":
        """Open the project of that name, or create it. Always leaves one open."""
        base = self.prj_base.text().strip() or os.path.join(
            os.path.expanduser("~"), "T2G-Projekte")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, T2GProject.slugify(title))
        if os.path.isfile(os.path.join(path, T2GProject.PROJECT_FILE)):
            self._project = T2GProject.Project.load(path)
        else:
            self._project = T2GProject.Project.create(base, title)
        self._flush_pending_params()
        self._remember_project()
        self.prj_base.setText(base)
        self._prj_scan()
        self._prj_show()
        return self._project

    def _remember_project(self) -> None:
        """So the next FreeCAD start comes back to the same project."""
        try:
            prm = FreeCAD.ParamGet(self._PREF_PATH)
            prm.SetString("last_project",
                          self._project.path if self._project else "")
        except Exception:  # noqa: BLE001
            pass

    def _restore_last_project(self) -> None:
        try:
            prm = FreeCAD.ParamGet(self._PREF_PATH)
            path = prm.GetString("last_project", "")
        except Exception:  # noqa: BLE001
            return
        if not path or not os.path.isfile(
                os.path.join(path, T2GProject.PROJECT_FILE)):
            return
        try:
            self._project = T2GProject.Project.load(path)
        except Exception as e:  # noqa: BLE001
            FreeCAD.Console.PrintWarning(
                "TextToGeometry: letztes Projekt nicht ladbar: %s\n" % e)
            return
        self.prj_base.setText(os.path.dirname(path))
        self._prj_scan()
        self._prj_show()
        for role, text in self._project.chat_transcript(30):
            self.chat_view.appendPlainText("%s: %s\n" % (role, text))
        if self._project.chat_summary.strip():
            self.chat_view.appendPlainText(
                "Bisher geklärt:\n%s\n" % self._project.chat_summary.strip())
        self.chat_view.appendPlainText(
            "— Sitzung fortgesetzt: %s (%d Parameter, %d Skill(s)) —\n"
            % (self._project.title, len(self._project.params),
               len(self._project.skills)))
        self.progress_label.setText(
            "Projekt „%s“ wiederhergestellt." % self._project.title)

    def _prj_require(self) -> "T2GProject.Project":
        if self._project is None:
            raise T2GProject.ProjectError(
                "Kein Projekt geöffnet – zuerst anlegen oder öffnen.")
        return self._project

    # ---- planning ---------------------------------------------------------

    def _prj_plan(self) -> None:
        try:
            p = self._prj_require()
            cfg, pi = self._learn_backend()
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText(str(e))
            return
        desc = self.prj_desc.toPlainText().strip() or p.brief
        if not desc:
            self.prj_status.setText("Bitte beschreiben, was gebaut werden soll.")
            return
        research = None
        if self.prj_web.isChecked():
            self.prj_status.setText("Recherchiere …")
            FreeCADGui.updateGui()
            research = T2GCore.research_topic(p.title or desc[:60],
                                              use_wikipedia=True)
            for err in research.errors:
                self.log_edit.appendPlainText("Recherche: " + err)
        self._prj_research = research
        available = self._skills_engine(reload=True).registry.names()
        prompt = T2GCore.build_project_plan_prompt(
            p.title, desc, research, available)
        self.prj_plan_btn.setEnabled(False)
        self._start_elapsed("Modell gliedert das Projekt …",
                            self.prj_status.setText)
        self._prj_worker = _TextWorker(prompt, T2GCore.PROJECT_PLAN_PROMPT,
                                       cfg, pi, tag="plan")
        self._prj_worker.done.connect(self._prj_plan_done)
        self._prj_worker.start()

    def _prj_plan_done(self, payload: dict) -> None:
        self._stop_elapsed()
        self.prj_plan_btn.setEnabled(True)
        if payload.get("error"):
            self.prj_status.setText("Planung fehlgeschlagen: " + payload["error"])
            return
        try:
            plan = T2GCore.parse_project_plan(payload["text"])
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText("Antwort unbrauchbar: " + str(e))
            self.log_edit.appendPlainText("Rohantwort:\n" + payload["text"][:2000])
            return
        self.prj_brief.setPlainText(plan["auftrag"])
        self.prj_questions.setPlainText("\n".join(plan["fragen"])
                                        or "(keine Rückfragen)")
        self.prj_skills.setPlainText(
            "\n".join(f"{s['name']};{s['description']}" for s in plan["skills"]))
        self.prj_tools.setPlainText(
            "\n".join(f"{t['name']};{t['purpose']}" for t in plan["tools"]))
        self.prj_criteria.setPlainText(
            "\n".join(f"{c['name']};{c['description']}" for c in plan["criteria"]))
        self.prj_status.setText(
            "Plan: %d Skill(s), %d Werkzeug(e), %d Kriterium/Kriterien, "
            "%d Rückfrage(n). Prüfen, dann „Übernehmen“."
            % (len(plan["skills"]), len(plan["tools"]),
               len(plan["criteria"]), len(plan["fragen"])))

    @staticmethod
    def _rows_from_text(text: str) -> list:
        out = []
        for ln in (text or "").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#") or ln.startswith("("):
                continue
            parts = [c.strip() for c in ln.split(";")]
            out.append((parts[0], parts[1] if len(parts) > 1 else ""))
        return out

    def _prj_apply(self) -> None:
        """Take the edited fields into the project and write agent.d."""
        try:
            p = self._prj_require()
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText(str(e))
            return
        p.title = self.prj_title.text().strip() or p.title
        p.brief = self.prj_brief.toPlainText().strip()
        p.questions = [q for q in self.prj_questions.toPlainText().splitlines()
                       if q.strip() and not q.startswith("(")]
        p.answers = self.prj_answers.toPlainText().strip()

        known = {s.name: s for s in p.skills}
        p.skills = []
        for name, desc in self._rows_from_text(self.prj_skills.toPlainText()):
            old = known.get(name)
            p.skills.append(T2GProject.SkillNeed(
                name=name, description=desc,
                status=old.status if old else "offen",
                source=old.source if old else ""))
        old_tools = {t["name"]: t.get("file", "") for t in p.tools}
        p.tools = [{"name": n, "purpose": d, "file": old_tools.get(n, "")}
                   for n, d in self._rows_from_text(self.prj_tools.toPlainText())]
        p.set_criteria([{"name": n, "description": d}
                        for n, d in self._rows_from_text(
                            self.prj_criteria.toPlainText())])
        files = p.write_agent_d()
        p.write_matrix_csv()
        p.save()
        self._prj_rebuild_pairs()
        self._prj_show_skill_status()
        self._prj_tool_refresh()
        self.prj_status.setText(
            "Gespeichert. agent.d: " + ", ".join(os.path.basename(f) for f in files))
        self.log_edit.appendPlainText(
            "Projekt gespeichert: %s\n  %s" % (p.path, "\n  ".join(files)))

    # ---- skills -----------------------------------------------------------

    def _prj_matches(self) -> list:
        p = self._prj_require()
        available = self._skills_engine(reload=True).registry.names()
        return T2GProject.match_skills(p.skills, available)

    def _prj_show_skill_status(self) -> None:
        if self._project is None or not self._project.skills:
            self.prj_skill_view.setPlainText("")
            return
        lines = []
        for m in self._prj_matches():
            need = m.need
            if need.status in ("kopiert", "gelernt"):
                lines.append(f"{need.name}: {need.status}")
            elif m.is_match:
                lines.append(f"{need.name}: vorhanden als „{m.candidate}“ "
                             f"– kopierbar")
            elif m.is_hint:
                # Named, not copied: "auslasskanal" is not "einlasskanal".
                lines.append(f"{need.name}: fehlt – ähnlich ist „{m.candidate}“ "
                             f"({m.score:.2f}), aber nicht dasselbe; "
                             f"lernen oder von Hand kopieren")
            else:
                lines.append(f"{need.name}: fehlt – muss gelernt werden")
        self.prj_skill_view.setPlainText("\n".join(lines))

    def _prj_copy_skills(self) -> None:
        try:
            p = self._prj_require()
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText(str(e))
            return
        eng = self._skills_engine(reload=True)
        copied, skipped, used = [], [], set()
        for m in self._prj_matches():
            need = m.need
            if need.status in ("kopiert", "gelernt"):
                continue
            if not m.is_match:
                if m.is_hint:
                    skipped.append(f"{need.name} (ähnlich: {m.candidate})")
                continue
            if m.candidate in used:
                # two needs pointing at one skill would silently overwrite
                skipped.append(f"{need.name} (zeigt auf bereits kopiertes "
                               f"{m.candidate})")
                continue
            try:
                src = eng.registry.get(m.candidate).definition.path
                dest = p.copy_skill(src, need)
                used.add(m.candidate)
                copied.append("%s → %s" % (m.candidate, os.path.basename(dest)))
            except Exception as e:  # noqa: BLE001
                self.log_edit.appendPlainText(
                    f"Kopieren von {m.candidate} fehlgeschlagen: {e}")
        p.write_agent_d()
        p.save()
        self._prj_show_skill_status()
        msg = ("%d Skill(s) kopiert: %s" % (len(copied), ", ".join(copied))
               if copied else "Nichts kopiert.")
        if skipped:
            msg += " · übersprungen: " + ", ".join(skipped)
        self.prj_status.setText(msg)

    def _prj_learn_all(self) -> None:
        """Work through every open skill, one after another."""
        try:
            p = self._prj_require()
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText(str(e))
            return
        offen = [m.need.name for m in self._prj_matches()
                 if not m.is_match and m.need.status not in ("kopiert", "gelernt")]
        if not offen:
            self.prj_status.setText("Kein offener Skill – alle vorhanden.")
            return
        self._learn_queue = list(offen)
        self.prj_status.setText(
            "Lerne %d Skill(s) nacheinander: %s"
            % (len(offen), ", ".join(offen)))
        self.log_edit.appendPlainText(
            "Lern-Warteschlange: " + ", ".join(offen))
        self._learn_next_in_queue()

    def _learn_next_in_queue(self) -> None:
        queue = getattr(self, "_learn_queue", None)
        if not queue:
            self.prj_status.setText("Warteschlange abgearbeitet.")
            return
        name = queue.pop(0)
        p = self._project
        need = next((x for x in (p.skills if p else []) if x.name == name), None)
        self.lrn_topic.setText(name)
        notes = (need.description + "\n\n" if need and need.description else "")
        if p is not None:
            notes += p.as_prompt_block()
        self.lrn_notes.setPlainText(notes)
        self.lrn_web.setChecked(False)
        self.main_tabs.setCurrentWidget(self.tab_learn)
        self._reveal(getattr(self, "_grp_learn", None))
        self.prj_status.setText(
            "Lerne „%s“ … (%d weitere in der Warteschlange)" % (name, len(queue)))
        self._queue_job = True
        self._learn_analyse()

    def _prj_learn_missing(self) -> None:
        """Hand the first open skill to the learn box, with project context."""
        try:
            p = self._prj_require()
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText(str(e))
            return
        offen = [m.need for m in self._prj_matches()
                 if not m.is_match and m.need.status not in ("kopiert", "gelernt")]
        if not offen:
            self.prj_status.setText("Kein offener Skill – alle vorhanden.")
            return
        need = offen[0]
        self.lrn_topic.setText(need.name)
        self.lrn_notes.setPlainText(
            (need.description + "\n\n" if need.description else "")
            + p.as_prompt_block())
        self.main_tabs.setCurrentWidget(self.tab_learn)
        self.lrn_analyse_btn.setFocus()
        self.prj_status.setText(
            f"„{need.name}“ in den Lern-Dialog übernommen (Tab „Skills“).")

    # ---- pairwise comparison ---------------------------------------------

    def _prj_clear_pairs(self) -> None:
        while self.prj_pair_form.count():
            item = self.prj_pair_form.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._prj_pair_rows = []

    def _prj_rebuild_pairs(self) -> None:
        self._prj_clear_pairs()
        if self._project is None:
            return
        m = self._project.matrix
        names = m.criteria
        if len(names) < 2:
            return
        for i, j in T2GProject.pair_indices(len(names)):
            combo = QComboBox()
            for label, value in T2GProject.SAATY_SCALE:
                combo.addItem(label.replace("A", names[i]).replace("B", names[j]),
                              value)
            current = m.get_pair(i, j)
            best, best_d = 4, None
            for idx, (_, value) in enumerate(T2GProject.SAATY_SCALE):
                d = abs(value - current)
                if best_d is None or d < best_d:
                    best, best_d = idx, d
            combo.setCurrentIndex(best)
            self.prj_pair_form.addRow(f"{names[i]} ⇄ {names[j]}:", combo)
            self._prj_pair_rows.append((i, j, combo))

    def _prj_read_pairs(self) -> None:
        p = self._prj_require()
        for i, j, combo in self._prj_pair_rows:
            p.matrix.set_pair(i, j, float(combo.currentData()))

    def _prj_suggest_pairs(self) -> None:
        try:
            p = self._prj_require()
            if len(p.matrix.criteria) < 2:
                raise T2GProject.ProjectError(
                    "Mindestens zwei Kriterien nötig – erst „Übernehmen“.")
            cfg, pi = self._learn_backend()
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText(str(e))
            return
        prompt = T2GCore.build_project_pairs_prompt(p.as_prompt_block(),
                                                    p.criteria)
        self.prj_pairs_btn.setEnabled(False)
        self._start_elapsed("Modell schlägt Gewichtungen vor …",
                            self.prj_status.setText)
        self._prj_worker = _TextWorker(prompt, T2GCore.PROJECT_PAIRS_PROMPT,
                                       cfg, pi, tag="paare")
        self._prj_worker.done.connect(self._prj_pairs_done)
        self._prj_worker.start()

    def _prj_pairs_done(self, payload: dict) -> None:
        self._stop_elapsed()
        self.prj_pairs_btn.setEnabled(True)
        if payload.get("error"):
            self.prj_status.setText("Vorschlag fehlgeschlagen: " + payload["error"])
            return
        p = self._project
        pairs = T2GCore.parse_pair_suggestions(payload["text"], p.criteria)
        if not pairs:
            self.prj_status.setText("Keine verwertbaren Paare in der Antwort.")
            self.log_edit.appendPlainText("Rohantwort:\n" + payload["text"][:1500])
            return
        for i, j, value, reason in pairs:
            p.matrix.set_pair(i, j, value)
            if reason:
                self.log_edit.appendPlainText(
                    "  %s vs. %s = %.3g  (%s)"
                    % (p.matrix.criteria[i], p.matrix.criteria[j], value, reason))
        self._prj_rebuild_pairs()
        self.prj_status.setText(
            "%d Paar(e) vorgeschlagen – bitte prüfen und anpassen, "
            "dann „Auswerten“." % len(pairs))

    def _prj_evaluate(self) -> None:
        try:
            p = self._prj_require()
            if len(p.matrix.criteria) < 2:
                raise T2GProject.ProjectError("Mindestens zwei Kriterien nötig.")
            self._prj_read_pairs()
        except Exception as e:  # noqa: BLE001
            self.prj_status.setText(str(e))
            return
        csv_path = p.write_matrix_csv()
        p.write_agent_d()
        p.save()
        ranking = p.matrix.ranking()
        cr = p.matrix.consistency_ratio()
        text = ["Gewichtung:"]
        text += ["  %d. %s – %.1f %%" % (r, n, w * 100)
                 for r, (n, w) in enumerate(ranking, 1)]
        text.append("Konsistenzverhältnis %.3f (%s)"
                    % (cr, "in Ordnung" if p.matrix.is_consistent()
                       else "über 0,10 – Urteile widersprechen sich"))
        if not p.matrix.is_consistent():
            for a, b, said, implied in p.matrix.worst_pairs():
                text.append("  strittig: %s vs. %s – bewertet %.2f, "
                            "aus den Gewichten folgt %.2f" % (a, b, said, implied))
            if len(p.matrix.criteria) == 3:
                text.append("  (bei drei Kriterien verteilt sich ein Widerspruch "
                            "gleichmäßig – alle drei Urteile prüfen)")
        self.prj_result.setText("\n".join(text))
        self.prj_status.setText("Ausgewertet, gespeichert: "
                                + os.path.basename(csv_path))
        self.log_edit.appendPlainText("\n".join(text))

    # ------------------------------------------------------------ werkzeuge --

    _EXTRA_TOOL_PATHS_KEY = "tool_paths"

    def _build_tools_group(self) -> QGroupBox:
        box = QGroupBox("Werkzeuge dieser FreeCAD-Installation")
        v = QVBoxLayout(box)
        hinweis = QLabel(
            "Makros, installierte Add-ons und Python-Module lassen sich wie "
            "eigene Skills benutzen – auch vom Agenten.")
        hinweis.setWordWrap(True)
        v.addWidget(hinweis)

        self.tools_list = QListWidget()
        self.tools_list.setMinimumHeight(160)
        v.addWidget(self.tools_list)

        row = QHBoxLayout()
        self.tools_scan_btn = QPushButton("Neu suchen")
        self.tools_scan_btn.clicked.connect(self._tools_scan)
        row.addWidget(self.tools_scan_btn)
        self.tools_run_btn = QPushButton("Ausführen")
        self.tools_run_btn.setToolTip(
            "Makro ausführen, Add-on-Befehl auslösen oder Python-Funktion "
            "aufrufen")
        self.tools_run_btn.clicked.connect(self._tools_run_selected)
        row.addWidget(self.tools_run_btn)
        self.tools_add_btn = QPushButton("Python-Ordner hinzufügen …")
        self.tools_add_btn.setToolTip(
            "Ein eigenes Python-Paket oder eine .py-Datei als Werkzeug "
            "einbinden, z. B. eine Prüf-Bibliothek")
        self.tools_add_btn.clicked.connect(self._tools_add_path)
        row.addWidget(self.tools_add_btn)
        row.addStretch(1)
        v.addLayout(row)

        self.tools_args = QLineEdit()
        self.tools_args.setPlaceholderText(
            "Argumente für Python-Werkzeuge, z. B. d=25.4; name=Platte")
        v.addWidget(self.tools_args)

        self.tools_status = QLabel("")
        self.tools_status.setWordWrap(True)
        v.addWidget(self.tools_status)
        self._tools: list = []
        return box

    def _extra_tool_paths(self) -> list:
        try:
            prm = FreeCAD.ParamGet(self._PREF_PATH)
            raw = prm.GetString(self._EXTRA_TOOL_PATHS_KEY, "")
        except Exception:  # noqa: BLE001
            return []
        return [x for x in raw.split(os.pathsep) if x.strip()]

    def _save_extra_tool_paths(self, paths: list) -> None:
        try:
            prm = FreeCAD.ParamGet(self._PREF_PATH)
            prm.SetString(self._EXTRA_TOOL_PATHS_KEY,
                          os.pathsep.join(dict.fromkeys(paths)))
        except Exception:  # noqa: BLE001
            pass

    def _tools_scan(self) -> None:
        """Find macros, add-ons and registered Python modules."""
        paths = self._extra_tool_paths()
        if self._project is not None and os.path.isdir(self._project.tools_dir):
            paths = paths + [self._project.tools_dir]
        gefunden = []
        try:
            gefunden += T2GTools.discover_macros()
        except Exception as e:  # noqa: BLE001
            self.log_edit.appendPlainText("Makrosuche: %s" % e)
        try:
            gefunden += T2GTools.discover_addons()
        except Exception as e:  # noqa: BLE001
            self.log_edit.appendPlainText("Add-on-Suche: %s" % e)
        try:
            gefunden += T2GTools.discover_python_tools(paths)
        except Exception as e:  # noqa: BLE001
            self.log_edit.appendPlainText("Python-Suche: %s" % e)
        self._tools = gefunden
        self.tools_list.clear()
        for t in gefunden:
            item = QListWidgetItem(t.as_line())
            item.setToolTip("%s\n%s" % (t.path or t.module, t.description))
            item.setData(Qt.UserRole, t.name)
            self.tools_list.addItem(item)
        arten = {}
        for t in gefunden:
            arten[t.kind] = arten.get(t.kind, 0) + 1
        self.tools_status.setText(
            "%d Werkzeug(e): %s" % (len(gefunden),
                                    ", ".join("%d %s" % (v, k)
                                              for k, v in sorted(arten.items())))
            if gefunden else "Nichts gefunden.")

    def _tools_add_path(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Python-Ordner als Werkzeug einbinden",
            os.path.expanduser("~"))
        if not d:
            return
        paths = self._extra_tool_paths() + [d]
        self._save_extra_tool_paths(paths)
        self.tools_status.setText("Eingebunden: " + d)
        self._tools_scan()

    def _tools_selected(self) -> "T2GTools.ExternalTool | None":
        item = self.tools_list.currentItem()
        if item is None:
            return None
        return T2GTools.find_tool(self._tools, item.data(Qt.UserRole))

    @staticmethod
    def _parse_args(text: str) -> dict:
        out = {}
        for teil in (text or "").split(";"):
            if "=" not in teil:
                continue
            k, v = teil.split("=", 1)
            k, v = k.strip(), v.strip()
            if not k:
                continue
            try:
                out[k] = int(v) if re.fullmatch(r"[+-]?\d+", v) else float(v)
            except ValueError:
                out[k] = v
        return out

    def _tools_run_selected(self) -> None:
        tool = self._tools_selected()
        if tool is None:
            self.tools_status.setText("Bitte ein Werkzeug auswählen.")
            return
        try:
            ergebnis = self.run_external_tool(tool, self.tools_args.text())
        except Exception as e:  # noqa: BLE001
            self.tools_status.setText("Fehlgeschlagen: %s" % e)
            FreeCAD.Console.PrintError("TextToGeometry Werkzeug: %s\n" % e)
            return
        self.tools_status.setText(ergebnis)
        self.log_edit.appendPlainText(ergebnis)

    def run_external_tool(self, tool, args_text: str = "") -> str:
        """Run a macro, an add-on command or a Python function."""
        if tool.kind == "makro":
            if not os.path.isfile(tool.path):
                raise T2GTools.ToolError("Makro fehlt: %s" % tool.path)
            with open(tool.path, encoding="utf-8", errors="replace") as fh:
                code = fh.read()
            ns = {"__name__": "__main__", "__file__": tool.path,
                  "App": FreeCAD, "FreeCAD": FreeCAD, "Gui": FreeCADGui,
                  "FreeCADGui": FreeCADGui}
            exec(compile(code, tool.path, "exec"), ns)   # noqa: S102
            doc = _active_doc()
            if doc is not None:
                doc.recompute()
            return "Makro „%s“ ausgeführt." % tool.name
        if tool.kind in ("befehl", "addon"):
            cmd = tool.command.split(",")[0] if tool.command else ""
            if not cmd:
                raise T2GTools.ToolError(
                    "„%s“ meldet keinen Befehl." % tool.name)
            vorher = len((_active_doc().Objects if _active_doc() else []))
            FreeCADGui.runCommand(cmd, 0)
            FreeCADGui.updateGui()
            doc = _active_doc()
            if doc is not None:
                doc.recompute()
            nachher = len(doc.Objects) if doc is not None else 0
            return ("Befehl %s ausgelöst (%d neue(s) Objekt(e))."
                    % (cmd, max(0, nachher - vorher)))
        if tool.kind == "python":
            werte = self._parse_args(args_text)
            ergebnis = T2GTools.call_python_tool(tool, **werte)
            return "%s(%s) → %s" % (
                tool.name, ", ".join("%s=%r" % kv for kv in werte.items()),
                str(ergebnis)[:400])
        raise T2GTools.ToolError("Unbekannte Werkzeugart: %s" % tool.kind)

    # ---- helper tools of the project --------------------------------------

    def _build_project_tools_group(self) -> QGroupBox:
        box = QGroupBox("Werkzeuge (Rechenhilfen des Projekts)")
        v = QVBoxLayout(box)
        row = QHBoxLayout()
        self.prj_tool_combo = QComboBox()
        row.addWidget(self.prj_tool_combo, 1)
        self.prj_tool_tries = QSpinBox()
        self.prj_tool_tries.setRange(1, 6)
        self.prj_tool_tries.setValue(3)
        self.prj_tool_tries.setPrefix("Versuche ")
        row.addWidget(self.prj_tool_tries)
        self.prj_tool_btn = QPushButton("Werkzeug erzeugen")
        self.prj_tool_btn.setToolTip(
            "Modell schreibt das Modul samt Selbsttest; der Selbsttest wird "
            "ausgeführt, bevor die Datei gespeichert wird")
        self.prj_tool_btn.clicked.connect(self._prj_tool_generate)
        row.addWidget(self.prj_tool_btn)
        v.addLayout(row)
        self.prj_tool_status = QLabel("")
        self.prj_tool_status.setWordWrap(True)
        v.addWidget(self.prj_tool_status)
        self._prj_tool_state: dict = {}
        return box

    def _prj_tool_refresh(self) -> None:
        self.prj_tool_combo.clear()
        p = self._project
        if p is None or not p.tools:
            self.prj_tool_combo.addItem("– keine Werkzeuge geplant –", "")
            return
        for t in p.tools:
            have = t.get("file") and os.path.isfile(t["file"])
            self.prj_tool_combo.addItem(
                "%s%s – %s" % ("✓ " if have else "", t["name"],
                               t.get("purpose", "")), t["name"])

    def _prj_tool_generate(self) -> None:
        try:
            p = self._prj_require()
            name = self.prj_tool_combo.currentData()
            if not name:
                raise T2GProject.ProjectError(
                    "Kein Werkzeug gewählt – erst planen und übernehmen.")
            cfg, pi = self._learn_backend()
        except Exception as e:  # noqa: BLE001
            self.prj_tool_status.setText(str(e))
            return
        entry = next((t for t in p.tools if t["name"] == name), None)
        self._prj_tool_state = {
            "name": name, "purpose": (entry or {}).get("purpose", ""),
            "cfg": cfg, "pi": pi, "attempt": 1,
            "max_tries": self.prj_tool_tries.value(),
            "code": "", "problems": []}
        self._prj_tool_request()

    def _prj_tool_request(self) -> None:
        st = self._prj_tool_state
        prompt = T2GCore.build_tool_prompt(
            st["name"], st["purpose"], self._project.as_prompt_block(),
            st.get("code", ""), st.get("problems") or None)
        self.prj_tool_btn.setEnabled(False)
        self._start_elapsed(
            "Versuch %d/%d: Modell schreibt %s …"
            % (st["attempt"], st["max_tries"], st["name"]),
            self.prj_tool_status.setText)
        self._prj_worker = _TextWorker(prompt, T2GCore.TOOL_CODE_PROMPT,
                                       T2GCore.with_thinking(st["cfg"], "high"),
                                       st["pi"], tag="werkzeug")
        self._prj_worker.done.connect(self._prj_tool_done)
        self._prj_worker.start()

    def _prj_tool_done(self, payload: dict) -> None:
        self._stop_elapsed()
        st = self._prj_tool_state
        if payload.get("error"):
            self.prj_tool_btn.setEnabled(True)
            self.prj_tool_status.setText("Fehlgeschlagen: " + payload["error"])
            self._job_finished(False, "werkzeug_erzeugen: " + payload["error"])
            return
        try:
            code = T2GCore.parse_tool_code(payload["text"])
        except Exception as e:  # noqa: BLE001
            problems, funcs = [str(e)], []
            code = payload["text"][:2000]
        else:
            problems, funcs = T2GProject.validate_tool_source(code)
            if not problems:
                return self._prj_tool_save(code, funcs)

        st["code"] = code
        st["problems"] = problems
        self.log_edit.appendPlainText(
            "Werkzeug %s, Versuch %d gescheitert:\n  - %s"
            % (st["name"], st["attempt"], "\n  - ".join(problems)))
        if st["attempt"] >= st["max_tries"]:
            self.prj_tool_btn.setEnabled(True)
            msg = ("Nach %d Versuchen nicht gelungen: %s"
                   % (st["attempt"], "; ".join(problems[:2])))
            self.prj_tool_status.setText(msg)
            self._job_finished(False, "werkzeug_erzeugen %s: %s" % (st["name"], msg))
            return
        st["attempt"] += 1
        self._prj_tool_request()

    def _prj_tool_save(self, code: str, funcs: list) -> None:
        st = self._prj_tool_state
        p = self._project
        try:
            path = p.write_tool(st["name"], code, st["purpose"])
        except Exception as e:  # noqa: BLE001
            self.prj_tool_btn.setEnabled(True)
            self.prj_tool_status.setText("Speichern fehlgeschlagen: " + str(e))
            return
        p.write_agent_d()
        p.save()
        self.prj_tool_btn.setEnabled(True)
        self._prj_tool_refresh()
        msg = ("Werkzeug „%s“ erzeugt und geprüft (Selbsttest bestanden), "
               "Funktionen: %s\n%s"
               % (st["name"], ", ".join(funcs) or "–", path))
        self.prj_tool_status.setText(msg)
        self.log_edit.appendPlainText(msg + "\n--- Modul ---\n" + code)
        self._job_finished(True, "Werkzeug %s erzeugt, Funktionen: %s"
                           % (st["name"], ", ".join(funcs) or "–"))

    # ---- refining an existing skill ---------------------------------------

    def _build_skill_refine_group(self) -> QGroupBox:
        box = QGroupBox("Skill verfeinern (vorhandenen Generator überarbeiten)")
        form = QFormLayout(box)
        self.ref_goal = QPlainTextEdit()
        self.ref_goal.setPlaceholderText(
            "Was soll besser werden? z. B. „Übergang zum Ventilsitz kegelig, "
            "Wandstärke überall einhalten“ – leer = allgemein verbessern")
        self.ref_goal.setMaximumHeight(56)
        form.addRow("Auftrag:", self.ref_goal)

        row = QHBoxLayout()
        self.ref_use_project = QCheckBox("Projektkontext + Gewichte verwenden")
        self.ref_use_project.setChecked(True)
        row.addWidget(self.ref_use_project)
        row.addStretch(1)
        self.ref_tries = QSpinBox()
        self.ref_tries.setRange(1, 6)
        self.ref_tries.setValue(3)
        self.ref_tries.setPrefix("Versuche ")
        row.addWidget(self.ref_tries)
        self.ref_btn = QPushButton("Skill verfeinern")
        self.ref_btn.setToolTip(
            "Überarbeitet den oben gewählten Skill. Die bisherige Fassung "
            "wird als .bak gesichert.")
        self.ref_btn.clicked.connect(self._skill_refine)
        row.addWidget(self.ref_btn)
        form.addRow(row)

        self.ref_status = QLabel("")
        self.ref_status.setWordWrap(True)
        form.addRow(self.ref_status)
        self._refine_state: dict = {}
        return box

    @staticmethod
    def _describe_build(shapes: list) -> str:
        """One line about what a skill currently produces."""
        if not shapes:
            return "keine Solids"
        try:
            vol = sum(float(getattr(s, "Volume", 0.0) or 0.0) for s in shapes)
            xs = [s.BoundBox for s in shapes]
            lo = (min(b.XMin for b in xs), min(b.YMin for b in xs),
                  min(b.ZMin for b in xs))
            hi = (max(b.XMax for b in xs), max(b.YMax for b in xs),
                  max(b.ZMax for b in xs))
            return ("%d Solid(s), Volumen %.0f mm^3, Hüllquader "
                    "%.0f x %.0f x %.0f mm"
                    % (len(shapes), vol, hi[0] - lo[0], hi[1] - lo[1],
                       hi[2] - lo[2]))
        except Exception:  # noqa: BLE001
            return "%d Solid(s)" % len(shapes)

    def _skill_refine(self) -> None:
        name = self.skill_combo.currentText().strip()
        if name in ("", "<wählen>"):
            self.ref_status.setText("Oben zuerst einen Skill wählen.")
            return
        try:
            cfg, pi = self._learn_backend()
            eng = self._skills_engine(reload=True)
            loaded = eng.registry.get(name)
        except Exception as e:  # noqa: BLE001
            self.ref_status.setText(str(e))
            return

        params = [(p.name, p.label, p.unit, p.default, p.min, p.max)
                  for p in loaded.definition.params]
        try:
            shapes, _vals, _probs = eng.build(name)
            measured = self._describe_build(shapes)
        except Exception as e:  # noqa: BLE001
            measured = "Bau mit Standardwerten scheitert derzeit: %s" % e

        ctx = ""
        if self.ref_use_project.isChecked() and self._project is not None:
            ctx = self._project.as_prompt_block()

        self._refine_state = {
            "name": name, "params": params,
            "code": T2GSkills.build_source(loaded),
            "description": loaded.definition.description,
            "rules": list(loaded.definition.pruefregeln) or
                     ["kollision", "konnektivitaet"],
            "dir": os.path.dirname(os.path.dirname(loaded.definition.path)),
            "before": measured, "ctx": ctx,
            "goal": self.ref_goal.toPlainText(),
            "cfg": cfg, "pi": pi, "attempt": 1,
            "max_tries": self.ref_tries.value(),
            "try_code": "", "problems": []}
        self.log_edit.appendPlainText(
            "Verfeinere %s – vorher: %s" % (name, measured))
        self._refine_request()

    def _refine_request(self) -> None:
        st = self._refine_state
        prompt = T2GCore.build_skill_refine_prompt(
            st["name"], st["params"], st["code"], st["goal"], st["ctx"],
            st["before"], st.get("try_code", ""), st.get("problems") or None)
        self.ref_btn.setEnabled(False)
        self._start_elapsed(
            "Versuch %d/%d: Modell überarbeitet %s …"
            % (st["attempt"], st["max_tries"], st["name"]),
            self.ref_status.setText)
        self._refine_worker = _TextWorker(prompt, T2GCore.SKILL_REFINE_PROMPT,
                                          T2GCore.with_thinking(st["cfg"], "high"),
                                          st["pi"], tag="verfeinern")
        self._refine_worker.done.connect(self._refine_done)
        self._refine_worker.start()

    def _refine_done(self, payload: dict) -> None:
        self._stop_elapsed()
        st = self._refine_state
        if payload.get("error"):
            self.ref_btn.setEnabled(True)
            self.ref_status.setText("Fehlgeschlagen: " + payload["error"])
            self._job_finished(False, "skill_verfeinern: " + payload["error"])
            return
        try:
            code, new_params = T2GCore.parse_skill_refinement(payload["text"])
        except Exception as e:  # noqa: BLE001
            problems = [str(e)]
            code, new_params = payload["text"][:2000], []
        else:
            params = new_params or st["params"]
            problems, shapes = T2GSkills.validate_skill_source(
                st["name"], params, code, pruefregeln=st["rules"])
            if not problems:
                return self._refine_save(code, params, shapes)

        st["try_code"] = code
        st["problems"] = problems
        self.log_edit.appendPlainText(
            "Verfeinerung Versuch %d gescheitert:\n  - %s"
            % (st["attempt"], "\n  - ".join(problems)))
        if st["attempt"] >= st["max_tries"]:
            self.ref_btn.setEnabled(True)
            msg = ("Nach %d Versuchen nicht gelungen – die bisherige Fassung "
                   "bleibt unverändert. %s"
                   % (st["attempt"], "; ".join(problems[:2])))
            self.ref_status.setText(msg)
            self._job_finished(False, "skill_verfeinern %s: %s" % (st["name"], msg))
            return
        st["attempt"] += 1
        self._refine_request()

    def _refine_save(self, code: str, params: list, shapes: list) -> None:
        st = self._refine_state
        desc = st["description"]
        if "verfeinert" not in desc.lower():
            desc = (desc + " – verfeinert").strip(" –")
        try:
            path, backup = T2GSkills.update_skill(
                st["name"], desc, params, code,
                pruefregeln=st["rules"], out_dir=st["dir"])
        except Exception as e:  # noqa: BLE001
            self.ref_btn.setEnabled(True)
            self.ref_status.setText("Speichern fehlgeschlagen: " + str(e))
            return
        self.ref_btn.setEnabled(True)
        after = self._describe_build(shapes)
        added = [p[0] for p in params
                 if p[0] not in [q[0] for q in st["params"]]]
        self._skill_refresh()
        idx = self.skill_combo.findText(st["name"])
        if idx >= 0:
            self.skill_combo.setCurrentIndex(idx)
        msg = ("„%s“ verfeinert (Versuch %d/%d).\n  vorher: %s\n  nachher: %s"
               % (st["name"], st["attempt"], st["max_tries"],
                  st["before"], after))
        if added:
            msg += "\n  neue Parameter: " + ", ".join(added)
        if backup:
            msg += "\n  vorherige Fassung: " + os.path.basename(backup)
        self.ref_status.setText(msg)
        self.log_edit.appendPlainText(msg + "\n--- neue build() ---\n" + code)
        self.progress_label.setText("Skill „%s“ verfeinert." % st["name"])
        self._job_finished(True, "Skill %s verfeinert: %s" % (st["name"], after))

    def _close_window(self) -> None:
        d = self.parentWidget()
        if isinstance(d, QDockWidget):
            d.close()
        else:
            self.close()

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
        for w in list(getattr(self, "_workers", [])):
            if w.isRunning():
                w.wait(3000)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Docking: panel hosted in a QDockWidget of FreeCAD's main window,
# so it can be docked (all sides), tabbed or floated natively.
# ---------------------------------------------------------------------------

_PANEL: T2GPanel | None = None
_DOCK: QDockWidget | None = None


def _get_panel() -> T2GPanel:
    """Create the shared docked panel (lazily) or re-show the existing one."""
    global _PANEL, _DOCK
    if _DOCK is not None:
        # Re-use the dock even while it is hidden; building a second one for
        # every re-open left a stack of empty "TextToGeometry" docks behind.
        if _PANEL is not None and _DOCK.widget() is not _PANEL:
            _DOCK.setWidget(_PANEL)
        _DOCK.show()
        _DOCK.raise_()
        _DOCK.activateWindow()
        return _PANEL  # type: ignore[return-value]

    if _PANEL is None:
        _PANEL = T2GPanel()
        _PANEL.setMinimumSize(420, 380)

    main = FreeCADGui.getMainWindow()
    if main is None:
        _PANEL.show()
        _PANEL.raise_()
        _PANEL.activateWindow()
        return _PANEL
    # a good moment to make sure the toolbar line is there as well
    try:
        ensure_toolbar_input()
    except Exception:  # noqa: BLE001
        pass

    icon = _icon("t2g-panel.svg")
    _DOCK = QDockWidget("TextToGeometry", main)
    _DOCK.setObjectName("TextToGeometry_Dock")
    _DOCK.setAllowedAreas(
        Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea
        | Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)
    _DOCK.setWidget(_PANEL)
    _DOCK.setMinimumWidth(420)
    _DOCK.setWindowIcon(QIcon(icon))
    main.addDockWidget(Qt.RightDockWidgetArea, _DOCK)
    FreeCADGui.updateGui()
    _DOCK.show()
    _DOCK.raise_()
    _DOCK.activateWindow()
    return _PANEL


# ---------------------------------------------------------------------------
# Command line in the workbench toolbar
# ---------------------------------------------------------------------------

TOOLBAR_NAME = "T2G"
TOOLBAR_INPUT_NAME = "T2G_ToolbarInput"


def _toolbar_input() -> "QLineEdit | None":
    main = FreeCADGui.getMainWindow()
    if main is None:
        return None
    return main.findChild(QLineEdit, TOOLBAR_INPUT_NAME)


def ensure_toolbar_input() -> bool:
    """Put a command line into the workbench toolbar. Idempotent.

    FreeCAD builds the toolbar from command names only, so the widget has to be
    added afterwards -- and again whenever the toolbar is rebuilt (workbench
    switch, toolbar customisation), hence the lookup by object name.
    """
    main = FreeCADGui.getMainWindow()
    if main is None:
        return False
    existing = _toolbar_input()
    if existing is not None and existing.isVisible():
        return True
    for tb in main.findChildren(QToolBar):
        if tb.objectName() != TOOLBAR_NAME:
            continue
        if tb.findChild(QLineEdit, TOOLBAR_INPUT_NAME) is not None:
            return True
        line = QLineEdit()
        line.setObjectName(TOOLBAR_INPUT_NAME)
        line.setPlaceholderText(
            "Anweisung an TextToGeometry – z. B. „neues Zylinderkopfprojekt“ "
            "(Enter)")
        line.setToolTip(
            "Was hier eingegeben wird, führt der Agent aus; die Antwort steht "
            "im TextToGeometry-Panel rechts.")
        line.setClearButtonEnabled(True)
        line.setMinimumWidth(320)
        line.setMaximumWidth(640)
        line.returnPressed.connect(lambda ln=line: run_toolbar_input(ln))
        tb.addWidget(line)
        return True
    return False


def run_toolbar_input(line: "QLineEdit | None" = None) -> None:
    """Send what was typed in the toolbar to the panel and show the answer."""
    line = line or _toolbar_input()
    if line is None:
        return
    text = line.text().strip()
    if not text:
        return
    panel = _get_panel()                 # creates and shows the dock
    panel.main_tabs.setCurrentWidget(panel.tab_chat)
    busy = (panel._chat_worker is not None and panel._chat_worker.isRunning())
    if busy:
        panel._chat_append("System",
                           "Es läuft noch ein Schritt – bitte abwarten oder "
                           "im Panel auf „Stop“.")
        return
    line.clear()
    panel.chat_input.setPlainText(text)
    panel._chat_send()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

class T2GPanelCommand:
    """Show / restore the dockable TextToGeometry panel."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "T2G-Panel",
            "ToolTip": "TextToGeometry-Panel öffnen/wiederherstellen "
                       "(andockbar an jeder Fensterseite)",
            "Pixmap": _icon("t2g-panel.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        _get_panel()
        FreeCAD.Console.PrintMessage("TextToGeometry: Panel geöffnet.\n")


class T2GGenerateCommand:
    """Open the panel focused on the LLM-Generierung tab."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Generieren (LLM)",
            "ToolTip": "Freitext oder Varianten-Tabelle (CSV/XLSX/Spreadsheet) "
                       "-> 3D FreeCAD-Geometrie (lokales LLM, mit Zielen + "
                       "Feedback-Loop)",
            "Pixmap": _icon("t2g-generate.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        p = _get_panel()
        p.main_tabs.setCurrentWidget(p.tab_gen)
        p.prompt_edit.setFocus()
        p.raise_()
        p.activateWindow()


class T2GChatCommand:
    """Open the panel on the Dialog tab and focus the input."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Dialog",
            "ToolTip": "Im Dialog am offenen Dokument arbeiten: „ergänze eine "
                       "Bohrung“, „lege ein Bauteil an“, „baue eine Baugruppe“, "
                       "„führe eine Festigkeitsanalyse durch“ – mit Rückfragen",
            "Pixmap": _icon("t2g-chat.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        p = _get_panel()
        p.main_tabs.setCurrentWidget(p.tab_chat)
        p._chat_refresh_context()
        p.chat_input.setFocus()
        p.raise_()
        p.activateWindow()


class T2GProjectCommand:
    """Open the panel on the project tab."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Projekt",
            "ToolTip": "Projektverzeichnis anlegen, Auftrag klären, agent.d "
                       "schreiben, Skills ermitteln, Kriterien im Paarvergleich "
                       "gewichten",
            "Pixmap": _icon("t2g-project.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        p = _get_panel()
        p.main_tabs.setCurrentWidget(p.tab_project)
        p._prj_scan()
        p.raise_()
        p.activateWindow()


class T2GSkillLearnCommand:
    """Open the panel on the Skills tab, focused on the learn box."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Skill lernen",
            "ToolTip": "Komplexes Bauteil (z. B. Einlasskanal) als "
                       "parametrischen Skill lernen – mit Rückfragen und "
                       "optionaler Webrecherche",
            "Pixmap": _icon("t2g-skill-learn.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        p = _get_panel()
        p.main_tabs.setCurrentWidget(p.tab_learn)
        p._reveal(getattr(p, "_grp_learn", None))
        p.lrn_topic.setFocus()
        p.raise_()
        p.activateWindow()


class _PanelActionMixin:
    """Helper: open the panel and call a zero-arg callable; report errors."""

    @staticmethod
    def _guard(fn):
        def _run():
            p = _get_panel()
            p.raise_()
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                p.log_edit.appendPlainText(f"Fehler:\n{e}")
                p.progress_label.setText(f"Fehler: {e}")
                FreeCAD.Console.PrintError(f"TextToGeometry: {e}\n")
        return _run


class T2GSkillBuildCommand(_PanelActionMixin):
    """Build the currently selected skill into the active document."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Skill bauen",
            "ToolTip": "Gewählten Skill mit seinen Parametern bauen "
                       "(deterministisch, ohne LLM)",
            "Pixmap": _icon("t2g-skill-build.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        p = _get_panel()
        p.main_tabs.setCurrentWidget(p.tab_skill)
        _PanelActionMixin._guard(lambda: p._skill_build())()


class T2GSkillDesignCommand(_PanelActionMixin):
    """Open the panel focused on the Skill-Designer and focus the name field."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Skill-Designer",
            "ToolTip": "Neuen parametrischen Skill (Python build-Funktion) "
                       "erstellen",
            "Pixmap": _icon("t2g-skill-design.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        p = _get_panel()
        p.main_tabs.setCurrentWidget(p.tab_learn)
        _PanelActionMixin._guard(
            lambda: (p._reveal(getattr(p, "_grp_creator", None)),
                     p.sc_name.setFocus(), p.sc_name.selectAll()))()


class T2GApiTestCommand(_PanelActionMixin):
    """Run the backend connection test in the panel's API group."""

    def GetResources(self) -> dict:
        return {
            "MenuText": "Backend testen",
            "ToolTip": "LLM-Backend prüfen und bei Bedarf Ollama starten",
            "Pixmap": _icon("t2g-backend.svg"),
        }

    def IsActive(self) -> bool:
        return True

    def Activated(self) -> None:
        p = _get_panel()
        p.main_tabs.setCurrentWidget(p.tab_api)
        _PanelActionMixin._guard(lambda: p._api_test())()


# Register the commands (FreeCADGui is already imported above).
FreeCADGui.addCommand("T2G_Panel", T2GPanelCommand())
FreeCADGui.addCommand("T2G_Chat", T2GChatCommand())
FreeCADGui.addCommand("T2G_Project", T2GProjectCommand())
FreeCADGui.addCommand("T2G_Generate", T2GGenerateCommand())
FreeCADGui.addCommand("T2G_SkillBuild", T2GSkillBuildCommand())
FreeCADGui.addCommand("T2G_SkillLearn", T2GSkillLearnCommand())
FreeCADGui.addCommand("T2G_SkillDesign", T2GSkillDesignCommand())
FreeCADGui.addCommand("T2G_ApiTest", T2GApiTestCommand())
