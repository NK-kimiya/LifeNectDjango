from django.db import models
from cloudinary.models import CloudinaryField
from django.contrib.auth.models import AbstractUser, BaseUserManager
import uuid

class UserManager(BaseUserManager):
    def create_user(self, email, nickname, password=None, **extra_fields):
        if not email:
            raise ValueError("メールアドレスは必須です")

        email = self.normalize_email(email)
        user = self.model(email=email, nickname=nickname, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, nickname, password=None, **extra_fields):
        extra_fields.setdefault("role", User.Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(email, nickname, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理者"
        USER = "user", "ユーザー"
    provider = models.CharField(max_length=20, default="email")
    google_sub = models.CharField(max_length=255, blank=True, null=True, unique=True)
    username = None
    email = models.EmailField(unique=True)
    nickname = models.CharField(max_length=50)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.USER,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nickname"]

    objects = UserManager()

    def __str__(self):
        return self.email

class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)  # 重複禁止

    def __str__(self):
        return self.name
    
    
class UploadedFile(models.Model):
    file =  CloudinaryField('image', blank=True, null=True) # 保存先: MEDIA_ROOT/uploads/
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.url if self.file else "No file"

class Post(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    title = models.CharField(max_length=200)
    comment = models.TextField()
    image_url = models.URLField(blank=True, null=True)
    parent_post = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="replies",
    )
    tags = models.ManyToManyField(
        Tag,
        related_name="posts",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title