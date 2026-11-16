"""UI strings in English and Japanese. Use t(key, lang, **fmt)."""

STRINGS = {
    # masthead
    "tagline": ("Show your ad to a panel of AI viewers before it goes live. See where each person looks, "
                "what they think at every moment, and ask them why.",
                "配信前に、AIの視聴者パネルで広告をテストします。一人ひとりの視線と、その瞬間の本音を確認し、"
                "理由を直接聞くことができます。"),
    # sidebar
    "reports": ("Reports", "レポート"),
    "new_test": ("New test", "新しいテスト"),
    "no_reports": ("Finished tests are saved here.", "完了したテストはここに保存されます。"),
    "viewers_n": ("{n} viewers", "{n}人"),
    "signed_in_as": ("Signed in as {who}", "{who} でログイン中"),
    "sign_out": ("Sign out", "ログアウト"),
    # setup
    "step1": ("1. Who is watching?", "1. 視聴者"),
    "age": ("Age range", "年齢"),
    "count": ("Number of viewers", "人数"),
    "gender": ("Gender", "性別"),
    "female": ("Female", "女性"),
    "male": ("Male", "男性"),
    "csv": ("Use your own people data, CSV (optional)", "顧客データを使う（CSV・任意）"),
    "step2": ("2. Which ad?", "2. 広告"),
    "media": ("Video or banner", "動画・バナー"),
    "context": ("What is the ad for? (optional)", "広告の内容（任意）"),
    "context_ph": ("e.g. Hybrid family car, long-term owner review", "例：ハイブリッドのファミリーカー、長期オーナーレビュー"),
    "start": ("Show it to the viewers", "視聴を開始"),
    "pick_gender": ("Pick at least one gender.", "性別を1つ以上選んでください。"),
    "drawing": ("Drawing portraits for {n} viewers", "{n}人の顔写真を作成中"),
    "panel": ("Your panel: {n} viewers", "パネル：{n}人"),
    # run
    "watching": ("Viewers are watching", "視聴中"),
    "frames": ("{n} frames analysed ({where})", "{n}フレームを解析（{where}）"),
    "lines": ("{n} spoken lines transcribed", "{n}行の音声を書き起こし"),
    "no_speech": ("No speech was transcribed, so viewers will judge the visuals only.",
                  "音声を書き起こせなかったため、映像のみで評価します。"),
    "reactions": ("{n} reactions from {p} viewers", "{p}人から{n}件の反応"),
    "saving": ("Saving report", "レポートを保存中"),
    "finished": ("Finished watching", "視聴完了"),
    # report
    "tested": ("Tested {when} with {n} viewers", "{when}に{n}人でテスト"),
    "tab_results": ("Results", "結果"),
    "tab_viewers": ("Viewers", "視聴者"),
    "tab_interview": ("Interview", "インタビュー"),
    "no_reactions": ("No reactions were recorded.", "反応が記録されていません。"),
    "interest_time": ("Interest over time", "興味の推移"),
    "looked_at": ("What they looked at", "注目したもの"),
    "by_segment": ("Interest by age and gender", "年齢・性別ごとの興味"),
    "transcript": ("What was said in the ad", "広告内の発言（書き起こし）"),
    "talk_to": ("Talk to", "話す相手"),
    "ask": ("Ask about the ad", "広告について質問する"),
    "not_found": ("This report does not exist or belongs to someone else.", "このレポートは存在しないか、他のユーザーのものです。"),
    # verdict
    "v_main": ("{e} of {n} viewers stayed interested.", "{n}人中{e}人が興味を持ち続けました。"),
    "v_low": (" Attention dipped lowest at {t}.", "最も関心が下がったのは{t}です。"),
    "v_sub": ("Most looked at: {top}. Average interest {avg} out of 5.", "最も注目されたもの：{top}。平均興味度は5点中{avg}。"),
    # persona card
    "who_line": ("{occ} in {region}, income {income}", "{region}在住、{occ}、年収 {income}"),
    "who_into": ("Into {x}.", "関心：{x}"),
    "who_uses": ("Uses {x}.", "よく使うメディア：{x}"),
    # login
    "login_title": ("Sign in to AdLens", "AdLensにログイン"),
    "login_google": ("Continue with Google", "Googleでログイン"),
    "password": ("Password", "パスワード"),
    "login_btn": ("Sign in", "ログイン"),
    "bad_password": ("That password is not correct.", "パスワードが正しくありません。"),
    "too_many": ("Too many attempts. Reload the page and try again later.", "試行回数が多すぎます。しばらくしてから再読み込みしてください。"),
    "not_allowed": ("{email} is not allowed to use this app. Ask the owner to add you.",
                    "{email} にはこのアプリの利用権限がありません。管理者に追加を依頼してください。"),
    # player
    "p_heat": ("Heatmap", "ヒートマップ"),
    "p_ai": ("AI viewers' gaze", "AI視聴者の視線"),
    "p_mix": ("AI viewers + image", "AI視聴者＋画像"),
    "p_img": ("Image only", "画像のみ"),
    "p_off": ("Off", "なし"),
    "p_who": ("Who", "対象"),
    "p_all": ("Everyone", "全員"),
    "p_u25": ("Under 25", "25歳未満"),
    "p_45": ("45 and over", "45歳以上"),
    "p_women": ("Women", "女性"),
    "p_men": ("Men", "男性"),
    "p_faces": ("Faces", "顔"),
    "p_looking": ("Looking at", "注目"),
    "p_avg": ("{n} viewers, average interest {a} of 5", "{n}人、平均興味度 {a} / 5"),
    "p_none": ("No viewers in this group", "このグループに該当者はいません"),
}

LANGS = {"en": 0, "ja": 1}


def t(key: str, lang: str = "en", **fmt) -> str:
    text = STRINGS[key][LANGS.get(lang, 0)]
    return text.format(**fmt) if fmt else text
