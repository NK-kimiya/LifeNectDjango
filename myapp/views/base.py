from rest_framework import viewsets
from myapp.exceptions import custom_handle_exception

class ExceptionHandlingMixin:
    """各ViewSetで重複している handle_exception を共通化"""
    def handle_exception(self, exc):
        # 共通の例外処理を利用
        response = custom_handle_exception(exc, context=self)
        if response:
            return response
        return super().handle_exception(exc)

class BaseModelViewSet(ExceptionHandlingMixin, viewsets.ModelViewSet):
    """継承用の共通ViewSet（必要に応じて共通設定を足せます）"""
    pass