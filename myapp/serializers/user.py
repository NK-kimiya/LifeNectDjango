from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from myapp.models import AccountApplication,AccountApplicationVerification
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.db.models import Count
from myapp.models import Post
from myapp.serializers.post import PostReadSerializer
from django.contrib.auth.password_validation import validate_password
from myapp.services.cloudflare_r2 import (
    CloudflareR2Error,
    generate_presigned_read_url,
    validate_avatar_content_type,
)
User = get_user_model()

class UserProfileSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "nickname",
            "role",
            "provider",
            "avatar_content_type",
            "avatar_url",
            "profile_text",
        )
        read_only_fields = (
            "id",
            "email",
            "role",
            "provider",
            "avatar_url",
        )

    def get_avatar_url(self, obj):
        try:
            return generate_presigned_read_url(obj.avatar_key)
        except CloudflareR2Error:
            return None

    def validate_profile_text(self, value):
        if len(value) > 500:
            raise serializers.ValidationError("プロフィール文は1000文字以内で入力してください。")
        return value

class UserAvatarUpdateSerializer(serializers.Serializer):
    avatar_key = serializers.CharField(max_length=500)
    avatar_content_type = serializers.CharField(max_length=100)

    #画像形式をチェック
    def validate_avatar_content_type(self, value):
        validate_avatar_content_type(value)
        return value

    #avatar_key の所有者チェック
    def validate_avatar_key(self, value):#value という文字列が expected_prefix で始まっているか
        user = self.context["request"].user
        expected_prefix = f"users/{user.id}/avatar/"

        if not value.startswith(expected_prefix):
            raise serializers.ValidationError("Invalid avatar key.")

        return value

    #User モデル更新
    def save(self, **kwargs):
        user = self.context["request"].user

        user.avatar_key = self.validated_data["avatar_key"]
        user.avatar_content_type = self.validated_data["avatar_content_type"]

        user.save(
            update_fields=[
                "avatar_key",
                "avatar_content_type",
            ]
        )

        return user


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "email", "nickname", "password", "role")
        read_only_fields = ("id", "role")

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            nickname=validated_data["nickname"],
            password=validated_data["password"],
        )


class RegisterResponseSerializer(serializers.ModelSerializer):
    access = serializers.SerializerMethodField()
    refresh = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "nickname", "role", "access", "refresh")

    def get_access(self, obj):
        refresh = RefreshToken.for_user(obj)
        return str(refresh.access_token)

    def get_refresh(self, obj):
        refresh = RefreshToken.for_user(obj)
        return str(refresh)

class AccountApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountApplication
        fields = ("id", "nickname", "email", "condition", "status", "created_at")
        read_only_fields = ("id", "status", "created_at")


class AccountApplicationAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountApplication
        fields = (
            "id",
            "nickname",
            "email",
            "condition",
            "status",
            "created_at",
            "reviewed_at",
        )
        read_only_fields = (
            "id",
            "nickname",
            "email",
            "condition",
            "created_at",
            "reviewed_at",
        )

class AccountApplicationSendCodeSerializer(serializers.Serializer):
    nickname = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    condition = serializers.CharField()

    def validate_email(self, value):
        email = value.lower().strip()

        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "このメールアドレスはすでに登録されています。"
            )

        if AccountApplication.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "このメールアドレスはすでに申請済みです。"
            )

        return email

class AccountApplicationVerifyCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)

    def validate_email(self, value):
        return value.lower().strip()

    def validate_code(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("認証コードは数字6桁で入力してください。")
        return value


#ログイン時のJWTトークン発行処理をカスタマイズするSerializer
class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        #親クラスのログイン認証処理を実行
        #メールアドレス・パスワードが正しければ、JWTトークンが dataに入る
        #認証されたユーザーは self.user に
        data = super().validate(attrs)

        #suspended や banned の場合はログインを拒否
        if self.user.account_status != User.AccountStatus.ACTIVE:
            raise AuthenticationFailed(
                "このアカウントは現在利用できません。",
                code="account_suspended",
            )

        #ログイン成功時のレスポンスに、JWTトークンだけでなくユーザー情報も追加
        data["id"] = self.user.id
        data["email"] = self.user.email
        data["nickname"] = self.user.nickname

        return data


class AdminUserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "nickname",
            "avatar_url",
            "account_status",
        )

    def get_avatar_url(self, obj):
        try:
            return generate_presigned_read_url(obj.avatar_key)
        except CloudflareR2Error:
            return None

class AdminUserDetailSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    posts = serializers.SerializerMethodField()
    post_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "nickname",
            "role",
            "provider",
            "account_status",
            "is_active",
            "is_staff",
            "is_superuser",
            "avatar_url",
            "avatar_content_type",
            "profile_text",
            "date_joined",
            "last_login",
            "post_count",
            "posts",
        )

    def get_avatar_url(self, obj):
        try:
            return generate_presigned_read_url(obj.avatar_key)
        except CloudflareR2Error:
            return None

    def get_post_count(self, obj):
        return obj.posts.count()

    def get_posts(self, obj):
        posts = (
            Post.objects
            .filter(user=obj, parent_post__isnull=True)
            .annotate(
                comment_count=Count("replies", distinct=True),
                like_count=Count("liked_users", distinct=True),
            )
            .order_by("-created_at")
        )
        return PostReadSerializer(posts, many=True, context=self.context).data

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):#入力されたメールアドレスを整形
        return value.lower().strip()

class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    #新しいパスワードと確認用パスワードが一致しているか確認
    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({
                "password_confirm": "パスワードが一致しません。"
            })

        validate_password(attrs["password"])
        return attrs