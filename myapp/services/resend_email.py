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

def send_account_created_email(user) -> None:
    if not settings.RESEND_API_KEY:
        raise ResendEmailError("RESEND_API_KEY is not configured.")

    if not settings.RESEND_FROM_EMAIL:
        raise ResendEmailError("RESEND_FROM_EMAIL is not configured.")

    template_id = settings.RESEND_ACCOUNT_CREATED_TEMPLATE_ID
    if not template_id:
        raise ResendEmailError("RESEND_ACCOUNT_CREATED_TEMPLATE_ID is not configured.")

    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [user.email],
            "template": {
                "id": template_id,
                "variables": {
                    "NICKNAME": user.nickname,
                    "EMAIL": user.email,
                },
            },
        })
    except ResendError as error:
        raise ResendEmailError(str(error)) from error

def send_account_status_email(user, previous_status: str, new_status: str) -> None:
    if not settings.RESEND_API_KEY:
        raise ResendEmailError("RESEND_API_KEY is not configured.")

    if not settings.RESEND_FROM_EMAIL:
        raise ResendEmailError("RESEND_FROM_EMAIL is not configured.")

    template_id = settings.RESEND_ACCOUNT_STATUS_TEMPLATE_ID
    if not template_id:
        raise ResendEmailError("RESEND_ACCOUNT_STATUS_TEMPLATE_ID is not configured.")

    status_labels = {
        "active": "通常利用",
        "suspended": "凍結",
        "banned": "利用停止",
    }

    if new_status == "active":
        subject_label = "凍結解除"
        message = "アカウントの凍結が解除されました。通常どおりご利用いただけます。"
    elif new_status == "suspended":
        subject_label = "凍結"
        message = "アカウントが凍結されました。現在、一部またはすべての機能をご利用いただけません。"
    elif new_status == "banned":
        subject_label = "利用停止"
        message = "アカウントが利用停止になりました。"
    else:
        return

    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [user.email],
            "template": {
                "id": template_id,
                "variables": {
                    "NICKNAME": user.nickname,
                    "EMAIL": user.email,
                    "STATUS_LABEL": status_labels.get(new_status, new_status),
                    "PREVIOUS_STATUS_LABEL": status_labels.get(previous_status, previous_status),
                    "SUBJECT_LABEL": subject_label,
                    "MESSAGE": message,
                },
            },
        })
    except ResendError as error:
        raise ResendEmailError(str(error)) from error

def send_password_reset_email(user, reset_url: str) -> None:
    if not settings.RESEND_API_KEY:
        raise ResendEmailError("RESEND_API_KEY is not configured.")

    if not settings.RESEND_FROM_EMAIL:
        raise ResendEmailError("RESEND_FROM_EMAIL is not configured.")

    template_id = settings.RESEND_PASSWORD_RESET_TEMPLATE_ID
    if not template_id:
        raise ResendEmailError("RESEND_PASSWORD_RESET_TEMPLATE_ID is not configured.")

    resend.api_key = settings.RESEND_API_KEY

    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [user.email],
            "template": {
                "id": template_id,
                "variables": {
                    "NICKNAME": user.nickname,
                    "RESET_URL": reset_url,
                    "EXPIRES_MINUTES": "30",
                },
            },
        })
    except ResendError as error:
        raise ResendEmailError(str(error)) from error