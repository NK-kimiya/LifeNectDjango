# myapp/views/files.py
from myapp.models import UploadedFile
from myapp.permissions import IsAdminOrReadOnly
from myapp.views.base import BaseModelViewSet
from ..serializers import (
    TagSerializer,
    UploadedFileReadSerializer, UploadedFileWriteSerializer,
    BlogArticleReadSerializer, BlogArticleWriteSerializer,
)
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

class UploadedFileViewSet(BaseModelViewSet):
    queryset = UploadedFile.objects.all().order_by("-uploaded_at")
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return UploadedFileWriteSerializer
        return UploadedFileReadSerializer
    
    def create(self, request, *args, **kwargs):
        # 🔽 ファイルがアップロードされているか確認
        if "file" not in request.data or not request.data["file"]:
            return Response(
                {"detail": "アップロードするファイルを選択してください。"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 🔽 ファイルサイズの例（10MB制限など）
        upload = request.data["file"]
        if upload.size > 10 * 1024 * 1024:  # 10MB
            return Response(
                {"detail": "ファイルサイズが大きすぎます。10MB以内のファイルを選択してください。"},
                status=status.HTTP_400_BAD_REQUEST
            )

        
        write_serializer = UploadedFileWriteSerializer(data=request.data)
        if not write_serializer.is_valid():
            # ★ 変更: ここでバリデーションエラーを返す
            return Response(write_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        instance = write_serializer.save()
        read_serializer = UploadedFileReadSerializer(instance, context={"request": request})
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)





