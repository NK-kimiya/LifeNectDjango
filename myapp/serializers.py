from rest_framework import serializers
from .models import Tag,UploadedFile

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]
        

class UploadedFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    class Meta:
        model = UploadedFile
        fields = ["id", "file_url", "uploaded_at"]
        
    def get_file_url(self, obj):
        if obj.file:
            return obj.file.url  # Cloudinary のURLが返る
        return None