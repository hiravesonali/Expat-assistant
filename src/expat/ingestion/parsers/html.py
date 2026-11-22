"""Main-content extraction for portal pages -> WebDocument (sections of markdown blocks).

One generic walker plus a small *site profile* per host. The profile says where the content is,
what to throw away and how FAQ accordions look; the walker does the rest:

    content root(s) -> drop noise -> walk in document order -> headings / paragraphs / lists /
    tables / FAQ items -> group into sections at the profile's section level (usually H2)

Selectors were chosen by inspecting real pages on 2026-11-17 (see each profile). When a site
redesigns, only its profile should need to change; `tests/ingestion` holds synthetic pages that
mimic each structure.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import markdownify

from expat.ingestion.documents import Block, BlockKind, Section, WebDocument
from expat.ingestion.text import markdown_table, normalize_whitespace

_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_LISTS = ("ul", "ol", "dl")
_BLOCK_TAGS = {"p", "div", "section", "article", "table", "details", "blockquote", "pre", "main", "aside", "figure"}
_BLOCK_TAGS |= set(_HEADINGS) | set(_LISTS)

# Removed on every site: never content.
_GLOBAL_DROP = (
    "script, style, noscript, template, svg, iframe, form, button, nav, header, footer, img, picture, "
    "video, audio, input, select, [hidden], [aria-hidden=true], .visually-hidden, .sr-only, .aural"
)

# Sections whose heading matches are navigation/related-content boxes, not information.
_GLOBAL_DROP_HEADINGS = re.compile(
    r"^(seiteninhalt|inhaltsverzeichnis|page content|table of contents|links und downloads|links and downloads|"
    r"weiterführende links|verwandte themen|ähnliche leistungen|similar services|further information|"
    r"formulare|für sie zuständig|teilen|share|social media|folgen sie uns.*|downloads?)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SiteProfile:
    """How to read one site. All selectors are CSS (BeautifulSoup / soupsieve)."""

    content: tuple[str, ...] = ("main", "article", "#content", "body")  # first selector with a match wins
    title: str = "h1"
    drop: tuple[str, ...] = ()
    drop_headings: re.Pattern[str] | None = None
    drop_text: re.Pattern[str] | None = None  # paragraphs to remove ("back to top", …)
    faq_item: str = ""  # an accordion item; question/answer selectors are relative to it
    faq_question: str = ""
    faq_answer: str = ""
    section_level: int = 2  # headings at this level start a Section
    move_to_end: tuple[str, ...] = ()  # side boxes that interrupt the main text flow
    stand: str = ""  # element holding a "last updated" date
    text_cleanup: re.Pattern[str] | None = None  # removed from every block (site-specific noise)
    unhide: tuple[str, ...] = ()  # elements whose hidden / aria-hidden is removed before the global drop
    demote: tuple[str, ...] = ()  # headings treated one level lower (accordion triggers styled as H2)
    notes: str = ""


PROFILES: dict[str, SiteProfile] = {
    # Munich service pages: <main><article> with one .m-component per section (Beschreibung,
    # Voraussetzungen, Benötigte Unterlagen, Dauer und Kosten, Fragen und Antworten (accordion),
    # Rechtliche Grundlagen, Kontakt). TOC, link boxes, "Termin vereinbaren" place search and the
    # "Ähnliche Leistungen" slider are dropped.
    "stadt.muenchen.de": SiteProfile(
        content=("main article", "main"),
        title="h1",
        drop=(
            ".m-component-table-of-contents-wrapper",
            ".m-component-linklist--boxed",
            ".m-component-contentbox-small",
            ".m-component-place-search",
            ".m-a11y-actions",
            ".m-intro-vertical__button-group",
            ".m-oembed-consent-dialog",
            ".m-breadcrumb-component",
            "#context",
        ),
        drop_text=re.compile(r"^(karte öffnen|anfahrt mit mvv|nachricht schreiben|termin vereinbaren)$", re.I),
        faq_item=".m-accordion__section",
        faq_question=".m-accordion__section-header",
        faq_answer=".m-accordion__section-content",
        notes="DE binding; EN pages are DeepL machine translations",
    ),
    # familienportal: question pages (.topics-page__main, H1 = question, H2 subsections) and the
    # BMBFSFJ background pages (#article: H2 per question, no accordion markup).
    "familienportal.de": SiteProfile(
        content=(".topics-page__main", "#article .article-content", "main"),
        title="h1.page-title, #article h1",
        drop=(".dateline", ".contact-flap", ".breadcrumb", ".teaser", ".accordion-close"),
    ),
    # BayernPortal "Leistung": h1 + H2 "Leistungsdetails" containing one div.accordion per
    # section (H3 Beschreibung, Voraussetzung, Erforderliche Unterlagen, Verfahrensablauf, Kosten,
    # Fristen, Bearbeitungsdauer, Rechtsgrundlagen, …). These are procedure sections, not FAQ,
    # so section_level is 3. Responsible-authority widgets depend on a postcode -> dropped.
    "www.bayernportal.de": SiteProfile(
        content=("div.accordion",),
        title="h1",
        section_level=3,
        drop_headings=re.compile(r"^(rechtsbehelf|weiterführende links|verwandte themen|formulare)$", re.I),
        drop_text=re.compile(r"^nicht angegeben$", re.I),
        text_cleanup=re.compile(r"\(ID: \d+\)"),  # internal catalogue ids in document lists
        stand="div.text-light-text > div",
    ),
    # BAMF: article in #content .s-richtext. Service boxes (.c-service-box: "Contact", "Good to
    # know!", "The legal basis") sit *between* an H2 and its paragraphs, so we move them to the
    # end instead of letting them steal the following text. Related-links tabs are dropped.
    "www.bamf.de": SiteProfile(
        content=("#content .s-richtext", "#content"),
        title="#content h1 > span:not(.aural):not(.c-meta), #content h1",
        drop=(".c-related", ".l-intro-media", ".c-language-switch", ".c-meta", ".c-sitemap"),
        move_to_end=(".c-service-box",),
        drop_headings=re.compile(r"^contact$", re.I),
    ),
    # rundfunkbeitrag.de: a stack of .textBlock modules with H2s; FAQ pages use H2 per question.
    "www.rundfunkbeitrag.de": SiteProfile(
        content=("main",),
        title="h1",
        drop=(".breadcrumb",),
        drop_headings=re.compile(
            r"^(general information|fee rules for certain target groups|frequently asked questions)$", re.I
        ),
        drop_text=re.compile(r"^(back to|zurück zu|go to) ", re.I),
    ),
    # make-it-in-germany: saved manually (bot protection). Generic article layout with
    # accordions; selectors are best-effort until a saved page is inspected.
    "www.make-it-in-germany.com": SiteProfile(
        content=("main #main-content", "main", "article"),
        title="h1",
        drop=(".breadcrumb", ".teaser", ".related"),
        faq_item="details, .accordion__item",
        faq_question="summary, .accordion__title",
        faq_answer=".accordion__content",
    ),
    # ---- Germany-wide sources (docs/research/germany-sources.md: selectors checked on saved pages, 2026-11-22)
    # Berlin service portal: div.block > h2.title per section (Verfahrensablauf, Voraussetzungen, Unterlagen,
    # Gebühren, ...). The "Für Sie zuständig" office list alone is ~21k characters -> dropped.
    "service.berlin.de": SiteProfile(
        content=("#layout-grid__area--maincontent",),
        title="h1.title",
        drop=(
            ".modul-servicepanel",
            ".location-notes",
            "#formulare",
            "#rechtsbehelf",
            "#zustaendig",
            ".modul",
            ".js-overlay-container",
            "#toplist",
        ),
        drop_headings=re.compile(
            r"^(online-abwicklung|online processing|your point of contact|weiterführende informationen|"
            r"more information|hinweise zur zuständigkeit|notes on responsibility)$",
            re.I,
        ),
    ),
    # Berlin Mietspiegel (WordPress site of the Senate department), FAQ accordions.
    "mietspiegel.berlin.de": SiteProfile(
        content=("main .page-content",),
        drop=(".modul-teasertile_buehne", ".modul-download-multi", ".modul-contact", ".modul-teaser", ".modul-linkup"),
        faq_item=".c-accordion__item",
        faq_question=".c-accordion__title",
        faq_answer=".c-accordion__content",
    ),
    # hamburg.de "km1": service pages (accordion H3s inside H2 "Informationen" -- do NOT drop that heading)
    # and authority articles. "Letzte Aktualisierung" is the render date, so it is not used as a Stand.
    "www.hamburg.de": SiteProfile(
        content=("main .km1-service-description-module", "main article.km1-main__article"),
        title="h1",
        drop=(
            ".km1-service-banner",
            ".km1-info-banner",
            ".km1-newsflash",
            ".km1-table-of-contents-article",
            ".km1-external-opt-in",
            ".km1-article-download",
            ".km1-image-opener",
        ),
        drop_headings=re.compile(r"^(rechtsbehelf|formulare, services & links)$", re.I),
    ),
    # Hamburg Welcome Center (German and English site): the visible title is an H2, the H1 is sr-only.
    "welcome.hamburg.de": SiteProfile(
        content=("main article.skhh-main__article",),
        title="h2.skhh-article__heading",
        drop=("h2.skhh-article__heading", ".skhh-table-of-contents", ".skhh-teaser-row"),
    ),
    # frankfurt.de (Sitecore): title + section headings are H4; foreign-office pages have no headings.
    # Cloudflare blocks /leistungen/* and /english/* for non-browsers (those pages are not used).
    "frankfurt.de": SiteProfile(
        content=("article#articlePage",),
        title="h4._headline",
        drop=("h3._categoryTitle", "h4._headline", "figure", ".teasers", "#cookieModal"),
        section_level=4,
    ),
    # stadt-koeln.de: accordions are div.accordionhead > h2 + visible div.accordionpanel -> H2 sections.
    "www.stadt-koeln.de": SiteProfile(
        content=("main#inhalt",),
        title="h1.articlehead",
        drop=(".innersearch", "#breadcrumb", ".produkt_kontakt", ".aehnliche_dienstleistungen", "aside", ".unsichtbar"),
        drop_headings=re.compile(r"^(anfahrt|kontakt und erreichbarkeit|online beantragen|vorsprache)$", re.I),
    ),
    # stuttgart.de: every collapsible body is aria-hidden in the server HTML (70-90 % of the text) -> unhide.
    "www.stuttgart.de": SiteProfile(
        content=(".SP-ArticleContent",),
        title="h1.SP-Headline--article",
        drop=(
            ".SP-DigitalService__button",
            ".SP-CallToAction",
            ".SP-Contact",
            ".SP-Share",
            ".SP-JumboButton",
            ".SP-CardTeaser",
            ".SP-LastUpdatedTimestamp",
        ),
        drop_headings=re.compile(r"^(termin vereinbaren|formulare|weitere informationen)$", re.I),
        stand=".SP-LastUpdatedTimestamp",
        unhide=(".SP-Collapsible__content",),
    ),
    # recht.nrw.de: one section.legaldoc-article per § with an H2 (read as a web page, § = section).
    "recht.nrw.de": SiteProfile(
        content=("#block-rnrw-content article",),
        title="h1",
        drop=(".paragraph--action-alert", ".footnote-container", ".paragraph--type--footnotes"),
        stand="#block-rnrw-legal-document-info-box",
    ),
    # Baden-Württemberg housing ministry explainer (FAQ accordions).
    "mlw.baden-wuerttemberg.de": SiteProfile(
        content=("main article.article",),
        drop=(".link-list", ".newsletter-breaker", ".js-reading-time"),
        faq_item=".accordion__item",
        faq_question=".accordion__header",
        faq_answer=".accordion__content",
    ),
}
# Same layout on sister hosts.
PROFILES["welcome.hamburg.com"] = PROFILES["welcome.hamburg.de"]
PROFILES["welcome.stuttgart.de"] = dataclasses.replace(
    PROFILES["www.stuttgart.de"],
    # Each permit type is an H2 section; its collapsible triggers ("Voraussetzung") are H2s too -> one level down.
    demote=("h2.SP-Collapsible__trigger__text",),
)
DEFAULT_PROFILE = SiteProfile()


def profile_for(url: str) -> SiteProfile:
    host = urlsplit(url).netloc.lower()
    return PROFILES.get(host) or PROFILES.get(host.removeprefix("www.")) or DEFAULT_PROFILE


# ---------------------------------------------------------------------------------------------


@dataclass
class _Event:
    """A flat item in reading order: a heading (level>0) or a content block (level 0)."""

    level: int
    text: str = ""
    block: Block | None = None


@dataclass
class _Walker:
    profile: SiteProfile
    events: list[_Event] = field(default_factory=list)

    def walk(self, element: Tag) -> None:
        for child in element.children:
            if isinstance(child, Tag):
                self._visit(child)
            elif type(child) is NavigableString:  # not Comment/Doctype (subclasses of NavigableString)
                # Loose text next to block elements, e.g. "<div>Intro <ul>…</ul></div>".
                self._add(BlockKind.TEXT, normalize_whitespace(str(child)))

    def _visit(self, el: Tag) -> None:
        name = el.name or ""
        if self.profile.faq_item and el.css.match(self.profile.faq_item) and el.select_one(self.profile.faq_question):
            self._faq_from_accordion(el)
        elif name == "details":
            self._faq_from_details(el)
        elif name in _HEADINGS:
            if name == "h1":
                return  # page title, read separately
            text = normalize_whitespace(el.get_text(" "))
            if text:
                self.events.append(_Event(level=int(name[1]), text=text))
        elif name == "table":
            self._add(BlockKind.TABLE, _table_to_markdown(el))
        elif name in _LISTS:
            self._add(BlockKind.LIST, _to_markdown(el))
        elif name == "p" or not _has_block_children(el):
            self._add(BlockKind.TEXT, _to_markdown(el))
        else:
            self.walk(el)

    def _add(self, kind: BlockKind, text: str, question: str = "") -> None:
        if self.profile.text_cleanup:
            text = normalize_whitespace(self.profile.text_cleanup.sub("", text))
        text = text.strip()
        if not text:
            return
        plain = re.sub(r"^[-*\s]+|[*\s]+$", "", text)  # ignore list bullets / bold markers
        if kind in (BlockKind.TEXT, BlockKind.LIST) and self.profile.drop_text and self.profile.drop_text.search(plain):
            return
        self.events.append(_Event(level=0, block=Block(kind=kind, text=text, question=question)))

    def _faq_from_accordion(self, el: Tag) -> None:
        question_el = el.select_one(self.profile.faq_question)
        answer_el = el.select_one(self.profile.faq_answer) if self.profile.faq_answer else None
        question = normalize_whitespace(question_el.get_text(" ")) if question_el else ""
        if answer_el is None and question_el is not None:
            question_el.extract()
            answer_el = el
        answer = _to_markdown(answer_el) if answer_el is not None else ""
        if question and answer:
            self.events.append(_Event(level=0, block=Block(kind=BlockKind.FAQ, text=answer, question=question)))

    def _faq_from_details(self, el: Tag) -> None:
        summary = el.find("summary")
        question = normalize_whitespace(summary.get_text(" ")) if isinstance(summary, Tag) else ""
        if isinstance(summary, Tag):
            summary.extract()
        answer = _to_markdown(el)
        if question and answer:
            self.events.append(_Event(level=0, block=Block(kind=BlockKind.FAQ, text=answer, question=question)))


def _has_block_children(el: Tag) -> bool:
    return any(isinstance(d, Tag) and d.name in _BLOCK_TAGS for d in el.descendants)


def _to_markdown(el: Tag) -> str:
    """HTML fragment -> markdown. Links keep their text only (URLs would pollute embeddings/BM25)."""
    md = markdownify(
        str(el),
        heading_style="ATX",
        bullets="-",
        strip=["a", "span", "img"],
        escape_misc=False,
        escape_asterisks=False,
        escape_underscores=False,
    )
    md = normalize_whitespace(md)
    md = re.sub(r"^\s*-\s*$", "", md, flags=re.MULTILINE)  # empty bullets
    return normalize_whitespace(md)


def _table_to_markdown(table: Tag) -> str:
    def cells(row: Tag) -> list[str]:
        return [normalize_whitespace(c.get_text(" ")) for c in row.find_all(["th", "td"], recursive=False)]

    rows = [r for r in table.find_all("tr") if r.find_parent("table") is table]
    if not rows:
        return ""
    first = rows[0]
    has_header = bool(first.find_all("th", recursive=False)) or first.find_parent("thead") is not None
    header = cells(first) if has_header else []
    body = [c for c in (cells(r) for r in (rows[1:] if has_header else rows)) if any(c)]
    return markdown_table(header, body)


def parse_html(html: str, url: str, profile: SiteProfile | None = None) -> WebDocument:
    """Parse one saved page into a WebDocument."""
    profile = profile or profile_for(url)
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(profile.title)
    title = normalize_whitespace(title_el.get_text(" ")) if title_el else ""
    if not title and soup.title:
        title = normalize_whitespace(soup.title.get_text(" ")).split(" - ")[0]
    stand_el = soup.select_one(profile.stand) if profile.stand else None
    stand = normalize_whitespace(stand_el.get_text(" ")) if stand_el else ""

    roots: list[Tag] = []
    for selector in profile.content:
        matches = soup.select(selector)
        # Keep only outermost matches, so nested matches are not walked twice.
        roots = [r for r in matches if not any(p is not r and r in p.descendants for p in matches)]
        if roots:
            break
    if not roots:
        roots = [soup.body or soup]

    for root in roots:
        # Accordion questions often live in a <button> inside the heading; keep the text.
        for button in root.select("h2 button, h3 button, h4 button, h5 button, summary button"):
            button.unwrap()
        # Collapsed accordion bodies that are real content (server HTML marks them hidden until clicked).
        for selector in profile.unhide:
            for el in root.select(selector):
                for attr in ("hidden", "aria-hidden"):
                    del el[attr]
        # Headings that are sub-headings in disguise (e.g. an accordion trigger styled as H2): one level down.
        for selector in profile.demote:
            for el in root.select(selector):
                if el.name in _HEADINGS and el.name != "h6":
                    el.name = f"h{int(el.name[1]) + 1}"
        for el in root.select(_GLOBAL_DROP + "".join(f", {s}" for s in profile.drop)):
            el.decompose()
        for selector in profile.move_to_end:
            for el in root.select(selector):
                root.append(el.extract())

    walker = _Walker(profile)
    for root in roots:
        walker.walk(root)
    return WebDocument(url=url, title=title, sections=_group(walker.events, profile), stand=stand)


def _group(events: list[_Event], profile: SiteProfile) -> list[Section]:
    """Turn the flat event stream into Sections at `profile.section_level`.

    - headings above the section level are kept as `context`;
    - headings below it become HEADING blocks inside the current section;
    - sections whose heading matches the drop lists are removed with their content.
    """
    sections: list[Section] = [Section(heading="")]
    context: dict[int, str] = {}
    dropping_level: int | None = None  # while set, everything until the next heading <= it is skipped

    for event in events:
        if event.level:
            if dropping_level is not None and event.level > dropping_level:
                continue  # sub-heading of a dropped section
            dropping_level = None
            if _is_dropped_heading(event.text, profile):
                dropping_level = event.level
                continue
            if event.level < profile.section_level:
                context = {lvl: txt for lvl, txt in context.items() if lvl < event.level}
                context[event.level] = event.text
                sections.append(Section(heading="", context=_context(context, profile.section_level)))
            elif event.level == profile.section_level:
                sections.append(Section(heading=event.text, context=_context(context, profile.section_level)))
            else:
                sections[-1].blocks.append(Block(kind=BlockKind.HEADING, text=event.text))
        elif dropping_level is None and event.block is not None:
            sections[-1].blocks.append(event.block)

    # Sections with only sub-headings and no content (e.g. a heading over a dropped widget) are noise.
    return [s for s in sections if any(b.kind != BlockKind.HEADING for b in s.blocks)]


def _context(context: dict[int, str], below: int) -> list[str]:
    return [txt for lvl, txt in sorted(context.items()) if lvl < below]


def _is_dropped_heading(text: str, profile: SiteProfile) -> bool:
    clean = text.strip().rstrip(":")
    if _GLOBAL_DROP_HEADINGS.match(clean):
        return True
    return bool(profile.drop_headings and profile.drop_headings.match(clean))
