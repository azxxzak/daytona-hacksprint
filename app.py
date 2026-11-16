"""AdLens — synthetic audience panel for ads. Streamlit UI (English / 日本語), behind a sign-in gate.

Flow: sign in -> setup page (audience + ad) -> run -> report page (saved per user, reopen any time)
"""
import io

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from core import auth, avatars, reports, ui  # noqa: E402
from core.gaze import chat_with_persona, persona_gaze  # noqa: E402
from core.i18n import t  # noqa: E402
from core.personas import load_csv, sample_personas, with_colors  # noqa: E402
from core.player import render_player  # noqa: E402
from core.sandbox import analyze  # noqa: E402

st.set_page_config(page_title="AdLens", page_icon="👁", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)
ss = st.session_state
ss.setdefault("page", "setup")
ss.setdefault("lang", st.query_params.get("lang", "en") if st.query_params.get("lang") in ("en", "ja") else "en")


def _set_lang():
    if ss.get("lang_switch"):
        ss.lang = ss.lang_switch
        st.query_params["lang"] = ss.lang
    else:  # clicking the selected option again clears it; keep the current language
        ss.lang_switch = ss.lang


def language_switch(where):
    ss.setdefault("lang_switch", ss.lang)
    where.segmented_control("Language", ["en", "ja"], label_visibility="collapsed", key="lang_switch",
                            format_func=lambda x: "English" if x == "en" else "日本語", on_change=_set_lang)


L = ss.lang

# ---------------- Sign-in gate ----------------
_, top_right = st.columns([5, 1])
language_switch(top_right)
user = auth.require_login(L)
if not user:
    st.stop()


def avatar_urls(ps):
    return {p["id"]: avatars.data_url(img) for p in ps if (img := avatars.cached(p))}


def go(page, rid=None):
    ss.page, ss.rid = page, rid
    st.rerun()


# ---------------- Sidebar: saved reports ----------------
with st.sidebar:
    st.header(t("reports", L))
    if st.button(t("new_test", L), use_container_width=True, type="primary"):
        go("setup")
    saved = reports.list_all(user)
    if not saved:
        st.caption(t("no_reports", L))
    for r in saved:
        label = f"{r['name'][:34]}\n{r['created']}, {t('viewers_n', L, n=r['viewers'])}"
        if st.button(label, key=f"open-{r['id']}", use_container_width=True,
                     type="primary" if ss.get("rid") == r["id"] and ss.page == "report" else "secondary"):
            go("report", r["id"])
    if auth.mode() != "open":
        st.divider()
        st.caption(t("signed_in_as", L, who=user))
        if st.button(t("sign_out", L)):
            auth.sign_out(L)


# ================= Page 1: setup =================
def page_setup():
    st.markdown(ui.masthead(L), unsafe_allow_html=True)
    left, right = st.columns([5, 4], gap="large")

    with left:
        st.subheader(t("step1", L))
        a, b = st.columns(2)
        age = a.slider(t("age", L), 15, 80, (20, 45))
        n = b.slider(t("count", L), 5, 60, 20, step=5)
        genders = st.segmented_control(t("gender", L), ["F", "M"], default=["F", "M"], selection_mode="multi",
                                       format_func=lambda g: t("female", L) if g == "F" else t("male", L))
        csv = st.file_uploader(t("csv", L), type="csv")

    with right:
        st.subheader(t("step2", L))
        up = st.file_uploader(t("media", L), type=["mp4", "mov", "webm", "png", "jpg", "jpeg"])
        context = st.text_input(t("context", L), placeholder=t("context_ph", L))
        start = st.button(t("start", L), type="primary", use_container_width=True, disabled=not (up and genders))

    if not genders:
        st.info(t("pick_gender", L))
        return
    df = load_csv(csv, age, genders).head(n) if csv else sample_personas(n, age, genders)
    personas = with_colors(df).to_dict("records")

    if avatars.available():
        tried = ss.setdefault("avatar_tried", set())
        missing = [p for p in personas if not avatars.cached(p) and avatars.key(p) not in tried]
        if missing:
            with st.spinner(t("drawing", L, n=len(missing))):
                avatars.generate_all(missing, st.caption)
            tried.update(avatars.key(p) for p in missing)

    if start:
        run(up, personas, context)

    st.subheader(t("panel", L, n=len(personas)))
    st.markdown(ui.roster(personas, avatar_urls(personas)), unsafe_allow_html=True)


def run(up, personas, context):
    media = up.getvalue()
    with st.status(t("watching", L), expanded=True) as status:
        log = st.write
        analysis, where = analyze(media, up.name, log)
        log(t("frames", L, n=len(analysis["frames"]), where=where))
        proxy = analysis.pop("proxy", None)
        if proxy:  # play the light 480p H.264 version in the browser
            media = proxy
        transcript = analysis.get("transcript", [])
        log(t("lines", L, n=len(transcript)))
        if not transcript and proxy:
            st.warning(t("no_speech", L))
        gaze = persona_gaze(analysis["keyframes"], personas, context, log, transcript)
        log(t("reactions", L, n=len(gaze), p=len(personas)))
        status.update(label=t("saving", L), state="running")
        rid = reports.save({"name": up.name, "mime": "video/mp4" if proxy else (up.type or "video/mp4"),
                            "context": context, "where": where, "analysis": analysis, "gaze": gaze,
                            "personas": personas, "chats": {}}, media, owner=user)
        status.update(label=t("finished", L), state="complete")
    go("report", rid)


# ================= Page 2: report =================
def page_report():
    if ss.get("rep", {}).get("id") != ss.rid:
        ss.rep = reports.load(ss.rid, user)
    res = ss.rep
    if not res:
        st.error(t("not_found", L))
        return
    ctx = f", {ui.escape(res['context'])}" if res.get("context") else ""
    st.markdown(f'<div class="mast"><div class="w">{ui.escape(res["name"][:60])}</div>'
                f'<div class="d">{t("tested", L, when=res["created"], n=len(res["personas"]))}{ctx}.</div></div>',
                unsafe_allow_html=True)

    g = pd.DataFrame(res["gaze"])
    if not g.empty:
        main, sub = ui.verdict(g, res["personas"], L)
        st.markdown(f'<div class="verdict">{main}</div><div class="verdict-sub">{sub}</div>', unsafe_allow_html=True)
    components.html(render_player(res["media"], res["mime"], res["analysis"], res["personas"], res["gaze"],
                                  avatars=avatar_urls(res["personas"]), lang=L), height=620, scrolling=False)

    t_res, t_view, t_chat = st.tabs([t("tab_results", L), t("tab_viewers", L), t("tab_interview", L)])
    with t_res:
        if g.empty:
            st.info(t("no_reactions", L))
        else:
            p = pd.DataFrame(res["personas"])[["id", "age", "gender"]]
            g = g.merge(p, on="id")
            g["age_group"] = pd.cut(g["age"], [0, 24, 34, 44, 54, 100], labels=["<25", "25-34", "35-44", "45-54", "55+"])
            c1, c2 = st.columns(2)
            with c1:
                st.subheader(t("interest_time", L))
                st.line_chart(g.pivot_table(index="t", columns="age_group", values="interest", observed=False))
            with c2:
                st.subheader(t("looked_at", L))
                st.bar_chart(g["looking_at"].str.lower().value_counts().head(10), horizontal=True)
            st.subheader(t("by_segment", L))
            st.dataframe(g.pivot_table(index="age_group", columns="gender", values="interest",
                                       aggfunc="mean", observed=False).round(2), use_container_width=True)
        if res["analysis"].get("transcript"):
            with st.expander(t("transcript", L)):
                for s in res["analysis"]["transcript"]:
                    st.write(f"`{s['start']:.0f}s` {s['text']}")
    with t_view:
        st.markdown(ui.roster(res["personas"], avatar_urls(res["personas"])), unsafe_allow_html=True)
    with t_chat:
        interview(res)


def interview(res):
    opts = {p["id"]: f"{p['name']} ({p['age']}, {p.get('occupation', '')})" for p in res["personas"]}
    pid = st.selectbox(t("talk_to", L), list(opts), format_func=opts.get)
    persona = next(p for p in res["personas"] if p["id"] == pid)
    face = avatars.cached(persona)
    st.markdown(ui.who(persona, avatars.data_url(face) if face else None, L), unsafe_allow_html=True)
    bot = Image.open(io.BytesIO(face)) if face else None
    history = res.setdefault("chats", {}).setdefault(pid, [])
    for m in history:
        st.chat_message(m["role"], avatar=bot if m["role"] == "assistant" else None).write(m["content"])
    q = st.chat_input(t("ask", L))
    if q:
        st.chat_message("user").write(q)
        kf = res["analysis"]["keyframes"][0] if res["analysis"]["keyframes"] else None
        mine = [x for x in res["gaze"] if x["id"] == pid]
        with st.spinner("…"):
            ans = chat_with_persona(persona, mine, list(history), q, kf, res["analysis"].get("transcript"))
        st.chat_message("assistant", avatar=bot).write(ans)
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": ans}]
        reports.update(res["id"], chats=res["chats"])  # interviews are saved with the report


if ss.page == "report" and ss.get("rid"):
    page_report()
else:
    page_setup()
