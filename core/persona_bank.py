"""Persona bank: ~5,000 synthetic Japanese residents (age 15-79) stored in Postgres, plus a fast query API.

Seeds are drawn from HAND-WRITTEN APPROXIMATIONS of public Japanese statistics (not exact tables):
  - age x gender: 2020 Population Census (e-Stat, 5-year bands, men's share by band), ages 15-79 only
  - prefecture: 2020 Census prefecture populations; urban/suburban/rural split by prefecture class (metro/mid/rural)
  - employment status by age and gender: shapes of the 2020 Census / Labour Force Survey (student share by exact age,
    regular vs non-regular, self-employed, homemaker, retired, unemployed)
  - occupation within regular employment by gender and age (managers appear with seniority)
  - personal income: lognormal around medians shaped like the NTA Private Salary Survey / Basic Survey on Wage
    Structure (age curve, ~22% gender gap, non-regular far lower, pension income for retirees), binned to bands
  - marital status by age and gender: 2020 Census marital shape (married / never-married / divorced / widowed)
  - household type conditional on age and marital status: shape of the Comprehensive Survey of Living Conditions
Everything is deterministic: persona i depends only on (BASE_SEED, i), so the bank is reproducible and extendable.

Layout: `PersonaBank` rows (id "bank_00001") are only inserted once a validated profile exists. `PersonaBankJob`
tracks every seed and its generation state (resumable builds), `PersonaBankBatch` tracks Message Batches.
Query API: sample() / get() / facets(). Candidate filtering uses a small in-memory index (5 short columns per
row, refreshed every INDEX_TTL seconds or via invalidate()); only the chosen rows' big JSON is read from the DB.
"""
import json
import math
import random
import re
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel, select

from core.personas import COLORS

BASE_SEED = 20260921
BANK_SIZE = 5000
GENDERS = ("Female", "Male")


def _now():
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- tables
class PersonaBank(SQLModel, table=True):
    __tablename__ = "persona_bank"
    id: str = Field(primary_key=True)                    # "bank_00001"
    age: int = Field(index=True)
    gender: str = Field(index=True)                      # Female | Male
    region: str = Field(index=True)                      # prefecture (Japanese, e.g. 東京都)
    area_type: str = ""                                  # urban | suburban | rural
    occupation: str = Field(index=True)
    employment: str = ""
    marital: str = ""
    household: str = ""
    income: str = ""
    segment_tags: list = Field(default_factory=list, sa_column=Column(JSON))
    profile: dict = Field(default_factory=dict, sa_column=Column(JSON))   # tier-1 profile (persona_profile.SCHEMA)
    seed: dict = Field(default_factory=dict, sa_column=Column(JSON))
    profile_en: dict | None = Field(default=None, sa_column=Column(JSON))  # English profile (core.localize)
    created_at: datetime = Field(default_factory=_now)


class PersonaBankJob(SQLModel, table=True):
    __tablename__ = "persona_bank_job"
    id: str = Field(primary_key=True)                    # same id as the future PersonaBank row
    seed: dict = Field(default_factory=dict, sa_column=Column(JSON))
    status: str = Field(default="pending", index=True)   # pending | submitted | done | failed
    attempt: int = 0                                     # number of batch submissions so far
    batch_id: str | None = Field(default=None, index=True)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = Field(default=None, sa_column=Column(Text))
    updated_at: datetime = Field(default_factory=_now)


class PersonaBankBatch(SQLModel, table=True):
    __tablename__ = "persona_bank_batch"
    batch_id: str = Field(primary_key=True)
    attempt: int = 1
    size: int = 0
    created_at: datetime = Field(default_factory=_now)
    collected_at: datetime | None = None
    input_tokens: int = 0
    output_tokens: int = 0


TABLES = [PersonaBank.__table__, PersonaBankJob.__table__, PersonaBankBatch.__table__]


def init_tables():
    from backend.db import engine
    SQLModel.metadata.create_all(engine, tables=TABLES)


# --------------------------------------------------------------------------- statistics (approximations)
# (prefecture ja, en, 2020 census population in thousands, class) class: T=Tokyo, M=metro, N=mid, R=rural
PREFS = [
    ("北海道", "Hokkaido", 5225, "N"), ("青森県", "Aomori", 1238, "R"), ("岩手県", "Iwate", 1211, "R"),
    ("宮城県", "Miyagi", 2302, "N"), ("秋田県", "Akita", 960, "R"), ("山形県", "Yamagata", 1068, "R"),
    ("福島県", "Fukushima", 1833, "R"), ("茨城県", "Ibaraki", 2867, "N"), ("栃木県", "Tochigi", 1933, "N"),
    ("群馬県", "Gunma", 1939, "N"), ("埼玉県", "Saitama", 7345, "M"), ("千葉県", "Chiba", 6284, "M"),
    ("東京都", "Tokyo", 14048, "T"), ("神奈川県", "Kanagawa", 9237, "M"), ("新潟県", "Niigata", 2201, "N"),
    ("富山県", "Toyama", 1035, "N"), ("石川県", "Ishikawa", 1133, "N"), ("福井県", "Fukui", 767, "R"),
    ("山梨県", "Yamanashi", 810, "R"), ("長野県", "Nagano", 2048, "N"), ("岐阜県", "Gifu", 1979, "N"),
    ("静岡県", "Shizuoka", 3633, "N"), ("愛知県", "Aichi", 7542, "M"), ("三重県", "Mie", 1770, "N"),
    ("滋賀県", "Shiga", 1414, "N"), ("京都府", "Kyoto", 2578, "M"), ("大阪府", "Osaka", 8838, "M"),
    ("兵庫県", "Hyogo", 5465, "M"), ("奈良県", "Nara", 1324, "N"), ("和歌山県", "Wakayama", 923, "R"),
    ("鳥取県", "Tottori", 553, "R"), ("島根県", "Shimane", 671, "R"), ("岡山県", "Okayama", 1888, "N"),
    ("広島県", "Hiroshima", 2800, "N"), ("山口県", "Yamaguchi", 1342, "R"), ("徳島県", "Tokushima", 720, "R"),
    ("香川県", "Kagawa", 951, "N"), ("愛媛県", "Ehime", 1335, "R"), ("高知県", "Kochi", 692, "R"),
    ("福岡県", "Fukuoka", 5135, "M"), ("佐賀県", "Saga", 811, "R"), ("長崎県", "Nagasaki", 1312, "R"),
    ("熊本県", "Kumamoto", 1738, "N"), ("大分県", "Oita", 1124, "R"), ("宮崎県", "Miyazaki", 1070, "R"),
    ("鹿児島県", "Kagoshima", 1588, "R"), ("沖縄県", "Okinawa", 1467, "N"),
]
PREF_EN = {ja: en for ja, en, _, _ in PREFS}
EN_TO_JA = {en.lower(): ja for ja, en, _, _ in PREFS}
AREA_MIX = {"T": (.88, .11, .01), "M": (.60, .34, .06), "N": (.35, .40, .25), "R": (.15, .33, .52)}

# (lo, hi, population thousands, male share) - 2020 census, 5-year bands
AGE_BANDS = [(15, 19, 5400, .512), (20, 24, 6150, .512), (25, 29, 6100, .507), (30, 34, 6350, .505),
             (35, 39, 7250, .503), (40, 44, 8450, .502), (45, 49, 9700, .502), (50, 54, 8650, .500),
             (55, 59, 7750, .497), (60, 64, 7650, .492), (65, 69, 8450, .485), (70, 74, 9000, .470),
             (75, 79, 7200, .450)]

# share of each age that is still a student (high school / university / graduate / vocational)
STUDENT_P = {15: .98, 16: .98, 17: .97, 18: .80, 19: .72, 20: .62, 21: .58, 22: .33, 23: .12, 24: .07,
             25: .03, 26: .03, 27: .02, 28: .02, 29: .02}

STATUSES = ("reg", "nonreg", "self", "home", "retired", "unemp")
# non-student status weights by band start: (reg, nonreg, self, home, retired, unemp)
STATUS_M = {15: (.66, .24, .02, 0, 0, .08), 25: (.78, .11, .04, .005, 0, .065), 30: (.80, .08, .06, .005, 0, .055),
            35: (.81, .07, .07, .005, 0, .045), 45: (.80, .07, .08, .005, 0, .045), 55: (.76, .10, .08, .005, .01, .045),
            60: (.38, .27, .11, .0, .17, .07), 65: (.15, .22, .14, 0, .42, .07), 70: (.07, .13, .16, 0, .56, .08),
            75: (.03, .07, .13, 0, .70, .07)}
STATUS_F = {15: (.46, .38, .01, .03, 0, .12), 25: (.58, .22, .03, .08, 0, .09), 30: (.40, .25, .04, .23, 0, .08),
            35: (.32, .36, .05, .20, 0, .07), 45: (.30, .40, .05, .20, 0, .05), 55: (.25, .38, .06, .25, 0, .06),
            60: (.12, .35, .07, .27, .12, .07), 65: (.05, .22, .08, .27, .33, .05), 70: (.02, .13, .09, .27, .44, .05),
            75: (.01, .07, .06, .27, .55, .04)}

REG_M = {"製造・生産職（正社員）": .20, "ITエンジニア（正社員）": .08, "営業職（正社員）": .13, "事務職（正社員）": .09,
         "建設・技能職（正社員）": .10, "運輸・物流（正社員）": .09, "販売・サービス職（正社員）": .07,
         "金融・保険（正社員）": .04, "医療職（正社員）": .03, "教員（正社員）": .03, "公務員": .06,
         "専門職・研究職（正社員）": .04, "介護・福祉職（正社員）": .02}
REG_F = {"事務職（正社員）": .25, "医療職（看護師・薬剤師など）": .14, "介護・福祉職（正社員）": .06,
         "教員・保育士": .09, "販売・サービス職（正社員）": .09, "公務員": .06, "金融・保険（正社員）": .06,
         "製造・生産職（正社員）": .06, "営業職（正社員）": .06, "ITエンジニア（正社員）": .04,
         "専門職・研究職（正社員）": .04, "運輸・物流（正社員）": .01}
NONREG_SECTORS = {"小売・販売": .25, "飲食・接客": .18, "事務": .12, "医療・介護": .10, "製造・軽作業": .12,
                  "物流・配送": .08, "清掃・警備": .05, "教育・塾": .05, "コールセンター": .05}
SELF_JOBS = {"個人事業主（飲食・小売）": .20, "フリーランス（クリエイティブ・IT）": .15, "農業": .12,
             "建設職人・一人親方": .15, "自営（サービス業）": .18, "士業・開業医・専門職": .08, "運転手・個人運送": .06,
             "家業手伝い・自営": .06}
JOB_INCOME_MULT = {"管理職": 1.5, "IT": 1.1, "金融": 1.25, "医療": 1.05, "公務員": 1.1, "専門職": 1.2, "製造": .95,
                   "販売": .85, "介護": .8, "教員": 1.1, "運輸": 1.0, "建設": .98, "営業": 1.05, "事務": .92}
REG_MEDIAN = [(24, 280), (29, 360), (34, 420), (39, 470), (44, 520), (49, 560), (54, 600), (59, 600), (64, 420), (99, 330)]
INCOME_BINS = [(0, "収入なし"), (1, "〜100万円"), (100, "100〜200万円"), (200, "200〜300万円"), (300, "300〜400万円"),
               (400, "400〜500万円"), (500, "500〜700万円"), (700, "700〜1000万円"), (1000, "1000万円以上")]

# share married by band start (2020 census shape), plus divorced / widowed shares
MARRIED_M = {20: .06, 25: .25, 30: .49, 35: .61, 40: .66, 45: .66, 50: .69, 55: .74, 60: .78, 65: .82, 70: .84, 75: .83}
MARRIED_F = {20: .11, 25: .40, 30: .62, 35: .69, 40: .71, 45: .70, 50: .69, 55: .68, 60: .66, 65: .62, 70: .55, 75: .44}
DIVORCED = {20: .01, 25: .02, 30: .04, 35: .07, 40: .09, 45: .11, 50: .12, 55: .12, 60: .10, 65: .08, 70: .06, 75: .05}
WIDOWED_M = {55: .01, 60: .02, 65: .04, 70: .07, 75: .12}
WIDOWED_F = {45: .01, 50: .03, 55: .05, 60: .09, 65: .15, 70: .27, 75: .40}

AD_STANCES = [("広告はほぼ飛ばす・避ける", .22), ("広告は信用しない・うっとうしいと感じる", .18),
              ("ほとんど気にしない・無関心", .25), ("内容や気分次第で見る", .20),
              ("広告を参考にすることもある", .08), ("特定ジャンルの広告だけ興味がある", .07)]
NON_USE = [  # (item, weight young, weight old)
    ("X(旧Twitter)", .30, .75), ("Instagram", .25, .75), ("TikTok", .45, .92), ("LINE以外のSNS全般", .10, .70),
    ("動画配信サブスク", .40, .75), ("ネット通販", .05, .55), ("ゲーム", .45, .85), ("テレビ", .45, .10),
    ("キャッシュレス決済", .10, .45), ("お酒", .40, .45), ("化粧品・美容サービス", .55, .55), ("新聞", .90, .30),
    ("YouTube", .08, .55), ("サプリ・健康食品", .70, .50),
]
HOBBIES_YOUNG = ["アニメ・漫画", "ゲーム", "K-POP・推し活", "ファッション", "カフェ巡り", "筋トレ", "動画配信視聴", "音楽ライブ",
                 "スポーツ観戦", "写真", "バンド・楽器", "プログラミング", "韓国ドラマ", "ダンス", "アウトドア・キャンプ"]
HOBBIES_MID = ["ドライブ", "ゴルフ", "料理", "子どもと過ごす", "ジョギング", "映画", "旅行", "釣り", "筋トレ", "投資・節約",
               "DIY・家庭菜園", "キャンプ", "ビール・クラフトビール", "読書", "ペットと暮らす", "野球観戦", "サウナ", "家事・時短工夫"]
HOBBIES_OLD = ["ウォーキング", "園芸・家庭菜園", "旅行", "囲碁・将棋", "カラオケ", "孫の世話", "テレビ・ドラマ", "釣り", "ゴルフ",
               "神社仏閣めぐり", "料理", "手芸・編み物", "健康維持", "地域のボランティア", "競馬・パチンコ", "写経・書道", "温泉"]

SURNAMES = ("佐藤:さとう 鈴木:すずき 高橋:たかはし 田中:たなか 伊藤:いとう 渡辺:わたなべ 山本:やまもと 中村:なかむら 小林:こばやし "
            "加藤:かとう 吉田:よしだ 山田:やまだ 佐々木:ささき 山口:やまぐち 松本:まつもと 井上:いのうえ 木村:きむら 林:はやし "
            "斎藤:さいとう 清水:しみず 山崎:やまざき 森:もり 池田:いけだ 橋本:はしもと 阿部:あべ 石川:いしかわ 山下:やました "
            "中島:なかじま 石井:いしい 小川:おがわ 前田:まえだ 岡田:おかだ 長谷川:はせがわ 藤田:ふじた 後藤:ごとう 近藤:こんどう "
            "村上:むらかみ 遠藤:えんどう 青木:あおき 坂本:さかもと 斉藤:さいとう 福田:ふくだ 太田:おおた 西村:にしむら 藤井:ふじい "
            "岡本:おかもと 三浦:みうら 金子:かねこ 中野:なかの 原田:はらだ 松田:まつだ 竹内:たけうち 小野:おの 田村:たむら "
            "中山:なかやま 和田:わだ 石田:いしだ 森田:もりた 上田:うえだ 原:はら 柴田:しばた 酒井:さかい 工藤:くどう 横山:よこやま "
            "宮崎:みやざき 宮本:みやもと 内田:うちだ 高木:たかぎ 安藤:あんどう 谷口:たにぐち 大野:おおの 丸山:まるやま 今井:いまい "
            "河野:こうの 藤原:ふじわら 大塚:おおつか 平野:ひらの 松井:まつい 千葉:ちば 武田:たけだ 杉山:すぎやま 菅原:すがわら "
            "小島:こじま 野口:のぐち 桜井:さくらい 木下:きのした 新井:あらい 久保:くぼ 水野:みずの 浅野:あさの 北村:きたむら")
SURNAMES_OKINAWA = "比嘉:ひが 金城:きんじょう 仲村:なかむら 新垣:あらかき 宮城:みやぎ 島袋:しまぶくろ 大城:おおしろ 玉城:たましろ 上原:うえはら 照屋:てるや"
GIVEN = {  # birth-year era -> gender -> "漢字:よみ ..."
    0: {"F": "和子:かずこ 幸子:さちこ 洋子:ようこ 節子:せつこ 恵子:けいこ 京子:きょうこ 孝子:たかこ 悦子:えつこ 道子:みちこ 智子:ともこ 弘子:ひろこ 美智子:みちこ",
        "M": "修:おさむ 勇:いさむ 正:ただし 茂:しげる 博:ひろし 進:すすむ 清:きよし 登:のぼる 隆:たかし 実:みのる 武:たけし 誠:まこと"},
    1: {"F": "真由美:まゆみ 由美子:ゆみこ 恵美子:えみこ 久美子:くみこ 裕子:ゆうこ 陽子:ようこ 直美:なおみ 順子:じゅんこ 公子:きみこ 明美:あけみ 典子:のりこ 清美:きよみ",
        "M": "裕:ゆたか 浩:ひろし 健二:けんじ 和夫:かずお 英樹:ひでき 達也:たつや 学:まなぶ 稔:みのる 誠一:せいいち 秀樹:ひでき 孝:たかし 剛:つよし"},
    2: {"F": "恵:めぐみ 智美:ともみ 美穂:みほ 由紀:ゆき 麻美:あさみ 浩美:ひろみ 純子:じゅんこ 久美:くみ 香織:かおり 千里:ちさと 美樹:みき 真理子:まりこ",
        "M": "淳:じゅん 剛:つよし 大輔:だいすけ 浩二:こうじ 直樹:なおき 賢一:けんいち 俊介:しゅんすけ 秀明:ひであき 誠:まこと 達也:たつや 和也:かずや 学:まなぶ"},
    3: {"F": "愛:あい 麻衣:まい 彩:あや 友美:ともみ 真紀:まき 絵里:えり 沙織:さおり 美香:みか 加奈:かな 里美:さとみ 千恵:ちえ 麻里:まり",
        "M": "大輔:だいすけ 健太:けんた 翔:しょう 拓也:たくや 雄太:ゆうた 慎吾:しんご 亮:りょう 哲也:てつや 直人:なおと 圭介:けいすけ 智也:ともや 誠:まこと"},
    4: {"F": "美咲:みさき 愛美:まなみ 彩香:あやか 絵美:えみ 夏帆:かほ 沙耶:さや 里奈:りな 瞳:ひとみ 優子:ゆうこ 菜摘:なつみ 梨沙:りさ 遥:はるか",
        "M": "翔太:しょうた 拓海:たくみ 大樹:だいき 優太:ゆうた 竜也:たつや 健太:けんた 駿:しゅん 雄大:ゆうだい 隼人:はやと 凌:りょう 和樹:かずき 蓮:れん"},
    5: {"F": "結衣:ゆい 陽菜:ひな 美優:みゆ 莉子:りこ 葵:あおい 彩乃:あやの 凛:りん 愛梨:あいり 七海:ななみ 咲希:さき 楓:かえで 萌:もえ",
        "M": "大和:やまと 蓮:れん 颯太:そうた 陸:りく 翔平:しょうへい 拓真:たくま 優斗:ゆうと 海斗:かいと 悠人:はると 樹:いつき 涼太:りょうた 瑛太:えいた"},
    6: {"F": "陽葵:ひまり 結菜:ゆいな 芽依:めい 紬:つむぎ 澪:みお 心春:こはる 美桜:みお 詩:うた 彩花:あやか 花:はな 咲良:さくら 凛:りん",
        "M": "悠真:ゆうま 蓮:れん 陽翔:はると 湊:みなと 大翔:ひろと 樹:いつき 颯:はやて 朝陽:あさひ 律:りつ 新:あらた 蒼太:そうた 結翔:ゆいと"},
}


def _pairs(s):
    return [tuple(x.split(":")) for x in s.split()]


_SURN, _SURN_OKI = _pairs(SURNAMES), _pairs(SURNAMES_OKINAWA)
_GIVEN = {era: {g: _pairs(v) for g, v in d.items()} for era, d in GIVEN.items()}
_PREF_TOTAL = sum(p[2] for p in PREFS)


def _band_val(table, age, default=0.0):
    keys = [k for k in table if k <= age]
    return table[max(keys)] if keys else default


def _wchoice(rng, weights: dict | list):
    items = list(weights.items()) if isinstance(weights, dict) else list(weights)
    return rng.choices([k for k, _ in items], [w for _, w in items])[0]


def _era(age):
    by = 2026 - age
    for i, lim in enumerate((1955, 1965, 1975, 1985, 1995, 2005)):
        if by <= lim:
            return i
    return 6


def age_band(age: int) -> str:
    if age < 20:
        return "15-19"
    lo = age // 10 * 10
    return f"{lo}-{lo + 9}"


BAND_ORDER = ["15-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79"]


def _band_label(age):
    return "10代" if age < 20 else f"{age // 10 * 10}代"


def _marital(rng, age, gender, student):
    if student or age < 18:
        return "未婚"
    t_m = MARRIED_M if gender == "Male" else MARRIED_F
    married = _band_val(t_m, age) if age >= 20 else .01
    div = _band_val(DIVORCED, age) if age >= 20 else 0
    wid = _band_val(WIDOWED_M if gender == "Male" else WIDOWED_F, age)
    r = rng.random()
    if r < married:
        return "既婚"
    r -= married
    if r < div:
        return "離別"
    r -= div
    if r < wid:
        return "死別"
    return "未婚"


def _status(rng, age, gender, marital, area):
    w = list(_band_val(STATUS_M if gender == "Male" else STATUS_F, age if age >= 15 else 15))
    if gender == "Female":
        w[3] *= 1.35 if marital == "既婚" else .05
    if gender == "Male" and marital != "既婚":
        w[3] = 0
    if age < 60:
        w[4] = 0
    if area == "rural":
        w[2] *= 1.4
    return rng.choices(STATUSES, w)[0]


def _occupation(rng, status, age, gender, area):
    """-> (occupation, employment, class) where class feeds the income model."""
    if status == "student":
        if age <= 17:
            return "高校生", "学生", "student"
        if age >= 22 and rng.random() < .25:
            return "大学院生", "学生", "student"
        return rng.choices(["大学生", "専門学校生", "高校生"], [.80, .17, .03 if age == 18 else 0])[0], "学生", "student"
    if status == "reg":
        w = dict(REG_M if gender == "Male" else REG_F)
        mg = 0 if age < 35 else .06 if age < 40 else .14 if age < 45 else .22 if age < 60 else .08
        if gender == "Female":
            mg *= .3
        w["管理職（課長以上）"] = mg * sum(w.values()) / max(1e-9, 1 - mg)
        return _wchoice(rng, w), "正社員", "reg"
    if status == "nonreg":
        sector = _wchoice(rng, NONREG_SECTORS)
        if age >= 60 and rng.random() < .5:
            sector = rng.choice(["清掃・警備", "物流・配送", "小売・販売", "製造・軽作業"])
        if rng.random() < (.75 if gender == "Female" else .62) or age >= 65 and rng.random() < .8:
            return f"パート・アルバイト（{sector}）", "パート・アルバイト", "pt"
        return f"契約社員・派遣社員（{sector}）", "契約・派遣", "contract"
    if status == "self":
        w = dict(SELF_JOBS)
        if area == "rural":
            w["農業"] *= 3
        if area == "urban":
            w["農業"] *= .1
        return _wchoice(rng, w), "自営・フリーランス", "self"
    if status == "home":
        return ("専業主婦" if gender == "Female" else "専業主夫"), "専業主婦(夫)", "home"
    if status == "retired":
        return "年金生活者（退職後）", "退職・年金生活", "retired"
    return ("無職（求職中・休職中）" if age < 60 else "無職"), "無職", "unemp"


def _income(rng, occ, cls, age, gender):
    z = rng.gauss(0, 1)
    if cls == "student":
        v = 0 if rng.random() < .30 else min(180, math.exp(math.log(45) + .9 * z))
    elif cls == "reg":
        med = next(m for a, m in REG_MEDIAN if age <= a)
        mult = next((m for k, m in JOB_INCOME_MULT.items() if k in occ), 1.0)
        v = med * mult * (.78 if gender == "Female" else 1.0) * math.exp(.30 * z)
    elif cls == "pt":
        v = (95 if gender == "Female" else 140) * math.exp(.6 * z)
    elif cls == "contract":
        v = (230 if gender == "Female" else 300) * math.exp(.45 * z)
    elif cls == "self":
        v = 330 * (.8 if gender == "Female" else 1) * math.exp(.8 * z)
    elif cls == "home":
        v = 0 if rng.random() < .72 else min(130, math.exp(math.log(70) + .5 * z))
    elif cls == "retired":
        v = (200 if gender == "Male" else 115) * math.exp(.45 * z)
    else:
        v = 0 if rng.random() < .6 else min(150, math.exp(math.log(60) + .7 * z))
    if age >= 65 and cls in ("pt", "contract", "self"):
        v *= .6   # older workers: fewer hours, lower pay
    v = max(0.0, v)
    label = INCOME_BINS[0][1]
    for lo, name in INCOME_BINS:
        if v >= lo and (lo > 0 or v == 0):
            label = name
    return label, v


def _household(rng, age, gender, marital, occ, cls):
    kids = lambda: rng.choices([1, 2, 3], [.30, .52, .18])[0]  # noqa: E731
    if marital == "未婚":
        if age < 25:
            p_alone = .40 if "大学" in occ or "専門" in occ else .12
            return "単身世帯（一人暮らし）" if rng.random() < p_alone else "親と同居"
        if age < 40:
            return "単身世帯（一人暮らし）" if rng.random() < (.60 if gender == "Male" else .55) else "親と同居"
        return "単身世帯（一人暮らし）" if rng.random() < .55 else "親と同居"
    if marital == "既婚":
        if age < 35:
            return _wchoice(rng, {"夫婦のみ": .35, f"夫婦と子ども（子{kids()}人）": .60, "三世代同居": .05})
        if age < 55:
            return _wchoice(rng, {"夫婦のみ": .15, f"夫婦と子ども（子{kids()}人）": .66, "三世代同居": .13, "夫婦と親": .06})
        return _wchoice(rng, {"夫婦のみ": .55, f"夫婦と子ども（成人した子{kids()}人と同居）": .25, "三世代同居": .15, "夫婦と親": .05})
    if marital == "離別":
        return _wchoice(rng, {"単身世帯（一人暮らし）": .45, f"ひとり親と子ども（子{kids()}人）": .35 if gender == "Female" else .12,
                              "親と同居": .20 if gender == "Female" else .43})
    return _wchoice(rng, {"単身世帯（一人暮らし）": .60, "子ども世帯と同居": .35, "親と同居": .05})


def _segments(age, gender, marital, household, area, occ, cls, v):
    tags = [_band_label(age)]
    if cls == "student":
        tags.append("学生")
    elif age >= 65:
        tags.append("シニア")
    elif age >= 50:
        tags.append("プレシニア")
    elif "子ども" in household and age < 55:
        tags.append("子育て世帯")
    elif marital == "既婚" and age < 50:
        tags.append("DINKs・子なし夫婦" if "夫婦のみ" in household else "既婚者")
    elif cls in ("reg", "contract", "pt") and age < 35:
        tags.append("若手社会人")
    if "単身" in household:
        tags.append("一人暮らし")
    if cls == "home":
        tags.append("専業主婦(夫)")
    if cls != "student" and v >= 700:
        tags.append("高所得層")
    elif cls in ("pt", "contract", "reg", "self") and v < 200:
        tags.append("低所得・節約志向")
    tags.append({"urban": "都市部", "suburban": "郊外", "rural": "地方"}[area])
    return tags


def _big_five(rng, age, gender):
    """Target Big Five scores (0-100) drawn per person so the panel is not uniformly 'conscientious and calm'."""
    mu = {"openness": 50 - (age - 15) * .15, "conscientiousness": 45 + (age - 15) * .2, "extraversion": 50,
          "agreeableness": 48 + (4 if gender == "Female" else 0) + (age - 15) * .08,
          "neuroticism": 50 + (5 if gender == "Female" else 0) - (age - 15) * .15}
    return {k: int(min(95, max(5, round(rng.gauss(m, 18))))) for k, m in mu.items()}


def make_seed(i: int, base: int = BASE_SEED) -> dict:
    """Deterministic seed for persona number i (1-based). Depends only on (base, i)."""
    rng = random.Random(f"adlens-bank:{base}:{i}")
    lo, hi, _, male_share = rng.choices(AGE_BANDS, [b[2] for b in AGE_BANDS])[0]
    age = rng.randint(lo, hi)
    gender = "Male" if rng.random() < male_share else "Female"
    pref = rng.choices(PREFS, [p[2] for p in PREFS])[0]
    area = rng.choices(["urban", "suburban", "rural"], AREA_MIX[pref[3]])[0]
    student = rng.random() < STUDENT_P.get(age, 0)
    marital = _marital(rng, age, gender, student)
    status = "student" if student else _status(rng, age, gender, marital, area)
    occ, emp, cls = _occupation(rng, status, age, gender, area)
    income, v = _income(rng, occ, cls, age, gender)
    household = _household(rng, age, gender, marital, occ, cls)

    g = "M" if gender == "Male" else "F"
    sur, sur_r = rng.choice(_SURN_OKI if pref[0] == "沖縄県" and rng.random() < .55 else _SURN)
    given, given_r = rng.choice(_GIVEN[_era(age)][g])
    young = (age - 15) / 64
    non_use = []
    pool = [(n, py + (po - py) * young) for n, py, po in NON_USE]
    if area == "urban":
        pool.append(("自家用車", .60))
    elif area == "suburban":
        pool.append(("自家用車", .20))
    for _ in range(rng.choice([2, 2, 3])):
        item = rng.choices(pool, [w for _, w in pool])[0]
        non_use.append(item[0])
        pool = [p for p in pool if p[0] != item[0]]
    hob = HOBBIES_YOUNG if age < 30 else HOBBIES_MID if age < 60 else HOBBIES_OLD
    digital = rng.choices(["ヘビー（スマホ・SNSを長時間）", "ふつう（必要なものは使う）", "ライト（スマホは連絡と調べもの程度）"],
                          [.62, .33, .05] if age < 30 else [.30, .55, .15] if age < 50 else [.12, .55, .33] if age < 65 else [.05, .45, .50])[0]
    return {
        "age": age, "gender": gender, "region": pref[0], "region_en": pref[1], "area_type": area,
        "occupation": occ, "employment": emp, "marital": marital, "household": household, "income": income,
        "segment_tags": _segments(age, gender, marital, household, area, occ, cls, v),
        "surname": sur, "surname_reading": sur_r, "given": given, "given_reading": given_r,
        "ad_stance": _wchoice(rng, AD_STANCES), "digital": digital, "non_use": non_use,
        "hobbies": rng.sample(hob, 2), "big_five": _big_five(rng, age, gender),
    }


def bank_id(i: int) -> str:
    return f"bank_{i:05d}"


# --------------------------------------------------------------------------- prompt + validation
def seed_text(s: dict) -> str:
    b = s["big_five"]
    area = {"urban": "都市部", "suburban": "郊外", "rural": "地方・農村部"}[s["area_type"]]
    return (f"年齢: {s['age']}歳 / 性別: {'女性' if s['gender'] == 'Female' else '男性'} / 居住地: {s['region']}（{area}）\n"
            f"職業: {s['occupation']}（{s['employment']}） / 個人年収: {s['income']}\n"
            f"婚姻: {s['marital']} / 世帯: {s['household']}\n"
            f"氏名（この通りに使うこと）: {s['surname']} {s['given']}（{s['surname_reading']} {s['given_reading']}）\n"
            f"セグメント: {', '.join(s['segment_tags'])}\n"
            f"広告への基本姿勢（ad_attitudeにこれを反映する）: {s['ad_stance']}\n"
            f"デジタル利用度: {s['digital']}\n"
            f"ビッグファイブ（big_fiveにこの値をそのまま書き、60以上/40以下の特性は言動に表れ、矛盾しない描写にする）: "
            f"開放性{b['openness']} 誠実性{b['conscientiousness']} 外向性{b['extraversion']} "
            f"協調性{b['agreeableness']} 神経症傾向{b['neuroticism']}\n"
            f"使っていない/関わっていないもの（必ず『使わない』と書き、mediaやpurchase_driversに入れない）: {', '.join(s['non_use'])}\n"
            f"趣味・関心のヒント（そのまま羅列せず、生活に合うものだけ使う）: {', '.join(s['hobbies'])}")


def build_system() -> str:
    from core.persona_profile import PROFILE_RULES, SCHEMA
    return (f"You write one consumer-research persona profile for a person living in Japan, for an audience panel that "
            f"watches advertisements.\n\n{PROFILE_RULES}\n\n"
            "Extra rules:\n"
            "- The given attributes are facts. Do not change age, job, region, household, income, name or reading.\n"
            "- full_name must be exactly: 姓 名（せい めい）, using the given name and readings.\n"
            "- meta follows 世代/性別/職業/婚姻 (e.g. 20代/女性/大学生/未婚). household, income and region must echo the given facts.\n"
            "- Not everyone is happy or well off: show money, time, health, family or work strain proportionate to the life.\n"
            "- Use region-appropriate life details (car vs train, local shops) without cliches. Seniors need not be tech-savvy; "
            "young people are not automatically heavy ad consumers.\n"
            "- media lists 3-5 channels the person really uses, each as 'channel: how they use it'. "
            "purchase_drivers and purchase_barriers have 3 items each. values_top and values_low have exactly 3 items.\n"
            "- Avoid stock phrases and clichés shared across people: do not write 'チャンネルを変える/席を立つ' for TV ads, "
            "do not mention obituary columns (訃報・おくやみ欄), and do not end every field with a lesson. Ground ad_attitude "
            "in a concrete habit or context of this person (an episode only sometimes); never open it with 先月 or 去年; "
            "do not use the 'subscription trap from a health-food ad' story; vary sentence shapes.\n"
            "- Write all text fields in Japanese. Big Five scores are integers 0-100 and should differ between people "
            "(do not default to 50-70).\n"
            f"- Return ONLY one JSON object, no markdown fence, exactly in this shape:\n{SCHEMA}")


def build_user(s: dict) -> str:
    return f"Attributes of this person:\n{seed_text(s)}"


_JP = re.compile(r"[぀-ヿ一-鿿]")
BIG5 = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def schema_keys() -> list[str]:
    from core.persona_profile import SCHEMA
    try:
        return list(json.loads(SCHEMA))
    except ValueError:
        return re.findall(r'^  "(\w+)":', SCHEMA, re.M)


def parse_profile(text: str):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in output")
    return json.loads(text[a:b + 1])


def validate_profile(p, seed: dict) -> str | None:
    """Returns an error string, or None if the profile is acceptable (and coerces big_five to ints in place)."""
    if not isinstance(p, dict):
        return "not an object"
    missing = [k for k in schema_keys() if k not in p]
    if missing:
        return f"missing keys {missing}"
    name = str(p["full_name"])
    if not _JP.search(name) or not name.startswith(seed["surname"]):
        return f"bad name {name!r}"
    b5 = p["big_five"]
    if not isinstance(b5, dict) or any(k not in b5 for k in BIG5):
        return "big_five keys"
    for k in BIG5:
        v = b5[k]
        if isinstance(v, float) and v == int(v):
            v = int(v)
        if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 100:
            return f"big_five {k}={v!r}"
        b5[k] = v
    p["big_five"] = dict(seed["big_five"])   # the seed's target scores are authoritative
    for k in ("media", "purchase_drivers", "purchase_barriers", "values_top", "values_low", "insights"):
        if not isinstance(p[k], list) or not p[k]:
            return f"{k} must be a non-empty list"
    if len(p["values_top"]) < 3 or len(p["purchase_drivers"]) < 3:
        return "too few values/drivers"
    if not str(p.get("ad_attitude", "")).strip() or not str(p.get("daily_life", "")).strip():
        return "empty text field"
    return None


# --------------------------------------------------------------------------- query API
INDEX_TTL = 300
_idx = {"rows": None, "t": 0.0, "facets": None}
_lock = threading.Lock()


def invalidate():
    with _lock:
        _idx.update(rows=None, t=0.0, facets=None)
        _rows.clear()


def _index():
    """In-memory light index [(id, age, gender, region, occupation)], sorted by id."""
    with _lock:
        if _idx["rows"] is not None and time.time() - _idx["t"] < INDEX_TTL:
            return _idx["rows"]
    from backend.db import session
    with session() as s:
        rows = s.exec(select(PersonaBank.id, PersonaBank.age, PersonaBank.gender, PersonaBank.region,
                             PersonaBank.occupation).order_by(PersonaBank.id)).all()
    rows = [tuple(r) for r in rows]
    with _lock:
        _idx.update(rows=rows, t=time.time(), facets=None)
        _rows.clear()   # a refresh may mean rows were rebuilt
    return rows


def _to_persona(row: PersonaBank, color: str | None = None) -> dict:
    prof = row.profile or {}
    name = re.sub(r"[（(].*?[）)]", "", prof.get("full_name") or "").strip() or row.id
    media = ", ".join(m.split(":")[0].split("：")[0].strip() for m in (prof.get("media") or [])[:4])
    return {
        "id": row.id, "name": name, "age": row.age, "gender": row.gender, "region": row.region,
        "occupation": row.occupation, "income": row.income,
        "interests": ", ".join(str(x) for x in (prof.get("purchase_drivers") or [])[:3]),
        "media": media, "values": ", ".join(str(x) for x in (prof.get("values_top") or [])),
        "marital": row.marital, "segment": ", ".join(row.segment_tags or []),
        "profile": prof, "color": color or COLORS[0],
    }


_rows: dict[str, PersonaBank] = {}   # id -> detached row; bounded by the bank size, cleared with the index


def _fetch(ids: list[str]) -> dict[str, PersonaBank]:
    """Full rows (with the big JSON) for the chosen ids: one `IN` query for whatever is not cached yet."""
    need = [i for i in dict.fromkeys(ids) if i not in _rows]
    if need:
        from backend.db import session
        with session() as s:
            for r in s.exec(select(PersonaBank).where(PersonaBank.id.in_(need))).all():
                _rows[r.id] = r
    return {i: _rows[i] for i in ids if i in _rows}


def _norm_regions(regions):
    return {EN_TO_JA.get(str(r).strip().lower(), str(r).strip()) for r in regions} if regions else None


def sample(age_min=15, age_max=79, genders=("Female", "Male"), count=20, regions=None, occupations=None, seed=None):
    """Stratified panel -> (personas, matched). Strata = (10-year age band, gender), allocated in proportion to the
    bank (largest remainder); inside a stratum picks round-robin over prefectures so regions are spread, not just Tokyo.
    Same seed + same filter => same panel (seed=None means a fresh random panel). `matched` = rows passing the filter."""
    gset = {"Female" if str(g).lower().startswith(("f", "女")) else "Male" for g in (genders or GENDERS)}
    rset, oset = _norm_regions(regions), (set(occupations) if occupations else None)
    cand = [r for r in _index() if age_min <= r[1] <= age_max and r[2] in gset
            and (rset is None or r[3] in rset) and (oset is None or r[4] in oset)]
    matched = len(cand)
    count = max(0, int(count))
    if matched <= count:
        chosen = [r[0] for r in cand]
        rng = random.Random(seed)
        rng.shuffle(chosen)
    else:
        rng = random.Random(seed)
        strata: dict = {}
        for r in cand:
            strata.setdefault((age_band(r[1]), r[2]), []).append(r)
        keys = sorted(strata)
        quota = {k: count * len(strata[k]) / matched for k in keys}
        take = {k: int(quota[k]) for k in keys}
        rest = count - sum(take.values())
        order = sorted(keys, key=lambda k: (-(quota[k] - take[k]), rng.random()))
        for k in order:
            if rest <= 0:
                break
            if take[k] < len(strata[k]):
                take[k] += 1
                rest -= 1
        chosen = []
        for k in keys:
            by_region: dict = {}
            for r in strata[k]:
                by_region.setdefault(r[3], []).append(r[0])
            groups = [by_region[x] for x in sorted(by_region)]
            for g in groups:
                rng.shuffle(g)
            rng.shuffle(groups)
            n = take[k]
            while n > 0 and groups:
                for g in list(groups):
                    if n == 0:
                        break
                    chosen.append(g.pop())
                    n -= 1
                    if not g:
                        groups.remove(g)
        rng.shuffle(chosen)
    rows = _fetch(chosen)
    out = [_to_persona(rows[i], COLORS[n % len(COLORS)]) for n, i in enumerate(x for x in chosen if x in rows)]
    return out, matched


def get(ids) -> list[dict]:
    """Personas for the given ids, in the given order (unknown ids skipped)."""
    ids = list(ids)
    rows = _fetch(ids)
    return [_to_persona(rows[i], COLORS[n % len(COLORS)]) for n, i in enumerate(x for x in ids if x in rows)]


def facets() -> dict:
    """{total, regions:[{name,count}], occupations:[{name,count}], age_bands:[{band,count}]}, cached in memory."""
    rows = _index()
    with _lock:
        if _idx["facets"] is not None:
            return _idx["facets"]
    from collections import Counter
    reg, occ, band = Counter(r[3] for r in rows), Counter(r[4] for r in rows), Counter(age_band(r[1]) for r in rows)
    # 10-year bands, with 15-19 kept separate; BAND_ORDER's 20-29 etc. come from age_band()
    out = {"total": len(rows),
           "regions": [{"name": k, "count": v} for k, v in reg.most_common()],
           "occupations": [{"name": k, "count": v} for k, v in occ.most_common()],
           "age_bands": [{"band": b, "count": band.get(b, 0)} for b in BAND_ORDER]}
    with _lock:
        _idx["facets"] = out
    return out
