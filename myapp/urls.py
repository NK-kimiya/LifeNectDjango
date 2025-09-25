from django.urls import path,include
from .views import me
from rest_framework.routers import DefaultRouter
from .views import TagViewSet,UploadedFileViewSet,BlogArticleViewSet

router = DefaultRouter()
router.register(r"tags", TagViewSet)
router.register(r'files', UploadedFileViewSet)
router.register(r'articles', BlogArticleViewSet)
urlpatterns = [
    path("me/", me, name="me"),  # 認証必須のサンプル
    path("", include(router.urls)),
]