# myapp/views/articles.py
from myapp.models import BlogArticle
from myapp.permissions import IsAdminOrReadOnly
from myapp.views.base import BaseModelViewSet
from rest_framework import viewsets
from bs4 import BeautifulSoup 
import re
from openai import OpenAI
from django.conf import settings
from pinecone import Pinecone
from rest_framework.response import Response
from rest_framework import status

from ..serializers import (
    TagSerializer,
    UploadedFileReadSerializer, UploadedFileWriteSerializer,
    BlogArticleReadSerializer, BlogArticleWriteSerializer,
)


# BlogArticleViewSet に追加
class BlogArticleViewSet(BaseModelViewSet):
    queryset = BlogArticle.objects.all().order_by("-created_at")
    permission_classes = [IsAdminOrReadOnly]
    
    
    def create(self, request, *args, **kwargs):
       body = request.data.get("body", "")
       text_only = BeautifulSoup(body, "html.parser").get_text()
       cleaned_text = re.sub(r"\s+", " ", text_only).strip()
       
       response = super().create(request, *args, **kwargs)
       article_id = response.data.get("id")
       
       chunks = chunk_text(cleaned_text, chunk_size=200, overlap=50)
       client = OpenAI(api_key=settings.OPENAI_API_KEY)
       pc = Pinecone(api_key=settings.PINECONE_API_KEY)
       index = pc.Index("my-index")
       
       for i, chunk in enumerate(chunks):
            emb = client.embeddings.create(
                input=chunk,
                model="text-embedding-3-small"
            )
            vector = emb.data[0].embedding

            index.upsert(vectors=[{
                "id": f"{article_id}-{i}",  # ← "記事ID-チャンク番号"
                "values": vector,
                "metadata": {"text": chunk}
            }])

       return response
   
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        article_id = instance.id  # ← DB上のIDを取得

        # Pinecone クライアント初期化
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index("my-index")

        # 🔹 まず対象記事に対応する全チャンクを削除する
        # ここでは便宜上 0〜99 までを削除対象とする（必要に応じて上限を決める）
        ids_to_delete = [f"{article_id}-{i}" for i in range(100)]
        index.delete(ids=ids_to_delete)

        # 🔹 DBから記事を削除
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return BlogArticleWriteSerializer
        return BlogArticleReadSerializer
    
def chunk_text(text: str, chunk_size: int = 200, overlap: int = 50) -> list[str]:
    """
    文字列を chunk_size ごとに分割し、overlap だけ重複を持たせる。
    末尾の余りがあれば最後の chunk_size 分を追加する。
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)

        if end >= text_length:
            break

        start = end - overlap  # overlap 分戻って次のチャンク開始

    return chunks
