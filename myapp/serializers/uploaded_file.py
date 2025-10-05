from rest_framework import serializers
from myapp.models import UploadedFile

class UploadedFileReadSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = UploadedFile
        fields = ["id", "file_url", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at"]

    def get_file_url(self, obj):
        # CloudinaryField は obj.file が None の可能性があるので安全に参照
        request = self.context.get("request")
        try:
            if obj.file:
                # ★ request がある場合は build_absolute_uri を使う
                return request.build_absolute_uri(obj.file.url) if request else obj.file.url
            return None
        except Exception:
            return None

class UploadedFileWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = ["id", "file"]  # 作成/更新時はファイル本体を受け取る
        read_only_fields = ["id"]
