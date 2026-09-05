from bs4 import BeautifulSoup
import re

from django.conf import settings
from openai import OpenAI, AuthenticationError, RateLimitError, APIError
from pinecone import Pinecone
from pinecone.core.client.exceptions import UnauthorizedException, PineconeApiException
from myapp.pagination import PostPagination

from rest_framework import status
from rest_framework.response import Response
from rest_framework.generics import ListAPIView
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny
from rest_framework.permissions import AllowAny, IsAuthenticated
from myapp.models import Post
from myapp.permissions import IsAdminOrReadOnly
from myapp.views.base import BaseModelViewSet
from django.shortcuts import get_object_or_404
from myapp.serializers.post import (
    PostReadSerializer,
    PostWriteSerializer,
    PostSerializer,
)

from django.db.models import Q,Count
from rest_framework.decorators import action

from myapp.services.cloudflare_r2 import (
    CloudflareR2Error,
    delete_post_image,
)
class PostViewSet(BaseModelViewSet):
    #permission_classes = [IsAdminOrReadOnly]
    pagination_class = PostPagination
    queryset = Post.objects.all().order_by("-created_at")

    
    @action(detail=True, methods=["get"], url_path="replies")
    def replies(self, request, pk=None):
        parent_post = get_object_or_404(Post, pk=pk)

        queryset = (
            Post.objects
            .filter(parent_post=parent_post)
            .annotate(comment_count=Count("replies", distinct=True))
            .order_by("created_at")
        )

        serializer = PostReadSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    def get_queryset(self):
        if self.action in ["retrieve", "update", "partial_update", "destroy", "replies"]:
            return (
                Post.objects
                .all()
                .annotate(comment_count=Count("replies", distinct=True))
                .order_by("-created_at")
            )
        queryset = (
            Post.objects
            .filter(parent_post__isnull=True)
            .annotate(comment_count=Count("replies"))
            .order_by("-created_at")
        )

        keyword = self.request.query_params.get("keyword")
        tag = self.request.query_params.get("tag")

        if keyword:
            queryset = queryset.filter(
                Q(title__icontains=keyword) |
                Q(comment__icontains=keyword)
            )

        if tag:
            queryset = queryset.filter(tags__name=tag)

        return queryset.distinct()

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated()]

        return [IsAdminOrReadOnly()]

    def create(self, request, *args, **kwargs):#postリクエスト時
        comment = request.data.get("comment", "")#リクエストデータから、commentを取得、存在しない場合は空
        title = request.data.get("title", "")#リクエストデータから title を取得

        if not comment:#comment が空かどうかを確認
            return Response(
                {"detail": "コメント文を入力してください。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        text_only = BeautifulSoup(comment, "html.parser").get_text()#commentにHTMLタグが含まれていた場合、取り除いたテキストを取得
        cleaned_text = re.sub(r"\s+", " ", text_only).strip()#改行や連続スペースを削除し、1つの半角スペースにまとめ、前後の空白を削除

        response = super().create(request, *args, **kwargs)#親クラスの通常の作成処理を呼び出す
        post_id = response.data.get("id")#作成された投稿の id をレスポンスデータから取得

        try:
            chunks = chunk_text(cleaned_text, chunk_size=200, overlap=50)#投稿文字を20文字ずつに分割し、前後のチャンクが50文字重なるようにする。
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)#Pinecone を使うためのクライアントを作成
            index = pc.Index("my-index")#Pinecone の my-index というインデックスを指定
            for i, chunk in enumerate(chunks):#分割した本文を1つずつ処理(i は何番目のチャンクか、chunk は分割された本文)
                emb = client.embeddings.create(#OpenAI の Embeddings APIを呼び出す
                    input=chunk,#ベクトル化する対象
                    model="text-embedding-3-small",#使用する埋め込みモデル
                )
                vector = emb.data[0].embedding#OpenAIから返ってきたembeddingベクトル

                index.upsert(vectors=[{#Pinecone にベクトルを保存(同じ場合は、更新)
                    "id": f"{post_id}-{i}",#Pinecone に保存するベクトルの ID
                    "values": vector,#ベクトル本体
                    "metadata": {
                "text": chunk,
                "post_id": str(post_id),
                "title": str(title),
                "type": "reply" if response.data.get("parent_post") else "post",
            }
                }])

        except AuthenticationError:#OpenAI API の認証エラー
            return Response(
                {"detail": "AIサービスに接続できません。時間をおいて再度お試しください。"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except RateLimitError:#OpenAI API の利用制限エラー
            return Response(
                {"detail": "利用上限に達しました。しばらく待ってから再度お試しください。"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except UnauthorizedException:#Pinecone の認証エラー
            return Response(
                {"detail": "検索サービスの認証に失敗しました。"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except PineconeApiException:#Pinecone API 側の一般的なエラー
            return Response(
                {"detail": "検索サービスでエラーが発生しました。"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except APIError:#OpenAI API の一般的なエラー
            return Response(
                {"detail": "AIサービス処理中にエラーが発生しました。"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return response

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()#削除対象のオブジェクトを取得
        post_id = instance.id#取得した投稿オブジェクトのidを取り出す
        image_key = instance.image_key

        try:
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)#Pineconeクライアントを作成
            index = pc.Index("my-index")#my-indexを取得
            index.delete(filter={"post_id": str(post_id)})#inecone 内のデータを削除
        except Exception:
            return Response(
                {"detail": "削除処理中にエラーが発生しました。"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        self.perform_destroy(instance)

        if image_key:
            try:
                delete_post_image(image_key)
            except CloudflareR2Error:
                return Response(
                    {"detail": "Post was deleted, but failed to delete image."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(status=status.HTTP_204_NO_CONTENT)


    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)#部分更新かどうかを取得:PATCH→TRUE、PUT→False
        instance = self.get_object()#更新対象の投稿データを取得
        was_visible = instance.is_visible

        serializer = self.get_serializer(#Selializerのインスタンスを返す
            instance,#現在の投稿データを serializer に渡す
            data=request.data,#送信データ
            partial=partial,#部分更新を許可するかどうかを指定
        )
        serializer.is_valid(raise_exception=True)#送られてきたデータが正しいかチェック
        self.perform_update(serializer)#DB上の投稿データを更新
        post = serializer.instance
        is_visible = post.is_visible
        content_changed = (
            "comment" in serializer.validated_data
            or "title" in serializer.validated_data
        )

        try:
            if was_visible and not is_visible:
                delete_post_vectors(post.id)

            elif not was_visible and is_visible:
                upsert_post_vectors(post)

            elif is_visible and content_changed:
                delete_post_vectors(post.id)
                upsert_post_vectors(post)

        except Exception:
            return Response(
                {"detail": "Pineconeの更新処理に失敗しました。"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(PostReadSerializer(post).data, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PostWriteSerializer
        return PostReadSerializer

def delete_post_vectors(post_id):
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index = pc.Index("my-index")
    index.delete(filter={"post_id": str(post_id)})


def upsert_post_vectors(post):
    text_only = BeautifulSoup(post.comment, "html.parser").get_text()
    cleaned_text = re.sub(r"\s+", " ", text_only).strip()

    if not cleaned_text:
        return

    chunks = chunk_text(cleaned_text, chunk_size=200, overlap=50)

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index = pc.Index("my-index")

    vectors = []
    for i, chunk in enumerate(chunks):
        emb = client.embeddings.create(
            input=chunk,
            model="text-embedding-3-small",
        )

        vectors.append({
            "id": f"{post.id}-{i}",
            "values": emb.data[0].embedding,
            "metadata": {
                "text": chunk,
                "post_id": str(post.id),
                "title": str(post.title),
                "type": "reply" if post.parent_post_id else "post",
            },
        })

    if vectors:
        index.upsert(vectors=vectors)

def chunk_text(text: str, chunk_size: int = 200, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)

        if end >= text_length:
            break

        start = end - overlap

    return chunks


class PostFilterView(ListAPIView):#投稿の絞り込み
    authentication_classes = ()#認証方式を空
    permission_classes = (AllowAny,)
    serializer_class = PostSerializer#
    filter_backends = [SearchFilter]#DRF の検索機能を有効
    search_fields = ["title", "comment"]#検索対象のフィールドを指定

    def get_queryset(self):
        queryset = Post.objects.all()

        tag = self.request.query_params.get("tag")#URLのクエリパラメータから tag を取得
        if tag:
            queryset = queryset.filter(tags__name=tag)#タグ名が tag と一致する投稿だけに絞り込み

        return queryset




