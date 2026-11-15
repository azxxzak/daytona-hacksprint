"""AdLens — synthetic audience panel for ads. Streamlit UI (English / 日本語).

Flow: setup page (audience + ad)  ->  run  ->  report page (saved to reports/, reopen any time)
"""
import io

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from core import avatars, reports, ui  # noqa: E402
from core.gaze import chat_with_persona, persona_gaze  # noqa: E402
from core.personas import load_csv, sample_personas, with_colors  # noqa: E402
from core.player import render_player  # noqa: E402
from core.sandbox import analyze  # noqa: E402

st.set_page_config(page_title="AdLens", page_icon="👁", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)
ss = st.session_state
ss.setdefault("page", "setup")


def avatar_urls(ps):
    return {p["id"]: avatars.data_url(img) for p in ps if (img := avatars.cached(p))}


def go(page, rid=None):
    ss.page, ss.rid = page, rid
    st.rerun()


# ---------------- Sidebar: saved reports ----------------
with st.sidebar:
    st.header("Reports / レポート")
    if st.button("New test / 新しいテスト", use_container_width=True, type="primary"):
        go("setup")
    saved = reports.list_all()
    if not saved:
        st.caption("Finished tests are saved here. / テスト結果はここに保存されます。")
    for r in saved:
        label = f"{r['name'][:34]}\n{r['created']}, {r['viewers']} viewers"
        if st.button(label, key=f"open-{r['id']}", use_container_width=True,
                     type="secondary" if ss.get("rid") != r["id"] else "primary"):
            go("report", r["id"])


# ================= Page 1: setup =================
def page_setup():
    st.markdown(ui.masthead(), unsafe_allow_html=True)
    left, right = st.columns([5, 4], gap="large")

    with left:
        st.subheader("1. Who is watching? / 視聴者")
        a, b = st.columns(2)
        age = a.slider("Age range / 年齢", 15, 80, (20, 45))
        n = b.slider("Number of viewers / 人数", 5, 60, 20, step=5)
        genders = st.segmented_control("Gender / 性別", ["F", "M"], default=["F", "M"], selection_mode="multi",
                                       format_func=lambda g: "Female / 女性" if g == "F" else "Male / 男性")
        csv = st.file_uploader("Use your own people data, CSV (optional) / 顧客データ（任意）", type="csv")

    with right:
        st.subheader("2. Which ad? / 広告")
        up = st.file_uploader("Video or banner / 動画・バナー", type=["mp4", "mov", "webm", "png", "jpg", "jpeg"])
        context = st.text_input("What is the ad for? (optional) / 広告の内容（任意）",
                                placeholder="e.g. Hybrid family car, long-term owner review")
        start = st.button("Show it to the viewers / 視聴開始", type="primary", use_container_width=True,
                          disabled=not (up and genders))

    if not genders:
        st.info("Pick at least one gender. / 性別を選んでください。")
        return
    df = load_csv(csv, age, genders).head(n) if csv else sample_personas(n, age, genders)
    personas = with_colors(df).to_dict("records")

    if avatars.available():
        tried = ss.setdefault("avatar_tried", set())
        missing = [p for p in personas if not avatars.cached(p) and avatars.key(p) not in tried]
        if missing:
            with st.spinner(f"Drawing portraits for {len(missing)} viewers / 顔写真を作成中"):
                avatars.generate_all(missing, st.caption)
            tried.update(avatars.key(p) for p in missing)

    if start:
        run(up, personas, context)

    st.subheader(f"Your panel: {len(personas)} viewers / パネル")
    st.markdown(ui.roster(personas, avatar_urls(personas)), unsafe_allow_html=True)


def run(up, personas, context):
    media = up.getvalue()
    with st.status("Viewers are watching / 視聴中", expanded=True) as status:
        log = st.write
        analysis, where = analyze(media, up.name, log)
        log(f"{len(analysis['frames'])} frames analysed ({where})")
        proxy = analysis.pop("proxy", None)
        if proxy:  # play the light 480p H.264 version in the browser
            media = proxy
        transcript = analysis.get("transcript", [])
        log(f"{len(transcript)} spoken lines transcribed")
        if not transcript and proxy:
            st.warning("No speech was transcribed, so viewers will judge the visuals only. / 音声を書き起こせませんでした。")
        gaze = persona_gaze(analysis["keyframes"], personas, context, log, transcript)
        log(f"{len(gaze)} reactions from {len(personas)} viewers")
        status.update(label="Saving report / レポート保存中", state="running")
        rid = reports.save({"name": up.name, "mime": "video/mp4" if proxy else (up.type or "video/mp4"),
                            "context": context, "where": where, "analysis": analysis, "gaze": gaze,
                            "personas": personas, "chats": {}}, media)
        status.update(label="Finished watching / 視聴完了", state="complete")
    go("report", rid)


# ================= Page 2: report =================
def page_report():
    if ss.get("rep", {}).get("id") != ss.rid:
        ss.rep = reports.load(ss.rid)
    res = ss.rep
    st.markdown(f'<div class="mast"><div class="w">{ui.escape(res["name"][:60])}</div>'
                f'<div class="d">Tested {res["created"]} with {len(res["personas"])} viewers'
                f'{", " + ui.escape(res["context"]) if res.get("context") else ""}.</div></div>',
                unsafe_allow_html=True)

    g = pd.DataFrame(res["gaze"])
    if not g.empty:
        main, sub = ui.verdict(g, res["personas"])
        st.markdown(f'<div class="verdict">{main}</div><div class="verdict-sub">{sub}</div>', unsafe_allow_html=True)
    components.html(render_player(res["media"], res["mime"], res["analysis"], res["personas"], res["gaze"],
                                  avatars=avatar_urls(res["personas"])), height=620, scrolling=False)

    t_res, t_view, t_chat = st.tabs(["Results / 結果", "Viewers / 視聴者", "Interview / インタビュー"])
    with t_res:
        if g.empty:
            st.info("No reactions were recorded. / 反応がありません。")
        else:
            p = pd.DataFrame(res["personas"])[["id", "age", "gender"]]
            g = g.merge(p, on="id")
            g["age_group"] = pd.cut(g["age"], [0, 24, 34, 44, 54, 100], labels=["<25", "25-34", "35-44", "45-54", "55+"])
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Interest over time / 興味の推移")
                st.line_chart(g.pivot_table(index="t", columns="age_group", values="interest", observed=False))
            with c2:
                st.subheader("What they looked at / 注目したもの")
                st.bar_chart(g["looking_at"].str.lower().value_counts().head(10), horizontal=True)
            st.subheader("Interest by age and gender / 属性別の興味")
            st.dataframe(g.pivot_table(index="age_group", columns="gender", values="interest",
                                       aggfunc="mean", observed=False).round(2), use_container_width=True)
        if res["analysis"].get("transcript"):
            with st.expander("What was said in the ad / 書き起こし"):
                for s in res["analysis"]["transcript"]:
                    st.write(f"`{s['start']:.0f}s` {s['text']}")
    with t_view:
        st.markdown(ui.roster(res["personas"], avatar_urls(res["personas"])), unsafe_allow_html=True)
    with t_chat:
        interview(res)


def interview(res):
    opts = {p["id"]: f"{p['name']} ({p['age']}, {p.get('occupation', '')})" for p in res["personas"]}
    pid = st.selectbox("Talk to / 話す相手", list(opts), format_func=opts.get)
    persona = next(p for p in res["personas"] if p["id"] == pid)
    face = avatars.cached(persona)
    st.markdown(ui.who(persona, avatars.data_url(face) if face else None), unsafe_allow_html=True)
    bot = Image.open(io.BytesIO(face)) if face else None
    history = res.setdefault("chats", {}).setdefault(pid, [])
    for m in history:
        st.chat_message(m["role"], avatar=bot if m["role"] == "assistant" else None).write(m["content"])
    q = st.chat_input("Ask about the ad / 広告について質問する")
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
