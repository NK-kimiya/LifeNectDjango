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