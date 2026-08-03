"""
Notifier — 이메일(SMTP) / Slack Webhook 알림 발송
v2 — 대시보드 오버라이드 파라미터 지원
"""

import os
import logging
import smtplib
import requests
from email.message import EmailMessage

# 🐛 FIX: python-dotenv 미설치 환경에서도 모듈 import가 죽지 않도록
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
log = logging.getLogger(__name__)


class Notifier:
    """
    대시보드에서 오버라이드 가능한 알림 발송기.

    Parameters
    ----------
    smtp_user : str | None
        None이면 .env의 SMTP_USER 사용
    smtp_pass : str | None
        None이면 .env의 SMTP_PASS 사용
    slack_webhook_url : str | None
        None이면 .env의 SLACK_WEBHOOK_URL 사용
    """

    def __init__(
        self,
        smtp_user: str | None = None,
        smtp_pass: str | None = None,
        slack_webhook_url: str | None = None,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
    ):
        self.smtp_user   = smtp_user or os.getenv("SMTP_USER")
        self.smtp_pass   = smtp_pass or os.getenv("SMTP_PASS")
        self.webhook_url = slack_webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        # ✨ v3.1: gmail 465 하드코딩 해제 — 타 SMTP/사내 릴레이 지원
        self.smtp_host   = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port   = int(smtp_port or os.getenv("SMTP_PORT", "465"))
        # ✨ v3.1: 마지막 실패 사유 — 대시보드가 읽어 화면에 표시 (로그 접근 불가 환경 대응)
        self.last_error  = ""

    # ── SMTP 연결 헬퍼 ─────────────────────────────────
    def _smtp_session(self, host: str, port: int):
        """465 → 암시적 SSL / 그 외(587 등) → 평문 접속 후 STARTTLS(지원 시)"""
        if port == 465:
            return smtplib.SMTP_SSL(host, port, timeout=15)
        s = smtplib.SMTP(host, port, timeout=15)
        s.ehlo()
        if s.has_extn("starttls"):
            s.starttls(); s.ehlo()
        return s

    @staticmethod
    def _classify(e: Exception, host: str, port: int) -> str:
        """예외 → 실무자가 조치 가능한 사유 문자열"""
        import socket, ssl
        if isinstance(e, smtplib.SMTPAuthenticationError):
            return (f"로그인 거부({e.smtp_code}) — Gmail은 일반 비밀번호가 아닌 "
                    "'앱 비밀번호'(2단계 인증 → 앱 비밀번호 발급)가 필요합니다. "
                    "공백 없이 16자리를 입력했는지 확인하세요")
        if isinstance(e, smtplib.SMTPRecipientsRefused):
            return f"수신 주소 거부 — 받는 이메일 주소를 확인하세요 ({e})"
        if isinstance(e, smtplib.SMTPSenderRefused):
            return f"발신 주소 거부({e.smtp_code}) — SMTP_USER와 동일한 주소인지 확인하세요"
        if isinstance(e, ssl.SSLError):
            return (f"SSL 오류 — 포트/프로토콜 불일치 가능성 (465=SSL, 587=STARTTLS). "
                    f"현재 {host}:{port} · {e}")
        if isinstance(e, (socket.timeout, TimeoutError)):
            return (f"연결 시간 초과 — {host}:{port} 가 방화벽/사내망에서 차단됐을 수 있습니다. "
                    "Slack(443)만 되고 메일이 안 되면 아웃바운드 SMTP 차단이 유력합니다")
        if isinstance(e, (ConnectionRefusedError, OSError)) and not isinstance(e, smtplib.SMTPException):
            return f"서버 접속 실패 — {host}:{port} (네트워크/방화벽/호스트명 확인) · {e}"
        return f"{type(e).__name__}: {e}"

    def test_smtp(self) -> tuple[bool, str]:
        """✨ v3.1: 실제 접속+로그인 검사 (발송 없음) — 기존 '객체 생성 = 성공' 가짜 테스트 대체"""
        if not self.smtp_user or not self.smtp_pass:
            self.last_error = "SMTP_USER / SMTP_PASS 미설정"
            return False, self.last_error
        try:
            with self._smtp_session(self.smtp_host, self.smtp_port) as s:
                s.login(self.smtp_user, self.smtp_pass)
            return True, f"{self.smtp_host}:{self.smtp_port} 로그인 성공 ({self.smtp_user})"
        except Exception as e:
            self.last_error = self._classify(e, self.smtp_host, self.smtp_port)
            return False, self.last_error

    # ── 이메일 발송 ────────────────────────────────────
    def send_email(self, to_address: str, subject: str, body: str,
                   html: str | None = None,
                   attachments: list | None = None) -> bool:
        """
        v3: multipart 지원.
          body        : 평문 파트 (html 미지원 클라이언트 폴백)
          html        : HTML 파트 — 지정 시 multipart/alternative 로 전송.
                        🐛 FIX: 기존엔 HTML 본문을 set_content(평문)로 보내
                        수신자에게 <div> 태그가 날것으로 보였음.
          attachments : [(filename, data(str|bytes), mime "text/html" 등), ...]
        기존 호출(send_email(to, subj, body))은 그대로 동작한다.
        """
        if not self.smtp_user or not self.smtp_pass:
            self.last_error = "SMTP_USER / SMTP_PASS 미설정 — .env 또는 대시보드 설정에 발신 계정을 입력하세요"
            log.warning("SMTP 환경변수 미설정 — 메일 발송 건너뜀")
            return False
        try:
            msg = EmailMessage()
            msg.set_content(body, charset="utf-8")
            if html:
                msg.add_alternative(html, subtype="html", charset="utf-8")
            for att in (attachments or []):
                try:
                    fname, data, mime = att
                    maintype, _, subtype = (mime or "application/octet-stream").partition("/")
                    if isinstance(data, str):
                        data = data.encode("utf-8")
                    msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream",
                                       filename=fname)
                except Exception as ae:                      # 첨부 1건 실패가 발송 전체를 막지 않도록
                    log.warning(f"첨부 실패({att[0] if att else '?'}): {ae}")
            msg["Subject"] = subject
            msg["From"]    = self.smtp_user
            msg["To"]      = to_address

            host, port = self.smtp_host, self.smtp_port
            try:
                with self._smtp_session(host, port) as server:
                    server.login(self.smtp_user, self.smtp_pass)
                    server.send_message(msg)
            except (OSError, TimeoutError) as ne:
                # ✨ v3.1: 465(암시적 SSL)가 방화벽에 막힌 환경 폴백 — 587 STARTTLS 재시도
                if port == 465 and not isinstance(ne, smtplib.SMTPException):
                    log.warning(f"{host}:465 접속 실패({ne}) → 587 STARTTLS 재시도")
                    with self._smtp_session(host, 587) as server:
                        server.login(self.smtp_user, self.smtp_pass)
                        server.send_message(msg)
                    log.info("587 폴백 발송 성공 — SMTP_PORT=587 고정 설정을 권장합니다")
                else:
                    raise
            self.last_error = ""
            log.info(f"메일 발송 완료 → {to_address}"
                     + (f" (HTML+첨부 {len(attachments or [])}건)" if html else ""))
            return True
        except Exception as e:
            self.last_error = self._classify(e, self.smtp_host, self.smtp_port)
            log.error(f"메일 발송 실패: {self.last_error}")
            return False

    # ── Slack 발송 ─────────────────────────────────────
    def send_slack(self, text: str) -> bool:
        if not self.webhook_url:
            self.last_error = "SLACK_WEBHOOK_URL 미설정"
            log.warning("SLACK_WEBHOOK_URL 미설정 — Slack 발송 건너뜀")
            return False
        try:
            resp = requests.post(self.webhook_url, json={"text": text}, timeout=10)
            if resp.status_code == 200:
                self.last_error = ""
                log.info("Slack 발송 완료")
                return True
            self.last_error = f"Slack 응답 {resp.status_code}: {resp.text[:120]}"
            log.error(f"Slack 발송 실패: {self.last_error}")
        except Exception as e:
            self.last_error = f"Slack 발송 오류: {e}"
            log.error(self.last_error)
        return False

    # ── 연결 상태 확인 ─────────────────────────────────
    def check_status(self) -> dict:
        """각 채널의 연결/설정 상태를 반환"""
        return {
            "smtp_host": f"{self.smtp_host}:{self.smtp_port}",
            "smtp_configured": bool(self.smtp_user and self.smtp_pass),
            "smtp_user": self.smtp_user or "(미설정)",
            "slack_configured": bool(self.webhook_url),
            "slack_url_prefix": (self.webhook_url.split("/services/")[0] + "/services/***") if self.webhook_url else "(미설정)",  # 🐛 FIX(v5): 시크릿 경로 노출 방지
        }
