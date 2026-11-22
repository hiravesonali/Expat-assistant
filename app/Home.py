"""Ankommen (Expat Germany Assistant): the chat page (Streamlit entrypoint, `streamlit run app/Home.py`).

How this page works (Streamlit's rerun model)
--------------------------------------------
This file is not a component that mounts once. Streamlit executes it TOP TO BOTTOM on every
interaction: a chat message, a button click, a form submit. Think of the whole script as one big
render function whose "props" are `st.session_state` plus the widget values.

So the flow of one chat turn is:
1. The user submits a message -> rerun. `st.chat_input` returns the text in THIS run only.
2. We append it to the conversation in `st.session_state`, run the pipeline, and stream the answer.
3. We save the finished events in session_state and call `st.rerun()`. The next run redraws the full
   history from state (with source pills, banners, and the updated sidebar conversation title).

Design (chat-product style): the first screen shows only a greeting, the composer and four
suggestions. Profile, mode and developer tools sit in two small menus at the bottom of the sidebar.

Everything the user enters (profile, conversations) lives only in `st.session_state`, i.e. in server
memory for this browser tab. It is gone when the tab closes (ADR-0007/0009: nothing is persisted).
"""

import math
import time
import uuid
from datetime import date
from typing import Any

import _bootstrap  # noqa: F401  (must be first: makes `expat` importable on Streamlit Cloud)
import export
import i18n
import streamlit as st
import ui
from i18n import t
from pipeline_adapter import DEMO, LIVE, live_status, run_pipeline, sync_secrets_to_env

from expat.config import get_settings
from expat.guards import DailyCap, QuestionCheck, SlidingWindowLimiter, check_question
from expat.places import STATES, SUPPORTED_CITIES, city_label
from expat.schemas import (
    AnswerMetaEvent,
    ClarificationEvent,
    ErrorEvent,
    PipelineEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserProfile,
)
from expat.schemas.profile import Citizenship, Housing, ResidenceStatus

# `set_page_config` must be the first Streamlit call of the run.
st.set_page_config(page_title=f"{ui.BRAND_NAME} · {t('tagline')}", page_icon=ui.LOGO_PNG, layout="centered")
ui.inject_css()
sync_secrets_to_env()

OTHER_CITY = "__other__"
ASSISTANT_AVATAR = ui.LOGO_PNG


def examples() -> list[tuple[str, str, str, str]]:
    """Topic cards on the start screen, in the interface language: (icon, title, description, prompt)."""
    return i18n.pick(i18n.EXAMPLES)


def profile_ui() -> dict[str, tuple[str, dict[str, str]]]:
    """Profile form labels in the interface language: field -> (label, {enum value: label})."""
    return i18n.pick(i18n.PROFILE_LABELS)


ADMIN_PAGES = [
    ("pages/1_🔎_Retrieval_Debugger.py", "Retrieval debugger", ":material/search_insights:"),
    ("pages/2_📚_Collection_Browser.py", "Collection browser", ":material/library_books:"),
    ("pages/3_📊_Evals.py", "Evaluation results", ":material/monitoring:"),
    ("pages/4_⚙️_Ingestion_Status.py", "Ingestion status", ":material/sync:"),
]


# ------------------------------------------------------------------------------------------------
# Session state ("the store"). `setdefault` only runs the first time in a browser session.
# ------------------------------------------------------------------------------------------------


def _new_conversation() -> str:
    conv_id = uuid.uuid4().hex[:8]
    st.session_state.conversations[conv_id] = {"title": "New chat", "messages": []}
    st.session_state.current = conv_id
    return conv_id


def init_state() -> None:
    st.session_state.setdefault("lang", i18n.DEFAULT_LANGUAGE)  # English unless the user switches
    st.session_state.setdefault("profile", UserProfile(answer_language=st.session_state.lang))
    st.session_state.setdefault("profile_saved", False)
    st.session_state.setdefault("conversations", {})
    if not st.session_state.get("current") or st.session_state.current not in st.session_state.conversations:
        _new_conversation()


def current_conversation() -> dict[str, Any]:
    return st.session_state.conversations[st.session_state.current]


# ------------------------------------------------------------------------------------------------
# Callbacks. `on_click` callbacks run BEFORE the next rerun draws anything, so the state they set is
# already visible at the top of the script. (Like a setState that is flushed before the re-render.)
# ------------------------------------------------------------------------------------------------


def _on_new_conversation() -> None:
    if current_conversation()["messages"]:
        _new_conversation()


def _on_select_conversation(conv_id: str) -> None:
    st.session_state.current = conv_id


def _on_example(prompt: str) -> None:
    st.session_state.pending_prompt = prompt


def _on_retry() -> None:
    """Drop the failed assistant turn + its question, and resubmit the question."""
    messages = current_conversation()["messages"]
    if messages and messages[-1]["role"] == "assistant":
        messages.pop()
    if messages and messages[-1]["role"] == "user":
        st.session_state.pending_prompt = messages.pop()["content"]


# ------------------------------------------------------------------------------------------------
# Sidebar: brand, new chat, recents; profile + settings menus pinned at the bottom
# ------------------------------------------------------------------------------------------------


def _select_profile_field(name: str, current: Any) -> Any:
    """One selectbox per enum field, generated from the UserProfile model (UNKNOWN = prefer not to say)."""
    label, labels = profile_ui().get(name, (name.replace("_", " ").capitalize(), {}))
    enum_cls = type(current)
    options = [v for v in enum_cls if v.value != "unknown"] + [enum_cls("unknown")]
    return st.selectbox(
        label,
        options,
        index=options.index(current),
        format_func=lambda v: t("prefer") if v.value == "unknown" else labels.get(v, v.value.replace("_", " ").title()),
        key=f"pf_{name}",
    )


def profile_short() -> str:
    """Popover label: 'Blue Card · 2 kids · renting', or a call to action before the profile is set."""
    if not st.session_state.profile_saved:
        return t("personalise")
    p: UserProfile = st.session_state.profile
    bits: list[str] = [city_label(p.city)] if p.city else ([STATES[p.state].split(" (")[0]] if p.state else [])
    if p.residence_status != ResidenceStatus.UNKNOWN:
        bits.append(profile_ui()["residence_status"][1].get(p.residence_status, p.residence_status.value))
    elif p.citizenship != Citizenship.UNKNOWN:
        bits.append(profile_ui()["citizenship"][1].get(p.citizenship, p.citizenship.value))
    if p.children_count:
        bits.append(f"{p.children_count} kid{'s' if p.children_count > 1 else ''}")
    if p.housing != Housing.UNKNOWN:
        bits.append(p.housing.value)
    return " · ".join(bits[:3]) or t("your_profile")


CITY_OPTIONS = ["", *SUPPORTED_CITIES, OTHER_CITY]
STATE_OPTIONS = ["", *STATES]


def render_location_fields(profile: UserProfile) -> dict[str, Any]:
    """City + state pickers inside the profile form. Returns {"city", "state"} for UserProfile.

    Widgets in a form don't rerun on change, so "other city" and the state picker are always visible:
    a supported city sets its state automatically (UserProfile validator); for any other place the user
    types the name and picks the state, which still unlocks state-level rules (e.g. the rent cap).
    """
    supported = profile.city in SUPPORTED_CITIES
    city_choice = st.selectbox(
        t("city"),
        CITY_OPTIONS,
        index=CITY_OPTIONS.index(profile.city if supported else (OTHER_CITY if profile.city else "")),
        format_func=lambda v: t("prefer") if v == "" else t("other_city_option") if v == OTHER_CITY else city_label(v),
        help=t("city_help"),
        key="pf_city",
    )
    other_name = st.text_input(
        t("other_city"), value="" if supported else (profile.city or "").title(), key="pf_city_other"
    )
    state = st.selectbox(
        t("state"),
        STATE_OPTIONS,
        index=STATE_OPTIONS.index(profile.state or ""),
        format_func=lambda v: t("prefer") if v == "" else STATES[v],
        help=t("state_help"),
        key="pf_state",
    )
    if city_choice == OTHER_CITY:
        return {"city": other_name.strip() or None, "state": state or None}
    return {"city": city_choice or None, "state": state or None}


def render_profile_form() -> None:
    profile: UserProfile = st.session_state.profile
    st.markdown(f"**{t('your_situation')}**")
    st.caption(t("situation_caption"))
    # A form batches its widgets: changing a selectbox does NOT rerun the script, only the submit does.
    with st.form("profile_form", border=False):
        values: dict[str, Any] = render_location_fields(profile)
        for name in UserProfile.model_fields:
            if name in ("city", "state"):
                continue
            if name == "children_count":
                # -1 = "prefer not to say". (A None option would render as an empty "Choose an option".)
                kids = st.selectbox(
                    t("children"),
                    [-1, *range(0, 11)],
                    index=0 if not st.session_state.profile_saved else profile.children_count + 1,
                    format_func=lambda v: t("prefer") if v < 0 else str(v),
                    key="pf_children_count",
                )
                values[name] = max(kids, 0)
            elif name == "youngest_child_age":
                ages = [-1, *range(0, 26)]
                age = st.selectbox(
                    t("youngest_age"),
                    ages,
                    index=ages.index(-1 if profile.youngest_child_age is None else profile.youngest_child_age),
                    format_func=lambda v: t("prefer") if v < 0 else t("years", n=v),
                    help=t("youngest_help"),
                    key="pf_youngest_child_age",
                )
                values[name] = None if age < 0 else age
            elif name == "answer_language":
                values[name] = i18n.lang()  # set by the language switch at the top, not in this form
            else:
                values[name] = _select_profile_field(name, getattr(profile, name))  # enum fields
        if st.form_submit_button(t("save_profile"), type="primary", width="stretch"):
            if not values["children_count"]:
                values["youngest_child_age"] = None
            st.session_state.profile = UserProfile(**values)
            st.session_state.profile_saved = True
            st.toast(t("saved"), icon=":material/check:")
            st.rerun()  # refresh the popover label


def render_settings() -> str:
    available, reason = live_status()
    st.markdown(f"**{t('settings')}**")
    live = st.toggle(
        t("live_answers"),
        value=available,
        disabled=not available,
        key="live_toggle",
        help=t("live_help") + ("" if available else f"\n\n{reason}"),
    )
    st.caption(t("dev_tools"))
    for path, label, icon in ADMIN_PAGES:
        st.page_link(path, label=label, icon=icon)
    st.divider()
    st.caption(f":material/gavel: {t('disclaimer')} {t('privacy')}")
    return LIVE if (live and available) else DEMO


def render_conversation_list() -> None:
    started = [(cid, c) for cid, c in reversed(st.session_state.conversations.items()) if c["messages"]]
    if not started:
        return
    st.caption(t("recents"))
    with st.container(key="recents", gap=None):
        for cid, conv in started:
            st.button(
                conv["title"],
                key=f"conv-{cid}",
                type="secondary" if cid == st.session_state.current else "tertiary",
                width="stretch",
                on_click=_on_select_conversation,
                args=(cid,),
            )


def render_sidebar() -> str:
    with st.sidebar:
        ui.brand_header()
        with st.container(key="new-chat"):
            st.button(
                t("new_chat"),
                icon=":material/edit_square:",
                type="tertiary",
                width="stretch",
                on_click=_on_new_conversation,
            )
        render_conversation_list()
        with st.container(key="sidebar-bottom"):
            with st.popover(profile_short(), icon=":material/person:", width="stretch"):
                render_profile_form()
            conv = current_conversation()
            if conv["messages"]:
                with st.popover(t("export_chat"), icon=":material/download:", width="stretch"):
                    render_export(conv)
            with st.popover(t("settings"), icon=":material/tune:", width="stretch"):
                mode = render_settings()
    return mode


def render_export(conv: dict[str, Any]) -> None:
    """Download the current chat: Markdown to read or share, JSON with sources, tool calls and costs."""
    s = get_settings()
    prices = (s.price_in_per_mtok, s.price_out_per_mtok)
    st.download_button(
        "Markdown (.md)",
        data=export.to_markdown(conv, *prices),
        file_name=export.filename(conv, "md"),
        mime="text/markdown",
        icon=":material/description:",
        width="stretch",
        on_click="ignore",  # don't rerun the app on download
    )
    st.download_button(
        "JSON (.json)",
        data=export.to_json(conv, *prices),
        file_name=export.filename(conv, "json"),
        mime="application/json",
        icon=":material/data_object:",
        width="stretch",
        on_click="ignore",
    )
    st.caption(t("export_caption"))


# ------------------------------------------------------------------------------------------------
# Main area
# ------------------------------------------------------------------------------------------------


def render_empty_state() -> str | None:
    """Brand hero + composer + topic cards + trust row. Returns a submitted prompt."""
    ui.hero()
    # Inside a container, st.chat_input renders inline (here: centred) instead of pinned to the bottom.
    with st.container():
        prompt = st.chat_input(t("placeholder"), key="composer", max_chars=get_settings().max_question_chars)
    with st.container(key="suggestions"):
        for i, (icon, title, blurb, full_prompt) in enumerate(examples()):
            st.button(
                f"**{title}**\n{blurb}",  # CSS `white-space: pre-line` turns the newline into a second line
                icon=icon,
                key=f"example-{i}",
                on_click=_on_example,
                args=(full_prompt,),
                help=full_prompt,
            )
    ui.trust_row()
    ui.disclaimer_footer()
    return prompt


def render_history(conv: dict[str, Any]) -> None:
    messages = conv["messages"]
    for i, msg in enumerate(messages):
        with st.chat_message(msg["role"], avatar=ASSISTANT_AVATAR if msg["role"] == "assistant" else None):
            if msg["role"] == "user":
                st.markdown(msg["content"])
                continue
            ui.render_assistant_message(
                msg["events"], msg["content"], key_prefix=f"{st.session_state.current}-{i}", mode=msg["mode"]
            )
            is_last = i == len(messages) - 1
            error = next((e for e in msg["events"] if isinstance(e, ErrorEvent)), None)
            if is_last and error and error.retryable:
                st.button(t("try_again"), icon=":material/refresh:", key=f"retry-{i}", on_click=_on_retry)
            clarification = next((e for e in msg["events"] if isinstance(e, ClarificationEvent)), None)
            if is_last and clarification:
                render_city_picker(clarification)


def render_city_picker(clarification: ClarificationEvent) -> None:
    """One-click answers to "Which city do you live in?" (plus a small form for any other place)."""
    with st.container(horizontal=True, gap="small", key="city-picker"):
        for value, label in clarification.options:
            if value == OTHER_CITY or value == "other":
                continue
            st.button(
                label,
                key=f"pick-city-{value}",
                icon=":material/location_on:",
                on_click=_on_pick_location,
                args=(value, None, clarification.original_question),
            )
    with st.expander(t("another_city"), icon=":material/map:"), st.form("other-city-form", border=False):
        name = st.text_input(t("city"), placeholder=t("city_placeholder"))
        state = st.selectbox(t("state"), list(STATES), format_func=STATES.get)
        if st.form_submit_button(t("use_place"), type="primary"):
            _on_pick_location(name.strip() or None, state, clarification.original_question)
            st.rerun()


def _on_pick_location(city: str | None, state: str | None, question: str) -> None:
    """Save the place in the profile, drop the 'Which city?' exchange and re-ask the original question."""
    profile: UserProfile = st.session_state.profile
    st.session_state.profile = UserProfile(**{**profile.model_dump(), "city": city, "state": state})
    st.session_state.profile_saved = True
    messages = current_conversation()["messages"]
    if messages and messages[-1]["role"] == "assistant":
        messages.pop()
    if messages and messages[-1]["role"] == "user":
        messages.pop()
    st.session_state.pending_prompt = question


def _history_for_pipeline(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    turns = get_settings().history_turns
    return [{"role": m["role"], "content": m["content"]} for m in messages[-2 * turns :]] if turns else []


@st.cache_resource
def _daily_cap() -> DailyCap:
    """ONE counter per server process, shared by every visitor (st.cache_resource = process-wide singleton)."""
    return DailyCap(get_settings().daily_question_cap)


def question_error(check: QuestionCheck) -> str:
    """The validation message in the interface language."""
    if check.reason == "too_long":
        return t("too_long", n=check.length, max=get_settings().max_question_chars)
    return t("empty_question")


def admit_question(raw: str, mode: str) -> str | None:
    """Validate the question and apply the usage limits (Live mode only). Returns the cleaned text or None.

    The UI also caps the input box (max_chars), but a pending prompt (suggestion, retry) bypasses the widget,
    so the server-side check here is the one that counts. See expat/guards.py for the three limit layers.
    """
    s = get_settings()
    check = check_question(raw, s.max_question_chars)
    if check.error:
        st.warning(question_error(check), icon=":material/edit_note:")
        return None
    if mode != LIVE:
        return check.text  # demo answers are scripted and free
    limiter = st.session_state.setdefault("limiter", SlidingWindowLimiter(s.questions_per_hour, 3600))
    if (wait := limiter.try_acquire(time.monotonic())) is not None:
        st.warning(
            t("rate_limited", n=s.questions_per_hour, minutes=math.ceil(wait / 60)),
            icon=":material/hourglass_top:",
        )
        return None
    if not _daily_cap().try_acquire(date.today()):
        st.warning(
            t("daily_cap"),
            icon=":material/hourglass_top:",
        )
        return None
    return check.text


def handle_prompt(prompt: str, mode: str) -> None:
    conv = current_conversation()
    history = _history_for_pipeline(conv["messages"])
    conv["messages"].append({"role": "user", "content": prompt})
    if conv["title"] == "New chat":
        conv["title"] = prompt if len(prompt) <= 42 else prompt[:40].rstrip() + "…"

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        # Containers are created up-front, then filled while the generator runs (like refs to DOM nodes).
        status = st.status(t("thinking"), expanded=False)
        tool_area = st.container()
        events: list[PipelineEvent] = []
        tool_slots: dict[str, Any] = {}
        calls: dict[str, ToolCallEvent] = {}

        def token_stream():
            """Route events: tokens go to st.write_stream, everything else updates the progress line."""
            for ev in run_pipeline(mode, prompt, history, st.session_state.profile):
                events.append(ev)
                if isinstance(ev, TokenEvent):
                    yield ev.text
                elif isinstance(ev, StepEvent) and ev.status == "started":
                    _, label = ui.step_label(ev.name)
                    status.update(label=f"{label}…", state="running")
                elif isinstance(ev, ToolCallEvent):
                    calls[ev.call_id] = ev
                    tool_slots[ev.call_id] = tool_area.empty()
                    with tool_slots[ev.call_id].container():
                        ui.render_tool_line(ev, None)
                elif isinstance(ev, ToolResultEvent) and ev.call_id in calls:
                    with tool_slots[ev.call_id].container():
                        ui.render_tool_line(calls[ev.call_id], ev)

        # write_stream pulls from the generator and renders text as it arrives (typewriter effect).
        answer = st.write_stream(token_stream())
        status.update(label=t("done"), state="complete")

    # Persist the post-checked text (invalid citations stripped) rather than the raw streamed tokens.
    final = next((ev.final_answer for ev in events if isinstance(ev, AnswerMetaEvent) and ev.final_answer), None)
    content = final if final is not None else (answer if isinstance(answer, str) else "")
    conv["messages"].append({"role": "assistant", "content": content, "events": events, "mode": mode})
    # Redraw everything from state: the progress line disappears, source pills and the details fold appear.
    st.rerun()


def _on_language_change() -> None:
    """The switch sets the interface language AND the answer language (profile.answer_language)."""
    choice = st.session_state.get("lang_switch")
    if choice in i18n.LANGUAGES:  # a segmented control can be clicked "off" (None): keep the current language
        st.session_state.lang = choice
        st.session_state.profile = st.session_state.profile.model_copy(update={"answer_language": choice})


def render_language_switch() -> None:
    """Compact English | Deutsch switch, pinned to the top-right corner (CSS: .st-key-lang-switch)."""
    with st.container(key="lang-switch"):
        st.segmented_control(
            t("language"),
            list(i18n.LANGUAGES),
            default=i18n.lang(),
            format_func=i18n.LANGUAGES.get,
            key="lang_switch",
            on_change=_on_language_change,
            label_visibility="collapsed",
        )


def main() -> None:
    init_state()
    render_language_switch()
    mode = render_sidebar()
    if mode == DEMO:
        st.badge(t("demo_badge"), icon=":material/science:", color="orange")

    conv = current_conversation()
    pending = st.session_state.pop("pending_prompt", None)  # from a suggestion, retry or the hero composer
    if not conv["messages"] and not pending:
        prompt = render_empty_state()
        if prompt and (check := check_question(prompt, get_settings().max_question_chars)).error:
            st.warning(question_error(check), icon=":material/edit_note:")  # stay on the start screen
        elif prompt:
            # Switch to the chat layout first, so the greeting doesn't stay above the streaming answer.
            st.session_state.pending_prompt = prompt
            st.rerun()
        return

    render_history(conv)
    # Called at the top level, st.chat_input is pinned to the bottom of the page.
    prompt = st.chat_input(t("placeholder"), key="composer", max_chars=get_settings().max_question_chars) or pending
    if prompt and (question := admit_question(prompt, mode)):
        handle_prompt(question, mode)


main()
