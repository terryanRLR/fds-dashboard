"""
SpeechToText — 챗봇 음성 입력용 STT (로컬 / 클라우드 선택)  ✨ v12 신규

설계 원칙 — **PII 락 승계**
  이 프로젝트는 미마스킹 데이터의 외부 전송을 `LLMAnalyzer.cloud_fallback=False`로
  차단한다(로컬 프로바이더 + 마스킹 스킵 조합). 그런데 **음성은 마스킹이 불가능한
  원본 개인정보**다 — 고객 이름·계좌번호·주소를 그대로 말할 수 있다.
  따라서 음성을 클라우드 STT로 보내는 것은 그 락을 우회하는 **새로운 유출 경로**다.

  → 규칙: LLM이 로컬 모드(외부 전송 차단)이면 STT도 **로컬만 허용**한다.
    `allow_cloud=False`로 생성하면 cloud 백엔드 요청을 거부하고 사유를 반환한다.

백엔드
  local  : faster-whisper (오프라인, 최초 모델 다운로드 ~40MB(tiny)~1.5GB(large))
           설치: pip install faster-whisper
  cloud  : OpenAI 호환 /v1/audio/transcriptions (whisper-1 / gpt-4o-transcribe 등)
           OPENAI_API_KEY 또는 대시보드 오버라이드 키 사용
  auto   : local 사용 가능하면 local, 아니면 (허용 시) cloud

핵심 API
  stt = SpeechToText(backend="auto", allow_cloud=False, lang="ko")
  ok, text, note = stt.transcribe(audio_bytes, filename="audio.wav")
  SpeechToText.availability()   → {"local": bool, "cloud": bool, "detail": {...}}
"""

from __future__ import annotations

import io
import os
import logging

log = logging.getLogger(__name__)

STT_VERSION = "v12"

# faster-whisper 모델 크기 — 정확도 vs 다운로드/속도
LOCAL_MODELS = ("tiny", "base", "small", "medium", "large-v3")
DEFAULT_LOCAL_MODEL = "base"

# 클라우드 모델 (OpenAI 호환)
CLOUD_MODELS = ("whisper-1", "gpt-4o-mini-transcribe", "gpt-4o-transcribe")
DEFAULT_CLOUD_MODEL = "whisper-1"

MAX_AUDIO_BYTES = 25 * 1024 * 1024      # OpenAI 업로드 상한과 동일

# ✨ v14: 업로드 허용 확장자 (마이크를 못 쓰는 환경의 대체 입력 경로)
AUDIO_EXTS = ("wav", "mp3", "m4a", "mp4", "ogg", "oga", "webm", "flac", "aac")
_MIME = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4", "mp4": "audio/mp4",
         "ogg": "audio/ogg", "oga": "audio/ogg", "webm": "audio/webm",
         "flac": "audio/flac", "aac": "audio/aac"}


def _mime_of(filename: str) -> str:
    ext = str(filename).rsplit(".", 1)[-1].lower() if "." in str(filename) else "wav"
    return _MIME.get(ext, "application/octet-stream")
_LANG_HINT = {"ko": "ko", "en": "en", "ja": "ja", "zh": "zh"}

_MSG = {
    "cloud_blocked": {
        "ko": ("🔒 로컬 LLM + 마스킹 스킵 모드에서는 음성을 외부로 보내지 않습니다. "
               "음성은 마스킹이 불가능한 원본 개인정보라, 클라우드 STT는 데이터 보호 정책을 "
               "우회하게 됩니다. 로컬 STT(faster-whisper)를 설치하거나 LLM 제공자를 외부로 바꿔주세요."),
        "en": ("🔒 Audio is never sent outside in local-LLM + skip-masking mode. Speech is "
               "unmaskable raw PII, so cloud STT would bypass the data-protection policy. "
               "Install local STT (faster-whisper) or switch the LLM provider to a cloud one."),
        "ja": ("🔒 ローカルLLM + マスキングスキップ時は音声を外部送信しません。音声はマスキング不能な"
               "生の個人情報のため、クラウドSTTは保護方針を回避します。ローカルSTT(faster-whisper)を"
               "導入するか、LLMプロバイダを外部に変更してください。"),
        "zh": ("🔒 在本地 LLM + 跳过脱敏模式下不会将音频外发。语音是无法脱敏的原始个人信息，"
               "云端 STT 会绕过数据保护策略。请安装本地 STT(faster-whisper) 或将 LLM 提供方改为云端。"),
    },
    "no_backend": {
        "ko": "사용 가능한 STT 백엔드가 없습니다. `pip install faster-whisper`(로컬) 또는 OpenAI 키(클라우드)를 설정하세요.",
        "en": "No STT backend available. Install `faster-whisper` (local) or set an OpenAI key (cloud).",
        "ja": "利用可能なSTTバックエンドがありません。`faster-whisper`(ローカル)か OpenAIキー(クラウド)を設定してください。",
        "zh": "没有可用的 STT 后端。请安装 `faster-whisper`(本地) 或设置 OpenAI 密钥(云端)。",
    },
    "empty": {
        "ko": "음성에서 문자를 인식하지 못했어요. 조금 더 길고 또렷하게 말해 주세요.",
        "en": "Couldn't recognize any speech. Please speak a bit longer and more clearly.",
        "ja": "音声を認識できませんでした。もう少し長く、はっきり話してください。",
        "zh": "未能识别到语音。请说得长一些、清楚一些。",
    },
    "too_big": {
        "ko": "녹음이 너무 깁니다(최대 25MB). 짧게 나눠 말해 주세요.",
        "en": "Recording too large (max 25MB). Please split it into shorter parts.",
        "ja": "録音が大きすぎます(最大25MB)。短く分けてください。",
        "zh": "录音过大(最多 25MB)。请分成较短的片段。",
    },
}


def _m(key: str, lang: str) -> str:
    d = _MSG.get(key, {})
    return d.get(lang, d.get("ko", key))


# ══════════════════════════════════════════════════════════
# 가용성 탐지
# ══════════════════════════════════════════════════════════

def _local_available() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401
        return True, "faster-whisper"
    except ImportError:
        return False, "faster-whisper 미설치"
    except Exception as e:                                  # pragma: no cover
        return False, f"{type(e).__name__}: {e}"


def _cloud_key(explicit: str | None = None) -> str | None:
    return (explicit or "").strip() or os.getenv("OPENAI_API_KEY") or None


def _cloud_available(explicit_key=None) -> tuple[bool, str]:
    if not _cloud_key(explicit_key):
        return False, "OPENAI_API_KEY 미설정"
    try:
        import requests  # noqa: F401  (가용성 탐지용 import)
        return True, "OpenAI 호환 /v1/audio/transcriptions"
    except ImportError:
        return False, "requests 미설치"


class SpeechToText:
    """음성 → 텍스트. 대시보드 STT 설정을 그대로 받아 동작한다.

    Parameters
    ----------
    backend : 'auto' | 'local' | 'cloud'
    allow_cloud : bool
        False면 클라우드 백엔드를 절대 쓰지 않는다 (LLM 로컬 모드의 PII 락 승계).
    local_model : faster-whisper 모델 크기
    cloud_model : OpenAI 호환 모델명
    api_key : 대시보드 오버라이드 키 (없으면 .env)
    base_url : OpenAI 호환 게이트웨이 (사내 프록시 등)
    lang : UI/음성 언어 힌트
    """

    def __init__(self, backend: str = "auto", allow_cloud: bool = True,
                 local_model: str = DEFAULT_LOCAL_MODEL, cloud_model: str = DEFAULT_CLOUD_MODEL,
                 api_key: str | None = None, base_url: str | None = None,
                 lang: str = "ko"):
        self.backend = backend if backend in ("auto", "local", "cloud") else "auto"
        self.allow_cloud = bool(allow_cloud)
        self.local_model = local_model if local_model in LOCAL_MODELS else DEFAULT_LOCAL_MODEL
        self.cloud_model = cloud_model or DEFAULT_CLOUD_MODEL
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.lang = lang if lang in _LANG_HINT else "ko"
        self.last_backend = ""

    # ── 가용성 ──────────────────────────────────────────
    @staticmethod
    def availability(api_key=None) -> dict:
        lo, lod = _local_available()
        co, cod = _cloud_available(api_key)
        return {"local": lo, "cloud": co, "detail": {"local": lod, "cloud": cod}}

    def resolve_backend(self) -> tuple[str | None, str]:
        """실제로 쓸 백엔드 결정 → (백엔드명|None, 사유)"""
        lo, lod = _local_available()
        co, cod = _cloud_available(self.api_key)
        if self.backend == "local":
            return ("local", lod) if lo else (None, lod)
        if self.backend == "cloud":
            if not self.allow_cloud:
                return None, _m("cloud_blocked", self.lang)
            return ("cloud", cod) if co else (None, cod)
        # auto — 로컬 우선(개인정보 안전), 없으면 허용 시 클라우드
        if lo:
            return "local", lod
        if co and self.allow_cloud:
            return "cloud", cod
        if co and not self.allow_cloud:
            return None, _m("cloud_blocked", self.lang)
        return None, _m("no_backend", self.lang)

    # ── 변환 ────────────────────────────────────────────
    def transcribe(self, audio: bytes, filename: str = "audio.wav") -> tuple[bool, str, str]:
        """오디오 바이트 → (성공여부, 텍스트, 안내문)"""
        if not audio:
            return False, "", _m("empty", self.lang)
        if len(audio) > MAX_AUDIO_BYTES:
            return False, "", _m("too_big", self.lang)

        be, why = self.resolve_backend()
        if be is None:
            return False, "", why
        self.last_backend = be
        try:
            text = (self._local(audio, filename) if be == "local"
                    else self._cloud(audio, filename))
        except Exception as e:
            log.error(f"STT 실패({be}): {type(e).__name__}: {e}")
            return False, "", f"{be} STT 실패 — {type(e).__name__}: {str(e)[:140]}"
        text = (text or "").strip()
        if not text:
            return False, "", _m("empty", self.lang)
        return True, text, f"🎤 {be} · {self.local_model if be=='local' else self.cloud_model}"

    # ── 백엔드 구현 ─────────────────────────────────────
    def _local(self, audio: bytes, filename: str = "audio.wav") -> str:
        model = _load_local_model(self.local_model)
        try:
            segments, _info = model.transcribe(
                io.BytesIO(audio), language=_LANG_HINT.get(self.lang, None),
                vad_filter=True, beam_size=1,
            )
            return " ".join(seg.text.strip() for seg in segments)
        except Exception:
            # ✨ v14: 일부 컨테이너(m4a/webm)는 BytesIO 경로에서 실패 → 임시파일로 재시도
            import tempfile, os as _os
            ext = str(filename).rsplit(".", 1)[-1].lower() if "." in str(filename) else "wav"
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tf:
                tf.write(audio); tmp = tf.name
            try:
                segments, _info = model.transcribe(
                    tmp, language=_LANG_HINT.get(self.lang, None), vad_filter=True, beam_size=1)
                return " ".join(seg.text.strip() for seg in segments)
            finally:
                try: _os.unlink(tmp)
                except OSError: pass

    def _cloud(self, audio: bytes, filename: str) -> str:
        import requests
        key = _cloud_key(self.api_key)
        if not key:
            raise RuntimeError("OPENAI_API_KEY 미설정")
        r = requests.post(
            f"{self.base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            # 🐛 FIX(v14): MIME을 'audio/wav'로 고정하면 업로드한 mp3/m4a가 서버에서 거부된다
            files={"file": (filename or "audio.wav", audio, _mime_of(filename))},
            data={"model": self.cloud_model, "language": _LANG_HINT.get(self.lang, "ko")},
            timeout=90,
        )
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:180]}")
        j = r.json()
        return j.get("text") or ""


# 로컬 모델은 로드가 무거우므로 프로세스 단위로 1회만 만든다
_LOCAL_CACHE: dict = {}


def _load_local_model(size: str):
    if size not in _LOCAL_CACHE:
        from faster_whisper import WhisperModel
        log.info(f"faster-whisper 모델 로드: {size} (최초 실행 시 다운로드)")
        _LOCAL_CACHE[size] = WhisperModel(size, device="auto", compute_type="int8")
    return _LOCAL_CACHE[size]
