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

def send_application_result_email(application) -> None:
    if not settings.RESEND_API_KEY:
        raise ResendEmailError("RESEND_API_KEY is not configured.")

    if not settings.RESEND_FROM_EMAIL:
        raise ResendEmailError("RESEND_FROM_EMAIL is not configured.")

    template_id = settings.RESEND_APPLICATION_RESULT_TEMPLATE_ID
    if not template_id:
        raise ResendEmailError("RESEND_APPLICATION_RESULT_TEMPLATE_ID is not configured.")

    result_label = (
        "承認"
        if application.status == application.Status.APPROVED
        else "却下"
    )

    message = (
        "アカウント作成が可能になりました。ログイン画面から登録を進めてください。"
        if application.status == application.Status.APPROVED
        else "申し訳ありませんが、今回の申請は却下されました。"
    )

    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [application.email],
            "template": {
                "id": template_id,
                "variables": {
                    "NICKNAME": application.nickname,
                    "RESULT_LABEL": result_label,
                    "MESSAGE": message,
                },
            },
        })
    except ResendError as error:
        raise ResendEmailError(str(error)) from error