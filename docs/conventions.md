# Engineering Conventions

## Source IDs (shared by `sources.yaml`, chunk metadata and the golden dataset)

| source_id | What | Type |
|---|---|---|
| `bgb` | BGB, rental law §§ 535–580a (+ § 193 deadlines, § 568 written form via ranges) | law |
| `aufenthg` | Residence Act (§ 18g Blue Card, § 9/§ 18c settlement, § 81 application, family reunion §§ 27–32) | law |
| `bmg` | Federal Registration Act (§ 17 Anmeldung, § 19 landlord confirmation) | law |
| `beeg` | Federal Parental Allowance Act (Elterngeld) | law |
| `estg` | Income Tax Act: tax classes §§ 26, 38b, 39, 39e, 39f (domain `taxes`) and Kindergeld §§ 62–78 | law |
| `sgbv` | Social Code V: compulsory / voluntary / family health insurance §§ 5–10, choosing the fund §§ 173–175 | law |
| `stag` | Nationality Act: naturalisation §§ 8–12b (§ 9 spouses, § 10 five years), § 4 birth, § 16, § 38 fees | law |
| `fev` | Driving Licence Regulation: § 7, §§ 28–31 foreign licences, `fev#anlage11` country list (table) | law |
| `ao` | Fiscal Code: tax ID §§ 139a–139b | law |
| `by-mieterschutzv` | Bavarian Mieterschutzverordnung (Mietpreisbremse, Kappungsgrenze, 2026–2029) | regulation |
| `muc-anmeldung` | Munich: Wohnsitz anmelden | procedure |
| `muc-anmeldung-familie` | Munich: Wohnsitzanmeldung Familie | procedure |
| `muc-aufenthaltstitel-fachkraefte` | Munich Ausländerbehörde: residence permit for skilled workers / Blue Card | procedure |
| `muc-niederlassung-blaue-karte` | Munich: settlement permit for Blue Card holders | procedure |
| `muc-kita` | Munich: Kita / kitafinder+ | procedure / faq |
| `muc-mietspiegel` | Munich Mietspiegel 2025 info | guide |
| `fp-elterngeld` | familienportal: Elterngeld | guide |
| `fp-elterngeld-neuregelungen` | familienportal: Elterngeld changes (income cap €175k) | guide |
| `fp-kindergeld` | familienportal: Kindergeld (+ FAQ) | guide / faq |
| `bp-<slug>` | BayernPortal procedure pages, e.g. `bp-wohnsitz-anmeldung`, `bp-blaue-karte`, `bp-kindergeld`, `bp-elterngeld` | procedure |
| `bamf-<slug>` | BAMF pages, e.g. `bamf-blue-card`, `bamf-family-reunification`, `bamf-einbuergerung` (DE) | guide |
| `miig-<slug>` | make-it-in-germany (manual save), e.g. `miig-blue-card`, `miig-family-reunification` | guide |
| `rb-<slug>` | rundfunkbeitrag.de, e.g. `rb-registration`, `rb-fee` | guide / faq |
| `ber-<slug>` | Berlin (service.berlin.de, mietspiegel.berlin.de), e.g. `ber-anmeldung`, `ber-lea-blaue-karte`, `ber-kita` | procedure / guide |
| `ham-<slug>` | Hamburg (hamburg.de, Hamburg Welcome Center), e.g. `ham-anmeldung`, `ham-welcome-blaue-karte`, `ham-kita` | procedure / guide |
| `fra-<slug>` | Frankfurt am Main (frankfurt.de), e.g. `fra-auslaenderbehoerde-blaue-karte`, `fra-kita`, `fra-mietspiegel` | procedure / guide |
| `cgn-<slug>` | Köln / Cologne (stadt-koeln.de), e.g. `cgn-anmeldung`, `cgn-kita`, `cgn-mietpreisueberhoehung` | procedure |
| `str-<slug>` | Stuttgart (stuttgart.de, welcome.stuttgart.de), e.g. `str-anmeldung`, `str-kita`, `str-mietspiegel` | procedure / guide |
| `be-<slug>` | Berlin state rules: `be-mietpreisbremse` (Mietenbegrenzungsverordnung 2026–2029, gazette PDF) | regulation |
| `hh-<slug>` | Hamburg state rules: `hh-mietpreisbremse` (gazette PDF), `hh-mietpreisbremse-info` (explainer) | regulation / guide |
| `he-<slug>` | Hesse: `he-mietpreisbremse` (Mieterschutzverordnung 17.11.2026, Annex 1 lists Frankfurt am Main) | regulation |
| `nw-<slug>` | North Rhine-Westphalia: `nw-mietpreisbremse` (recht.nrw.de), `nw-mietpreisbremse-anlage` (municipality list) | regulation |
| `bw-<slug>` | Baden-Württemberg: `bw-mietpreisbremse-info` (ministry explainer; law PDFs parked) | guide |
| `bmg-<slug>` | Federal Ministry of Health: `bmg-krankenversicherung` (4 DE pages), `bmg-shi-en` | guide |
| `bmi-<slug>` | Federal Ministry of the Interior: `bmi-einbuergerung-en`, `bmi-einbuergerung` (+ nationality law page) | guide |
| `bmv-<slug>` | Federal Ministry of Transport: `bmv-fuehrerschein-en`, `bmv-fuehrerschein` | guide |
| `bzst-<slug>` | Federal Central Tax Office: `bzst-steuer-id` (EN info + FAQ) | faq |
| `fa-nrw-steuerklassen` | NRW tax administration: tax classes (federal law, valid everywhere) | guide |

City slugs in chunk metadata (`city`): `munich`, `berlin`, `hamburg`, `frankfurt`, `cologne`, `stuttgart`
(`expat/places.py`); state codes (`state`): ISO 3166-2:DE without `DE-` (`BY`, `BE`, `HH`, `HE`, `NW`, `BW`, …).

New sources: add a row here **and** in `sources.yaml` in the same commit.

## doc_key
- Laws and regulations: `<source_id>#<paragraph>`, lowercase, no spaces: `bgb#573c`, `aufenthg#18g`, `bmg#17`, `estg#66`;
  annex tables: `<source_id>#anlage<n>` (`fev#anlage11`).
- Web pages: `<source_id>#<section-slug>`, where the slug is the `section_kind` for procedures (`muc-anmeldung#documents`), or the slugified H2 heading for guides (`fp-elterngeld#hoehe-des-elterngeldes`).
- The golden set may reference just `<source_id>`. It then matches any section (`expat.schemas.doc_key_matches`).

## Code
- Python 3.12, type hints everywhere, `pathlib`, Pydantic at every boundary. Config only via `expat.config.get_settings()`.
- Docstrings explain **why** (this is a learning and review project).
- Tests are offline by default. Anything that needs internet or API keys is marked `@pytest.mark.network`.
- Before each commit: `uv run ruff check --fix && uv run ruff format && uv run pytest`.
- Commits: Conventional Commits (`feat(ingestion): …`, `test(tools): …`, `docs: …`), small and focused.
