from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotAuthenticated, AuthenticationFailed, ValidationError

def custom_handle_exception(exc, context=None):
    """例外ごとにカスタムレスポンスを返す"""
    if isinstance(exc, PermissionDenied):
        return Response(
            {"message": "管理者権限が必要です。再度ログインしてください。"},
            status=status.HTTP_403_FORBIDDEN
        )
    if isinstance(exc, NotAuthenticated):
        return Response(
            {"message": "ログインしていません。ログインしてください。"},
            status=status.HTTP_401_UNAUTHORIZED
        )
    if isinstance(exc, AuthenticationFailed):
        return Response(
            {"message": "認証に失敗しました。再度ログインしてください。"},
            status=status.HTTP_401_UNAUTHORIZED
        )
    if isinstance(exc, ValidationError):
        return Response(
            {"message": "入力内容に誤りがあるか、既に作成されているデータです。", "details": exc.detail},
            status=status.HTTP_400_BAD_REQUEST
        )
    return None  # それ以外はデフォルト処理
