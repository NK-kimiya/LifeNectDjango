# myapp/views/files.py
from myapp.models import UploadedFile
from myapp.permissions import IsAdminOrReadOnly
from myapp.views.base import BaseModelViewSet
from ..serializers import (
    TagSerializer,
    UploadedFileReadSerializer, UploadedFileWriteSerializer,
    BlogArticleReadSerializer, BlogArticleWriteSerializer,
)


class UploadedFileViewSet(BaseModelViewSet):
    queryset = UploadedFile.objects.all().order_by("-uploaded_at")
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return UploadedFileWriteSerializer
        return UploadedFileReadSerializer



