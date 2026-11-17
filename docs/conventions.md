# Engineering Conventions

## Source IDs (shared by `sources.yaml`, chunk metadata and the golden dataset)

| source_id | What | Type |
|---|---|---|
| `bgb` | BGB, rental law §§ 535–580a (+ § 193 deadlines, § 568 written form via ranges) | law |
| `aufenthg` | Residence Act (§ 18g Blue Card, § 9/§ 18c settlement, § 81 application, family reunion §§ 27–32) | law |
| `bmg` | Federal Registration Act (§ 17 Anmeldung, § 19 landlord confirmation) | law |
| `beeg` | Federal Parental Allowance Act (Elterngeld) | law |
| `estg` | Income Tax Act, Kindergeld §§ 62–78 only | law |
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
| `bamf-<slug>` | BAMF EN pages, e.g. `bamf-blue-card`, `bamf-family-reunification` | guide |
| `miig-<slug>` | make-it-in-germany (manual save), e.g. `miig-blue-card`, `miig-family-reunification` | guide |
| `rb-<slug>` | rundfunkbeitrag.de, e.g. `rb-registration`, `rb-fee` | guide / faq |

New sources: add a row here **and** in `sources.yaml` in the same commit.

## doc_key
- Laws and regulations: `<source_id>#<paragraph>`, lowercase, no spaces: `bgb#573c`, `aufenthg#18g`, `bmg#17`, `estg#66`.
- Web pages: `<source_id>#<section-slug>`, where the slug is the `section_kind` for procedures (`muc-anmeldung#documents`), or the slugified H2 heading for guides (`fp-elterngeld#hoehe-des-elterngeldes`).
- The golden set may reference just `<source_id>`. It then matches any section (`expat.schemas.doc_key_matches`).

## Code
- Python 3.12, type hints everywhere, `pathlib`, Pydantic at every boundary. Config only via `expat.config.get_settings()`.
- Docstrings explain **why** (this is a learning and review project).
- Tests are offline by default. Anything that needs internet or API keys is marked `@pytest.mark.network`.
- Before each commit: `uv run ruff check --fix && uv run ruff format && uv run pytest`.
- Commits: Conventional Commits (`feat(ingestion): …`, `test(tools): …`, `docs: …`), small and focused.
