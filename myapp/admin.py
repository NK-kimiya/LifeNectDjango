from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, Tag,UploadedFile,Post

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name")  # 一覧画面に表示するフィールド
    search_fields = ("name",)      # 検索ボックスで検索可能にする

@admin.register(UploadedFile)
class UploadAdmin(admin.ModelAdmin):
    list_display = ("id", "file")  # 一覧画面に表示するフィールド
    search_fields = ("id",) 
    
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "user",
        "created_at",
        "updated_at",
        "display_tags",
        "is_visible",
    )

    def display_tags(self, obj):
        return ", ".join(tag.name for tag in obj.tags.all())

    display_tags.short_description = "タグ"
    

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    model = User

    list_display = (
        "id",
        "email",
        "nickname",
        "role",
        "provider",
        "google_sub",
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
        "avatar_key",
  
    )
    list_filter = ("role", "provider","is_staff", "is_superuser", "is_active")
    search_fields = ("email", "nickname","google_sub",)
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("ユーザー情報", {"fields": ("nickname", "first_name", "last_name")}),
        ("プロフィール", {"fields": ("avatar_key",)}),
        (
            "権限",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("重要な日付", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "nickname",
                    "role",
                    "provider",
                    "google_sub",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                    "is_active",
                ),
            },
        ),
    )