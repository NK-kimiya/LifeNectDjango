

from rest_framework import serializers
from myapp.models import Post, Tag, User
from .tag import TagSerializer
from myapp.services.cloudflare_r2 import (
    CloudflareR2Error,
    generate_presigned_read_url,
)

#投稿に紐づくユーザー情報を表示するためのシリアライザー
class PostUserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "nickname",
            "avatar_url",
        ]

    def get_avatar_url(self, obj):
        try:
            return generate_presigned_read_url(obj.avatar_key)
        except CloudflareR2Error:
            return None


class PostSerializer(serializers.ModelSerializer):
    user = PostUserSerializer(read_only=True)
    tags = serializers.StringRelatedField(many=True)
    image_url = serializers.SerializerMethodField()

    def get_image_url(self, obj):
        if not obj.image_key:
            return None

        try:
            return generate_presigned_read_url(obj.image_key)
        except CloudflareR2Error:
            return None

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "title",
            "comment",
            "image_url",
            "parent_post",
            "tags",
            "created_at",
        ]

#投稿を「作成・更新するため」のシリアライザー
class PostWriteSerializer(serializers.ModelSerializer):
    #タグをIDで受け取るためのフィールドを定義
    tag_ids = serializers.PrimaryKeyRelatedField(
        many=True,#複数のタグIDを受け取る
        queryset=Tag.objects.all(),#指定されたタグIDが、実際に存在する Tag の中から選ばれているか確認
        write_only=True,#書き込み専用
        required=False,#レスポンスには、タグIDは指定しない
    )

    parent_post = serializers.PrimaryKeyRelatedField(
        queryset=Post.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Post
        fields = [
            "id",
            "title",
            "comment",
            "image_key",
            "image_content_type",
            "parent_post",
            "tag_ids",
        ]
        read_only_fields = ["id"]

    def validate_image_key(self, value):
        if not value:
            return value

        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication is required.")

        expected_prefix = f"posts/users/{request.user.id}/images/"
        if not value.startswith(expected_prefix):
            raise serializers.ValidationError("Invalid image key.")

        return value

    def validate_image_content_type(self, value):
        if not value:
            return value

        allowed_content_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if value not in allowed_content_types:
            raise serializers.ValidationError("Unsupported image content type.")

        return value

    def validate(self, attrs):
        image_key = attrs.get("image_key")
        image_content_type = attrs.get("image_content_type")
        parent_post = attrs.get("parent_post")
        if parent_post is None and self.instance:
            parent_post = self.instance.parent_post

        if bool(image_key) != bool(image_content_type):
            raise serializers.ValidationError(
                "image_key and image_content_type must be set together."
            )

        if parent_post and image_key:
            raise serializers.ValidationError(
                "Replies cannot have images."
            )

    

        return attrs

    #arent_post の値を検証するメソッド
    def validate_parent_post(self, value):
        if self.instance and value == self.instance:#更新時に、自分自身を親投稿として指定していないか確認
            raise serializers.ValidationError("自分自身を返信先に指定することはできません。")
        return value

    #投稿を新規作成するときの処理
    def create(self, validated_data):
        request = self.context.get("request")#シリアライザーの context からリクエスト情報を取得
        tags = validated_data.pop("tag_ids", [])#送信データからtag_idを取り出す、存在しなければ空リスト

        post = Post.objects.create(
            user=request.user,#投稿者を現在ログイン中のユーザー
            **validated_data,#title、comment、image_url、parent_post などの検証済みデータ
        )

        if tags:#タグが指定されている場合だけ
            post.tags.set(tags)#作成した投稿にタグを紐づけ

        return post

    #投稿を更新するときの処理
    def update(self, instance, validated_data):
        tags = validated_data.pop("tag_ids", None)#更新データから、tag_idsを取り出す

        for attr, value in validated_data.items():#更新データを1つずつ取り出す
            setattr(instance, attr, value)#投稿オブジェクトの属性を更新

        instance.save()

        if tags is not None:
            instance.tags.set(tags)

        return instance


class PostReadSerializer(serializers.ModelSerializer):
    user = PostUserSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    comment_count = serializers.IntegerField(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = [
            "id",
            "user",
            "title",
            "comment",
            "image_url",
            "parent_post",
            "tags",
            "comment_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def get_image_url(self, obj):
        if not obj.image_key:
            return None

        try:
            return generate_presigned_read_url(obj.image_key)
        except CloudflareR2Error:
            return None