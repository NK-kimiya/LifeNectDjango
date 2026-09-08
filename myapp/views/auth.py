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
from myapp.models import AccountApplication
from myapp.serializers.user import AccountApplicationSerializer
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from myapp.permissions import IsAdminUserRole
from myapp.serializers.user import AccountApplicationAdminSerializer

User = get_user_model()
class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        email = request.data.get("email")

        approved = AccountApplication.objects.filter(
            email__iexact=email,
            status=AccountApplication.Status.APPROVED,
        ).exists()

        if not approved:
            return Response(
                {"detail": "このメールアドレスはまだ承認されていません。"},
                status=status.HTTP_403_FORBIDDEN,
            )
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

        approved = AccountApplication.objects.filter(
                    email__iexact=email,
                    status=AccountApplication.Status.APPROVED,
                ).exists()
        
        existing_user = User.objects.filter(email__iexact=email).first()
        
        if not existing_user and not approved:
                    return Response(
                        {"detail": "管理者に承認されたメールアドレスのみ登録できます。"},
                        status=status.HTTP_403_FORBIDDEN,
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

class AccountApplicationView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = AccountApplicationSerializer


class AccountApplicationAdminViewSet(viewsets.ModelViewSet):
    queryset = AccountApplication.objects.all().order_by("-created_at")
    serializer_class = AccountApplicationAdminSerializer
    permission_classes = [IsAdminUserRole]
    #許可する HTTP メソッドを制限
    # GET   → 申請一覧・詳細を見る
    # PATCH → 承認・却下など一部更新する
    # HEAD / OPTIONS → API確認用
    http_method_names = ["get", "patch", "head", "options"]

    #個別の申請に対して、approve という追加 API を作成
    @action(detail=True, methods=["patch"], url_path="approve")
    def approve(self, request, pk=None):
        application = self.get_object()#URL の {id} に対応する申請データを1件取得
        application.status = AccountApplication.Status.APPROVED#申請ステータスを 承認済み に変更
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "reviewed_at"])#status と reviewed_at だけを DB に保存

        serializer = self.get_serializer(application)#更新後の申請データを JSON に変換する準備
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="reject")
    def reject(self, request, pk=None):
        application = self.get_object()
        application.status = AccountApplication.Status.REJECTED
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "reviewed_at"])

        serializer = self.get_serializer(application)
        return Response(serializer.data, status=status.HTTP_200_OK)


