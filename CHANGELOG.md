# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.3.4] — 2026-10-04

### Added
- **Verträge erscheinen als eigene Zeilen in Ausgaben.** Unter jeder Ausgaben-
  Position, in die ein Vertrag schreibt, steht jetzt je Vertrag eine schreib-
  geschützte 🔗-Zeile mit seinen Monatsbeträgen, dazu eine Zeile „✎ manuell
  erfasst“ für händisch eingetragene Beträge. Die Positionszeile zeigt weiter die
  Summe; die Unterzeilen zählen nicht noch einmal in Σ. So ist auf einen Blick zu
  sehen, wenn derselbe Aufwand doppelt erfasst ist (händisch und als Vertrag).
- **Preis-Positionen je Vertrag.** Im Vertragsdialog lässt sich der Betrag über
  „Preis-Positionen verwenden“ in mehrere Zeilen (Betrag + Bezeichnung) aufteilen;
  der Betrag je Intervall ist deren Summe. Jede Position wird in Ausgaben als
  eigene Detailzeile erzeugt („Vertrag: Position“). Tooltip auf „Betrag“ in der
  Vertragsliste zeigt die Aufteilung. VSt-Umrechnung skaliert jede Position.

### Fixed
- **Aktions-Spalten in Verträge & Abos waren unlesbar.** Statt abgeschnittener
  Wörter („edit“, „folder_open“, „delete“) stehen dort jetzt Symbole: Stift,
  Ordner, Papierkorb.

## [1.3.3] — 2026-09-24

### Added
- **„Zelle leeren“ im Zellen-Dialog (Einnahmen + Ausgaben).** Ein Klick entfernt
  Wert, Detail-Aufstellung, Notiz und Zellenfarbe — statt Farbe zurücksetzen,
  Schalter „Detail-Aufstellung“ umlegen und Betrag löschen. In Ausgaben bleiben
  Zeilen aus Verträgen & Abos erhalten (sie werden dort gepflegt).
- **Zelle in Folgejahre kopieren.** „Auch in diese Monate kopieren“ bietet jetzt
  jeden Monat des Planungszeitraums an („Mär 2027“), nicht nur die des offenen
  Jahres — mit Wert, Aufstellung, Notiz und Farbe. Schnellauswahl: „Rest des
  Jahres“, „gleicher Monat im Folgejahr“, „ganzes Folgejahr“.

## [1.3.2] — 2026-09-14

### Fixed
- **Snapshot-Vergleich: „Tiefststand Liquidität“ und „Endsaldo Liquidität“ galten
  fürs ganze Planungsende statt fürs gewählte Jahr.** Beide Kennzahlen wurden aus
  der kompletten Kontostand-Reihe bis zum Planungsende (z. B. 2028) gezogen, egal
  welches Jahr im Vergleich eingestellt war. Jetzt zählen nur die 15./Monatsende-
  Buckets des gewählten Zeitraums: Tiefststand = niedrigster Kontostand darin,
  Endsaldo = Kontostand am letzten Bucket des Zeitraums.

### Added
- **Snapshot-Vergleich nach Jahr, Quartal oder Monat.** Neue Auswahl „Auflösung“:
  bei Quartal/Monat zeigt die Tabelle je Periode Snapshot / Aktuell / Differenz
  plus eine Spalte „Gesamt“ fürs Jahr; der Haken „nur Differenz“ blendet die
  Absolutwerte aus (kompakt bei 12 Monaten). Das Diagramm zeigt dann den Verlauf
  Snapshot vs. Aktuell je Periode für eine wählbare Kennzahl.
- **Umsatzerlöse je Einnahmequelle im Vergleich.** Unter „Umsatzerlöse“ steht
  jede Quelle als eigene Zeile. Zuordnung über die ID der Quelle, nicht den Namen:
  eine seit dem Snapshot umbenannte Quelle bleibt vergleichbar und trägt den
  alten Namen als Hinweis „(im Snapshot: …)“; Quellen, die nur auf einer Seite
  existieren, sind als „nur im Snapshot“ bzw. „neu, nicht im Snapshot“ markiert.
- Beide Seiten werden je Jahr/Szenario nur einmal durchgerechnet und dann pro
  Periode aufgeteilt; die Monatsansicht kostet nichts extra.
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
