# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.3.1] — 2026-09-13

### Added
- **Netto oder brutto? Jedes Betragsfeld sagt es jetzt selbst.** Im Zellen-Dialog
  der Ausgaben und Einnahmen, im Dialog „Wiederkehrende Ausgabe“ und im
  Vertrags-Dialog steht ein farbiger Hinweis, ob Beträge **exkl. MwSt. (netto)**
  oder **inkl. MwSt. (= Zahlbetrag)** einzugeben sind, samt Erklärung, was die
  App daraus rechnet (Bruttozahlung, Vorsteuer-Rückfluss am 15. des übernächsten
  Monats). Die Feldbeschriftung selbst lautet „Betrag (exkl. MwSt.)“ bzw.
  „Betrag (inkl. MwSt.)“. Maßgeblich ist allein der Haken „VSt“ (Ausgaben) bzw.
  „USt“ (Einnahmen) der jeweiligen Position; der Hinweis nennt, wo er sitzt.
- Neue Ausgaben-Positionen fragen den Vorsteuerabzug beim Anlegen ab (bisher
  stillschweigend aktiv), ebenso „Wiederkehrende Ausgabe“ bei neuer Position.
- Die Haken „VSt“/„USt“ in den Bearbeiten-Bereichen erklären per Tooltip, was
  sie für die Betragseingabe bedeuten; unter beiden Rastern steht die Regel als
  Legende.
- **Haken umschalten bei vorhandenen Werten → Umrechnungs-Abfrage.** Wer VSt
  bzw. USt einer Position ein- oder ausschaltet, die schon Werte hat, wird
  gefragt: „Umrechnen (÷ 1,2 bzw. × 1,2)“ hält die Bedeutung der Zahlen bei
  (aus dem bisherigen Brutto- wird der passende Nettobetrag und umgekehrt),
  „Werte beibehalten“ lässt sie stehen, „Abbrechen“ lässt den Haken wie er war.
  Umgerechnet werden alle Zellen und Detailzeilen der Position über alle Jahre,
  bei Ausgaben auch die zugeordneten Vertragsbeträge, bei Einnahmen Preise,
  Fixkosten, Sub-Sätze und €-Anzahlungen — Mengen und Prozentsätze nicht.

## [1.3.0] — 2026-08-20

### Added
- **Neuer Reiter „Verträge & Abos"** — ein Register aller laufenden Verträge,
  Abos und Fixkosten (Partner, Vertrags-/Polizzennummer, Betrag je Intervall,
  Rhythmus, Beginn/erste Zahlung/Ende, stillschweigende Verlängerung,
  Kündigungsfrist, Hauptfälligkeit, Zahlweg, Status, Ablage, Notiz).
  - **Fixkosten-Generator:** Aus den Vertragsdaten entstehen die Monatszellen der
    zugeordneten Ausgaben-Position — die Jahresprämie landet im Fälligkeitsmonat,
    in jedem Planjahr, ohne sie erneut einzutippen. Ab dort läuft alles durch die
    bestehende Pipeline: GuV im Zellmonat, Zahlung über das Zahlungsziel der
    Kategorie, Vorsteuer über deren USt-Flag.
  - **Terminüberwachung:** nächste Fälligkeit, Hauptfälligkeit und
    Kündigungsstichtag (Hauptfälligkeit minus Kündigungsfrist) je Vertrag, mit
    Ampel — gelb ab 120, rot ab 60 Tagen; grau ohne Verlängerung oder wenn der
    Vertrag nicht aktiv ist.
  - **KPI-Zeile:** Fixkosten je Monat und je Jahr (auf den Rhythmus normalisiert),
    Anzahl aktiver Verträge, nächster Kündigungsstichtag.
  - **Import:** „Verträge importieren" ergänzt Verträge aus einer JSON-Datei im
    Export-Format, ohne den übrigen Plan zu ersetzen.

### Changed
- Ausgaben: Zellen, die von einem Vertrag stammen, sind im Raster gesperrt; im
  Detail-Dialog stehen die erzeugten Zeilen mit Schloss-Symbol und Vertragsnamen
  schreibgeschützt über den händischen Zeilen und zählen in die Zellsumme.
  Händisch erfasste Werte einer solchen Zelle bleiben erhalten.
- Das Ausgaben-Raster lädt beim Öffnen des Reiters neu, damit neu erzeugte
  Vertragszellen sofort sichtbar sind.
- Sicherung/Export und Snapshots enthalten die Verträge; nach einem
  Snapshot-Restore werden die Vertragszellen neu erzeugt.

## [1.2.0] — 2026-08-17

### Fixed
- **Excel-Export erzeugte in der Windows-App gar keine Datei.** Der Export lief
  über einen Browser-Download; pywebview bricht Downloads im nativen Fenster aber
  grundsätzlich ab (`ALLOW_DOWNLOADS` ist aus), sodass „Szenario exportieren" und
  „Szenarienvergleich exportieren" folgenlos blieben.
- **„Durchsuchen…"** (Datenverzeichnis) öffnete keinen Dialog mehr: die
  Fenster-Methode ist inzwischen asynchron und wurde nicht awaited.

### Changed
- Jede Datei, die die App herausgibt (Szenario-Export, Szenarienvergleich,
  ZIP-Sicherung), fragt jetzt über einen echten **„Speichern unter"-Dialog** nach
  dem Zielpfad; der zuletzt gewählte Ordner wird als Startordner gemerkt. Läuft
  die App aus dem Quellcode im Browser, bleibt es beim normalen Download.
- Die ZIP-Sicherung landet damit dort, wo der Benutzer sie hinlegt, statt fix im
  Ordner `exports` des Datenverzeichnisses.

## [1.0.0] — 2026-06-28

First publicly distributable release: a standalone Windows app you can hand to
non-technical users.

### Added
- **Standalone Windows `.exe`** built with `nicegui-pack` (PyInstaller), opening
  in a native desktop window. Austrian red-white-red app icon.
- **About dialog** (header ℹ button) showing version, author, repository and the
  MIT licence.
- **Data management** (Settings → Daten):
  - **Export** all data to a timestamped ZIP backup (records the app version it
    was created with).
  - **Import** a ZIP backup; the current plan is snapshotted first as a safety
    net, and a version mismatch is detected and reported.
  - **Change the data directory** — relocate the database to a folder of your
    choice; the database is rebound live without a restart.
- Database is stored in a stable per-user location (`%LOCALAPPDATA%`) for the
  packaged build, so data survives restarts and updates.
- Application versioning via a single source of truth (`app/version.py`).

### Fixed
- Native window: the left navigation drawer no longer collapses into an
  unrecoverable mobile overlay; the window opens in desktop layout.
- Tables on every page now fill the available width with a readable minimum
  column width and re-flow on window resize (no more columns crushed to the
  left with an empty right half).
