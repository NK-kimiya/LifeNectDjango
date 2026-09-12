from django.conf import settings
import resend
from resend.exceptions import ResendError


class ResendEmailError(Exception):
    pass


def send_application_verification_code(email: str, code: str) -> None:
    if not settings.RESEND_API_KEY:
        raise ResendEmailError("RESEND_API_KEY is not configured.")

    if not settings.RESEND_FROM_EMAIL:
        raise ResendEmailError("RESEND_FROM_EMAIL is not configured.")

    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [email],
            "subject": "アカウント申請の認証コード",
            "html": f"""
                <p>アカウント申請の認証コードです。</p>
                <p><strong>{code}</strong></p>
                <p>このコードの有効期限は10分です。</p>
            """,
        })
    except ResendError as error:
        raise ResendEmailError(str(error)) from error