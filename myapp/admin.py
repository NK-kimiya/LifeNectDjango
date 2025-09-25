from django.contrib import admin
from .models import Tag,UploadedFile,BlogArticle

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name")  # 一覧画面に表示するフィールド
    search_fields = ("name",)      # 検索ボックスで検索可能にする

@admin.register(UploadedFile)
class UploadAdmin(admin.ModelAdmin):
    list_display = ("id", "file")  # 一覧画面に表示するフィールド
    search_fields = ("id",) 
    
@admin.register(BlogArticle)
class BlogAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "eyecatch", "body", "display_tags", "created_at", "updated_at")  # 一覧画面に表示するフィールド
    search_fields = ("id",)

    def display_tags(self, obj):
        return ", ".join([tag.name for tag in obj.tags.all()])
    display_tags.short_description = "Tags"