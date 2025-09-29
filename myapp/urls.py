# myapp/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import me, TagViewSet, UploadedFileViewSet, BlogArticleViewSet,RagAnswer,BlogArticleFilterView

router = DefaultRouter()
router.register(r"tags", TagViewSet)
router.register(r"files", UploadedFileViewSet)
router.register(r"articles", BlogArticleViewSet)

urlpatterns = [
    path("me/", me.as_view(), name="me"),
    path("rag-answer/", RagAnswer.as_view(), name="similar-articles"), 
    path("", include(router.urls)),
    path("articles-search/", BlogArticleFilterView.as_view(),name="articles-search"),
]