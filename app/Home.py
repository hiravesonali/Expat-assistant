"""Expat Germany Assistant: the chat page (Streamlit entrypoint, `streamlit run app/Home.py`).

How this page works (Streamlit's rerun model, for React developers)
--------------------------------------------------------------------
This file is not a component that mounts once. Streamlit executes it TOP TO BOTTOM on every
interaction: a chat message, a button click, a form submit. Think of the whole script as one big
render function whose "props" are `st.session_state` plus the widget values.

So the flow of one chat turn is:
1. The user submits a message -> rerun. `st.chat_input` returns the text in THIS run only.
2. We append it to the conversation in `st.session_state`, run the pipeline, and stream the answer.
3. We save the finished events in session_state and call `st.rerun()`. The next run redraws the full
   history from state (with citation chips, banners, and the updated sidebar conversation title).

Everything the user enters (profile, conversations) lives only in `st.session_state`, i.e. in server
memory for this browser tab. It is gone when the tab closes (ADR-0007/0009: nothing is persisted).
"""

import uuid
from typing import Any

import _bootstrap  # noqa: F401  (must be first: makes `expat` importable on Streamlit Cloud)
import streamlit as st
import ui
from pipeline_adapter import DEMO, LIVE, live_status, run_pipeline, sync_secrets_to_env

from expat.config import get_settings
from expat.schemas import (
    AnswerMetaEvent,
    ErrorEvent,
    PipelineEvent,
    StepEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserProfile,
)
from expat.schemas.profile import Citizenship, Employment, FamilyStatus, Housing, ResidenceStatus

# `set_page_config` must be the first Streamlit call of the run.
st.set_page_config(page_title="Expat Germany Assistant", page_icon="🇩🇪", layout="centered")
ui.inject_css()
sync_secrets_to_env()

PREFER = "Prefer not to say"

EXAMPLES = [
    (
        ":material/home: Tenant",
        "I rent a flat in Munich since 2021. If I give notice today, when does my tenancy end?",
    ),
    (
        ":material/badge: New arrival",
        "I just moved to Munich on a Blue Card. What do I need for the Anmeldung, and by when?",
    ),
    (
        ":material/family_restroom: Young family",
        "We're expecting a baby in March. How much Kindergeld and Elterngeld can we get?",
    ),
    (
        ":material/verified_user: Blue Card holder",
        "When can I apply for a settlement permit (Niederlassungserlaubnis) with my Blue Card?",
    ),
]

# Labels for the generated profile form. Keys are UserProfile field names; enum values map to labels.
PROFILE_UI: dict[str, tuple[str, dict[str, str]]] = {
    "citizenship": (
        "Citizenship",
        {Citizenship.EU: "EU / EEA / Swiss", Citizenship.NON_EU: "Non-EU", Citizenship.GERMAN: "German"},
    ),
    "residence_status": (
        "Residence status",
        {
            ResidenceStatus.BLUE_CARD: "EU Blue Card",
            ResidenceStatus.WORK_PERMIT: "Work permit",
            ResidenceStatus.STUDENT: "Student visa",
            ResidenceStatus.FAMILY_REUNION: "Family reunion",
            ResidenceStatus.SETTLEMENT: "Settlement permit",
            ResidenceStatus.EU_FREEDOM: "EU freedom of movement",
            ResidenceStatus.OTHER: "Other",
        },
    ),
    "employment": (
        "Employment",
        {
            Employment.EMPLOYEE: "Employee",
            Employment.FREELANCER: "Freelancer",
            Employment.SELF_EMPLOYED: "Self-employed",
            Employment.STUDENT: "Student",
            Employment.UNEMPLOYED: "Not working",
        },
    ),
    "family_status": (
        "Family status",
        {FamilyStatus.SINGLE: "Single", FamilyStatus.MARRIED: "Married", FamilyStatus.PARTNERSHIP: "Partnership"},
    ),
    "housing": (
        "Housing",
        {Housing.RENTING: "Renting", Housing.OWNING: "Owning", Housing.LOOKING: "Looking for a flat"},
    ),
}


# ------------------------------------------------------------------------------------------------
# Session state ("the store"). `setdefault` only runs the first time in a browser session.
# ------------------------------------------------------------------------------------------------


def _new_conversation() -> str:
    conv_id = uuid.uuid4().hex[:8]
    st.session_state.conversations[conv_id] = {"title": "New conversation", "messages": []}
    st.session_state.current = conv_id
    return conv_id


def init_state() -> None:
    st.session_state.setdefault("profile", UserProfile())
    st.session_state.setdefault("profile_saved", False)
    st.session_state.setdefault("conversations", {})
    st.session_state.setdefault("seen_intro", False)
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
# Sidebar
# ------------------------------------------------------------------------------------------------


def _select_profile_field(name: str, current: Any) -> Any:
    """One selectbox per enum field, generated from the UserProfile model (UNKNOWN = prefer not to say)."""
    label, labels = PROFILE_UI.get(name, (name.replace("_", " ").capitalize(), {}))
    enum_cls = type(current)
    options = [v for v in enum_cls if v.value != "unknown"] + [enum_cls("unknown")]
    return st.selectbox(
        label,
        options,
        index=options.index(current),
        format_func=lambda v: PREFER if v.value == "unknown" else labels.get(v, v.value.replace("_", " ").title()),
        key=f"pf_{name}",
    )


def render_profile_form() -> None:
    profile: UserProfile = st.session_state.profile
    with st.expander(":material/person: Your situation", expanded=not st.session_state.profile_saved):
        st.caption("Optional. Helps me pick the rules that apply to you. Stored only in this browser session.")
        # A form batches its widgets: changing a selectbox does NOT rerun the script, only the submit does.
        with st.form("profile_form", border=False):
            st.selectbox("City", ["Munich (Bavaria)"], disabled=True, help="The MVP covers Munich only.")
            values: dict[str, Any] = {}
            for name in UserProfile.model_fields:
                if name in ("city", "state"):
                    continue
                if name == "children_count":
                    kids = st.selectbox(
                        "Children",
                        [None, *range(0, 11)],
                        index=0 if not st.session_state.profile_saved else profile.children_count + 1,
                        format_func=lambda v: PREFER if v is None else str(v),
                        key="pf_children_count",
                    )
                    values[name] = kids or 0
                elif name == "youngest_child_age":
                    ages = [None, *range(0, 26)]
                    values[name] = st.selectbox(
                        "Youngest child's age",
                        ages,
                        index=ages.index(profile.youngest_child_age),
                        format_func=lambda v: PREFER if v is None else f"{v} years",
                        help="Only used when you have children (Kindergeld, Elterngeld, Kita).",
                        key="pf_youngest_child_age",
                    )
                elif name == "answer_language":
                    langs = ["en", "de"]
                    values[name] = st.selectbox(
                        "Answer language",
                        langs,
                        index=langs.index(profile.answer_language),
                        format_func={"en": "English", "de": "Deutsch"}.get,
                        key="pf_answer_language",
                    )
                else:
                    values[name] = _select_profile_field(name, getattr(profile, name))  # enum fields
            if st.form_submit_button("Save profile", type="primary", width="stretch"):
                if not values["children_count"]:
                    values["youngest_child_age"] = None
                st.session_state.profile = UserProfile(**values)
                st.session_state.profile_saved = True
                st.toast("Profile saved for this session", icon=":material/check:")
    if st.session_state.profile_saved:
        st.caption(f":material/badge: {st.session_state.profile.summary()}")


def render_conversation_list() -> None:
    st.button(
        "New conversation",
        icon=":material/add_comment:",
        width="stretch",
        on_click=_on_new_conversation,
    )
    convs = st.session_state.conversations
    started = [(cid, c) for cid, c in reversed(convs.items()) if c["messages"]]
    if started:
        st.caption("Conversations (this session)")
    for cid, conv in started:
        st.button(
            conv["title"],
            key=f"conv-{cid}",
            icon=":material/chat_bubble:",
            type="primary" if cid == st.session_state.current else "tertiary",
            width="stretch",
            on_click=_on_select_conversation,
            args=(cid,),
        )


def render_mode_toggle() -> str:
    available, reason = live_status()
    live = st.toggle(
        "Live mode",
        value=available,
        disabled=not available,
        key="live_toggle",
        help="Live calls the real RAG pipeline via OpenRouter. Demo replays scripted answers offline."
        + ("" if available else f"\n\n{reason}"),
    )
    mode = LIVE if (live and available) else DEMO
    if mode == DEMO:
        st.caption(":material/science: **Demo mode**: scripted answers, no API calls.")
    return mode


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("### :material/travel_explore: Expat Germany Assistant")
        render_conversation_list()
        st.divider()
        render_profile_form()
        st.divider()
        mode = render_mode_toggle()
        st.divider()
        st.caption(f":material/gavel: {ui.DISCLAIMER}")
    return mode


# ------------------------------------------------------------------------------------------------
# Main area
# ------------------------------------------------------------------------------------------------


@st.dialog("Welcome to the Expat Germany Assistant")
def first_run_notice() -> None:
    st.markdown(
        "I answer questions about **registration (Anmeldung), residence permits, renting and family "
        "benefits in Munich**, using official German sources only.\n\n"
        "- Every statement cites its source; click a chip to see the original text.\n"
        "- **General information, not legal or tax advice.** For your specific case, ask a Mieterverein, "
        "a migration counselling service (MBE) or a lawyer.\n"
        "- Your profile and chats live only in this browser session. Nothing is stored."
    )
    if st.button("Got it", type="primary", width="stretch"):
        st.rerun()  # closes the dialog


def render_empty_state() -> None:
    st.markdown("## How can I help you settle in? :material/waving_hand:")
    st.caption("Ask in English or German. Pick an example to see how answers are grounded in official sources.")
    cols = st.columns(2)
    for i, (persona, prompt) in enumerate(EXAMPLES):
        with cols[i % 2]:
            st.button(
                f"**{persona}**\n\n{prompt}",
                key=f"example-{i}",
                width="stretch",
                on_click=_on_example,
                args=(prompt,),
            )


def render_history(conv: dict[str, Any]) -> None:
    messages = conv["messages"]
    for i, msg in enumerate(messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg["content"])
                continue
            ui.render_assistant_message(
                msg["events"], msg["content"], key_prefix=f"{st.session_state.current}-{i}", mode=msg["mode"]
            )
            is_last = i == len(messages) - 1
            error = next((e for e in msg["events"] if isinstance(e, ErrorEvent)), None)
            if is_last and error and error.retryable:
                st.button("Retry", icon=":material/refresh:", key=f"retry-{i}", on_click=_on_retry)


def _history_for_pipeline(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    turns = get_settings().history_turns
    return [{"role": m["role"], "content": m["content"]} for m in messages[-2 * turns :]] if turns else []


def handle_prompt(prompt: str, mode: str) -> None:
    conv = current_conversation()
    history = _history_for_pipeline(conv["messages"])
    conv["messages"].append({"role": "user", "content": prompt})
    if conv["title"] == "New conversation":
        conv["title"] = prompt if len(prompt) <= 42 else prompt[:40].rstrip() + "…"

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Containers are created up-front, then filled while the generator runs (like refs to DOM nodes).
        status = st.status("Understanding your question…", expanded=False)
        tool_area = st.container()
        events: list[PipelineEvent] = []
        tool_slots: dict[str, Any] = {}
        calls: dict[str, ToolCallEvent] = {}

        def token_stream():
            """Route events: tokens go to st.write_stream, everything else updates the other containers."""
            for ev in run_pipeline(mode, prompt, history, st.session_state.profile):
                events.append(ev)
                if isinstance(ev, TokenEvent):
                    yield ev.text
                elif isinstance(ev, StepEvent):
                    _, label = ui.STEP_LABELS.get(ev.name, ("", ev.name))
                    if ev.status == "started":
                        status.update(label=f"{label}…", state="running")
                    else:
                        with status:
                            ui.render_step(ev)
                elif isinstance(ev, ToolCallEvent):
                    calls[ev.call_id] = ev
                    tool_slots[ev.call_id] = tool_area.empty()
                    with tool_slots[ev.call_id].container():
                        ui.render_tool_card(ev, None)
                elif isinstance(ev, ToolResultEvent) and ev.call_id in calls:
                    with tool_slots[ev.call_id].container():
                        ui.render_tool_card(calls[ev.call_id], ev)

        # write_stream pulls from the generator and renders text as it arrives (typewriter effect).
        # The st.status box above already shows progress, so no extra spinner is needed.
        answer = st.write_stream(token_stream())

        parts = ui.split_events(events)
        status.update(
            label=ui.timeline_label(len(parts["steps"]), parts["done"]),
            state="error" if "error" in parts else "complete",
            expanded=False,
        )

    # Persist the post-checked text (invalid citations stripped) rather than the raw streamed tokens.
    final = next((ev.final_answer for ev in events if isinstance(ev, AnswerMetaEvent) and ev.final_answer), None)
    content = final if final is not None else (answer if isinstance(answer, str) else "")
    conv["messages"].append({"role": "assistant", "content": content, "events": events, "mode": mode})
    # Redraw everything from state: citation chips, banners, retry button, sidebar title.
    st.rerun()


def main() -> None:
    init_state()
    mode = render_sidebar()

    if not st.session_state.seen_intro:
        st.session_state.seen_intro = True
        first_run_notice()

    # `st.chat_input` is pinned to the bottom of the page wherever it is called.
    prompt = st.chat_input("Ask about Anmeldung, renting, Blue Card, Kindergeld…")
    prompt = prompt or st.session_state.pop("pending_prompt", None)

    conv = current_conversation()
    if not conv["messages"] and not prompt:
        render_empty_state()
    render_history(conv)
    if prompt:
        handle_prompt(prompt, mode)
    ui.disclaimer_footer()


main()
