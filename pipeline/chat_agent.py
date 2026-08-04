"""
ChatAgent — FDS 대시보드 해설·대화 봇 (읽기 전용 v1)

설계 요지
  · 대화 히스토리 + (이미 마스킹된) 대시보드 상태 스냅샷을 단일 프롬프트로 평탄화하여
    LLMAnalyzer._call 을 재사용한다. → 모든 프로바이더(local/anthropic/openai/…)에서 동작하고,
    LLMAnalyzer 의 cloud_fallback(PII 락)·에러 수집 로직을 그대로 승계한다.
  · PII: 컨텍스트 텍스트는 대시보드 쪽 _build_masker() 정책으로 이미 마스킹된 상태로 전달받는다
    (로컬+스킵이면 원문 유지·외부 전송 차단 / 외부 프로바이더면 마스킹 적용).
  · 도구 실행(탭 이동·값 입력·분석 실행)은 다음 증분에서 레지스트리와 함께 추가 예정.
    현재 버전은 "화면을 읽고 해설/질의응답"만 수행하는 읽기 전용이다.
"""

from __future__ import annotations

import re
import logging

log = logging.getLogger(__name__)

MAX_TURNS = 12   # 프롬프트에 포함할 최근 대화 턴 수 (과대 프롬프트 방지)

_SYSTEM = {
    "ko": ("당신은 전자금융 이상거래탐지(FDS) 대시보드의 친절한 해설 도우미입니다. "
           "아래 [현재 대시보드 상태]에 주어진 정보만을 근거로, 통계에 익숙하지 않은 사용자도 "
           "이해할 수 있게 쉽고 간결하게 한국어로 답하세요. 상태에 없는 수치는 지어내지 말고 "
           "'화면에 표시되지 않았다'고 답하세요. µF1·정밀도·재현율·위험점수 같은 지표는 "
           "전문용어를 풀어 쉬운 말로 설명하세요. 마크다운 표는 피하고 짧게 답하세요.\n"
           "⚠ 매우 중요: [이전 대화]는 대화 흐름 참고용일 뿐, 검증된 사실이 아닙니다. "
           "이전 AI 답변에 등장한 수치·주장이라도 지금의 [현재 대시보드 상태]에 없다면 "
           "그 이전 답변이 틀렸을 가능성이 높습니다. 절대 이전 답변을 그대로 재인용하거나 "
           "사실로 취급하지 말고, 매번 오직 [현재 대시보드 상태]만 다시 확인해 답하세요. "
           "이전 답변과 실제 상태가 다르면 조용히 정정해서 답하세요."),
    "en": ("You are a friendly explainer for a financial fraud-detection (FDS) dashboard. "
           "Answer only from the [Current dashboard state] below, in clear and concise English that "
           "a non-statistician can follow. Do not invent numbers that aren't in the state — say they "
           "aren't shown on screen. Explain metrics like µF1, precision, recall, and risk score in plain "
           "words. Avoid markdown tables and keep answers short.\n"
           "⚠ Very important: [Previous conversation] is for conversational flow only — it is NOT "
           "verified fact. Even if a prior AI turn stated a number or claim, if it isn't in the current "
           "[Current dashboard state], that earlier answer was likely wrong. Never restate or treat a "
           "previous answer as true; re-derive every answer solely from [Current dashboard state] each "
           "time, and quietly correct any past answer that conflicts with it."),
    "ja": ("あなたは金融不正検知(FDS)ダッシュボードの親切な解説アシスタントです。"
           "以下の[現在のダッシュボード状態]の情報だけを根拠に、統計に不慣れな利用者にも分かるよう "
           "簡潔な日本語で答えてください。状態にない数値は作らず「画面に表示されていない」と答えます。"
           "µF1・適合率・再現率・リスクスコア等の指標は専門用語を噛み砕いて説明してください。"
           "マークダウン表は避け、短く答えてください。\n"
           "⚠ 重要: [これまでの会話]は会話の流れの参考にすぎず、検証された事実ではありません。"
           "以前のAIの回答に数値や主張があっても、現在の[現在のダッシュボード状態]になければ、"
           "その回答は誤りである可能性が高いです。過去の回答をそのまま真実として繰り返さず、"
           "毎回[現在のダッシュボード状態]だけを根拠に答え直し、矛盾があれば静かに訂正してください。"),
    "zh": ("你是金融欺诈检测(FDS)仪表板的友好讲解助手。"
           "仅根据下面的[当前仪表板状态]作答，用非统计专业者也能理解的简洁中文回答。"
           "状态中没有的数字不要编造，请说明「屏幕上未显示」。对 µF1、精确率、召回率、风险分数等指标，"
           "请用通俗语言解释。避免使用 Markdown 表格，回答要简短。\n"
           "⚠ 非常重要：[此前对话]仅用于对话连贯性参考，并非已验证的事实。即使之前的AI回复中出现过"
           "某个数字或说法，只要它不在当前的[当前仪表板状态]中，那个旧回复很可能是错的。切勿原样重复"
           "或把旧回复当作事实，每次都必须只依据[当前仪表板状态]重新作答，如与旧回复冲突请悄悄予以更正。"),
}

# ✨ v18: 워처·DB 실측 사실과 자가진단 결과가 상태에 함께 들어온다.
#   이 값들은 파이썬이 실제로 조회·점검한 것이므로, LLM이 다시 추론하면
#   그럴듯한 오답을 만든다(예: 멀쩡한 워처를 죽었다고 단정). 인용만 하게 못박는다.
_FACTS_RULE = {
    "ko": ("\n[자가진단] 항목이 상태에 있으면, 그 판정과 조치 문구를 그대로 전달하세요. "
           "원인을 스스로 추측하거나 순서를 바꾸지 말고, '문제'로 표시된 항목을 먼저 안내하세요. "
           "워처 임계값과 화면 상단 임계값은 서로 다른 값입니다 — 사용자가 '임계값'만 말하면 "
           "어느 쪽인지 되물어 확인하세요."),
    "en": ("\nIf a [self-diagnosis] section is present, relay its verdicts and fixes verbatim. "
           "Do not infer causes yourself or reorder them; surface items marked as problems first. "
           "The watcher threshold and the on-screen threshold are different values — if the user "
           "just says 'threshold', ask which one they mean."),
    "ja": ("\n[自己診断]の項目があれば、その判定と対処文をそのまま伝えてください。"
           "原因を自分で推測せず、問題と表示された項目を先に案内してください。"
           "ウォッチャーの閾値と画面上部の閾値は別の値です — 「閾値」とだけ言われたらどちらか確認してください。"),
    "zh": ("\n若状态中含[自我诊断]部分，请原样转达其判定与处理建议。"
           "不要自行推测原因，先说明标记为问题的项目。"
           "监视器阈值与页面顶部阈值是不同的值 — 用户只说\"阈值\"时请先确认是哪一个。"),
}
for _lk in list(_SYSTEM):
    _SYSTEM[_lk] = _SYSTEM[_lk] + _FACTS_RULE.get(_lk, "")

_ROLE = {"ko": ("사용자", "AI"), "en": ("User", "AI"),
         "ja": ("ユーザー", "AI"), "zh": ("用户", "AI")}

_NO_CTX = {"ko": "(표시된 상태 정보 없음)", "en": "(no state shown)",
           "ja": "(表示された状態情報なし)", "zh": "(无显示的状态信息)"}

_FALLBACK = {
    "ko": "⚠ LLM 응답을 받지 못했어요. 세션 5의 LLM 설정/연결을 확인해 주세요.",
    "en": "⚠ No response from the LLM. Please check the LLM settings/connection in Session 5.",
    "ja": "⚠ LLMから応答がありません。セッション5のLLM設定・接続を確認してください。",
    "zh": "⚠ 未收到 LLM 响应。请检查会话 5 中的 LLM 设置/连接。",
}


_HIST_HEADER = {
    "ko": "[이전 대화 — 대화 흐름 참고용, 사실 검증 안 됨. 아래 내용과 다르더라도 [현재 대시보드 상태]가 항상 우선]",
    "en": "[Previous conversation — for flow only, NOT verified fact. If it conflicts with anything above, [Current dashboard state] always wins]",
    "ja": "[これまでの会話 — 流れ参考用、事実未検証。内容と食い違っても[現在のダッシュボード状態]を常に優先]",
    "zh": "[此前对话 — 仅供对话连贯参考，未经事实核实。如与之冲突，始终以[当前仪表板状态]为准]",
}

_REGROUND = {
    "ko": "\n\n(다시 확인: 위 [이전 대화]는 참고일 뿐입니다. 지금 답은 오직 위 [현재 대시보드 상태]만 근거로, 이전 답변이 틀렸다면 조용히 정정해서 작성하세요.)",
    "en": "\n\n(Reminder: [Previous conversation] above is reference only. Base this answer solely on [Current dashboard state], quietly correcting any earlier wrong claim.)",
    "ja": "\n\n(再確認: 上記[これまでの会話]は参考にすぎません。今回の回答は[現在のダッシュボード状態]だけを根拠にし、以前の誤りがあれば静かに訂正してください。)",
    "zh": "\n\n(提醒：上面的[此前对话]仅供参考。请仅依据[当前仪表板状态]作答，如之前有错误说法请悄悄予以更正。)",
}

_ACTED = {
    "ko": "네, 요청한 화면·설정을 적용했어요.",
    "en": "Done — I applied the requested screen/setting.",
    "ja": "はい、ご要望の画面・設定を適用しました。",
    "zh": "好的，已应用所请求的界面/设置。",
}

_HIST_TRUNC = 220   # 히스토리 항목(특히 이전 AI 답변)의 최대 길이 — 과거 할루시네이션이 그대로 반복·강화되는 표면을 줄인다


def default_system(lang: str = "ko") -> str:
    """UI 프롬프트 편집기 프리필용 — 해당 언어의 기본 시스템 프롬프트를 반환."""
    return _SYSTEM.get(lang, _SYSTEM["ko"])


# ══════════════════════════════════════════════════════════
# 에이전트 액션 화이트리스트 (② 레지스트리)
#   · 여기 등록된 이름/인자만 파싱·검증되며, 실제 상태 변경은 dashboard의 실행기가 수행.
#   · 텍스트 프로토콜: LLM이 답변에 [[ACTION: 이름(인자)]] 을 적으면 파싱한다
#     (로컬 모델 포함 모든 프로바이더에서 동작 — provider별 function-calling 의존 없음).
#   · v1은 위젯 key 충돌이 없는 plain state만 대상: 세션 이동 / 초보자모드.
#     (s5 탭 이동·값 입력·분석 실행은 pending-key 패턴이 필요 → 다음 증분)
# ══════════════════════════════════════════════════════════
ACTIONS = {
    "goto_session": {
        "kind": "int", "min": 1, "max": 5,
        "example": "goto_session(2)",
        "label": {
            "ko": "메인 세션 이동(1~5). 1=개요/데이터, 2=모델 성능, 3=오탐·미탐, 4=합성 데이터, 5=실시간 탐지",
            "en": "Go to main session (1-5). 1=Overview, 2=Model performance, 3=FP/FN, 4=Synthetic data, 5=Detection",
            "ja": "メインセッション移動(1〜5)。1=概要, 2=モデル性能, 3=誤検知・見逃し, 4=合成データ, 5=検知",
            "zh": "跳转主会话(1-5)。1=概览, 2=模型性能, 3=误报漏报, 4=合成数据, 5=实时检测",
        },
    },
    "goto_s5_tab": {
        "kind": "enum", "values": ["manual", "test", "train", "synthetic", "folder"],
        "example": "goto_s5_tab(manual)",
        "label": {
            "ko": "세션5 입력 방식 탭 이동. manual=직접입력, test=test.csv, train=train.csv, synthetic=합성생성, folder=폴더배치",
            "en": "Switch session-5 input tab. manual/test/train/synthetic/folder",
            "ja": "セッション5の入力タブ切替。manual/test/train/synthetic/folder",
            "zh": "切换会话5输入选项卡。manual/test/train/synthetic/folder",
        },
    },
    "set_manual_field": {
        "kind": "field2", "fields": ["amount", "distance", "balance", "channel", "os"],
        "example": "set_manual_field(amount, 50000000)",
        "label": {
            "ko": "직접입력 폼 값 채우기. field=amount/distance/balance/channel/os, value=값 (예: 금액 5천만이면 amount, 50000000)",
            "en": "Fill a manual-input field. field=amount/distance/balance/channel/os, value=the value",
            "ja": "直接入力フォームの値を設定。field=amount/distance/balance/channel/os, value=値",
            "zh": "填写直接输入表单字段。field=amount/distance/balance/channel/os, value=值",
        },
    },
    "run_detection": {
        "kind": "none",
        "example": "run_detection()",
        "label": {
            "ko": "직접입력 화면의 현재 값으로 탐지 실행 (값을 먼저 set_manual_field로 채운 뒤 사용)",
            "en": "Run detection with current manual-input values (fill fields first with set_manual_field)",
            "ja": "直接入力の現在値で検知を実行(先に set_manual_field で値を設定)",
            "zh": "用直接输入的当前值运行检测(先用 set_manual_field 填值)",
        },
    },
    "goto_batch_subtab": {
        "kind": "enum", "values": ["all", "analysis", "slack", "email"],
        "example": "goto_batch_subtab(analysis)",
        "label": {
            "ko": "배치 결과 하위 탭 이동. all=전체결과, analysis=AI분석, slack=Slack, email=Email",
            "en": "Switch batch-result sub-tab. all/analysis/slack/email",
            "ja": "バッチ結果のサブタブ切替。all/analysis/slack/email",
            "zh": "切换批量结果子选项卡。all/analysis/slack/email",
        },
    },
    "set_manual_flag": {
        "kind": "flag2",
        "example": "set_manual_flag(vpn, on)",
        "label": {
            "ko": "직접입력 위험 플래그 on/off. 플래그명 일부(예: rooting, vpn, unused, suspend, malicious) + on/off",
            "en": "Toggle a manual-input risk flag on/off. partial flag name (e.g., rooting, vpn, unused, suspend) + on/off",
            "ja": "直接入力のリスクフラグをon/off。フラグ名の一部(rooting, vpn 等) + on/off",
            "zh": "开关直接输入的风险标记。标记名片段(如 rooting, vpn) + on/off",
        },
    },
    # ══════════════════════════════════════════════════════
    # ✨ v15: 대시보드를 실제로 "운용"하는 데 필요했던 액션 8종 추가
    #   기존 7종은 화면 이동·직접입력 폼에 한정돼 있어, 임계값·모델·데이터셋 같은
    #   핵심 제어를 말로 바꿀 수 없었다(사용자가 결국 손으로 만져야 했다).
    # ══════════════════════════════════════════════════════
    "set_threshold": {
        "kind": "float", "min": 0.0, "max": 1.0,
        "example": "set_threshold(0.7)",
        "label": {
            "ko": "이상거래 판정 임계값 설정(0.0~1.0). 높이면 오탐↓미탐↑, 낮추면 반대",
            "en": "Set the anomaly threshold (0.0-1.0). Higher = fewer false positives, more misses",
            "ja": "異常判定の閾値設定(0.0〜1.0)。高くすると誤検知↓見逃し↑",
            "zh": "设置异常判定阈值(0.0-1.0)。越高误报↓漏报↑",
        },
    },
    "set_watcher_threshold": {
        "kind": "field2", "fields": ["review", "confirm"],
        "example": "set_watcher_threshold(review, 0.30)",
        "label": {
            "ko": ("워처(무인 감시) 임계값 설정. review=1차(Slack만·검토요청), "
                   "confirm=2차(Slack+Email·확정통보). 화면 상단 임계값과는 별개이며 "
                   "저장 즉시 워처에 5초 내 반영된다. 사용자가 어느 쪽인지 말하지 않았으면 먼저 물을 것"),
            "en": ("Set the watcher (unattended) threshold. review=tier1 (Slack only), "
                   "confirm=tier2 (Slack+Email). Separate from the on-screen threshold; "
                   "applies to the running watcher within 5s. Ask which tier if unspecified"),
            "ja": ("ウォッチャー(無人監視)の閾値設定。review=1次(Slackのみ)、confirm=2次(Slack+Email)。"
                   "画面上部の閾値とは別で、保存後5秒以内に反映される"),
            "zh": ("设置监视器(无人值守)阈值。review=一级(仅Slack)，confirm=二级(Slack+Email)。"
                   "与页面顶部阈值不同，保存后5秒内生效"),
        },
    },
    "watcher_stop": {
        "kind": "int", "min": 0, "max": 1440,
        "example": "watcher_stop(30)",
        "label": {
            "ko": ("워처(무인 감시) 중지 요청. 인자는 자동 재개까지의 분(0=무기한). "
                   "즉시 실행되지 않고 화면에 확인 카드가 뜨며 사람이 승인해야 실행된다. "
                   "중지 중에는 탐지·알림이 전혀 나가지 않으므로 되도록 자동 재개 시간을 함께 받을 것"),
            "en": ("Request to stop the watcher. Arg = minutes until auto-resume (0 = indefinite). "
                   "Shows a confirmation card; a human must approve. Detection stops entirely while off, "
                   "so prefer asking for an auto-resume time"),
            "ja": ("ウォッチャー停止要求。引数は自動再開までの分(0=無期限)。確認カードが表示され人の承認が必要"),
            "zh": ("请求停止监视器。参数为自动恢复前的分钟数(0=无限期)。将显示确认卡片，需人工批准"),
        },
    },
    "watcher_start": {
        "kind": "none",
        "example": "watcher_start()",
        "label": {
            "ko": "워처(무인 감시) 시작 요청. 확인 카드 승인 후 실행된다",
            "en": "Request to start the watcher. Runs after confirmation",
            "ja": "ウォッチャー開始要求。確認後に実行",
            "zh": "请求启动监视器。确认后执行",
        },
    },
    "reprocess_file": {
        "kind": "text",
        "example": "reprocess_file(batch_0804.csv)",
        "label": {
            "ko": ("감시 파일의 처리 커서를 지워 전량 재처리한다. 되돌릴 수 없고 "
                   "이미 보낸 알림이 다시 갈 수 있으므로 확인 카드 승인이 필요하다"),
            "en": ("Clear a watched file's cursor so it is reprocessed from the start. "
                   "Irreversible and may resend alerts — requires confirmation"),
            "ja": "監視ファイルのカーソルを消して全件再処理。確認が必要",
            "zh": "清除监视文件的游标以重新处理全部行。需确认",
        },
    },
    "select_model": {
        "kind": "text",
        "example": "select_model(lgbm_13class)",
        "label": {
            "ko": "탐지·평가에 쓸 모델 선택. 모델명 일부만 적어도 됨(예: lgbm_13class, xgboost)",
            "en": "Select the model for detection/evaluation. A name fragment is enough (e.g. lgbm_13class)",
            "ja": "検知・評価に使うモデルを選択。名前の一部でも可(例: lgbm_13class)",
            "zh": "选择用于检测/评估的模型。可只写名称片段(如 lgbm_13class)",
        },
    },
    "select_dataset": {
        "kind": "text",
        "example": "select_dataset(X_va)",
        "label": {
            "ko": "분석에 쓸 데이터셋 선택. 파일명 일부만 적어도 됨(예: X_va, train.csv)",
            "en": "Select the dataset to analyse. A filename fragment is enough (e.g. X_va, train.csv)",
            "ja": "分析に使うデータセットを選択。ファイル名の一部でも可(例: X_va)",
            "zh": "选择用于分析的数据集。可只写文件名片段(如 X_va)",
        },
    },
    "set_eval_mode": {
        "kind": "enum", "values": ["static", "dynamic"],
        "example": "set_eval_mode(dynamic)",
        "label": {
            "ko": "세션2 평가 모드. dynamic=선택 데이터셋×모델 실시간 재평가, static=학습 시점 리포트",
            "en": "Session-2 evaluation mode. dynamic = live re-evaluation on the selected dataset/model; static = training-time report",
            "ja": "セッション2の評価モード。dynamic=選択データ×モデルで再評価, static=学習時レポート",
            "zh": "会话2评估模式。dynamic=按所选数据集×模型实时重评，static=训练时报告",
        },
    },
    "run_batch": {
        "kind": "none",
        "example": "run_batch()",
        "label": {
            "ko": "현재 선택된 여러 건에 대해 일괄 분석 실행 (먼저 test/train/합성 탭에서 여러 건을 추출해야 함)",
            "en": "Run batch analysis on the currently loaded rows (extract several rows first in the test/train/synthetic tab)",
            "ja": "現在読み込まれた複数件で一括分析を実行(先にtest/train/合成タブで複数抽出)",
            "zh": "对当前载入的多条记录执行批量分析(需先在 test/train/合成 选项卡抽取多条)",
        },
    },
    "set_pii_level": {
        "kind": "enum", "values": ["off", "basic", "standard", "strict"],
        "example": "set_pii_level(strict)",
        "label": {
            "ko": "개인정보 마스킹 강도. off=없음, basic=이름·식별번호, standard=+IP·위치·계좌, strict=+생년·시간",
            "en": "PII masking level. off / basic (name, ID) / standard (+IP, location, account) / strict (+birth year, timestamps)",
            "ja": "個人情報マスキング強度。off / basic / standard / strict",
            "zh": "个人信息脱敏强度。off / basic / standard / strict",
        },
    },
    "set_compact_mode": {
        "kind": "onoff",
        "example": "set_compact_mode(on)",
        "label": {
            "ko": "컴팩트 모드(스크롤 없이 한 화면에 보기) 켜기/끄기",
            "en": "Turn compact mode (fit a session on one screen) on/off",
            "ja": "コンパクトモード(1画面表示)のオン/オフ",
            "zh": "开关紧凑模式(一屏显示)",
        },
    },
    "autofill_high_risk": {
        "kind": "none",
        "example": "autofill_high_risk()",
        "label": {
            "ko": "직접입력 폼에 고위험 시나리오 예시값을 한 번에 채움(고액·원거리·루팅·VPN 등)",
            "en": "Fill the manual-input form with a high-risk scenario at once (large amount, long distance, rooting, VPN…)",
            "ja": "直接入力フォームに高リスクシナリオの例を一括入力(高額・遠距離・ルート化・VPN等)",
            "zh": "一次性将高风险场景示例填入直接输入表单(大额、远距离、越狱、VPN 等)",
        },
    },
    # ══════════════════════════════════════════════════════
    # 📨 v18: 발송 요청 액션 — **즉시 발송하지 않는다**
    #   다른 14종은 되돌릴 수 있지만(임계값 바꿨다 되돌리면 끝) 메일·Slack은
    #   한 번 나가면 회수가 불가능하다. LLM이 문맥을 오해해 발송을 뱉으면
    #   담당자에게 오발송된다 → 액션은 '요청'까지만 하고, 대시보드가 미리보기와
    #   함께 확인 카드를 띄운 뒤 **사람이 승인 버튼을 눌러야** 실제로 전송된다.
    #   (Human-in-the-loop: 비가역 작업에만 확인 게이트를 둔다)
    # ══════════════════════════════════════════════════════
    "request_send": {
        "kind": "enum", "values": ["slack", "email", "both"],
        "example": "request_send(slack)",
        "label": {
            "ko": "탐지 결과 발송을 '요청'한다. 즉시 나가지 않고 확인 카드가 떠서 사람이 승인해야 전송됨 (slack | email | both)",
            "en": "Request sending the detection result. It is NOT sent immediately — a confirmation card appears and a human must approve (slack | email | both)",
            "ja": "検知結果の送信を『要求』します。即時送信されず、確認カードで人が承認して初めて送信されます (slack | email | both)",
            "zh": "请求发送检测结果。不会立即发送——会弹出确认卡片，需人工批准后才发送 (slack | email | both)",
        },
    },
    "cancel_send": {
        "kind": "none",
        "example": "cancel_send()",
        "label": {
            "ko": "대기 중인 발송 요청을 취소한다",
            "en": "Cancel a pending send request",
            "ja": "保留中の送信要求をキャンセルします",
            "zh": "取消待处理的发送请求",
        },
    },
    "set_beginner_mode": {
        "kind": "onoff",
        "example": "set_beginner_mode(on)",
        "label": {
            "ko": "초보자 설명(쉬운 해설) 켜기/끄기. 인자: on 또는 off",
            "en": "Turn beginner hints on/off. arg: on or off",
            "ja": "初心者ガイドのオン/オフ。引数: on または off",
            "zh": "开关新手提示。参数：on 或 off",
        },
    },
}

_ACTION_HEADER = {
    "ko": ("\n\n[사용 가능한 동작]\n사용자를 특정 화면으로 데려가거나 설정을 바꾸는 게 도움이 될 때만, "
           "답변 맨 끝에 아래 형식으로 한 줄씩 적으세요(불필요하면 생략). 그 외에는 평소처럼 답하세요.\n"
           "형식: [[ACTION: 이름(인자)]]\n"),
    "en": ("\n\n[Available actions]\nOnly when it helps to take the user to a screen or change a setting, "
           "append lines in the format below at the very end of your reply (omit if unnecessary). "
           "Otherwise answer normally.\nFormat: [[ACTION: name(arg)]]\n"),
    "ja": ("\n\n[利用可能な操作]\n特定の画面へ案内したり設定を変えると役立つ場合のみ、"
           "返答の最後に以下の形式で1行ずつ記載してください(不要なら省略)。それ以外は通常どおり回答します。\n"
           "形式: [[ACTION: 名前(引数)]]\n"),
    "zh": ("\n\n[可用操作]\n仅当带用户前往某屏幕或更改设置有帮助时，"
           "在回复末尾按下面格式逐行写出(不需要则省略)。其余情况正常回答。\n"
           "格式: [[ACTION: 名称(参数)]]\n"),
}


def actions_prompt(lang: str = "ko") -> str:
    """시스템 프롬프트에 덧붙일 '사용 가능한 동작' 안내 블록."""
    lang = lang if lang in _ACTION_HEADER else "ko"
    lines = "\n".join(
        f" - {name}: {meta['label'][lang]}  예) [[ACTION: {meta['example']}]]"
        for name, meta in ACTIONS.items()
    )
    return _ACTION_HEADER[lang] + lines


_ACTION_RE = re.compile(r"\[\[\s*ACTION\s*:\s*(\w+)\s*\(([^)]*)\)\s*\]\]", re.IGNORECASE)


def parse_actions(text: str):
    """LLM 응답에서 [[ACTION: ...]] 파싱·검증 → (마커 제거된 텍스트, [검증된 액션]).
    화이트리스트(ACTIONS)에 없거나 인자 검증 실패 시 무시(안전)."""
    if not text:
        return text, []
    acts = []
    for m in _ACTION_RE.finditer(text):
        name = m.group(1)
        raw = m.group(2).strip()
        meta = ACTIONS.get(name)
        if not meta:
            continue
        kind = meta["kind"]
        if kind == "float":
            try:
                v = float(raw.strip("'\"").rstrip("%"))
            except (ValueError, TypeError):
                continue
            if v > 1.0 and v <= 100.0:      # "70%" 처럼 준 경우 관용 처리
                v = v / 100.0
            if meta["min"] <= v <= meta["max"]:
                acts.append({"name": name, "arg": round(v, 4)})
        elif kind == "text":
            v = raw.strip().strip("'\"")
            if 1 <= len(v) <= 60:           # 실행기에서 화이트리스트 목록과 부분매칭
                acts.append({"name": name, "arg": v})
        elif kind == "int":
            try:
                v = int(raw.strip("'\""))
            except (ValueError, TypeError):
                continue
            if meta["min"] <= v <= meta["max"]:
                acts.append({"name": name, "arg": v})
        elif kind == "onoff":
            acts.append({"name": name,
                         "arg": raw.strip("'\"").lower() in ("on", "true", "1", "yes", "켜기", "켜", "オン", "开")})
        elif kind == "enum":
            v = raw.strip("'\"").lower()
            if v in meta["values"]:
                acts.append({"name": name, "arg": v})
        elif kind == "field2":
            parts = [p.strip().strip("'\"") for p in raw.split(",", 1)]
            if len(parts) == 2 and parts[0].lower() in meta["fields"]:
                acts.append({"name": name, "arg": {"field": parts[0].lower(), "value": parts[1]}})
        elif kind == "flag2":
            parts = [p.strip().strip("'\"") for p in raw.split(",", 1)]
            if len(parts) == 2 and parts[0]:      # 플래그명 매칭은 실행기(도메인)에서
                acts.append({"name": name, "arg": {"flag": parts[0], "value": parts[1]}})
        elif kind == "none":
            acts.append({"name": name, "arg": None})
    cleaned = _ACTION_RE.sub("", text).strip()
    return cleaned, acts


class ChatAgent:
    """읽기 전용 대시보드 해설 챗봇.

    Parameters
    ----------
    analyzer : LLMAnalyzer | None
        대시보드가 세션5 설정으로 만든 인스턴스를 그대로 넘긴다(프로바이더·키·PII 락 승계).
        None이면 폴백 메시지를 반환한다.
    lang : str
        UI 언어 ('ko'|'en'|'ja'|'zh').
    system_override : str | None
        비어있지 않으면 기본 _SYSTEM[lang] 대신 이 시스템 지시문을 사용한다
        (대시보드 '프롬프트 편집' UI에서 라이브 수정 → 재시작 불필요).
    """

    def __init__(self, analyzer, lang: str = "ko", system_override: str | None = None,
                 enable_actions: bool = True):
        self.analyzer = analyzer
        self.lang = lang if lang in _SYSTEM else "ko"
        self.system = (system_override or "").strip() or None
        self.enable_actions = enable_actions

    def answer(self, history: list[dict], user_msg: str, context_text: str):
        """이전 대화(history) + 사용자 메시지 + 마스킹된 상태 → (응답텍스트, 액션리스트).
        액션리스트는 검증된 [{'name','arg'}, ...] (없으면 빈 리스트)."""
        if self.analyzer is None:
            return _FALLBACK[self.lang], []
        prompt = self._build_prompt(history, user_msg, context_text)
        try:
            out = self.analyzer._call(prompt, max_tokens=700, timeout=90)
        except Exception as e:
            log.error(f"ChatAgent 호출 실패: {type(e).__name__}: {e}")
            out = None
        if out and out.strip():
            if self.enable_actions:
                cleaned, acts = parse_actions(out.strip())
                if cleaned:
                    return cleaned, acts
                # 🐛 FIX(v12): 응답이 액션 마커만 있는 경우 기존엔 out.strip()을 그대로 반환해
                #   사용자에게 "[[ACTION: goto_session(2)]]" 원문이 노출됐다.
                #   액션이 검증됐다면 실행 알림만 남기고(실행기가 notes를 붙인다),
                #   검증 실패면 마커를 지운 흔적 대신 폴백 안내를 보여준다.
                return (_ACTED[self.lang] if acts else _FALLBACK[self.lang]), acts
            return out.strip(), []
        # 실패 사유(있으면) 최근 2건만 덧붙여 진단을 돕는다
        errs = getattr(self.analyzer, "_errors", []) or []
        msg = _FALLBACK[self.lang]
        if errs:
            msg += "\n\n" + " / ".join(str(e) for e in errs[-2:])
        return msg, []

    def _build_prompt(self, history: list[dict], user_msg: str, context_text: str) -> str:
        u, a = _ROLE[self.lang]
        turns = (history or [])[-MAX_TURNS:]
        transcript = "\n".join(
            f"{u if h.get('role') == 'user' else a}: {str(h.get('content', ''))[:_HIST_TRUNC]}"
            for h in turns
        )
        ctx = (context_text or "").strip() or _NO_CTX[self.lang]
        _hh = _HIST_HEADER.get(self.lang, _HIST_HEADER["ko"])
        head = f"{_hh}\n{transcript}\n" if transcript else ""
        sys_prompt = self.system or _SYSTEM[self.lang]      # 편집 오버라이드 우선
        if self.enable_actions:                             # 동작 안내는 항상 자동 부착(편집과 무관)
            sys_prompt += actions_prompt(self.lang)
        _reground = _REGROUND.get(self.lang, _REGROUND["ko"]) if transcript else ""
        return (f"{sys_prompt}\n\n"
                f"[현재 대시보드 상태]\n{ctx}\n\n"
                f"{head}{_reground}\n{u}: {user_msg}\n{a}:")
