# Germany-wide sources: discovery and verification (2026-11-22)

Scope: Berlin, Hamburg, Frankfurt am Main, Köln, Stuttgart (Anmeldung, Blue Card / settlement permit,
Kita, Mietspiegel) plus the rent-cap regulation of BE, HH, HE, NW and BW. Draft registry entries:
`docs/research/sources-germany-draft.yaml`.

**Method.** Every URL was fetched with plain `curl -sL -A "Mozilla/5.0 (compatible; AnkommenResearch/0.1)"`,
one request at a time with at least 2 s between requests. "Verified" means HTTP 200, the main text is in the
raw HTML (checked with BeautifulSoup on the saved file) and robots.txt allows the path. Raw samples:
`data/_research/<id>.html|.pdf` (git-ignored), robots.txt copies: `data/_research/robots/`. Selectors were
tried out on the saved files with `parse_html()` and a throw-away `SiteProfile` (no repo file was changed).

Legend: **JS?** = main text only rendered by JavaScript. **EN** = a static English page exists (MT = machine translation).

---

## 1. Per city / state

### Berlin (BE)

| Topic | URL | Verified | JS? | robots | EN | Notes |
|---|---|---|---|---|---|---|
| Anmeldung | https://service.berlin.de/dienstleistung/120686/ | yes | no | ok | no | The linked `/en/` and `/ru/` pages return **404** (checked twice). No separate family page; 120686 covers family members. |
| Blue Card (LEA) | https://service.berlin.de/dienstleistung/324659/ | yes | no | ok | yes (`/en/`) | LEA; online application only. |
| Settlement permit, Blue Card | https://service.berlin.de/dienstleistung/326556/ | yes | no | ok | yes (`/en/`) | |
| Kita (Kita-Gutschein) | https://service.berlin.de/dienstleistung/324873/ | yes | no | ok | yes (`/en/`) | Page has a district notice box (`.location-notes`), drop it. |
| Mietspiegel 2026 | https://mietspiegel.berlin.de/ (+ `/berliner-mietspiegel/erlaeuterungen-zum-mietspiegel/`, `.../preisspannen/`) | yes | no | ok | no | WordPress site of SenStadt. `berlin.de/sen/wohnen/service/mietspiegel/` is only a teaser to it. The Abfrage tool is interactive. |
| Rent cap | https://www.berlin.de/sen/stadt/_assets/service/rechtsvorschriften/bereich-wohnen/vo19-298.pdf | yes (PDF) | n/a | ok | no | Mietenbegrenzungsverordnung of 11.11.2025 (GVBl. S. 577), **whole city**, in force **01.01.2026 to 31.12.2029** (§ 3, checked with pdftotext). The consolidated text is on `gesetze.berlin.de/bsbe/document/jlr-MietBegrVBE2026rahmen`, but robots.txt blocks all non-whitelisted bots. **Needs a PDF parser.** |

robots.txt of `service.berlin.de` / `www.berlin.de`: the bot must identify itself in the UA and follow REP; only `/pdf/`, export and appointment-API paths are disallowed.

### Hamburg (HH)

| Topic | URL | Verified | JS? | robots | EN | Notes |
|---|---|---|---|---|---|---|
| Anmeldung (from abroad) | https://www.hamburg.de/service/info/111142065/n0/ | yes | no | ok | no (JS translator) | `111202447` ("Anmeldung der alleinigen Wohnung") is an empty umbrella page ("siehe Rubrik Links"). 111142065 has the real text: documents, 2-week deadline, apostille. |
| Blue Card (Welcome Center) | https://welcome.hamburg.de/einreise-und-aufenthalt/aufenthaltserlaubnisse/blaue-karte-eu-416694 | yes | no | ok (sitemap only) | **yes**: https://welcome.hamburg.com/entry-and-residence/residence-permit/eu-blue-card-17644 | Hamburg Welcome Center (Amt für Migration). Real EN site (separate sitemap). |
| Settlement permit | https://welcome.hamburg.de/einreise-und-aufenthalt/aufenthaltserlaubnisse/niederlassungerlaubnis-416776 | yes | no | ok | **yes**: https://welcome.hamburg.com/entry-and-residence/residence-permit/settlement-permit-17664 | |
| Blue Card (Hamburg Service, procedure style) | https://www.hamburg.de/service/info/111251568/ | yes | no | ok | no | Optional, overlaps with the Welcome Center page. |
| Settlement permit, Blue Card (Hamburg Service) | https://www.hamburg.de/service/info/111204805/ | yes | no | ok | no | Optional. Its `<h1>` is empty in the HTML; the title comes from `<title>`. |
| Kita (Kita-Gutschein) | https://www.hamburg.de/politik-und-verwaltung/behoerden/bsfb/familie/kinderbetreuung/elterninformationen/kita-gutschein-35656 | yes | no | ok | no | BSFB guide. The H1 is a teaser ("Seit Januar 2025 gibt es den XL-Kita-Gutschein!"); the registry `name` should be used as the title. |
| Mietenspiegel 2025 | https://www.hamburg.de/politik-und-verwaltung/behoerden/behoerde-fuer-stadtentwicklung-und-wohnen/themen/wohnen/mieten/mietenspiegel/mietenspiegel-hintergrund-189816 | yes | partly | ok | no | Short (about 2,000 characters). Table and brochure are PDFs on `dokumente.hamburg.de`; the online map is a JS opt-in widget. The hub `/mietenspiegel` holds only teasers. |
| Rent cap (law) | https://dokumente.hamburg.de/resource/blob/1127230/f4eeaf811b75b9b992bc00add53192d9/d-hmbgvbl-nr-41-dezember-2025-data.pdf | yes (PDF) | n/a | ok | no | Mietpreisbegrenzungsverordnung of 25.11.2025, HmbGVBl. 2025 Nr. 41. **Whole city**, **01.01.2026 to 31.12.2029** (§ 2, checked). The PDF is a whole gazette issue; the regulation has to be cut out. `landesrecht-hamburg.de` is robots-blocked. |
| Rent cap (explainer) | https://www.hamburg.de/politik-und-verwaltung/behoerden/behoerde-fuer-stadtentwicklung-und-wohnen/themen/wohnen/mieten/mietenspiegel/mietpreisbremse-189826 | yes | no | ok | no | States "gilt bis zum 31. Dezember 2029 für das gesamte Hamburger Gebiet" and explains the exceptions. |

### Frankfurt am Main (HE)

| Topic | URL | Verified | JS? | robots | EN | Notes |
|---|---|---|---|---|---|---|
| Anmeldung | https://frankfurt.de/leistungen/Umzug-8958631/Abmeldungen-Ummeldungen-Anmeldungen-8958634/Anmeldung-einer-Wohnung | **no** | – | ok | EN page also 403 | **HTTP 403 Cloudflare challenge** ("Just a moment...") on 3 tries, 10-30 s apart. Entry commented out; it would need `fetch_method: manual`. |
| Blue Card | https://frankfurt.de/auslaenderangelegenheiten/ich-moechte-einen-antrag-stellen/arbeitnehmer/blaue-karte-eu | yes | no | ok | no (Conword JS) | Ausländerbehörde microsite. No headings: uses `<strong>` and one-cell layout tables. |
| Settlement permit | https://frankfurt.de/auslaenderangelegenheiten/ich-moechte-einen-antrag-stellen/arbeitnehmer/niederlassungserlaubnis | yes | no | ok | no | Covers employees incl. Blue Card holders. |
| Kita | https://frankfurt.de/themen/arbeit-bildung-und-wissenschaft/bildung/kindertagesbetreuung/betreuungsplatz-suchen-und-finden | yes | no | ok | EN page 403 | `kindernetfrankfurt.de` itself is an Angular app (Lecos "Kivan"): 87 characters of text in the HTML, and robots.txt returns **HTTP 500**. Not usable. |
| Mietspiegel 2026 | https://frankfurt.de/themen/planen-bauen-und-wohnen/wohnen/informationen-zum-wohnungsmarkt/mietspiegel | yes | no | ok | EN page 403 | Qualified Mietspiegel 2026, recognised 25.06.2026. The table itself is a PDF. |
| Rent cap (law) | https://verkuendung.hessen.de/sites/verkuendung.hessen.de/files/veroeffentlichungsplattform_plugin/published/1568/GVBl_2026_Nr_78_Regelungstext.pdf | yes (PDF) | n/a | ok | no | **New** Hessische Mieterschutzverordnung of 17.11.2026, GVBl. 2026 Nr. 78 of **19.11.2026**. In force the day after promulgation (§ 5 (1), i.e. 20.11.2026). § 1 Nr. 1 (Mietpreisbremse) runs **to 31.12.2029**; the Kappungsgrenze and Kündigungssperre parts run to 19.11.2031. Anlage 1 has 71 municipalities, **"20. Frankfurt am Main" is listed**. It repeals MiSchuV 2020/2025. `rv.hessenrecht.hessen.de` is robots-blocked. |
| Rent cap (explainer) | https://wirtschaft.hessen.de/wohnen-und-bauen/wohnungsrecht/mieterschutzverordnung-vom-18-november-2020-gvbl-s-802 | yes, **but stale** | no | ok | no | Still describes the repealed 2020/2025 regulation. Commented out. |

frankfurt.de robots.txt (Cloudflare managed): `User-agent: * Allow: /` with `Content-Signal: search=yes, ai-train=no, use=reference`. `ai-input` is not set, which per the file's own text means "neither granted nor restricted". It disallows ClaudeBot / GPTBot etc., but not our UA. Cloudflare behaviour differed by path: `/auslaenderangelegenheiten/*`, `/themen/*` and `/service-und-rathaus/*` returned 200; `/leistungen/*` and `/english/*` returned 403 every time, and once even the home page returned 403.

### Köln / Cologne (NW)

| Topic | URL | Verified | JS? | robots | EN | Notes |
|---|---|---|---|---|---|---|
| Anmeldung | https://www.stadt-koeln.de/service/produkte/00415/index.html | yes | no | ok | no (Conword proxy) | |
| Blue Card | https://www.stadt-koeln.de/service/produkte/20321/index.html | yes | no | ok | no | Ausländeramt, Arbeitsmigration. |
| Settlement permit (Fachkräfte) | https://www.stadt-koeln.de/service/produkte/20359/index.html | yes | no | ok | no | Canonical of `/service/produkt/niederlassungserlaubnis-fuer-fachkraefte`. |
| Kita (LITTLE BIRD) | https://www.stadt-koeln.de/service/produkte/00386/index.html + FAQ https://www.stadt-koeln.de/artikel/65229/index.html | yes | no | ok | no | The FAQ has one H2 per question (about 30 questions). |
| Mietspiegel | – | **gap** | – | – | – | The Kölner Mietspiegel 2025 is an *einfacher* Mietspiegel published by the **Rheinische Immobilienbörse e.V.** (a private association), so it is not an official source. Substitute: the city's Mietpreisüberhöhung page https://www.stadt-koeln.de/service/produkte/00702/index.html (verified), which explains the 20 %/50 % rules and links to the RIB download. |
| Rent cap | https://recht.nrw.de/lrgv/rechtsverordnung/07112025-mieterschutzverordnung-nrw-mietschvo-nrw/ | yes (HTML) | no | ok | no | MietSchVO NRW of 28.01.2025 (GV. NRW. S. 111), amended 28.10.2025 (S. 848), version valid since 07.11.2025. In force 01.03.2025. § 3 (2): § 1 (1) (Mietpreisbremse) expires **31.12.2029**, the rest 28.02.2030. The municipality list (57 Kommunen) is **only a PDF** (`/system/files/BA/54532-52830-sgv_238_20250128_1_anlage1.pdf`); **"28 Köln" is listed** (checked with pdftotext). |

stadt-koeln.de robots.txt: only 3 unrelated paths disallowed.

### Stuttgart (BW)

| Topic | URL | Verified | JS? | robots | EN | Notes |
|---|---|---|---|---|---|---|
| Anmeldung | https://www.stuttgart.de/organigramm/leistungen/wohnsitz-anmelden-als-hauptwohnsitz | yes | **see note** | ok | MT (`/en/...`, `og:locale=en_US_deepl`) | Text is in the HTML, but the collapsible sections carry `aria-hidden="true"` and `style="display:none"`. The current global drop list removes them (see section 2). |
| Anmeldung (Welcome Center) | https://welcome.stuttgart.de/ankommen/anmelden | yes | no | ok | MT (`/en/ankommen/anmelden`) | DeepL renders the title "Anmelden" as **"Log in"**: the EN quality is poor. |
| Blue Card | https://www.stuttgart.de/organigramm/leistungen/blaue-karte-zur-ausuebung-einer-hochqualifizierten-beschaeftigung-beantragen-blue-card- | yes | see note | ok | MT | Same collapsible issue. |
| Blue Card (Welcome Center) | https://welcome.stuttgart.de/ankommen/aufenthalt/blaue-karte-eu | yes | no | ok | MT | Stand 18.12.2025. |
| Settlement permit | https://welcome.stuttgart.de/ankommen/aufenthalt/niederlassungserlaubnis | yes | see note | ok | MT | Has a section "Niederlassungserlaubnis für Inhaber einer Blauen Karte". There is no separate stuttgart.de procedure page. Stand 25.08.2025. |
| Kita | https://www.stuttgart.de/kita-portal | yes | see note | ok | no | Stand 06.10.2026. |
| Mietspiegel 2025/2026 | https://www.stuttgart.de/mietspiegel | yes | no | ok | no (`/en/` redirects to DE) | Qualified, **valid 01.01.2025 to 31.12.2026**. The successor 2027/28 is not yet published. |
| Rent cap 2026 | https://www.baden-wuerttemberg.de/de/service/gesetze-und-verordnungen/gesetzblatt/detail/2025-144 (+ PDF) | yes (PDF) | n/a | ok | no | MietBegrVO BW of 16.12.2025, GBl. 2025 Nr. 144. **01.01.2026 to 31.12.2026**; **Stuttgart listed** in § 1. |
| Rent cap 2027-2029 | https://www.baden-wuerttemberg.de/de/service/gesetze-und-verordnungen/gesetzblatt/detail/2026-95 (+ PDF) | yes (PDF) | n/a | ok | no | MietBegrVO BW of 10.11.2026, GBl. 2026 Nr. 95 of 12.11.2026. **01.01.2027 to 31.12.2029** (§ 2); 133 municipalities, **Stuttgart listed** in § 1. The SHA-256 on the detail page matches the download. |
| Rent cap (explainer) | https://mlw.baden-wuerttemberg.de/de/bauen-wohnen/wohnungsbau/mietpreisbremse | yes | no | ok | no | Ministry page with an "Aktuelles" note on the 2027 extension and 7 FAQ accordions. |

stuttgart.de / welcome.stuttgart.de robots.txt: same Cloudflare-managed file as Frankfurt (`Allow: /`, `use=reference`, `ai-train=no`). No challenge was seen in 14 requests. `www.landesrecht-bw.de` is robots-blocked. The Gesetzblatt PDF links contain a session-like `token=`: resolve them from the stable detail page at fetch time.

---

## 2. Site-profile proposals (style of `parsers/html.py`)

All tried out with `parse_html()` on the saved files. Section counts and character counts below come from these trial runs.

```python
# Berlin service portal. Checked: ber-lea-blaue-karte.html, ber-anmeldung.html, ber-kita(.en).html
# -> 6-7 sections (Verfahrensablauf, Voraussetzungen, Erforderliche Unterlagen, Gebühren, Rechtsgrundlagen,
#    Bearbeitungszeit), about 10-13k chars. Each section is div#<key>.block > h2.title. Intro text = first div.block.
"service.berlin.de": SiteProfile(
    content=("#layout-grid__area--maincontent",),
    title="h1.title",
    drop=(".modul-servicepanel", ".location-notes", "#formulare", "#rechtsbehelf", "#zustaendig",
          ".modul", ".js-overlay-container", "#toplist"),      # "Für Sie zuständig" location list = 21k chars on 120686
    drop_headings=re.compile(r"^(online-abwicklung|online processing|your point of contact|weiterführende informationen|"
                             r"more information|hinweise zur zuständigkeit|notes on responsibility)$", re.I),
    notes="no Stand element on the page",
),
# Berlin Mietspiegel (WordPress). Checked: ber-mietspiegel.html -> 3 FAQ blocks picked up.
"mietspiegel.berlin.de": SiteProfile(
    content=("main .page-content",),
    drop=(".modul-teasertile_buehne", ".modul-download-multi", ".modul-contact", ".modul-teaser", ".modul-linkup"),
    faq_item=".c-accordion__item", faq_question=".c-accordion__title", faq_answer=".c-accordion__content",
),
# hamburg.de "km1" design system. One host, two templates:
#   Hamburg Service (/service/info/...): .km1-service-description-module; H2 "Beschreibung der Leistung",
#     H2 "Informationen" with H3 accordion items ("Wichtige Hinweise", "Ablauf, Dauer & Gebühren", ...) whose
#     panels contain *more H3s* (Voraussetzungen, Benötigte Unterlagen, Fristen, ...).
#   Behörde articles (/politik-und-verwaltung/...): article.km1-main__article, H2 per section.
# section_level=2 works for both (accordion H3s become HEADING blocks). Do NOT drop "Informationen":
# with drop_headings it removes the whole accordion (tested: 394 chars instead of 2,781).
# Checked: ham-anmeldung.html (2 sections, 2.8k), ham-blaue-karte.html (5.2k), ham-kita.html (6 sections, 8.5k).
"www.hamburg.de": SiteProfile(
    content=("main .km1-service-description-module", "main article.km1-main__article"),
    title="h1",   # empty on 111204805 -> falls back to <title>
    drop=(".km1-service-banner", ".km1-info-banner", ".km1-newsflash", ".km1-table-of-contents-article",
          ".km1-external-opt-in", ".km1-article-download", ".km1-image-opener"),
    drop_headings=re.compile(r"^(rechtsbehelf|formulare, services & links)$", re.I),
    notes="'Letzte Aktualisierung: <date>' in .km1-text-block__content equals the render date (21.11.2026 on "
          "every page fetched 22.11.) -> not a real Stand; do not use",
),
# Hamburg Welcome Center ("skhh" design). Checked: ham-welcome-blaue-karte(.en).html -> 8 sections, 5.6k.
# The visible title is an H2; the H1 is an sr-only category name ("Aufenthaltserlaubnisse").
"welcome.hamburg.de": SiteProfile(           # same for welcome.hamburg.com
    content=("main article.skhh-main__article",),
    title="h2.skhh-article__heading",
    drop=("h2.skhh-article__heading", ".skhh-table-of-contents", ".skhh-teaser-row"),
),
# frankfurt.de (Sitecore). Checked: fra-auslaenderbehoerde-blaue-karte.html, fra-mietspiegel.html, fra-kita.html.
# Title = h4._headline (h1/h2 are .h-title-hidden). Sections = h4._secheader (only on /themen pages);
# the Ausländerbehörde pages have none (1 section, 7.3k chars, <strong> pseudo-headings + one-cell layout
# tables .rte-tbl-wrd-wrap that become markdown tables -> consider unwrapping single-cell tables).
"frankfurt.de": SiteProfile(
    content=("article#articlePage",),
    title="h4._headline",
    drop=("h3._categoryTitle", "h4._headline", "figure", ".teasers", "#cookieModal"),
    section_level=4,
    notes="Cloudflare: /leistungen/* and /english/* return 403 challenge to non-browsers",
),
# stadt-koeln.de. Checked: cgn-auslaenderbehoerde-blaue-karte.html (10 sections, 7k), cgn-kita-faq.html (31).
# Accordions are div.accordionhead > h2.flexheadline + div.accordionpanel (not hidden) -> plain H2 sections.
"www.stadt-koeln.de": SiteProfile(
    content=("main#inhalt",),
    title="h1.articlehead",
    drop=(".innersearch", "#breadcrumb", ".produkt_kontakt", ".aehnliche_dienstleistungen", "aside", ".unsichtbar"),
    drop_headings=re.compile(r"^(anfahrt|kontakt und erreichbarkeit|online beantragen|vorsprache)$", re.I),
),
# stuttgart.de + welcome.stuttgart.de ("SP" design, same CMS). Checked: str-anmeldung.html,
# str-auslaenderbehoerde-blaue-karte.html, str-welcome-niederlassung.html, str-kita.html, str-mietspiegel.html.
"www.stuttgart.de": SiteProfile(              # also "welcome.stuttgart.de"
    content=(".SP-ArticleContent",),
    title="h1.SP-Headline--article",
    drop=(".SP-DigitalService", ".SP-Section__wrapper", ".SP-CallToAction", ".SP-Contact", ".SP-Share",
          ".SP-JumboButton", ".SP-CardTeaser", ".SP-LastUpdatedTimestamp"),
    drop_headings=re.compile(r"^(termin vereinbaren|formulare|weitere informationen)$", re.I),
    stand=".SP-LastUpdatedTimestamp",          # "Stand: 03.06.2026" (not on /organigramm/leistungen pages)
),
# recht.nrw.de (if read with html.py rather than a dedicated law parser). Checked: nw-mietpreisbremse.html
# -> 3 sections (§ 1, § 2, § 3). Each § = section.legaldoc-article > div.paragraph--type--article with an H2.
"recht.nrw.de": SiteProfile(
    content=("#block-rnrw-content article",),
    title="h1",
    drop=(".paragraph--action-alert", ".footnote-container", ".paragraph--type--footnotes"),
    stand="#block-rnrw-legal-document-info-box",   # "Stammnorm Ausfertigungsdatum 28.01.2025 Fassung Gültig ab 07.11.2025"
),
# mlw.baden-wuerttemberg.de. Checked: bw-mietpreisbremse-info.html -> 6 sections, 7 FAQ blocks.
"mlw.baden-wuerttemberg.de": SiteProfile(
    content=("main article.article",),
    drop=(".link-list", ".newsletter-breaker", ".js-reading-time"),
    faq_item=".accordion__item", faq_question=".accordion__header", faq_answer=".accordion__content",
),
```

**Code change needed for Stuttgart (blocker).** `_GLOBAL_DROP` removes `[aria-hidden=true]`. On stuttgart.de
and welcome.stuttgart.de every collapsible body (`.SP-Collapsible__content`) is `aria-hidden="true"
style="display:none"` in the server HTML. Trial results with the attribute stripped vs. as-is:

| file | as-is | with `aria-hidden` removed from `.SP-Collapsible__content` |
|---|---|---|
| str-anmeldung | 1 section, 1,441 chars | 6 sections, 4,257 chars |
| str-auslaenderbehoerde-blaue-karte | 1 section, 594 chars | 8 sections, 4,496 chars |
| str-welcome-niederlassung | 1,065 chars | 7,060 chars |
| str-kita | 2,123 chars | 7,544 chars |

Proposal: a `SiteProfile.unhide: tuple[str, ...]` (selectors whose `hidden`/`aria-hidden` is removed before
the global drop). A second issue on welcome.stuttgart.de: each permit type is an H2 (`.SP-Section`) followed by a
collapsible whose trigger is *also* an H2 ("Voraussetzung"). That gives sections named "Voraussetzung" without
their parent. Fix: treat `.SP-Collapsible__trigger` headings as level 3 (e.g. a `demote` selector list). No other
host lost more than 330 characters to the global hidden-drop (scan over all samples).

**Law PDFs.** BE, HH, HE and BW law text is only available robots-compliantly as gazette PDFs. `pdftotext -layout`
(available in the dev shell) extracts clean text. Caveats: the HmbGVBl PDF is a whole issue (cut out pp. 684-686);
the Hessen Anlage 1 and NRW Anlage are multi-column lists (use `-raw`, or parse the table); the BW PDFs have
60+ pages of Begründung (keep §§ only, or treat the Begründung as a separate guide). Suggested: a `law_pdf` parser
that produces `LawDocument` like `bayern_recht.py`, splitting on `^§ \d+` lines.

---

## 3. verwaltung.bund.de shortcut: verdict **no (not usable as a systematic source)**

- **Generic service pages are fetchable, but not local.** `https://verwaltung.bund.de/leistungsverzeichnis/DE/leistung/99115005104000`
  ("Wohnsitz anmelden") returns 200 with only about 640 characters of main text: a teaser plus "Bitte wählen Sie aus,
  wo Sie die Leistung beantragen möchten: Region auswählen". The region picker is a JS modal (Nuxt app).
- **Region-specific pages are server-rendered**, but the URL needs a publisher id that cannot be derived. Example found via
  web search: `.../leistung/99115005104000/herausgeber/HH-S1000020010000012125/region/020000000000` returns 200 with 9,900
  characters of SSR content ("Umzug nach Hamburg aus einem anderen Bundesland melden": Voraussetzungen, Fristen, ...;
  sample `data/_research/bund-anmeldung-hamburg.html`). Its imprint says "Herausgeber: Keine Angabe / Letzte
  Aktualisierung: Keine Angabe". The path segment is `<mandant>-<leikaObjektId>` (from the JS bundle:
  `/api/leistung/{schluessel}/herausgeber/{mandant}-{leikaObjektId}/region/{ars}`).
- **The guessable form fails:** `.../leistung/99115005104000/region/053150000000` (Köln) and `.../064120000000`
  (Frankfurt) return **404**. The sitemap (`/leistungsverzeichnis/sitemap_de.xml`, 5,882 URLs) has **no region URLs**,
  only generic `/de/leistung/<id>` pages.
- Discovering the ids would mean calling the portal's internal JSON API (`/leistungsverzeichnis/DE/api/...`). I did not do
  that: it is undocumented, and the permission system blocked the probe. Even with ids, the content comes from the state
  editorial systems (it duplicates hamburg.de text for HH) and adds no city-specific facts beyond the responsible office.
- Conclusion: use the city portals directly. verwaltung.bund.de could at most serve as a fallback for generic federal
  service texts (the `/de/leistung/<id>` pages), not for local ones.

---

## 4. Gaps and risks

1. **Hessen rent cap changed 3 days ago.** The new MiSchuV is in force since 20.11.2026; the old one was held void by LG
   Frankfurt (04.11.2026, 2-11 S 110/26). The ministry explainer is stale. Re-check `wirtschaft.hessen.de` before
   ingesting any explainer. Answers about Frankfurt rent caps *before* 20.11.2026 are legally contested.
2. **BW has two regulations**: 2026 (expires 31.12.2026) and 2027-2029. Both are in the draft with valid_from/valid_until;
   retrieval must filter by date. The Stuttgart Mietspiegel also expires 31.12.2026 (successor pending).
3. **Köln Mietspiegel is not official** (Rheinische Immobilienbörse e.V.). Gap; only the city's Mietpreisüberhöhung page is covered.
4. **Frankfurt Anmeldung missing** (Cloudflare 403 on `/leistungen/*`); `kindernetfrankfurt.de` unusable (JS app, robots 500).
   Option: a manual save, or the Hessen "Verwaltungsportal" texts (not researched).
5. **Law parsers missing**: `law_pdf` (BE, HH, HE, BW) and a recht.nrw.de parser (or html profile). The juris state portals
   (gesetze.berlin.de, landesrecht-hamburg.de, rv.hessenrecht.hessen.de, landesrecht-bw.de) are robots-blocked for us.
6. **Stuttgart needs an html.py change** (`aria-hidden` collapsibles) or about 70-90 % of the text is lost.
7. **Content-Signal on frankfurt.de / stuttgart.de**: `use=reference`, `ai-train=no`, `ai-input` unspecified. The "chunks +
   link only" policy fits "reference"; get a legal read before launch.
8. **English coverage is thin**: real EN only on service.berlin.de (3 of 4 pages) and welcome.hamburg.com. Stuttgart EN is DeepL
   (poor: "Anmelden" becomes "Log in"); Hamburg, Köln and Frankfurt use JS translators only.
9. **Volatile content**: service.berlin.de district notices, hamburg.de render-date "Letzte Aktualisierung" (useless as Stand),
   and the BW gazette PDF URLs carry tokens (resolve via the detail page).
10. New `city` slugs and the subtopic `rent_control` (cgn-mietpreisueberhoehung) must be added to `docs/conventions.md`.

### Sample files (data/_research/)
One file per draft id (`<id>.html`, `<id>.en.html` for EN alternates, `<id>.pdf` for gazettes), plus evidence files:
`ber-rechtsvorschriften-wohnen.html` (Berlin law list), `bund-anmeldung-generic.html` / `bund-anmeldung-hamburg.html`,
`nw-mietpreisbremse-anlage1.pdf`, `ber-mietspiegel-*.html` (extra pages), `cgn-kita-faq.html`, `he-mietpreisbremse-info.html`
(stale), `robots/*.txt`.
