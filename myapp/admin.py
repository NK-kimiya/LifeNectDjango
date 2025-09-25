from django.contrib import admin
from .models import Tag

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name")  # 一覧画面に表示するフィールド
    search_fields = ("name",)      # 検索ボックスで検索可能にする
