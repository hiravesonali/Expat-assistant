"""A deliberately simple password gate for the admin pages (ADR-0009).

- Deployed: set `ADMIN_PASSWORD` in the Streamlit secrets. Each admin page calls `require_admin()` first;
  without the password, the page stops rendering (`st.stop()` ends the current script run, like an
  early `return` from the render function).
- Locally (no secrets file / no ADMIN_PASSWORD): the pages are open.

This is a demo-grade gate (one shared password, session-scoped), not authentication.
"""

import hmac

import streamlit as st


def _admin_password() -> str | None:
    try:
        value = st.secrets.get("ADMIN_PASSWORD")
    except Exception:  # no secrets.toml at all
        return None
    return str(value) if value else None


def require_admin() -> None:
    expected = _admin_password()
    if expected is None or st.session_state.get("admin_ok"):
        return

    st.markdown("### :material/lock: Admin area")
    st.caption("The debugging pages are password-protected in the deployed app.")
    with st.form("admin_login"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Unlock", type="primary")
    if submitted:
        # compare_digest: constant-time comparison (no timing side channel).
        if hmac.compare_digest(password.encode(), expected.encode()):
            st.session_state.admin_ok = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()
