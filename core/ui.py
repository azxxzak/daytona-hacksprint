"""Styling helpers for the Streamlit UI."""
from html import escape

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=Noto+Sans+JP:wght@400;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText { font-family: 'Inter', 'Noto Sans JP', sans-serif; }
.block-container { padding-top: 1.6rem; max-width: 1400px; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { background: #0F1422; border-right: 1px solid #1E2638; }

.hero { padding: 26px 30px; border-radius: 18px; margin-bottom: 18px;
  background: radial-gradient(1200px 300px at 0% 0%, rgba(255,90,95,.28), transparent 60%),
              radial-gradient(900px 300px at 100% 100%, rgba(124,92,255,.28), transparent 60%), #121829;
  border: 1px solid #222B40; }
.hero .grad { letter-spacing: -0.02em;
  background: linear-gradient(90deg, #FF8A5B, #FF5A5F 40%, #A78BFA); -webkit-background-clip: text; color: transparent; }
.hero p { color: #A9B3C7; margin: 6px 0 12px; font-size: 1rem; }
.pill { display: inline-block; padding: 4px 11px; margin: 0 6px 4px 0; border-radius: 999px; font-size: .78rem;
  background: #1B2236; border: 1px solid #2A3550; color: #C9D2E3; }
.pill b { color: #FF8A5B; }

.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 6px 0 16px; }
.kpi { background: #141A2A; border: 1px solid #222B40; border-radius: 14px; padding: 14px 16px; }
.kpi .l { color: #8C97AD; font-size: .76rem; text-transform: uppercase; letter-spacing: .06em; }
.kpi .v { font-size: 1.6rem; font-weight: 800; margin-top: 2px; }
.kpi .s { color: #8C97AD; font-size: .78rem; }

.pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(165px, 1fr)); gap: 12px; }
.pcard { background: #141A2A; border: 1px solid #222B40; border-radius: 14px; overflow: hidden; }
.pcard img { width: 100%; aspect-ratio: 1/1; object-fit: cover; display: block; }
.pcard .ph { width: 100%; aspect-ratio: 1/1; display: flex; align-items: center; justify-content: center;
  font-size: 2.4rem; font-weight: 800; color: #0B0F19; }
.pcard .b { padding: 9px 11px 11px; border-top: 3px solid var(--c); }
.pcard .n { font-weight: 700; } .pcard .m { color: #8C97AD; font-size: .76rem; margin: 2px 0 6px; }
.pcard .t { display: inline-block; font-size: .68rem; padding: 2px 7px; margin: 0 4px 4px 0; border-radius: 999px;
  background: #1E2638; color: #C9D2E3; }

.profile { display: flex; gap: 16px; align-items: center; background: #141A2A; border: 1px solid #222B40;
  border-radius: 14px; padding: 14px; margin-bottom: 10px; }
.profile img { width: 92px; height: 92px; border-radius: 50%; object-fit: cover; border: 3px solid var(--c); }
.profile .n { font-size: 1.2rem; font-weight: 800; } .profile .m { color: #A9B3C7; font-size: .85rem; }
div[data-testid="stTabs"] button p { font-size: 1rem; font-weight: 600; }
</style>
"""


def hero(n_personas: int, age, genders) -> str:
    g = " + ".join("Female" if x == "F" else "Male" for x in genders)
    return f"""<div class="hero"><div style="font-size:2.3rem;font-weight:800;line-height:1.2">👁 <span class="grad">AdLens</span></div>
<p>AI audience panel for video & banner ads — see where people look, what they think, and ask them why.<br>
広告をAIペルソナパネルで事前検証。視線・本音・インタビューまで。</p>
<span class="pill">Panel <b>{n_personas}</b> personas</span>
<span class="pill">Age <b>{age[0]}–{age[1]}</b></span><span class="pill">{escape(g)}</span>
<span class="pill">⚡ Powered by <b>Daytona</b> sandboxes</span>
<span class="pill">🧠 Claude · 🎨 GPT Image · 🗣 Whisper</span></div>"""


def kpis(items) -> str:
    cells = "".join(f'<div class="kpi"><div class="l">{escape(l)}</div><div class="v">{escape(str(v))}</div>'
                    f'<div class="s">{escape(s)}</div></div>' for l, v, s in items)
    return f'<div class="kpis">{cells}</div>'


def persona_cards(personas, img_urls) -> str:
    cards = []
    for p in personas:
        c = p.get("color", "#888")
        img = (f'<img src="{img_urls[p["id"]]}">' if p["id"] in img_urls
               else f'<div class="ph" style="background:{c}">{escape(str(p["name"])[:1])}</div>')
        tags = "".join(f'<span class="t">{escape(t.strip())}</span>' for t in str(p.get("interests", "")).split(",")[:3])
        cards.append(f'<div class="pcard" style="--c:{c}">{img}<div class="b">'
                     f'<div class="n">{escape(str(p["name"]))}, {escape(str(p["age"]))}</div>'
                     f'<div class="m">{escape(str(p.get("occupation", "")))} · {escape(str(p.get("region", "")))}</div>'
                     f'{tags}</div></div>')
    return f'<div class="pgrid">{"".join(cards)}</div>'


def profile(p, img_url) -> str:
    c = p.get("color", "#888")
    img = f'<img src="{img_url}">' if img_url else ""
    return (f'<div class="profile" style="--c:{c}">{img}<div><div class="n">{escape(str(p["name"]))}, '
            f'{escape(str(p["age"]))}</div><div class="m">{escape(str(p.get("gender", "")))} · '
            f'{escape(str(p.get("occupation", "")))} · {escape(str(p.get("region", "")))} · '
            f'{escape(str(p.get("income", "")))}</div><div class="m">❤️ {escape(str(p.get("interests", "")))}'
            f'</div><div class="m">📱 {escape(str(p.get("media", "")))} · 🧭 {escape(str(p.get("values", "")))}'
            f'</div></div></div>')
