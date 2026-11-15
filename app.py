"""AdLens — synthetic audience panel for ads. Streamlit UI (English / 日本語)."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()

from core.gaze import chat_with_persona, persona_gaze  # noqa: E402
from core.personas import load_csv, sample_personas, with_colors  # noqa: E402
from core.player import render_player  # noqa: E402
from core.sandbox import analyze  # noqa: E402

st.set_page_config(page_title="AdLens", page_icon="👁", layout="wide")
st.title("👁 AdLens — AI audience panel for ads")
st.caption("Upload a video or banner → Daytona sandbox computes attention heatmaps → "
           "hundreds of personas watch it and react in real time. / 広告をAIペルソナパネルで事前検証")

# ---------------- Audience builder ----------------
with st.sidebar:
    st.header("🎯 Audience / ターゲット")
    csv = st.file_uploader("People data CSV (optional) / ペルソナデータ", type="csv")
    age = st.slider("Age range / 年齢", 15, 80, (20, 45))
    genders = st.multiselect("Gender / 性別", ["F", "M"], default=["F", "M"],
                             format_func=lambda g: "Female / 女性" if g == "F" else "Male / 男性")
    n = st.slider("Panel size / 人数", 5, 60, 20, step=5)
    context = st.text_input("Ad context (optional) / 広告の説明", placeholder="e.g. New energy drink, launch campaign")
    if not genders:
        st.stop()
    if csv:
        df = load_csv(csv, age, genders).head(n)
    else:
        df = sample_personas(n, age, genders)
    df = with_colors(df)
    st.session_state.personas = df

personas = st.session_state.personas.to_dict("records")

tab_run, tab_panel, tab_chat = st.tabs(["▶️ Test ad / 広告テスト", "👥 Panel / パネル", "💬 Interview / インタビュー"])

with tab_panel:
    st.write(f"{len(personas)} personas")
    st.dataframe(st.session_state.personas.drop(columns=["color"]), use_container_width=True, hide_index=True)

# ---------------- Run analysis ----------------
with tab_run:
    up = st.file_uploader("Video or banner / 動画・バナー", type=["mp4", "mov", "webm", "png", "jpg", "jpeg"])
    if up and st.button("🚀 Run panel / 分析開始", type="primary"):
        media = up.getvalue()
        with st.status("Running… / 実行中", expanded=True) as status:
            log = st.write
            analysis, where = analyze(media, up.name, log)
            log(f"✅ {len(analysis['frames'])} frames analysed ({where})")
            proxy = analysis.pop("proxy", None)
            if proxy:  # play the light 480p H.264 version in the browser
                media = proxy
            transcript = analysis.get("transcript", [])
            log(f"🗣 {len(transcript)} speech segments transcribed")
            gaze = persona_gaze(analysis["keyframes"], personas, context, log, transcript)
            log(f"✅ {len(gaze)} gaze points from {len(personas)} personas")
            status.update(label="Done / 完了", state="complete", expanded=False)
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
        st.caption(f"Heatmaps computed in: **{res['where']}** sandbox · {res['name']}")
        components.html(render_player(res["media"], res["mime"], res["analysis"], res["personas"], res["gaze"]),
                        height=620, scrolling=False)

        g = pd.DataFrame(res["gaze"])
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
                st.subheader("What people looked at / 注目ポイント")
                st.bar_chart(g["looking_at"].str.lower().value_counts().head(10))
            st.subheader("Interest by segment / セグメント別")
            st.dataframe(g.pivot_table(index="age_group", columns="gender", values="interest",
                                       aggfunc="mean", observed=False).round(2), use_container_width=True)

# ---------------- Persona chat ----------------
with tab_chat:
    res = st.session_state.get("result")
    if not res:
        st.info("Run a test first. / 先に広告テストを実行してください。")
    else:
        opts = {p["id"]: f"{p['name']} ({p['age']}, {p['gender']}, {p.get('occupation', '')})" for p in res["personas"]}
        pid = st.selectbox("Persona", list(opts), format_func=opts.get)
        persona = next(p for p in res["personas"] if p["id"] == pid)
        mine = [x for x in res["gaze"] if x["id"] == pid]
        if res["analysis"].get("transcript"):
            with st.expander("🗣 Transcript / 書き起こし"):
                for s in res["analysis"]["transcript"]:
                    st.write(f"`{s['start']:.0f}s` {s['text']}")
        chats = st.session_state.setdefault("chats", {})
        history = chats.setdefault(pid, [])
        for m in history:
            text = m["content"] if isinstance(m["content"], str) else m["content"][-1]["text"]
            st.chat_message(m["role"]).write(text)
        q = st.chat_input("Ask this persona… / 質問してください")
        if q:
            st.chat_message("user").write(q)
            kf = res["analysis"]["keyframes"][0] if res["analysis"]["keyframes"] else None
            ans = chat_with_persona(persona, mine, history, q, kf, res["analysis"].get("transcript"))
            st.chat_message("assistant").write(ans)
            history += [{"role": "user", "content": q}, {"role": "assistant", "content": ans}]
