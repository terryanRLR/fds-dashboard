# -*- coding: utf-8 -*-
"""
FDS QA Dashboard — 다국어(i18n) 데이터 모듈
언어: ko(기본) / en / ja / zh
dashboard.py에서 `from i18n_data import *` 로 불러와 사용합니다.
"""

LANG_OPTIONS = ["ko", "en", "ja", "zh"]
LANG_DISPLAY = {"ko": "🇰🇷 한국어", "en": "🇺🇸 English", "ja": "🇯🇵 日本語", "zh": "🇨🇳 中文"}


def make_t(session_state):
    """session_state를 클로저로 받아 t(key, **kwargs) 헬퍼를 반환"""
    def t(key, **kwargs):
        lang = session_state.get('lang', 'ko')
        s = TR.get(lang, TR['ko']).get(key)
        if s is None:
            s = TR['ko'].get(key, key)
        if kwargs:
            try:
                return s.format(**kwargs)
            except Exception:
                return s
        return s
    return t


# ══════════════════════════════════════════════════════════
# 정적 UI 문자열
# ══════════════════════════════════════════════════════════
TR = {"ko": {}, "en": {}, "ja": {}, "zh": {}}

def _add(key, ko, en, ja, zh):
    TR["ko"][key] = ko
    TR["en"][key] = en
    TR["ja"][key] = ja
    TR["zh"][key] = zh

# ── 패키지 체크 ──
_add("pkg.expander", "⚠️ 미설치 패키지 {n}개 감지 — 클릭하여 확인", "⚠️ {n} package(s) missing — click to view", "⚠️ 未インストールのパッケージが{n}件 — クリックして確認", "⚠️ 检测到 {n} 个未安装的软件包 — 点击查看")
_add("pkg.desc", "일부 기능이 제한될 수 있습니다. 아래 명령어로 설치하세요:", "Some features may be limited. Install with the command below:", "一部の機能が制限される場合があります。以下のコマンドでインストールしてください:", "部分功能可能受限。请使用以下命令安装：")
_add("pkg.install_all", "**한 번에 설치:**", "**Install all at once:**", "**一括インストール:**", "**一键安装：**")

# ── 🔰 초보자 설명(beginner mode) — 지표/차트 아래 쉬운 한 줄 해설 on/off ──
_add("nav.beginner_toggle",
     "🔰 초보자 설명", "🔰 Beginner hints", "🔰 初心者ガイド", "🔰 新手提示")
_add("nav.beginner_hint",
     "각 지표·차트 아래에 쉬운 한 줄 해설을 표시합니다. 통계에 익숙하면 꺼서 화면을 간결하게 유지하세요.",
     "Shows a plain one-line explanation under each metric and chart. Turn it off to keep the screen clean if you're comfortable with the stats.",
     "各指標・グラフの下にやさしい一行解説を表示します。統計に慣れていればオフにして画面をすっきり保てます。",
     "在每个指标和图表下方显示通俗的一行说明。若你熟悉统计，可关闭以保持界面简洁。")
_add("beginner.s2_metrics",
     "💡 µF1(사기)는 '사기를 놓치지 않으면서 정상을 사기로 잘못 몰지도 않는' 정도를 0~1로 나타낸 종합 점수예요(높을수록 좋음). 정확도는 99%가 정상인 데이터에선 '전부 정상'만 찍어도 높게 나와 변별력이 없어, 사기 탐지 성능은 µF1로 봅니다.",
     "💡 µF1 (fraud) is a 0–1 combined score of how well the model catches fraud without falsely flagging normal transactions (higher is better). Plain accuracy is misleading here: since 99% of transactions are normal, 'call everything normal' already scores high — so judge fraud performance by µF1.",
     "💡 µF1（不正）は、正常な取引を誤って不正としないまま不正をどれだけ捕捉できるかを0〜1で表す総合スコアです（高いほど良い）。正解率は99%が正常なデータでは「すべて正常」と答えても高く出て意味がないため、不正検知の性能はµF1で判断します。",
     "💡 µF1（欺诈）用0–1分综合衡量模型在不误报正常交易的前提下抓住欺诈的能力（越高越好）。由于99%的交易是正常的，只看准确率会失真（全判为正常也很高），因此欺诈检测性能要看µF1。")
_add("beginner.s2_cm",
     "💡 혼동행렬은 '실제 유형(세로) × 예측 유형(가로)' 표예요. 대각선은 맞힌 것, 대각선 밖 붉은 칸은 틀린 것(오탐·미탐)입니다. 특정 행에 붉은 칸이 몰리면 그 사기 유형을 자주 놓친다는 뜻이에요.",
     "💡 The confusion matrix is an 'actual type (rows) × predicted type (columns)' grid. The diagonal is correct; red off-diagonal cells are mistakes (false alarms / misses). Many red cells in one row means that fraud type is often missed.",
     "💡 混同行列は「実際の種類（縦）×予測した種類（横）」の表です。対角線が正解、対角線外の赤いセルが誤り（誤検知・見逃し）。ある行に赤が集中していれば、その不正種類をよく見逃しているサインです。",
     "💡 混淆矩阵是「实际类型（行）×预测类型（列）」的表格。对角线表示预测正确，对角线外的红色格为错误（误报/漏报）。某一行红格集中，说明该欺诈类型经常被漏掉。")

# ── 3-1: 임계값 → 비즈니스 언어 요약 (현재 임계값에서의 실측 건수 · 모집단 환산) ──
_add("s2.biz_readout",
     "💼 현재 임계값 {th}에서는 실제 사기 약 {caught}건을 잡고 {missed}건을 놓칩니다. 대신 정상 거래 약 {fp}건이 검토 대기열로 갑니다. (예상 총비용 약 {cost}원 · 모집단 환산)",
     "💼 At the current threshold {th}, you catch ~{caught} fraud cases and miss {missed}. In exchange, ~{fp} normal transactions go to the review queue. (Est. total cost ≈ {cost} KRW, population-scaled)",
     "💼 現在のしきい値 {th} では、実際の不正 約{caught}件を捕捉し {missed}件を見逃します。代わりに正常取引 約{fp}件が確認待ち行列に入ります。（推定総コスト 約{cost}ウォン・母集団換算）",
     "💼 在当前阈值 {th} 下，可抓住约 {caught} 笔欺诈，漏掉 {missed} 笔。代价是约 {fp} 笔正常交易进入复核队列。（预计总成本约 {cost} 韩元，按总体折算）")
_add("beginner.s2_cost",
     "💡 임계값을 낮출수록 사기를 더 많이 잡지만(미탐↓) 정상 거래도 더 많이 검토 대기열로 보내(오탐↑) 상담원 부담이 커져요. 높이면 그 반대. '총비용'이 가장 낮은 지점이 균형점입니다.",
     "💡 Lowering the threshold catches more fraud (fewer misses) but sends more normal transactions to review (more false alarms), raising analyst workload — and vice versa. The point where 'total cost' is lowest is the balance.",
     "💡 しきい値を下げるほど不正を多く捕捉できます（見逃し↓）が、正常取引も多く確認待ちに回り（誤検知↑）担当者の負担が増えます。逆も然り。『総コスト』が最も低い点が均衡点です。",
     "💡 阈值越低，抓到的欺诈越多（漏报↓），但也会把更多正常交易送去复核（误报↑），增加人工负担；反之亦然。'总成本'最低的点即为平衡点。")
_add("beginner.s3_intro",
     "💡 이 화면은 '어떤 상황에서 사기가 자주 나는지'를 보여줍니다. 채널·금액대·위험 플래그별로 정상 대비 사기 비율을 비교해, 어디를 집중 감시할지 감을 잡을 수 있어요.",
     "💡 This view shows where fraud tends to occur. It compares fraud vs. normal rates by channel, amount band, and risk flags, helping you see where to focus monitoring.",
     "💡 この画面は「どんな状況で不正が多いか」を示します。チャネル・金額帯・リスクフラグ別に正常と不正の割合を比較し、どこを重点監視すべきかの手がかりになります。",
     "💡 此视图展示欺诈易发生的场景。按渠道、金额区间和风险标记比较欺诈与正常的比例，帮助你判断应重点监控何处。")

# ── 3-5: 원클릭 인터랙티브 HTML 리포트 (배치) — 제목은 이메일 경로와 공유(notif.report_title_batch) ──
_add("s5.batch_report_dl",
     "🧾 리포트(HTML)", "🧾 Report (HTML)", "🧾 レポート(HTML)", "🧾 报告(HTML)")

# ── 🤖 AI 챗 (사이드바 도킹, 읽기 전용 v1) ──
_add("chat.toggle", "🤖 AI 챗", "🤖 AI chat", "🤖 AI チャット", "🤖 AI 聊天")
_add("chat.help",
     "현재 화면(지표·판정·배치)을 읽고 쉬운 말로 해설해 주는 도우미예요. 접으면 화면을 차지하지 않습니다.",
     "An assistant that reads the current screen (metrics, results, batch) and explains it in plain words. Collapse it to free up space.",
     "現在の画面(指標・判定・バッチ)を読み取り、やさしく解説するアシスタントです。閉じれば画面を占有しません。",
     "读取当前屏幕(指标、判定、批量)并用通俗语言讲解的助手。收起后不占用空间。")
_add("chat.input_ph",
     "이 화면에 대해 물어보세요…", "Ask about this screen…", "この画面について質問…", "询问关于此屏幕的问题…")
_add("chat.thinking", "생각 중…", "Thinking…", "考え中…", "思考中…")
_add("chat.clear", "🗑 대화 지우기", "🗑 Clear chat", "🗑 履歴を消去", "🗑 清除对话")
_add("chat.empty",
     "예: \"지금 이 화면이 뭘 보여줘?\", \"위험점수가 뭐야?\"",
     "e.g. \"What does this screen show?\", \"What is the risk score?\"",
     "例:「この画面は何を示している?」「リスクスコアとは?」",
     "例如：「这个屏幕显示什么?」「风险分数是什么?」")
_add("chat.pii_masked", "PII 마스킹 적용", "PII masked", "PII マスキング適用", "已应用 PII 脱敏")
_add("chat.pii_local", "로컬 전용(외부 전송 없음)", "local-only (no external send)",
     "ローカル専用(外部送信なし)", "仅本地(不外发)")
_add("chat.status", "프로바이더: {prov} · {pii}", "Provider: {prov} · {pii}",
     "プロバイダ: {prov} · {pii}", "提供方: {prov} · {pii}")
_add("chat.sys_editor", "⚙️ 프롬프트 편집", "⚙️ Edit prompt", "⚙️ プロンプト編集", "⚙️ 编辑提示词")
_add("chat.sys_editor_help",
     "챗봇의 시스템 지시문(역할·말투·규칙)을 여기서 바로 수정할 수 있어요. 저장하면 이 세션에 적용되고, 영구 기본값은 chat_agent.py의 _SYSTEM에서 바꿉니다.",
     "Edit the chatbot's system instruction (role, tone, rules) here. Saving applies it for this session; change the permanent default in _SYSTEM in chat_agent.py.",
     "チャットボットのシステム指示（役割・口調・ルール）をここで直接編集できます。保存でこのセッションに適用。恒久的な既定値は chat_agent.py の _SYSTEM で変更します。",
     "在此直接编辑聊天机器人的系统指令（角色、语气、规则）。保存后应用于本会话；永久默认值请在 chat_agent.py 的 _SYSTEM 中修改。")
_add("chat.sys_save", "💾 적용", "💾 Apply", "💾 適用", "💾 应用")
_add("chat.sys_reset", "↩ 기본값", "↩ Default", "↩ 既定値", "↩ 默认")
_add("chat.sys_active", "✏️ 편집한 프롬프트 적용 중", "✏️ Using edited prompt",
     "✏️ 編集済みプロンプト適用中", "✏️ 正在使用已编辑的提示词")
_add("chat.act_goto_session", "세션 {n}(으)로 이동했어요", "Moved to session {n}",
     "セッション{n}へ移動しました", "已切换到会话 {n}")
_add("chat.act_beginner_on", "초보자 설명을 켰어요", "Turned beginner hints on",
     "初心者ガイドをオンにしました", "已开启新手提示")
_add("chat.act_beginner_off", "초보자 설명을 껐어요", "Turned beginner hints off",
     "初心者ガイドをオフにしました", "已关闭新手提示")
_add("chat.act_goto_s5tab", "입력 방식을 '{tab}'(으)로 바꿨어요", "Switched input tab to '{tab}'",
     "入力方式を「{tab}」に切り替えました", "已切换输入方式为「{tab}」")
_add("chat.act_set_field", "{field} 값을 {value}(으)로 채웠어요", "Set {field} to {value}",
     "{field} を {value} に設定しました", "已将 {field} 设为 {value}")
_add("chat.act_run_detection", "직접입력 값으로 탐지를 실행했어요", "Ran detection with the manual input",
     "直接入力の値で検知を実行しました", "已用直接输入的值运行检测")
_add("chat.act_goto_batch_subtab", "배치 결과 탭을 '{tab}'(으)로 바꿨어요", "Switched batch tab to '{tab}'",
     "バッチ結果タブを「{tab}」に切り替えました", "已切换批量结果选项卡为「{tab}」")
_add("chat.act_set_flag", "플래그 '{flag}'을(를) {on} 했어요", "Set flag '{flag}' {on}",
     "フラグ「{flag}」を{on}にしました", "已将标记「{flag}」设为 {on}")
_add("chat.on", "켜기", "on", "オン", "开")
_add("chat.off", "끄기", "off", "オフ", "关")

# ── 🔰 초보자 힌트 전파 (세션 1·2·3·4·5) ──
_add("beginner.s1_dist",
     "💡 이 데이터는 정상 거래가 약 99%로 극도로 치우쳐 있어요(불균형). 그래서 사기(소수 클래스)를 얼마나 잡는지가 어렵고 중요한 과제예요 — 뒤의 µF1 지표가 이걸 측정합니다.",
     "💡 This data is extremely imbalanced — about 99% are normal transactions. That's what makes catching the rare fraud cases hard and important; the µF1 metric later measures exactly that.",
     "💡 このデータは正常取引が約99%と極端に偏っています（不均衡）。そのため少数派である不正をどれだけ捕捉できるかが難しく重要な課題です。後のµF1指標がこれを測ります。",
     "💡 该数据极度不平衡——约99%为正常交易。因此抓住少数的欺诈既难又关键；后面的µF1指标正是衡量这一点。")
_add("beginner.s2_classreport",
     "💡 정밀도(precision)는 '사기라고 한 것 중 진짜 비율', 재현율(recall)은 '실제 사기 중 잡아낸 비율'이에요. 정밀도↑=오탐 적음, 재현율↑=놓침 적음. 유형별로 어디가 약한지 이 표로 봅니다.",
     "💡 Precision is 'of those flagged as fraud, how many really were'; recall is 'of actual fraud, how many were caught'. Higher precision = fewer false alarms; higher recall = fewer misses. Use it to see which fraud types are weak.",
     "💡 適合率(precision)は「不正と判定したうち本当に不正だった割合」、再現率(recall)は「実際の不正のうち捕捉できた割合」です。適合率↑=誤検知が少ない、再現率↑=見逃しが少ない。どの種類が弱いかをこの表で確認します。",
     "💡 精确率(precision)是「判为欺诈中真正是欺诈的比例」，召回率(recall)是「实际欺诈中被抓到的比例」。精确率↑=误报少，召回率↑=漏报少。用它查看哪些欺诈类型较弱。")
_add("beginner.s3_flags",
     "💡 '플래그'는 각 거래에 붙는 위험 신호(예: 루팅 단말, VPN 사용, 인증정보 변경 등) 예/아니오 표시예요. 특정 플래그가 켜진 거래에서 사기 비율이 유독 높으면, 그 신호가 강한 탐지 단서라는 뜻입니다.",
     "💡 A 'flag' is a yes/no risk signal on each transaction (e.g., rooted device, VPN use, changed credentials). If fraud is much more common when a flag is on, that signal is a strong detection clue.",
     "💡 「フラグ」は各取引に付く危険信号（例：ルート化端末、VPN利用、認証情報の変更など）のはい/いいえ表示です。特定のフラグがオンの取引で不正率が突出して高ければ、その信号が強い検知手がかりになります。",
     "💡 「标记(flag)」是每笔交易上的是/否风险信号（如已root设备、使用VPN、更改凭证等）。若某标记为是时欺诈比例明显更高，说明该信号是很强的检测线索。")
_add("beginner.s4_intro",
     "💡 이 화면은 학습 데이터의 통계 분포를 흉내 낸 '가짜(합성) 거래'를 만들어, 실제 개인정보 없이 모델을 안전하게 테스트하는 곳이에요. 생성된 데이터가 원본 분포와 얼마나 닮았는지도 함께 확인합니다.",
     "💡 This screen creates fake (synthetic) transactions that mimic the training data's statistics, so you can test the model safely without real personal data. It also checks how closely the generated data resembles the original distribution.",
     "💡 この画面は学習データの統計分布を模した「偽(合成)取引」を生成し、実際の個人情報なしにモデルを安全にテストする場所です。生成データが元の分布にどれだけ近いかも併せて確認します。",
     "💡 此界面生成模仿训练数据统计分布的「假(合成)交易」，让你无需真实个人信息即可安全测试模型，并同时检查生成数据与原始分布的相似程度。")
_add("beginner.s5_result",
     "💡 위험점수는 '이 거래가 사기일 가능성'을 0~1로 나타낸 값이에요(=1−정상확률). 임계값을 넘으면 이상거래로 표시됩니다. 예측 유형은 어떤 사기 수법에 가장 가까운지를 뜻해요.",
     "💡 The risk score shows how likely this transaction is fraud, from 0 to 1 (= 1 − probability of normal). If it crosses the threshold, it's flagged as anomalous. The predicted type is which fraud pattern it most resembles.",
     "💡 リスクスコアは「この取引が不正である可能性」を0〜1で表した値です（=1−正常確率）。しきい値を超えると異常取引として表示されます。予測種別はどの不正手口に最も近いかを示します。",
     "💡 风险分数用0–1表示这笔交易是欺诈的可能性（=1−正常概率）。超过阈值即标记为异常。预测类型表示它最接近哪种欺诈手法。")
_add("beginner.s5_prob",
     "💡 아래 막대는 모델이 각 유형(a~m)에 매긴 확률이에요. 가장 높은 막대가 예측 유형이 되고, 'm'은 정상을 뜻합니다. 여러 유형에 확률이 분산돼 있으면 모델이 확신하지 못한다는 신호예요.",
     "💡 The bars below are the probability the model assigns to each type (a–m). The tallest bar becomes the predicted type, and 'm' means normal. Probability spread across many types signals the model is unsure.",
     "💡 下の棒はモデルが各種別(a〜m)に付けた確率です。最も高い棒が予測種別となり、'm'は正常を意味します。確率が多くの種別に分散していれば、モデルが確信を持てていない兆候です。",
     "💡 下方柱状是模型给每个类型(a–m)分配的概率。最高的柱即为预测类型，'m'表示正常。概率分散在多个类型上，说明模型不太确定。")

# ── 상단 네비게이션 ──
_add("nav.s1", "📋 프로젝트 개요", "📋 Project Overview", "📋 プロジェクト概要", "📋 项目概览")
_add("nav.s2", "📊 모델 성능", "📊 Model Performance", "📊 モデル性能", "📊 模型性能")
_add("nav.s3", "🔍 오탐·미탐 분석", "🔍 FP/FN Analysis", "🔍 誤検知・見逃し分析", "🔍 误报/漏报分析")
_add("nav.s4", "🧪 합성데이터 QA", "🧪 Synthetic Data QA", "🧪 合成データQA", "🧪 合成数据QA")
_add("nav.s5", "🚀 실시간 탐지 시연", "🚀 Live Detection Demo", "🚀 リアルタイム検知デモ", "🚀 实时检测演示")
_add("nav.brand_name", "FDS QA", "FDS QA", "FDS QA", "FDS QA")
_add("nav.brand_sub", "QA CONSOLE v7", "QA CONSOLE v7", "QA CONSOLE v7", "QA CONSOLE v7")
_add("nav.settings_help", "화면 설정", "Display settings", "画面設定", "显示设置")
_add("nav.settings_title", "🎛 화면 설정", "🎛 Display Settings", "🎛 画面設定", "🎛 显示设置")
_add("nav.settings_desc", "UI 모드와 테마를 바꿀 수 있습니다", "Switch UI mode and theme here", "UIモードとテーマを変更できます", "可在此切换UI模式与主题")
_add("nav.ui_mode_label", "UI 모드", "UI Mode", "UIモード", "UI模式")
_add("nav.ui_new", "✨ 신 UI", "✨ New UI", "✨ 新UI", "✨ 新版UI")
_add("nav.ui_old", "🕹 구 UI", "🕹 Classic UI", "🕹 旧UI", "🕹 旧版UI")
_add("nav.new_theme_label", "신 UI 테마 ({n}종)", "New UI Theme ({n} options)", "新UIテーマ（{n}種）", "新版UI主题（{n}种）")
_add("nav.new_theme_hint", "구 UI로 전환하면 클래식 테마 7종을 사이드바에서 고를 수 있습니다.", "Switch to Classic UI to choose from 7 classic themes in the sidebar.", "旧UIに切り替えると、サイドバーでクラシックテーマ7種を選択できます。", "切换到旧版UI后，可在侧边栏选择7种经典主题。")
_add("nav.old_theme_hint", "구 UI 테마 7종은 좌측 사이드바 🎨 테마 모드에서 변경합니다.", "Change the 7 Classic UI themes from 🎨 Theme Mode in the left sidebar.", "旧UIのテーマ7種は左側サイドバーの🎨テーマモードで変更します。", "旧版UI的7种主题可在左侧边栏的🎨主题模式中更改。")

# ── 사이드바 ──
_add("sb.lang_label", "🌐 언어", "🌐 Language", "🌐 言語", "🌐 语言")
_add("sb.title", "⚙ 운영 설정", "⚙ Operation Settings", "⚙ 運用設定", "⚙ 运行设置")
_add("sb.subtitle", "OPERATION PARAMETERS", "OPERATION PARAMETERS", "OPERATION PARAMETERS", "OPERATION PARAMETERS")
_add("sb.threshold_label", "위험점수 임계값", "Risk Score Threshold", "リスクスコア閾値", "风险评分阈值")
_add("sb.threshold_help", "이 값 이상이면 이상거래로 판정 (유형이 m이 아니면 점수와 무관하게 이상 판정)", "Transactions scoring at or above this value are flagged as anomalous (if type isn't 'm', it's flagged regardless of score)", "この値以上で異常取引と判定します（유形がmでなければスコアに関わらず異常と判定）", "达到或超过此值即判定为异常交易（若类型不是m，则不论分数如何都判定为异常）")
_add("sb.hist_recalc", "↳ 이력 {n}건 재계산: 🚨 {anom} · ✅ {normal}{flip}", "↳ Recalculated {n} history entries: 🚨 {anom} · ✅ {normal}{flip}", "↳ 履歴{n}件を再計算: 🚨 {anom} · ✅ {normal}{flip}", "↳ 重新计算了{n}条历史记录：🚨 {anom} · ✅ {normal}{flip}")
_add("sb.hist_flip", " · ⚠ 판정 변경 {n}건", " · ⚠ {n} verdict(s) changed", " · ⚠ 判定変更 {n}件", " · ⚠ {n} 条判定发生变化")
_add("sb.hist_no_change", " · 변경 없음", " · No change", " · 変更なし", " · 无变化")
_add("sb.rag_label", "RAG 문서 수", "RAG Document Count", "RAG文書数", "RAG文档数量")
_add("sb.model_section", "🧠 탐지 모델 (전역)", "🧠 Detection Model (Global)", "🧠 検知モデル（全体）", "🧠 检测模型（全局）")
_add("sb.model_select_label", "탐지 모델", "Detection Model", "検知モデル", "检测模型")
_add("sb.model_select_help", "세션 04(합성 QA)와 05(실시간 탐지)가 공용으로 사용하는 모델입니다", "This model is shared by Session 04 (Synthetic QA) and 05 (Live Detection)", "セッション04（合成QA）と05（リアルタイム検知）が共用するモデルです", "此模型由会话04（合成QA）与05（实时检测）共用")
_add("sb.model_loadable", "✓ 로드 가능", "✓ Loadable", "✓ ロード可能", "✓ 可加载")
_add("sb.model_missing", "✗ 파일 없음", "✗ File not found", "✗ ファイルなし", "✗ 文件不存在")
_add("sb.data_path_section", "📁 데이터 경로", "📁 Data Paths", "📁 データパス", "📁 数据路径")
_add("sb.model_status_title", "모델 상태", "Model Status", "モデル状態", "模型状态")
_add("sb.model_status_features", "{name} · 48 features", "{name} · 48 features", "{name} · 48 features", "{name} · 48 features")
_add("sb.theme_section", "🎨 테마 모드", "🎨 Theme Mode", "🎨 テーマモード", "🎨 主题模式")
_add("sb.theme_select_label", "테마 선택", "Select Theme", "テーマ選択", "选择主题")
_add("sb.os_detect_button", "🌗 OS 테마 자동 감지", "🌗 Auto-detect OS Theme", "🌗 OSテーマ自動検出", "🌗 自动检测系统主题")
_add("sb.os_detect_help", "운영체제의 다크/라이트 설정에 맞는 테마를 자동 선택합니다", "Automatically selects a theme matching your OS dark/light setting", "OSのダーク/ライト設定に合わせてテーマを自動選択します", "根据操作系统的深色/浅色设置自动选择主题")
_add("sb.api_key_expander", "🔑 API 키 설정 (선택 — .env보다 우선)", "🔑 API Key Settings (optional — overrides .env)", "🔑 APIキー設定（任意 — .envより優先）", "🔑 API密钥设置（可选，优先于.env）")
_add("sb.api_key_hint", "비워두면 .env 값을 사용합니다", "Leave blank to use the value from .env", "空欄の場合は.envの値を使用します", "留空则使用.env中的值")
_add("sb.notify_section", "알림 설정", "Notification Settings", "通知設定", "通知设置")
_add("sb.custom_key_help", "커스텀 제공자의 URL·모델명은 세션 05 ⚙️ 탐지 환경 설정에서 입력합니다", "Enter the custom provider's URL and model name in Session 05 ⚙️ Detection Environment Settings", "カスタムプロバイダーのURL・モデル名はセッション05 ⚙️ 検知環境設定で入力します", "自定义提供商的URL和模型名称请在会话05 ⚙️ 检测环境设置中输入")

# ── 공통 ──
_add("common.normal", "정상", "Normal", "正常", "正常")
_add("common.fraud", "사기", "Fraud", "不正", "欺诈")
_add("common.none", "없음", "None", "なし", "无")
_add("common.change_model_hint", "변경: 좌측 사이드바 › 탐지 모델", "Change in the left sidebar › Detection Model", "変更: 左サイドバー › 検知モデル", "更改：左侧边栏 › 检测模型")

# ── 세션 01 ──
_add("s1.title_main", "이상거래탐지 모델", "Fraud Detection Model", "不正取引検知モデル", "异常交易检测模型")
_add("s1.title_span", "QA 검증", "QA Validation", "QA検証", "QA验证")
_add("s1.title_sub", "FRAUD DETECTION SYSTEM · KOREAN ELECTRONIC FINANCE · 13-CLASS MULTICLASSIFICATION", "FRAUD DETECTION SYSTEM · KOREAN ELECTRONIC FINANCE · 13-CLASS MULTICLASSIFICATION", "FRAUD DETECTION SYSTEM · KOREAN ELECTRONIC FINANCE · 13-CLASS MULTICLASSIFICATION", "FRAUD DETECTION SYSTEM · KOREAN ELECTRONIC FINANCE · 13-CLASS MULTICLASSIFICATION")
_add("s1.kpi_total_label", "총 거래 수", "Total Transactions", "総取引数", "总交易数")
_add("s1.kpi_total_unit", "건", "txns", "件", "笔")
_add("s1.kpi_normal_label", "정상 비율", "Normal Ratio", "正常比率", "正常占比")
_add("s1.kpi_normal_unit", "클래스 m", "Class m", "クラスm", "类别m")
_add("s1.kpi_fraud_label", "사기 유형", "Fraud Types", "不正類型", "欺诈类型")
_add("s1.kpi_fraud_val", "12종", "12 types", "12種", "12种")
_add("s1.kpi_fraud_unit", "a ~ l", "a – l", "a〜l", "a～l")
_add("s1.kpi_feat_label", "전체 피처", "Total Features", "全特徴量", "全部特征")
_add("s1.kpi_feat_val", "64개", "64", "64個", "64个")
_add("s1.kpi_feat_unit", "학습 48개 사용", "48 used for training", "学習に48個使用", "训练中使用48个")
_add("s1.kpi_period_label", "데이터 기간", "Data Split", "データ期間", "数据周期")
_add("s1.kpi_period_val", "시간 분할", "Time-based", "時系列分割", "按时间划分")
_add("s1.kpi_period_unit", "80/20 split", "80/20 split", "80/20 split", "80/20 split")
_add("s1.why_title", "프로젝트 목적", "Project Purpose", "プロジェクトの目的", "项目目的")
_add("s1.why_body", "실제 운영 환경에서 <b>정상 거래를 과도하게 차단하지 않으면서 위험 거래를 놓치지 않는</b> 신뢰 가능한 탐지 시스템을 QA 관점에서 검증합니다.<br><br>오탐(FP) · 미탐(FN) · 유형 오분류 · 임계값 분석을 통해 운영 리스크를 정량화하고, 이상거래 발생 시 <b>탐지 → AI 해석 → 알림 자동화</b>까지 이어지는 파이프라인을 시연합니다.",
     "From a QA perspective, we validate a reliable detection system that, in a real production environment, <b>doesn't over-block legitimate transactions while never missing risky ones</b>.<br><br>Through false-positive (FP), false-negative (FN), misclassification, and threshold analysis, we quantify operational risk, and demonstrate the full pipeline from <b>detection → AI interpretation → automated notification</b> when an anomaly occurs.",
     "実運用環境において<b>正常な取引を過度にブロックせず、危険な取引も見逃さない</b>信頼性の高い検知システムをQAの観点から検証します。<br><br>誤検知（FP）・見逃し（FN）・類型誤分類・閾値分析を通じて運用リスクを定量化し、異常取引発生時に<b>検知→AI解釈→通知自動化</b>まで続くパイプラインを実演します。",
     "从QA角度验证一个在真实生产环境中<b>既不过度拦截正常交易、又不会漏掉风险交易</b>的可靠检测系统。<br><br>通过误报(FP)、漏报(FN)、类型误判及阈值分析对运营风险进行量化，并演示从<b>检测 → AI解读 → 通知自动化</b>的完整流程。")
_add("s1.hyp_title", "핵심 가설", "Key Hypotheses", "主要仮説", "核心假设")
_add("s1.fraud_dict_title", "사기 유형 사전", "Fraud Type Reference", "不正類型辞典", "欺诈类型词典")
_add("s1.fraud_dict_hint", "각 유형을 펼쳐 RAG 기반 상세 해설과 주요 탐지 지표를 확인하세요.", "Expand each type to see RAG-based detailed explanations and key detection indicators.", "各類型を展開してRAGベースの詳細解説と主要検知指標を確認してください。", "展开各类型可查看基于RAG的详细说明及主要检测指标。")
_add("s1.data_dist_title", "데이터 분포", "Data Distribution", "データ分布", "数据分布")
_add("s1.chart_all_title", "Fraud_Type 전체 분포 (정상 포함)", "Full Fraud_Type Distribution (incl. Normal)", "Fraud_Type全体分布（正常含む）", "Fraud_Type 全体分布（含正常）")
_add("s1.chart_zoom_title", "사기 유형 확대 분포", "Fraud Type Distribution (Zoomed)", "不正類型 拡大分布", "欺诈类型放大分布")
_add("s1.chart_detail_title", "사기 유형 A~L 건수 상세", "Fraud Type A–L Count Detail", "不正類型A〜L 件数詳細", "欺诈类型A～L数量明细")
_add("s1.avg_annotation", "평균 {n}건", "avg {n}", "平均{n}件", "平均{n}笔")
_add("s1.table_title", "유형별 건수 상세", "Count Detail by Type", "類型別件数詳細", "各类型数量明细")
_add("s1.th_type", "유형", "Type", "類型", "类型")
_add("s1.th_desc", "설명", "Description", "説明", "说明")
_add("s1.th_count", "건수", "Count", "件数", "数量")
_add("s1.th_ratio", "비율", "Ratio", "比率", "占比")
_add("s1.th_rel_ratio", "상대 비율", "Relative Ratio", "相対比率", "相对比率")

# ── 세션 02 ──
_add("s2.title_main", "모델", "Model", "モデル", "模型")
_add("s2.title_span", "성능 분석", "Performance Analysis", "性能分析", "性能分析")
_add("s2.no_eval_warn", "⚠ models/eval_result.json 없음. 모델 학습 후 재실행하세요.", "⚠ models/eval_result.json not found. Train the model and re-run.", "⚠ models/eval_result.json が見つかりません。モデルを学習後に再実行してください。", "⚠ 未找到 models/eval_result.json。请训练模型后重新运行。")
_add("s2.compare_title", "모델 비교", "Model Comparison", "モデル比較", "模型对比")
_add("s2.class_report_title", "클래스별 Precision · Recall · F1", "Precision · Recall · F1 by Class", "クラス別 Precision・Recall・F1", "各类别 Precision · Recall · F1")
_add("s2.confusion_title", "13 × 13 혼동 행렬", "13 × 13 Confusion Matrix", "13×13 混同行列", "13 × 13 混淆矩阵")
_add("s2.pred_axis", "예측 유형 (Predicted)", "Predicted Type", "予測類型（Predicted）", "预测类型（Predicted）")
_add("s2.actual_axis", "실제 유형 (Actual)", "Actual Type", "実際類型（Actual）", "实际类型（Actual）")
_add("s2.count_axis", "건수", "Count", "件数", "数量")
_add("s2.threshold_title", "임계값 기대비용 분석", "Threshold Expected-Cost Analysis", "閾値期待コスト分析", "阈值期望成本分析")
_add("s2.fn_cost", "미탐(FN) 비용", "FN (Miss) Cost", "見逃し（FN）コスト", "漏报(FN)成本")
_add("s2.fp_cost", "오탐(FP) 비용", "FP (False Alarm) Cost", "誤検知（FP）コスト", "误报(FP)成本")
_add("s2.total_cost", "총 기대비용", "Total Expected Cost", "総期待コスト", "总期望成本")
_add("s2.current_annotation", "현재 {th}", "current {th}", "現在 {th}", "当前 {th}")
_add("s2.threshold_axis", "임계값", "Threshold", "閾値", "阈值")
_add("s2.cost_axis", "기대비용 (임의 단위)", "Expected Cost (arb. unit)", "期待コスト（任意単位）", "期望成本（任意单位）")

# ── 세션 03 ──
_add("s3.title_main", "오탐·미탐", "FP/FN", "誤検知・見逃し", "误报/漏报")
_add("s3.title_span", "세그먼트 분석", "Segment Analysis", "セグメント分析", "分段分析")
_add("s3.info_note", "팀원 모델의 예측 결과(y_pred, y_true) 연동 시 실시간 갱신됩니다. 현재는 원본 데이터 기준 분포를 표시합니다.", "This updates live once linked to your team's model predictions (y_pred, y_true). Currently showing distribution based on raw data.", "チームモデルの予測結果（y_pred, y_true）連携時にリアルタイム更新されます。現在は元データ基準の分布を表示しています。", "接入团队模型的预测结果（y_pred、y_true）后将实时更新。当前显示的是基于原始数据的分布。")
_add("s3.no_train_warn", "⚠ train.csv 없음", "⚠ train.csv not found", "⚠ train.csv が見つかりません", "⚠ 未找到 train.csv")
_add("s3.seg_title", "세그먼트별 사기 분포", "Fraud Distribution by Segment", "セグメント別 不正分布", "各分段的欺诈分布")
_add("s3.seg_select_label", "세그먼트 기준 선택", "Select Segment Criterion", "セグメント基準選択", "选择分段依据")
_add("s3.amount_title", "거래금액대별 사기 밀도", "Fraud Density by Amount Band", "取引金額帯別 不正密度", "各交易金额区间的欺诈密度")
_add("s3.amt_bin1", "대규모출금", "Large Withdrawal", "大口出金", "大额取款")
_add("s3.amt_bin2", "소규모출금", "Small Withdrawal", "小口出金", "小额取款")
_add("s3.amt_bin3", "소규모입금", "Small Deposit", "小口入金", "小额存款")
_add("s3.amt_bin4", "중규모입금", "Medium Deposit", "中口入金", "中额存款")
_add("s3.amt_bin5", "대규모입금", "Large Deposit", "大口入金", "大额存款")
_add("s3.amt_col", "금액대", "Amount Band", "金額帯", "金额区间")
_add("s3.cat_col", "구분", "Category", "区分", "类别")
_add("s3.flag_title", "위험 플래그 ON 비율 (사기 vs 정상)", "Risk Flag ON Ratio (Fraud vs Normal)", "リスクフラグON比率（不正 vs 正常）", "风险标志开启比例（欺诈 vs 正常）")
_add("s3.flag_col", "플래그", "Flag", "フラグ", "标志")
_add("s3.ratio_axis", "비율 (%)", "Ratio (%)", "比率（%）", "比例（%）")

# ── 세션 04 ──
_add("s4.title_main", "합성데이터", "Synthetic Data", "合成データ", "合成数据")
_add("s4.title_span", "QA 검증", "QA Validation", "QA検証", "QA验证")
_add("s4.model_title", "검증 대상 모델", "Model Under Validation", "検証対象モデル", "验证对象模型")
_add("s4.gen_settings_title", "생성 설정", "Generation Settings", "生成設定", "生成设置")
_add("s4.gen_count_label", "생성 건수", "Rows to Generate", "生成件数", "生成数量")
_add("s4.target_type_label", "목표 사기 유형", "Target Fraud Type", "目標不正類型", "目标欺诈类型")
_add("s4.seed_label", "랜덤 시드", "Random Seed", "乱数シード", "随机种子")
_add("s4.seed_help", "-1 = 자동 랜덤", "-1 = auto-random", "-1 = 自動ランダム", "-1 = 自动随机")
_add("s5.seed_label", "랜덤 시드", "Random Seed", "乱数シード", "随机种子")
_add("s5.seed_help", "-1 = 자동 랜덤", "-1 = auto-random", "-1 = 自動ランダム", "-1 = 自动随机")
_add("s4.gen_button", "🎲 생성", "🎲 Generate", "🎲 生成", "🎲 生成")
_add("s4.gen_spinner", "합성 데이터 생성 중...", "Generating synthetic data...", "合成データ生成中...", "正在生成合成数据...")
_add("s4.gen_success", "✅ {n}건 생성 완료", "✅ {n} row(s) generated", "✅ {n}件生成完了", "✅ 已生成 {n} 条")
_add("s4.gen_fail", "❌ 생성 실패: {e}", "❌ Generation failed: {e}", "❌ 生成失敗: {e}", "❌ 生成失败：{e}")
_add("s4.pass_title", "적합성 검증", "Validity Check", "適合性検証", "有效性验证")
_add("s4.check_amount", "이체 금액", "Transfer Amount", "振込金額", "转账金额")
_add("s4.check_distance", "거래 거리", "Transaction Distance", "取引距離", "交易距离")
_add("s4.check_balance", "계좌 잔액", "Account Balance", "口座残高", "账户余额")
_add("s4.th_item", "항목", "Item", "項目", "项目")
_add("s4.th_column", "컬럼", "Column", "カラム", "列")
_add("s4.th_range", "기준 범위", "Reference Range", "基準範囲", "参考范围")
_add("s4.th_syn_range", "합성 범위", "Synthetic Range", "合成範囲", "合成范围")
_add("s4.th_in_range", "범위 내 비율", "In-Range Ratio", "範囲内比率", "范围内比例")
_add("s4.th_result", "결과", "Result", "結果", "结果")
_add("s4.pass_badge", "✓ PASS", "✓ PASS", "✓ PASS", "✓ PASS")
_add("s4.fail_badge", "✗ FAIL", "✗ FAIL", "✗ FAIL", "✗ FAIL")
_add("s4.dist_title", "분포 비교 (합성 vs 원본)", "Distribution Comparison (Synthetic vs Original)", "分布比較（合成 vs 元データ）", "分布对比（合成 vs 原始）")
_add("s4.cmp_col_label", "비교 컬럼", "Comparison Column", "比較カラム", "对比列")
_add("s4.legend_original", "원본", "Original", "元データ", "原始")
_add("s4.legend_synthetic", "합성", "Synthetic", "合成", "合成")
_add("s4.preview_title", "생성 데이터 미리보기", "Generated Data Preview", "生成データプレビュー", "生成数据预览")
_add("s4.preview_badge", "{n}건", "{n} rows", "{n}件", "{n} 条")

# ── 세션 05 ──
_add("s5.title_main", "실시간 탐지", "Live Detection", "リアルタイム検知", "实时检测")
_add("s5.title_span", "시연", "Demo", "デモ", "演示")
_add("s5.env_expander", "⚙️ 탐지 환경 설정 — LLM · 자동발송 · 마스킹 · 연결 테스트 · 모델 선택", "⚙️ Detection Environment — LLM · Auto-notify · Masking · Connection Test · Model", "⚙️ 検知環境設定 — LLM・自動送信・マスキング・接続テスト・モデル選択", "⚙️ 检测环境设置 — LLM · 自动发送 · 脱敏 · 连接测试 · 模型选择")
_add("s5.llm_config_title", "AI 분석 설정", "AI Analysis Settings", "AI分析設定", "AI分析设置")
_add("s5.llm_provider_label", "LLM 제공자", "LLM Provider", "LLMプロバイダー", "LLM提供商")
_add("s5.llm_p_local", "🖥 로컬 (llama.cpp)", "🖥 Local (llama.cpp)", "🖥 ローカル（llama.cpp）", "🖥 本地（llama.cpp）")
_add("s5.llm_p_anthropic", "☁ Anthropic", "☁ Anthropic", "☁ Anthropic", "☁ Anthropic")
_add("s5.llm_p_openai", "☁ OpenAI", "☁ OpenAI", "☁ OpenAI", "☁ OpenAI")
_add("s5.llm_p_deepseek", "☁ DeepSeek", "☁ DeepSeek", "☁ DeepSeek", "☁ DeepSeek")
_add("s5.llm_p_moonshot", "☁ Moonshot", "☁ Moonshot", "☁ Moonshot", "☁ Moonshot")
_add("s5.llm_p_custom", "🌐 커스텀 (OpenRouter 등)", "🌐 Custom (OpenRouter, etc.)", "🌐 カスタム（OpenRouter等）", "🌐 自定义（OpenRouter 等）")
_add("s5.llm_p_fallback", "⚡ LLM 사용 안함 (폴백)", "⚡ No LLM (fallback)", "⚡ LLM不使用（フォールバック）", "⚡ 不使用LLM（回退）")
_add("s5.llm_provider_help", "custom = OpenAI 호환 API라면 무엇이든 연결 가능 (OpenRouter, Together, Groq, vLLM, LM Studio 등). fallback = LLM 호출 없이 규칙 기반 메시지 생성", "custom = connect any OpenAI-compatible API (OpenRouter, Together, Groq, vLLM, LM Studio, etc). fallback = rule-based message generation without any LLM call", "custom = OpenAI互換APIであれば何でも接続可能（OpenRouter、Together、Groq、vLLM、LM Studio等）。fallback = LLM呼び出しなしでルールベースのメッセージを生成", "custom = 可连接任何兼容OpenAI的API（OpenRouter、Together、Groq、vLLM、LM Studio 等）。fallback = 不调用LLM，基于规则生成消息")
_add("s5.api_mode_label", "API 모드", "API Mode", "APIモード", "API模式")
_add("s5.api_mode_local", "로컬 서버 (llama.cpp)", "Local Server (llama.cpp)", "ローカルサーバー（llama.cpp）", "本地服务器（llama.cpp）")
_add("s5.api_mode_cloud", "클라우드 API", "Cloud API", "クラウドAPI", "云端API")
_add("s5.cloud_note", "💡 클라우드 API 사용 시 <code>.env</code> 파일에 API 키를 설정하세요. 현재 선택: <b>{p}</b>", "💡 When using a cloud API, set the API key in your <code>.env</code> file. Currently selected: <b>{p}</b>", "💡 クラウドAPI使用時は<code>.env</code>ファイルにAPIキーを設定してください。現在の選択: <b>{p}</b>", "💡 使用云端API时，请在 <code>.env</code> 文件中设置API密钥。当前选择：<b>{p}</b>")
_add("s5.local_note", "⚡ 로컬 서버 모드 — <code>llama.cpp</code> 서버가 실행 중이어야 합니다.", "⚡ Local server mode — the <code>llama.cpp</code> server must be running.", "⚡ ローカルサーバーモード — <code>llama.cpp</code>サーバーが起動している必要があります。", "⚡ 本地服务器模式 — 需要 <code>llama.cpp</code> 服务器正在运行。")
_add("s5.custom_url_label", "Base URL (chat/completions 전체 경로)", "Base URL (full chat/completions path)", "Base URL（chat/completionsの完全パス）", "Base URL（chat/completions 完整路径）")
_add("s5.custom_url_help", "OpenAI 호환 chat/completions 엔드포인트의 전체 URL입니다. 비워두면 .env의 CUSTOM_LLM_URL, 그것도 없으면 OpenRouter 기본값을 사용합니다.", "The full URL of an OpenAI-compatible chat/completions endpoint. If blank, falls back to CUSTOM_LLM_URL in .env, then the OpenRouter default.", "OpenAI互換chat/completionsエンドポイントの完全URLです。空欄の場合は.envのCUSTOM_LLM_URL、それもなければOpenRouterのデフォルト値を使用します。", "OpenAI兼容 chat/completions 端点的完整URL。留空则使用.env中的CUSTOM_LLM_URL，若也没有则使用OpenRouter默认值。")
_add("s5.custom_model_label", "모델명", "Model Name", "モデル名", "模型名称")
_add("s5.custom_model_help", "제공자의 모델 식별자입니다 (OpenRouter는 'vendor/model' 형식). 비워두면 .env의 CUSTOM_LLM_MODEL 사용.", "The provider's model identifier (OpenRouter uses the 'vendor/model' format). If blank, uses CUSTOM_LLM_MODEL from .env.", "プロバイダーのモデル識別子です（OpenRouterは'vendor/model'形式）。空欄の場合は.envのCUSTOM_LLM_MODELを使用。", "提供商的模型标识符（OpenRouter使用'vendor/model'格式）。留空则使用.env中的CUSTOM_LLM_MODEL。")
_add("s5.custom_key_label", "API Key", "API Key", "APIキー", "API密钥")
_add("s5.custom_key_help", "비워두면 .env의 CUSTOM_LLM_API_KEY 사용.", "If blank, uses CUSTOM_LLM_API_KEY from .env.", "空欄の場合は.envのCUSTOM_LLM_API_KEYを使用。", "留空则使用.env中的CUSTOM_LLM_API_KEY。")
_add("s5.conn_test_button", "🔌 연결 테스트", "🔌 Connection Test", "🔌 接続テスト", "🔌 连接测试")
_add("s5.conn_test_spinner", "연결 테스트 중...", "Testing connection...", "接続テスト中...", "正在测试连接...")
_add("s5.conn_test_error", "테스트 실행 오류: {e}", "Test execution error: {e}", "テスト実行エラー: {e}", "测试执行出错：{e}")
_add("s5.conn_test_desc", "간단한 프롬프트로 LLM 연결 상태를 확인합니다. 실패 시 에러 사유가 표시됩니다.", "Checks LLM connectivity with a simple prompt. If it fails, the error reason is shown.", "簡単なプロンプトでLLM接続状態を確認します。失敗時はエラー理由が表示されます。", "使用简单提示词检查LLM连接状态。失败时会显示错误原因。")
_add("s5.auto_notify_title", "자동 발송 설정", "Auto-notify Settings", "自動送信設定", "自动发送设置")
_add("s5.slack_toggle", "🔔 Slack 자동발송", "🔔 Auto-send to Slack", "🔔 Slack自動送信", "🔔 自动发送到Slack")
_add("s5.email_toggle", "📧 이메일 자동발송", "📧 Auto-send Email", "📧 メール自動送信", "📧 自动发送邮件")
_add("s5.recipient_label", "📮 수신자 이메일", "📮 Recipient Email", "📮 受信者メール", "📮 收件人邮箱")
_add("s5.recipient_help", "이상거래 알림 이메일을 받을 주소입니다. 자동발송과 수동발송 모두 이 주소를 사용하며, 비워두면 .env의 FDS_NOTIFY_EMAIL을 사용합니다.", "The address that receives anomaly alert emails. Used for both auto- and manual-send; if blank, uses FDS_NOTIFY_EMAIL from .env.", "異常取引通知メールを受け取るアドレスです。自動送信・手動送信ともにこのアドレスを使用し、空欄の場合は.envのFDS_NOTIFY_EMAILを使用します。", "接收异常交易通知邮件的地址。自动发送与手动发送均使用此地址，留空则使用.env中的FDS_NOTIFY_EMAIL。")
_add("s5.auto_notify_desc", "이상거래 탐지 시 자동으로 알림을 발송합니다 · 이메일은 좌측 <b>수신자 이메일</b> 주소로 전송됩니다 (비워두면 .env의 FDS_NOTIFY_EMAIL)", "Automatically sends alerts when anomalies are detected · Emails go to the <b>Recipient Email</b> address on the left (if blank, uses FDS_NOTIFY_EMAIL from .env)", "異常取引検知時に自動で通知を送信します・メールは左側の<b>受信者メール</b>アドレスに送信されます（空欄の場合は.envのFDS_NOTIFY_EMAIL）", "检测到异常交易时自动发送通知 · 邮件将发送至左侧的<b>收件人邮箱</b>地址（留空则使用.env中的FDS_NOTIFY_EMAIL）")
_add("s5.pii_title", "개인정보 마스킹", "PII Masking", "個人情報マスキング", "个人信息脱敏")
_add("s5.pii_off", "🔓 OFF", "🔓 OFF", "🔓 OFF", "🔓 OFF")
_add("s5.pii_basic", "🟡 기본", "🟡 Basic", "🟡 基本", "🟡 基础")
_add("s5.pii_standard", "🟠 표준", "🟠 Standard", "🟠 標準", "🟠 标准")
_add("s5.pii_strict", "🔴 강화", "🔴 Strict", "🔴 強化", "🔴 强化")
_add("s5.pii_level_label", "마스킹 레벨", "Masking Level", "マスキングレベル", "脱敏级别")
_add("s5.pii_skip_local_label", "로컬 LLM은 스킵", "Skip for local LLM", "ローカルLLMはスキップ", "本地LLM跳过")
_add("s5.pii_skip_local_help", "로컬 llama.cpp는 데이터가 외부로 전송되지 않으므로 마스킹 불필요", "Local llama.cpp doesn't send data externally, so masking is unnecessary", "ローカルllama.cppはデータが外部に送信されないためマスキング不要", "本地llama.cpp不会将数据发送到外部，因此无需脱敏")
_add("s5.pii_desc_off", "마스킹 없음 — 원본 그대로 전달", "No masking — data passed through as-is", "マスキングなし — 元データのまま送信", "无脱敏 — 原样传递数据")
_add("s5.pii_desc_basic", "이름·식별번호·거래ID만 마스킹", "Masks only name, ID number, and transaction ID", "氏名・識別番号・取引IDのみマスキング", "仅对姓名、身份编号、交易ID进行脱敏")
_add("s5.pii_desc_standard", "이름·식별번호 + IP·위치·계좌 마스킹 (권장)", "Masks name, ID number + IP, location, account (recommended)", "氏名・識別番号 + IP・位置・口座マスキング（推奨）", "对姓名、身份编号 + IP、位置、账户进行脱敏（推荐）")
_add("s5.pii_desc_strict", "전체 마스킹 + 생년·시간 일반화", "Full masking + birth year/time generalization", "全体マスキング + 生年・時刻の一般化", "全面脱敏 + 出生年份/时间泛化")
_add("s5.pii_effective_off", "OFF (로컬 LLM 스킵 활성)", "OFF (local LLM skip active)", "OFF（ローカルLLMスキップ有効）", "OFF（本地LLM跳过已启用）")
_add("s5.conn_status_title", "연결 상태 확인", "Connection Status Check", "接続状態確認", "连接状态检查")
_add("s5.test_ml_button", "🧪 ML 모델 테스트", "🧪 Test ML Model", "🧪 MLモデルテスト", "🧪 测试ML模型")
_add("s5.test_ml_ok", "✅ ML 모델 로드 성공", "✅ ML model loaded successfully", "✅ MLモデルのロードに成功", "✅ ML模型加载成功")
_add("s5.test_ml_fail", "❌ ML 모델 실패: {e}", "❌ ML model failed: {e}", "❌ MLモデル失敗: {e}", "❌ ML模型失败：{e}")
_add("s5.test_rag_button", "🧪 RAG 테스트", "🧪 Test RAG", "🧪 RAGテスト", "🧪 测试RAG")
_add("s5.test_rag_query", "테스트 쿼리", "test query", "テストクエリ", "测试查询")
_add("s5.test_rag_ok", "✅ RAG 연결 성공 ({n})", "✅ RAG connected successfully ({n})", "✅ RAG接続成功（{n}）", "✅ RAG连接成功（{n}）")
_add("s5.test_rag_fail", "❌ RAG 실패: {e}", "❌ RAG failed: {e}", "❌ RAG失敗: {e}", "❌ RAG失败：{e}")
_add("s5.test_llm_button", "🧪 LLM 테스트", "🧪 Test LLM", "🧪 LLMテスト", "🧪 测试LLM")
_add("s5.test_llm_query", "테스트", "test", "テスト", "测试")
_add("s5.test_llm_ok", "✅ LLM 응답 성공 (반환 타입: {t})", "✅ LLM responded successfully (return type: {t})", "✅ LLM応答成功（戻り値の型: {t}）", "✅ LLM响应成功（返回类型：{t}）")
_add("s5.test_llm_fail", "❌ LLM 실패: {e}", "❌ LLM failed: {e}", "❌ LLM失敗: {e}", "❌ LLM失败：{e}")
_add("s5.test_notify_button", "🧪 알림 테스트", "🧪 Test Notifier", "🧪 通知テスト", "🧪 测试通知")
_add("s5.test_notify_ok", "✅ Notifier 초기화 성공", "✅ Notifier initialized successfully", "✅ Notifier初期化成功", "✅ Notifier初始化成功")
_add("s5.test_notify_fail", "❌ Notifier 실패: {e}", "❌ Notifier failed: {e}", "❌ Notifier失敗: {e}", "❌ Notifier失败：{e}")
_add("s5.model_section_title", "탐지 모델", "Detection Model", "検知モデル", "检测模型")
_add("s5.input_mode_title", "입력 방식 선택", "Select Input Mode", "入力方式選択", "选择输入方式")
_add("s5.ai_include_toggle", "🤖 AI 분석 포함", "🤖 Include AI Analysis", "🤖 AI分析を含める", "🤖 包含AI分析")
_add("s5.ai_include_help", "OFF = ML 탐지만 (즉시), ON = ML + AI 분석 (30초~2분)", "OFF = ML detection only (instant), ON = ML + AI analysis (30s–2min)", "OFF = ML検知のみ（即時）、ON = ML＋AI分析（30秒〜2分）", "OFF = 仅ML检测（即时），ON = ML + AI分析（30秒～2分钟）")
_add("s5.ai_include_on_desc", "탐지 실행 시 ML 분류 → AI 3단계 분석(분석·Slack·Email) 자동 실행 | 제공자: <b>{p}</b>", "Running detection auto-triggers ML classification → AI 3-step analysis (Analysis · Slack · Email) | Provider: <b>{p}</b>", "検知実行時にML分類→AI3段階分析（分析・Slack・Email）を自動実行 | プロバイダー: <b>{p}</b>", "运行检测时自动执行ML分类 → AI三阶段分析（分析·Slack·Email）| 提供商：<b>{p}</b>")
_add("s5.ai_include_off_desc", "탐지 실행 시 ML 분류만 즉시 실행 (~1초) | 결과 화면에서 AI 분석 버튼으로 추가 가능", "Running detection executes only ML classification instantly (~1s) | AI analysis can be added later via the button on the results screen", "検知実行時にML分類のみ即時実行（〜1秒）| 結果画面のAI分析ボタンで追加可能", "运行检测时仅立即执行ML分类（约1秒）| 可在结果页面通过AI分析按钮追加分析")
_add("s5.tab1", "✏️ 직접 입력", "✏️ Manual Input", "✏️ 手動入力", "✏️ 手动输入")
_add("s5.tab2", "📂 test.csv", "📂 test.csv", "📂 test.csv", "📂 test.csv")
_add("s5.tab3", "📊 train.csv", "📊 train.csv", "📊 train.csv", "📊 train.csv")
_add("s5.tab4", "🧪 합성 생성", "🧪 Synthetic Gen", "🧪 合成生成", "🧪 合成生成")
_add("s5.tab5", "📁 폴더 배치", "📁 Folder Batch", "📁 フォルダ一括", "📁 文件夹批处理")
_add("s5.autofill_button", "⚡ 고위험 시나리오 자동입력", "⚡ Auto-fill High-Risk Scenario", "⚡ 高リスクシナリオ自動入力", "⚡ 自动填充高风险场景")
_add("s5.section_txn_info", "거래 정보", "Transaction Info", "取引情報", "交易信息")
_add("s5.section_env_info", "환경 정보", "Environment Info", "環境情報", "环境信息")
_add("s5.section_risk_flags", "🚩 위험 플래그", "🚩 Risk Flags", "🚩 リスクフラグ", "🚩 风险标志")
_add("s5.amount_label", "거래 금액 (원)", "Transaction Amount (KRW)", "取引金額（ウォン）", "交易金额（韩元）")
_add("s5.amount_help", "이체·입출금 금액입니다. 음수는 출금(계좌에서 나가는) 방향, 양수는 입금 방향 거래를 의미합니다. 고액일수록, 평소 패턴과 다를수록 위험 가중.", "The transfer/deposit-withdrawal amount. Negative means withdrawal (money leaving the account), positive means deposit. Risk increases with larger amounts and greater deviation from usual patterns.", "振込・入出金金額です。マイナスは出金（口座から出ていく）方向、プラスは入金方向の取引を意味します。高額であるほど、普段のパターンと異なるほどリスクが増加します。", "转账/存取款金额。负数表示取款（资金流出账户）方向，正数表示存款方向。金额越大、与平时模式差异越大，风险权重越高。")
_add("s5.distance_label", "거래 거리 (km)", "Transaction Distance (km)", "取引距離（km）", "交易距离（公里）")
_add("s5.distance_help", "고객의 평소 활동 지역(등록 주소·최근 거래 위치)과 이번 거래 발생 지점 간 거리입니다. 값이 클수록 위치 이상(원격지 접속) 가능성이 높습니다.", "The distance between the customer's usual activity area (registered address / recent transaction location) and this transaction's location. Larger values suggest a higher chance of location anomaly (remote access).", "顧客の普段の活動地域（登録住所・最近の取引位置）と今回の取引発生地点との距離です。値が大きいほど位置異常（遠隔地アクセス）の可能性が高まります。", "客户日常活动区域（注册地址/近期交易位置）与本次交易发生地点之间的距离。数值越大，位置异常（远程访问）的可能性越高。")
_add("s5.balance_label", "계좌 잔액", "Account Balance", "口座残高", "账户余额")
_add("s5.balance_help", "거래 시점의 계좌 잔액(원)입니다. 잔액 대비 거래 금액 비중이 비정상적으로 크면 자금 탈취 의심 신호가 됩니다.", "The account balance (KRW) at the time of transaction. An abnormally high transaction-to-balance ratio is a sign of suspected fund theft.", "取引時点の口座残高（ウォン）です。残高に対する取引金額の割合が異常に大きい場合、資金奪取の疑いのシグナルとなります。", "交易时点的账户余额（韩元）。若交易金额相对于余额的比例异常大，则可能是资金盗用的可疑信号。")
_add("s5.channel_label", "채널", "Channel", "チャネル", "渠道")
_add("s5.channel_help", "거래가 발생한 접점입니다. ATM=현금자동입출금기 · internet=인터넷뱅킹(PC) · mobile=모바일뱅킹 앱 · Others=창구 등 기타. 사기 유형별 주 사용 채널이 달라 핵심 피처입니다 (예: ATM 인출 사기, 피싱은 internet 비중↑).", "The touchpoint where the transaction occurred. ATM=cash machine · internet=internet banking (PC) · mobile=mobile banking app · Others=branch counter, etc. A key feature since fraud types favor different channels (e.g., ATM withdrawal fraud, phishing skews toward internet).", "取引が発生した接点です。ATM=現金自動預け払い機・internet=インターネットバンキング（PC）・mobile=モバイルバンキングアプリ・Others=窓口等その他。詐欺類型ごとに主に使うチャネルが異なるため重要な特徴量です（例: ATM引き出し詐欺、フィッシングはinternetの比率が高い）。", "交易发生的触点。ATM=自动取款机 · internet=网上银行（PC）· mobile=手机银行APP · Others=柜台等其他。不同欺诈类型主要使用的渠道不同，是关键特征（例如：ATM取款欺诈、钓鱼欺诈中internet占比较高）。")
_add("s5.os_label", "OS", "OS", "OS", "操作系统")
_add("s5.os_help", "거래 단말의 운영체제입니다. 고객이 평소 쓰지 않던 OS의 갑작스러운 접속(예: 모바일 고객의 Linux 접속)은 단말 탈취·원격제어 의심 신호입니다.", "The OS of the transaction device. A sudden connection from an OS the customer doesn't normally use (e.g., a Linux connection from a mobile customer) suggests device takeover or remote control.", "取引端末のOSです。顧客が普段使わないOSからの突然のアクセス（例: モバイル顧客のLinuxアクセス）は端末乗っ取り・遠隔操作の疑いのシグナルです。", "交易设备的操作系统。客户平时不使用的操作系统突然接入（例如移动端客户使用Linux接入）是设备劫持、远程控制的可疑信号。")
_add("s5.access_medium_label", "접근 매체", "Access Medium", "アクセス媒体", "接入介质")
_add("s5.access_medium_help", "거래 시스템 접근에 사용된 인증 매체입니다. a: ID/PW 로그인 · b: 패턴 · c: 생체 로그인 · d: 금융/공동 인증서 · e: 사설인증서 · f: 보안카드 · g: OTP · h: 보안카드+OTP. 평소보다 보안 강도가 낮은 매체로의 전환(예: OTP→ID/PW)은 이상 신호일 수 있습니다.", "The authentication medium used to access the transaction system. a: ID/PW login · b: pattern · c: biometric login · d: financial/joint certificate · e: private certificate · f: security card · g: OTP · h: security card+OTP. A shift to a lower-security medium than usual (e.g., OTP→ID/PW) can be an anomaly signal.", "取引システムアクセスに使用された認証媒体です。a: ID/PWログイン・b: パターン・c: 生体認証ログイン・d: 金融/共同認証書・e: 私設認証書・f: セキュリティカード・g: OTP・h: セキュリティカード+OTP。普段より低いセキュリティ強度の媒体への切替（例: OTP→ID/PW）は異常シグナルの可能性があります。", "用于访问交易系统的认证介质。a: 账号/密码登录 · b: 图案 · c: 生物识别登录 · d: 金融/联合认证书 · e: 私人认证书 · f: 安全卡 · g: OTP · h: 安全卡+OTP。切换到比平时安全强度更低的介质（例如OTP→账号/密码）可能是异常信号。")
_add("s5.detect_button", "🔍 탐지 실행", "🔍 Run Detection", "🔍 検知実行", "🔍 运行检测")
_add("s5.t2_info", "정답(Fraud_Type)을 모르는 실제 테스트 데이터에서 임의 추출합니다.", "Randomly samples from real test data where the ground-truth (Fraud_Type) is unknown.", "正解（Fraud_Type）が不明な実際のテストデータからランダム抽出します。", "从真实测试数据中随机抽取（Fraud_Type 真值未知）。")
_add("s5.sample_count_label", "추출 건수", "Rows to Sample", "抽出件数", "抽取数量")
_add("s5.random_extract_button", "🎲 랜덤 추출", "🎲 Random Sample", "🎲 ランダム抽出", "🎲 随机抽取")
_add("s5.extract_success", "✅ {n}건 추출 완료", "✅ {n} row(s) sampled", "✅ {n}件抽出完了", "✅ 已抽取 {n} 条")
_add("s5.testcsv_missing", "❌ test.csv 없음: {p}", "❌ test.csv not found: {p}", "❌ test.csv が見つかりません: {p}", "❌ 未找到 test.csv：{p}")
_add("s5.row_select_label", "탐지할 행 선택", "Select Row to Detect", "検知する行選択", "选择要检测的行")
_add("s5.row_select_fmt", "행 {i} (ID: {id})", "Row {i} (ID: {id})", "行{i}（ID: {id}）", "第{i}行（ID: {id}）")
_add("s5.run_detect_arrow", "▶ 탐지 실행", "▶ Run Detection", "▶ 検知実行", "▶ 运行检测")
_add("s5.t3_info", "정답(Fraud_Type)이 포함된 학습 데이터에서 추출 — 모델 예측과 정답 비교 가능합니다.", "Sampled from training data that includes the ground-truth (Fraud_Type) — lets you compare model prediction against the true label.", "正解（Fraud_Type）を含む学習データから抽出 — モデル予測と正解の比較が可能です。", "从包含真值（Fraud_Type）的训练数据中抽取——可比较模型预测与真实标签。")
_add("s5.type_filter_label", "유형 필터", "Type Filter", "類型フィルター", "类型筛选")
_add("s5.type_filter_all_both", "전체(정상+사기)", "All (Normal+Fraud)", "全体（正常+不正）", "全部（正常+欺诈）")
_add("s5.type_filter_all_fraud", "전체(사기만)", "All (Fraud only)", "全体（不正のみ）", "全部（仅欺诈）")
_add("s5.type_filter_normal", "m(정상)", "m (Normal)", "m（正常）", "m（正常）")
_add("s5.random_dice_help", "랜덤 추출", "Random sample", "ランダム抽出", "随机抽取")
_add("s5.type_no_data", "⚠ 유형 {type} 데이터 없음", "⚠ No data for type {type}", "⚠ 類型{type}のデータなし", "⚠ 没有类型{type}的数据")
_add("s5.row_select_true_fmt", "행 {i} — 유형 {type} (ID: {id})", "Row {i} — type {type} (ID: {id})", "行{i} — 類型{type}（ID: {id}）", "第{i}行 — 类型{type}（ID: {id}）")
_add("s5.true_answer_label", "선택 행 정답:", "Ground truth for selected row:", "選択行の正解:", "所选行真值：")
_add("s5.t4_info", "train.csv 분포를 기반으로 합성 데이터를 생성한 뒤 즉시 탐지합니다.", "Generates synthetic data based on the train.csv distribution and detects it immediately.", "train.csvの分布に基づき合成データを生成し、直ちに検知します。", "基于 train.csv 的分布生成合成数据，并立即进行检测。")
_add("s5.target_type_label5", "목표 유형", "Target Type", "目標類型", "目标类型")
_add("s5.synth_dice_help", "합성 생성", "Generate synthetic", "合成生成", "合成生成")
_add("s5.row_select_synth_fmt", "합성 행 {i}", "Synthetic row {i}", "合成行{i}", "合成第{i}行")
_add("s5.t5_info", "폴더 내 모든 CSV를 순차 처리합니다.", "Processes all CSVs in the folder sequentially.", "フォルダ内の全CSVを順次処理します。", "依次处理文件夹中的所有CSV。")
_add("s5.folder_path_label", "폴더 경로", "Folder Path", "フォルダパス", "文件夹路径")
_add("s5.folder_scan_button", "📁 폴더 스캔 후 첫 이상거래 탐지", "📁 Scan Folder & Detect First Anomaly", "📁 フォルダスキャン後、最初の異常取引を検知", "📁 扫描文件夹并检测首个异常交易")
_add("s5.files_found", "✅ {n}개 파일 발견", "✅ {n} file(s) found", "✅ {n}個のファイルを発見", "✅ 发现 {n} 个文件")
_add("s5.csv_read_fail", "❌ CSV 읽기 실패: {name}", "❌ Failed to read CSV: {name}", "❌ CSV読み込み失敗: {name}", "❌ 读取CSV失败：{name}")
_add("s5.no_csv_warn", "⚠ {path} 에 CSV 파일 없음", "⚠ No CSV files in {path}", "⚠ {path} にCSVファイルなし", "⚠ {path} 中没有CSV文件")
_add("s5.ml_classify_spinner", "ML 모델 분류 중...", "Running ML classification...", "ML分類中...", "正在进行ML分类...")
_add("s5.llm_analyzing_spinner", "AI 분석 중... (분석 → Slack → Email)", "Running AI analysis... (Analysis → Slack → Email)", "AI分析中...（分析→Slack→Email）", "正在进行AI分析...（分析→Slack→Email）")
_add("s5.empty_title", "아직 탐지 결과가 없습니다", "No detection result yet", "まだ検知結果がありません", "尚无检测结果")
_add("s5.empty_desc", "위 입력 탭에서 거래를 입력하거나, <b style=\"color:{accent}\">⚡ 고위험 시나리오 자동입력</b> 후<br><b style=\"color:{accent}\">🔍 탐지 실행</b>을 누르면 ML 분류 → AI 3단계 분석이 이어집니다 <span style=\"opacity:0.7\">(키보드 1~5로 세션 이동)</span>",
     "Enter a transaction in the tab above, or click <b style=\"color:{accent}\">⚡ Auto-fill High-Risk Scenario</b><br>then <b style=\"color:{accent}\">🔍 Run Detection</b> to trigger ML classification → AI 3-step analysis <span style=\"opacity:0.7\">(press 1–5 to switch sessions)</span>",
     "上の入力タブで取引を入力するか、<b style=\"color:{accent}\">⚡ 高リスクシナリオ自動入力</b>後<br><b style=\"color:{accent}\">🔍 検知実行</b>を押すとML分類→AI3段階分析が続きます<span style=\"opacity:0.7\">（キーボード1〜5でセッション移動）</span>",
     "在上方输入标签中输入交易，或点击<b style=\"color:{accent}\">⚡ 自动填充高风险场景</b>后<br>点击<b style=\"color:{accent}\">🔍 运行检测</b>即可依次执行ML分类→AI三阶段分析<span style=\"opacity:0.7\">（键盘1～5可切换会话）</span>")
_add("s5.result_title", "탐지 결과", "Detection Result", "検知結果", "检测结果")
_add("s5.model_error", "❌ 모델 오류: {e}", "❌ Model error: {e}", "❌ モデルエラー: {e}", "❌ 模型错误：{e}")
_add("s5.verdict_anomaly", "🚨 이상거래 탐지", "🚨 Anomaly Detected", "🚨 異常取引検知", "🚨 检测到异常交易")
_add("s5.verdict_normal", "✅ 정상 거래", "✅ Normal Transaction", "✅ 正常取引", "✅ 正常交易")
_add("s5.model_line", "모델: {m}", "Model: {m}", "モデル: {m}", "模型：{m}")
_add("s5.threshold_line", "임계값:", "Threshold:", "閾値:", "阈值：")
_add("s5.th_pred_type", "예측 유형", "Predicted Type", "予測類型", "预测类型")
_add("s5.th_true_answer", "실제 정답", "Ground Truth", "実際の正解", "真实答案")
_add("s5.th_input_mode", "입력 방식", "Input Mode", "入力方式", "输入方式")
_add("s5.th_risk_features", "위험 피처", "Risk Features", "リスク特徴量", "风险特征")
_add("s5.notify_slack_sent", "Slack ✓ 자동발송됨", "Slack ✓ Auto-sent", "Slack ✓ 自動送信済み", "Slack ✓ 已自动发送")
_add("s5.notify_slack_fail", "Slack ✗ 발송실패", "Slack ✗ Send failed", "Slack ✗ 送信失敗", "Slack ✗ 发送失败")
_add("s5.notify_email_sent", "Email ✓ 자동발송됨", "Email ✓ Auto-sent", "Email ✓ 自動送信済み", "Email ✓ 已自动发送")
_add("s5.notify_email_fail", "Email ✗ 발송실패", "Email ✗ Send failed", "Email ✗ 送信失敗", "Email ✗ 发送失败")
_add("s5.fraud_info_title", "탐지 유형 해설", "Fraud Type Explanation", "検知類型解説", "检测类型说明")
_add("s5.prob_title", "클래스별 예측 확률", "Predicted Probability by Class", "クラス別予測確率", "各类别预测概率")
_add("s5.llm_section_title", "AI 원인 분석 · 조치 해석", "AI Root-Cause Analysis · Action Guidance", "AI原因分析・対応解釈", "AI原因分析 · 处置建议")
_add("s5.llm_auto_skip_info", "✅ 정상 거래로 판정되어 AI 분석이 <b>자동 실행되지 않았습니다</b> (LLM 호출 비용 절약을 위해 이상거래만 자동 분석). 필요하면 아래 버튼으로 수동 실행할 수 있습니다.", "✅ Judged as normal, so AI analysis was <b>not run automatically</b> (only anomalies are auto-analyzed to save LLM call cost). You can run it manually below if needed.", "✅ 正常取引と判定されたためAI分析は<b>自動実行されませんでした</b>（LLM呼び出しコスト節約のため異常取引のみ自動分析）。必要な場合は下のボタンで手動実行できます。", "✅ 判定为正常交易，因此AI分析<b>未自动执行</b>（为节省LLM调用成本，仅对异常交易自动分析）。如需要，可通过下方按钮手动执行。")
_add("s5.llm_start_button", "🤖 AI 분석 시작", "🤖 Start AI Analysis", "🤖 AI分析開始", "🤖 开始AI分析")
_add("s5.llm_provider_desc", "제공자: <b>{p}</b> | 3단계 호출 (분석→Slack→Email) | 소요 ~30초~2분", "Provider: <b>{p}</b> | 3-step call (Analysis→Slack→Email) | Takes ~30s–2min", "プロバイダー: <b>{p}</b> | 3段階呼び出し（分析→Slack→Email）| 所要 〜30秒〜2分", "提供商：<b>{p}</b> | 三阶段调用（分析→Slack→Email）| 耗时约30秒～2分钟")
_add("s5.llm_fail", "⚠ LLM 분석 실패 — {e}", "⚠ LLM analysis failed — {e}", "⚠ LLM分析失敗 — {e}", "⚠ LLM分析失败 — {e}")
_add("s5.retry_button", "🔄 다시 시도", "🔄 Retry", "🔄 再試行", "🔄 重试")
_add("s5.fallback_all_title", "⚠️ **LLM 응답 없음 — 3단계 모두 폴백 메시지로 대체됨**", "⚠️ **No LLM response — all 3 steps replaced with fallback messages**", "⚠️ **LLM応答なし — 3段階すべてフォールバックメッセージに置換されました**", "⚠️ **无LLM响应 — 三个阶段均已替换为回退消息**")
_add("s5.fallback_provider", "제공자: `{p}`", "Provider: `{p}`", "プロバイダー: `{p}`", "提供商：`{p}`")
_add("s5.fallback_error_log", "**에러 로그:**", "**Error log:**", "**エラーログ:**", "**错误日志：**")
_add("s5.fallback_no_error", "(에러 없음)", "(no errors)", "（エラーなし）", "（无错误）")
_add("s5.fallback_partial_title", "⚠️ **일부 단계 폴백: {fb}**", "⚠️ **Some steps fell back: {fb}**", "⚠️ **一部段階フォールバック: {fb}**", "⚠️ **部分阶段已回退：{fb}**")
_add("s5.fallback_empty_no_error", "**[{field}]** — 에러 없이 빈 응답 (_strip_channel_leak 필터링 가능성)", "**[{field}]** — empty response with no error (possibly filtered by _strip_channel_leak)", "**[{field}]** — エラーなしで空応答（_strip_channel_leakによるフィルタリングの可能性）", "**[{field}]** — 无错误但响应为空（可能被 _strip_channel_leak 过滤）")
_add("s5.analysis_result_title", "📋 분석 결과", "📋 Analysis Result", "📋 分析結果", "📋 分析结果")
_add("s5.analysis_raw_expander", "📋 분석 결과 원문 복사", "📋 Copy Raw Analysis", "📋 分析結果原文コピー", "📋 复制分析结果原文")
_add("s5.no_analysis", "분석 결과 없음", "No analysis result", "分析結果なし", "无分析结果")
_add("s5.slack_title", "💬 Slack 알림", "💬 Slack Alert", "💬 Slack通知", "💬 Slack通知")
_add("s5.email_title", "📧 이메일 본문", "📧 Email Body", "📧 メール本文", "📧 邮件正文")
_add("s5.email_raw_expander", "📋 이메일 원문 복사", "📋 Copy Raw Email", "📋 メール原文コピー", "📋 复制邮件原文")
_add("s5.send_toolbar_title", "📤 알림 발송", "📤 Send Notification", "📤 通知送信", "📤 发送通知")
_add("s5.send_slack_button", "Slack", "Slack", "Slack", "Slack")
_add("s5.send_slack_help", "Slack으로 수동 발송", "Manually send to Slack", "Slackへ手動送信", "手动发送到Slack")
_add("s5.send_email_button", "이메일", "Email", "メール", "邮件")
_add("s5.send_email_help", "이메일로 수동 발송", "Manually send email", "メールで手動送信", "手动发送邮件")
_add("s5.slack_sent_toast", "✅ Slack 발송 완료", "✅ Slack sent", "✅ Slack送信完了", "✅ Slack发送完成")
_add("s5.slack_fail_toast", "❌ Slack 발송 실패", "❌ Slack send failed", "❌ Slack送信失敗", "❌ Slack发送失败")
_add("s5.email_sent_toast", "✅ 이메일 발송 완료", "✅ Email sent", "✅ メール送信完了", "✅ 邮件发送完成")
_add("s5.email_fail_toast", "❌ 이메일 발송 실패", "❌ Email send failed", "❌ メール送信失敗", "❌ 邮件发送失败")
_add("s5.redo_toolbar_title", "♻️ 재생성", "♻️ Regenerate", "♻️ 再生成", "♻️ 重新生成")
_add("s5.redo_all_button", "전체", "All", "全体", "全部")
_add("s5.redo_all_help", "분석·Slack·Email 3단계 전체 재분석", "Re-run all 3 steps: Analysis, Slack, Email", "分析・Slack・Email 3段階全体を再分析", "重新分析全部三阶段：分析·Slack·邮件")
_add("s5.redo_analysis_button", "분석", "Analysis", "分析", "分析")
_add("s5.redo_analysis_help", "분석 리포트만 재생성", "Regenerate only the analysis report", "分析レポートのみ再生成", "仅重新生成分析报告")
_add("s5.redo_slack_help", "Slack 메시지만 재생성", "Regenerate only the Slack message", "Slackメッセージのみ再生成", "仅重新生成Slack消息")
_add("s5.redo_email_help", "이메일 본문만 재생성", "Regenerate only the email body", "メール本文のみ再生成", "仅重新生成邮件正文")
_add("s5.redo_all_spinner", "전체 재분석 중...", "Re-analyzing everything...", "全体再分析中...", "正在全部重新分析...")
_add("s5.redo_analysis_spinner", "분석 재생성 중...", "Regenerating analysis...", "分析再生成中...", "正在重新生成分析...")
_add("s5.redo_slack_spinner", "Slack 재생성 중...", "Regenerating Slack message...", "Slack再生成中...", "正在重新生成Slack消息...")
_add("s5.redo_email_spinner", "Email 재생성 중...", "Regenerating email...", "Email再生成中...", "正在重新生成邮件...")
_add("s5.clear_result_button", "🗑 결과 초기화", "🗑 Clear Result", "🗑 結果初期化", "🗑 清除结果")
_add("s5.report_download_button", "📄 보고서 .md 저장", "📄 Save Report (.md)", "📄 レポート.md保存", "📄 保存报告(.md)")
_add("s5.raw_data_expander", "🗂 입력 데이터 원본", "🗂 Raw Input Data", "🗂 入力データ原本", "🗂 输入数据原文")
_add("s5.masked_preview_expander", "🔒 마스킹된 데이터 미리보기", "🔒 Masked Data Preview", "🔒 マスキング済みデータプレビュー", "🔒 脱敏数据预览")
_add("s5.masking_applied", "🛡 마스킹 적용 필드: {fields}", "🛡 Masked fields: {fields}", "🛡 マスキング適用フィールド: {fields}", "🛡 已脱敏字段：{fields}")
_add("s5.masking_off_note", "마스킹 레벨 OFF — 변경 없음", "Masking level OFF — no change", "マスキングレベルOFF — 変更なし", "脱敏级别OFF — 无变化")
_add("s5.history_expander", "🕘 탐지 이력 — 이번 세션 {n}건", "🕘 Detection History — {n} this session", "🕘 検知履歴 — 今セッション{n}件", "🕘 检测历史 — 本次会话{n}条")
_add("s5.history_recalc_note", "⚖️ 현재 임계값 <b style=\"color:{accent}\">{th}</b> 기준 재계산 → <b style=\"color:{red}\">🚨 {anom}</b> · <b style=\"color:{green}\">✅ {normal}</b> · <b style=\"color:{fc}\">당시 판정 대비 변경 {flip}건</b> <span style=\"color:{muted};font-size:10.5px\">(판정=당시 임계값, 현재 기준=사이드바 임계값 적용 시)</span>",
     "⚖️ Recalculated at current threshold <b style=\"color:{accent}\">{th}</b> → <b style=\"color:{red}\">🚨 {anom}</b> · <b style=\"color:{green}\">✅ {normal}</b> · <b style=\"color:{fc}\">{flip} changed vs. original verdict</b> <span style=\"color:{muted};font-size:10.5px\">(Verdict = threshold at the time, Current = sidebar threshold applied)</span>",
     "⚖️ 現在の閾値<b style=\"color:{accent}\">{th}</b>基準で再計算 → <b style=\"color:{red}\">🚨 {anom}</b>・<b style=\"color:{green}\">✅ {normal}</b>・<b style=\"color:{fc}\">当時判定との差異{flip}件</b> <span style=\"color:{muted};font-size:10.5px\">（判定＝当時の閾値、現在基準＝サイドバー閾値適用時）</span>",
     "⚖️ 按当前阈值 <b style=\"color:{accent}\">{th}</b> 重新计算 → <b style=\"color:{red}\">🚨 {anom}</b> · <b style=\"color:{green}\">✅ {normal}</b> · <b style=\"color:{fc}\">与当时判定相比变化{flip}条</b> <span style=\"color:{muted};font-size:10.5px\">（判定=当时阈值，当前基准=应用侧边栏阈值）</span>")
_add("s5.history_csv_button", "⬇ CSV 저장", "⬇ Save CSV", "⬇ CSV保存", "⬇ 保存CSV")
_add("s5.history_clear_button", "🗑 이력 지우기", "🗑 Clear History", "🗑 履歴削除", "🗑 清除历史")
_add("s5.h_time", "시각", "Time", "時刻", "时间")
_add("s5.h_txn_id", "거래ID", "Txn ID", "取引ID", "交易ID")
_add("s5.h_verdict", "판정", "Verdict", "判定", "判定")
_add("s5.h_current_verdict", "현재 기준", "Current", "現在基準", "当前基准")
_add("s5.h_change", "변경", "Changed", "変更", "变化")
_add("s5.h_type", "유형", "Type", "類型", "类型")
_add("s5.h_risk_score", "위험점수", "Risk Score", "リスクスコア", "风险评分")
_add("s5.h_threshold", "임계값", "Threshold", "閾値", "阈值")
_add("s5.h_input", "입력", "Input", "入力", "输入")
_add("s5.h_model", "모델", "Model", "モデル", "模型")
_add("s5.report_generated_at", "생성 시각", "Generated at", "生成時刻", "生成时间")

# ── ✨ v7 DESIGN: 히어로 아이브로 배지 + 차트 라벨 ──
_add("s1.eyebrow", "SESSION 01 · 프로젝트 개요", "SESSION 01 · OVERVIEW", "SESSION 01 · 概要", "SESSION 01 · 概览")
_add("s2.eyebrow", "SESSION 02 · 모델 벤치마크", "SESSION 02 · BENCHMARK", "SESSION 02 · ベンチマーク", "SESSION 02 · 基准评测")
_add("s3.eyebrow", "SESSION 03 · 오탐·미탐 심층 분석", "SESSION 03 · DEEP DIVE", "SESSION 03 · 詳細分析", "SESSION 03 · 深入分析")
_add("s4.eyebrow", "SESSION 04 · 합성데이터 QA", "SESSION 04 · SYNTHETIC QA", "SESSION 04 · 合成データQA", "SESSION 04 · 合成数据QA")
_add("s5.eyebrow", "SESSION 05 · 실시간 탐지", "SESSION 05 · LIVE DETECTION", "SESSION 05 · リアルタイム検知", "SESSION 05 · 实时检测")
_add("s1.donut_normal", "정상", "Normal", "正常", "正常")
_add("s1.donut_fraud", "사기", "Fraud", "不正", "欺诈")
_add("s1.donut_hover", "{label}: {value}건 ({percent})", "{label}: {value} txns ({percent})", "{label}: {value}件（{percent}）", "{label}：{value}笔（{percent}）")
_add("s2.macro_label", "전체(macro)", "Overall (macro)", "全体（macro）", "总体（macro）")
_add("s2.cm_hover_correct", "정탐", "Correct", "正解", "正确")
_add("s2.cm_hover_error", "예측 오류", "Misclassified", "予測誤り", "预测错误")
_add("s2.hover_support", "표본 {n}건", "Support {n}", "サンプル{n}件", "样本{n}笔")
_add("s2.optimal_annotation", "최적 {th}", "Optimal {th}", "最適 {th}", "最优 {th}")
_add("sb.voice_section", "🔊 음성 · 알람", "🔊 Voice · Alarm", "🔊 音声・アラーム", "🔊 语音·警报")
_add("sb.tts_lang_label", "TTS 언어", "TTS Language", "TTS言語", "TTS语言")
_add("sb.alarm_toggle", "🔔 위험 감지 알람", "🔔 Risk Detection Alarm", "🔔 リスク検知アラーム", "🔔 风险检测警报")
_add("s5.email_btn_label", "이메일", "Email", "メール", "邮件")

MODEL_DISPLAY_I18N = {
    "LightGBM (기본)": {"ko":"LightGBM (기본)", "en":"LightGBM (Default)", "ja":"LightGBM（デフォルト）", "zh":"LightGBM（默认）"},
    "MLP (신경망)":    {"ko":"MLP (신경망)",    "en":"MLP (Neural Net)",  "ja":"MLP（ニューラルネット）", "zh":"MLP（神经网络）"},
}
def model_display_name(name, lang):
    return MODEL_DISPLAY_I18N.get(name, {}).get(lang, name)
_add("s5.render_error", "❌ 탐지 결과 렌더링 오류: {e}", "❌ Error rendering detection result: {e}", "❌ 検知結果レンダリングエラー: {e}", "❌ 检测结果渲染出错：{e}")
_add("s5.render_error_expander", "🔍 상세 에러 로그", "🔍 Detailed Error Log", "🔍 詳細エラーログ", "🔍 详细错误日志")
_add("common.key_indicators", "주요 지표", "Key Indicators", "主要指標", "主要指标")
_add("common.csv_loading_spinner", "CSV 로딩 중...", "Loading CSV...", "CSV読み込み中...", "正在加载CSV...")
_add("common.rag_index_spinner", "RAG 인덱스 준비 중... (최초 1회)", "Preparing RAG index... (first time only)", "RAGインデックス準備中...（初回のみ）", "正在准备RAG索引...（仅首次）")
_add("common.random_seed_toast", "🎲 랜덤 시드 생성: {s}", "🎲 Random seed generated: {s}", "🎲 ランダムシード生成: {s}", "🎲 已生成随机种子：{s}")
_add("common.session_render_error", "❌ [{session}] 렌더링 오류: {e}", "❌ [{session}] Render error: {e}", "❌ [{session}] レンダリングエラー: {e}", "❌ [{session}] 渲染出错：{e}")
_add("common.custom_api_key_label", "Custom API Key (OpenRouter 등)", "Custom API Key (OpenRouter, etc.)", "カスタムAPIキー（OpenRouter等）", "自定义API密钥（OpenRouter等）")
_add("common.redo_step_fail_toast", "❌ {step} 재분석 실패: {e}", "❌ {step} re-analysis failed: {e}", "❌ {step} 再分析失敗: {e}", "❌ {step} 重新分析失败：{e}")
_add("hist.verdict_anomaly", "🚨 이상", "🚨 Anomaly", "🚨 異常", "🚨 异常")
_add("hist.verdict_normal", "✅ 정상", "✅ Normal", "✅ 正常", "✅ 正常")

# ══════════════════════════════════════════════════════════
# 언어별 데이터 딕셔너리 (내부 키는 언어 무관 — a~l, 코드값 등)
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
# 🔴 v17: 사기 유형 사전 전면 교체
#   기존 정의(원격제어/피싱/스미싱/대출빙자 …)는 실제 데이터와 무관한 일반 명칭이었다.
#   팀 EDA 유형 정의 + X_tr/X_va 120,000행 전수 검증 결과로 대체한다.
#   'evidence'는 신설 필드 — 실측 수치를 화면에 직접 노출해 담당자와 AI가 같은 근거를 본다.
#   ⚠️ indicators는 '해당 유형에서 두드러지는 특징'이며 사기 판정 조건이 아니다
#      (정상 거래도 수취정지 49%·미사용계좌 51%를 가짐).
# ══════════════════════════════════════════════════════════
FRAUD_LABELS_I18N = {
    'ko': {'a':'유형 A — 원거리 즉시이체','b':'유형 B — 저신용층 표적','c':'유형 C — 악성앱→ATM','d':'유형 D — 약신호 미분류','e':'유형 E — 대량입금→ATM인출','f':'유형 F — 위장 최종인출','g':'유형 G — 인출 중간단계','h':'유형 H — 휴면계좌 실패','i':'유형 I — 고액 이체','j':'유형 J — 대포통장 유입','k':'유형 K — 계좌 재사용','l':'유형 L — 고령층 표적','m':'정상 거래'},
    'en': {'a':'Type A — Remote instant transfer','b':'Type B — Low-credit targeting','c':'Type C — Malware→ATM','d':'Type D — Weak signal','e':'Type E — Inflow→ATM drain','f':'Type F — Disguised final drain','g':'Type G — Mid-stage drain','h':'Type H — Dormant reactivation fail','i':'Type I — Large transfer','j':'Type J — Mule account inflow','k':'Type K — Recipient reuse','l':'Type L — Elderly targeting','m':'Normal'},
    'ja': {'a':'類型A — 遠距離即時送金','b':'類型B — 低信用層標的','c':'類型C — 悪性アプリ→ATM','d':'類型D — 弱信号未分類','e':'類型E — 大量入金→ATM出金','f':'類型F — 偽装最終出金','g':'類型G — 出金中間段階','h':'類型H — 休眠口座失敗','i':'類型I — 高額送金','j':'類型J — 不正口座入金','k':'類型K — 口座再利用','l':'類型L — 高齢層標的','m':'正常取引'},
    'zh': {'a':'类型A — 远距离即时转账','b':'类型B — 低信用群体','c':'类型C — 恶意应用→ATM','d':'类型D — 弱信号未分类','e':'类型E — 大额入账→ATM提现','f':'类型F — 伪装最终提现','g':'类型G — 提现中间阶段','h':'类型H — 休眠账户失败','i':'类型I — 大额转账','j':'类型J — 空壳账户流入','k':'类型K — 账户复用','l':'类型L — 老年群体','m':'正常交易'},
}
FRAUD_SHORT_I18N = {
    'ko': {'a':'A 원거리','b':'B 저신용','c':'C 악성앱','d':'D 약신호','e':'E 입금→ATM','f':'F 위장인출','g':'G 중간단계','h':'H 휴면실패','i':'I 고액','j':'J 대포통장','k':'K 재사용','l':'L 고령층','m':'정상'},
    'en': {'a':'A Remote','b':'B LowCredit','c':'C Malware','d':'D WeakSig','e':'E Inflow→ATM','f':'F Disguised','g':'G MidStage','h':'H DormantFail','i':'I LargeAmt','j':'J Mule','k':'K Reuse','l':'L Elderly','m':'Normal'},
    'ja': {'a':'A 遠距離','b':'B 低信用','c':'C 悪性アプリ','d':'D 弱信号','e':'E 入金→ATM','f':'F 偽装出金','g':'G 中間','h':'H 休眠失敗','i':'I 高額','j':'J 不正口座','k':'K 再利用','l':'L 高齢層','m':'正常'},
    'zh': {'a':'A 远距离','b':'B 低信用','c':'C 恶意应用','d':'D 弱信号','e':'E 入账→ATM','f':'F 伪装提现','g':'G 中间阶段','h':'H 休眠失败','i':'I 大额','j':'J 空壳账户','k':'K 复用','l':'L 老年','m':'正常'},
}

FRAUD_TYPE_DETAILS_I18N = {
    'ko': {
        'a':{'name':"원거리 즉시이체 (계정탈취)",'desc':"계정을 탈취한 공격자가 피해자와 다른 지역·국가에서 곧바로 이어서 이체하는 유형입니다. 단말 감염 흔적 없이 물리적 거리만 튀는 것이 특징이며, 자격증명만 탈취해 공격자 환경에서 접속했음을 시사합니다.",'evidence':"접속거리 273km↑ 100% (타 유형 11% · 리프트 8.8배) · 거리 z=+2.37 전 유형 1위 · 단말 악성흔적 평균 수준",'indicators':["원거리 접속", "단말흔적 없음", "채널 무관"],'risk':'HIGH'},
        'b':{'name':"저신용층 표적 계좌탈취",'desc':"원격제어 앱을 설치하게 유도한 뒤 신용등급이 낮은 계층을 표적으로 계좌를 탈취하는 유형입니다. 12개 유형 중 유일하게 신용등급이 완전히 분리됩니다.",'evidence':"신용등급 C/D/E 100% (A/B/S 0건) · 모바일 55% · 루팅 51%(전체의 7배) · VPN 42%(6배) · Others 채널 0%",'indicators':["신용 C/D/E", "모바일", "루팅·탈옥", "VPN"],'risk':'HIGH'},
        'c':{'name':"악성앱 정보탈취 → ATM 출금",'desc':"악성앱을 설치시켜 키로깅·파밍으로 정보를 탈취한 뒤 ATM에서 직접 현금을 출금하는 유형입니다. VPN을 쓰지 않는 점이 B형과 다르며, 피해자 환경에서 거래가 발생했음을 시사합니다.",'evidence':"단말 악성행위 플래그 평균 1.74개 (전체 0.58 · 3배, 전 유형 1위) · ATM 54% · Windows 45% · VPN 2%",'indicators':["단말 악성행위", "ATM 채널", "Windows"],'risk':'HIGH'},
        'd':{'name':"약신호 미분류 (조사 필요)",'desc':"뚜렷한 위협 신호 없이 탐지된 유형으로, 유형 정의 자체가 미완성입니다. 모델이 D형이라고 하면 '신호가 약해 확신하기 어렵다'로 읽고 규칙 적합도 2·3순위를 함께 검토해야 합니다.",'evidence':"인터넷뱅킹 45% · 미사용단말 100% · 거래실패 0% · 루팅 4% — 위협 신호가 오히려 평균 이하",'indicators':["인터넷뱅킹", "미사용 단말", "위협신호 없음"],'risk':'MEDIUM'},
        'e':{'name':"원격제어 대량입금 → ATM 전액인출",'desc':"감염 단말을 원격제어해 대량 입금을 유입시킨 뒤 ATM에서 전액 인출하는 유형입니다. E→G→F 3단 가설의 첫 단계로 해석되나, 데이터에 감염 시점 정보가 없어 선후 관계는 가설입니다.",'evidence':"1천만원↑ 입금 100% · ATM 채널 100% (모바일/iOS/Android 0%) · 루팅 17%(전체의 2.4배)",'indicators':["1천만원↑ 입금", "ATM 100%", "루팅·원격제어"],'risk':'HIGH'},
        'f':{'name':"위장 최종인출 (자금세탁 의심)",'desc':"원격조작 흔적을 전혀 남기지 않고 은밀한 채널로 잔액을 가장 크게 비우는 최종 인출 단계입니다. 위협 흔적이 0인 것 자체가 결정적 근거이며, 12유형 중 가장 깨끗하게 분리됩니다(규칙 Top-1 96%).",'evidence':"1천만원↑ 입금 100% · Others 채널 100% (ATM/모바일 0%) · 루팅 0% · 악성행위 0.00 · 거래 후 잔액 z=-0.42 전 유형 최저",'indicators':["Others 채널", "1천만원↑ 입금", "흔적 완전 없음", "잔액 대량소진"],'risk':'HIGH'},
        'g':{'name':"대량입금 인출 중간단계",'desc':"고액 입금 후 아직 최종 인출에 이르지 않은 중간 단계입니다. 원격제어 흔적이 E형(2.4배)과 F형(0배)의 정확히 중간(1.3배)이라는 점이 3단 가설의 정량적 근거입니다.",'evidence':"1천만원↑ 입금 100% · 채널 혼합(고정 채널 없음) · 루팅 9%(전체의 1.3배) · 수취계좌 거래이력 z=-0.35 · 미사용계좌 63%",'indicators':["1천만원↑ 입금", "채널 혼합", "신규 수취계좌"],'risk':'MEDIUM'},
        'h':{'name':"휴면계좌 재개 → 잔액부족 실패",'desc':"장기간 쓰지 않던 소액 계좌를 재개해 규모에 맞지 않는 거래를 시도하다 잔액 부족으로 반복 실패하는 유형입니다. 실패 자체가 탐지 신호인 특이한 유형입니다.",'evidence':"1개월 표준편차 10만원 미만 100% (타 유형 32%) · 1개월 최대이체 중앙 13.5만원 (전체 1,415만원) · 거래실패 17%·잔액부족 에러 17% 모두 전 유형 최고 · 시간차 z=+1.00 1위",'indicators':["시간차 극대", "거래 실패", "잔액부족 에러", "평소 소액계좌"],'risk':'MEDIUM'},
        'i':{'name':"고액 이체 (확신도 낮음)",'desc':"금액 자체가 극단적으로 큰 이체입니다. 다만 금액 외 신호가 약해 정상 고액 거래와 구분이 어렵고, 팀 정의에도 확신도 낮음이 명시돼 있습니다. 오탐 비용이 큰 구간이므로 정밀도 우선 운영을 권합니다.",'evidence':"거래금액 z=+1.97 전 유형 1위(중앙 3,454만원 vs 전체 271만원) · 1개월 최대이체 z=+0.87 1위 · 인증변경 이력 3.83 전 유형 최고 · 거래실패 0%",'indicators':["금액 극대", "평소도 고액계좌", "인증변경 다수"],'risk':'MEDIUM'},
        'j':{'name':"대포통장 초기 자금유입",'desc':"새로 확보한 대포통장에 처음으로 자금을 유입시키려는 시도입니다. 수취계좌 정지 이력과 휴면 상태가 동시에 100%인 것이 이 유형의 지문입니다. 피해 확산을 막기 위해 즉시 차단이 최우선입니다.",'evidence':"수취계좌 거래중지 100% + 미사용계좌 100% 동시 (전체 각 49%·51%) · 수취계좌 거래이력 z=-0.72 전 유형 최저 = 첫 송금 · 저축계좌 34%",'indicators':["수취계좌 정지", "미사용 계좌", "거래이력 없음"],'risk':'HIGH'},
        'k':{'name':"계좌 재사용 반복거래 · 인증변경",'desc':"같은 수취계좌로 짧은 시간에 반복 이체하는 유형입니다. 성공한 경로를 재활용하는 행동 패턴이며, 인증수단 변경이 함께 높아 계정 통제권을 확보한 뒤 반복 이체했다는 해석을 지지합니다. J형(휴면 대포통장)과 정반대입니다.",'evidence':"동일 수취계좌 거래횟수 z=+2.17 전 유형 1위 · 수취계좌 거래이력 z=+1.01 1위 · 미사용계좌 0% (타 유형 40~63%) 강한 배제조건 · 인증변경 3.59 · ATM 36%",'indicators':["동일계좌 반복", "인증수단 변경", "활성 계좌", "ATM 비중"],'risk':'HIGH'},
        'l':{'name':"고령층 표적 명의도용",'desc':"고령 고객을 표적으로 한 명의도용 정황입니다. 기술적 침입 흔적이 거의 없는데 연령만 편중된다는 조합은 악성코드가 아닌 대면·통화 기반 심리 조작(사회공학)을 시사합니다. 모델·규칙 모두 성능이 낮은 구간이므로 사람 개입을 전제로 운영해야 합니다.",'evidence':"출생연도 z=-1.18 — 12유형 중 유일한 연령 편중 (1955~1965 집중) · 단말 악성행위 0.34 사기 중 최저 수준 · 입출금계좌 38% 전 유형 최고 · 채널 균등",'indicators':["고령 연령대", "단말흔적 없음", "신규 수취계좌"],'risk':'MEDIUM'},
        'm':{'name':"정상 거래",'desc':"잔액 대비 소액 이체 패턴의 정상 거래로, 전체 데이터의 99%(118,800건)를 차지합니다. ⚠️ 정상 거래도 수취계좌 정지 49%·미사용계좌 51%·고액입금 42%·미사용단말 92%를 가지므로, 이 항목들은 사기 판별에 쓸 수 없습니다.",'evidence':"거래금액 z=-0.01 · 잔액 z=+0.00 · 루팅 7% · VPN 7% · 악성행위 0.58 (모두 기준선) · 거래실패 2%",'indicators':["소액 이체", "여유 잔액", "위협신호 없음"],'risk':'LOW'},
    },
    'en': {
        'a':{'name':"Remote instant transfer (account takeover)",'desc':"An attacker who has taken over the account transfers immediately from a different region or country. Only the physical distance stands out while device-threat traces stay normal, suggesting credential theft with access from the attacker's own environment.",'evidence':"100% exceed 273km (vs 11% other types, lift 8.8x) · distance z=+2.37, highest of all types · device-malware traces at baseline",'indicators':["Long distance", "No device trace", "Channel-agnostic"],'risk':'HIGH'},
        'b':{'name':"Low-credit-segment account takeover",'desc':"Victims are lured into installing a remote-control app; targeting concentrates on low credit ratings. The only type where credit rating separates completely.",'evidence':"Credit C/D/E 100% (zero A/B/S) · mobile 55% · rooting 51% (7x baseline) · VPN 42% (6x) · Others channel 0%",'indicators':["Credit C/D/E", "Mobile", "Rooted", "VPN"],'risk':'HIGH'},
        'c':{'name':"Malicious app → ATM withdrawal",'desc':"A malicious app harvests credentials via keylogging/pharming, then cash is withdrawn at an ATM. Unlike type B, VPN is not used, suggesting the transaction originated in the victim's own environment.",'evidence':"Device-malware flags avg 1.74 (vs 0.58 overall, 3x, highest of all types) · ATM 54% · Windows 45% · VPN 2%",'indicators':["Device malware", "ATM channel", "Windows"],'risk':'HIGH'},
        'd':{'name':"Weak signal, unresolved (needs investigation)",'desc':"Detected without any distinct threat signal; the type definition itself is incomplete. Read a D prediction as 'too weak to be confident' and review the 2nd/3rd ranked rule matches.",'evidence':"Internet banking 45% · unused terminal 100% · failure 0% · rooting 4% — threat signals below baseline",'indicators':["Internet banking", "Unused terminal", "No threat signal"],'risk':'MEDIUM'},
        'e':{'name':"Remote-control inflow → full ATM drain",'desc':"A compromised device is remote-controlled to receive a large inflow, then drained at an ATM. Read as stage 1 of the E→G→F hypothesis; the ordering is a hypothesis since infection timestamps are absent.",'evidence':"Deposit >=10M 100% · ATM channel 100% (mobile/iOS/Android 0%) · rooting 17% (2.4x baseline)",'indicators':["Deposit >=10M", "ATM 100%", "Rooting"],'risk':'HIGH'},
        'f':{'name':"Disguised final drain (possible laundering)",'desc':"The final withdrawal stage: it leaves no remote-control trace at all and drains the balance through a covert channel. The absence of any trace is itself the decisive evidence, and it separates most cleanly of the 12 types (rule Top-1 96%).",'evidence':"Deposit >=10M 100% · Others channel 100% (ATM/mobile 0%) · rooting 0% · malware 0.00 · post-balance z=-0.42, lowest",'indicators':["Others channel", "Deposit >=10M", "Zero trace", "Balance drained"],'risk':'HIGH'},
        'g':{'name':"Mid-stage of inflow-to-drain",'desc':"A large inflow has arrived but the final withdrawal has not yet occurred. Remote-control traces sit exactly between type E (2.4x) and F (0x) at 1.3x, the quantitative basis for the 3-stage hypothesis.",'evidence':"Deposit >=10M 100% · mixed channels (no fixed channel) · rooting 9% (1.3x baseline) · recipient history z=-0.35 · dormant account 63%",'indicators':["Deposit >=10M", "Mixed channel", "New recipient"],'risk':'MEDIUM'},
        'h':{'name':"Dormant reactivation → insufficient-balance failure",'desc':"A long-unused small-amount account is reactivated and attempts a transaction far above its usual scale, failing repeatedly for insufficient balance. Unusually, the failure itself is the detection signal.",'evidence':"1-month sigma <100K in 100% (vs 32%) · 1-month max median 135K (overall 14.15M) · failure 17% and insufficient-balance error 17%, both highest · time-gap z=+1.00, highest",'indicators':["Huge time gap", "Failure", "Insufficient balance", "Small-amount account"],'risk':'MEDIUM'},
        'i':{'name':"Large transfer (low confidence)",'desc':"The amount itself is extreme, but signals beyond the amount are weak, making it hard to separate from legitimate high-value transfers; the team definition also flags low confidence. False positives are costly here, so favour precision.",'evidence':"Amount z=+1.97, highest (median 34.5M vs 2.71M overall) · 1-month max z=+0.87, highest · auth changes 3.83, highest of all types · failure 0%",'indicators':["Extreme amount", "Habitually high-value", "Many auth changes"],'risk':'MEDIUM'},
        'j':{'name':"Initial inflow into a mule account",'desc':"A first attempt to move funds into a newly obtained mule account. The simultaneous 100% of recipient suspension and dormancy is this type's fingerprint. Immediate blocking takes priority to stop the spread of harm.",'evidence':"Recipient suspended 100% + dormant account 100% simultaneously (49%/51% overall) · recipient history z=-0.72, lowest of all types = first-ever transfer · savings account 34%",'indicators':["Recipient suspended", "Dormant account", "No prior history"],'risk':'HIGH'},
        'k':{'name':"Recipient reuse with auth changes",'desc':"Repeated transfers to the same recipient in a short window, the behaviour pattern of reusing a proven path. Authentication changes are also high, supporting the reading that the account was taken over first. The exact opposite of type J.",'evidence':"Same-recipient count z=+2.17, highest · recipient history z=+1.01, highest · dormant account 0% (vs 40-63% elsewhere), a strong exclusion signal · auth changes 3.59 · ATM 36%",'indicators':["Repeated recipient", "Auth changes", "Active account", "ATM share"],'risk':'HIGH'},
        'l':{'name':"Elderly-targeted identity theft",'desc':"Identity theft aimed at elderly customers. Almost no technical intrusion trace combined with an age concentration points to social engineering by phone or in person rather than malware. Both model and rules perform poorly here, so assume human review.",'evidence':"Birth year z=-1.18, the only age concentration among the 12 types (1955-1965) · device malware 0.34, near the lowest among fraud · checking account 38%, highest · channels evenly spread",'indicators':["Elderly age band", "No device trace", "New recipient"],'risk':'MEDIUM'},
        'm':{'name':"Normal transaction",'desc':"Normal transactions with small amounts relative to balance, 99% of the data (118,800 rows). Note: normal transactions also show recipient suspension 49%, dormant account 51%, large deposit 42% and unused terminal 92%, so those items cannot be used to detect fraud.",'evidence':"Amount z=-0.01 · balance z=+0.00 · rooting 7% · VPN 7% · malware 0.58 (all at baseline) · failure 2%",'indicators':["Small amount", "Ample balance", "No threat signal"],'risk':'LOW'},
    },
    'ja': {
        'a':{'name':"遠距離即時送金(アカウント乗っ取り)",'desc':"アカウントを乗っ取った攻撃者が被害者とは別の地域・国からそのまま送金する類型です。端末感染の痕跡がなく物理的距離のみが突出します。",'evidence':"273km超が100%(他類型11%・リフト8.8倍)・距離z=+2.37で全類型1位・端末悪性痕跡は平均水準",'indicators':["遠距離アクセス", "端末痕跡なし", "チャネル無関係"],'risk':'HIGH'},
        'b':{'name':"低信用層標的の口座乗っ取り",'desc':"遠隔操作アプリを導入させた後、信用等級の低い層を標的にします。12類型中唯一、信用等級が完全に分離します。",'evidence':"信用C/D/E 100%(A/B/S 0件)・モバイル55%・ルート化51%(全体の7倍)・VPN 42%(6倍)・Othersチャネル0%",'indicators':["信用C/D/E", "モバイル", "ルート化", "VPN"],'risk':'HIGH'},
        'c':{'name':"悪性アプリ情報窃取 → ATM出金",'desc':"悪性アプリでキーロギング・ファーミングにより情報を窃取し、ATMで現金を出金します。VPNを使わない点がB型と異なります。",'evidence':"端末悪性行為フラグ平均1.74個(全体0.58・3倍、全類型1位)・ATM 54%・Windows 45%・VPN 2%",'indicators':["端末悪性行為", "ATMチャネル", "Windows"],'risk':'HIGH'},
        'd':{'name':"弱信号・未分類(調査必要)",'desc':"明確な脅威信号なしに検知された類型で、類型定義自体が未完成です。D型予測は確信が持てないと読み、ルール適合度2・3位を併せて検討してください。",'evidence':"インターネットバンキング45%・未使用端末100%・取引失敗0%・ルート化4% — 脅威信号は平均以下",'indicators':["ネットバンキング", "未使用端末", "脅威信号なし"],'risk':'MEDIUM'},
        'e':{'name':"遠隔操作大量入金 → ATM全額出金",'desc':"感染端末を遠隔操作して大量入金を流入させ、ATMで全額出金します。E→G→F三段仮説の第一段階ですが、感染時点情報がないため順序は仮説です。",'evidence':"1千万円↑入金100%・ATMチャネル100%・ルート化17%(全体の2.4倍)",'indicators':["1千万↑入金", "ATM 100%", "ルート化"],'risk':'HIGH'},
        'f':{'name':"偽装最終出金(資金洗浄疑い)",'desc':"遠隔操作の痕跡を全く残さず、隠密なチャネルで残高を最も大きく空にする最終出金段階です。痕跡が0であること自体が決定的根拠で、12類型中最も明確に分離します(ルールTop-1 96%)。",'evidence':"1千万円↑入金100%・Othersチャネル100%・ルート化0%・悪性行為0.00・取引後残高z=-0.42で最低",'indicators':["Othersチャネル", "1千万↑入金", "痕跡完全になし", "残高大量消尽"],'risk':'HIGH'},
        'g':{'name':"大量入金・出金の中間段階",'desc':"高額入金後、最終出金に至っていない中間段階です。遠隔操作痕跡がE型(2.4倍)とF型(0倍)の正確な中間(1.3倍)である点が三段仮説の定量的根拠です。",'evidence':"1千万円↑入金100%・チャネル混合・ルート化9%(1.3倍)・受取口座取引履歴z=-0.35・未使用口座63%",'indicators':["1千万↑入金", "チャネル混合", "新規受取口座"],'risk':'MEDIUM'},
        'h':{'name':"休眠口座再開 → 残高不足失敗",'desc':"長期間使われていない少額口座を再開し、規模に合わない取引を試みて残高不足で繰り返し失敗します。失敗自体が検知信号となる特異な類型です。",'evidence':"1ヶ月標準偏差10万円未満100%(他類型32%)・1ヶ月最大送金中央13.5万円・取引失敗17%・残高不足17%いずれも最高・時間差z=+1.00で1位",'indicators':["時間差極大", "取引失敗", "残高不足", "普段少額口座"],'risk':'MEDIUM'},
        'i':{'name':"高額送金(確信度低)",'desc':"金額自体が極端に大きい送金です。ただし金額以外の信号が弱く正常な高額取引と区別しにくく、チーム定義にも確信度低が明記されています。",'evidence':"取引金額z=+1.97で1位(中央3,454万円 vs 全体271万円)・1ヶ月最大送金z=+0.87で1位・認証変更履歴3.83で最高・取引失敗0%",'indicators':["金額極大", "普段も高額口座", "認証変更多数"],'risk':'MEDIUM'},
        'j':{'name':"不正口座への初期資金流入",'desc':"新たに確保した不正口座へ初めて資金を流入させる試みです。受取口座停止と休眠状態が同時に100%であることがこの類型の指紋です。",'evidence':"受取口座取引中止100% + 未使用口座100%同時(全体各49%・51%)・受取口座取引履歴z=-0.72で最低=初回送金・貯蓄口座34%",'indicators':["受取口座停止", "未使用口座", "取引履歴なし"],'risk':'HIGH'},
        'k':{'name':"口座再利用の反復取引・認証変更",'desc':"同じ受取口座へ短時間に反復送金する類型です。成功した経路を再利用する行動パターンで、認証手段変更も高くJ型とは正反対です。",'evidence':"同一受取口座取引回数z=+2.17で1位・取引履歴z=+1.01で1位・未使用口座0%(他類型40〜63%)・認証変更3.59・ATM 36%",'indicators':["同一口座反復", "認証手段変更", "活性口座", "ATM比重"],'risk':'HIGH'},
        'l':{'name':"高齢層標的の名義盗用",'desc':"高齢顧客を標的とした名義盗用の情況です。技術的侵入痕跡がほとんどないのに年齢のみ偏るという組み合わせは、対面・通話ベースの心理操作を示唆します。",'evidence':"出生年z=-1.18 — 12類型中唯一の年齢偏重(1955〜1965集中)・端末悪性行為0.34で最低水準・入出金口座38%で最高",'indicators':["高齢年齢層", "端末痕跡なし", "新規受取口座"],'risk':'MEDIUM'},
        'm':{'name':"正常取引",'desc':"残高に対して少額の送金パターンの正常取引で、全体データの99%(118,800件)を占めます。正常取引も受取口座停止49%・未使用口座51%・高額入金42%を持つため、これらは不正判別に使えません。",'evidence':"取引金額z=-0.01・残高z=+0.00・ルート化7%・VPN 7%・悪性行為0.58(すべて基準線)・取引失敗2%",'indicators':["少額送金", "余裕残高", "脅威信号なし"],'risk':'LOW'},
    },
    'zh': {
        'a':{'name':"远距离即时转账(账户被盗)",'desc':"盗取账户的攻击者从与受害者不同的地区或国家直接转账。设备感染痕迹正常而仅物理距离突出，提示仅凭凭证被盗、从攻击者自身环境接入。",'evidence':"超过273km占100%(其他类型11%·提升8.8倍)·距离 z=+2.37 全类型第一·设备恶意痕迹处于基线",'indicators':["远距离接入", "无设备痕迹", "与渠道无关"],'risk':'HIGH'},
        'b':{'name':"低信用群体账户劫持",'desc':"诱导安装远程控制应用后，专门针对信用等级较低的群体。12种类型中唯一信用等级完全分离的类型。",'evidence':"信用 C/D/E 占100%(A/B/S 为0)·移动端55%·越狱51%(基线的7倍)·VPN 42%(6倍)·Others渠道0%",'indicators':["信用C/D/E", "移动端", "越狱", "VPN"],'risk':'HIGH'},
        'c':{'name':"恶意应用窃取信息 → ATM取现",'desc':"通过恶意应用以键盘记录/域名欺骗窃取信息后在ATM直接取现。与B型不同的是不使用VPN，提示交易发生在受害者自身环境。",'evidence':"设备恶意行为标记平均1.74个(整体0.58·3倍，全类型第一)·ATM 54%·Windows 45%·VPN 2%",'indicators':["设备恶意行为", "ATM渠道", "Windows"],'risk':'HIGH'},
        'd':{'name':"弱信号未分类(需调查)",'desc':"在没有明显威胁信号的情况下被检出，类型定义本身尚未完成。模型判为D型应理解为信号弱、难以确认，需同时查看规则契合度第2、3位。",'evidence':"网银45%·未使用终端100%·交易失败0%·越狱4% — 威胁信号反而低于平均",'indicators':["网上银行", "未使用终端", "无威胁信号"],'risk':'MEDIUM'},
        'e':{'name':"远程控制大额入账 → ATM全额提现",'desc':"远程控制受感染设备接收大额入账后在ATM全额提现。可视为E→G→F三阶段假设的第一阶段，但因缺少感染时间信息，顺序仅为假设。",'evidence':"1千万↑入账100%·ATM渠道100%·越狱17%(基线2.4倍)",'indicators':["1千万↑入账", "ATM 100%", "越狱"],'risk':'HIGH'},
        'f':{'name':"伪装最终提现(疑似洗钱)",'desc':"完全不留远程操作痕迹，通过隐蔽渠道最大程度清空余额的最终提现阶段。痕迹为零本身就是决定性依据，在12种类型中分离最为清晰(规则 Top-1 96%)。",'evidence':"1千万↑入账100%·Others渠道100%·越狱0%·恶意行为0.00·交易后余额 z=-0.42 全类型最低",'indicators':["Others渠道", "1千万↑入账", "完全无痕迹", "余额大量消耗"],'risk':'HIGH'},
        'g':{'name':"大额入账提现中间阶段",'desc':"大额入账后尚未进入最终提现的中间阶段。远程控制痕迹恰好位于E型(2.4倍)与F型(0倍)之间(1.3倍)，是三阶段假设的量化依据。",'evidence':"1千万↑入账100%·渠道混合·越狱9%(1.3倍)·收款账户交易历史 z=-0.35·未使用账户63%",'indicators':["1千万↑入账", "渠道混合", "新收款账户"],'risk':'MEDIUM'},
        'h':{'name':"休眠账户重启 → 余额不足失败",'desc':"长期未使用的小额账户重启后尝试与其规模不符的交易，因余额不足反复失败。失败本身即检测信号，较为特殊。",'evidence':"1个月标准差低于10万占100%(其他类型32%)·1个月最大转账中位13.5万·交易失败17%与余额不足17%均为最高·时间差 z=+1.00 第一",'indicators':["时间差极大", "交易失败", "余额不足", "平时小额账户"],'risk':'MEDIUM'},
        'i':{'name':"大额转账(置信度低)",'desc':"金额本身极大，但除金额外信号较弱，难以与正常大额交易区分，团队定义中也标注置信度低。误报成本较高，建议优先保证精确率。",'evidence':"交易金额 z=+1.97 全类型第一(中位3,454万 vs 整体271万)·1个月最大转账 z=+0.87 第一·认证变更3.83最高·交易失败0%",'indicators':["金额极大", "平时也是大额账户", "多次认证变更"],'risk':'MEDIUM'},
        'j':{'name':"空壳账户初期资金流入",'desc':"向新获取的空壳账户首次注入资金的尝试。收款账户停用与休眠状态同时为100%是该类型的指纹特征。为阻止危害扩散，立即拦截为最优先。",'evidence':"收款账户交易中止100% + 未使用账户100%同时成立(整体各49%·51%)·收款账户交易历史 z=-0.72 全类型最低=首次转账·储蓄账户34%",'indicators':["收款账户停用", "未使用账户", "无交易历史"],'risk':'HIGH'},
        'k':{'name':"账户复用重复交易·认证变更",'desc':"短时间内向同一收款账户重复转账。属于复用已验证路径的行为模式，认证变更也偏高，与J型完全相反。",'evidence':"同一收款账户交易次数 z=+2.17 第一·交易历史 z=+1.01 第一·未使用账户0%(其他类型40~63%)·认证变更3.59·ATM 36%",'indicators':["同账户重复", "认证方式变更", "活跃账户", "ATM占比"],'risk':'HIGH'},
        'l':{'name':"针对老年群体的身份盗用",'desc':"针对老年客户的身份盗用情形。几乎没有技术入侵痕迹却仅有年龄集中，提示为电话或面对面的社会工程而非恶意软件。模型与规则在此区间表现均较低，应以人工介入为前提运营。",'evidence':"出生年 z=-1.18 — 12种类型中唯一的年龄集中(1955~1965)·设备恶意行为0.34接近最低·活期账户38%最高·渠道分布均匀",'indicators':["老年年龄段", "无设备痕迹", "新收款账户"],'risk':'MEDIUM'},
        'm':{'name':"正常交易",'desc':"相对余额为小额转账的正常交易，占全部数据的99%(118,800条)。正常交易同样具有收款账户停用49%、未使用账户51%、大额入账42%，因此这些项不可用于欺诈判别。",'evidence':"交易金额 z=-0.01·余额 z=+0.00·越狱7%·VPN 7%·恶意行为0.58(均为基线)·交易失败2%",'indicators':["小额转账", "余额充裕", "无威胁信号"],'risk':'LOW'},
    },
}

ACCESS_MEDIUM_MAP_I18N = {
    'ko': {'a':'ID/PW 로그인','b':'패턴','c':'생체 로그인','d':'금융/공동 인증서','e':'사설인증서','f':'보안카드','g':'OTP','h':'보안카드+OTP'},
    'en': {'a':'ID/PW Login','b':'Pattern','c':'Biometric Login','d':'Financial/Joint Certificate','e':'Private Certificate','f':'Security Card','g':'OTP','h':'Security Card+OTP'},
    'ja': {'a':'ID/PWログイン','b':'パターン','c':'生体認証ログイン','d':'金融/共同認証書','e':'私設認証書','f':'セキュリティカード','g':'OTP','h':'セキュリティカード+OTP'},
    'zh': {'a':'账号/密码登录','b':'图案','c':'生物识别登录','d':'金融/联合认证书','e':'私人认证书','f':'安全卡','g':'OTP','h':'安全卡+OTP'},
}

FLAG_LABELS_I18N = {
    'ko': {'Customer_rooting_jailbreak_indicator':'루팅/탈옥','Customer_VPN_Indicator':'VPN 사용','Customer_flag_terminal_malicious_behavior_1':'단말 악성행위-1','Customer_flag_terminal_malicious_behavior_2':'단말 악성행위-2','Customer_flag_terminal_malicious_behavior_3':'단말 악성행위-3','Unused_terminal_status':'미사용 단말','Unused_account_status':'미사용 계좌','Recipient_account_suspend_status':'수취계좌 정지','Account_release_suspention':'계좌 거래정지','Transaction_Failure_Status':'거래 실패','Another_Person_Account':'타인 계좌','Flag_deposit_more_than_tenMillion':'1천만원↑ 입금'},
    'en': {'Customer_rooting_jailbreak_indicator':'Rooted/Jailbroken','Customer_VPN_Indicator':'VPN Use','Customer_flag_terminal_malicious_behavior_1':'Device Malware-1','Customer_flag_terminal_malicious_behavior_2':'Device Malware-2','Customer_flag_terminal_malicious_behavior_3':'Device Malware-3','Unused_terminal_status':'Unused Device','Unused_account_status':'Unused Account','Recipient_account_suspend_status':'Recipient Suspended','Account_release_suspention':'Account Suspended','Transaction_Failure_Status':'Transaction Failure','Another_Person_Account':'Third-party Account','Flag_deposit_more_than_tenMillion':'Deposit ≥ 10M KRW'},
    'ja': {'Customer_rooting_jailbreak_indicator':'ルート化/脱獄','Customer_VPN_Indicator':'VPN使用','Customer_flag_terminal_malicious_behavior_1':'端末悪性行為-1','Customer_flag_terminal_malicious_behavior_2':'端末悪性行為-2','Customer_flag_terminal_malicious_behavior_3':'端末悪性行為-3','Unused_terminal_status':'未使用端末','Unused_account_status':'未使用口座','Recipient_account_suspend_status':'受取口座停止','Account_release_suspention':'口座取引停止','Transaction_Failure_Status':'取引失敗','Another_Person_Account':'他人口座','Flag_deposit_more_than_tenMillion':'1000万ウォン↑入金'},
    'zh': {'Customer_rooting_jailbreak_indicator':'已root/越狱','Customer_VPN_Indicator':'使用VPN','Customer_flag_terminal_malicious_behavior_1':'终端恶意行为-1','Customer_flag_terminal_malicious_behavior_2':'终端恶意行为-2','Customer_flag_terminal_malicious_behavior_3':'终端恶意行为-3','Unused_terminal_status':'未使用终端','Unused_account_status':'未使用账户','Recipient_account_suspend_status':'收款账户停用','Account_release_suspention':'账户交易停用','Transaction_Failure_Status':'交易失败','Another_Person_Account':'他人账户','Flag_deposit_more_than_tenMillion':'存入1千万韩元以上'},
}

FLAG_HELP_I18N = {
    'ko': {
        'Customer_rooting_jailbreak_indicator':'거래 단말이 루팅(Android)/탈옥(iOS)된 상태입니다. 보안 통제 우회·악성앱 설치가 가능해져 원격제어·스미싱 유형의 핵심 신호입니다.',
        'Customer_VPN_Indicator':'VPN을 경유한 접속입니다. 실제 접속 위치를 은폐할 수 있어 피싱·원격제어 유형에서 자주 관찰됩니다.',
        'Customer_flag_terminal_malicious_behavior_1':'단말 보안 모듈이 탐지한 악성 행위 시그널 1번 룰입니다 (악성앱·후킹 시도 등 내부 탐지 기준).',
        'Customer_flag_terminal_malicious_behavior_2':'단말 보안 모듈이 탐지한 악성 행위 시그널 2번 룰입니다.',
        'Customer_flag_terminal_malicious_behavior_3':'단말 보안 모듈이 탐지한 악성 행위 시그널 3번 룰입니다.',
        'Unused_terminal_status':'장기간 사용 이력이 없던 단말에서의 접속입니다. 단말 탈취·명의도용 의심 신호입니다.',
        'Unused_account_status':'장기 미사용 계좌에서 갑작스러운 거래가 발생했습니다. 계좌 이상 패턴의 주요 지표입니다.',
        'Recipient_account_suspend_status':'수취(입금 대상) 계좌가 지급정지 상태입니다. 사기 신고 이력 계좌로의 이체 시도일 수 있습니다.',
        'Account_release_suspention':'거래 계좌의 거래정지/해제 이력 관련 상태 플래그입니다. 정지 직후 해제·거래 재개 패턴은 고위험 유형에서 관찰됩니다.',
        'Transaction_Failure_Status':'직전 거래 실패 이력이 있습니다. 단시간 반복 시도와 결합 시 위험도가 높아집니다.',
        'Another_Person_Account':'본인 명의가 아닌 타인 계좌 관련 거래입니다. 명의도용·오픈뱅킹 악용의 핵심 지표입니다.',
        'Flag_deposit_more_than_tenMillion':'1천만 원 이상 고액 입금이 발생했습니다. 대출빙자·현금화 시도와 결합 시 주의가 필요합니다.',
    },
    'en': {
        'Customer_rooting_jailbreak_indicator':"The device is rooted (Android)/jailbroken (iOS). This enables bypassing security controls and installing malware, a key signal for remote-control and smishing types.",
        'Customer_VPN_Indicator':'Access via VPN. Can conceal the real access location; often seen in phishing and remote-control types.',
        'Customer_flag_terminal_malicious_behavior_1':'Malicious-behavior signal rule #1 detected by the device security module (internal detection criteria such as malware/hooking attempts).',
        'Customer_flag_terminal_malicious_behavior_2':'Malicious-behavior signal rule #2 detected by the device security module.',
        'Customer_flag_terminal_malicious_behavior_3':'Malicious-behavior signal rule #3 detected by the device security module.',
        'Unused_terminal_status':'Access from a device with no usage history for a long period. A suspected sign of device takeover or identity theft.',
        'Unused_account_status':'A sudden transaction occurred on a long-dormant account. A key indicator of an account anomaly pattern.',
        'Recipient_account_suspend_status':'The recipient (deposit-target) account is under payment suspension. May be a transfer attempt to an account with a fraud-report history.',
        'Account_release_suspention':'A status flag related to the suspension/release history of the transaction account. A pattern of release right after suspension and resumed transactions is observed in high-risk types.',
        'Transaction_Failure_Status':'There is a history of an immediately preceding failed transaction. Risk increases when combined with repeated short-interval attempts.',
        'Another_Person_Account':"A transaction related to an account not under the customer's own name. A key indicator of identity theft or Open Banking abuse.",
        'Flag_deposit_more_than_tenMillion':'A large deposit of 10 million KRW or more occurred. Caution is needed when combined with loan-scam or cash-out attempts.',
    },
    'ja': {
        'Customer_rooting_jailbreak_indicator':'取引端末がルート化(Android)/脱獄(iOS)された状態です。セキュリティ制御の回避・悪性アプリのインストールが可能になり、遠隔操作・スミッシング類型の主要シグナルです。',
        'Customer_VPN_Indicator':'VPN経由の接続です。実際の接続位置を隠蔽できるため、フィッシング・遠隔操作類型で頻繁に観察されます。',
        'Customer_flag_terminal_malicious_behavior_1':'端末セキュリティモジュールが検知した悪性行為シグナル1番ルールです（悪性アプリ・フッキング試行等の内部検知基準）。',
        'Customer_flag_terminal_malicious_behavior_2':'端末セキュリティモジュールが検知した悪性行為シグナル2番ルールです。',
        'Customer_flag_terminal_malicious_behavior_3':'端末セキュリティモジュールが検知した悪性行為シグナル3番ルールです。',
        'Unused_terminal_status':'長期間使用履歴のなかった端末からの接続です。端末乗っ取り・なりすましの疑いのシグナルです。',
        'Unused_account_status':'長期未使用口座で突然の取引が発生しました。口座異常パターンの主要指標です。',
        'Recipient_account_suspend_status':'受取（入金対象）口座が支給停止状態です。詐欺申告履歴のある口座への送金試行の可能性があります。',
        'Account_release_suspention':'取引口座の取引停止/解除履歴に関連する状態フラグです。停止直後の解除・取引再開パターンは高リスク類型で観察されます。',
        'Transaction_Failure_Status':'直前の取引失敗履歴があります。短時間の反復試行と結合すると危険度が高まります。',
        'Another_Person_Account':'本人名義でない他人口座関連の取引です。なりすまし・オープンバンキング悪用の主要指標です。',
        'Flag_deposit_more_than_tenMillion':'1000万ウォン以上の高額入金が発生しました。融資詐欺・現金化試行と結合する場合は注意が必要です。',
    },
    'zh': {
        'Customer_rooting_jailbreak_indicator':'交易终端处于root(Android)/越狱(iOS)状态。可绕过安全控制、安装恶意应用，是远程控制、短信钓鱼类型的核心信号。',
        'Customer_VPN_Indicator':'通过VPN接入。可隐藏真实接入位置，常见于网络钓鱼、远程控制类型。',
        'Customer_flag_terminal_malicious_behavior_1':'终端安全模块检测到的恶意行为信号规则1号（恶意应用、hooking尝试等内部检测标准）。',
        'Customer_flag_terminal_malicious_behavior_2':'终端安全模块检测到的恶意行为信号规则2号。',
        'Customer_flag_terminal_malicious_behavior_3':'终端安全模块检测到的恶意行为信号规则3号。',
        'Unused_terminal_status':'来自长期无使用记录终端的接入。是终端劫持、冒用身份的可疑信号。',
        'Unused_account_status':'长期未使用账户突然发生交易。是账户异常模式的主要指标。',
        'Recipient_account_suspend_status':'收款（入账对象）账户处于停止支付状态。可能是向有诈骗举报记录账户的转账尝试。',
        'Account_release_suspention':'与交易账户的停用/解除历史相关的状态标志。停用后立即解除并恢复交易的模式常见于高风险类型。',
        'Transaction_Failure_Status':'存在紧邻之前的交易失败记录。与短时间内反复尝试结合时风险度会提高。',
        'Another_Person_Account':'与非本人名义的他人账户相关的交易。是冒用身份、开放银行滥用的核心指标。',
        'Flag_deposit_more_than_tenMillion':'发生了1千万韩元以上的大额存款。与贷款诈骗、套现尝试结合时需要注意。',
    },
}

SESSION_LABELS_I18N = {
    'ko': ["📋 프로젝트 개요","📊 모델 성능","🔍 오탐·미탐 분석","🧪 합성데이터 QA","🚀 실시간 탐지 시연"],
    'en': ["📋 Project Overview","📊 Model Performance","🔍 FP/FN Analysis","🧪 Synthetic Data QA","🚀 Live Detection Demo"],
    'ja': ["📋 プロジェクト概要","📊 モデル性能","🔍 誤検知・見逃し分析","🧪 合成データQA","🚀 リアルタイム検知デモ"],
    'zh': ["📋 项目概览","📊 模型性能","🔍 误报/漏报分析","🧪 合成数据QA","🚀 实时检测演示"],
}

MODEL_DESC_I18N = {
    "LightGBM (기본)":    {"ko":"Gradient Boosting 기반 다중분류 — 기본 탐지 모델", "en":"Gradient Boosting multiclass — default detection model", "ja":"Gradient Boostingベース多クラス分類 — 基本検知モデル", "zh":"基于Gradient Boosting的多分类——默认检测模型"},
    "RandomForest":       {"ko":"앙상블 트리 기반 — 안정적 baseline", "en":"Ensemble tree-based — stable baseline", "ja":"アンサンブルツリーベース — 安定したベースライン", "zh":"基于集成树——稳定的基线模型"},
    "LogisticRegression": {"ko":"선형 모델 — 빠른 추론, 해석 용이", "en":"Linear model — fast inference, easy to interpret", "ja":"線形モデル — 高速推論、解釈容易", "zh":"线性模型——推理速度快，易于解释"},
    "XGBoost":            {"ko":"Gradient Boosting — LightGBM 대안", "en":"Gradient Boosting — an alternative to LightGBM", "ja":"Gradient Boosting — LightGBMの代替", "zh":"Gradient Boosting——LightGBM的替代方案"},
    "CatBoost":           {"ko":"범주형 피처 자동 처리 — 전처리 최소화", "en":"Automatic categorical-feature handling — minimal preprocessing", "ja":"カテゴリ特徴量自動処理 — 前処理最小化", "zh":"自动处理类别特征——最大限度减少预处理"},
    "MLP (신경망)":        {"ko":"다층 퍼셉트론 — 비선형 패턴 포착", "en":"Multi-layer perceptron — captures nonlinear patterns", "ja":"多層パーセプトロン — 非線形パターン捕捉", "zh":"多层感知机——捕捉非线性模式"},
}
_add("model.auto_discovered", "자동 발견된 모델", "Auto-discovered model", "自動発見モデル", "自动发现的模型")

THEME_LABEL_I18N = {
    "🌊 Cyber Teal":      {"ko":"기본 — 사이버 보안 다크", "en":"Default — Cyber-security Dark", "ja":"デフォルト — サイバーセキュリティダーク", "zh":"默认——网络安全暗色"},
    "🔥 Crimson Matrix":  {"ko":"사이버 공격 탐지 레드", "en":"Cyber-attack Detection Red", "ja":"サイバー攻撃検知レッド", "zh":"网络攻击检测红"},
    "🌌 Nebula Purple":   {"ko":"우주 성운 바이올렛", "en":"Cosmic Nebula Violet", "ja":"宇宙星雲バイオレット", "zh":"宇宙星云紫"},
    "🏔️ Arctic Frost":    {"ko":"라이트 모드 — 빙하 블루", "en":"Light Mode — Glacier Blue", "ja":"ライトモード — 氷河ブルー", "zh":"浅色模式——冰川蓝"},
    "🌿 Forest Terminal": {"ko":"매트릭스 그린 터미널", "en":"Matrix Green Terminal", "ja":"マトリックスグリーンターミナル", "zh":"矩阵绿色终端"},
    "🌅 Solar Gold":      {"ko":"프리미엄 골드 다크", "en":"Premium Gold Dark", "ja":"プレミアムゴールドダーク", "zh":"高级金色暗色"},
    "🎭 Phantom Noir":    {"ko":"모노크롬 초다크", "en":"Monochrome Ultra-dark", "ja":"モノクローム超ダーク", "zh":"单色超暗"},
}

# 신 UI 테마 — 내부 안정 키(dark/light/...) + 언어별 표시명/설명
NEW_THEME_META_I18N = {
    'dark':          {"display": {"ko":"🌙 다크","en":"🌙 Dark","ja":"🌙 ダーク","zh":"🌙 深色"},        "label": {"ko":"미드나이트 콘솔","en":"Midnight Console","ja":"ミッドナイトコンソール","zh":"午夜控制台"}},
    'light':         {"display": {"ko":"☀️ 라이트","en":"☀️ Light","ja":"☀️ ライト","zh":"☀️ 浅色"},       "label": {"ko":"페이퍼 콘솔","en":"Paper Console","ja":"ペーパーコンソール","zh":"纸质控制台"}},
    'amber':         {"display": {"ko":"🥃 앰버 그래파이트","en":"🥃 Amber Graphite","ja":"🥃 アンバーグラファイト","zh":"🥃 琥珀石墨"}, "label": {"ko":"야간 관제 앰버 (다크)","en":"Night-watch Amber (Dark)","ja":"夜間管制アンバー（ダーク）","zh":"夜间管控琥珀（深色）"}},
    'evergreen':     {"display": {"ko":"🌲 에버그린","en":"🌲 Evergreen","ja":"🌲 エバーグリーン","zh":"🌲 常青"},   "label": {"ko":"포레스트 콘솔 (다크)","en":"Forest Console (Dark)","ja":"フォレストコンソール（ダーク）","zh":"森林控制台（深色）"}},
    'ivory':         {"display": {"ko":"🏛 아이보리 뱅커","en":"🏛 Ivory Banker","ja":"🏛 アイボリーバンカー","zh":"🏛 象牙银行家"}, "label": {"ko":"클래식 프라이빗 뱅킹 (라이트)","en":"Classic Private Banking (Light)","ja":"クラシックプライベートバンキング（ライト）","zh":"经典私人银行（浅色）"}},
    'crimson':       {"display": {"ko":"🩸 크림슨 시그널","en":"🩸 Crimson Signal","ja":"🩸 クリムゾンシグナル","zh":"🩸 深红信号"}, "label": {"ko":"크림슨 워룸 (다크)","en":"Crimson War Room (Dark)","ja":"クリムゾン作戦室（ダーク）","zh":"深红作战室（深色）"}},
    'slate':         {"display": {"ko":"🌌 슬레이트 바이올렛","en":"🌌 Slate Violet","ja":"🌌 スレートバイオレット","zh":"🌌 板岩紫"}, "label": {"ko":"듀스크 슬레이트 (다크)","en":"Dusk Slate (Dark)","ja":"ダスクスレート（ダーク）","zh":"暮色板岩（深色）"}},
}
NEW_THEME_ORDER = ['dark','light','amber','evergreen','ivory','crimson','slate']

# 세션04 적합성 검증 항목 라벨
CHECK_LABEL_I18N = {
    'Transaction_Amount': {"ko":"이체 금액","en":"Transfer Amount","ja":"振込金額","zh":"转账金额"},
    'Distance':           {"ko":"거래 거리","en":"Transaction Distance","ja":"取引距離","zh":"交易距离"},
    'Account_balance':    {"ko":"계좌 잔액","en":"Account Balance","ja":"口座残高","zh":"账户余额"},
}

# 세션01 핵심 가설 (코드, 제목, 설명) — 언어별
HYPOTHESES_I18N = {
 'ko': [("H1","Accuracy는 성능을 왜곡","전부 정상(m)으로 예측해도 Accuracy ≈82% → Macro-F1·클래스별 Recall이 타당한 지표"),
        ("H2","LightGBM이 규칙 기반 대비 우수","Gradient Boosting 계열이 다중분류 탐지 성능을 유의미하게 개선"),
        ("H3","비용 기반 임계값이 효과적","FP/FN 비용 기반 임계값 조정 시 운영 기대비용 최소화 가능"),
        ("H4","시간 분할이 보수적·현실적","Transaction_Datetime 기준 분할이 랜덤 분할보다 실제 성능에 근접"),
        ("H5","전처리 방식이 성능에 영향","결측치 처리 방식에 따라 탐지 결과가 유의미하게 달라짐"),
        ("H6","특정 세그먼트에 오류 편중","금액대·채널·OS별로 오탐/미탐이 집중되어 운영 리스크가 편향됨")],
 'en': [("H1","Accuracy distorts performance","Predicting all-Normal (m) still gives Accuracy ≈82% → Macro-F1 and per-class Recall are the valid metrics"),
        ("H2","LightGBM outperforms rule-based","Gradient Boosting models meaningfully improve multiclass detection performance"),
        ("H3","Cost-based threshold is effective","Tuning the threshold based on FP/FN cost can minimize the operational expected cost"),
        ("H4","Time-based split is conservative and realistic","Splitting by Transaction_Datetime tracks real-world performance more closely than a random split"),
        ("H5","Preprocessing choices affect performance","Detection results vary meaningfully depending on how missing values are handled"),
        ("H6","Errors concentrate in specific segments","FP/FN are concentrated by amount band, channel, and OS, skewing operational risk")],
 'ja': [("H1","Accuracyは性能を歪める","全て正常(m)と予測してもAccuracy≈82% → Macro-F1・クラス別Recallが妥当な指標"),
        ("H2","LightGBMがルールベース対比優秀","Gradient Boosting系が多クラス検知性能を有意に改善"),
        ("H3","コストベース閾値が効果的","FP/FNコストベースの閾値調整で運用期待コストを最小化可能"),
        ("H4","時系列分割が保守的・現実的","Transaction_Datetime基準の分割がランダム分割より実性能に近い"),
        ("H5","前処理方式が性能に影響","欠損値処理方式により検知結果が有意に変化"),
        ("H6","特定セグメントにエラー偏重","金額帯・チャネル・OS別に誤検知/見逃しが集中し運用リスクが偏る")],
 'zh': [("H1","Accuracy会扭曲性能评估","即使全部预测为正常(m)，Accuracy仍≈82% → Macro-F1和各类别Recall才是合理指标"),
        ("H2","LightGBM优于基于规则的方法","Gradient Boosting系列显著改善多分类检测性能"),
        ("H3","基于成本的阈值调整有效","基于FP/FN成本调整阈值可最小化运营期望成本"),
        ("H4","按时间划分更保守、更贴近实际","按Transaction_Datetime划分比随机划分更接近真实性能"),
        ("H5","预处理方式影响性能","缺失值处理方式不同会显著改变检测结果"),
        ("H6","错误集中在特定分段","误报/漏报按金额区间、渠道、操作系统集中，导致运营风险偏斜")],
}
# -*- coding: utf-8 -*-
# ══════════════════════════════════════════════════════════
# i18n 추가 키 — v5 업데이트 (배치 분석 · 동적 평가 · 데이터셋 선택)
# 사용법: 이 파일 내용을 i18n_data.py 맨 아래(마지막 _add 뒤)에 붙여넣기
# (_add 헬퍼가 이미 정의돼 있으므로 그대로 동작)
# ══════════════════════════════════════════════════════════

# ── 데이터셋 선택 (사이드바/세션2 공용) ──
_add("ds.section", "데이터셋", "Dataset", "データセット", "数据集")
_add("ds.select_label", "평가 데이터셋 선택", "Select evaluation dataset", "評価データセットを選択", "选择评估数据集")
_add("ds.folder_label", "데이터 폴더", "Data folder", "データフォルダ", "数据文件夹")
_add("ds.rescan", "🔄 다시 검색", "🔄 Rescan", "🔄 再スキャン", "🔄 重新扫描")
_add("ds.none_found", "⚠ 폴더에서 데이터셋을 찾지 못했습니다 (CSV/Parquet)", "⚠ No datasets found in folder (CSV/Parquet)", "⚠ フォルダにデータセットが見つかりません (CSV/Parquet)", "⚠ 文件夹中未找到数据集 (CSV/Parquet)")
_add("ds.no_label_warn", "선택한 데이터셋에 라벨(Fraud_Type)이 없어 평가할 수 없습니다 — 예측 전용", "Selected dataset has no label (Fraud_Type) — prediction only", "選択したデータセットにラベル(Fraud_Type)がなく評価できません — 予測専用", "所选数据集没有标签(Fraud_Type)，无法评估 — 仅供预测")
_add("ds.loaded_info", "데이터셋 로드: {name} — {n:,}행 · {note}", "Dataset loaded: {name} — {n:,} rows · {note}", "データセット読込: {name} — {n:,}行・{note}", "已加载数据集: {name} — {n:,} 行 · {note}")
_add("ds.xy_join_note", "X/y 분할 Parquet — 자동 결합됨", "Split X/y Parquet — auto-joined", "X/y分割Parquet — 自動結合済み", "X/y 拆分 Parquet — 已自动合并")

# ── 세션 2 동적 평가 ──
_add("s2.mode_label", "평가 모드", "Evaluation mode", "評価モード", "评估模式")
_add("s2.mode_static", "학습 시점 리포트 (eval_result.json)", "Training-time report (eval_result.json)", "学習時レポート (eval_result.json)", "训练时报告 (eval_result.json)")
_add("s2.mode_dynamic", "실시간 재평가 (선택 데이터셋 × 모델)", "Live re-evaluation (dataset × models)", "リアルタイム再評価（データセット×モデル）", "实时重新评估（数据集 × 模型）")
_add("s2.model_multi_label", "비교할 모델 (최대 3개)", "Models to compare (max 3)", "比較するモデル（最大3）", "要比较的模型（最多3个）")
_add("s2.run_eval_button", "⚡ 평가 실행", "⚡ Run evaluation", "⚡ 評価実行", "⚡ 运行评估")
_add("s2.eval_spinner", "선택 데이터셋으로 {n}개 모델 평가 중...", "Evaluating {n} models on selected dataset...", "選択データセットで{n}モデルを評価中...", "正在用所选数据集评估 {n} 个模型...")
_add("s2.eval_size_note", "평가 표본: {n:,}건 (성능을 위해 최대 {max:,}건 샘플링)", "Eval sample: {n:,} rows (capped at {max:,} for responsiveness)", "評価サンプル: {n:,}件（応答性のため最大{max:,}件）", "评估样本: {n:,} 条（为保证响应速度上限 {max:,} 条）")
_add("s2.eval_fail", "평가 실패: {e}", "Evaluation failed: {e}", "評価失敗: {e}", "评估失败: {e}")
_add("s2.cost_real_title", "임계값 기대비용 분석 (실측)", "Threshold Expected-Cost (measured)", "閾値期待コスト分析（実測）", "阈值期望成本分析（实测）")
_add("s2.cost_fn_unit", "미탐 1건 비용(원)", "Cost per FN", "FN1件あたりコスト", "单次漏报成本")
_add("s2.cost_fp_unit", "오탐 1건 비용(원)", "Cost per FP", "FP1件あたりコスト", "单次误报成本")
_add("s2.cost_optimal", "최적 임계값 {th} (총비용 최소)", "Optimal threshold {th} (min total cost)", "最適閾値 {th}（総コスト最小）", "最优阈值 {th}（总成本最小）")
_add("s2.model_fmt_badge", "형식: {fmt}", "Format: {fmt}", "形式: {fmt}", "格式: {fmt}")

# ── 세션 5 배치 분석 ──
_add("s5.batch_button", "📦 일괄 분석 ({n}건)", "📦 Batch analyze ({n})", "📦 一括分析（{n}件）", "📦 批量分析（{n} 条）")
_add("s2.no_model_loaded", "선택한 모델을 하나도 로드하지 못했습니다 — 각 오류 메시지를 확인하세요", "No selected model could be loaded — check each error message", "選択したモデルを1つも読み込めませんでした — 各エラーを確認してください", "所选模型均未能加载 — 请检查各错误信息")
_add("s2.cm_error_hint", "🟥 붉은 셀 = 오탐/미탐 (대각선 밖 예측 오류)", "🟥 Red cells = misclassifications (off-diagonal errors)", "🟥 赤いセル = 誤検知/見逃し（対角線外の予測誤り）", "🟥 红色单元格 = 误报/漏报（对角线外的预测错误）")
_add("s5.batch_spinner", "배치 분석 중... ({i}/{n})", "Batch analyzing... ({i}/{n})", "バッチ分析中... ({i}/{n})", "批量分析中... ({i}/{n})")
_add("s5.batch_min_warn", "일괄 분석은 2건 이상일 때 사용할 수 있습니다", "Batch analysis requires 2+ rows", "一括分析には2件以上必要です", "批量分析需要至少 2 条数据")
_add("s5.batch_result_title", "배치 분석 결과", "Batch Analysis Result", "バッチ分析結果", "批量分析结果")
_add("s5.batch_kpi_total", "전체 거래", "Total", "全取引", "总交易数")
_add("s5.batch_kpi_anomaly", "이상 거래", "Anomalies", "異常取引", "异常交易")
_add("s5.batch_kpi_avg", "평균 위험", "Avg risk", "平均リスク", "平均风险")
_add("s5.batch_kpi_max", "최고 위험", "Max risk", "最高リスク", "最高风险")
_add("s5.batch_summary_label", "탐지 요약", "Summary", "検知要約", "检测摘要")
_add("s5.batch_report_title", "🧾 배치 AI 분석 보고서", "🧾 Batch AI Report", "🧾 バッチAI分析レポート", "🧾 批量 AI 分析报告")
_add("s5.batch_table_title", "건별 판정 결과", "Per-row verdicts", "件別判定結果", "逐条判定结果")
_add("s5.batch_llm_fallback_note", "⚠ LLM 미연결 — 집계 기반 폴백 보고서입니다", "⚠ LLM unavailable — rule-based fallback report", "⚠ LLM未接続 — 集計ベースの代替レポート", "⚠ LLM 未连接 — 基于统计的兜底报告")
_add("s5.batch_send_slack", "📨 Slack 발송", "📨 Send Slack", "📨 Slack送信", "📨 发送 Slack")
_add("s5.batch_send_email", "📧 Email 발송", "📧 Send Email", "📧 メール送信", "📧 发送邮件")
_add("s5.batch_clear", "🗑 배치 결과 지우기", "🗑 Clear batch result", "🗑 バッチ結果をクリア", "🗑 清除批量结果")
_add("s5.batch_accuracy_note", "정답 보유 {n}건 중 유형 일치 {hit}건 ({pct:.1f}%)", "Of {n} labeled rows, {hit} type-matched ({pct:.1f}%)", "正解あり{n}件中、型一致{hit}件（{pct:.1f}%）", "有标签 {n} 条中类型匹配 {hit} 条（{pct:.1f}%）")

_add("s5.batch_download_csv", "⬇️ 결과 CSV", "⬇️ Result CSV", "⬇️ 結果CSV", "⬇️ 结果CSV")

_add("s2.ratio_toggle", "비율(%)로 보기 — 실제 유형별 예측 분포", "Show as % — per-true-class distribution", "比率(%)で表示 — 実際タイプ別予測分布", "按比例(%)显示 — 各真实类型的预测分布")
_add("s3.ratio_toggle", "비율(%)로 보기", "Show as %", "比率(%)で表示", "按比例(%)显示")
_add("s2.zero_f1_warn", "⚠ F1=0 유형: {types} — 모델이 해당 유형을 전혀 정탐하지 못했습니다 (혼동행렬의 해당 행 참조)", "⚠ F1=0 classes: {types} — the model never detects these (see corresponding CM rows)", "⚠ F1=0 タイプ: {types} — モデルが全く検知できていません（混同行列の該当行を参照）", "⚠ F1=0 类型: {types} — 模型完全未能识别（参见混淆矩阵对应行）")
_add("s2.adapt_note_prefix", "자동 피처 매칭 적용", "Auto feature-matching applied", "自動特徴量マッチング適用", "已应用自动特征匹配")

_add("s2.sample_cap_label", "표본 상한", "Sample cap", "サンプル上限", "样本上限")
_add("s2.low_support_warn", "⚠ 표본 10건 미만 유형: {types} — 해당 유형 지표는 통계적으로 불안정합니다", "⚠ Classes with <10 samples: {types} — metrics for these are statistically unstable", "⚠ サンプル10件未満のタイプ: {types} — 指標は統計的に不安定です", "⚠ 样本不足10条的类型: {types} — 指标在统计上不稳定")
_add("s2.absent_class_note", "ℹ 이 데이터셋에 없는 유형: {types} (지표 0으로 표시)", "ℹ Classes absent from this dataset: {types} (shown as 0)", "ℹ このデータセットに存在しないタイプ: {types}（0と表示）", "ℹ 此数据集中不存在的类型: {types}（显示为0）")

_add("s2.skipped_models", "⚠ 데이터셋과 피처 계열이 달라 평가에서 제외된 모델:<br>{models}", "⚠ Models skipped — feature mismatch:<br>{models}", "⚠ 特徴量不一致でスキップ:<br>{models}", "⚠ 特征不匹配，已跳过:<br>{models}")
_add("s5.tab3_src_label", "데이터 소스", "Data source", "データソース", "数据来源")
_add("s5.tab3_src_csv", "📄 원본 CSV (train.csv)", "📄 Raw CSV", "📄 元データCSV", "📄 原始CSV")
_add("s5.tab3_src_pq", "📦 전처리 완료 (Parquet)", "📦 Engineered (Parquet)", "📦 前処理済み (Parquet)", "📦 已预处理 (Parquet)")

_add("s5.batch_reroll", "재분석", "Re-analyze", "再分析", "重新分析")

# ══════════════════════════════════════════════════════════
# ✨ 리치 알림 (Slack/Email 시각화) — v8 신규
# ══════════════════════════════════════════════════════════
_add("notif.rich_toggle", "📊 리치 알림 (시각 요약)", "📊 Rich alerts (visual summary)", "📊 リッチ通知（視覚サマリー）", "📊 富通知（可视化摘要）")
_add("notif.rich_help", "Slack엔 텍스트 게이지·분포, 이메일엔 KPI 카드·막대 차트와 인터랙티브 HTML 리포트 첨부를 더합니다", "Adds text gauges to Slack, KPI cards + bar charts to email, and attaches an interactive HTML report", "Slackにテキストゲージ、メールにKPIカード・棒グラフとインタラクティブHTMLレポート添付を追加します", "为Slack添加文本仪表，为邮件添加KPI卡片、条形图及交互式HTML报告附件")
_add("notif.risk", "위험", "Risk", "リスク", "风险")
_add("notif.thr", "임계", "thr", "閾値", "阈值")
_add("notif.prob", "확률", "Prob", "確率", "概率")
_add("notif.prob_top", "클래스별 확률 (상위 5)", "Class probabilities (top 5)", "クラス別確率（上位5）", "各类别概率（前5）")
_add("notif.cnt", "건", "", "件", "条")
_add("notif.risk_dist", "위험도 분포", "Risk distribution", "リスク分布", "风险分布")
_add("notif.type_dist", "이상거래 유형 분포", "Anomaly type distribution", "異常取引タイプ分布", "异常交易类型分布")
_add("notif.attached", "상세 인터랙티브 리포트가 첨부되어 있습니다 — 브라우저에서 열어보세요.", "An interactive detail report is attached — open it in a browser.", "詳細なインタラクティブレポートが添付されています — ブラウザで開いてください。", "已附上交互式详细报告 — 请在浏览器中打开。")
_add("notif.auto_note", "본 메일은 이상거래 탐지 시스템에서 자동 발송되었습니다.", "This email was sent automatically by the fraud detection system.", "このメールは不正検知システムから自動送信されました。", "此邮件由异常交易检测系统自动发送。")
_add("notif.masked", "거래 데이터 (마스킹 적용)", "Transaction data (masked)", "取引データ（マスキング済み）", "交易数据（已脱敏）")
_add("notif.analysis", "AI 분석", "AI analysis", "AI分析", "AI 分析")
_add("notif.verdicts", "건별 판정", "Per-row verdicts", "件別判定", "逐条判定")
_add("notif.report_title_single", "FDS 이상거래 탐지 리포트", "FDS Detection Report", "FDS異常検知レポート", "FDS 异常检测报告")
_add("notif.report_title_batch", "FDS 배치 분석 리포트", "FDS Batch Report", "FDSバッチ分析レポート", "FDS 批量分析报告")

# ══════════════════════════════════════════════════════════
# 🔧 호환성 경고 (신규 전처리 스키마 대응) — v8에서 i18n 편입
# ══════════════════════════════════════════════════════════
_add("compat.s1_fallback", "⚠ 선택 데이터셋 <b>{name}</b>에 Fraud_Type 라벨이 없어 train.csv로 대체 표시합니다 — 새 전처리 parquet이라면 라벨 컬럼명(Fraud_Type/label/target/y)을 확인하세요", "⚠ Selected dataset <b>{name}</b> has no Fraud_Type label — showing train.csv instead. For new parquet, check the label column name (Fraud_Type/label/target/y)", "⚠ 選択データセット<b>{name}</b>にFraud_Typeラベルがないため、train.csvで代替表示します — 新しいparquetの場合はラベル列名を確認してください", "⚠ 所选数据集<b>{name}</b>缺少Fraud_Type标签，已回退显示train.csv — 新parquet请检查标签列名")
_add("compat.s3_fallback", "⚠ 선택 데이터셋 <b>{name}</b>은 라벨 또는 세그먼트 컬럼(Channel/OS/접근매체 등)이 없어 train.csv로 대체 분석합니다", "⚠ Dataset <b>{name}</b> lacks label or segment columns (Channel/OS/etc.) — falling back to train.csv", "⚠ データセット<b>{name}</b>にラベルまたはセグメント列がないため、train.csvで代替分析します", "⚠ 数据集<b>{name}</b>缺少标签或分段列 — 已回退到train.csv进行分析")
_add("compat.s3_no_amount", "⚠ 이 데이터셋에는 <b>Transaction_Amount</b>(또는 _abs/is_withdrawal 쌍) 컬럼이 없어 금액대 분석을 건너뜁니다", "⚠ No <b>Transaction_Amount</b> (or _abs/is_withdrawal pair) in this dataset — skipping amount-band analysis", "⚠ <b>Transaction_Amount</b>（または_abs/is_withdrawalペア）がないため、金額帯分析をスキップします", "⚠ 此数据集缺少<b>Transaction_Amount</b>（或_abs/is_withdrawal对）— 跳过金额段分析")
_add("compat.s3_amount_restored", "🔗 Transaction_Amount 복원 — Transaction_Amount_abs × (출금이면 −1)", "🔗 Transaction_Amount reconstructed — Transaction_Amount_abs × (−1 if withdrawal)", "🔗 Transaction_Amount復元 — Transaction_Amount_abs ×（出金なら−1）", "🔗 已重建Transaction_Amount — Transaction_Amount_abs ×（取款则为−1）")
_add("compat.s3_no_flags", "⚠ 이 데이터셋에는 위험 플래그 컬럼(BINARY_FLAGS 12종)이 하나도 없어 플래그 분석을 건너뜁니다", "⚠ None of the 12 BINARY_FLAGS columns exist in this dataset — skipping flag analysis", "⚠ リスクフラグ列（BINARY_FLAGS 12種）が存在しないため、フラグ分析をスキップします", "⚠ 此数据集不含任何风险标志列（12种BINARY_FLAGS）— 跳过标志分析")
_add("compat.t3_label_decode", "⚠ 이 parquet의 라벨이 'a'~'m'으로 디코딩되지 않았습니다 — models/le_target.pkl(새 전처리 기준)을 배치했는지 확인하세요", "⚠ Labels in this parquet were not decoded to 'a'~'m' — check that models/le_target.pkl (from the new preprocessing) is in place", "⚠ このparquetのラベルが'a'〜'm'にデコードされていません — models/le_target.pklを確認してください", "⚠ 此parquet的标签未解码为'a'~'m' — 请确认已放置models/le_target.pkl")
_add("compat.leak_t3", "🚨 <b>is_fraud</b> 컬럼 발견 — 라벨과 동일한 정보(라벨 누출)입니다. 이 컬럼이 학습에 포함된 모델은 평가가 무의미하며, 실시간 입력에는 이 값이 없어 예측이 왜곡됩니다. 전처리 담당자에게 제거를 요청하세요", "🚨 <b>is_fraud</b> column found — it duplicates the label (label leakage). Models trained with it have meaningless metrics and distorted live predictions. Ask the preprocessing owner to remove it", "🚨 <b>is_fraud</b>列を検出 — ラベルと同一情報（ラベルリーク）です。前処理担当者に削除を依頼してください", "🚨 发现<b>is_fraud</b>列 — 与标签完全相同（标签泄漏）。请要求预处理负责人删除该列")
_add("compat.leak_s2", "🚨 데이터셋에 <b>is_fraud</b>(라벨 누출) 컬럼이 있습니다 — 이 컬럼을 피처로 쓰는 모델의 지표는 허위로 완벽하게 나옵니다. 결과 해석에 주의하고, 전처리 담당자에게 제거를 요청하세요", "🚨 Dataset contains <b>is_fraud</b> (label leakage) — models using it as a feature will show falsely perfect metrics. Interpret with care and ask for its removal", "🚨 データセットに<b>is_fraud</b>（ラベルリーク）列があります — 指標が虚偽的に完璧になります。解釈に注意してください", "🚨 数据集包含<b>is_fraud</b>（标签泄漏）列 — 使用它的模型指标会虚假完美。请谨慎解读并要求删除")

# ══════════════════════════════════════════════════════════
# 🩺 호환성 진단(Schema Doctor) + 🗃 DB 이력 뷰어 — v8 신규
# ══════════════════════════════════════════════════════════
_add("doc.expander", "🩺 호환성 진단 — 데이터셋 × 모델", "🩺 Schema doctor — dataset × model", "🩺 互換性診断 — データセット × モデル", "🩺 兼容性诊断 — 数据集 × 模型")
_add("doc.desc", "선택한 데이터셋과 모델의 스키마 호환성을 자동 점검합니다. 재학습 모델 교체 직후 1회 실행을 권장합니다.", "Automatically checks schema compatibility between the selected dataset and model. Run once right after swapping in retrained models.", "選択したデータセットとモデルのスキーマ互換性を自動点検します。再学習モデル差し替え直後の実行を推奨します。", "自动检查所选数据集与模型的架构兼容性。建议在替换重训模型后立即运行一次。")
_add("doc.run", "🩺 진단 실행", "🩺 Run diagnosis", "🩺 診断実行", "🩺 运行诊断")
_add("doc.target", "진단 대상: 📂 {ds} × 🧠 {model}", "Target: 📂 {ds} × 🧠 {model}", "診断対象: 📂 {ds} × 🧠 {model}", "诊断对象: 📂 {ds} × 🧠 {model}")
_add("doc.spinner", "스키마 대조 중...", "Checking schemas...", "スキーマ照合中...", "正在比对架构...")
_add("doc.ds_missing", "🚨 데이터셋 '{name}'을 폴더에서 찾지 못했습니다 — 사이드바에서 데이터셋을 선택하세요", "🚨 Dataset '{name}' not found — select one in the sidebar", "🚨 データセット'{name}'が見つかりません — サイドバーで選択してください", "🚨 未找到数据集'{name}' — 请在侧边栏选择")
_add("doc.ds_ok", "✅ 데이터셋 인식: {name} ({kind}) — {note}", "✅ Dataset recognized: {name} ({kind}) — {note}", "✅ データセット認識: {name} ({kind}) — {note}", "✅ 数据集已识别: {name} ({kind}) — {note}")
_add("doc.load_fail", "🚨 데이터셋 로드 실패: {e}", "🚨 Dataset load failed: {e}", "🚨 データセット読込失敗: {e}", "🚨 数据集加载失败: {e}")
_add("doc.no_label", "⚠ 라벨(Fraud_Type) 없음 — 예측 전용, 평가·정답 비교 불가", "⚠ No label (Fraud_Type) — prediction only; evaluation unavailable", "⚠ ラベルなし — 予測専用、評価不可", "⚠ 无标签 — 仅可预测，无法评估")
_add("doc.label_ok", "✅ 라벨 디코딩 정상 — 'a'~'m' {pct:.1f}% · 정상(m) 비율 {mratio:.1f}%", "✅ Label decoding OK — 'a'~'m' {pct:.1f}% · normal(m) ratio {mratio:.1f}%", "✅ ラベルデコード正常 — 'a'〜'm' {pct:.1f}% · 正常(m)比率 {mratio:.1f}%", "✅ 标签解码正常 — 'a'~'m' {pct:.1f}% · 正常(m)比例 {mratio:.1f}%")
_add("doc.label_bad", "🚨 라벨이 'a'~'m'으로 디코딩되지 않음 — models/le_target.pkl(새 전처리 기준) 배치 필요", "🚨 Labels not decoded to 'a'~'m' — place the new models/le_target.pkl", "🚨 ラベルが'a'〜'm'にデコードされていません — 新しいle_target.pklを配置してください", "🚨 标签未解码为'a'~'m' — 请放置新的le_target.pkl")
_add("doc.leak", "🚨 라벨 누출 의심 컬럼: {cols} — 라벨과 일치율 99.9% 이상. 학습 전 제거 필수", "🚨 Suspected label-leak columns: {cols} — ≥99.9% identical to the label. Must be removed before training", "🚨 ラベルリーク疑い列: {cols} — ラベルと99.9%以上一致。学習前に削除必須", "🚨 疑似标签泄漏列: {cols} — 与标签一致率≥99.9%。训练前必须删除")
_add("doc.const", "⚠ 상수 컬럼(판별력 0): {cols}", "⚠ Constant columns (zero signal): {cols}", "⚠ 定数列（判別力0）: {cols}", "⚠ 常量列（无判别力）: {cols}")
_add("doc.nan", "⚠ NaN 보유 컬럼 {n}개: {cols} — LGBM/XGB는 무관, LogReg/ONNX 계열은 fillna 필요", "⚠ {n} columns with NaN: {cols} — fine for LGBM/XGB; LogReg/ONNX need fillna", "⚠ NaN保有列{n}個: {cols} — LGBM/XGBは問題なし、LogReg/ONNX系はfillna必要", "⚠ 含NaN的列{n}个: {cols} — LGBM/XGB无碍，LogReg/ONNX需fillna")
_add("doc.nan_none", "✅ NaN 없음", "✅ No NaN values", "✅ NaNなし", "✅ 无NaN")
_add("doc.model_fail", "🚨 모델 로드 실패: {e}", "🚨 Model load failed: {e}", "🚨 モデル読込失敗: {e}", "🚨 模型加载失败: {e}")
_add("doc.feat_noname", "⚠ 모델에 피처명 기록 없음 — 위치 기반 입력이라 컬럼 순서가 다르면 조용히 오예측합니다 (DataFrame으로 재학습 권장)", "⚠ Model stores no feature names — positional input silently mispredicts if column order differs (retrain with a DataFrame)", "⚠ モデルに特徴量名の記録なし — 列順が異なると静かに誤予測します（DataFrameでの再学習推奨）", "⚠ 模型未记录特征名 — 列顺序不同将静默误判（建议用DataFrame重训）")
_add("doc.feat_ok", "✅ 피처 완전 일치 — 모델 기대 {n}개 전부 데이터셋에 존재", "✅ Features fully match — all {n} expected features present", "✅ 特徴量完全一致 — 期待{n}個すべて存在", "✅ 特征完全匹配 — 期望的{n}个全部存在")
_add("doc.feat_partial", "⚠ 피처 부분 일치 — {miss}/{n}개 누락 (예: {ex}) → 기본값 대체로 평가는 진행되나 지표가 왜곡될 수 있음", "⚠ Partial feature match — {miss}/{n} missing (e.g. {ex}) → evaluation proceeds with defaults but metrics may distort", "⚠ 特徴量部分一致 — {miss}/{n}個欠落（例: {ex}）→ 既定値で進むが指標が歪む可能性", "⚠ 特征部分匹配 — 缺失{miss}/{n}个（如: {ex}）→ 以默认值继续但指标可能失真")
_add("doc.feat_bad", "🚨 피처 계열 불일치 — {miss}/{n}개 누락 (예: {ex}) → 이 데이터셋×모델 조합은 평가 불가", "🚨 Feature family mismatch — {miss}/{n} missing (e.g. {ex}) → this dataset×model pair cannot be evaluated", "🚨 特徴量系列不一致 — {miss}/{n}個欠落（例: {ex}）→ この組み合わせは評価不可", "🚨 特征系不匹配 — 缺失{miss}/{n}个（如: {ex}）→ 此组合无法评估")
_add("doc.extra_note", "ℹ 데이터셋 전용 컬럼 {n}개 (모델 미사용): {cols}", "ℹ {n} dataset-only columns (unused by model): {cols}", "ℹ データセット専用列{n}個（モデル未使用）: {cols}", "ℹ 数据集独有列{n}个（模型未使用）: {cols}")
_add("doc.meta_ok", "✅ 메타 4종 세트 존재 — label_encoders · le_target · feature_cols · feature_defaults", "✅ Meta set complete — label_encoders · le_target · feature_cols · feature_defaults", "✅ メタ4点セット存在", "✅ 元数据4件套齐全")
_add("doc.meta_miss", "⚠ 메타 파일 누락: {files} — 세션 5 원본 입력 경로가 더미 모드/왜곡 예측이 될 수 있음", "⚠ Missing meta files: {files} — session 5 raw-input paths may fall to dummy mode or distorted predictions", "⚠ メタファイル欠落: {files} — セッション5の元データ入力が正しく動かない可能性", "⚠ 缺少元数据文件: {files} — 会话5原始输入路径可能异常")
_add("doc.bridge_note", "ℹ feature_bridge.pkl 존재 — 모델을 재학습했다면 삭제 후 자동 재학습 권장 (구 변환 규칙 잔존 위험)", "ℹ feature_bridge.pkl exists — if models were retrained, delete it so it auto-refits (stale transform risk)", "ℹ feature_bridge.pkl存在 — モデル再学習後は削除して自動再学習を推奨", "ℹ 存在feature_bridge.pkl — 若已重训模型建议删除以便自动重建")
_add("doc.summary", "진단 완료 — ✅ {ok} · ⚠ {warn} · 🚨 {err}", "Diagnosis complete — ✅ {ok} · ⚠ {warn} · 🚨 {err}", "診断完了 — ✅ {ok} · ⚠ {warn} · 🚨 {err}", "诊断完成 — ✅ {ok} · ⚠ {warn} · 🚨 {err}")
_add("db.expander", "🗃 누적 탐지 이력 — 영구 DB ({n}건)", "🗃 Detection history — persistent DB ({n} rows)", "🗃 累積検知履歴 — 永続DB（{n}件）", "🗃 累计检测历史 — 持久DB（{n}条）")
_add("db.empty", "아직 저장된 탐지 기록이 없습니다 — 탐지를 실행하면 fds_results.db에 자동 적재됩니다", "No saved detections yet — running a detection auto-saves to fds_results.db", "保存された検知記録はまだありません — 検知実行でfds_results.dbに自動保存されます", "尚无保存的检测记录 — 执行检测后将自动存入fds_results.db")
_add("db.kpi", "누적 {n}건 · 이상 {anom}건 ({pct:.1f}%) · 최근 {last}", "Total {n} · anomalies {anom} ({pct:.1f}%) · last {last}", "累積{n}件 · 異常{anom}件（{pct:.1f}%）· 直近 {last}", "累计{n}条 · 异常{anom}条（{pct:.1f}%）· 最近 {last}")
_add("db.csv", "⬇️ 이력 CSV", "⬇️ History CSV", "⬇️ 履歴CSV", "⬇️ 历史CSV")
_add("db.clear", "🗑 DB 이력 비우기", "🗑 Clear DB history", "🗑 DB履歴をクリア", "🗑 清空DB历史")
_add("db.cleared", "DB 이력을 비웠습니다", "DB history cleared", "DB履歴をクリアしました", "已清空DB历史")
_add("db.read_fail", "DB 읽기 실패: {e}", "DB read failed: {e}", "DB読込失敗: {e}", "DB读取失败: {e}")

# ── 📮 알림 진단 (v8.1) ──
_add("notif.smtp_ok", "✅ SMTP 연결·로그인 성공 — {detail}", "✅ SMTP connect & login OK — {detail}", "✅ SMTP接続・ログイン成功 — {detail}", "✅ SMTP连接·登录成功 — {detail}")
_add("notif.smtp_fail", "🚨 SMTP 실패 — {detail}", "🚨 SMTP failed — {detail}", "🚨 SMTP失敗 — {detail}", "🚨 SMTP失败 — {detail}")
_add("notif.send_fail_reason", "📧 메일 발송 실패 사유: {e}", "📧 Email send failure: {e}", "📧 メール送信失敗の理由: {e}", "📧 邮件发送失败原因: {e}")
_add("notif.slack_fail_reason", "📨 Slack 발송 실패 사유: {e}", "📨 Slack send failure: {e}", "📨 Slack送信失敗の理由: {e}", "📨 Slack发送失败原因: {e}")

# ── 📮 수신 주소 폴백 표시 (v8.2) ──
_add("notif.recipient_fallback", "↳ 비워두면 .env 값 사용 — 현재 수신: {addr}", "↳ Empty = use .env — current recipient: {addr}", "↳ 空欄なら.env値を使用 — 現在の宛先: {addr}", "↳ 留空则使用.env — 当前收件人: {addr}")
_add("notif.recipient_none", "⚠ 수신 주소 없음 — 위에 입력하거나 .env에 FDS_NOTIFY_EMAIL을 설정하세요", "⚠ No recipient — type one above or set FDS_NOTIFY_EMAIL in .env", "⚠ 宛先なし — 上に入力するか.envにFDS_NOTIFY_EMAILを設定してください", "⚠ 无收件人 — 请在上方输入或在.env中设置FDS_NOTIFY_EMAIL")

# ── ⌨ 키보드 단축키 (v8.3) ──
_add("kbd.hint", "⌨ <b>1–5</b> 세션 · <b>←/→</b> 이동 · <b>C</b> 챗봇 · <b>V</b> 컴팩트 · <b>H</b> 사용안내 · <b>U T L S</b> UI/테마/언어/설정 · <b>?</b> 전체 단축키", "⌨ <b>1–5</b> sessions · <b>←/→</b> move · <b>U</b> UI · <b>T</b> theme · <b>L</b> language · <b>S</b> settings · <b>?</b>·<b>Ctrl+/</b> help", "⌨ <b>1–5</b> セッション · <b>←/→</b> 移動 · <b>U</b> UI · <b>T</b> テーマ · <b>L</b> 言語 · <b>S</b> 設定 · <b>?</b>·<b>Ctrl+/</b> ヘルプ", "⌨ <b>1–5</b> 会话 · <b>←/→</b> 切换 · <b>U</b> UI · <b>T</b> 主题 · <b>L</b> 语言 · <b>S</b> 设置 · <b>?</b>·<b>Ctrl+/</b> 帮助")

# ── 🩺 누출 × 모델 교차검증 (v8.5) ──
_add("doc.leak_model_uses", "🚨 모델이 누출 컬럼을 피처로 사용 중: {cols} — 이 모델의 지표는 신뢰 불가, 재학습 필요", "🚨 Model USES leaked columns as features: {cols} — its metrics are untrustworthy; retrain required", "🚨 モデルがリーク列を特徴量として使用中: {cols} — 指標は信頼不可、再学習が必要", "🚨 模型正在使用泄漏列作为特征: {cols} — 指标不可信，需重新训练")
_add("doc.leak_model_excluded", "✅ 누출 의심 컬럼({cols})은 이 모델의 피처에서 제외됨 — 학습 시 제거 확인", "✅ Suspected leak columns ({cols}) are excluded from this model's features — removal at training confirmed", "✅ リーク疑い列（{cols}）はこのモデルの特徴量から除外済み — 学習時の削除を確認", "✅ 疑似泄漏列（{cols}）已从该模型特征中排除 — 确认训练时已删除")

# 모듈 버전 — 🩺 진단 패널이 표시 (구버전 모듈 잔존 진단용)
I18N_VERSION = "v8.5"  # (역호환: 실제 값은 파일 끝에서 v9.1로 갱신됨)

# ── 🔗 데이터 소스 연동 (v8.6) ──
_add("link.toggle", "🔗 사이드바 연동", "🔗 Follow sidebar", "🔗 サイドバー連動", "🔗 跟随侧边栏")
_add("link.help", "사이드바의 '평가 데이터셋' 선택을 이 탭의 데이터 소스가 자동으로 따라갑니다. 끄면 독립적으로 선택합니다.", "This tab's data source automatically follows the sidebar's evaluation dataset. Turn off to choose independently.", "サイドバーの評価データセット選択にこのタブのデータソースが自動追従します。オフで独立選択。", "此选项卡的数据源自动跟随侧边栏的评估数据集。关闭后可独立选择。")
_add("link.unsupported", "↯ 전역 선택 '{name}'은 이 탭에서 지원되지 않아(라벨 없음/비parquet) 로컬 선택을 유지합니다", "↯ Global selection '{name}' isn't usable here (no label / not parquet) — keeping local choice", "↯ グローバル選択'{name}'はこのタブで使用不可のため、ローカル選択を維持します", "↯ 全局选择'{name}'在此选项卡不可用 — 保持本地选择")

# ══════════════════════════════════════════════════════════
# ✨ v9.1 — 하드코딩 한국어 문자열 i18n 이관 + 신규 기능(이중 임계값·컴팩트 뷰)
#   (기존 배치 UI/캡션/제목이 t()를 거치지 않아 en/ja/zh에서 한국어로 남던 누수 해소)
# ══════════════════════════════════════════════════════════
_add("common.close", "닫기", "Close", "閉じる", "关闭")
_add("common.rows", "행", "rows", "行", "行")

# ── 세션1 데이터 출처 표기 ──
_add("s1.note_train_default", "train.csv (기본)", "train.csv (default)", "train.csv (デフォルト)", "train.csv (默认)")

# ── 세션2 평가 캡션 ──
_add("s2.eval_sample_caption", "📏 평가 표본 {n}건", "📏 Eval sample: {n}", "📏 評価サンプル {n}件", "📏 评估样本 {n} 条")
_add("s2.eval_full_use", "전체 사용", "full set", "全件使用", "全部使用")
_add("s2.dummy_curve_note",
     "※ 시연용 더미 곡선 — 실측 분석은 상단 '실시간 재평가' 모드에서",
     "※ Demo placeholder curve — for real analysis use 'Live re-evaluation' mode above",
     "※ デモ用ダミー曲線 — 実測分析は上部の「リアルタイム再評価」モードで",
     "※ 演示用占位曲线 — 实测分析请使用上方的\"实时重新评估\"模式")

# ── 세션5 배치 결과 패널·탭·버튼 ──
_add("s5.batch_panel_analysis", "📋 분석 결과", "📋 Analysis", "📋 分析結果", "📋 分析结果")
_add("s5.batch_copy_analysis", "📋 분석 결과 원문 복사", "📋 Copy analysis text", "📋 分析結果の原文をコピー", "📋 复制分析原文")
_add("s5.batch_notify_label", "📮 알림 발송", "📮 Send notifications", "📮 通知送信", "📮 发送通知")
_add("s5.batch_regen_label", "🔄 재생성", "🔄 Regenerate", "🔄 再生成", "🔄 重新生成")
_add("s5.batch_slack_label", "🔵 Slack 알림", "🔵 Slack message", "🔵 Slack通知", "🔵 Slack 通知")
_add("s5.batch_email_label", "📧 이메일 본문", "📧 Email body", "📧 メール本文", "📧 邮件正文")
_add("s5.batch_copy_email", "📋 이메일 원문 복사", "📋 Copy email source", "📋 メール原文をコピー", "📋 复制邮件原文")
_add("s5.batch_tab_all", "전체", "All", "全体", "全部")
_add("s5.batch_tab_analysis", "분석", "Analysis", "分析", "分析")
_add("s5.batch_save_md", "📋 보고서 .md 저장", "📋 Save report .md", "📋 レポート.md保存", "📋 保存报告 .md")
_add("s5.batch_save_pkg", "📋 전체 패키지(.txt)", "📋 Full package (.txt)", "📋 全体パッケージ(.txt)", "📋 完整包 (.txt)")
_add("s5.batch_email_subject",
     "[FDS 배치] 이상 {n}건", "[FDS Batch] {n} anomalies",
     "[FDS バッチ] 異常 {n}件", "[FDS 批量] 异常 {n} 条")

# ── FeatureBridge 경유 안내 ──
_add("s5.bridge_via_detail",
     "🌉 FeatureBridge 경유 — 원본 행을 파생 피처로 변환해 {ck} 로 탐지",
     "🌉 Via FeatureBridge — raw row converted to derived features, detected with {ck}",
     "🌉 FeatureBridge経由 — 元の行を派生特徴に変換し {ck} で検知",
     "🌉 经由 FeatureBridge — 将原始行转换为衍生特征并用 {ck} 检测")
_add("s5.bridge_via_batch",
     "🌉 FeatureBridge 경유 — {info}", "🌉 Via FeatureBridge — {info}",
     "🌉 FeatureBridge経由 — {info}", "🌉 经由 FeatureBridge — {info}")

# ── 단건 이메일 제목 (이중 임계값 'single' 케이스) ──
_add("notif.subject_single",
     "[FDS] {ft} 탐지", "[FDS] {ft} detected",
     "[FDS] {ft} 検知", "[FDS] 检测到 {ft}")

# ── 우측 상단 컴팩트 뷰 토글 ──
_add("nav.compact_toggle", "🗜 한눈에 보기 (컴팩트)", "🗜 One-screen view (compact)",
     "🗜 一画面表示（コンパクト）", "🗜 单屏视图（紧凑）")
_add("nav.compact_hint",
     "현재 세션의 모든 정보를 한 화면에 압축 배치합니다 (신 UI 전용 · 단축키 V)",
     "Packs all info of the current session onto one screen (New UI only · shortcut V)",
     "現在のセッションの全情報を1画面に圧縮配置します（新UI専用・ショートカット V）",
     "将当前会话的所有信息压缩到一屏（仅新版UI · 快捷键 V）")

# ── 사이드바 이중 임계값 발송 ──
_add("sb.dual_toggle", "📮 이중 임계값 발송", "📮 Dual-threshold dispatch",
     "📮 二段しきい値送信", "📮 双阈值发送")
_add("sb.dual_help",
     "위험도 구간에 따라 발송 채널·메시지 톤을 이원화합니다. 1차(의심) 이상~2차 미만: Slack만 · 담당자 검토 요청 / 2차(확정) 이상: Slack+Email 동시 · 확정 통보",
     "Splits dispatch channel and message tone by risk band. Between the 1st (suspect) and 2nd threshold: Slack only, asking the reviewer to double-check. At/above the 2nd (confirmed) threshold: Slack + Email together as a confirmed alert.",
     "リスク帯によって送信チャネルとメッセージのトーンを二分します。1次（疑い）以上〜2次未満：Slackのみ・担当者へ確認依頼／2次（確定）以上：Slack+Email同時・確定通知。",
     "根据风险区间将发送渠道与消息语气二分。第一（可疑）阈值至第二阈值之间：仅 Slack · 请负责人复核；达到第二（确定）阈值：Slack+Email 同时 · 确定通报。")
_add("sb.th1_label", "1차 임계값 — 의심 (Slack 검토요청)", "1st threshold — suspect (Slack review request)",
     "1次しきい値 — 疑い（Slack確認依頼）", "第一阈值 — 可疑（Slack 复核请求）")
_add("sb.th2_label", "2차 임계값 — 확정 (Slack+Email)", "2nd threshold — confirmed (Slack+Email)",
     "2次しきい値 — 確定（Slack+Email）", "第二阈值 — 确定（Slack+Email）")
_add("sb.dual_swap_warn",
     "⚠ 2차 임계값이 1차보다 낮습니다 — 발송 판정 시 2차={t2:.2f}로 보정 적용",
     "⚠ 2nd threshold is below the 1st — dispatch uses corrected 2nd={t2:.2f}",
     "⚠ 2次しきい値が1次より低いです — 送信判定では2次={t2:.2f}に補正",
     "⚠ 第二阈值低于第一阈值 — 发送判定按第二={t2:.2f} 校正")
_add("sb.dual_rule_note",
     "위험도 &lt;{t1:.2f}: 발송 없음 · {t1:.2f}~{t2:.2f}: 🟡 Slack 검토요청 · ≥{t2:.2f}: 🔴 Slack+Email 확정통보",
     "risk &lt;{t1:.2f}: no dispatch · {t1:.2f}–{t2:.2f}: 🟡 Slack review · ≥{t2:.2f}: 🔴 Slack+Email confirmed",
     "リスク &lt;{t1:.2f}: 送信なし · {t1:.2f}〜{t2:.2f}: 🟡 Slack確認依頼 · ≥{t2:.2f}: 🔴 Slack+Email確定通知",
     "风险 &lt;{t1:.2f}：不发送 · {t1:.2f}~{t2:.2f}：🟡 Slack 复核 · ≥{t2:.2f}：🔴 Slack+Email 确定通报")
_add("s5.dual_active_note",
     "📮 이중 임계값 모드 활성 — 구간 설정은 좌측 사이드바",
     "📮 Dual-threshold mode active — configure bands in the left sidebar",
     "📮 二段しきい値モード有効 — 区間設定は左サイドバー",
     "📮 双阈值模式已启用 — 区间设置在左侧边栏")

# ── 이중 임계값 발송 메시지 머리말·제목 ──
_add("notif.tier_review_head",
     "🟡 [의심 단계 · 추가 검토 요청]\n위험도 {r:.2f} — 1차 임계값({t1:.2f})을 초과했으나 2차 임계값 미만입니다.\n확정 판정 전 단계이므로 담당자의 추가 검토를 요청드립니다. 원거래 내역과 아래 분석 내용을 대조해 오탐 여부를 확인해 주세요.",
     "🟡 [Suspect · additional review requested]\nRisk {r:.2f} — above the 1st threshold ({t1:.2f}) but below the 2nd.\nThis is a pre-confirmation stage; please have a reviewer double-check. Compare the original transaction against the analysis below to rule out a false positive.",
     "🟡 [疑い段階 · 追加確認依頼]\nリスク {r:.2f} — 1次しきい値({t1:.2f})を超えましたが2次未満です。\n確定前の段階のため、担当者による追加確認をお願いします。元取引と以下の分析を照合し、誤検知かどうかご確認ください。",
     "🟡 [可疑阶段 · 请求进一步复核]\n风险 {r:.2f} — 超过第一阈值({t1:.2f})但低于第二阈值。\n此为确定判定前的阶段，请负责人进一步复核。请将原始交易与下方分析对照，确认是否为误报。")
_add("notif.tier_confirm_head",
     "🔴 [확정 단계 · 즉시 대응 요망]\n위험도 {r:.2f} — 2차 임계값({t2:.2f}) 이상으로 이상거래로 판단됩니다.\nSlack·Email 동시 통보되었습니다. 계정 보호 조치 및 거래 차단 검토를 즉시 진행해 주세요.",
     "🔴 [Confirmed · immediate action required]\nRisk {r:.2f} — at/above the 2nd threshold ({t2:.2f}); judged as fraud.\nNotified via Slack and Email simultaneously. Please proceed at once with account protection and transaction-block review.",
     "🔴 [確定段階 · 即時対応要]\nリスク {r:.2f} — 2次しきい値({t2:.2f})以上のため異常取引と判断されます。\nSlack・Email同時通知済み。口座保護措置および取引ブロックの検討を直ちに進めてください。",
     "🔴 [确定阶段 · 需立即处置]\n风险 {r:.2f} — 达到或超过第二阈值({t2:.2f})，判定为异常交易。\n已同时通过 Slack 与 Email 通报。请立即进行账户保护及交易拦截评估。")
_add("notif.subject_review",
     "[FDS 검토요청] {ft} 의심 거래 — 위험도 {r:.2f}", "[FDS Review] {ft} suspect txn — risk {r:.2f}",
     "[FDS 確認依頼] {ft} 疑い取引 — リスク {r:.2f}", "[FDS 复核请求] {ft} 可疑交易 — 风险 {r:.2f}")
_add("notif.subject_confirm",
     "[FDS] {ft} 이상거래 확정 — 위험도 {r:.2f}", "[FDS] {ft} fraud confirmed — risk {r:.2f}",
     "[FDS] {ft} 異常取引確定 — リスク {r:.2f}", "[FDS] {ft} 异常交易确定 — 风险 {r:.2f}")
_add("s5.notify_tier_review", "🟡 의심(1차) — Slack 검토요청", "🟡 Suspect (1st) — Slack review",
     "🟡 疑い(1次) — Slack確認依頼", "🟡 可疑(第一) — Slack 复核")
_add("s5.notify_tier_confirm", "🔴 확정(2차) — Slack+Email 통보", "🔴 Confirmed (2nd) — Slack+Email",
     "🔴 確定(2次) — Slack+Email通知", "🔴 确定(第二) — Slack+Email 通报")
_add("s5.notify_tier_none", "⚪ 1차 임계값 미만 — 자동 발송 생략", "⚪ Below 1st threshold — auto-dispatch skipped",
     "⚪ 1次しきい値未満 — 自動送信スキップ", "⚪ 低于第一阈值 — 跳过自动发送")

I18N_VERSION = "v9.1"

# ── 세션1 KPI 동적 단위 (v9.1) ──
_add("s1.kpi_fraud_types", "유형 {n}종", "{n} types", "{n}種", "{n}种")
_add("common.count", "건", "cases", "件", "条")

# ── v9.1: 기존 _V5_KO(한글 전용) 잔여 키 다국어 이관 — 세션2 지표/누출경고 등 ──
_add("link.two_way",
     "↔ 사이드바와 양방향 연동 중 — 어느 쪽에서 바꿔도 함께 변경됩니다",
     "↔ Two-way linked with the sidebar — changing either side updates both",
     "↔ サイドバーと双方向連動中 — どちらを変えても一緒に変わります",
     "↔ 与侧边栏双向联动 — 任一侧更改都会同步")
_add("nav.leak_muted",
     "🔕 is_fraud 누출 경고 숨김 상태 — 사이드바 '경고 배너' 토글로 다시 켤 수 있어요",
     "🔕 is_fraud leakage warning is hidden — re-enable it via the 'warning banner' toggle in the sidebar",
     "🔕 is_fraud リーク警告は非表示 — サイドバーの「警告バナー」トグルで再表示できます",
     "🔕 is_fraud 泄漏警告已隐藏 — 可通过侧边栏的\"警告横幅\"开关重新开启")
_add("nav.leak_warn_help",
     "세션 2·5의 is_fraud 누출 경고 배너를 표시합니다. 담당자 확인이 끝났다면 꺼서 소음을 줄이세요 — 꺼도 🩺 호환성 진단에는 항상 기록됩니다.",
     "Shows the is_fraud leakage warning banner in Sessions 2 & 5. Turn it off to reduce noise once reviewed — it is still always recorded in the 🩺 compatibility diagnostics.",
     "セッション2・5の is_fraud リーク警告バナーを表示します。確認済みならオフにしてノイズを減らせます — オフでも🩺互換性診断には常に記録されます。",
     "在会话 2 与 5 中显示 is_fraud 泄漏警告横幅。确认完成后可关闭以减少干扰 — 即使关闭，🩺 兼容性诊断中也始终会记录。")
_add("nav.leak_warn_toggle",
     "🚨 라벨 누출 경고 배너", "🚨 Label leakage warning banner",
     "🚨 ラベルリーク警告バナー", "🚨 标签泄漏警告横幅")
_add("s2.cost_weight_note",
     "오탐 비용 모집단 보정 ×{w} 적용 (층화 표본)",
     "False-positive cost scaled to population ×{w} (stratified sample)",
     "誤検知コストを母集団補正 ×{w} 適用（層化標本）",
     "误报成本按总体校正 ×{w}（分层抽样）")
_add("s2.evaluator_stale",
     "⚠ pipeline/evaluator.py가 구버전입니다 — 표본→모집단 보정 없이 계산됩니다. 새 evaluator.py를 pipeline/에 배치하고 완전 재시작하세요",
     "⚠ pipeline/evaluator.py is outdated — computed without sample→population correction. Place the new evaluator.py in pipeline/ and fully restart",
     "⚠ pipeline/evaluator.py が旧版です — 標本→母集団補正なしで計算されます。新しい evaluator.py を pipeline/ に配置し完全再起動してください",
     "⚠ pipeline/evaluator.py 为旧版 — 未经样本→总体校正即计算。请将新的 evaluator.py 放入 pipeline/ 并完全重启")
_add("s2.metric_pick", "표시 지표", "Metrics shown", "表示指標", "显示指标")
_add("s2.micro_label", "전체 µ(사기)", "Overall µ (fraud)", "全体 µ（不正）", "整体 µ（欺诈）")
_add("s2.micro_note",
     "📌 주 지표 µF1 = 사기 클래스(a~l) 한정 micro F1 (건수 가중 통합) · 참고: 13클래스 전체 micro F1은 정확도와 동일해 99% 정상 데이터에선 변별력이 없습니다",
     "📌 Primary metric µF1 = micro F1 over fraud classes (a–l) only, count-weighted · Note: micro F1 over all 13 classes equals accuracy, so it has no discriminative power on 99%-normal data",
     "📌 主指標 µF1 = 不正クラス(a〜l)限定の micro F1（件数加重統合）· 参考: 13クラス全体の micro F1 は精度と同一で、99%が正常のデータでは判別力がありません",
     "📌 主指标 µF1 = 仅限欺诈类别(a~l)的 micro F1（按条数加权）· 注: 13 个类别整体的 micro F1 等同于准确率，在 99% 为正常的数据上无区分力")
_add("s2.model_chart_title", "모델 성능 비교", "Model performance comparison", "モデル性能比較", "模型性能比较")

# ── v9.2: 컴팩트 뷰 안내 핀 ──
_add("nav.compact_pin",
     "🗜 컴팩트 뷰 · 상세는 아래 섹션을 펼쳐 확인 (해제: 단축키 V)",
     "🗜 Compact view · expand the sections below for details (exit: shortcut V)",
     "🗜 コンパクト表示 · 詳細は下のセクションを展開 (解除: ショートカット V)",
     "🗜 紧凑视图 · 展开下方各节查看详情（退出：快捷键 V）")


# ══════════════════════════════════════════════════════════
# ✨ v9.3 — 프롬프트/폴백 다국어화
#   (a) llm_lang_directive: LLM에 UI 언어로 응답하도록 지시하는 프롬프트 접미사
#       (프롬프트 본문은 한국어 코퍼스 유지, 출력 언어만 전환하는 기존 설계 계승)
#   (b) fb.*: LLM 미연결 시 사용자에게 직접 보이는 폴백 템플릿 — 전체 문장을 언어별로 보관
# ══════════════════════════════════════════════════════════
def llm_lang_directive(lang: str) -> str:
    """UI 언어가 한국어가 아니면 '전체 응답을 해당 언어로 작성하라'는 지시문을 반환."""
    _names = {"en": "English", "ja": "日本語 (Japanese)", "zh": "简体中文 (Simplified Chinese)"}
    _name = _names.get(lang)
    return f"\n\n(Please write your entire response in {_name}.)" if _name else ""

# ── 단건 폴백: 분석 리포트 ──
_add("fb.no_flags", "• 위험 플래그 없음", "• No risk flags", "• リスクフラグなし", "• 无风险标记")
_add("fb.analysis_single",
 "⚠️ {ft}형 이상거래 탐지 — {name}\n\n【판정 근거】\n위험 점수 {r}로 {ft}형 사기 패턴이 탐지되었습니다. 거래 금액 {amt}원, 채널 {ch}, 거래 거리 {dist}km 등 주요 지표가 해당 사기 유형의 특성과 일치합니다.\n\n【이상 패턴 요약】\n{flags}\n\n【권장 조치】\n즉시: 거래 보류 후 담당자 수동 검토\n단기: 고객 본인 확인 후 처리\n장기: 해당 패턴 모니터링 강화",
 "⚠️ Type {ft} anomaly detected — {name}\n\n[Basis]\nA type-{ft} fraud pattern was detected at risk score {r}. Key indicators — amount {amt} KRW, channel {ch}, distance {dist} km — match the characteristics of this fraud type.\n\n[Anomaly Summary]\n{flags}\n\n[Recommended Actions]\nImmediate: hold the transaction and route to a reviewer for manual check\nShort-term: process after verifying the customer's identity\nLong-term: strengthen monitoring of this pattern",
 "⚠️ {ft}型異常取引を検知 — {name}\n\n【判定根拠】\nリスクスコア{r}で{ft}型詐欺パターンが検知されました。取引金額{amt}ウォン、チャネル{ch}、取引距離{dist}km等の主要指標が当該詐欺類型の特性と一致します。\n\n【異常パターン要約】\n{flags}\n\n【推奨措置】\n即時: 取引を保留し担当者が手動で確認\n短期: 顧客本人確認の後に処理\n長期: 当該パターンのモニタリングを強化",
 "⚠️ 检测到{ft}型异常交易 — {name}\n\n【判定依据】\n在风险分数{r}下检测到{ft}型欺诈模式。交易金额{amt}韩元、渠道{ch}、交易距离{dist}km等主要指标与该欺诈类型的特征一致。\n\n【异常模式摘要】\n{flags}\n\n【建议措施】\n立即：暂停交易并转交负责人人工复核\n短期：完成客户本人验证后处理\n长期：加强对该模式的监控")

# ── 단건 폴백: Slack ──
_add("fb.slack_single",
 "{level} *{ft}형 이상거래 탐지* | 거래ID: `{id}` | 금액: `{amt}원` | 채널: `{ch}`\n> 위험점수 {r} — 즉시 확인 및 조치 필요",
 "{level} *Type {ft} anomaly detected* | Txn ID: `{id}` | Amount: `{amt} KRW` | Channel: `{ch}`\n> Risk score {r} — immediate check and action required",
 "{level} *{ft}型異常取引を検知* | 取引ID: `{id}` | 金額: `{amt}ウォン` | チャネル: `{ch}`\n> リスクスコア {r} — 即時確認・対応が必要",
 "{level} *检测到{ft}型异常交易* | 交易ID: `{id}` | 金额: `{amt}韩元` | 渠道: `{ch}`\n> 风险分数 {r} — 需立即确认并处置")

# ── 단건 폴백: 이메일 ──
_add("fb.email_single",
 "제목: [FDS 긴급] {ft}형 이상거래 탐지 (거래ID: {id})\n\n담당자 귀중,\n\nFDS 시스템에서 이상거래를 탐지하였습니다.\n\n{line}\n■ 탐지 개요\n{line}\n  사기 유형  : {ft}형\n  위험 점수  : {r}\n  거래 ID   : {id}\n  거래 일시  : {dt}\n  거래 금액  : {amt}원\n  거래 채널  : {ch}\n\n{line}\n■ AI 분석 결과\n{line}\n{analysis}\n\n{line}\n본 메일은 FDS 자동화 시스템에 의해 발송되었습니다.\nFDS QA 자동화 시스템 드림",
 "Subject: [FDS URGENT] Type {ft} anomaly detected (Txn ID: {id})\n\nDear team,\n\nThe FDS system has detected an anomalous transaction.\n\n{line}\n■ Detection Overview\n{line}\n  Fraud type : Type {ft}\n  Risk score : {r}\n  Txn ID     : {id}\n  Timestamp  : {dt}\n  Amount     : {amt} KRW\n  Channel    : {ch}\n\n{line}\n■ AI Analysis\n{line}\n{analysis}\n\n{line}\nThis email was sent automatically by the FDS system.\nFDS QA Automation System",
 "件名: [FDS 緊急] {ft}型異常取引を検知 (取引ID: {id})\n\nご担当者様\n\nFDSシステムが異常取引を検知しました。\n\n{line}\n■ 検知概要\n{line}\n  詐欺類型  : {ft}型\n  リスクスコア: {r}\n  取引ID    : {id}\n  取引日時  : {dt}\n  取引金額  : {amt}ウォン\n  取引チャネル: {ch}\n\n{line}\n■ AI分析結果\n{line}\n{analysis}\n\n{line}\n本メールはFDS自動化システムにより送信されました。\nFDS QA自動化システム",
 "主题: [FDS 紧急] 检测到{ft}型异常交易 (交易ID: {id})\n\n负责人您好，\n\nFDS系统检测到异常交易。\n\n{line}\n■ 检测概览\n{line}\n  欺诈类型  : {ft}型\n  风险分数  : {r}\n  交易ID    : {id}\n  交易时间  : {dt}\n  交易金额  : {amt}韩元\n  交易渠道  : {ch}\n\n{line}\n■ AI分析结果\n{line}\n{analysis}\n\n{line}\n本邮件由FDS自动化系统发送。\nFDS QA自动化系统")

# ── 배치 폴백: 요약문 ──
_add("fb.summary_normal", "정상 {n}건", "Normal {n}", "正常 {n}件", "正常 {n}条")
_add("fb.summary_type", "{ft}형 {n}건", "Type {ft} {n}", "{ft}型 {n}件", "{ft}型 {n}条")
_add("fb.summary_line", "{parts}으로 측정되었습니다", "Measured: {parts}", "{parts}と測定されました", "测定为：{parts}")
_add("fb.summary_none", "측정된 거래가 없습니다", "No transactions measured", "測定された取引がありません", "无已测定交易")

# ── 배치 폴백: 보고서/유형줄/위험줄 ──
_add("fb.batch_type_line", " • {ft}형 ({name}): {n}건", " • Type {ft} ({name}): {n}", " • {ft}型 ({name}): {n}件", " • {ft}型 ({name}): {n}条")
_add("fb.batch_no_types", " • 이상 유형 없음", " • No anomaly types", " • 異常類型なし", " • 无异常类型")
_add("fb.batch_risky_line", " {i}. {id} — {ft}형 (위험점수 {r})", " {i}. {id} — Type {ft} (risk {r})", " {i}. {id} — {ft}型 (リスク {r})", " {i}. {id} — {ft}型 (风险 {r})")
_add("fb.batch_risky_none", " (없음)", " (none)", " (なし)", " (无)")
_add("fb.batch_report",
 "【📋AI 배치 분석 보고서】\n\n【탐지 요약】\n{summary}. 전체 {total}건 중 이상거래 {anomaly}건 (임계값 {thr}), 평균 위험점수 {avg}입니다.\n\n【유형별 분포】\n{type_lines}\n\n【우선 조치 대상】\n{risky}\n\n【권장 조치】\n 즉시: 위험 상위 거래를 보류하고 담당자 수동 검토를 진행하십시오.\n 단기: 다건 탐지된 유형에 대해 고객 본인 확인 절차를 강화하십시오.\n 장기: 해당 배치의 오탐/미탐 여부를 라벨링하여 모델 재학습 데이터로 축적하십시오.",
 "[📋 AI Batch Analysis Report]\n\n[Detection Summary]\n{summary}. Of {total} transactions, {anomaly} are anomalous (threshold {thr}); average risk score {avg}.\n\n[Distribution by Type]\n{type_lines}\n\n[Priority Actions]\n{risky}\n\n[Recommended Actions]\n Immediate: hold the top-risk transactions and proceed with manual reviewer checks.\n Short-term: strengthen customer identity verification for types detected in volume.\n Long-term: label this batch's false-positive/negative outcomes and accumulate them as model-retraining data.",
 "【📋AIバッチ分析レポート】\n\n【検知要約】\n{summary}。全{total}件中、異常取引{anomaly}件（しきい値{thr}）、平均リスクスコア{avg}です。\n\n【類型別分布】\n{type_lines}\n\n【優先対応対象】\n{risky}\n\n【推奨措置】\n 即時: リスク上位の取引を保留し、担当者による手動確認を進めてください。\n 短期: 多数検知された類型について顧客本人確認手続きを強化してください。\n 長期: 当該バッチの誤検知/見逃しをラベリングし、モデル再学習データとして蓄積してください。",
 "【📋AI批量分析报告】\n\n【检测摘要】\n{summary}。全部{total}条中，异常交易{anomaly}条（阈值{thr}），平均风险分数{avg}。\n\n【按类型分布】\n{type_lines}\n\n【优先处置对象】\n{risky}\n\n【建议措施】\n 立即：暂停高风险交易并进行负责人人工复核。\n 短期：对多次检测到的类型加强客户本人验证流程。\n 长期：对该批次的误报/漏报进行标注，作为模型再训练数据积累。")

# ── 배치 폴백: Slack ──
_add("fb.batch_slack",
 "{lvl} *[배치 탐지] {summary}*\n> 전체 {total}건 | 이상 {anomaly}건 | 평균 위험 {avg} | 최고 {max} (임계값 {thr})",
 "{lvl} *[Batch] {summary}*\n> Total {total} | Anomalies {anomaly} | Avg risk {avg} | Max {max} (threshold {thr})",
 "{lvl} *[バッチ検知] {summary}*\n> 全{total}件 | 異常{anomaly}件 | 平均リスク {avg} | 最高 {max} (しきい値 {thr})",
 "{lvl} *[批量检测] {summary}*\n> 全部{total}条 | 异常{anomaly}条 | 平均风险 {avg} | 最高 {max} (阈值 {thr})")

# ── 배치 폴백: 이메일 ──
_add("fb.batch_email",
 "제목: [FDS 배치 경보] 이상거래 {anomaly}건 / 전체 {total}건\n\n담당자 귀중,\n\nFDS 배치 분석 결과를 보고드립니다.\n\n{line}\n■ 배치 개요\n{line}\n  탐지 요약  : {summary}\n  전체 거래  : {total}건\n  이상 거래  : {anomaly}건 (임계값 {thr})\n  평균 위험  : {avg} / 최고 {max}\n\n{line}\n■ AI 분석 결과\n{line}\n{analysis}\n\n{line}\n본 메일은 FDS 자동화 시스템에 의해 발송되었습니다.\nFDS QA 자동화 시스템 드림",
 "Subject: [FDS Batch Alert] {anomaly} anomalies / {total} total\n\nDear team,\n\nPlease find the FDS batch analysis results below.\n\n{line}\n■ Batch Overview\n{line}\n  Summary    : {summary}\n  Total txns : {total}\n  Anomalies  : {anomaly} (threshold {thr})\n  Avg risk   : {avg} / max {max}\n\n{line}\n■ AI Analysis\n{line}\n{analysis}\n\n{line}\nThis email was sent automatically by the FDS system.\nFDS QA Automation System",
 "件名: [FDS バッチ警報] 異常取引{anomaly}件 / 全{total}件\n\nご担当者様\n\nFDSバッチ分析結果をご報告します。\n\n{line}\n■ バッチ概要\n{line}\n  検知要約  : {summary}\n  全取引    : {total}件\n  異常取引  : {anomaly}件 (しきい値 {thr})\n  平均リスク: {avg} / 最高 {max}\n\n{line}\n■ AI分析結果\n{line}\n{analysis}\n\n{line}\n本メールはFDS自動化システムにより送信されました。\nFDS QA自動化システム",
 "主题: [FDS 批量警报] 异常交易{anomaly}条 / 全部{total}条\n\n负责人您好，\n\n现汇报FDS批量分析结果。\n\n{line}\n■ 批量概览\n{line}\n  检测摘要  : {summary}\n  全部交易  : {total}条\n  异常交易  : {anomaly}条 (阈值 {thr})\n  平均风险  : {avg} / 最高 {max}\n\n{line}\n■ AI分析结果\n{line}\n{analysis}\n\n{line}\n本邮件由FDS自动化系统发送。\nFDS QA自动化系统")

I18N_VERSION = "v9.3"

# ══════════════════════════════════════════════════════════
# 🔴 v10 병합 — dashboard._V5_KO 에만 존재해 EN/JA/ZH에서 한국어로 노출되던 17키
#   (프롬프트 편집기 12키 + 챗봇 퀵프롬프트 6키 + 베이스 모델 설명 1키)
# ══════════════════════════════════════════════════════════
_add("s5.prompt_editor_title", "🖊 AI 프롬프트 편집", "🖊 Edit AI prompts",
     "🖊 AIプロンプト編集", "🖊 编辑 AI 提示词")
_add("s5.prompt_editor_help",
     "기본 프롬프트를 직접 수정합니다. 저장하면 이후 모든 분석에 적용되고, 초기화하면 기본값으로 돌아갑니다. 형식 오류가 있으면 자동으로 기본 프롬프트로 복귀하므로 탐지가 멈추지 않습니다.",
     "Edit the built-in prompts. Saving applies them to every later analysis; Reset restores the default. If a template has a formatting error it silently falls back to the default, so detection never stops.",
     "既定のプロンプトを直接編集します。保存すると以降の分析すべてに適用され、リセットで既定に戻ります。書式エラー時は自動的に既定へ復帰するため検知は止まりません。",
     "直接编辑默认提示词。保存后应用于后续所有分析，重置则恢复默认。若模板格式有误会自动回退到默认，检测不会中断。")
_add("s5.prompt_save", "💾 저장", "💾 Save", "💾 保存", "💾 保存")
_add("s5.prompt_reset", "↺ 기본값으로", "↺ Reset to default", "↺ 既定に戻す", "↺ 恢复默认")
_add("s5.prompt_active", "✅ 커스텀 프롬프트가 적용 중입니다", "✅ A custom prompt is active",
     "✅ カスタムプロンプトが適用中です", "✅ 自定义提示词已生效")
_add("s5.prompt_vars_label", "사용 가능한 자리표시자", "Available placeholders",
     "使用可能なプレースホルダ", "可用占位符")
_add("s5.prompt_tab_analysis", "분석 리포트", "Analysis report", "分析レポート", "分析报告")
_add("s5.prompt_tab_slack", "Slack 알림", "Slack alert", "Slack通知", "Slack 通知")
_add("s5.prompt_tab_email", "이메일 본문", "Email body", "メール本文", "邮件正文")
_add("s5.prompt_tab_batch", "배치 종합보고서", "Batch report", "バッチ総合レポート", "批量综合报告")
_add("chat.quick_title", "예시 질문", "Example questions", "質問例", "示例问题")
_add("chat.quick1", "이 화면 요약해줘", "Summarize this screen",
     "この画面を要約して", "总结一下这个界面")
_add("chat.quick2", "µF1이 무슨 뜻이야?", "What does µF1 mean?",
     "µF1とは何ですか？", "µF1 是什么意思？")
_add("chat.quick3", "지금 위험한 거래 있어?", "Any risky transactions right now?",
     "今リスクの高い取引はある？", "现在有高风险交易吗？")
_add("chat.quick4", "실시간 탐지 화면으로 가줘", "Take me to live detection",
     "リアルタイム検知画面へ", "带我去实时检测页面")
_add("chat.hotkey_hint", "⌨ 단축키 C 로 언제든 챗봇을 열 수 있어요",
     "⌨ Press C anytime to open the chat", "⌨ ショートカット C でいつでもチャットを開けます",
     "⌨ 随时按 C 打开聊天")
_add("model.base_bundle", "팀 배포 번들 · 58피처 13클래스 (macro F1 0.6138)",
     "Team deployment bundle · 58 features, 13 classes (macro F1 0.6138)",
     "チーム配布バンドル · 58特徴量 13クラス (macro F1 0.6138)",
     "团队部署包 · 58 个特征 13 个类别 (macro F1 0.6138)")

# ══════════════════════════════════════════════════════════
# ✨ v10 — 분류기 선택 모드 표시 (세션5 단건·배치 공용)
# ══════════════════════════════════════════════════════════
_add("clf.mode_bundle", "🎯 배포 번들 · Preprocessor 경유 ({n}피처, 입력 형태: {shape})",
     "🎯 Deployment bundle · via Preprocessor ({n} features, input: {shape})",
     "🎯 配布バンドル · Preprocessor経由 ({n}特徴量, 入力: {shape})",
     "🎯 部署包 · 经 Preprocessor ({n} 个特征, 输入: {shape})")
_add("clf.mode_encoded", "🔢 전처리 완료 행 · 모델 피처 순서로 정렬",
     "🔢 Pre-encoded rows · aligned to model feature order",
     "🔢 前処理済み行 · モデルの特徴量順に整列",
     "🔢 已预处理行 · 按模型特征顺序对齐")
_add("clf.mode_bridge", "🌉 FeatureBridge 경유 · 컴포지트 {ck}",
     "🌉 via FeatureBridge · composite {ck}",
     "🌉 FeatureBridge経由 · コンポジット {ck}",
     "🌉 经 FeatureBridge · 组合 {ck}")
_add("clf.mode_mlclf", "⚙ MLClassifier 기본 전처리 경유",
     "⚙ via MLClassifier default preprocessing",
     "⚙ MLClassifier 既定前処理を経由",
     "⚙ 经 MLClassifier 默认预处理")
_add("clf.shape_raw", "원본 행", "raw row", "元の行", "原始行")
_add("clf.shape_engineered", "전처리 완료", "pre-encoded", "前処理済み", "已预处理")

# ══════════════════════════════════════════════════════════
# ✨ v11 — 배치 리포트 행별 위험도 판정 (요청 1)
# ══════════════════════════════════════════════════════════
_add("fb.row_over", "임계 초과 → 이상", "over threshold → anomaly", "閾値超過 → 異常", "超过阈值 → 异常")
_add("fb.row_under", "임계 미만 → 정상", "below threshold → normal", "閾値未満 → 正常", "低于阈值 → 正常")
_add("fb.row_near", " ⚠경계", " ⚠borderline", " ⚠境界", " ⚠临界")
_add("fb.row_omitted", " … 이하 {n}건 생략 (위험점수 {cut} 이하, 그 중 임계 초과 {over}건)",
     " … {n} more rows omitted (risk ≤ {cut}; {over} of them over threshold)",
     " … 以下 {n} 件省略 (リスク {cut} 以下、うち閾値超過 {over} 件)",
     " … 以下省略 {n} 条 (风险 ≤ {cut}，其中超阈值 {over} 条)")
_add("s5.batch_rowtab", "행별 판정", "Per-row", "行別判定", "逐行判定")
_add("fb.batch_rows_block",
     "【행별 위험도 판정】\n위험점수 최저 {lo} · 중앙 {mid} · 최고 {hi} · 구간별 {hist}\n{rows}\n{note}",
     "【Per-row risk verdict】\nRisk min {lo} · median {mid} · max {hi} · by band {hist}\n{rows}\n{note}",
     "【行別リスク判定】\nリスク 最低 {lo} · 中央 {mid} · 最高 {hi} · 区間別 {hist}\n{rows}\n{note}",
     "【逐行风险判定】\n风险 最低 {lo} · 中位 {mid} · 最高 {hi} · 分段 {hist}\n{rows}\n{note}")
_add("fb.row_line", " {i:>4}. {id:<18} | {ft}형 | 위험 {r} ({d}) | {verdict}{near}",
     " {i:>4}. {id:<18} | Type {ft} | risk {r} ({d}) | {verdict}{near}",
     " {i:>4}. {id:<18} | {ft}型 | リスク {r} ({d}) | {verdict}{near}",
     " {i:>4}. {id:<18} | {ft}型 | 风险 {r} ({d}) | {verdict}{near}")

# ══════════════════════════════════════════════════════════
# ✨ v11 — RAG 기본 문서 편집기 (요청 3)
# ══════════════════════════════════════════════════════════
_add("s5.rag_editor_title", "📚 RAG 참고문서 편집", "📚 Edit RAG documents",
     "📚 RAG参照ドキュメント編集", "📚 编辑 RAG 参考文档")
_add("s5.rag_editor_help",
     "AI가 분석 근거로 참고하는 사기 시나리오·대응 매뉴얼을 직접 수정합니다. 저장하면 벡터 인덱스가 자동으로 다시 만들어지고, 이후 모든 분석에 반영됩니다(재시작 불필요).",
     "Edit the fraud scenarios and response manuals the AI cites as evidence. Saving rebuilds the vector index automatically and applies to every later analysis — no restart needed.",
     "AIが分析根拠として参照する不正シナリオ・対応マニュアルを直接編集します。保存するとベクトルインデックスが自動再構築され、以降の分析に反映されます(再起動不要)。",
     "直接编辑 AI 作为分析依据引用的欺诈场景与应对手册。保存后会自动重建向量索引并应用于后续所有分析（无需重启）。")
_add("s5.rag_docs_path", "📂 {path} — 문서 {n}개", "📂 {path} — {n} document(s)",
     "📂 {path} — ドキュメント {n} 件", "📂 {path} — {n} 个文档")
_add("s5.rag_save", "💾 저장 + 재색인", "💾 Save + reindex", "💾 保存 + 再索引", "💾 保存 + 重建索引")
_add("s5.rag_reindex", "🔄 강제 재색인", "🔄 Force reindex", "🔄 強制再索引", "🔄 强制重建索引")
_add("s5.rag_delete", "🗑 삭제", "🗑 Delete", "🗑 削除", "🗑 删除")
_add("s5.rag_delete_confirm", "⚠ '{name}'을 삭제하려면 삭제 버튼을 한 번 더 누르세요",
     "⚠ Press Delete again to remove '{name}'",
     "⚠ '{name}' を削除するには削除ボタンをもう一度押してください",
     "⚠ 再次点击删除以移除 '{name}'")
_add("s5.rag_deleted", "🗑 '{name}' 삭제됨 — 인덱스 재구축 예정",
     "🗑 '{name}' deleted — index will rebuild",
     "🗑 '{name}' を削除 — インデックスを再構築します",
     "🗑 已删除 '{name}' — 将重建索引")
_add("s5.rag_saved", "✅ 저장 완료 — 다음 분석에서 인덱스가 재구축됩니다",
     "✅ Saved — the index rebuilds on the next analysis",
     "✅ 保存しました — 次の分析でインデックスを再構築します",
     "✅ 已保存 — 下次分析时将重建索引")
_add("s5.rag_reindexed", "🔄 재색인 예약 — 다음 분석에서 전체 재임베딩됩니다",
     "🔄 Reindex queued — full re-embedding on the next analysis",
     "🔄 再索引を予約 — 次の分析で全再埋め込みします",
     "🔄 已排队重建 — 下次分析时全量重新嵌入")
_add("s5.rag_create_samples", "📄 샘플 문서 생성 (사기유형 + 대응매뉴얼)",
     "📄 Create sample docs (fraud types + response manual)",
     "📄 サンプル文書を作成 (不正類型 + 対応マニュアル)",
     "📄 创建示例文档 (欺诈类型 + 应对手册)")
_add("s5.rag_new_label", "새 문서 파일명", "New document filename", "新しい文書のファイル名", "新文档文件名")
_add("s5.rag_new_btn", "➕ 추가", "➕ Add", "➕ 追加", "➕ 添加")
_add("s5.rag_new_empty", "파일명을 입력하세요", "Please enter a filename", "ファイル名を入力してください", "请输入文件名")
_add("s5.rag_new_bad", "파일명에 경로 구분자(/ \\)나 앞선 점(.)은 쓸 수 없습니다",
     "Filenames cannot contain path separators (/ \\) or a leading dot",
     "ファイル名にパス区切り(/ \\)や先頭のドット(.)は使えません",
     "文件名不能包含路径分隔符 (/ \\) 或以点开头")
_add("s5.rag_new_dup", "'{name}'이 이미 있습니다", "'{name}' already exists",
     "'{name}' は既に存在します", "'{name}' 已存在")
_add("s5.rag_read_fail", "'{name}' 읽기 실패: {e}", "Failed to read '{name}': {e}",
     "'{name}' の読み込み失敗: {e}", "读取 '{name}' 失败: {e}")
_add("s5.rag_fail", "RAG 문서 처리 실패: {e}", "RAG document operation failed: {e}",
     "RAGドキュメント処理に失敗: {e}", "RAG 文档处理失败: {e}")

# ══════════════════════════════════════════════════════════
# ✨ v12 — 챗봇 음성 입력 (요청 2)
# ══════════════════════════════════════════════════════════
_add("chat.voice_title", "🎤 음성으로 질문하기", "🎤 Ask by voice", "🎤 音声で質問", "🎤 语音提问")
_add("chat.voice_backend", "인식 방식", "Recognition", "認識方式", "识别方式")
_add("chat.voice_auto", "자동 (로컬 우선)", "Auto (local first)", "自動 (ローカル優先)", "自动 (优先本地)")
_add("chat.voice_local", "로컬 (오프라인·안전)", "Local (offline, private)", "ローカル (オフライン・安全)", "本地 (离线・安全)")
_add("chat.voice_cloud", "클라우드 (빠름·정확)", "Cloud (fast, accurate)", "クラウド (高速・高精度)", "云端 (快速・准确)")
_add("chat.voice_backend_help",
     "로컬은 음성이 PC를 떠나지 않아 개인정보에 안전합니다(최초 1회 모델 다운로드). 클라우드는 빠르고 정확하지만 음성이 외부로 전송됩니다.",
     "Local keeps audio on your machine — safest for PII (one-time model download). Cloud is faster and more accurate but sends audio out.",
     "ローカルは音声が端末外に出ないため個人情報に安全です(初回のみモデルDL)。クラウドは高速・高精度ですが音声が外部送信されます。",
     "本地模式音频不离开本机，对个人信息最安全(首次需下载模型)。云端更快更准，但会外发音频。")
_add("chat.voice_model", "모델", "Model", "モデル", "模型")
_add("chat.voice_local_model_help",
     "tiny=가장 빠름/부정확, base=권장, large-v3=가장 정확하나 느리고 용량 큼",
     "tiny = fastest/least accurate, base = recommended, large-v3 = most accurate but slow and large",
     "tiny=最速/低精度, base=推奨, large-v3=最高精度だが低速・大容量",
     "tiny=最快/最不准, base=推荐, large-v3=最准但慢且体积大")
_add("chat.voice_status", "로컬: {lo} · 클라우드: {cl}", "Local: {lo} · Cloud: {cl}",
     "ローカル: {lo} · クラウド: {cl}", "本地: {lo} · 云端: {cl}")
_add("chat.voice_locked",
     "🔒 로컬 LLM + 마스킹 생략 모드 — 음성을 외부로 보내지 않습니다 (로컬 인식만 사용)",
     "🔒 Local LLM + skip-masking mode — audio is never sent outside (local recognition only)",
     "🔒 ローカルLLM + マスキング省略 — 音声を外部送信しません(ローカル認識のみ)",
     "🔒 本地 LLM + 跳过脱敏 — 不会外发音频(仅本地识别)")
_add("chat.voice_record", "🔴 녹음 (누르고 말하기)", "🔴 Record (press and speak)",
     "🔴 録音 (押して話す)", "🔴 录音 (按下说话)")
_add("chat.voice_autosend", "인식되면 바로 전송", "Send as soon as recognized",
     "認識したらすぐ送信", "识别后立即发送")
_add("chat.voice_working", "음성을 문자로 변환 중…", "Transcribing…", "音声を文字に変換中…", "正在转写语音…")
_add("chat.voice_send", "전송", "Send", "送信", "发送")
_add("chat.voice_need_upgrade",
     "음성 입력은 Streamlit 1.42 이상이 필요합니다. `pip install -U streamlit`로 업그레이드하세요.",
     "Voice input requires Streamlit 1.42+. Please run `pip install -U streamlit`.",
     "音声入力には Streamlit 1.42 以上が必要です。`pip install -U streamlit` を実行してください。",
     "语音输入需要 Streamlit 1.42 及以上版本。请执行 `pip install -U streamlit`。")
_add("chat.voice_fail", "음성 입력 오류: {e}", "Voice input error: {e}", "音声入力エラー: {e}", "语音输入错误: {e}")

# ══════════════════════════════════════════════════════════
# ✨ v14 — 음성 입력 오류 진단 + 오디오 파일 업로드 (요청 1·2)
# ══════════════════════════════════════════════════════════
_add("chat.voice_no_backend",
     "🎙 음성을 문자로 바꿀 수단이 아직 없어서 녹음 버튼을 숨겼습니다. 아래 중 하나를 하면 바로 켜집니다.",
     "🎙 No speech-to-text backend yet, so the record button is hidden. Do one of the following to enable it.",
     "🎙 音声認識の手段がないため録音ボタンを非表示にしました。以下のいずれかで有効になります。",
     "🎙 尚无语音转文字后端，已隐藏录音按钮。完成以下任一项即可启用。")
_add("chat.voice_no_backend_alt",
     "또는 사이드바 '🔑 API 키' 에 OpenAI 키를 입력하고, 세션5 LLM 제공자를 외부(openai 등)로 바꾸면 클라우드 인식이 켜집니다.",
     "Or enter an OpenAI key under '🔑 API keys' in the sidebar and switch the Session-5 LLM provider to a cloud one to enable cloud recognition.",
     "またはサイドバーの「🔑 APIキー」にOpenAIキーを入力し、セッション5のLLMプロバイダを外部(openai等)に変更するとクラウド認識が有効になります。",
     "或在侧边栏「🔑 API 密钥」中填入 OpenAI 密钥，并将会话5的 LLM 提供方改为云端(如 openai)以启用云端识别。")
_add("chat.voice_mic_hint",
     "마이크가 안 되면(권한 거부·장치 없음·HTTPS 아님) 아래 파일 업로드를 쓰세요.",
     "If the mic fails (permission denied, no device, not HTTPS), use the file upload below.",
     "マイクが使えない場合(権限拒否・デバイスなし・HTTPS以外)は下のファイルアップロードをご利用ください。",
     "如果麦克风不可用(权限被拒、无设备、非 HTTPS)，请使用下方的文件上传。")
_add("chat.voice_upload", "📁 오디오 파일 업로드", "📁 Upload an audio file",
     "📁 音声ファイルをアップロード", "📁 上传音频文件")
_add("chat.voice_upload_help",
     "wav · mp3 · m4a · ogg · webm · flac · aac (최대 25MB). 마이크를 전혀 사용하지 않습니다.",
     "wav · mp3 · m4a · ogg · webm · flac · aac (max 25MB). Does not use the microphone at all.",
     "wav · mp3 · m4a · ogg · webm · flac · aac (最大25MB)。マイクは一切使用しません。",
     "wav · mp3 · m4a · ogg · webm · flac · aac (最多 25MB)。完全不使用麦克风。")
_add("chat.voice_file_info", "📄 {name} · {kb} KB", "📄 {name} · {kb} KB", "📄 {name} · {kb} KB", "📄 {name} · {kb} KB")
_add("chat.voice_transcribe", "🔤 문자로 변환", "🔤 Transcribe", "🔤 文字に変換", "🔤 转为文字")
_add("chat.voice_discard", "버리기", "Discard", "破棄", "丢弃")
_add("chat.voice_diag", "🩺 음성 입력 진단", "🩺 Voice input diagnostics", "🩺 音声入力の診断", "🩺 语音输入诊断")
_add("chat.voice_diag_secure",
     "브라우저 마이크는 localhost 또는 HTTPS에서만 허용됩니다. 사내 IP(예: http://192.168.x.x:8501)로 접속했다면 마이크가 차단되니 파일 업로드를 쓰세요.",
     "Browsers only allow mic access on localhost or HTTPS. If you opened the app via a LAN IP (e.g. http://192.168.x.x:8501) the mic is blocked — use file upload instead.",
     "ブラウザのマイクは localhost か HTTPS のみ許可されます。社内IP(例: http://192.168.x.x:8501)で開いた場合はマイクがブロックされるため、ファイルアップロードをご利用ください。",
     "浏览器仅在 localhost 或 HTTPS 下允许麦克风。若通过局域网 IP(如 http://192.168.x.x:8501)访问，麦克风会被阻止，请改用文件上传。")
_add("chat.agent_diag", "🩺 에이전트 도구 호출 진단", "🩺 Agent tool-call diagnostics",
     "🩺 エージェント操作の診断", "🩺 智能体工具调用诊断")
_add("chat.agent_diag_help",
     "챗봇이 화면을 바꾸지 않는다면 대개 액션 파이프라인이 아니라 LLM 연결 문제입니다. 아래 두 버튼으로 원인을 분리하세요.",
     "If the bot never changes the screen, it's usually the LLM connection — not the action pipeline. Use the two buttons below to isolate the cause.",
     "ボットが画面を変えない場合、原因は多くの場合アクション処理ではなくLLM接続です。下の2つのボタンで切り分けてください。",
     "如果机器人从不改变界面，通常是 LLM 连接问题而非动作管线。用下面两个按钮来定位原因。")
_add("chat.agent_test_llm", "① LLM 연결 확인", "① Test LLM connection", "① LLM接続を確認", "① 测试 LLM 连接")
_add("chat.agent_test_actions", "② 액션 파이프라인 확인", "② Test action pipeline", "② アクション処理を確認", "② 测试动作管线")
_add("chat.agent_ok", "✅ 액션 {n}종 전부 검증 통과 · 악성 입력 전부 차단 — 파이프라인 정상입니다. 화면이 안 바뀌면 ①번(LLM 연결)을 확인하세요.",
     "✅ All {n} actions validated and all malicious inputs blocked — the pipeline is healthy. If the screen still doesn't change, check ① (LLM connection).",
     "✅ アクション{n}種すべて検証通過・不正入力はすべて遮断 — 処理は正常です。画面が変わらない場合は①(LLM接続)を確認してください。",
     "✅ 全部 {n} 个动作校验通过，恶意输入全部拦截 — 管线正常。若界面仍不变，请检查 ①(LLM 连接)。")
_add("chat.agent_ng", "❌ {n}건 문제 — 위 목록을 확인하세요", "❌ {n} issue(s) — see the list above",
     "❌ {n}件の問題 — 上の一覧を確認してください", "❌ {n} 项问题 — 请查看上面的列表")
_add("chat.agent_live", "라이브 테스트할 동작", "Action to live-test", "ライブテストする操作", "要实测的动作")
_add("chat.agent_live_run", "▶ 실제로 실행해보기", "▶ Run it for real", "▶ 実際に実行", "▶ 实际执行")
_add("chat.agent_live_none", "이 동작은 현재 상태에서 적용할 대상이 없습니다",
     "This action has nothing to apply in the current state",
     "この操作は現在の状態では適用対象がありません", "此动作在当前状态下无可应用对象")

# ══════════════════════════════════════════════════════════
# ✨ v14 — 세션4 합성 데이터 사기유형 강조 + 세션5 전송 (요청 5·6)
# ══════════════════════════════════════════════════════════
_add("s4.syn_type_label", "🎯 이 합성 데이터의 사기 유형", "🎯 Fraud type of this synthetic data",
     "🎯 この合成データの不正類型", "🎯 该合成数据的欺诈类型")
_add("s4.syn_type_random", "RANDOM — 전 유형 혼합", "RANDOM — all types mixed",
     "RANDOM — 全類型混合", "RANDOM — 全类型混合")
_add("s4.syn_type_random_desc",
     "특정 유형을 지정하지 않아 train 전체 분포를 따릅니다. 실제 유형은 모델 예측으로 확인하세요 — 아래 '세션5로 보내기'를 누르면 바로 판정됩니다.",
     "No target type was fixed, so the rows follow the full train distribution. Confirm the actual type via model prediction — press 'Send to Session 5' below.",
     "特定の類型を指定していないため、train全体の分布に従います。実際の類型はモデル予測で確認してください — 下の「セッション5へ送る」を押してください。",
     "未指定目标类型，行遵循 train 的整体分布。请通过模型预测确认实际类型 — 点击下方「发送到会话5」。")
_add("s4.syn_type_fixed_desc",
     "{n}행 전부 위 유형의 분포를 따라 생성되었습니다. 모델이 이 유형을 실제로 맞히는지 세션5에서 검증할 수 있습니다.",
     "All {n} rows were generated from the distribution of the type above. Verify in Session 5 whether the model actually predicts it.",
     "{n}行すべて上記類型の分布から生成されました。モデルが実際にこの類型を当てるかセッション5で検証できます。",
     "全部 {n} 行均按上述类型的分布生成。可在会话5验证模型是否真能预测出该类型。")
_add("s4.send_to_s5", "🚀 이 데이터로 세션5 탐지", "🚀 Detect in Session 5", "🚀 このデータでセッション5検知", "🚀 用该数据在会话5检测")
_add("s4.send_to_s5_help",
     "합성한 행을 그대로 세션5 합성 탭으로 보냅니다. 단건 탐지와 일괄 분석 모두 즉시 실행할 수 있습니다.",
     "Sends the generated rows straight to the Session-5 synthetic tab. Both single detection and batch analysis are ready immediately.",
     "生成した行をそのままセッション5の合成タブへ送ります。単件検知・一括分析の両方をすぐ実行できます。",
     "将生成的行直接发送到会话5的合成选项卡。可立即执行单条检测与批量分析。")
_add("s4.send_to_s5_note", "{n}행이 세션5 합성 탭에 그대로 실립니다 (재생성 불필요).",
     "{n} rows will be loaded into the Session-5 synthetic tab as-is (no regeneration).",
     "{n}行がセッション5の合成タブにそのまま読み込まれます(再生成不要)。",
     "{n} 行将原样载入会话5的合成选项卡(无需重新生成)。")
_add("s4.sent_to_s5", "🚀 {n}행을 세션5로 보냈습니다", "🚀 Sent {n} rows to Session 5",
     "🚀 {n}行をセッション5へ送りました", "🚀 已将 {n} 行发送到会话5")
_add("s4.th_target_type", "목표유형", "Target type", "目標類型", "目标类型")

# ══════════════════════════════════════════════════════════
# ✨ v15 — 에이전트 신규 액션 8종 알림 (요청 1)
# ══════════════════════════════════════════════════════════
_add("chat.act_set_threshold", "임계값을 {v}(으)로 바꿨어요", "Set the threshold to {v}",
     "閾値を {v} に変更しました", "已将阈值改为 {v}")
_add("chat.act_select_model", "모델을 '{m}'(으)로 바꿨어요", "Switched the model to '{m}'",
     "モデルを「{m}」に変更しました", "已将模型切换为「{m}」")
_add("chat.act_select_dataset", "데이터셋을 '{d}'(으)로 바꿨어요", "Switched the dataset to '{d}'",
     "データセットを「{d}」に変更しました", "已将数据集切换为「{d}」")
_add("chat.act_set_eval_mode", "세션2 평가 모드를 {m}(으)로 바꿨어요", "Set Session-2 evaluation mode to {m}",
     "セッション2の評価モードを {m} に変更しました", "已将会话2评估模式设为 {m}")
_add("chat.act_run_batch", "{n}건 일괄 분석을 실행했어요", "Started batch analysis on {n} rows",
     "{n}件の一括分析を実行しました", "已对 {n} 条记录启动批量分析")
_add("chat.act_run_batch_none",
     "일괄 분석할 데이터가 2건 미만이에요. test/train/합성 탭에서 여러 건을 먼저 추출해 주세요",
     "Fewer than 2 rows loaded. Please extract several rows first in the test/train/synthetic tab",
     "一括分析するデータが2件未満です。test/train/合成タブで先に複数抽出してください",
     "载入的记录少于 2 条。请先在 test/train/合成 选项卡抽取多条")
_add("chat.act_set_pii", "개인정보 마스킹을 '{lv}'(으)로 바꿨어요", "Set PII masking to '{lv}'",
     "個人情報マスキングを「{lv}」に変更しました", "已将个人信息脱敏设为「{lv}」")
_add("chat.act_compact_on", "컴팩트 모드를 켰어요", "Turned compact mode on",
     "コンパクトモードをオンにしました", "已开启紧凑模式")
_add("chat.act_compact_off", "컴팩트 모드를 껐어요", "Turned compact mode off",
     "コンパクトモードをオフにしました", "已关闭紧凑模式")
_add("chat.act_autofill", "고위험 시나리오 예시값을 직접입력 폼에 채웠어요",
     "Filled the manual-input form with a high-risk scenario",
     "高リスクシナリオの例を直接入力フォームに入力しました", "已将高风险场景示例填入直接输入表单")

# ══════════════════════════════════════════════════════════
# ✨ v15 — 즉석 녹음을 파일로 만들어 입력 (요청 2)
# ══════════════════════════════════════════════════════════
_add("chat.voice_dl", "⬇ 파일로 저장", "⬇ Download", "⬇ ファイルで保存", "⬇ 保存为文件")
_add("chat.voice_save", "📌 서버에 보관", "📌 Keep on server", "📌 サーバーに保管", "📌 保存到服务器")
_add("chat.voice_saved", "📌 {name} 으로 보관했어요 — 아래 '저장된 녹음'에서 다시 쓸 수 있어요",
     "📌 Kept as {name} — reusable from 'Saved recordings' below",
     "📌 {name} として保管しました — 下の「保存済み録音」から再利用できます",
     "📌 已保存为 {name} — 可从下方「已保存录音」再次使用")
_add("chat.voice_saved_label", "🗂 저장된 녹음", "🗂 Saved recordings", "🗂 保存済み録音", "🗂 已保存录音")
_add("chat.voice_saved_hint", "최근 {n}개 · {dir}", "{n} most recent · {dir}",
     "最新 {n} 件 · {dir}", "最近 {n} 个 · {dir}")

# ══════════════════════════════════════════════════════════
# ✨ v15 — 첫 방문 온보딩 도우미 (요청 3)
# ══════════════════════════════════════════════════════════
_add("onb.title", "🎓 FDS 대시보드 처음 오셨나요?", "🎓 First time on the FDS dashboard?",
     "🎓 FDSダッシュボードは初めてですか？", "🎓 第一次使用 FDS 仪表板？")
_add("onb.intro",
     "이 대시보드는 <b>전자금융 이상거래(사기) 탐지</b>를 다섯 단계로 나눠 보여줍니다. 아래에서 각 화면이 무엇을 하는지, 무엇을 눌러볼 수 있는지 확인하세요. 통계 용어를 몰라도 괜찮습니다.",
     "This dashboard walks through <b>financial fraud detection</b> in five stages. Below is what each screen does and what you can try. No statistics background needed.",
     "このダッシュボードは<b>電子金融の不正取引検知</b>を5段階に分けて表示します。各画面の役割と試せる操作を確認してください。統計の知識は不要です。",
     "本仪表板将<b>金融欺诈检测</b>分为五个阶段展示。下面说明每个界面的作用与可尝试的操作。无需统计学背景。")
_add("onb.s01_title", "개요 · 데이터 살펴보기", "Overview · Explore data", "概要・データ確認", "概览 · 查看数据")
_add("onb.s01_body",
     "전체 거래가 몇 건이고 그중 사기가 몇 %인지, 어떤 사기 유형이 많은지 봅니다. <b>사이드바에서 데이터셋을 바꾸면</b> 모든 세션이 그 데이터 기준으로 다시 계산됩니다.",
     "See how many transactions there are, what share is fraud, and which fraud types dominate. <b>Changing the dataset in the sidebar</b> recalculates every session.",
     "取引総数・不正比率・多い不正類型を確認します。<b>サイドバーでデータセットを変える</b>と全セッションが再計算されます。",
     "查看交易总数、欺诈占比以及占比最高的欺诈类型。<b>在侧边栏更换数据集</b>会让所有会话重新计算。")
_add("onb.s02_title", "모델 성능 · 얼마나 잘 맞히나", "Model performance · How accurate",
     "モデル性能・どれだけ当たるか", "模型性能 · 准确度如何")
_add("onb.s02_body",
     "선택한 데이터셋과 모델로 <b>실시간 재평가</b>가 기본입니다. µF1은 '사기를 얼마나 잘 잡는지'를 0~1로 나타낸 점수입니다. 모델을 최대 3개까지 골라 비교할 수 있습니다.",
     "Defaults to <b>live re-evaluation</b> on your selected dataset and model. µF1 scores how well fraud is caught (0-1). You can compare up to 3 models.",
     "選択したデータセットとモデルで<b>リアルタイム再評価</b>が既定です。µF1は不正をどれだけ捕まえるかを0〜1で示します。最大3モデル比較可能。",
     "默认按所选数据集与模型进行<b>实时重评</b>。µF1 以 0-1 表示捕获欺诈的能力。最多可比较 3 个模型。")
_add("onb.s03_title", "오탐 · 미탐 분석", "False positives · Misses", "誤検知・見逃し分析", "误报 · 漏报分析")
_add("onb.s03_body",
     "정상을 사기로 본 <b>오탐</b>과, 사기를 놓친 <b>미탐</b>을 나눠 봅니다. 사이드바 <b>임계값</b>을 올리면 오탐이 줄지만 미탐이 늘어납니다 — 이 균형점을 찾는 화면입니다.",
     "Separates <b>false positives</b> (normal flagged as fraud) from <b>misses</b>. Raising the sidebar <b>threshold</b> cuts false positives but increases misses — this screen finds that balance.",
     "正常を不正と判定した<b>誤検知</b>と、不正を見逃した<b>見逃し</b>を分けて確認。サイドバーの<b>閾値</b>を上げると誤検知↓見逃し↑。",
     "区分<b>误报</b>(正常被判为欺诈)与<b>漏报</b>。提高侧边栏<b>阈值</b>会减少误报但增加漏报 — 本界面用于找到平衡点。")
_add("onb.s04_title", "합성 데이터 QA", "Synthetic data QA", "合成データQA", "合成数据 QA")
_add("onb.s04_body",
     "학습 데이터 분포를 흉내낸 <b>가상 거래</b>를 만들어 모델을 시험합니다. 목표 사기 유형을 골라 생성하면 상단에 <b>어떤 유형인지 크게 표시</b>되고, <b>🚀 세션5 탐지</b> 버튼으로 그대로 판정해볼 수 있습니다.",
     "Generates <b>synthetic transactions</b> that mimic the training distribution to stress-test the model. Pick a target fraud type and it's <b>shown prominently</b>; press <b>🚀 Detect in Session 5</b> to score them as-is.",
     "学習分布を模した<b>仮想取引</b>を生成してモデルを試します。目標類型を選ぶと上部に<b>大きく表示</b>され、<b>🚀セッション5検知</b>でそのまま判定できます。",
     "生成模仿训练分布的<b>虚拟交易</b>来测试模型。选定目标欺诈类型后会在顶部<b>醒目显示</b>，点击<b>🚀 会话5检测</b>可直接判定。")
_add("onb.s05_title", "실시간 탐지 · 여기가 핵심", "Live detection · The main event",
     "リアルタイム検知・ここが本番", "实时检测 · 核心所在")
_add("onb.s05_body",
     "거래 한 건을 넣어 <b>사기 여부·유형·위험점수</b>를 판정하고, AI가 판정 근거와 대응 방안을 써 줍니다. 입력 방법 5가지(직접입력·test·train·합성·폴더)와 <b>일괄 분석</b>, Slack·이메일 자동 알림까지 여기서 합니다.",
     "Feed one transaction to get <b>fraud verdict, type, and risk score</b>, with an AI write-up of the reasoning and response plan. Five input methods, <b>batch analysis</b>, and Slack/email alerts all live here.",
     "取引1件を入力し<b>不正の有無・類型・リスクスコア</b>を判定、AIが根拠と対応策を作成します。入力5方式・<b>一括分析</b>・Slack/メール通知もここです。",
     "输入一笔交易即可得到<b>是否欺诈、类型与风险分数</b>，AI 会撰写判定依据与应对方案。五种输入方式、<b>批量分析</b>与 Slack/邮件告警都在这里。")
_add("onb.tips_title", "💡 알아두면 편한 것", "💡 Handy to know", "💡 知っておくと便利", "💡 值得知道")
_add("onb.tips_body",
     "· <b>🔰 초보자 설명</b>을 켜면 지표마다 쉬운 해설이 한 줄씩 붙습니다<br>"
     "· <b>단축키 1~5</b> 세션 이동 · <b>C</b> AI 챗봇 · <b>H</b> 이 안내 다시 보기 · <b>?</b> 전체 단축키<br>"
     "· <b>AI 챗봇에게 말로 시킬 수 있습니다</b> — \"임계값 0.7로 바꿔줘\", \"고위험 예시 채워줘\", \"일괄 분석 돌려줘\"<br>"
     "· <b>컴팩트 모드</b>를 켜면 스크롤 없이 한 화면에 들어옵니다<br>"
     "· 모델·AI가 준비 안 돼도 대시보드는 <b>더미/폴백 모드</b>로 계속 동작합니다",
     "· Turn on <b>🔰 Beginner hints</b> for a one-line plain explanation under each metric<br>"
     "· <b>Keys 1-5</b> switch sessions · <b>C</b> AI chat · <b>H</b> reopen this guide · <b>?</b> all shortcuts<br>"
     "· <b>You can just tell the chatbot</b> — \"set threshold to 0.7\", \"fill a high-risk example\", \"run batch analysis\"<br>"
     "· <b>Compact mode</b> fits a session on one screen without scrolling<br>"
     "· Even without a model or LLM ready, the dashboard keeps working in <b>dummy/fallback mode</b>",
     "· <b>🔰初心者ガイド</b>をオンにすると各指標に一行の平易な解説が付きます<br>"
     "· <b>1〜5キー</b>セッション移動 · <b>C</b> AIチャット · <b>H</b> この案内を再表示 · <b>?</b> 全ショートカット<br>"
     "· <b>チャットに話しかけて操作できます</b> — 「閾値を0.7に」「高リスク例を入力」「一括分析を実行」<br>"
     "· <b>コンパクトモード</b>でスクロールなしに1画面表示<br>"
     "· モデルやLLMが未準備でも<b>ダミー/フォールバック</b>で動作します",
     "· 开启<b>🔰新手提示</b>后，每个指标下会有一行通俗解释<br>"
     "· <b>按键 1-5</b> 切换会话 · <b>C</b> AI 聊天 · <b>H</b> 再看本指南 · <b>?</b> 全部快捷键<br>"
     "· <b>可以直接对聊天机器人下指令</b> — “把阈值改成 0.7”“填入高风险示例”“跑批量分析”<br>"
     "· 开启<b>紧凑模式</b>可一屏显示，无需滚动<br>"
     "· 即使模型或 LLM 未就绪，仪表板也会以<b>兜底模式</b>继续运行")
_add("onb.start_beginner", "🔰 초보자 모드로 시작", "🔰 Start in beginner mode",
     "🔰 初心者モードで開始", "🔰 以新手模式开始")
_add("onb.goto_detect", "🚨 바로 탐지해보기", "🚨 Try detection now", "🚨 すぐ検知を試す", "🚨 立即试用检测")
_add("onb.close", "닫기", "Close", "閉じる", "关闭")
_add("onb.reopen", "🎓 사용 안내 다시 보기", "🎓 Show the guide again", "🎓 使い方を再表示", "🎓 再次查看指南")
_add("onb.reopen_help", "각 세션이 무엇을 하는지 다시 안내합니다",
     "Explains again what each session does", "各セッションの役割を再度案内します", "再次说明各会话的作用")

# ══════════════════════════════════════════════════════════
# ✨ v16 — 규칙 체크리스트 (판정 근거 패널)
# ══════════════════════════════════════════════════════════
_add("s5.rule_title", "📋 규칙 체크리스트 (판정 근거)", "📋 Rule checklist (evidence)",
     "📋 ルールチェックリスト(判定根拠)", "📋 规则清单(判定依据)")
_add("s5.rule_disclaimer",
     "이 항목은 '사기 여부'가 아니라 '어느 유형의 특징에 맞는지'만 나타냅니다. 정상 거래도 같은 특징을 흔히 가지므로(수취정지 49%·미사용계좌 51%), 사기 판정은 ML 모델 결과를 따르세요.",
     "These items show which fraud type's profile the transaction matches — not whether it is fraud. Normal transactions share these traits (suspended recipient 49%, dormant account 51%), so rely on the ML model for the fraud verdict.",
     "この項目は「不正か否か」ではなく「どの類型の特徴に合うか」だけを示します。正常取引も同じ特徴を多く持つため(受取停止49%・休眠口座51%)、不正判定はMLモデルに従ってください。",
     "此清单仅显示交易符合哪种欺诈类型的特征，而非是否为欺诈。正常交易也常具备这些特征(收款账户停用 49%、休眠账户 51%)，欺诈判定请以 ML 模型为准。")
_add("s5.rule_score", "지표 충족 · 적합도 지수 {idx}배", "indicators met · fit index {idx}×",
     "指標該当 · 適合度指数 {idx}倍", "符合指标 · 契合指数 {idx}倍")
_add("s5.rule_mismatch",
     "⚠ 규칙상으로는 {tp}형이 더 잘 맞습니다 (적합도 {a} vs {b} = {g}배). 모델과 규칙이 엇갈리는 건은 수동 검토를 권장합니다.",
     "⚠ The rules fit type {tp} better (fit {a} vs {b} = {g}×). Manual review is recommended when model and rules disagree.",
     "⚠ ルール上は{tp}型のほうが適合します(適合度 {a} vs {b} = {g}倍)。モデルとルールが食い違う件は手動確認を推奨します。",
     "⚠ 按规则更符合 {tp} 型(契合度 {a} vs {b} = {g} 倍)。模型与规则不一致时建议人工复核。")
_add("s5.rule_ranking", "규칙 적합도 순위: {r}", "Rule fit ranking: {r}",
     "ルール適合度順位: {r}", "规则契合度排名: {r}")

# ══════════════════════════════════════════════════════════
# ✨ v17 — 전체 단축키 모음 모달 + 실측 근거 라벨
# ══════════════════════════════════════════════════════════
_add("kbd.modal_title", "⌨ 단축키 모음", "⌨ Keyboard shortcuts", "⌨ ショートカット一覧", "⌨ 快捷键一览")
_add("kbd.modal_help",
     "입력창·선택박스에 커서가 있을 때는 단축키가 동작하지 않습니다 (오타 방지).",
     "Shortcuts are disabled while the cursor is in a text box or select (to avoid typos).",
     "入力欄・選択ボックスにカーソルがある間はショートカットが無効です(誤入力防止)。",
     "光标位于输入框或选择框内时快捷键不生效(防止误输入)。")
_add("kbd.modal_note",
     "한글 입력 중(IME 조합)에는 무시됩니다. 영문 입력 상태에서 눌러주세요.",
     "Ignored while a Korean/CJK IME is composing. Press in Latin input mode.",
     "日本語入力(IME変換中)は無視されます。英数入力で押してください。",
     "中文输入法组字过程中会被忽略。请在英文输入状态下按键。")
_add("kbd.k_session", "세션 1~5 이동", "Jump to session 1-5", "セッション1〜5へ移動", "跳转到会话 1-5")
_add("kbd.k_move", "이전 / 다음 세션", "Previous / next session", "前 / 次のセッション", "上一个 / 下一个会话")
_add("kbd.k_guide", "사용 안내 열기 (각 세션 설명)", "Open the guide (what each session does)",
     "使い方案内を開く", "打开使用指南")
_add("kbd.k_help", "이 단축키 모음 열기", "Open this shortcut list", "このショートカット一覧を開く", "打开此快捷键列表")
_add("kbd.k_chat", "AI 챗봇 열기 / 입력창 포커스", "Open AI chat / focus the input",
     "AIチャットを開く / 入力欄へ", "打开 AI 聊天 / 聚焦输入框")
_add("kbd.k_compact", "컴팩트 모드 켜기·끄기", "Toggle compact mode", "コンパクトモード切替", "切换紧凑模式")
_add("kbd.k_ui", "UI 스타일 전환", "Switch UI style", "UIスタイル切替", "切换 UI 风格")
_add("kbd.k_theme", "테마 전환 (다크/라이트)", "Switch theme (dark/light)", "テーマ切替", "切换主题")
_add("kbd.k_lang", "언어 전환 (한/영/일/중)", "Switch language (KO/EN/JA/ZH)", "言語切替", "切换语言")
_add("kbd.k_settings", "설정 패널 열기", "Open the settings panel", "設定パネルを開く", "打开设置面板")
_add("kbd.k_toast", "단축키 요약 토스트 (간단 참조)", "Quick shortcut toast (brief reference)",
     "ショートカット要約トースト", "快捷键摘要提示")
# ✨ v18: 신규 단축키 5개 (사이드바 · 초보자 설명 · 세션 5 직행 · 세션 1 직행 · 챗봇 닫기)
_add("kbd.k_sidebar", "사이드바 펼치기/접기", "Toggle sidebar", "サイドバー開閉切替", "侧边栏展开/收起")
_add("kbd.k_beginner", "초보자 설명 켜기·끄기", "Toggle beginner tips", "初心者向け説明の切替", "切换新手提示")
_add("kbd.k_detect", "5번째 세션(탐지)으로 바로 이동", "Jump straight to session 5 (detection)",
     "5番目のセッション(検知)へ直接移動", "直接跳转到第5个会话(检测)")
_add("kbd.k_home", "1번째 세션으로 바로 이동", "Jump straight to session 1",
     "1番目のセッションへ直接移動", "直接跳转到第1个会话")
_add("kbd.k_chatclose", "챗봇 닫기", "Close chatbot", "チャットボットを閉じる", "关闭聊天机器人")
_add("common.measured_evidence", "실측 근거", "Measured evidence", "実測根拠", "实测依据")

# ══════════════════════════════════════════════════════════
# ✨ v18 — 사이드바 정리 (데이터 경로 → 설정 팝오버 이주)
# ══════════════════════════════════════════════════════════
_add("cfg.paths_title", "📁 데이터 경로", "📁 Data paths", "📁 データパス", "📁 数据路径")
_add("cfg.paths_help",
     "한 번 정하면 거의 바꾸지 않는 값이라 사이드바에서 이곳으로 옮겼습니다. 변경 후에는 화면이 자동으로 다시 계산됩니다.",
     "These rarely change once set, so they moved here from the sidebar. The app recalculates automatically after a change.",
     "一度決めればほぼ変更しない値のため、サイドバーからこちらへ移しました。変更後は自動的に再計算されます。",
     "这些值设定后几乎不再更改，因此从侧边栏移至此处。修改后界面会自动重新计算。")
_add("cfg.folder_help",
     "이 폴더를 스캔해 사이드바 '평가 데이터셋 선택' 목록을 만듭니다 (CSV · Parquet · X/y 분할셋).",
     "Scanned to build the 'Evaluation dataset' list in the sidebar (CSV, Parquet, X/y split sets).",
     "このフォルダをスキャンしてサイドバーの「評価データセット選択」一覧を作ります。",
     "扫描该文件夹以生成侧边栏「评估数据集选择」列表。")
_add("onb.reopen_short", "🎓 사용 안내", "🎓 Guide", "🎓 使い方", "🎓 使用指南")
_add("s5.autofill_help",
     "고액·원거리·루팅·VPN 등 고위험 조합을 폼에 한 번에 채웁니다. 현재 입력값은 덮어써집니다.",
     "Fills the form with a high-risk combination (large amount, long distance, rooting, VPN). Current values are overwritten.",
     "高額・遠距離・ルート化・VPN等の高リスク組合せを一括入力します。現在の入力値は上書きされます。",
     "一次性填入大额、远距离、越狱、VPN 等高风险组合。当前输入值将被覆盖。")

# ══════════════════════════════════════════════════════════
# ✨ v18 — 챗봇 발송 요청 확인 카드 (Human-in-the-loop)
# ══════════════════════════════════════════════════════════
_add("s5.send_confirm_title", "📨 챗봇이 발송을 요청했습니다 — 승인이 필요합니다",
     "📨 The chatbot requested a send — your approval is required",
     "📨 チャットボットが送信を要求しました — 承認が必要です",
     "📨 聊天机器人请求发送 — 需要您的批准")
_add("s5.send_confirm_ch", "채널", "Channel", "チャネル", "渠道")
_add("s5.send_confirm_to", "수신", "To", "宛先", "收件人")
_add("s5.send_confirm_to_none", "(미설정 — 아래 환경설정에서 입력)", "(not set — enter it in settings below)",
     "(未設定 — 下の設定で入力)", "(未设置 — 请在下方设置中填写)")
_add("s5.send_confirm_subj", "제목", "Subject", "件名", "主题")
_add("s5.send_confirm_mask", "마스킹", "Masking", "マスキング", "脱敏级别")
_add("s5.send_confirm_preview", "📄 발송 본문 미리보기", "📄 Preview the message body",
     "📄 送信本文プレビュー", "📄 预览发送正文")
_add("s5.send_confirm_att", "첨부 {n}건", "{n} attachment(s)", "添付 {n} 件", "{n} 个附件")
_add("s5.send_confirm_go", "✅ 승인하고 발송", "✅ Approve and send", "✅ 承認して送信", "✅ 批准并发送")
_add("s5.send_confirm_cancel", "취소", "Cancel", "キャンセル", "取消")
_add("s5.send_confirm_sent", "발송 완료", "Sent", "送信しました", "已发送")
_add("chat.act_request_send",
     "{ch} 발송을 요청했어요. 실시간 탐지 화면에 확인 카드가 떴으니, 내용을 확인하고 승인 버튼을 눌러주세요 (제가 바로 보내지는 않아요)",
     "I requested a {ch} send. A confirmation card is now on the live-detection screen — review it and press approve (I do not send it myself)",
     "{ch} 送信を要求しました。リアルタイム検知画面に確認カードが出ています。内容を確認して承認してください(私が直接送信することはありません)",
     "已请求 {ch} 发送。实时检测界面已显示确认卡片，请查看后点击批准(我不会直接发送)")
_add("chat.act_send_no_result",
     "먼저 탐지를 실행해야 발송할 내용이 생겨요. '탐지 실행'을 눌러주세요",
     "Run a detection first so there is something to send. Press 'Run detection'",
     "先に検知を実行しないと送信する内容がありません。「検知実行」を押してください",
     "请先执行检测才有可发送的内容。请点击「执行检测」")
_add("chat.act_cancel_send", "대기 중이던 발송 요청을 취소했어요", "Cancelled the pending send request",
     "保留中の送信要求をキャンセルしました", "已取消待处理的发送请求")
_add("chat.act_cancel_send_none", "취소할 발송 요청이 없어요", "There is no pending send request",
     "キャンセルする送信要求がありません", "没有待处理的发送请求")

# ══════════════════════════════════════════════════════════
# ✨ v19 — 챗봇 발송 승인 게이트 토글
# ══════════════════════════════════════════════════════════
_add("s5.agent_gate_toggle", "🚦 챗봇 발송 승인 게이트", "🚦 Approval gate for chatbot sends",
     "🚦 チャット送信の承認ゲート", "🚦 聊天发送审批闸门")
_add("s5.agent_gate_help",
     "켜짐(기본): 챗봇이 발송을 요청하면 확인 카드가 뜨고, 내용을 확인한 뒤 승인해야 전송됩니다. 끄면 챗봇 요청만으로 즉시 발송됩니다 — 빠르지만 되돌릴 수 없습니다.",
     "ON (default): a confirmation card appears when the chatbot requests a send; you review and approve before it goes out. OFF: the chatbot's request sends immediately — fast, but irreversible.",
     "オン(既定): チャットが送信を要求すると確認カードが表示され、承認後に送信されます。オフ: 要求だけで即時送信されます — 速いですが取り消せません。",
     "开启(默认)：聊天机器人请求发送时会弹出确认卡片，经您审核批准后才发送。关闭：仅凭请求即立即发送 — 快速但不可撤销。")
_add("s5.agent_gate_off_warn",
     "⚡ 즉시 발송 모드 — 챗봇 요청만으로 메일·Slack이 바로 나갑니다. 발송은 되돌릴 수 없습니다.",
     "⚡ Immediate-send mode — a chatbot request alone dispatches mail/Slack. Sends cannot be undone.",
     "⚡ 即時送信モード — チャットの要求だけでメール・Slackが送信されます。取り消せません。",
     "⚡ 立即发送模式 — 仅凭聊天请求即发出邮件/Slack。发送无法撤销。")
_add("s5.agent_gate_off_pii",
     "🔴 위험 조합: 마스킹 OFF + 승인 게이트 OFF — 미마스킹 개인정보가 승인 없이 외부로 나갈 수 있습니다.",
     "🔴 Dangerous combination: masking OFF + approval gate OFF — unmasked PII can leave without review.",
     "🔴 危険な組合せ: マスキングOFF + 承認ゲートOFF — 未マスクの個人情報が確認なしに外部送信されます。",
     "🔴 危险组合：脱敏关闭 + 审批闸门关闭 — 未脱敏的个人信息可能未经审核外发。")
_add("s5.agent_audit_title", "🧾 게이트 없이 발송된 기록 ({n}건)", "🧾 Sent without gate ({n})",
     "🧾 ゲートなし送信の記録 ({n}件)", "🧾 未经闸门的发送记录 ({n} 条)")
_add("chat.act_sent_now_ok", "{ch} 발송을 완료했어요 (즉시 발송 모드)",
     "Sent via {ch} (immediate-send mode)", "{ch} で送信しました(即時送信モード)",
     "已通过 {ch} 发送(立即发送模式)")
_add("chat.act_sent_now_fail", "{ch} 발송에 실패했어요 — {e}", "{ch} send failed — {e}",
     "{ch} の送信に失敗しました — {e}", "{ch} 发送失败 — {e}")
_add("chat.act_sent_now_unmasked",
     "⚠️ 마스킹이 꺼진 상태로 나갔습니다. 개인정보 보호가 필요하면 마스킹을 켜주세요.",
     "⚠️ It went out with masking disabled. Turn masking on if PII protection is needed.",
     "⚠️ マスキング無効のまま送信されました。個人情報保護が必要なら有効にしてください。",
     "⚠️ 已在脱敏关闭状态下发出。如需保护个人信息请开启脱敏。")
