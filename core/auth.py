"""Sign-in gate.

Two modes, picked automatically:
  1. Google (OIDC) via st.login, when .streamlit/secrets.toml has an [auth] section.
     Only emails in ALLOWED_EMAILS or domains in ALLOWED_DOMAINS may enter (deny by default).
  2. Shared password, when APP_PASSWORD is set in the environment.
If neither is configured the app runs open, for local development only.
"""
import hmac
import os

import streamlit as st

from core.i18n import t

MAX_ATTEMPTS = 5


def _csv_env(name):
    return {x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()}


def _oidc_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:  # noqa: BLE001 - no secrets.toml at all
        return False


def mode() -> str:
    if _oidc_configured():
        return "google"
    if os.getenv("APP_PASSWORD"):
        return "password"
    return "open"


def _allowed(email: str) -> bool:
    email = (email or "").lower()
    emails, domains = _csv_env("ALLOWED_EMAILS"), _csv_env("ALLOWED_DOMAINS")
    return email in emails or email.split("@")[-1] in domains


def require_login(lang: str) -> str | None:
    """Renders the sign-in screen when needed. Returns the user id, or None (caller should stop)."""
    m = mode()
    if m == "open":
        return "local"

    if m == "google":
        if not st.user.is_logged_in:
            _screen(lang)
            if st.button(t("login_google", lang), type="primary"):
                st.login()
            return None
        email = st.user.get("email", "")
        if not _allowed(email):
            st.error(t("not_allowed", lang, email=email))
            if st.button(t("sign_out", lang)):
                st.logout()
            return None
        return email.lower()

    # shared password
    ss = st.session_state
    if ss.get("authed"):
        return "team"
    _screen(lang)
    if ss.get("attempts", 0) >= MAX_ATTEMPTS:
        st.error(t("too_many", lang))
        return None
    with st.form("login"):
        pw = st.text_input(t("password", lang), type="password")
        ok = st.form_submit_button(t("login_btn", lang), type="primary")
    if ok:
        if hmac.compare_digest(pw.encode(), os.environ["APP_PASSWORD"].encode()):
            ss.authed = True
            st.rerun()
        ss.attempts = ss.get("attempts", 0) + 1
        st.error(t("bad_password", lang))
    return None


def sign_out(lang: str):
    if mode() == "google":
        st.logout()
    else:
        st.session_state.authed = False
        st.rerun()


def _screen(lang):
    st.markdown(f'<div class="mast"><div class="w">AdLens</div><div class="d">{t("tagline", lang)}</div></div>',
                unsafe_allow_html=True)
    st.subheader(t("login_title", lang))
