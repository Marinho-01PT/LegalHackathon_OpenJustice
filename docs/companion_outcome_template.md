# Outcome template for the legal team (OpenJustice editor → outcome node → instructions / template)

The baseline engine (OpenJustice node-by-node) cannot receive our instructions via the API, so the companion
frame must live in the protocol's **outcome nodes**. Paste this into every outcome node so all three conditions
produce the same structure:

```
Formuliere als Orientierungshilfe für Mieter:innen, nicht als Entscheid. Verwende genau diese Überschriften:
## Einschätzung            – rechtliche Einschätzung mit Quellen ("spricht dafür, dass …")
## Sicherheit der Einschätzung – hoch / mittel / unsicher + warum
## ⚠ Fristen               – jede Frist mit Datum/Dauer, Rechtsgrundlage, Folge bei Verpassen. Nie abschwächen.
## Ihre Optionen           – A) … B) … mit Vor-/Nachteilen
## Nächste Schritte        – konkret: zuständige Schlichtungsbehörde (Kanton), Formular, Unterlagen, Kosten
## Fehlende Angaben        – was wir noch wissen müssten
## Wann Sie sich beraten lassen sollten – Mieterverband / Anwalt, wenn …
## Hinweis                 – "Dies ist eine Orientierungshilfe, keine Rechtsberatung und kein Entscheid. Verbindlich
                             entscheiden nur die Schlichtungsbehörde bzw. das Gericht."
```
