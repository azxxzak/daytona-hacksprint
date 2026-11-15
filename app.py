"""AdLens — synthetic audience panel for ads. Streamlit UI (English / 日本語)."""
import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from core import avatars, ui  # noqa: E402
from core.gaze import chat_with_persona, persona_gaze  # noqa: E402
from core.personas import load_csv, sample_personas, with_colors  # noqa: E402
from core.player import render_player  # noqa: E402
from core.sandbox import analyze  # noqa: E402

st.set_page_config(page_title="AdLens", page_icon="👁", layout="wide")
st.markdown(ui.CSS, unsafe_allow_html=True)
st.markdown(ui.masthead(), unsafe_allow_html=True)

# ---------------- Audience builder ----------------
with st.sidebar:
    st.header("Who is watching / 視聴者")
    csv = st.file_uploader("Your own people data, CSV (optional) / 顧客データ", type="csv")
    age = st.slider("Age range / 年齢", 15, 80, (20, 45))
    genders = st.multiselect("Gender / 性別", ["F", "M"], default=["F", "M"],
                             format_func=lambda g: "Female / 女性" if g == "F" else "Male / 男性")
    n = st.slider("Number of viewers / 人数", 5, 60, 20, step=5)
    context = st.text_input("What is the ad for? (optional) / 広告の内容", placeholder="e.g. New energy drink, launch campaign")
    if not genders:
        st.stop()
    if csv:
        df = load_csv(csv, age, genders).head(n)
    else:
        df = sample_personas(n, age, genders)
    df = with_colors(df)
    st.session_state.personas = df

personas = st.session_state.personas.to_dict("records")

# Portraits are generated automatically for any persona that doesn't have one yet (cached on disk).
if avatars.available():
    tried = st.session_state.setdefault("avatar_tried", set())
    missing = [p for p in personas if not avatars.cached(p) and avatars.key(p) not in tried]
    if missing:
        with st.spinner(f"Drawing portraits for {len(missing)} viewers / 顔写真を作成中"):
            avatars.generate_all(missing, st.sidebar.caption)
        tried.update(avatars.key(p) for p in missing)


tab_run, tab_panel, tab_chat = st.tabs(["Test an ad / 広告テスト", "Viewers / 視聴者", "Interview / インタビュー"])

def avatar_map(ps):
    return {p["id"]: img for p in ps if (img := avatars.cached(p))}


def avatar_urls(ps):
    return {k: avatars.data_url(v) for k, v in avatar_map(ps).items()}


with tab_panel:
    if not avatars.available():
        st.caption("Add OPENAI_API_KEY to .env to generate persona portraits.")
    st.markdown(ui.roster(personas, avatar_urls(personas)), unsafe_allow_html=True)
    with st.expander("See the data / データを見る"):
        st.dataframe(st.session_state.personas.drop(columns=["color"]), use_container_width=True, hide_index=True)

# ---------------- Run analysis ----------------
with tab_run:
    up = st.file_uploader("Upload a video or banner / 動画・バナーをアップロード", type=["mp4", "mov", "webm", "png", "jpg", "jpeg"])
    if up and st.button("Show it to the viewers / 視聴開始", type="primary"):
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
            gaze = persona_gaze(analysis["keyframes"], personas, context, log, transcript)
            log(f"{len(gaze)} reactions from {len(personas)} viewers")
            status.update(label="Finished watching / 視聴完了", state="complete", expanded=False)
        mime = "video/mp4" if proxy else (up.type or "video/mp4")
        st.session_state.result = {"media": media, "mime": mime, "name": up.name,
                                   "analysis": analysis, "gaze": gaze, "where": where,
                                   "personas": personas}
        st.session_state.chats = {}
        Path("cache").mkdir(exist_ok=True)
        Path("cache/last_run.json").write_text(json.dumps(
            {k: v for k, v in st.session_state.result.items() if k != "media"}, ensure_ascii=False, default=str))

    res = st.session_state.get("result")
    if res:
        g = pd.DataFrame(res["gaze"])
        if not g.empty:
            main, sub = ui.verdict(g, res["personas"])
            st.markdown(f'<div class="verdict">{main}</div><div class="verdict-sub">{sub}</div>',
                        unsafe_allow_html=True)
        components.html(render_player(res["media"], res["mime"], res["analysis"], res["personas"], res["gaze"],
                                      avatars=avatar_urls(res["personas"])),
                        height=620, scrolling=False)

        if not g.empty:
            p = pd.DataFrame(res["personas"])[["id", "age", "gender"]]
            g = g.merge(p, on="id")
            g["age_group"] = pd.cut(g["age"], [0, 24, 34, 44, 54, 100],
                                    labels=["<25", "25-34", "35-44", "45-54", "55+"])
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Interest over time / 興味の推移")
                st.line_chart(g.pivot_table(index="t", columns="age_group", values="interest", observed=False))
            with c2:
                st.subheader("What they looked at / 注目したもの")
                st.bar_chart(g["looking_at"].str.lower().value_counts().head(10))
            st.subheader("Interest by age and gender / 属性別の興味")
            st.dataframe(g.pivot_table(index="age_group", columns="gender", values="interest",
                                       aggfunc="mean", observed=False).round(2), use_container_width=True)

# ---------------- Persona chat ----------------
with tab_chat:
    res = st.session_state.get("result")
    if not res:
        st.info("Test an ad first, then come back to ask the viewers about it. / 先に広告をテストしてください。")
    else:
        opts = {p["id"]: f"{p['name']} ({p['age']}, {p['gender']}, {p.get('occupation', '')})" for p in res["personas"]}
        pid = st.selectbox("Talk to / 話す相手", list(opts), format_func=opts.get)
        persona = next(p for p in res["personas"] if p["id"] == pid)
        mine = [x for x in res["gaze"] if x["id"] == pid]
        if res["analysis"].get("transcript"):
            with st.expander("What was said in the ad / 書き起こし"):
                for s in res["analysis"]["transcript"]:
                    st.write(f"`{s['start']:.0f}s` {s['text']}")
        chats = st.session_state.setdefault("chats", {})
        history = chats.setdefault(pid, [])
        face = avatars.cached(persona)
        st.markdown(ui.who(persona, avatars.data_url(face) if face else None), unsafe_allow_html=True)
        bot = Image.open(io.BytesIO(face)) if face else None
        for m in history:
            text = m["content"] if isinstance(m["content"], str) else m["content"][-1]["text"]
            st.chat_message(m["role"], avatar=bot if m["role"] == "assistant" else None).write(text)
        q = st.chat_input("Ask about the ad / 広告について質問する")
        if q:
            st.chat_message("user").write(q)
            kf = res["analysis"]["keyframes"][0] if res["analysis"]["keyframes"] else None
            ans = chat_with_persona(persona, mine, history, q, kf, res["analysis"].get("transcript"))
            st.chat_message("assistant", avatar=bot).write(ans)
            history += [{"role": "user", "content": q}, {"role": "assistant", "content": ans}]
