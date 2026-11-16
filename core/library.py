"""Persona library: reusable groups (like a panel catalogue). Profiles and portraits are generated once.

Seeds are deliberately short; `persona_profile.ensure_profiles` turns each into a full tier-1 profile.
"""
import json

from core import llm
from core.personas import COLORS

M, F = "Male", "Female"

# (group id, JA name, EN name, description, [(seed id, age, gender, occupation, marital, segment)])
GROUPS = [
    ("age_gender", "性年代", "Age & gender", "各年代の標準的な生活者 / A typical person for each age band", [
        ("m15", 17, M, "高校生", "未婚", "男性15-19歳"), ("m20", 24, M, "大学院生", "未婚", "男性20-29歳"),
        ("m30", 34, M, "プログラマー", "未婚", "男性30-39歳"), ("m40", 45, M, "SE", "既婚", "男性40-49歳"),
        ("m50", 55, M, "技術管理職", "既婚", "男性50-59歳"), ("m60", 64, M, "無職", "既婚", "男性60-69歳"),
        ("m70", 73, M, "無職", "既婚", "男性70-79歳"),
        ("f15", 16, F, "高校生", "未婚", "女性15-19歳"), ("f20", 21, F, "大学生", "未婚", "女性20-29歳"),
        ("f30", 36, F, "パートタイム", "既婚", "女性30-39歳"), ("f40", 44, F, "パートタイム", "既婚", "女性40-49歳"),
        ("f50", 53, F, "パートタイム", "既婚", "女性50-59歳"), ("f60", 65, F, "専業主婦", "既婚", "女性60-69歳"),
        ("f70", 74, F, "専業主婦", "既婚", "女性70-79歳")]),
    ("lifestyle", "ライフスタイル", "Lifestyle", "生活価値観で分けた12タイプ / 12 lifestyle types", [
        ("ls_digital", 23, F, "大学生", "未婚", "デジタル先行・都市単身"),
        ("ls_dinks", 35, M, "IT管理職", "既婚", "時短思考・共働きDINKs"),
        ("ls_newparent", 33, F, "商品企画", "既婚", "子育てスタート"),
        ("ls_edu", 43, F, "一般事務", "既婚", "教育投資・小中子育て家族"),
        ("ls_busy", 46, F, "パートタイム", "既婚", "部活・送迎多忙家族"),
        ("ls_suburb", 63, M, "技術嘱託", "既婚", "郊外安定・実利派"),
        ("ls_premium", 44, M, "外資IT管理職", "既婚", "プレミアム思考・都市共働き"),
        ("ls_frugal", 38, F, "経理管理職", "既婚", "節約・堅実志向"),
        ("ls_wellness", 41, M, "外資IT管理職", "既婚", "ウェルネス・自己投資層"),
        ("ls_local", 56, F, "パートタイム", "既婚", "地域密着・リアル重視"),
        ("ls_active", 66, M, "無職", "既婚", "アクティブシニア"),
        ("ls_home", 67, F, "専業主婦", "既婚", "自宅ゆったり思考層")]),
    ("media_heavy", "メディア（ヘビー層）", "Heavy media users", "各メディアをよく使う人 / Heavy users of each channel", [
        ("md_tv", 64, F, "無職", "既婚", "地上波テレビ放送ヘビー層"),
        ("md_yt", 22, M, "大学生", "未婚", "YouTubeヘビー層"),
        ("md_ctv", 34, F, "ITマーケティング", "既婚", "cTV（TVer・ABEMA・Netflix等）ヘビー層"),
        ("md_line", 37, F, "パートタイム", "既婚", "LINEヘビー層"),
        ("md_ig", 26, F, "広告営業", "未婚", "Instagramヘビー層"),
        ("md_x", 28, F, "デザイン進行管理", "未婚", "Xヘビー層"),
        ("md_tiktok", 17, F, "高校生", "未婚", "TikTokヘビー層"),
        ("md_paper", 72, M, "無職", "既婚", "新聞ヘビー層"),
        ("md_radio", 63, M, "無職", "既婚", "ラジオヘビー層")]),
    ("category_loyal", "カテゴリー（ロイヤル層）", "Category loyalists", "そのカテゴリーをよく買う人 / Frequent buyers", [
        ("ct_skincare", 52, F, "専業主婦", "既婚", "化粧品（スキンケア）ロイヤル層"),
        ("ct_energy", 26, M, "エンジニア", "未婚", "エナジードリンク ロイヤル層"),
        ("ct_frozen", 17, F, "高校生", "未婚", "冷凍食品 ロイヤル層"),
        ("ct_beer", 62, M, "営業管理職", "既婚", "ビール飲料 ロイヤル層"),
        ("ct_conbini", 53, M, "商社課長", "既婚", "コンビニ ロイヤル層"),
        ("ct_ec", 27, F, "広告企画", "未婚", "インターネット通販 ロイヤル層"),
        ("ct_game", 25, M, "ITインフラ", "未婚", "ゲーム ロイヤル層"),
        ("ct_outdoor", 46, M, "技術管理職", "既婚", "アウトドア ロイヤル層"),
        ("ct_car", 61, M, "技術顧問", "既婚", "車・バイク ロイヤル層")]),
    ("car_owners", "ブランド・ロイヤル層（自動車）", "Car owners by model", "車種別オーナー / Owners by car model", [
        ("car_aqua", 62, M, "事務職", "未婚", "トヨタ アクア オーナー"),
        ("car_alphard", 36, M, "開発エンジニア", "既婚", "トヨタ アルファード オーナー"),
        ("car_prius", 54, M, "営業職", "未婚", "トヨタ プリウス オーナー"),
        ("car_sienta", 37, M, "経理職", "既婚", "トヨタ シエンタ オーナー"),
        ("car_note", 63, M, "技術職", "既婚", "日産 ノート e-POWER オーナー"),
        ("car_nbox", 42, F, "パートタイム", "既婚", "ホンダ N-BOX オーナー"),
        ("car_cx5", 35, M, "デザイナー", "既婚", "マツダ CX-5 オーナー"),
        ("car_hustler", 27, F, "事務職", "未婚", "スズキ ハスラー オーナー")]),
]

REGION_HINT = {"m15": "東京都世田谷区", "md_paper": "長野県", "ls_suburb": "埼玉県", "ls_local": "静岡県"}


def seeds() -> list[dict]:
    out, i = [], 0
    for gid, _, _, _, members in GROUPS:
        for sid, age, gender, job, marital, segment in members:
            out.append({"id": f"lib_{sid}", "group": gid, "name": "", "age": age, "gender": gender,
                        "occupation": job, "marital": marital, "segment": segment,
                        "region": REGION_HINT.get(sid, ""), "income": "", "interests": "", "media": "",
                        "values": "", "color": COLORS[i % len(COLORS)]})
            i += 1
    return out


def all_personas() -> dict[str, dict]:
    """Seeds merged with their generated profiles (if ready)."""
    from core.persona_profile import cached
    ps = seeds()
    for p in ps:
        prof = cached(p)
        if prof:
            p["profile"] = prof
            p["name"] = prof.get("full_name", "").split("（")[0].strip() or p["segment"]
            p["interests"] = ", ".join(prof.get("purchase_drivers", [])[:3])
            p["media"] = ", ".join(m.split(":")[0].split("：")[0].strip() for m in prof.get("media", [])[:4])
            p["values"] = ", ".join(prof.get("values_top", []))
            p["region"] = prof.get("region") or p["region"]
            p["income"] = prof.get("income", "")
        else:
            p["name"] = p["segment"]
    return {p["id"]: p for p in ps}


def build(model=None, log=print):
    """One-off: generate every library profile (Sonnet for quality) and portrait."""
    from core import avatars
    from core.persona_profile import ensure_profiles
    ps = seeds()
    ensure_profiles(ps, model=model or llm.CHAT_MODEL, log=log, batch_size=3)
    ps = list(all_personas().values())
    if avatars.available():
        missing = [p for p in ps if not avatars.cached(p)]
        log(f"Drawing {len(missing)} library portraits")
        avatars.generate_all(missing, log, workers=8)
    return ps


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(json.dumps({"personas": len(build())}))
