from django.urls import path
from .views import me

urlpatterns = [
    path("me/", me, name="me"),  # 認証必須のサンプル
]