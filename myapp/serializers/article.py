from rest_framework import serializers
from myapp.models import BlogArticle, Tag
from .tag import TagSerializer

class BlogArticleReadSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = BlogArticle
        fields = ["id", "title", "eyecatch", "body", "tags", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

class BlogArticleWriteSerializer(serializers.ModelSerializer):
    # 書き込み用に tag_ids を受ける（PK配列）
    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = BlogArticle
        fields = ["id", "title", "eyecatch", "body", "tag_ids"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        tags = validated_data.pop("tag_ids", [])
        article = BlogArticle.objects.create(**validated_data)
        if tags:
            article.tags.set(tags)
        return article

    def update(self, instance, validated_data):
        tags = validated_data.pop("tag_ids", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if tags is not None:
            instance.tags.set(tags)
        return instance
