# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Erweiterbare Eingabemaske für die Getriebe-Makros.

Ein FreeCAD-Makro bekommt keine Argumente und liefert keinen Rückgabewert —
es wird nur mit ``exec()`` ausgeführt. Wer ein Makro parametrieren will, muss
also selbst fragen. Genau dafür ist diese Maske da.

Erweitert wird sie durch **Anhängen an eine Feldliste**, nicht durch Ändern von
Code:

    FELDER = [
        Feld("modul",  "Modul",      "mm",  2.0, 0.3, 20.0, gruppe="Verzahnung"),
        Feld("art",    "Verzahnung", "",    "gerade", auswahl=["gerade",
                                                              "schraeg",
                                                              "pfeil"]),
    ]
    werte = frage_ab(FELDER, "Getriebe")     # None, wenn abgebrochen

Die Werte werden unter ``BaseApp/Preferences/Mod/TextToGeometry/masken/<id>``
gemerkt und beim nächsten Öffnen wieder vorgelegt — wer dreimal dasselbe
Getriebe mit einer anderen Wandstärke baut, tippt nicht dreimal alles neu.

Ohne laufende GUI (``FreeCADCmd``) gibt es keinen Dialog: ``frage_ab`` liefert
dann die Vorgabewerte zurück, damit Tests und der Agentenpfad durchlaufen.
"""

import FreeCAD

#: Wo die zuletzt eingegebenen Werte liegen.
PREF_PFAD = "User parameter:BaseApp/Preferences/Mod/TextToGeometry/masken"


class Feld(object):
    """Ein Eingabefeld.

    Die ersten sechs Angaben sind absichtlich dieselben wie bei den
    Skill-Parametern des Projekts (``name, label, einheit, default, min, max``),
    damit Feldlisten zwischen beiden Welten wandern können. ``auswahl`` und
    ``gruppe`` kommen dazu: Auswahlfelder gab es im 6-Tupel-Format nicht, und
    ohne Gruppen wird eine Maske mit dreißig Feldern unlesbar.
    """

    def __init__(self, name, label, einheit="", default=0.0, minimum=None,
                 maximum=None, auswahl=None, gruppe="Allgemein", hinweis=""):
        self.name = str(name)
        self.label = str(label or name)
        self.einheit = str(einheit or "")
        self.default = default
        self.minimum = minimum
        self.maximum = maximum
        self.auswahl = list(auswahl) if auswahl else []
        self.gruppe = str(gruppe or "Allgemein")
        self.hinweis = str(hinweis or "")

    @property
    def art(self):
        """``auswahl`` | ``int`` | ``float`` | ``text``."""
        if self.auswahl:
            return "auswahl"
        if isinstance(self.default, bool):
            return "auswahl"
        if isinstance(self.default, int):
            return "int"
        if isinstance(self.default, float):
            return "float"
        return "text"

    def wandle(self, roh):
        """Einen eingetippten Wert in den Typ des Feldes bringen."""
        if self.art == "int":
            return int(round(float(roh)))
        if self.art == "float":
            return float(roh)
        return roh

    def __repr__(self):
        return "Feld(%r, %r)" % (self.name, self.default)


def vorgaben(felder):
    """Die Vorgabewerte als dict — das, was ohne Dialog herauskommt."""
    return {f.name: f.default for f in felder}


# ---------------------------------------------------------------- merken --

def _gruppe(kennung):
    return FreeCAD.ParamGet("%s/%s" % (PREF_PFAD, kennung))


def gemerkt(felder, kennung):
    """Zuletzt eingegebene Werte, sonst die Vorgabe."""
    werte = vorgaben(felder)
    if not kennung:
        return werte
    try:
        p = _gruppe(kennung)
    except Exception:  # noqa: BLE001 - ohne Einstellungen eben die Vorgaben
        return werte
    for f in felder:
        try:
            if f.art == "float":
                if f.name in p.GetFloats():
                    werte[f.name] = p.GetFloat(f.name, float(f.default))
            elif f.art == "int":
                if f.name in p.GetInts():
                    werte[f.name] = p.GetInt(f.name, int(f.default))
            else:
                if f.name in p.GetStrings():
                    werte[f.name] = p.GetString(f.name, str(f.default))
        except Exception:  # noqa: BLE001 - ein kaputter Eintrag darf nicht stoppen
            continue
    return werte


def merke(felder, werte, kennung):
    """Die Eingaben für das nächste Mal behalten."""
    if not kennung:
        return
    try:
        p = _gruppe(kennung)
    except Exception:  # noqa: BLE001
        return
    for f in felder:
        if f.name not in werte:
            continue
        try:
            if f.art == "float":
                p.SetFloat(f.name, float(werte[f.name]))
            elif f.art == "int":
                p.SetInt(f.name, int(werte[f.name]))
            else:
                p.SetString(f.name, str(werte[f.name]))
        except Exception:  # noqa: BLE001
            continue


# ----------------------------------------------------------------- Dialog --

def gui_da():
    """Läuft eine Oberfläche, in der ein Dialog überhaupt erscheinen kann?"""
    if not getattr(FreeCAD, "GuiUp", False):
        return False
    try:
        from PySide6 import QtWidgets
    except ImportError:
        try:
            from PySide import QtWidgets           # noqa: F401
        except ImportError:
            return False
    return QtWidgets.QApplication.instance() is not None


def _qt():
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide import QtWidgets
    return QtWidgets


def baue_dialog(felder, titel, werte):
    """Den Dialog zusammensetzen; liefert (dialog, ausleser)."""
    Q = _qt()
    dlg = Q.QDialog()
    dlg.setWindowTitle(titel)
    dlg.setMinimumWidth(420)
    aussen = Q.QVBoxLayout(dlg)

    # Je Gruppe ein Reiter, in der Reihenfolge des ersten Auftretens.
    reihenfolge = []
    for f in felder:
        if f.gruppe not in reihenfolge:
            reihenfolge.append(f.gruppe)

    tabs = Q.QTabWidget()
    aussen.addWidget(tabs, 1)
    formulare = {}
    for g in reihenfolge:
        seite = Q.QWidget()
        formulare[g] = Q.QFormLayout(seite)
        tabs.addTab(seite, g)
    if len(reihenfolge) == 1:
        tabs.tabBar().setVisible(False)

    widgets = {}
    for f in felder:
        wert = werte.get(f.name, f.default)
        if f.art == "auswahl":
            w = Q.QComboBox()
            eintraege = f.auswahl or ["ja", "nein"]
            w.addItems([str(x) for x in eintraege])
            i = w.findText(str(wert))
            w.setCurrentIndex(i if i >= 0 else 0)
        elif f.art in ("int", "float"):
            w = Q.QDoubleSpinBox()
            w.setDecimals(0 if f.art == "int" else 3)
            w.setSingleStep(1.0 if f.art == "int" else 0.1)
            w.setMinimum(float(f.minimum) if f.minimum is not None else -1e9)
            w.setMaximum(float(f.maximum) if f.maximum is not None else 1e9)
            if f.einheit:
                w.setSuffix(" " + f.einheit)
            w.setValue(float(wert))
        else:
            w = Q.QLineEdit()
            w.setText(str(wert))
        if f.hinweis:
            w.setToolTip(f.hinweis)
        beschriftung = f.label
        if f.einheit and f.art not in ("int", "float"):
            beschriftung += " [%s]" % f.einheit
        formulare[f.gruppe].addRow(beschriftung + ":", w)
        widgets[f.name] = (f, w)

    knoepfe = Q.QDialogButtonBox(Q.QDialogButtonBox.Ok
                                 | Q.QDialogButtonBox.Cancel)
    knoepfe.accepted.connect(dlg.accept)
    knoepfe.rejected.connect(dlg.reject)
    aussen.addWidget(knoepfe)

    def auslesen():
        aus = {}
        for name, (f, w) in widgets.items():
            if f.art == "auswahl":
                aus[name] = w.currentText()
            elif f.art in ("int", "float"):
                aus[name] = f.wandle(w.value())
            else:
                aus[name] = w.text().strip()
        return aus

    return dlg, auslesen


def frage_ab(felder, titel="Eingaben", kennung=None):
    """Maske zeigen und die Werte liefern; ``None`` bei Abbruch.

    Ohne GUI (FreeCADCmd, Tests, Agentenlauf) kommen die gemerkten bzw. die
    Vorgabewerte zurück, statt dass nichts geht.
    """
    kennung = kennung or titel.lower().replace(" ", "_")
    werte = gemerkt(felder, kennung)
    if not gui_da():
        return werte
    dlg, auslesen = baue_dialog(felder, titel, werte)
    if not dlg.exec():
        return None
    werte = auslesen()
    merke(felder, werte, kennung)
    return werte


def selbsttest():
    """Prüft die Feldlogik ohne Oberfläche."""
    felder = [
        Feld("modul", "Modul", "mm", 2.0, 0.3, 20.0),
        Feld("zaehne", "Zähnezahl", "", 20, 6, 200),
        Feld("art", "Verzahnung", "", "gerade",
             auswahl=["gerade", "schraeg", "pfeil"]),
        Feld("name", "Bezeichnung", "", "6204"),
    ]
    arten = [f.art for f in felder]
    if arten != ["float", "int", "auswahl", "text"]:
        raise AssertionError("Feldarten falsch erkannt: %s" % arten)
    v = vorgaben(felder)
    if v["zaehne"] != 20 or v["art"] != "gerade":
        raise AssertionError("Vorgaben falsch: %r" % v)
    if felder[1].wandle(19.6) != 20:
        raise AssertionError("int-Wandlung rundet nicht")
    if abs(felder[0].wandle("2.5") - 2.5) > 1e-9:
        raise AssertionError("float-Wandlung aus Text schlug fehl")
    return "Maske-Selbsttest bestanden"
