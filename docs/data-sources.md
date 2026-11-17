# Data Source Inventory

> Verified 2026-11-17 by fetching each site, its robots.txt and its Impressum/terms. "Could not verify" means exactly that, so re-check on Day 1.
> **Not legal advice on copyright.** This is a non-commercial educational project. The policy below is deliberately conservative.

## Ingestion policy (what you say in the review)

1. **Statutes are public domain** (amtliche Werke, § 5 UrhG). Ingest them fully, as XML.
2. **Portal content is "all rights reserved"** on most sites. For a non-commercial course project we:
   - ingest only pages needed for the MVP domains, fetched politely (robots.txt respected, ≥ 1 s between requests, honouring `Crawl-delay`, identifying User-Agent);
   - store chunks with **attribution and a deep link**, show only short quotes in the UI, and always link to the original;
   - **never commit** raw/scraped content or the vector DB to the public repo (`data/` is gitignored; the README explains how to rebuild);
   - **exclude** sources whose terms explicitly forbid storage in electronic systems or that block AI crawlers (DRV, arbeitsagentur.de). The assistant *links* to them instead;
   - for a public deployment beyond the course, request permission (contacts are listed in the Impressum pages).
3. **Snapshots:** every fetch is saved to `data/raw/` with a timestamp, so dev and evals never hit the sites again. This is both polite and reproducible.

## MVP sources (3 domains + Munich)

| # | Source | Domain(s) | What exactly | Format | Lang | robots.txt | Terms | Update cadence | MVP |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **gesetze-im-internet.de** | Tenancy, Bureaucracy, Family | **BGB** §§ 535–580a (rental law), **AufenthG** (incl. § 18g Blue Card, § 9 settlement), **BMG** (§ 17 Anmeldung), **BEEG** (Elterngeld), **EStG** §§ 62–78 (Kindergeld) | **XML** (`/<abk>/xml.zip`, `gii-norm.dtd`; `<norm>` → `enbez` "§ 573c", `titel`, `<P>` = Absatz; `builddate` attribute) | DE | `Disallow:` (empty, all allowed) | § 5 UrhG, public domain. Deep links explicitly allowed. | Weekly check of `builddate`. Laws change ~monthly | ✅ |
| 2 | **stadt.muenchen.de** (city of Munich) | Bureaucracy, Family, Tenancy | Wohnsitzanmeldung (+ family variant), Ausländerbehörde / Service-Center für internationale Fachkräfte (Blue Card, extension, settlement permit), Kita (Geschäftsbereich Kita + kitafinder FAQ), Mietspiegel 2025 info page | HTML | DE + EN (`/service/en-GB/…`, `?lang=en`). EN is **machine-translated (DeepL)**, so DE is binding | Only `ia_archiver` blocked | Copyrighted texts. Private use per § 53 UrhG. Laws/notices free. → chunks + links | Monthly | ✅ |
| 3 | **familienportal.de** (BMBFSFJ) | Family | Elterngeld (amounts, cap, ElterngeldPlus), Kindergeld FAQ (€259), Kinderzuschlag | HTML | DE + EN overview + 9 languages | All allowed | Copyright BMBFSFJ; copying needs written consent. → minimal chunks + links. Ask for permission if deploying publicly | Monthly; **January check** | ✅ |
| 4 | **BayernPortal** (bayernportal.de) | Bureaucracy, Family | Structured procedure descriptions ("Leistungen") for Bavaria: Anmeldung, Aufenthaltstitel, Kindergeld, Elterngeld. Each has required documents, fees, deadlines, legal basis, which is **ideal for checklist chunks** | HTML (consistent template) | DE + EN (`?locale=en`) | 404 (no restrictions) | Terms heading exists but text could not be retrieved. Official Art. 27 BayDiG portal | Monthly | ✅ |
| 5 | **verkuendung-bayern.de** | Tenancy | Bavarian **Mieterschutzverordnung** (BayMBl. 2025 Nr. 558): Mietpreisbremse + 15% Kappungsgrenze, valid 2026-01-01 to 2029-12-31, municipality list | HTML/PDF | DE | Not checked (check Day 1) | Official regulation, § 5 UrhG | On change (valid until 2029) | ✅ |
| 6 | **bamf.de** | Bureaucracy | EN pages on residence/integration (`/EN/Themen/MigrationAufenthalt/`), integration course info | HTML (+ PDF brochures) | DE, EN | 404 (none) | Impressum covers images only; text terms could not be verified | Monthly | ✅ (EN pages, ≤ 15) |
| 7 | **make-it-in-germany.com** | Bureaucracy | Blue Card, family reunification, visa pages, Blue Card info PDF | HTML/PDF | EN, DE, others | Content allowed; **bot protection (JS challenge) blocks scripted fetching** | Free reuse for non-commercial/editorial use with credit, unaltered text (from the legal notice snippet) | Monthly | ✅ **manual save** (`fetch_method: manual`, ≤ 10 pages) |
| 8 | **rundfunkbeitrag.de** | Bureaucracy | Registration, €18.36/month, exemptions, EN pages | HTML | DE + 7 languages | Info pages allowed | Disclaimer only | Quarterly (KEF 2027 proposal pending) | ✅ (small) |

Expected MVP corpus: ~5 law XMLs (only the relevant sections of BGB/EStG) + ~60–100 web pages → **~1.5–3k child chunks**. That is small enough to re-embed in minutes and big enough for meaningful retrieval evals.

## Stretch sources

| Source | Domain | Format | Lang | robots.txt | Terms | Notes |
|---|---|---|---|---|---|---|
| auswaertiges-amt.de | Travel (visas for visiting parents) | HTML | DE, EN | Mostly allowed | All rights reserved; country info is link-only | Travel domain stretch |
| bundesfinanzministerium.de | Taxes | HTML/PDF | DE, EN | **Crawl-delay 180 s** | Texts need consent; decrees/notices free | BMF letters are free (§ 5). Ingest few pages, manual |
| elster.de | Taxes | HTML | DE, EN | None | No reuse licence found | How-to only |
| bzst.de | Taxes (Steuer-ID) | HTML | DE, EN | Crawl-delay 30 | not checked | |
| bundesgesundheitsministerium.de, gkv-spitzenverband.de | Finance (health insurance) | HTML | DE, some EN | Fairly open | Not checked | Finance stretch |
| auswaertiges-amt / EU Commission short-stay calculator page | Travel | HTML | EN | — | — | Source for the Schengen tool |
| **rechtsinformationen.bund.de (NeuRIS)** | Law | **API** (JSON/XML/HTML) | DE | `Disallow: /`, so **use the API, not crawling** | Licence unverified; "trial service", incomplete | Interesting future replacement for gesetze-im-internet XML. Mention in the review as "future work" |
| verwaltung.bund.de (Bundesportal, PVOG) | Bureaucracy | HTML + structured XZuFi via PVOG/FITKO | DE, partly EN | Leistungsverzeichnis crawlable, has a sitemap | No public licence found | Federal procedure catalogue. Good for scaling to other cities |

## Excluded (link-only)

| Source | Why excluded from ingestion | What we do instead |
|---|---|---|
| **deutsche-rentenversicherung.de** | Blocks GPTBot/meta AI bots. Terms require **prior written consent for storage in databases/electronic systems** | Link in answers about pensions (out of MVP scope anyway) |
| **arbeitsagentur.de** (Familienkasse) | Terms require prior permission for storing/processing in electronic systems. Content JS-rendered | Kindergeld facts come from familienportal.de + EStG. Link to the Familienkasse application |
| **gesetze-im-internet.de English translations** (`/englisch_bgb/`, `/englisch_aufenthg/`) | **Copyrighted** (unlike the German originals), **outdated** (BGB EN as of 2021, AufenthG EN 2024), not binding | Link as a convenience translation in the source panel ("unofficial EN translation, outdated"). Never use it as a retrieval source |
| **muenchen.de** (city marketing portal, Portal München GmbH) | Private-use-only terms, not the city administration | Use **stadt.muenchen.de** (official) |
| **fimportal.de** | robots.txt blocks ClaudeBot/GPTBot/anthropic-ai. Licence unverified | Mention as the structured-data source of the future |

## `sources.yaml` entry format (the ingestion input)

```yaml
- id: bgb
  name: "Bürgerliches Gesetzbuch (BGB)"
  publisher: "Bundesministerium der Justiz / gesetze-im-internet.de"
  url: https://www.gesetze-im-internet.de/bgb/xml.zip
  source_type: law
  parser: law_xml
  domain_map:              # which § ranges map to which domain/subtopic
    - range: "535-580a"
      domain: tenancy
  include_ranges: ["535-580a"]
  language: de
  jurisdiction: federal
  fetch_method: http        # http | manual
  refresh: weekly
  terms: "§ 5 UrhG, public domain"
- id: muc-anmeldung
  name: "Wohnsitz anmelden – Landeshauptstadt München"
  url: https://stadt.muenchen.de/service/info/wohnsitzanmeldung/1063475/n0/
  alt_lang_urls: {en: https://stadt.muenchen.de/service/en-GB/info/register-or-reregister-your-place-of-residence/10424740/n0/}
  source_type: procedure
  parser: guide_html
  domain: bureaucracy
  subtopic: anmeldung
  jurisdiction: city
  state: BY
  city: munich
  applies_to: [all]
  fetch_method: http
  refresh: monthly
  terms: "© LH München, private use § 53 UrhG; chunks + link only"
```

## Freshness strategy

| Mechanism | How |
|---|---|
| `last_verified` per chunk | The date the source was last fetched **and** its content hash checked. If unchanged, only `last_verified` is bumped (a metadata update, no re-embed) |
| `valid_from` / `valid_until` | From the law XML (`standangabe`, `builddate`), the regulation text (e.g. Mieterschutzverordnung until 2029-12-31), or `rules/2026.yaml` |
| Conditional fetch | `ETag` / `If-Modified-Since`, plus a content hash of the *cleaned* text (ignores nav/footer noise) |
| Re-ingestion schedule | `refresh` per source: weekly (laws via `builddate`), monthly (portals), January sweep for all amounts. Run as a CLI (`expat-ingest --due`). In production: a GitHub Actions cron or a scheduled job |
| Change log | The manifest table records `(doc_id, version_hash, fetched_at, changed: bool)`. The Streamlit ingestion page shows "changed since last run" |
| UI staleness | Citation chip shows "verified 18 Nov 2026". Amber if > 90 days, red if `valid_until` has passed |
| Known pending changes | `rules/2026.yaml → pending_changes:` (Elterngeld reform for births from 2027-11, Rundfunkbeitrag 2027 proposal + BVerfG case, Mietrechtsreform in the Bundestag, Steuerklassen III/V debate). The answer mentions them when relevant |
