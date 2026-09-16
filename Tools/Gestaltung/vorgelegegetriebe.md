<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Vorgelegegetriebe — geometrische Gestaltung

Skript: `Tools/getriebe_fcgear.py`, `bauart="vorgelege"`

## Was die Bauform ausmacht

Ein längs eingebauter Motor braucht den Abtrieb **hinten auf der
Kurbelwellenachse**. Das leistet nur das Vorgelegegetriebe:

```
Motor ─► Antriebswelle ──┤Zapfen├── Hauptwelle ─► Abtrieb     (y = 0)
             │ Konstante                  ▲ Gangpaar
             ▼                            │
          Vorgelegewelle ─────────────────┘                   (y = a)
```

- **Antriebswelle und Hauptwelle liegen auf derselben Achse.** Die
  Antriebswelle endet hinter dem Konstantenrad und stützt sich mit einem
  Zapfen im aufgebohrten Vorderende der Hauptwelle ab (Pilotlager).
- Die **Vorgelegewelle** liegt achsversetzt darunter (oder darüber — das ist
  eine Frage des Einbaus).
- Das **Konstantenpaar** (Antriebskonstante) sitzt motorseitig und treibt die
  Vorgelegewelle dauernd an.
- Die **Festräder** sitzen auf der Vorgelegewelle, die **Losräder** auf der
  Hauptwelle. Eine Schaltmuffe kuppelt das gewählte Losrad mit der
  Hauptwelle.
- Der **direkte Gang**: die vorderste Muffe greift über den Wellenstoß und
  kuppelt Antriebswelle und Hauptwelle unmittelbar. Die Vorgelegewelle läuft
  leer mit, ohne Moment zu übertragen — i = 1, und das ist der
  wirkungsgradbeste Gang.

## Die Übersetzung ist ein Produkt

Weil der Kraftfluss über **zwei** Radpaare geht:

```
i = (z_VK / z_AK) · (z_Losrad / z_Festrad)
```

Alle Paare — auch die Konstante — laufen auf **einem** Achsabstand, also ist
`z1 + z2` überall dieselbe Summe. Das begrenzt die Spreizung: gemessen an
einem Sechsganggetriebe mit z-Summe 69 und Konstante 32/37 (i = 1,156)
ergeben sich

| Gang | Festrad | Losrad | i |
|---|---|---|---|
| 1 | 17 | 52 | 3,54 |
| 2 | 19 | 50 | 3,04 |
| 3 | 21 | 48 | 2,64 |
| 4 | 23 | 46 | 2,31 |
| 5 | 25 | 44 | 2,04 |
| 6 | 27 | 42 | 1,80 |
| direkt | — | — | 1,00 |

Der Sprung vom sechsten zum direkten Gang ist groß. Ein echtes Getriebe legt
deshalb den direkten Gang **in die Reihe** (meist als vierten oder fünften)
und setzt einen Schongang dahinter; das wäre der nächste Schritt.

## Zwei Dinge, die die Durchdringungsprüfung gezeigt hat

1. **Der Zentrierzapfen braucht eine Bohrung.** Als bloßer Zylinder auf der
   Stirnfläche der Hauptwelle stak er zu 100 % im Vollmaterial. Real ist die
   Hauptwelle vorn aufgebohrt und trägt dort das Pilotlager.
2. **Am hinteren Ende der Antriebswelle gehört kein Lagersitz hin**, sondern
   die Kupplungsverzahnung für den direkten Gang — dort schiebt sich die
   Muffe darüber. Mit einem 30-mm-Lagersitz unter einer 29-mm-Muffenbohrung
   durchdrangen sich beide um 4 %. `_welle()` nimmt deshalb
   `sitze="beide|vorn|hinten"`.

## Was offen bleibt

- **Synchronringe** — die Muffen sind unsynchronisiert dargestellt.
- **Rückwärtsgang** mit Zwischenrad.
- Der direkte Gang steht am Ende der Reihe statt in ihr.
- Das **Differential** fehlt; der Abtrieb endet an der Hauptwelle.

## Quellen

- [kfz-tech.de: Gleichachsiges Getriebe — Konstantenpaar, Fest- und Losräder, direkter Gang](https://www.kfz-tech.de/Biblio/Getriebe/GleichachsigesGetriebe.htm)
- [DE 10 2006 031 267 A1: *Getriebe in Vorgelegebauweise* — Wellenanordnung, Antriebskonstante](https://patents.google.com/patent/DE102006031267A1/de)
- [EP 1 877 681 A1: *Getriebe mit im Direktgang abkoppelbarer Vorgelegewelle*](https://patents.google.com/patent/EP1877681A1/de)
