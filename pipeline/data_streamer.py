"""
DataStreamer — 5가지 입력 방식 지원
  방식 1: 직접 입력 (dict)
  방식 2: test.csv 임의 추출
  방식 3: train.csv 임의 추출 (정답 포함)
  방식 4: train.csv 분포 기반 합성 생성
  방식 5: 폴더 내 전체 CSV 파일 순차 처리
"""

import random
import sqlite3
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Generator

log = logging.getLogger(__name__)

CAT_OPTIONS = {
    'Customer_Gender':       ['male','female'],
    'Customer_credit_rating':['A','B','C','D','E','S'],
    'Customer_loan_type':    ['a','b','c','d','e'],
    'Account_account_type':  ['a','b','c','d'],
    'Channel':               ['ATM','internet','mobile','Others'],
    'Operating_System':      ['Android','Linux','Others','Windows','iOS','macOS'],
    'Error_Code':            ['a','c'],
    'Type_General_Automatic':['automatic','general'],
    'Access_Medium':         ['a','b','c','d','e','f','g'],
}

BINARY_FLAGS = [
    'Customer_flag_change_of_authentication_1',
    'Customer_flag_change_of_authentication_2',
    'Customer_flag_change_of_authentication_3',
    'Customer_flag_change_of_authentication_4',
    'Customer_rooting_jailbreak_indicator',
    'Customer_mobile_roaming_indicator',
    'Customer_VPN_Indicator',
    'Customer_flag_terminal_malicious_behavior_1',
    'Customer_flag_terminal_malicious_behavior_2',
    'Customer_flag_terminal_malicious_behavior_3',
    'Customer_flag_terminal_malicious_behavior_4',
    'Customer_flag_terminal_malicious_behavior_5',
    'Customer_flag_terminal_malicious_behavior_6',
    'Customer_inquery_atm_limit',
    'Customer_increase_atm_limit',
    'Account_indicator_release_limit_excess',
    'Account_indicator_Openbanking',
    'Account_release_suspention',
    'Transaction_Failure_Status',
    'Unused_terminal_status',
    'Flag_deposit_more_than_tenMillion',
    'Unused_account_status',
    'Recipient_account_suspend_status',
    'First_time_iOS_by_vulnerable_user',
    'Another_Person_Account',
]


class DataStreamer:
    def __init__(
        self,
        train_path: str = "data/train.csv",
        test_path:  str = "data/test.csv",
        folder_path:str = "data/",
        db_path:    str = "fds_results.db",
    ):
        self.train_path  = Path(train_path)
        self.test_path   = Path(test_path)
        self.folder_path = Path(folder_path)
        self.db_path     = db_path
        self._train_df   = None
        self._init_db()

    # ── DB 초기화 ────────────────────────────────────────
    def _init_db(self):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT,
                fraud_type     TEXT,
                risk_score     REAL,
                is_anomaly     INTEGER DEFAULT 0,
                input_mode     TEXT,
                true_label     TEXT,
                processed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit(); con.close()

    # ════════════════════════════════════════════════════
    # 방식 1 — 직접 입력
    # ════════════════════════════════════════════════════
    def from_manual(self, row: dict) -> dict:
        """UI에서 직접 입력한 dict를 그대로 반환"""
        row['_input_mode'] = 'manual'
        row['transaction_id'] = row.get('transaction_id', f"MANUAL_{random.randint(1000,9999)}")
        return row

    # ════════════════════════════════════════════════════
    # 방식 2 — test.csv 임의 추출
    # ════════════════════════════════════════════════════
    def from_test_csv(self, n: int = 1) -> list[dict]:
        if not self.test_path.exists():
            log.warning(f"test.csv 없음: {self.test_path}")
            return []
        df = pd.read_csv(self.test_path)
        rows = df.sample(min(n, len(df))).to_dict('records')
        for r in rows:
            r['_input_mode'] = 'test_csv'
            r['transaction_id'] = r.get('ID', f"TEST_{random.randint(1000,9999)}")
        return rows

    # ════════════════════════════════════════════════════
    # 방식 3 — train.csv 임의 추출 (정답 포함)
    # ════════════════════════════════════════════════════
    def from_train_csv(self, n: int = 1, fraud_only: bool = False) -> list[dict]:
        df = self._get_train_df()
        if fraud_only:
            df = df[df['Fraud_Type'] != 'm']
        rows = df.sample(min(n, len(df))).to_dict('records')
        for r in rows:
            r['_input_mode']    = 'train_csv'
            r['_true_label']    = r.get('Fraud_Type', 'unknown')
            r['transaction_id'] = r.get('ID', f"TRAIN_{random.randint(1000,9999)}")
        return rows

    # ════════════════════════════════════════════════════
    # 방식 4 — train.csv 분포 기반 합성 생성
    # ════════════════════════════════════════════════════
    def from_synthetic(self, n: int = 1, fraud_type: str = None) -> list[dict]:
        """train 분포를 학습해 합성 데이터 생성"""
        df = self._get_train_df()
        if fraud_type and fraud_type in df['Fraud_Type'].unique():
            ref_df = df[df['Fraud_Type'] == fraud_type]
        else:
            ref_df = df

        # ⚡ 최적화: 통계를 루프 밖에서 1회만 계산
        #   (기존: n건 생성 시 mean/std/value_counts를 n번 재계산 → n=1000이면 수십 초)
        num_cols = [c for c in ref_df.select_dtypes(include='number').columns
                    if c != 'Fraud_Type']
        num_stats = {}
        for col in num_cols:
            mu  = float(ref_df[col].mean())
            sig = float(ref_df[col].std())
            num_stats[col] = (mu, sig if sig > 0 else 1.0)

        cat_probs = {}
        for col, options in CAT_OPTIONS.items():
            if col in ref_df.columns:
                freq  = ref_df[col].value_counts(normalize=True)
                probs = [float(freq.get(o, 0)) for o in options]
                total = sum(probs)
                cat_probs[col] = [p/total for p in probs] if total > 0 else None
            else:
                cat_probs[col] = None

        # 수치형 전체를 벡터화 샘플링 (n × cols 한 번에)
        sampled = {col: np.random.normal(mu, sig, size=n)
                   for col, (mu, sig) in num_stats.items()}

        rows = []
        for i in range(n):
            row = {}
            for col in num_cols:
                val = sampled[col][i]
                if col in BINARY_FLAGS:
                    row[col] = int(np.clip(round(val), 0, 1))
                else:
                    row[col] = round(float(val), 2)

            for col, options in CAT_OPTIONS.items():
                probs = cat_probs.get(col)
                if col in ref_df.columns:
                    # str() 캐스팅 — np.str_ 타입이 json 직렬화/비교에서 섞이지 않도록
                    row[col] = str(np.random.choice(options, p=probs))
                else:
                    row[col] = random.choice(options)

            row['_input_mode']    = 'synthetic'
            row['_target_type']   = fraud_type or 'random'
            row['transaction_id'] = f"SYN_{i:04d}_{random.randint(100,999)}"
            rows.append(row)

        return rows

    # ════════════════════════════════════════════════════
    # 방식 5 — 폴더 전체 CSV 파일 순차 스트리밍
    # ════════════════════════════════════════════════════
    def stream_folder(self) -> Generator[dict, None, None]:
        csv_files = sorted(self.folder_path.glob("*.csv"))
        if not csv_files:
            log.warning(f"CSV 파일 없음: {self.folder_path}")
            return
        for csv_file in csv_files:
            log.info(f"파일 처리 중: {csv_file.name}")
            df = pd.read_csv(csv_file)
            for _, row in df.iterrows():
                r = row.to_dict()
                r['_input_mode']    = 'folder'
                r['_source_file']   = csv_file.name
                r['transaction_id'] = r.get('ID', f"FOLDER_{random.randint(1000,9999)}")
                yield r

    # ── 시간 순 스트리밍 (기존 main.py 호환) ─────────────
    def stream(self) -> Generator[dict, None, None]:
        """train.csv를 Transaction_Datetime 순으로 스트리밍"""
        df = self._get_train_df()
        # 🐛 FIX(v5): 시간 컬럼 없는 CSV(test 계열 등)에서 KeyError로 즉사하지 않도록
        if 'Transaction_Datetime' in df.columns:
            df = df.sort_values('Transaction_Datetime', na_position='last')
        else:
            log.warning("Transaction_Datetime 컬럼 없음 — 원본 순서로 스트리밍")
        for _, row in df.iterrows():
            r = row.to_dict()
            r['_input_mode']    = 'stream'
            r['transaction_id'] = r.get('ID', '')
            yield r

    # ── DB 저장 ──────────────────────────────────────────
    def save_result(self, row: dict, fraud_type: str,
                    risk_score: float, is_anomaly: bool):
        con = sqlite3.connect(self.db_path)
        con.execute(
            """INSERT INTO transactions
               (transaction_id, fraud_type, risk_score, is_anomaly, input_mode, true_label)
               VALUES (?,?,?,?,?,?)""",
            (
                row.get('transaction_id',''),
                fraud_type,
                risk_score,
                int(is_anomaly),
                row.get('_input_mode','unknown'),
                row.get('_true_label',''),
            )
        )
        con.commit(); con.close()

    def save_normal(self, row: dict, fraud_type: str, risk_score: float):
        self.save_result(row, fraud_type, risk_score, is_anomaly=False)

    # ── 내부 헬퍼 ────────────────────────────────────────
    def _get_train_df(self) -> pd.DataFrame:
        if self._train_df is None:
            if not self.train_path.exists():
                raise FileNotFoundError(f"train.csv 없음: {self.train_path}")
            self._train_df = pd.read_csv(self.train_path)
            log.info(f"train.csv 로드: {len(self._train_df)}건")
        return self._train_df

    # ── 범주형 옵션 반환 (대시보드 UI용) ─────────────────
    @staticmethod
    def get_cat_options() -> dict:
        return CAT_OPTIONS

    @staticmethod
    def get_binary_flags() -> list:
        return BINARY_FLAGS
