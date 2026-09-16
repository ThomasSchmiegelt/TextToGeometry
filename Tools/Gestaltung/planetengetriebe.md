<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0-NoMilitary -->
# Planetengetriebe — geometrische Gestaltung

Skript: `Tools/planetengetriebe.py`

## Was es ausmacht

Drei Wellen auf **einer** Achse: Sonnenrad, Steg (Planetenträger), Hohlrad.
Welche antreibt, welche abtreibt und welche festgehalten wird, entscheidet
über die Übersetzung — **dasselbe** Getriebe übersetzt ins Langsame, ins
Schnelle oder rückwärts. Dazu teilt sich die Leistung auf mehrere Planeten
auf, und alles bleibt koaxial. Deshalb sitzt es in Automatikgetrieben,
Nabenschaltungen und Windkraftanlagen.

## Die vier Bedingungen

Ein Planetensatz lässt sich **nicht** aus beliebigen Zähnezahlen bauen.

**1. Achsbedingung** (Konzentrizität) — Sonne und Hohlrad brauchen denselben
Mittelpunkt:

```
z_Hohlrad = z_Sonne + 2 · z_Planet
```

**2. Montagebedingung** — gleichmäßig verteilte Planeten gehen nur, wenn

```
(z_Sonne + z_Hohlrad) / Planetenzahl    ganzzahlig ist
```

Beispiel: (24 + 66)/3 = 30 ✔, (24 + 66)/4 = 22,5 ✘ — mit vier Planeten passt
der letzte nicht mehr in die Verzahnung.

**3. Nachbarbedingung** — zwei benachbarte Planeten dürfen sich nicht
berühren. Ihr Mittenabstand ist `2a·sin(π/p)`, ihr Kopfkreis `m(z_P + 2)`:

```
(z_Sonne + z_Planet) · sin(π / p)  >  z_Planet + 2
```

**4. Übersetzung** — die Willis-Gleichung. Mit der **Standübersetzung**
(Steg festgehalten)

```
i₀ = − z_Hohlrad / z_Sonne
```

folgt:

| festgehalten | Formel | Bereich |
|---|---|---|
| Hohlrad | `i = 1 − i₀ = 1 + z_H/z_S` | 2 … ∞ (ins Langsame) |
| Sonne | `i = 1 + z_S/z_H` | 1 … 2 (ins Langsame) |
| Steg | `i = i₀ = − z_H/z_S` | −∞ … −1 (Richtungsumkehr) |

Lehrbuchbeispiel z_S = 30, z_H = 80: i₀ = −2,67, Hohlrad fest 3,67, Sonne
fest 1,375. Der Selbsttest rechnet genau diese drei Zahlen nach.

## Zähnezahlen zu einer gewünschten Übersetzung

`vorschlag(i_soll, planeten)` sucht die Kombination, die `i` am nächsten
kommt **und alle drei geometrischen Bedingungen hält**. Ohne diese Prüfung
kommt leicht ein Satz heraus, dessen Planeten sich berühren oder der sich
gar nicht montieren lässt. Gemessen, drei Planeten:

| i gewünscht | Sonne | Planet | Hohlrad | i erreicht |
|---|---|---|---|---|
| 3,0 | 34 | 17 | 68 | 3,0000 |
| 4,0 | 18 | 18 | 54 | 4,0000 |
| 5,0 | 18 | 27 | 72 | 5,0000 |
| 6,0 | 17 | 34 | 85 | 6,0000 |

## Geometrie

Gebaut wird entlang **+X**, alle drei Wellen auf y = z = 0. Achsabstand
Sonne–Planet `a = m(z_S + z_P)/2`. Das Hohlrad ist innenverzahnt und hier
als Ring ab dem Fußkreis der Innenverzahnung dargestellt — der liegt bei
einer Innenverzahnung **außerhalb** des Teilkreises.

Die **Phase** der Planeten ist nicht frei: ein Planet an der Winkelposition
φ muss dort in die Sonne greifen, also um `φ · z_S/z_P` verdreht stehen.
Nachgemessen stehen die drei Planeten auf 119,9 / 120,0 / 120,1 Grad.

Die **Stegwangen** brauchen Bohrungen für die Planetenbolzen — ohne sie stak
der Bolzen zu 21 % im Vollmaterial. Genau diese Bohrungen machen den Steg
zum Planetenträger.

## Was offen bleibt

- Das **Hohlrad ist unverzahnt** dargestellt (glatter Ring). FCGear kann
  Innenverzahnungen; sie einzusetzen wäre der nächste Schritt.
- **Schrägverzahnung** und Profilverschiebung.
- **Lagerung** der Planetenbolzen (Nadellager).
- Mehrstufige Sätze und die Schaltelemente eines Automatikgetriebes.

## Quellen

- [tec-science: Übersetzungsmöglichkeiten der Planetengetriebe (Willis-Gleichung)](https://www.tec-science.com/de/getriebe-technik/planetengetriebe/ubersetzungsmoglichkeiten-der-plantengetriebe/) — i₀, alle drei Fälle, Zahlenbeispiel
- [MITCalc: Planetary gear — Koaxialitäts-, Montage- und Nachbarbedingung](https://www.mitcalc.com/doc/gear5/help/en/gear5.htm)
- [I.CH Motion: The condition of the number of the tooth in planetary gears](https://de.ichgear.com/news/the-condition-of-the-number-of-the-tooth-in-pl-37945904.html)
- [eAssistant: Planetenstufe nach DIN 3990](https://www.eassistant.eu/fileadmin/dokumente/eassistant/etc/HTMLHandbuch/de/eAssistantHandbch9.html)
