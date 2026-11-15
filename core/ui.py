"""Styling: a quiet research-notes page around one dark 'screening room' stage."""
from html import escape

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900&display=swap');
html, body, [class*="css"], .stMarkdown, p, label, button, input, textarea {
  font-family: 'Zen Kaku Gothic New', sans-serif !important; }
.block-container { padding-top: 2rem; max-width: 1280px; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { background: #E7E9E4; border-right: 1px solid #D6DAD5; }
section[data-testid="stSidebar"] h2 { font-size: 1.05rem; font-weight: 700; }

.mast { display: flex; align-items: baseline; gap: 18px; flex-wrap: wrap;
  padding-bottom: 14px; margin-bottom: 8px; border-bottom: 1px solid #D6DAD5; }
.mast .w { font-size: 2.6rem; font-weight: 900; letter-spacing: -0.035em; color: #1D2321; line-height: 1; }
.mast .d { color: #5E6763; font-size: .98rem; max-width: 62ch; line-height: 1.55; }

.verdict { font-size: 1.45rem; font-weight: 700; line-height: 1.45; max-width: 46ch; margin: 10px 0 4px; color: #1D2321; }
.verdict-sub { color: #5E6763; font-size: .92rem; margin-bottom: 16px; }

.roster { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 22px 16px; margin-top: 8px; }
.roster figure { margin: 0; }
.roster img, .roster .ph { width: 100%; aspect-ratio: 1/1; object-fit: cover; border-radius: 6px; display: block; }
.roster .ph { display: flex; align-items: center; justify-content: center; font-size: 2rem; font-weight: 900; color: #F3F4F1; }
.roster figcaption { margin-top: 7px; font-size: .86rem; line-height: 1.4; border-left: 3px solid var(--c); padding-left: 7px; }
.roster figcaption b { font-weight: 700; } .roster figcaption span { color: #5E6763; display: block; }

.who { display: flex; gap: 18px; align-items: center; margin: 6px 0 14px; }
.who img { width: 96px; height: 96px; border-radius: 50%; object-fit: cover; box-shadow: 0 0 0 3px var(--c); }
.who .n { font-size: 1.35rem; font-weight: 900; } .who .m { color: #5E6763; font-size: .9rem; line-height: 1.55; }
div[data-testid="stTabs"] button p { font-size: 1rem; font-weight: 700; }
</style>
"""


def masthead() -> str:
    return ('<div class="mast"><div class="w">AdLens</div><div class="d">'
            'Show your ad to a panel of AI viewers before it goes live. See where each person looks, '
            'what they think at every moment, and ask them why. '
            '<br>配信前に、AIの視聴者パネルで広告をテストします。</div></div>')


def verdict(g, personas) -> tuple[str, str]:
    per = g.groupby("id")["interest"].mean()
    curve = g.groupby("t")["interest"].mean()
    top = g["looking_at"].str.lower().value_counts()
    engaged = int((per >= 3.5).sum())
    low_t = curve.idxmin() if len(curve) > 1 else None
    main = f"{engaged} of {len(per)} viewers stayed interested."
    if low_t is not None:
        main += f" Attention dipped lowest at {int(low_t // 60)}:{int(low_t % 60):02d}."
    sub = f"Most looked at: {top.index[0]}. Average interest {g['interest'].mean():.1f} out of 5." if len(top) else ""
    return main, sub


def roster(personas, img_urls) -> str:
    out = []
    for p in personas:
        c = p.get("color", "#888")
        img = (f'<img src="{img_urls[p["id"]]}" alt="">' if p["id"] in img_urls
               else f'<div class="ph" style="background:{c}">{escape(str(p["name"])[:1])}</div>')
        out.append(f'<figure style="--c:{c}">{img}<figcaption><b>{escape(str(p["name"]))}, {escape(str(p["age"]))}</b>'
                   f'<span>{escape(str(p.get("occupation", "")))}, {escape(str(p.get("region", "")))}</span>'
                   f'<span>{escape(str(p.get("interests", "")))}</span></figcaption></figure>')
    return f'<div class="roster">{"".join(out)}</div>'


def who(p, img_url) -> str:
    img = f'<img src="{img_url}" alt="">' if img_url else ""
    return (f'<div class="who" style="--c:{p.get("color", "#888")}">{img}<div>'
            f'<div class="n">{escape(str(p["name"]))}, {escape(str(p["age"]))}</div>'
            f'<div class="m">{escape(str(p.get("occupation", "")))} in {escape(str(p.get("region", "")))}, '
            f'income {escape(str(p.get("income", "")))}<br>Into {escape(str(p.get("interests", "")))}. '
            f'Uses {escape(str(p.get("media", "")))}. {escape(str(p.get("values", "")).capitalize())}.</div></div></div>')
