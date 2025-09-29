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
from rest_framework.generics import ListAPIView
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny
from ..serializers import (
    TagSerializer,
    UploadedFileReadSerializer, UploadedFileWriteSerializer,
    BlogArticleReadSerializer, BlogArticleWriteSerializer,
)
from myapp.serializers.article import BlogArticleSerializer


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
    
    def update(self, request, *args, **kwargs):
        # 1. 更新対象の記事を取得
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        article_id = serializer.instance.id
        body = serializer.validated_data.get("body", "")

        # 2. 本文をクリーニング
        text_only = BeautifulSoup(body, "html.parser").get_text()
        cleaned_text = re.sub(r"\s+", " ", text_only).strip()

        # 3. Pinecone クライアント準備
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index("my-index")

        # 4. 既存ベクトル削除（記事IDで始まるものを全部消す）
        # namespace を使っていない場合は、チャンク数を保存しておいて range で列挙する方が安全です
        # 簡易的には delete(filter=...) を使う
        index.delete(filter={"article_id": str(article_id)})

        # 5. チャンク化
        chunks = chunk_text(cleaned_text, chunk_size=200, overlap=50)

        # 6. Embedding を作成 & Pinecone に保存
        vectors = []
        for i, chunk in enumerate(chunks):
            emb = client.embeddings.create(input=chunk, model="text-embedding-3-small")
            vectors.append({
                "id": f"{article_id}-{i}",
                "values": emb.data[0].embedding,
                "metadata": {"text": chunk, "article_id": str(article_id)}
            })
        index.upsert(vectors=vectors)

        return Response(serializer.data, status=status.HTTP_200_OK)

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


class BlogArticleFilterView(ListAPIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    serializer_class = BlogArticleSerializer
    filter_backends = [SearchFilter]
    search_fields = ["title", "body"]  # ← キーワード検索対象

    def get_queryset(self):
        queryset = BlogArticle.objects.all()
        tag = self.request.query_params.get("tag")
        if tag:
            queryset = queryset.filter(tags__name=tag)
        return queryset
