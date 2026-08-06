

from rest_framework import serializers
from myapp.models import Post, Tag, User
from .tag import TagSerializer

#投稿に紐づくユーザー情報を表示するためのシリアライザー
class PostUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "nickname",
        ]


#投稿を「読み取り用」に表示するためのシリアライザー
class PostReadSerializer(serializers.ModelSerializer):
    user = PostUserSerializer(read_only=True)#投稿を「読み取り用」に表示するためのシリアライザー(APIから書き換え不可)
    tags = TagSerializer(many=True, read_only=True)#投稿を「読み取り用」に表示するためのシリアライザー
    comment_count = serializers.IntegerField(read_only=True)

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
        read_only_fields = ["id", "user", "created_at", "updated_at"]#読み取り専用にする


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
            "image_url",
            "parent_post",
            "tag_ids",
        ]
        read_only_fields = ["id"]

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


class PostSerializer(serializers.ModelSerializer):
    user = PostUserSerializer(read_only=True)
    tags = serializers.StringRelatedField(many=True)

    #投稿用シリアライザー
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