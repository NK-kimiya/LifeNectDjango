# myapp/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MeView,UploadedFileViewSet,RagAnswer
from .views.tags import TagViewSet
from .views.health import health
from .views.auth import AdminLoginView, RegisterView
router = DefaultRouter()
from .views.auth import GoogleAuthView
from rest_framework_simplejwt.views import TokenObtainPairView
from .views.post import PostViewSet
from .views import UserAvatarUploadUrlView, UserAvatarView
from .views import PostImageUploadUrlView
'''
GET http://localhost:8000/tags/
POST http://localhost:8000/tags/
GET http://localhost:8000/tags/{id}/
PUT http://localhost:8000/tags/{id}/
DELETE http://localhost:8000/tags/{id}/

{
  "name": "Django",
  "description": "Djangoに関する記事タグ"
}
'''
router.register(r"tags", TagViewSet)
router.register(r"files", UploadedFileViewSet)
router.register(r"posts", PostViewSet)


urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/upload-url/", UserAvatarUploadUrlView.as_view(), name="me-avatar-upload-url"),
    path("me/avatar/", UserAvatarView.as_view(), name="me-avatar"),
    path("posts/upload-url/", PostImageUploadUrlView.as_view(), name="post-image-upload-url"),
    path("rag-answer/", RagAnswer.as_view(), name="similar-articles"), 
    path("", include(router.urls)),
    path("health/", health),
    path("auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/admin/login/", AdminLoginView.as_view(), name="admin-login"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/google/", GoogleAuthView.as_view(), name="google-auth"),
]
