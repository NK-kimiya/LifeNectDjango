# myapp/views/articles.py
from myapp.models import BlogArticle
from myapp.permissions import IsAdminOrReadOnly
from myapp.views.base import BaseModelViewSet
from rest_framework import viewsets

from ..serializers import (
    TagSerializer,
    UploadedFileReadSerializer, UploadedFileWriteSerializer,
    BlogArticleReadSerializer, BlogArticleWriteSerializer,
)


# BlogArticleViewSet に追加
class BlogArticleViewSet(BaseModelViewSet):
    queryset = BlogArticle.objects.all().order_by("-created_at")
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return BlogArticleWriteSerializer
        return BlogArticleReadSerializer