from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.conf import settings
from google.oauth2 import id_token
from django.contrib.auth import get_user_model
from myapp.serializers.user import RegisterResponseSerializer, RegisterSerializer
from rest_framework.views import APIView
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

User = get_user_model()
class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        response_serializer = RegisterResponseSerializer(user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    

class GoogleAuthView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        credential = request.data.get("credential")

        if not credential:
            return Response(
                {"detail": "credential is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not settings.GOOGLE_CLIENT_ID:
            return Response(
                {"detail": "GOOGLE_CLIENT_ID is not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            #tokenはGoogleが発行したものなのか確認
            payload = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except ValueError:
            return Response(
                {"detail": "Invalid Google token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = payload.get("email")
        email_verified = payload.get("email_verified")
        google_sub = payload.get("sub")
        nickname = payload.get("name") or email.split("@")[0]

        #メールがないか未確認、subがない場合
        if not email or not email_verified or not google_sub:
            return Response(
                {"detail": "Google account information is invalid"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        #google_sub で既存ユーザーを探す
        user = User.objects.filter(google_sub=google_sub).first()
        created = False

        if user:
            pass
        else:
            
            user = User.objects.filter(email=email).first()
            
            #すでに通常のメール/パスワード登録で同じメールアドレスのユーザーがいる場合
            if user:
                #そのメールアドレスのユーザーに、すでに別の google_sub が登録されていたら
                if user.google_sub and user.google_sub != google_sub:
                    return Response(
                        {"detail": "This email is already linked to another Google account"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                #問題なければ、既存ユーザーに Google 情報を保存
                user.google_sub = google_sub
                user.provider = "google"
                user.save(update_fields=["google_sub", "provider"])
            else:
                #ユーザーが存在しなければ新規作成
                user = User.objects.create_user(
                    email=email,
                    nickname=nickname,
                    password=None,
                    provider="google",
                    google_sub=google_sub,
                )
                created = True

        #自分のアプリ用のJWTを発行
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "id": user.id,
                "email": user.email,
                "nickname": user.nickname,
                "role": user.role,
                "provider": user.provider,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class AdminLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"detail": "email and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=email, password=password)

        if not user:
            return Response(
                {"detail": "Invalid email or password"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.role != User.Role.ADMIN and not user.is_staff:
            return Response(
                {"detail": "Admin permission is required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "id": user.id,
                "email": user.email,
                "nickname": user.nickname,
                "role": user.role,
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )
