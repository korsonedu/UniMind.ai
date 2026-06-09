import logging
import secrets
import smtplib
import string
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from django.conf import settings

logger = logging.getLogger(__name__)

VERIFICATION_CODE_LENGTH = 6
VERIFICATION_CODE_TTL_MINUTES = 10

# Feishu SMTP
FEISHU_SMTP_HOST = "smtp.feishu.cn"
FEISHU_SMTP_PORT = 465
DEFAULT_FROM_EMAIL = "notification@unimind-ai.com"
DEFAULT_FROM_NAME = "UniMind"


def _smtp_password():
    return getattr(settings, "FEISHU_NOTIFY_PASSWORD", "")


def generate_verification_code() -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(VERIFICATION_CODE_LENGTH))


def _send_via_smtp(*, to: str, subject: str, html: str, text: str) -> bool:
    password = _smtp_password()
    if not password:
        logger.error("FEISHU_NOTIFY_PASSWORD not configured")
        return False

    msg = MIMEMultipart()
    msg["From"] = f"{DEFAULT_FROM_NAME} <{DEFAULT_FROM_EMAIL}>"
    msg["To"] = to
    msg["Subject"] = subject
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    if text:
        msg.attach(MIMEText(text, "plain", "utf-8"))

    for attempt in range(3):
        try:
            with smtplib.SMTP_SSL(FEISHU_SMTP_HOST, FEISHU_SMTP_PORT, timeout=15) as server:
                server.login(DEFAULT_FROM_EMAIL, password)
                server.sendmail(DEFAULT_FROM_EMAIL, [to], msg.as_bytes())
            logger.info("Email sent to %s via Feishu SMTP", to)
            return True
        except Exception as exc:
            if attempt < 2:
                time.sleep(min(2 ** attempt, 4))
                continue
            logger.exception("Failed to send email to %s after 3 attempts: %s", to, exc)
            return False
    return False


def _verification_email_html(code: str) -> str:
    logo_url = getattr(settings, "UNIMIND_LOGO_URL", "https://unimind-ai.com/logo.png")
    minutes = VERIFICATION_CODE_TTL_MINUTES
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
</head>
<body style="margin:0;padding:0;background-color:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" role="presentation">
  <tr>
    <td align="center" style="padding:48px 24px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="max-width:480px;background-color:#ffffff;border-radius:12px;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background-color:#1a1a1a;padding:32px 40px;text-align:center;">
            <img src="{logo_url}" alt="UniMind" width="140" height="28" style="display:block;margin:0 auto;border:0;">
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:40px 40px 24px;">

            <p style="margin:0 0 4px;font-size:22px;font-weight:700;color:#1a1a1a;line-height:1.3;">
              Your Verification Code
            </p>
            <p style="margin:0 0 36px;font-size:16px;font-weight:700;color:#1a1a1a;line-height:1.3;">
              您的验证码
            </p>

            <!-- Code box -->
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="margin-bottom:36px;">
              <tr>
                <td style="background-color:#f7f8fa;border-radius:10px;padding:24px 16px;text-align:center;">
                  <span style="font-size:38px;font-weight:800;letter-spacing:14px;color:#1a1a1a;font-family:'SF Mono','Menlo','Courier New',monospace;mso-font-width:120%;">{code}</span>
                </td>
              </tr>
            </table>

            <p style="margin:0 0 6px;font-size:14px;color:#999;line-height:1.6;">
              This code will expire in <strong style="color:#1a1a1a;">{minutes} minutes</strong>.
            </p>
            <p style="margin:0 0 32px;font-size:14px;color:#999;line-height:1.6;">
              此验证码 <strong style="color:#1a1a1a;">{minutes} 分钟</strong> 内有效。
            </p>

            <!-- Security notice -->
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="border:1px solid #fde68a;background-color:#fffbeb;border-radius:8px;margin-bottom:28px;">
              <tr>
                <td style="padding:16px;">
                  <p style="margin:0 0 4px;font-size:13px;color:#92400e;line-height:1.5;">
                    For security, do not share this code with anyone.
                  </p>
                  <p style="margin:0;font-size:13px;color:#92400e;line-height:1.5;">
                    出于安全考虑，请勿向任何人转发此验证码。
                  </p>
                </td>
              </tr>
            </table>

            <p style="margin:0 0 4px;font-size:12px;color:#ccc;line-height:1.5;">
              If you did not request this code, please ignore this email.
            </p>
            <p style="margin:0;font-size:12px;color:#ccc;line-height:1.5;">
              如果您未请求此验证码，请忽略此邮件。
            </p>

          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="border-top:1px solid #eee;padding:24px 40px;text-align:center;">
            <p style="margin:0;font-size:12px;color:#bbb;">UniMind.ai</p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def send_verification_email(email: str, code: str) -> bool:
    subject = "UniMind.ai – Verification Code / 邮箱验证码"
    plain = (
        f"您的 UniMind.ai 验证码是：{code}\n"
        f"Your UniMind.ai verification code is: {code}\n\n"
        f"验证码 {VERIFICATION_CODE_TTL_MINUTES} 分钟内有效，请勿转发给他人。\n"
        f"This code will expire in {VERIFICATION_CODE_TTL_MINUTES} minutes. "
        f"For security, do not share this code with anyone.\n\n"
        f"如果您未注册 UniMind.ai，请忽略此邮件。\n"
        f"If you did not request this code, please ignore this email.\n\n"
        f"UniMind.ai"
    )
    return _send_via_smtp(to=email, subject=subject, html=_verification_email_html(code), text=plain)


def send_email(recipient: str, subject: str, body: str) -> bool:
    """Generic email sender — plain text only."""
    return _send_via_smtp(to=recipient, subject=subject, text=body, html="")


def send_membership_notification(email: str, tier: str, expires_at) -> bool:
    tier_labels = {'free': 'Free', 'starter': 'Starter', 'growth': 'Growth', 'enterprise': 'Enterprise'}
    label = tier_labels.get(tier, tier)
    subject = f"UniMind.ai — 会员激活成功 ({label})"
    if expires_at:
        expiry_str = expires_at.strftime('%Y-%m-%d %H:%M')
        message = f"您的 UniMind.ai {label} 会员已激活，有效期至 {expiry_str}。"
    else:
        message = f"您的 UniMind.ai {label} 会员已激活，无限期有效。"
    message += "\n\n如有任何问题，请回复此邮件联系我们。\n\n— UniMind.ai 团队"

    return _send_via_smtp(to=email, subject=subject, text=message, html="")
