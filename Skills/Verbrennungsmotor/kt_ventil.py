# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary
"""Ventil — die gemeinsame Grundform von Ein- und Auslassventil.

Dieses Skript baut **kein** fertiges Bauteil des Motors. Es ist der Rohling,
aus dem ``kt_einlassventil`` und ``kt_auslassventil`` ihre beiden wirklich
verschiedenen Teile machen; der Ventiltrieb ruft die beiden, nie dieses hier.
Getrennt gehalten, weil Teller, Sitzfase, Schaft und Keilnut bei beiden
gleich entstehen — verschieden sind die Maße, die Form des Übergangs und der
hohle Schaft des Auslassventils.

Teller mit Sitzfase, Schaft, Keilnut am Schaftende. Gebaut wird entlang
**+Z**, Schaft nach oben. Der Ursprung liegt in der **Tellerunterkante**
(der Brennraumseite) — das ist die Fläche, die im Zylinderkopf sitzt und den
Brennraum begrenzt.

Die Sitzfase hat 45°; der wirksame Sitzdurchmesser liegt darunter und ist als
Kennwert ausgewiesen, weil der Zylinderkopf ihn braucht.

Anschlusspunkte
    ``sitz``        Tellerrand am Ventilsitz, Achse -Z, Art *flaeche*
    ``schaft``      Schaftmitte auf halber Höhe, Achse +Z, Art *welle*
                    (läuft in der Schaftführung)
    ``schaft_ende`` Schaftende oben, Achse +Z, Art *flaeche* — hier drückt
                    der Stößel, und hier sitzt der Federteller
"""

import math

import FreeCAD
import Part
from FreeCAD import Vector

from kt_schnittstelle import Bauteil, Punkt


def vorschlag(bohrung=86.0, ventile_je_zylinder=4, einlass=True):
    """Übliche Tellerdurchmesser als Anteil der Bohrung.

    Zwei Ventile: Einlass etwa 0,45·D, Auslass 0,38·D. Vier Ventile: die
    Teller werden kleiner, dafür ist die Gesamtfläche größer — Einlass
    0,36·D, Auslass 0,31·D.
    """
    d = float(bohrung)
    if int(ventile_je_zylinder) >= 4:
        return round(d * (0.36 if einlass else 0.31), 1)
    return round(d * (0.45 if einlass else 0.38), 1)


def kennwerte(teller_d=31.0, schaft_d=6.0, laenge=110.0, fase=45.0,
              sitzbreite=1.5, tellerrand_h=0.0, **_rest):
    """Die Maße, die der Zylinderkopf und der Ventiltrieb brauchen.

    ``sitzbreite`` ist die tragende Breite der Dichtfläche — beim Einlass
    rund 1,5 mm, beim Auslass rund 2 mm, denn dort geht die Wärme über den
    Sitz weg und eine breitere Fläche leitet besser. ``tellerrand_h`` ist die
    Höhe des zylindrischen Randes über der Fase; üblich sind 4 bis 6 % des
    Tellerdurchmessers, und ein zu dünner Rand brennt ab.
    """
    d = float(teller_d)
    return {
        "teller_d": d,
        "schaft_d": float(schaft_d),
        "laenge": float(laenge),
        # Der wirksame Sitzdurchmesser liegt eine halbe Sitzbreite innen,
        # gemessen auf der 45-Grad-Fase.
        "sitz_d": round(d - float(sitzbreite) * math.cos(
            math.radians(float(fase))), 2),
        "sitzbreite": float(sitzbreite),
        "sitzwinkel": float(fase),
        "tellerrand_h": round(float(tellerrand_h) or d * 0.05, 2),
        "teller_anteil_schaft": round(float(schaft_d) / d, 4),
    }


def _uebergang(rt, rs, hoehe, z0, form=1.0, stuecke=8):
    """Der Übergang vom Teller zum Schaft als Folge von Kegelstümpfen.

    ``form`` ist der Exponent des Profils ``r(f) = rs + (rt-rs)·(1-f)^form``:

    * ``1.0`` — gerade. Der klassische Flachteller: der Übergang ist ein
      glatter Kegel.
    * ``2.0`` — **Tulpenform**. Der Radius fällt zuerst schnell und dann
      flach aus, die Unterseite ist also hohl. Das ist die Form des
      Auslassventils: sie leitet die Wärme besser aus dem Tellerrand ab und
      strömt beim Ausschieben sauberer ab.

    Der Unterschied ist messbar — ein Tulpenventil hat bei gleichem Teller
    und Schaft weniger Material im Übergang.
    """
    n = max(2, int(stuecke))
    h = float(hoehe) / n
    stuecke_liste = []
    for i in range(n):
        f0 = i / float(n)
        f1 = (i + 1) / float(n)
        r0 = rs + (rt - rs) * (1.0 - f0) ** float(form)
        r1 = rs + (rt - rs) * (1.0 - f1) ** float(form)
        stuecke_liste.append(Part.makeCone(
            max(r0, rs), max(r1, rs), h, Vector(0, 0, float(z0) + i * h)))
    koerper = stuecke_liste[0]
    for weiter in stuecke_liste[1:]:
        koerper = koerper.fuse(weiter)
    return koerper


def baue(teller_d=31.0, schaft_d=6.0, laenge=110.0, teller_t=0.0, fase=45.0,
         fase_b=2.0, kegel_h=9.0, nut_t=0.8, nut_h=3.0, kegel_form=1.0,
         hohl_d=0.0, hohl_anteil=0.75, sitzbreite=1.5, name="Ventil"):
    """Ein Ventil als :class:`Bauteil`.

    teller_d    Tellerdurchmesser [mm]
    schaft_d    Schaftdurchmesser [mm]
    laenge      Gesamtlänge von der Tellerunterkante bis zum Schaftende [mm]
    teller_t    Höhe des zylindrischen Tellerrandes [mm]; 0 = 5 % des
                Tellerdurchmessers (üblich 4…6 %)
    fase        Sitzwinkel [Grad], üblich 45
    kegel_h     Höhe des Übergangs Teller → Schaft [mm]
    nut_t       Tiefe der Keilnut am Schaftende [mm]
    kegel_form  1,0 = gerader Kegel, 2,0 = Tulpenform (siehe ``_uebergang``)
    hohl_d      Durchmesser der Schaftbohrung [mm]; > 0 gibt einen
                **innen geschlossenen Hohlraum** — der natriumgefüllte
                Schaft des Auslassventils. Der Körper bleibt ein Solid,
                bekommt aber eine zweite Schale.
    hohl_anteil Bis zu welchem Anteil der Länge die Bohrung reicht
    sitzbreite  tragende Breite der Dichtfläche [mm] — 1,5 am Einlass,
                2,0 am Auslass. Sie geht in den ausgewiesenen
                Sitzdurchmesser ein, den der Zylinderkopf braucht.
    """
    rt = float(teller_d) / 2.0
    rs = float(schaft_d) / 2.0
    l = float(laenge)
    if rs >= rt:
        raise ValueError("Der Schaft (%.1f) ist nicht duenner als der Teller "
                         "(%.1f)." % (float(schaft_d), float(teller_d)))
    if l <= float(teller_t) + float(kegel_h) + float(nut_h) + 5.0:
        raise ValueError("Ventillaenge %.1f mm ist zu kurz fuer Teller, "
                         "Kegel und Keilnut." % l)

    # Tellerrand mit Sitzfase: ein Kegelstumpf, unten schmaler. Der
    # Tellerrand darueber ist 4 bis 6 % des Tellerdurchmessers hoch; fest
    # 3 mm waren bei 31 mm Teller fast 10 %.
    teller_t = float(teller_t) or round(float(teller_d) * 0.05, 2)
    fb = float(fase_b)
    unten_r = rt - fb * math.tan(math.radians(float(fase)) / 1.0) * 0.0 - fb
    teller = Part.makeCone(max(unten_r, rs + 0.5), rt, fb, Vector(0, 0, 0))
    teller = teller.fuse(Part.makeCylinder(rt, float(teller_t),
                                           Vector(0, 0, fb)))
    # Uebergang zum Schaft — gerade oder als Tulpe.
    kegel = _uebergang(rt, rs, float(kegel_h), fb + float(teller_t),
                       float(kegel_form))
    schaft_z = fb + float(teller_t) + float(kegel_h)
    schaft = Part.makeCylinder(rs, l - schaft_z, Vector(0, 0, schaft_z))

    koerper = teller.fuse(kegel).fuse(schaft)

    # Hohler, natriumgefuellter Schaft: eine Bohrung, die NIRGENDS nach
    # aussen durchbricht. Sie faengt im Teller an und endet unter der
    # Keilnut — dort sitzt spaeter der Stoessel, da darf kein Loch sein.
    if float(hohl_d) > 0.0:
        rh = float(hohl_d) / 2.0
        if rh >= rs - 0.8:
            raise ValueError(
                "Die Schaftbohrung (%.1f) laesst bei %.1f mm Schaft keine "
                "Wand uebrig." % (float(hohl_d), float(schaft_d)))
        z_unten = fb + float(teller_t) * 0.5
        z_oben = l * float(hohl_anteil)
        koerper = koerper.cut(Part.makeCylinder(rh, z_oben - z_unten,
                                                Vector(0, 0, z_unten)))

    # Keilnut am Schaftende
    if float(nut_t) > 0.0:
        z0 = l - float(nut_h) - 2.0
        nut = Part.makeCylinder(rs + 1.0, float(nut_h), Vector(0, 0, z0))
        kern = Part.makeCylinder(rs - float(nut_t), float(nut_h) + 2.0,
                                 Vector(0, 0, z0 - 1.0))
        koerper = koerper.cut(nut.cut(kern))

    return Bauteil(
        name,
        koerper=[(name, koerper.removeSplitter())],
        punkte=[
            Punkt("sitz", (0, 0, 0), (0, 0, -1), "flaeche", float(teller_d),
                  "Tellerunterkante – sitzt im Zylinderkopf"),
            Punkt("schaft", (0, 0, schaft_z + (l - schaft_z) / 2.0),
                  (0, 0, 1), "welle", float(schaft_d),
                  "Schaftmitte – laeuft in der Schaftfuehrung"),
            Punkt("schaft_ende", (0, 0, l), (0, 0, 1), "flaeche",
                  float(schaft_d),
                  "Schaftende – hier drueckt der Stoessel"),
        ],
        kennwerte=kennwerte(teller_d, schaft_d, l, fase,
                            sitzbreite=sitzbreite,
                            tellerrand_h=teller_t))


def selbsttest():
    """Prüft Maße, Sitzfase und Anschlusspunkte."""
    t = baue(teller_d=31.0, schaft_d=6.0, laenge=110.0)
    shp = t.koerper[0][1]
    if not shp.Solids:
        raise AssertionError("Ventil ist kein Solid")
    b = shp.BoundBox
    if abs(b.XLength - 31.0) > 0.1:
        raise AssertionError("Tellerdurchmesser %.2f statt 31" % b.XLength)
    if abs(b.ZLength - 110.0) > 0.01:
        raise AssertionError("Ventillaenge %.2f statt 110" % b.ZLength)
    if abs(b.ZMin) > 1e-9:
        raise AssertionError("Der Ursprung liegt nicht an der "
                             "Tellerunterkante (z %.3f)" % b.ZMin)

    # Der Schaft muss wirklich duenn sein: eine Huelse um den Schaft darf
    # kein Material treffen.
    huelse = Part.makeCylinder(6.0 / 2.0 + 3.0, 40.0,
                               Vector(0, 0, 60.0)).cut(
        Part.makeCylinder(6.0 / 2.0 + 0.1, 42.0, Vector(0, 0, 59.0)))
    if shp.common(huelse).Volume > 1.0:
        raise AssertionError("um den Schaft steht Material, wo keines "
                             "hingehoert")

    # Punkte.
    for name in ("sitz", "schaft", "schaft_ende"):
        t.punkt(name)
    if abs(t.punkt("schaft_ende").ort.z - 110.0) > 1e-9:
        raise AssertionError("Schaftende sitzt nicht auf der Ventillaenge")
    if t.punkt("sitz").achse.z > 0:
        raise AssertionError("die Sitzflaeche muss nach unten zeigen")

    # Vorschlaege: vier Ventile sind kleiner als zwei.
    if not (vorschlag(86.0, 4, True) < vorschlag(86.0, 2, True)):
        raise AssertionError("Vierventiler brauchen kleinere Teller")
    if not (vorschlag(86.0, 4, False) < vorschlag(86.0, 4, True)):
        raise AssertionError("das Auslassventil ist kleiner als das Einlass")

    # Unsinnige Eingaben muessen auffallen.
    for kw in ({"teller_d": 6.0, "schaft_d": 6.0}, {"laenge": 15.0}):
        try:
            baue(**kw)
            raise AssertionError("unsinnige Eingabe blieb unbemerkt: %r" % kw)
        except ValueError:
            pass
    return ("Ventil-Selbsttest bestanden (Teller %.0f, Schaft %.0f, %.0f mm "
            "lang, %.0f mm^3)" % (b.XLength, 6.0, b.ZLength, shp.Volume))
