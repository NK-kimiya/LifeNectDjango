from django.db import models

class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)  # 重複禁止

    def __str__(self):
        return self.name
