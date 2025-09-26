# myapp/views/tags.py
from myapp.models import Tag
from myapp.permissions import IsAdminOrReadOnly
from myapp.views.base import BaseModelViewSet
from ..serializers import (
    TagSerializer,
)

class TagViewSet(BaseModelViewSet):
    queryset = Tag.objects.all().order_by("id")
    serializer_class = TagSerializer
    permission_classes = [IsAdminOrReadOnly]