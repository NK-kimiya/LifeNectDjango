from rest_framework import serializers
from .models import Tag,UploadedFile,BlogArticle

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

class BlogArticleSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), many=True, write_only=True, required=False
    )

    class Meta:
        model = BlogArticle
        fields = [
            "id", "title", "eyecatch", "body",
            "tags", "tag_ids", "created_at", "updated_at"
        ]

    def create(self, validated_data):
        tag_ids = validated_data.pop("tag_ids", [])
        article = BlogArticle.objects.create(**validated_data)
        article.tags.set(tag_ids)
        return article

    def update(self, instance, validated_data):
        tag_ids = validated_data.pop("tag_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tag_ids is not None:
            instance.tags.set(tag_ids)
        return instance