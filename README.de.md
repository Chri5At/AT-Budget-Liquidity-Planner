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

## ⬇️ Herunterladen & starten (ohne Installation — empfohlen)

**Noch nie GitHub benutzt? Mehr brauchst du nicht — kein Python, keine Installation.**

1. Öffne die **[Releases-Seite](https://github.com/Chri5At/AT-Budget-Liquidity-Planner/releases/latest)**.
2. Klicke unter **Assets** auf **`BudgetLiquidity-1.0.0.exe`** — der Download startet.
   (Siehst du nur ein „Source code"-ZIP, ist die `.exe` hinter dem kleinen
   Dreieck **Assets ▸** verborgen — draufklicken, um die Liste aufzuklappen.)
3. Doppelklicke die heruntergeladene Datei `BudgetLiquidity-1.0.0.exe`.
4. Windows zeigt ein blaues Fenster **„Der Computer wurde durch Windows
   geschützt"**. Das ist normal — die App ist kostenlos und quelloffen, aber
   **nicht signiert**. Klicke auf **Weitere Informationen** und dann auf den
   erscheinenden Button **Trotzdem ausführen**.
5. Die App öffnet sich in einem eigenen Fenster. Beim ersten Start werden
   **fiktive Demo-Daten** geladen, damit du dich umsehen kannst; ersetze sie
   jederzeit durch deine eigenen Zahlen.

Fertig. Es ist eine einzige Datei — nichts wird installiert, und **alle deine
Daten bleiben auf deinem Rechner**. Zum Verschieben kopierst du die `.exe`
einfach irgendwohin (der Desktop reicht).

> **Wo liegen meine Daten?** Deine Planungsdatenbank liegt unter
> `%LOCALAPPDATA%\BudgetLiquidity\` auf deinem PC — nie in der `.exe` und nie in
> der Cloud. Sichere sie jederzeit über **Einstellungen → Daten → Export (ZIP)**.

---

## Für Entwickler — aus dem Quellcode starten (Windows)

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

## Die eigenständige `.exe` selbst bauen (für Entwickler)

Die einzelne, in sich geschlossene `.exe`, die Endnutzer herunterladen (siehe
[Herunterladen & starten](#️-herunterladen--starten-ohne-installation--empfohlen)
oben), wird so erzeugt. Baue sie selbst, um ein neues Release zu schnüren:

```powershell
# im Projektverzeichnis, mit bereits angelegtem .venv (siehe Schnellstart)
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
```

Das installiert die reinen Build-Abhängigkeiten (PyInstaller + pywebview) und
erzeugt mit `nicegui-pack` die Datei **`dist\BudgetLiquidity.exe`** (~55 MB).
Diese eine Datei kannst du weitergeben — Python wird nicht benötigt.

- **Beim ersten Start** wird eine frische Datenbank unter
  `%LOCALAPPDATA%\BudgetLiquidity\` angelegt (mit den fiktiven Demo-Daten
  befüllt). Deine eigenen Planungsdaten verlassen deinen Rechner nie und sind
  **nicht** Teil der `.exe`.
- **SmartScreen:** Die `.exe` ist **nicht signiert**, daher zeigt Windows eine
  Warnung „unbekannte App" — klicke auf **Weitere Informationen → Trotzdem
  ausführen**. Das ist normal; ein Installer oder Zertifikat würde daran nichts
  ändern (die Reputation einer unsignierten Datei baut sich erst mit der Zeit auf).

## Reiter

- **Mitarbeiter** — Mitarbeiter anlegen, monatliche Brutto-Matrix bearbeiten
  (Doppelgehalt Jun/Nov = Sonderzahlung), Live-Vorschau Netto/Abgaben.
- **Einnahmen** — Einnahmequellen (Produkt / wiederkehrend / Projekt / einmalig)
  mit Zahlungsziel.
- **Kosten** — Kostenkategorien je P&L-Zuordnung (Material / Wareneinsatz /
  bezogene Leistungen / OPEX).
- **Verträge & Abos** — Register aller laufenden Verträge, Abos und Fixkosten.
  Ein Vertrag wird einmal erfasst (Betrag je Intervall, Rhythmus, Beginn/Ende,
  Kündigungsfrist); daraus entstehen die Monatszellen in der zugeordneten
  Ausgaben-Position — die Jahresprämie landet im Fälligkeitsmonat, in jedem
  Planjahr, ohne sie erneut einzutippen. Eine Ampel warnt vor dem
  Kündigungsstichtag (gelb ab 120, rot ab 60 Tagen), die KPI-Zeile zeigt die
  normalisierten Fixkosten je Monat und Jahr. Erzeugte Zellen sind im Reiter
  Ausgaben schreibgeschützt; händisch erfasste Werte derselben Zelle bleiben
  erhalten und werden dazugezählt.
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
