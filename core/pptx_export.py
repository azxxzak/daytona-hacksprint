"""Editable 16:9 deck (native charts and tables) from a DecisionReport + the test result."""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from core import avatars
from core.decision_report import SEGMENTS, persona_means, segment_of

INK = RGBColor(0x11, 0x11, 0x11)
MUTED = RGBColor(0x6B, 0x6B, 0x6B)
ACCENT = RGBColor(0xC8, 0xF0, 0x31)
LINE = RGBColor(0xE4, 0xE4, 0xE4)
PANEL = RGBColor(0xF5, 0xF5, 0xF2)
SERIES = [RGBColor(0x11, 0x11, 0x11), RGBColor(0x2F, 0x6F, 0xED), RGBColor(0xE0, 0x6C, 0x2D),
          RGBColor(0x2E, 0x9E, 0x6B), RGBColor(0x8A, 0x5A, 0xD6)]
FONT = "Noto Sans JP"
FOOTER = "AI-generated panel — directional, not a substitute for real research"
W, H = Inches(13.333), Inches(7.5)
MX = Inches(0.6)

T = {
    "en": dict(sub="AI panel pre-screen", thesis="Thesis", curve="Interest over time", curve_sub="Panel mean interest (1-5) per keyframe",
               seg="Interest by segment", seg_sub="Average interest (1-5)", focus="What viewers looked at",
               focus_sub="Share of all viewer moments", themes="Themes in viewers' words", ev="Evidence", sw="So what", nw="Now what",
               verdicts="Where to play", seg_h="Segment", ver_h="Verdict", why_h="Why", tens="Tensions to resolve",
               strat="Strategy", acts="Actions", hz="When", act_h="Action", kpi_h="KPI", viewer_hi="Most interested", viewer_lo="Least interested",
               avg="avg interest", panel="Panel", win="Win", grow="Grow", dep="Deprioritize", all="Panel mean", thoughts="Said while watching"),
    "ja": dict(sub="AIパネル事前スクリーニング", thesis="結論", curve="関心度の推移", curve_sub="パネル平均関心度 (1-5) / キーフレーム別",
               seg="セグメント別の関心度", seg_sub="平均関心度 (1-5)", focus="視線の行き先",
               focus_sub="全視聴場面に占める割合", themes="自由回答のテーマ", ev="根拠", sw="だから何か", nw="次の一手",
               verdicts="どこで勝負するか", seg_h="セグメント", ver_h="判定", why_h="理由", tens="解消すべき葛藤",
               strat="打ち手", acts="アクション", hz="期限", act_h="アクション", kpi_h="KPI", viewer_hi="関心が最も高い視聴者", viewer_lo="関心が最も低い視聴者",
               avg="平均関心度", panel="パネル", win="攻める", grow="育てる", dep="後回し", all="パネル平均", thoughts="視聴中のひとこと"),
}
HZ = {"en": {"48h": "48 hours", "2w": "2 weeks", "6w": "6 weeks"}, "ja": {"48h": "48時間", "2w": "2週間", "6w": "6週間"}}


# ----------------------------------------------------------------------------- helpers

def _font(run_or_font, size, bold=False, color=INK):
    f = getattr(run_or_font, "font", run_or_font)
    f.size, f.bold, f.name = Pt(size), bold, FONT
    f.color.rgb = color
    rpr = f._element if hasattr(f, "_element") else None
    return f


def _set_ea(run):
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {})
            rpr.append(el)
        el.set("typeface", FONT)


def text(slide, x, y, w, h, s, size=14, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(str(s).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = para
        _font(r, size, bold, color)
        _set_ea(r)
    return tb


def rect(slide, x, y, w, h, fill=PANEL, line=None):
    from pptx.enum.shapes import MSO_SHAPE
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
    sh.shadow.inherit = False
    return sh


def new_slide(prs, title=None, sub=None, n=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    if title:
        rect(s, MX, Inches(0.55), Inches(0.12), Inches(0.5), ACCENT)
        text(s, MX + Inches(0.25), Inches(0.5), W - 2 * MX, Inches(0.6), title, 26, True, anchor=MSO_ANCHOR.MIDDLE)
        if sub:
            text(s, MX + Inches(0.25), Inches(1.1), W - 2 * MX, Inches(0.35), sub, 13, False, MUTED)
    rect(s, MX, H - Inches(0.62), W - 2 * MX, Emu(9525), LINE)
    text(s, MX, H - Inches(0.5), W - 2 * MX - Inches(1), Inches(0.3), FOOTER, 10, False, MUTED)
    if n:
        text(s, W - MX - Inches(0.8), H - Inches(0.5), Inches(0.8), Inches(0.3), str(n), 10, False, MUTED, PP_ALIGN.RIGHT)
    return s


def _style_chart(chart, legend=False, size=11):
    chart.font.size = Pt(size)
    chart.font.name = FONT
    chart.font.color.rgb = INK
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    chart.has_title = False


def _table(slide, x, y, w, rows, col_w, size=12, row_h=Inches(0.5)):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), x, y, w, row_h * len(rows))
    tbl = shape.table
    tblPr = tbl._tbl.tblPr
    for a in ("bandRow", "firstRow"):
        tblPr.set(a, "0")
    sid = tblPr.find(qn("a:tableStyleId"))
    if sid is not None:
        sid.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # "No Style, No Grid"
    tot = sum(col_w)
    for i, cw in enumerate(col_w):
        tbl.columns[i].width = int(w * cw / tot)
    for r, row in enumerate(rows):
        tbl.rows[r].height = row_h
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = INK if r == 0 else (PANEL if r % 2 == 0 else RGBColor(0xFF, 0xFF, 0xFF))
            cell.margin_left = cell.margin_right = Inches(0.1)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            run = p.add_run()
            run.text = str(val)
            _font(run, size, r == 0, RGBColor(0xFF, 0xFF, 0xFF) if r == 0 else INK)
            _set_ea(run)
    return tbl


def _clip(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


# ----------------------------------------------------------------------------- data

def _num(report, key, default=""):
    for n in report.get("numbers", []):
        if n["key"] == key:
            return n["value"]
    return default


def _curves(result):
    """panel mean per keyframe + per age band (computed from gaze)."""
    pmap = {p["id"]: p for p in result.get("personas", [])}
    by_t = defaultdict(lambda: defaultdict(list))
    for g in result.get("gaze", []):
        p = pmap.get(g["id"])
        if not p:
            continue
        by_t[g["t"]]["all"].append(g["interest"])
        for s in segment_of(p)[:1]:  # age band only
            by_t[g["t"]][s].append(g["interest"])
    ts = sorted(by_t)
    return ts, {k: [round(sum(by_t[t][k]) / len(by_t[t][k]), 2) if by_t[t][k] else None for t in ts]
                for k in ("all", "<25", "25-34", "35-44", "45+")}


def _mmss(t):
    t = int(round(t))
    return f"{t // 60}:{t % 60:02d}"


# ----------------------------------------------------------------------------- slides

def build_pptx(report: dict, result: dict, test_name: str) -> bytes:
    lang = report.get("lang", "en")
    L = T[lang]
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    n = 0

    def ns(title=None, sub=None):
        nonlocal n
        n += 1
        return new_slide(prs, title, sub, n if n > 1 else None)

    # 1 title
    s = ns()
    rect(s, MX, Inches(2.2), Inches(0.2), Inches(1.9), ACCENT)
    text(s, MX + Inches(0.5), Inches(2.1), Inches(11), Inches(1.5), _clip(test_name, 80), 40, True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, MX + Inches(0.5), Inches(3.7), Inches(11), Inches(0.5), L["sub"], 20, False, MUTED)
    text(s, MX + Inches(0.5), Inches(4.3), Inches(11), Inches(0.4), datetime.now().strftime("%Y-%m-%d"), 14, False, MUTED)
    if report.get("decision_question"):
        text(s, MX + Inches(0.5), Inches(5.3), Inches(11), Inches(0.9), _clip(report["decision_question"], 200), 14, False, INK)

    # 2 thesis + cards
    s = ns(L["thesis"])
    text(s, MX, Inches(1.35), W - 2 * MX, Inches(1.5), report["thesis"], 22, True)
    cards = report["headline_cards"][:4]
    cw, gap = Inches(2.85), Inches(0.2)
    for i, c in enumerate(cards):
        x = MX + i * (cw + gap)
        rect(s, x, Inches(3.2), cw, Inches(3.4), PANEL)
        rect(s, x, Inches(3.2), cw, Emu(38100), ACCENT if i == 0 else INK)
        text(s, x + Inches(0.2), Inches(3.4), cw - Inches(0.4), Inches(0.3), c["label"], 11, True, MUTED)
        text(s, x + Inches(0.2), Inches(3.8), cw - Inches(0.4), Inches(1.2), _clip(c["value"], 70), 17, True)
        text(s, x + Inches(0.2), Inches(5.1), cw - Inches(0.4), Inches(1.4), _clip(c["note"], 150), 13, False, MUTED)

    # 3 interest over time (native line chart)
    ts, curves = _curves(result)
    if ts:
        s = ns(L["curve"], L["curve_sub"])
        cd = CategoryChartData()
        cd.categories = [_mmss(t) for t in ts]
        cd.add_series(L["all"], curves["all"])
        for band in ("<25", "25-34", "35-44", "45+"):
            if any(v is not None for v in curves[band]):
                cd.add_series(band, curves[band])
        gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, MX, Inches(1.6), W - 2 * MX, Inches(5.1), cd)
        ch = gf.chart
        _style_chart(ch, legend=True)
        va = ch.value_axis
        va.minimum_scale, va.maximum_scale, va.major_unit = 1, 5, 1
        va.major_gridlines.format.line.color.rgb = LINE
        for i, ser in enumerate(ch.plots[0].series):
            ser.smooth = False
            ser.format.line.color.rgb = SERIES[i % len(SERIES)]
            ser.format.line.width = Pt(3.5 if i == 0 else 1.75)
            ser.marker.format.fill.solid()
            ser.marker.format.fill.fore_color.rgb = SERIES[i % len(SERIES)]
            ser.marker.format.line.color.rgb = SERIES[i % len(SERIES)]

    # 4 segment bars (native)
    means, personas = persona_means(result), result.get("personas", [])
    segrows = []
    for name, _ in SEGMENTS:
        m = [means[p["id"]] for p in personas if name in segment_of(p) and p["id"] in means]
        if m:
            segrows.append((f"{name} (n={len(m)})", round(sum(m) / len(m), 2)))
    if segrows:
        s = ns(L["seg"], L["seg_sub"])
        cd = CategoryChartData()
        cd.categories = [r[0] for r in segrows]
        cd.add_series(L["avg"], [r[1] for r in segrows])
        gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MX, Inches(1.6), W - 2 * MX, Inches(5.1), cd)
        ch = gf.chart
        _style_chart(ch)
        ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 1, 5
        ch.value_axis.major_gridlines.format.line.color.rgb = LINE
        pl = ch.plots[0]
        pl.gap_width = 70
        pl.has_data_labels = True
        pl.data_labels.number_format, pl.data_labels.number_format_is_linked = "0.0", False
        pl.data_labels.font.size = Pt(12)
        pl.series[0].format.fill.solid()
        pl.series[0].format.fill.fore_color.rgb = INK

    # 5 top focus (native)
    focus = [(n_["label"].split(": ", 1)[-1], float(n_["value"].rstrip("%"))) for n_ in report.get("numbers", [])
             if n_["key"].startswith("focus_")]
    if focus:
        s = ns(L["focus"], L["focus_sub"])
        cd = CategoryChartData()
        cd.categories = [_clip(f[0], 40) for f in reversed(focus)]
        cd.add_series("%", [f[1] / 100 for f in reversed(focus)])
        gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, MX, Inches(1.6), W - 2 * MX, Inches(5.1), cd)
        ch = gf.chart
        _style_chart(ch)
        ch.value_axis.has_major_gridlines = False
        ch.value_axis.tick_labels.number_format, ch.value_axis.tick_labels.number_format_is_linked = "0%", False
        pl = ch.plots[0]
        pl.gap_width = 60
        pl.has_data_labels = True
        pl.data_labels.number_format, pl.data_labels.number_format_is_linked = "0%", False
        pl.series[0].format.fill.solid()
        pl.series[0].format.fill.fore_color.rgb = INK

    # 6 themes
    themes = result.get("themes") or []
    if themes:
        s = ns(L["themes"])
        rows = [[("テーマ" if lang == "ja" else "Theme"), ("説明" if lang == "ja" else "Description"),
                 ("割合" if lang == "ja" else "Share")]]
        for t in themes[:7]:
            rows.append([_clip(t.get("title", ""), 40), _clip(t.get("description", ""), 150), f'{round(float(t.get("share", 0)) * 100)}%'])
        _table(s, MX, Inches(1.5), W - 2 * MX, rows, [3, 8, 1], 12, Inches(0.62))

    # insights
    for i, ins in enumerate(report["insights"], 1):
        s = ns(f"{i}. {_clip(ins['title'], 60)}")
        cw3 = (W - 2 * MX - Inches(0.4)) / 3
        for j, (lab, key) in enumerate(((L["ev"], "evidence"), (L["sw"], "so_what"), (L["nw"], "now_what"))):
            x = MX + j * (cw3 + Inches(0.2))
            rect(s, x, Inches(1.5), cw3, Inches(5.0), PANEL)
            rect(s, x, Inches(1.5), cw3, Emu(38100), ACCENT if j == 2 else INK)
            text(s, x + Inches(0.25), Inches(1.75), cw3 - Inches(0.5), Inches(0.3), lab, 12, True, MUTED)
            text(s, x + Inches(0.25), Inches(2.2), cw3 - Inches(0.5), Inches(4.1), _clip(ins[key], 420), 18)

    # verdict table
    s = ns(L["verdicts"])
    vl = {"win": L["win"], "grow": L["grow"], "deprioritize": L["dep"]}
    order = {"win": 0, "grow": 1, "deprioritize": 2}
    rows = [[L["seg_h"], L["ver_h"], L["why_h"]]] + [
        [x["segment"], vl[x["verdict"]], _clip(x["why"], 170)]
        for x in sorted(report["segments"], key=lambda x: order[x["verdict"]])]
    _table(s, MX, Inches(1.5), W - 2 * MX, rows, [2, 2, 9], 12, Inches(0.7 if len(rows) < 6 else 0.62))

    # tensions
    if report["tensions"]:
        s = ns(L["tens"])
        rows = [[L["tens"], L["strat"]]] + [[_clip(t["tension"], 170), _clip(t["strategy"], 220)] for t in report["tensions"]]
        _table(s, MX, Inches(1.5), W - 2 * MX, rows, [5, 6], 13, Inches(1.2))

    # actions
    s = ns(L["acts"])
    rows = [[L["hz"], L["act_h"], L["kpi_h"]]] + [
        [HZ[lang][a["horizon"]], _clip(a["action"], 150), _clip(a["kpi"], 90)] for a in report["actions"]]
    _table(s, MX, Inches(1.4), W - 2 * MX, rows, [1.4, 7, 4], 11, Inches(0.53))

    # personas
    ranked = sorted((p for p in personas if p["id"] in means), key=lambda p: -means[p["id"]])
    picks = [(p, True) for p in ranked[:3]] + [(p, False) for p in reversed(ranked[-3:]) if p not in ranked[:3]]
    pm = {p["id"]: p for p in personas}
    gz = defaultdict(list)
    for g in result.get("gaze", []):
        gz[g["id"]].append(g)
    for p, hi in picks[:6]:
        prof = p.get("profile") or {}
        name = prof.get("full_name") or p.get("name", p["id"])
        meta = prof.get("meta") or f'{p.get("age", "")} / {p.get("gender", "")} / {p.get("occupation", "")} / {p.get("region", "")}'
        s = ns(f'{L["viewer_hi"] if hi else L["viewer_lo"]}: {_clip(name, 30)}')
        img = Path(avatars.CACHE) / f"{avatars.key(p)}.jpg"
        if img.exists():
            s.shapes.add_picture(str(img), MX, Inches(1.6), Inches(3.4), Inches(3.4))
        text(s, MX, Inches(5.2), Inches(3.4), Inches(0.5), name, 18, True)
        text(s, MX, Inches(5.65), Inches(3.4), Inches(0.9), _clip(meta, 90), 12, False, MUTED)
        text(s, MX + Inches(4.0), Inches(1.6), Inches(6), Inches(0.4),
             f'{L["avg"]}: {means[p["id"]]:.1f}' + (f'  ·  {_clip(prof["headline"], 70)}' if prof.get("headline") else ''), 14, True)
        text(s, MX + Inches(4.0), Inches(2.3), Inches(6), Inches(0.3), L["thoughts"], 12, True, MUTED)
        gs = sorted(gz[p["id"]], key=lambda g: -g["interest"] if hi else g["interest"])[:2]
        y = Inches(2.75)
        for g in gs:
            q = (g.get("thought_en") if lang == "en" and g.get("thought_en") else g.get("thought")) or ""
            rect(s, MX + Inches(4.0), y, Inches(0.07), Inches(1.5), ACCENT if hi else INK)
            text(s, MX + Inches(4.25), y, Inches(8.0), Inches(1.5), f"“{_clip(q, 200)}”\n{_mmss(g['t'])}  ·  {g.get('looking_at', '')}", 14)
            y += Inches(1.9)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
