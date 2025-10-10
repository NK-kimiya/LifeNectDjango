from django.db import models
from cloudinary.models import CloudinaryField

class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)  # 重複禁止

    def __str__(self):
        return self.name
    
    
class UploadedFile(models.Model):
    file =  CloudinaryField('image', blank=True, null=True) # 保存先: MEDIA_ROOT/uploads/
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.url if self.file else "No file"

class BlogArticle(models.Model):
    title = models.CharField(max_length=200)
    eyecatch = models.URLField(blank=True, null=True)  # アイキャッチ画像URL
    body = models.TextField()
    tags = models.ManyToManyField(Tag, related_name="articles", blank=True)  # 複数タグ
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title
    
class ChatLog(models.Model):
    question = models.TextField(verbose_name="質問文")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.question}"