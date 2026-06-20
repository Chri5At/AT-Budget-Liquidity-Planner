🇬🇧 [English](README.md) · 🇩🇪 **Deutsch**

# Budget- & Liquiditätsplanung

**Kostenlose Open-Source-Software für Budget- und Liquiditätsplanung für
österreichische Unternehmen.** Plane dein Budget, prognostiziere die Liquidität
(Cashflow) und sieh deine Gewinn- und Verlustrechnung (GuV) — alles in einer
lokalen App, als Excel-freie Alternative zur Finanzplanung. Mit integrierter
österreichischer Lohn- und Abgabenlogik (ÖGK / Finanzamt) und Banktag-Regeln —
passend für GmbHs, Start-ups und KMU in Österreich.

Lokale Web-App (NiceGUI + SQLite) für die **Budget- und Liquiditätsplanung eines
österreichischen Unternehmens** (jede Rechtsform — GmbH, Einzelunternehmen usw.).
Sie ersetzt verknüpfte Excel-Dateien: **eine Datenbank
ist die einzige Quelle der Wahrheit**, GuV (Budget) und Liquidität sind nur zwei
*Sichten* auf dieselben Daten — keine fragilen Querverweise, kein `#REF!`.

Alles läuft **lokal auf deinem Rechner**. Es werden keine Daten in die Cloud oder
an Dritte gesendet.

> **Hinweis zu den Beispieldaten:** Beim ersten Start werden **frei erfundene
> Demodaten** geladen (Firma „Muster GmbH", Mitarbeiter „A. Beispiel", „B. Muster"
> … mit runden Platzhalterzahlen). Sie dienen nur dazu, die App zu illustrieren,
> und sind in der Oberfläche vollständig editierbar. Deine echten Planungsdaten
> liegen ausschließlich in `data/planung.sqlite` und werden **nie** mit Git
> eingecheckt (siehe `.gitignore`).

## Schnellstart (Windows)

### Variante A — Python + venv (Standard)

```powershell
# einmalig: virtuelle Umgebung + Abhängigkeiten
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# starten
.\.venv\Scripts\python run.py
```

### Variante B — mit uv (schneller)

[uv](https://docs.astral.sh/uv/) ist ein moderner, sehr schneller Python-Paket-
und Umgebungsmanager.

```powershell
# Umgebung anlegen + Abhängigkeiten installieren
uv venv
uv pip install -r requirements.txt
# (oder, über pyproject.toml:  uv sync )

# starten
uv run run.py
```

Danach öffnet sich der Browser automatisch (Standard-Port **8137**, mit
automatischem Ausweichen auf den nächsten freien Port).
Alternativ unter Windows: Doppelklick auf `start.bat`.

> **Voraussetzung:** Python **3.11 oder neuer**.

## Für Endnutzer ohne Python (geplant)

Für nicht-technische Anwender sind **fertige Windows-Installer (eine `.exe`,
erstellt mit PyInstaller)** geplant. Sobald verfügbar, findest du sie unter
**[Releases](../../releases)** — dann ist keine Python-Installation nötig.

## Reiter

- **Mitarbeiter** — Mitarbeiter anlegen, monatliche Brutto-Matrix bearbeiten
  (Doppelgehalt Jun/Nov = Sonderzahlung), Live-Vorschau Netto/Abgaben.
- **Einnahmen** — Einnahmequellen (Produkt / wiederkehrend / Projekt / einmalig)
  mit Zahlungsziel.
- **Kosten** — Kostenkategorien je P&L-Zuordnung (Material / Wareneinsatz /
  bezogene Leistungen / OPEX).
- **GuV / Budget** — Deckungsbeitragsrechnung (DB I/II, EBITDA, EBIT, EBT),
  automatisch berechnet.
- **Liquidität** — Geldfluss in 15.-/Monatsende-Buckets mit laufendem
  Kontostand (mit & ohne EU-Förderung) und Verlaufsgrafik.
- **Szenarien** — ein Basis-Plan plus abgeleitete Was-wäre-wenn-Szenarien. Ein
  abgeleitetes Szenario erbt alle Einnahmen/Kosten der Basis; einzelne
  Basis-Positionen lassen sich ab-/zuschalten und eigene hinzufügen — der Effekt
  wird in GuV und Liquidität verglichen.
- **Einstellungen** — Aufteilungsmodell, Prozentsätze, Anfangskontostand,
  Planungszeitraum.

## Gehalt → Liquidität (Österreich)

Pro Monat wird das Bruttogehalt aufgeteilt:
- **Netto** → Auszahlung am **letzten Banktag** des Monats.
- **Abgaben** (Finanzamt / ÖGK) → **15. des Folgemonats** (bei Wochenende/
  Feiertag in Österreich der vorherige Banktag).

Zwei umschaltbare Modelle (Einstellungen):
- **Fixer Prozentsatz** (Standard): Abgaben = Gesamtkosten × Abgaben-% (Default 30 %).
- **Buchhalterisch genau**: Abgaben = Brutto + LNK − Netto.

> Die Lohn-/Abgabenlogik (ÖGK, Finanzamt-Termine, österreichische Feiertage) ist
> **Österreich-spezifisch** (das Bundesland für regionale Feiertage ist
> einstellbar, Standard: Oberösterreich). Für andere Länder müssten diese Regeln
> angepasst werden.

## Tests

```powershell
.\.venv\Scripts\python -m pip install pytest pytest-asyncio selenium
.\.venv\Scripts\python -m pytest -q
```

Engine-Tests (Banktag-/Feiertagslogik, beide Aufteilungsmodelle, Reconciliation)
plus ein Headless-UI-Smoke-Test.

## Technik

- **Python** (lokale `.venv`, nichts global installiert)
- **NiceGUI** — UI in reinem Python
- **SQLite** Einzeldatei via **SQLModel**
- UI auf Deutsch (österreichische Begriffe), Code/Kommentare auf Englisch

## Lizenz

Veröffentlicht unter der **[MIT-Lizenz](LICENSE)** — du darfst die Software
**kostenlos nutzen, verändern und weitergeben, auch kommerziell**. Einzige
Bedingung: Der Copyright- und Lizenzhinweis muss erhalten bleiben.

Wenn du das Projekt verwendest oder darauf aufbaust, **verlinke bitte das
Originalprojekt** als Quelle. 🙏

© 2026 Chri5At
