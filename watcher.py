"""
watcher — inbox 폴더 감시 데몬 (Windows 우선)  ✨ v15 신규

흐름
  inbox/*.csv 폴링 → 신규/추가분만 읽기 → DetectService.detect() → 알림
  판정 로직은 전부 pipeline/detect_service.py 에 있다. 이 파일은 **파일 I/O만** 담당한다.
  (대시보드와 판정이 갈라지지 않게 하려는 의도적 분리)

왜 watchdog이 아니라 폴링인가
  사내 PC/서버의 감시 폴더는 네트워크 공유(SMB)인 경우가 많은데,
  Windows의 ReadDirectoryChangesW는 네트워크 드라이브에서 이벤트를 신뢰할 수 없다.
  조용히 파일을 놓치면서 로그에도 아무것도 남지 않는 게 최악의 실패 모드다.
  하루 수백 건 규모에서는 5초 폴링이 훨씬 단순하고 확실하다.
  보너스: "크기가 직전 폴링과 같을 때만 처리" 규칙이
  **쓰는 중인 반쪽 파일 읽기 문제를 공짜로 해결**한다.

신규 파일 / 행 추가(append) 둘 다 지원
  watch_cursor 테이블에 (경로, 크기, mtime, 처리행수, 헤더해시)를 남긴다.
    · 미등록 경로            → 신규 파일, 전량 처리
    · 크기 증가 + 헤더 동일  → append, 새 행만 처리 (skiprows)
    · 크기 감소 / 헤더 변경  → 로테이션·교체, 커서 리셋 후 전량 재처리

사용
  python watcher.py --inbox inbox --interval 5
  python watcher.py --once                  # 1회만 돌고 종료 (동작 확인용)
  python watcher.py --dry-run               # 판정만, 알림 발송 안 함
  python watcher.py --seed-cursor           # 🚑 기존 파일을 '처리완료'로 표시만 (알림 폭격 방지)
"""

from __future__ import annotations

import os
import sys
import time
import signal
import atexit
import hashlib
import logging
import argparse
import sqlite3
from pathlib import Path

# Windows 콘솔 한글 깨짐 방지 (llm_analyzer와 동일 정책)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_PROJ = Path(__file__).resolve().parent
if str(_PROJ) not in sys.path:
    sys.path.insert(0, str(_PROJ))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pandas as pd

from pipeline.detect_service import DetectService, DetectConfig, ModelNotReadyError
from pipeline import watcher_config as wcfg

log = logging.getLogger("watcher")

WATCHER_VERSION = "v17"
LOCK_PATH = _PROJ / ".watcher.lock"
# 대시보드 등 외부에서 '정상 종료'를 요청하는 신호 파일.
#   프로세스 kill 과 달리 현재 처리 중인 행을 마치고 커서를 저장한 뒤 멈춘다.
#   파일 하나면 되므로 권한·세션 문제가 없고, 서비스로 등록돼 있어도 동작한다.
STOP_FLAG_PATH = _PROJ / ".watcher.stop"

# CSV 인코딩 시도 순서 (한국어 환경에서 cp949 파일이 섞여 들어오는 경우 대비)
_ENCODINGS = ("utf-8-sig", "cp949", "utf-8")


# ══════════════════════════════════════════════════════════
# 중복 실행 방지 — 아이콘 두 번 누르면 알림도 두 배로 간다
# ══════════════════════════════════════════════════════════

_lock_fh = None


def acquire_single_instance_lock() -> bool:
    global _lock_fh
    try:
        _lock_fh = open(LOCK_PATH, "w")
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        atexit.register(_release_lock)
        return True
    except Exception:
        return False


def _release_lock():
    global _lock_fh
    try:
        if _lock_fh:
            _lock_fh.close()
            _lock_fh = None
        LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
# 커서 저장소
# ══════════════════════════════════════════════════════════

class CursorStore:
    """파일별 처리 위치. DetectService와 같은 sqlite 파일을 공유한다."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    def _conn(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA busy_timeout=30000")
        except Exception:
            pass
        return con

    def _init(self):
        con = self._conn()
        con.execute("""
            CREATE TABLE IF NOT EXISTS watch_cursor (
                path        TEXT PRIMARY KEY,
                size        INTEGER,
                mtime       REAL,
                rows_done   INTEGER DEFAULT 0,
                header_hash TEXT,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        con.execute("""
            CREATE TABLE IF NOT EXISTS watcher_status (
                id         INTEGER PRIMARY KEY CHECK (id = 1),
                started_at TIMESTAMP,
                last_poll  TIMESTAMP,
                polls      INTEGER DEFAULT 0,
                rows_done  INTEGER DEFAULT 0,
                anomalies  INTEGER DEFAULT 0,
                notified   INTEGER DEFAULT 0,
                errors     INTEGER DEFAULT 0,
                note       TEXT
            )""")
        con.commit()
        con.close()

    def get(self, path: Path) -> dict | None:
        con = self._conn()
        cur = con.execute(
            "SELECT size, mtime, rows_done, header_hash FROM watch_cursor WHERE path=?",
            (str(path.resolve()),))
        r = cur.fetchone()
        con.close()
        if not r:
            return None
        return {"size": r[0], "mtime": r[1], "rows_done": r[2], "header_hash": r[3]}

    def put(self, path: Path, size: int, mtime: float, rows_done: int, header_hash: str):
        con = self._conn()
        con.execute(
            """INSERT INTO watch_cursor (path, size, mtime, rows_done, header_hash, updated_at)
               VALUES (?,?,?,?,?,datetime('now'))
               ON CONFLICT(path) DO UPDATE SET
                 size=excluded.size, mtime=excluded.mtime, rows_done=excluded.rows_done,
                 header_hash=excluded.header_hash, updated_at=excluded.updated_at""",
            (str(path.resolve()), int(size), float(mtime), int(rows_done), header_hash))
        con.commit()
        con.close()

    def heartbeat(self, **kw):
        con = self._conn()
        con.execute("INSERT OR IGNORE INTO watcher_status (id, started_at) VALUES (1, datetime('now'))")
        con.execute(
            """UPDATE watcher_status SET last_poll=datetime('now'),
               polls=?, rows_done=?, anomalies=?, notified=?, errors=?, note=? WHERE id=1""",
            (kw.get("polls", 0), kw.get("rows_done", 0), kw.get("anomalies", 0),
             kw.get("notified", 0), kw.get("errors", 0), kw.get("note", "")))
        con.commit()
        con.close()

    def mark_started(self, note: str):
        con = self._conn()
        con.execute("INSERT OR IGNORE INTO watcher_status (id, started_at) VALUES (1, datetime('now'))")
        con.execute("UPDATE watcher_status SET started_at=datetime('now'), polls=0, "
                    "rows_done=0, anomalies=0, notified=0, errors=0, note=? WHERE id=1", (note,))
        con.commit()
        con.close()


# ══════════════════════════════════════════════════════════
# CSV 읽기 보조
# ══════════════════════════════════════════════════════════

def _header_hash(path: Path) -> str:
    """첫 줄(헤더) 해시 — 바뀌면 '다른 파일'로 취급한다."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.readline().strip()).hexdigest()
    except Exception:
        return ""


def _read_csv(path: Path, skip_rows: int = 0) -> pd.DataFrame | None:
    """skip_rows: 헤더를 제외하고 건너뛸 데이터 행 수."""
    kw = {}
    if skip_rows > 0:
        kw["skiprows"] = range(1, skip_rows + 1)     # 헤더(0행)는 남기고 데이터만 건너뜀
    last = None
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, **kw)
        except UnicodeDecodeError as e:
            last = e
            continue
        except pd.errors.EmptyDataError:
            return None
        except Exception as e:
            last = e
            break
    log.error(f"CSV 읽기 실패: {path.name} — {type(last).__name__}: {last}")
    return None


def _rows_of(df: pd.DataFrame, src_name: str) -> list[dict]:
    rows = df.to_dict("records")
    for i, r in enumerate(rows):
        r["_input_mode"] = "watcher"
        r["_source_file"] = src_name
        if not r.get("transaction_id"):
            r["transaction_id"] = str(r.get("ID") or f"{Path(src_name).stem}_{i}")
    return rows


# ══════════════════════════════════════════════════════════
# 워처 본체
# ══════════════════════════════════════════════════════════

class Watcher:
    def __init__(self, svc: DetectService, inbox: Path, interval: float = 5.0,
                 pattern: str = "*.csv", max_rows_per_poll: int = 2000,
                 stable_after: float = 3.0, config_path: str | None = None):
        self.svc = svc
        self.inbox = Path(inbox)
        self.interval = float(interval)
        self.pattern = pattern
        self.max_rows_per_poll = int(max_rows_per_poll)
        self.stable_after = float(stable_after)
        self.config_path = config_path or wcfg.DEFAULT_PATH
        self._cfg_mtime = -1.0
        self.cursors = CursorStore(svc.cfg.db_path)
        self._seen_size: dict[str, int] = {}     # 안정화 판정용 (직전 폴링의 크기)
        self._running = True
        self.polls = 0
        self.rows_done = 0

    def stop(self, *_):
        log.info("종료 신호 수신 — 현재 파일 처리 후 정리합니다…")
        self._running = False

    # ── 커서 시딩: 기존 파일을 '처리 완료'로만 표시 ──
    def seed_cursor(self) -> int:
        """🚑 기존 파일 전량을 알림 없이 처리완료로 등록.
        train.csv 같은 대용량 파일이 있는 폴더에 워처를 붙일 때
        첫 폴링에서 수만 건 알림이 나가는 사고를 막는다."""
        n = 0
        for p in sorted(self.inbox.glob(self.pattern)):
            try:
                st = p.stat()
                df = _read_csv(p)
                rows = 0 if df is None else len(df)
                self.cursors.put(p, st.st_size, st.st_mtime, rows, _header_hash(p))
                log.info(f"  시딩: {p.name} — {rows:,}행 처리완료로 표시")
                n += 1
            except Exception as e:
                log.error(f"  시딩 실패: {p.name} — {e}")
        return n

    # ── 설정 핫 리로드 ──
    def reload_config(self, force: bool = False):
        """watcher_config.json이 바뀌었으면 다시 읽어 반영한다 (재시작 불필요)."""
        try:
            fp = wcfg.path_of(self.config_path)
            mt = fp.stat().st_mtime if fp.exists() else 0.0
        except OSError:
            return
        if not force and mt == self._cfg_mtime:
            return
        self._cfg_mtime = mt
        if mt == 0.0:
            return
        changed = wcfg.apply_to(self.svc.cfg, wcfg.load(fp))
        if changed:
            # 마스킹 레벨이 바뀌면 마스커를 다시 만들어야 실제로 적용된다
            if any(c.startswith("pii_level") for c in changed):
                self.svc._masker = None
            log.warning(f"⚙️ 설정 변경 반영 — {' · '.join(changed)}")

    # ── 폴링 1회 ──
    def poll_once(self) -> int:
        processed = 0
        self.reload_config()
        if not self.inbox.is_dir():
            log.warning(f"감시 폴더 없음: {self.inbox}")
            return 0

        for p in sorted(self.inbox.glob(self.pattern)):
            if not self._running:
                break
            try:
                st = p.stat()
            except OSError:
                continue                       # 폴링 중 삭제/이동됨
            key = str(p.resolve())

            # ① 안정화 확인 — 쓰는 중인 반쪽 파일 회피
            #   🐛 FIX: 기존엔 '직전 폴링과 크기 동일'만 봤는데, _seen_size는 메모리
            #   dict라 첫 폴링에서는 항상 비어 있다. 그래서 --once는 무조건 0행이 되고,
            #   워처를 재시작할 때마다 대기 중이던 파일을 한 폴링씩 통째로 흘렸다.
            #   → 수정된 지 stable_after초가 지난 파일은 '이미 다 쓰인 것'으로 판정한다.
            #     (크기 비교는 지금 막 쓰이는 중인 파일에만 필요하다)
            mtime_age = time.time() - st.st_mtime
            stable = (mtime_age >= self.stable_after) or (self._seen_size.get(key) == st.st_size)
            self._seen_size[key] = st.st_size
            if not stable:
                log.debug(f"  {p.name}: 쓰기 진행 중으로 보임"
                          f"(수정 {mtime_age:.1f}초 전) — 다음 폴링에서 처리")
                continue

            prev = self.cursors.get(p)
            hh = _header_hash(p)

            if prev is None:
                mode, skip = "신규", 0
            elif hh and prev["header_hash"] and hh != prev["header_hash"]:
                mode, skip = "헤더변경→재처리", 0
            elif st.st_size < (prev["size"] or 0):
                mode, skip = "축소/로테이션→재처리", 0
            elif st.st_size > (prev["size"] or 0):
                mode, skip = "추가분", int(prev["rows_done"] or 0)
            else:
                continue                       # 변화 없음

            df = _read_csv(p, skip_rows=skip)
            if df is None or df.empty:
                self.cursors.put(p, st.st_size, st.st_mtime,
                                 int(prev["rows_done"]) if prev else 0, hh)
                continue

            truncated = False
            if len(df) > self.max_rows_per_poll:
                df = df.head(self.max_rows_per_poll)
                truncated = True               # 나머지는 다음 폴링에서 (루프 블로킹 방지)

            rows = _rows_of(df, p.name)
            log.info(f"📥 {p.name} [{mode}] {len(rows):,}행 처리 시작"
                     + (" (분할 처리 중)" if truncated else ""))

            n_anom = 0
            for r in rows:
                if not self._running:
                    break
                det = self.svc.detect(r, source=f"watcher:{p.name}")
                self.rows_done += 1
                processed += 1
                if det["is_anomaly"]:
                    n_anom += 1

            done = skip + len(rows)
            # 중간에 멈췄으면 커서를 진행분까지만 저장해야 재시작 시 누락이 없다
            self.cursors.put(p, st.st_size if not truncated else (prev["size"] if prev else 0),
                             st.st_mtime, done, hh)
            log.info(f"   완료 — {len(rows):,}행 · 이상거래 {n_anom}건")

        return processed

    def _check_stop_flag(self) -> bool:
        """.watcher.stop 이 있으면 지우고 정상 종료 절차로 들어간다."""
        try:
            if STOP_FLAG_PATH.exists():
                try:
                    STOP_FLAG_PATH.unlink()
                except OSError:
                    pass
                log.warning("🛑 중지 요청 감지(.watcher.stop) — 현재 작업을 마치고 종료합니다")
                self._running = False
                return True
        except OSError:
            pass
        return False

    # ── 메인 루프 ──
    def run(self):
        log.info(f"👁  감시 시작 — {self.inbox.resolve()} · {self.interval}초 간격 · 패턴 {self.pattern}")
        # 이전 세션에서 남은 중지 신호가 있으면 무시하고 지운다
        try:
            STOP_FLAG_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        while self._running:
            t0 = time.time()
            if self._check_stop_flag():
                break
            try:
                self.poll_once()
                self.polls += 1
            except Exception as e:
                log.exception(f"폴링 중 예외(계속 진행): {type(e).__name__}: {e}")
                self.svc.stats["errors"] += 1
            try:
                s = self.svc.stats
                self.cursors.heartbeat(polls=self.polls, rows_done=self.rows_done,
                                       anomalies=s["anomaly"], notified=s["notified"],
                                       errors=s["errors"], note="running")
            except Exception:
                pass
            sleep = max(0.5, self.interval - (time.time() - t0))
            end = time.time() + sleep
            while self._running and time.time() < end:
                time.sleep(0.25)               # Ctrl+C 반응성 확보
                if self._check_stop_flag():    # 대기 중에도 중지 요청에 반응
                    break
        log.info(f"🛑 감시 종료 — 총 {self.rows_done:,}행 처리 · "
                 f"이상 {self.svc.stats['anomaly']}건 · 발송 {self.svc.stats['notified']}건")
        try:
            self.cursors.heartbeat(polls=self.polls, rows_done=self.rows_done,
                                   anomalies=self.svc.stats["anomaly"],
                                   notified=self.svc.stats["notified"],
                                   errors=self.svc.stats["errors"], note="stopped")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="FDS 폴더 감시 워처")
    ap.add_argument("--inbox", default="inbox", help="감시할 폴더 (기본: inbox)")
    ap.add_argument("--pattern", default="*.csv")
    ap.add_argument("--interval", type=float, default=5.0, help="폴링 간격(초)")
    ap.add_argument("--models", default="models/", help="모델 디렉토리")
    ap.add_argument("--model", default=None, help="모델 파일 경로 (미지정 시 자동 탐색)")
    ap.add_argument("--db", default="fds_results.db")

    ap.add_argument("--review", type=float, default=None, help="1차 임계값 (Slack만)")
    ap.add_argument("--confirm", type=float, default=None, help="2차 임계값 (Slack+Email)")
    ap.add_argument("--single-threshold", type=float, default=None,
                    help="이중 임계값 대신 단일 임계값 사용")

    ap.add_argument("--pii", default=None, choices=["off", "basic", "standard", "strict"])
    ap.add_argument("--provider", default=None, help="LLM 제공자 (local/anthropic/openai/…)")
    ap.add_argument("--no-llm", action="store_true", help="LLM 분석 없이 폴백 양식으로만 발송")
    ap.add_argument("--no-rag", action="store_true")
    ap.add_argument("--cloud-fallback", action="store_true",
                    help="로컬 LLM 실패 시 외부 API 폴백 허용 (기본: 차단)")

    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--email-to", default=None)

    ap.add_argument("--once", action="store_true", help="1회 폴링 후 종료")
    ap.add_argument("--dry-run", action="store_true", help="발송하지 않고 판정만")
    ap.add_argument("--seed-cursor", action="store_true",
                    help="기존 파일을 알림 없이 '처리완료'로 표시하고 종료")
    ap.add_argument("--allow-dummy", action="store_true",
                    help="🚨 모델 로드 실패해도 랜덤 예측으로 계속 (개발 전용, 운영 금지)")
    ap.add_argument("--startup-ping", action="store_true", help="기동 시 Slack으로 시작 알림")
    ap.add_argument("--max-rows-per-poll", type=int, default=2000)
    ap.add_argument("--config", default=None,
                    help="튜닝 설정 파일 (기본: watcher_config.json). "
                         "폴링마다 다시 읽으므로 실행 중 수정하면 즉시 반영된다")
    ap.add_argument("--no-config-file", action="store_true",
                    help="설정 파일을 무시하고 CLI/.env 값만 사용")
    ap.add_argument("--stable-after", type=float, default=3.0,
                    help="파일 수정 후 이 시간(초)이 지나면 '쓰기 완료'로 판정 (기본 3초)")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def main():
    a = build_parser().parse_args()

    logging.basicConfig(
        level=logging.DEBUG if a.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(_PROJ / "watcher.log", encoding="utf-8")],
    )
    # 🐛 FIX: -v 를 주면 matplotlib·httpx·PIL 등의 DEBUG가 화면을 덮어
    #   정작 봐야 할 워처 로그가 파묻힌다. 서드파티는 WARNING 이상만 남긴다.
    for _noisy in ("chromadb", "matplotlib", "urllib3", "httpx", "httpcore", "PIL",
                   "sentence_transformers", "transformers", "huggingface_hub",
                   "filelock", "asyncio", "numexpr"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    if not acquire_single_instance_lock():
        log.error("❌ 워처가 이미 실행 중입니다 (.watcher.lock). "
                  "중복 실행하면 같은 거래로 알림이 두 번 갑니다.")
        sys.exit(3)

    cfg = DetectConfig.from_env(
        model_dir=a.models, model_path=a.model, db_path=a.db,
        pii_level=a.pii, llm_provider=a.provider,
        use_llm=not a.no_llm, use_rag=not a.no_rag,
        cloud_fallback=a.cloud_fallback or None,
        notify_slack=not a.no_slack, notify_email=not a.no_email,
        email_to=a.email_to, dry_run=a.dry_run or None,
        allow_dummy=a.allow_dummy or None,
        th_review=a.review, th_confirm=a.confirm,
    )
    if a.single_threshold is not None:
        cfg.dual_threshold = False
        cfg.threshold = a.single_threshold

    # ── 설정 파일 반영 (우선순위: CLI 명시 > 파일 > .env > 기본값) ──
    _cfg_path = a.config or wcfg.DEFAULT_PATH
    _explicit = {k for k, v in vars(a).items() if v is not None and v is not False}
    if not a.no_config_file:
        _file_vals = wcfg.load(_cfg_path)
        # CLI로 명시한 값은 파일이 덮어쓰지 않는다
        for _cli_key, _cfg_key in (("review", "th_review"), ("confirm", "th_confirm"),
                                   ("single_threshold", "threshold"), ("pii", "pii_level"),
                                   ("email_to", "email_to"), ("dry_run", "dry_run")):
            if _cli_key in _explicit:
                _file_vals.pop(_cfg_key, None)
        if a.no_llm:
            _file_vals.pop("use_llm", None)
        if a.no_rag:
            _file_vals.pop("use_rag", None)
        if a.no_slack:
            _file_vals.pop("notify_slack", None)
        if a.no_email:
            _file_vals.pop("notify_email", None)
        _applied = wcfg.apply_to(cfg, _file_vals)
        if _applied:
            log.info(f"설정 파일 적용({_cfg_path}) — {' · '.join(_applied)}")

    inbox = Path(a.inbox)
    inbox.mkdir(parents=True, exist_ok=True)

    # ── 기동 하드 가드 ──
    try:
        svc = DetectService(cfg)
    except ModelNotReadyError as e:
        log.error(str(e))
        _try_alert_startup_failure(cfg, str(e))
        sys.exit(2)
    except Exception as e:
        log.exception(f"기동 실패: {type(e).__name__}: {e}")
        _try_alert_startup_failure(cfg, f"{type(e).__name__}: {e}")
        sys.exit(2)

    # ── 자가진단 출력 ──
    hc = svc.healthcheck()
    print("=" * 70)
    print(f" FDS 워처 {WATCHER_VERSION} · 코어 {hc['service_version']}")
    print("=" * 70)
    print(f" 감시 폴더 : {inbox.resolve()}  ({a.pattern}, {a.interval}초)")
    print(f" 분류기    : {hc['classifier']}")
    print(f" 임계값    : {hc['threshold']}")
    print(f" 마스킹    : {hc['pii_level']}")
    print(f" LLM       : {hc['llm']}")
    print(f" RAG       : {hc['rag']}")
    print(f" 알림      : Slack {'✅' if hc['slack'] else '❌'} · "
          f"Email {'✅' if hc['email'] else '❌'}"
          + ("  [DRY-RUN]" if hc["dry_run"] else ""))
    print(f" DB        : {hc['db']}")
    if not a.no_config_file:
        print(f" 설정파일  : {_cfg_path}  (수정하면 다음 폴링에 즉시 반영)")
    for w in hc["warnings"]:
        print(f" ⚠️  {w}")
    print("=" * 70)

    w = Watcher(svc, inbox, a.interval, a.pattern, a.max_rows_per_poll,
                a.stable_after, None if a.no_config_file else _cfg_path)
    # 파일이 없으면 현재 설정으로 만들어 준다 → 대시보드에서 바로 편집 가능
    if not a.no_config_file and wcfg.seed_if_missing(cfg, _cfg_path):
        print(f" 설정 파일 생성: {Path(_cfg_path).resolve()}")
    w._cfg_mtime = (wcfg.path_of(_cfg_path).stat().st_mtime
                    if wcfg.path_of(_cfg_path).exists() else -1.0)

    if a.seed_cursor:
        n = w.seed_cursor()
        print(f"✅ 커서 시딩 완료 — {n}개 파일을 처리완료로 표시했습니다. "
              f"이제부터 추가되는 행만 탐지합니다.")
        return

    signal.signal(signal.SIGINT, w.stop)
    try:
        signal.signal(signal.SIGTERM, w.stop)
    except (AttributeError, ValueError):
        pass

    w.cursors.mark_started(f"watcher {WATCHER_VERSION} · {inbox}")

    if a.startup_ping and not cfg.dry_run:
        try:
            svc._get_notifier().send_slack(
                f"🟢 FDS 워처 기동 — `{inbox}` 감시 시작\n"
                f"분류기: {hc['classifier']} · 임계값: {hc['threshold']}")
        except Exception:
            pass

    if a.once:
        n = w.poll_once()
        w.polls = 1
        # 🐛 FIX: 하트비트가 run() 루프 안에만 있어서 --once 실행은 패널에
        #   "0폴링 · 마지막 폴링 None"으로 남았다. 1회 실행도 기록을 남긴다.
        try:
            s = svc.stats
            w.cursors.heartbeat(polls=1, rows_done=w.rows_done, anomalies=s["anomaly"],
                                notified=s["notified"], errors=s["errors"], note="once")
        except Exception:
            pass
        print(f"✅ 1회 폴링 완료 — {n:,}행 처리 · 이상 {svc.stats['anomaly']}건")
        return

    w.run()


def _try_alert_startup_failure(cfg: DetectConfig, msg: str):
    """기동 실패는 아무도 모르게 지나가면 안 된다 — Slack으로라도 알린다."""
    if cfg.dry_run or not cfg.notify_slack:
        return
    try:
        from pipeline.notifier import Notifier
        Notifier().send_slack(
            "🔴 *FDS 워처 기동 실패 — 탐지가 동작하지 않습니다*\n```" + msg[:900] + "```")
    except Exception:
        pass


if __name__ == "__main__":
    main()
