"""
RAGSearcher — Chroma 벡터 DB에서 사기 시나리오·대응 매뉴얼을 검색
최초 실행 시 docs/ 폴더의 마크다운 파일을 임베딩해 DB를 구축한다.
"""

import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# 🐛 FIX(v5): CWD 기준 상대경로 → 실행 위치에 따라 docs/DB를 못 찾던 문제.
#   ml_classifier와 동일하게 프로젝트 루트(모듈 상위) 기준으로 앵커링, 환경변수로 오버라이드 가능.
import os as _os
_PROJ = Path(__file__).resolve().parent.parent
DOCS_DIR   = Path(_os.environ.get("FDS_DOCS_DIR",   _PROJ / "docs"))       # 사기 시나리오 md 파일 위치
CHROMA_DIR = Path(_os.environ.get("FDS_CHROMA_DIR", _PROJ / "chroma_db"))  # 벡터 DB 저장 위치


def _docs_mtime_check(docs_path=DOCS_DIR):
    """✨ v6.1 / 🐛 FIX(v10): docs/ 파일 변경 감지 — mtime 해시로 재임베딩 트리거.
    기존 기본값 'docs/'는 CWD 상대라 DOCS_DIR(프로젝트 루트 기준)과 어긋났고,
    애초에 어디서도 호출되지 않는 데드코드였음 → DOCS_DIR로 통일하고 _init_chroma에서 실사용."""
    import hashlib
    dp = Path(docs_path)
    if not dp.is_dir():
        return ""
    return hashlib.md5("".join(
        f"{p.name}:{p.stat().st_mtime}" for p in sorted(dp.glob("*.md"))
    ).encode()).hexdigest()


class RAGSearcher:
    # 🐛 FIX(v10): docs/ 변경 서명 저장 위치 (Chroma DB 옆 사이드카)
    _SIG_PATH = CHROMA_DIR / ".docs_sig"

    def __init__(self, top_k: int = 3):
        self.top_k      = top_k
        self.collection = None
        self._client    = None
        self._embed_fn  = None
        self._init_chroma()

    @classmethod
    def _read_sig(cls) -> str:
        try:
            return cls._SIG_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    @classmethod
    def _write_sig(cls, sig: str):
        try:
            cls._SIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            cls._SIG_PATH.write_text(sig or "", encoding="utf-8")
        except Exception as e:
            log.debug(f"docs 서명 저장 실패(무시): {e}")

    def _init_chroma(self):
        """Chroma DB 초기화 — 문서가 없거나 docs/가 변경됐으면 재임베딩"""
        try:
            import chromadb
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )

            embed_fn = SentenceTransformerEmbeddingFunction(
                model_name="snunlp/KR-SBERT-V40K-klueNLI-augSTS"  # 한국어 특화 모델
            )
            self._client   = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._embed_fn = embed_fn
            self.collection = self._client.get_or_create_collection(
                name="fds_docs",
                embedding_function=embed_fn,
            )

            # 🐛 FIX(v10): docs/ 변경 감지 → 재임베딩 (기존엔 _docs_mtime_check가
            #   호출되지 않아, docs/*.md를 수정해도 반영되지 않았음).
            cur_sig = _docs_mtime_check(DOCS_DIR)
            if self.collection.count() == 0:
                self._build_index()
                self._write_sig(cur_sig)
            elif cur_sig and cur_sig != self._read_sig():
                log.info("docs/ 변경 감지 → 인덱스 재구축")
                self._client.delete_collection("fds_docs")
                self.collection = self._client.get_or_create_collection(
                    name="fds_docs", embedding_function=embed_fn,
                )
                self._build_index()
                self._write_sig(cur_sig)

            log.info(f"Chroma DB 준비 완료 (문서 수: {self.collection.count()})")

        except ImportError:
            log.warning("chromadb / sentence-transformers 미설치 — RAG 더미 모드")
            self.collection = None
        except Exception as e:
            # 🐛 FIX: DB 손상·임베딩 모델 다운로드 실패·네트워크 오류 등
            #        어떤 초기화 실패도 대시보드를 죽이지 않고 더미 모드로 전환
            log.error(f"Chroma 초기화 실패 → RAG 더미 모드: {type(e).__name__}: {e}")
            self.collection = None

    def _build_index(self):
        """docs/ 폴더의 .md 파일을 읽어 벡터 DB에 적재"""
        if not DOCS_DIR.exists():
            log.warning(f"docs/ 폴더 없음 — 샘플 문서를 자동 생성합니다")
            self._create_sample_docs()

        docs, ids, metas = [], [], []
        for md_file in sorted(DOCS_DIR.glob("*.md")):
            text = md_file.read_text(encoding="utf-8")
            # 청크 분할 (단순 문단 기준, 필요시 LangChain TextSplitter 대체)
            chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 50]
            for i, chunk in enumerate(chunks):
                docs.append(chunk)
                ids.append(f"{md_file.stem}_chunk{i}")
                metas.append({"source": md_file.name})

        if docs:
            self.collection.add(documents=docs, ids=ids, metadatas=metas)
            log.info(f"임베딩 완료: {len(docs)}개 청크")

    def search(self, query: str, fraud_type: str = "") -> list[str]:
        """쿼리와 유사한 문서 청크 반환"""
        if self.collection is None:
            return self._dummy_search(fraud_type)

        try:
            # 🐛 FIX: n_results > 문서 수면 일부 chroma 버전에서 오류 → min 처리
            n = max(1, min(self.top_k, self.collection.count() or 1))
            results = self.collection.query(
                query_texts=[query],
                n_results=n,
            )
            docs = results.get("documents", [[]])[0]
            return docs if docs else self._dummy_search(fraud_type)
        except Exception as e:
            log.error(f"RAG 검색 실패 → 더미 폴백: {e}")
            return self._dummy_search(fraud_type)

    # ── 샘플 문서 자동 생성 ────────────────────────────
    def _create_sample_docs(self):
        DOCS_DIR.mkdir(exist_ok=True)
        samples = {
            "fraud_types.md": """# 사기 유형 설명

## 유형 a — 원격제어 사기
피해자 단말기를 원격으로 제어해 이체를 유도하는 수법.
징후: 원격제어 앱 설치, 미사용 단말 접속, 새벽 고액 이체.
권장 조치: 추가 인증 요청, 거래 보류, 고객 직접 확인.

## 유형 b — 피싱 사기
가짜 금융기관 사이트 유도 후 정보 탈취.
징후: 비정상 URL 접속, 연속 인증 시도, 소액 선테스트 후 고액 이체.
권장 조치: 계좌 일시 정지, 보안팀 에스컬레이션.

## 유형 c — 명의도용
타인 명의로 계좌 개설 후 자금 이동.
징후: 신규 계좌 즉시 고액 이체, 등록 정보 불일치.
권장 조치: 본인 확인 절차 강화, 거래 중지.

## 유형 d — 대출 빙자 사기
저금리 대출 명목으로 수수료 선납 유도.
징후: 수취 계좌 거래 중지 이력, 반복 소액 이체.
권장 조치: 수취 계좌 모니터링, 고객 안내.
""",
            "response_manual.md": """# 이상거래 대응 매뉴얼

## 위험 점수 0.9 이상
즉시 거래 차단 + 보안팀 에스컬레이션 + 고객 확인 전화.

## 위험 점수 0.7~0.9
거래 보류 + 추가 인증 요청 (OTP/생체).

## 위험 점수 0.5~0.7
모니터링 강화 + 알림 발송 + 수동 검토 대기열 등록.

## 공통 조치
- 거래 ID와 예측 유형을 사고 이력 DB에 기록
- 고객에게 이상거래 안내 SMS 발송
- 3회 이상 반복 시 계좌 일시 정지
""",
        }
        for fname, content in samples.items():
            (DOCS_DIR / fname).write_text(content, encoding="utf-8")
        log.info("샘플 문서 생성 완료")

    def _dummy_search(self, fraud_type: str) -> list[str]:
        base = [
            f"유형 {fraud_type} 관련 사기 시나리오: 비정상 접속 패턴 및 고액 이체 의심.",
            "권장 조치: 추가 인증 요청 또는 거래 보류 후 수동 검토.",
            "위험 점수가 높은 경우 즉시 보안팀에 에스컬레이션 필요.",
        ]
        return base[:self.top_k] if self.top_k else base   # 🐛 FIX(v10): top_k 존중
