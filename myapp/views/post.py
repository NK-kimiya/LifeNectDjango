# # myapp/views/articles.py
# from myapp.models import BlogArticle
# from myapp.permissions import IsAdminOrReadOnly
# from myapp.views.base import BaseModelViewSet
# from rest_framework import viewsets
# from bs4 import BeautifulSoup 
# import re
# from openai import OpenAI
# from django.conf import settings
# from pinecone import Pinecone
# from rest_framework.response import Response
# from rest_framework import status
# from rest_framework.generics import ListAPIView
# from rest_framework.filters import SearchFilter
# from rest_framework.permissions import AllowAny
# from rest_framework_simplejwt.authentication import JWTAuthentication
# from ..serializers import (
#     TagSerializer,
#     UploadedFileReadSerializer, UploadedFileWriteSerializer,
#     BlogArticleReadSerializer, BlogArticleWriteSerializer,
# )
# from myproject.myapp.serializers.post import BlogArticleSerializer
# from openai import AuthenticationError, RateLimitError, APIError, APIError
# from pinecone.core.client.exceptions import UnauthorizedException, PineconeApiException

# # BlogArticleViewSet に追加
# class BlogArticleViewSet(BaseModelViewSet):
#     permission_classes = [IsAdminOrReadOnly]
#     queryset = BlogArticle.objects.all().order_by("-created_at")
    
    
#     def create(self, request, *args, **kwargs):
#        body = request.data.get("body", "")
#        title = request.data.get("title", "")
#        if not body:
#             return Response(
#                 {"detail": "入力内容が空です。メッセージを入力してください。"},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#        text_only = BeautifulSoup(body, "html.parser").get_text()
#        cleaned_text = re.sub(r"\s+", " ", text_only).strip()
       
#        response = super().create(request, *args, **kwargs)
#        article_id = response.data.get("id")
#        try:
#         chunks = chunk_text(cleaned_text, chunk_size=200, overlap=50)
#         client = OpenAI(api_key=settings.OPENAI_API_KEY)
#         pc = Pinecone(api_key=settings.PINECONE_API_KEY)
#         index = pc.Index("my-index")
        
#         for i, chunk in enumerate(chunks):
#                 emb = client.embeddings.create(
#                     input=chunk,
#                     model="text-embedding-3-small"
#                 )
#                 vector = emb.data[0].embedding

#                 index.upsert(vectors=[{
#                     "id": f"{article_id}-{i}",  # ← "記事ID-チャンク番号"
#                     "values": vector,
#                     "metadata": {"text": chunk, "article_id": str(article_id),"title":str(title)}
#                 }])
#        except AuthenticationError:
#         return Response(
#             {"detail": "現在AIサービスに接続できません。時間をおいて再度お試しください。"},
#             status=status.HTTP_401_UNAUTHORIZED
#         )
#        except RateLimitError:
#         return Response(
#             {"detail": "現在、全体の利用量が上限に達したため処理できません。"
#                     "復旧対応を行っておりますので、しばらくお待ちください。"},
#             status=status.HTTP_429_TOO_MANY_REQUESTS
#         )
#        except UnauthorizedException:  # Pinecone 認証エラー
#         return Response(
#             {"detail": "通信エラーが発生しました。時間をおいて再度お試しください。"},
#             status=status.HTTP_401_UNAUTHORIZED
#         )
#        except PineconeApiException:  # ← 修正: ApiException → PineconeApiException
#         return Response(
#             {"detail": "検索サービスで内部エラーが発生しました。改善しない場合はお問い合わせください。"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         ) 
#        except APIError:
#         return Response(
#             {"detail": "AIサービス処理中にエラーが発生しました。時間をおいて再度お試しください。"},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )

#        return response
   
#     def destroy(self, request, *args, **kwargs):
#         instance = self.get_object()
#         article_id = instance.id  # ← DB上のIDを取得

#         # Pinecone クライアント初期化
#         client = OpenAI(api_key=settings.OPENAI_API_KEY)
#         try:
#             pc = Pinecone(api_key=settings.PINECONE_API_KEY)
#             index = pc.Index("my-index")

#             # 🔹 まず対象記事に対応する全チャンクを削除する
#             # ここでは便宜上 0〜99 までを削除対象とする（必要に応じて上限を決める）
#             index.delete(filter={"article_id": str(article_id)})
#         except Exception as e:
#             return Response({"detail": f"予期しないエラーが発生しました。改善しない場合はお問い合わせください。"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#         # 🔹 DBから記事を削除
#         self.perform_destroy(instance)
#         return Response(status=status.HTTP_204_NO_CONTENT)
    
#     def update(self, request, *args, **kwargs):
#         # 1. 更新対象の記事を取得
#         partial = kwargs.pop("partial", False)
#         instance = self.get_object()
#         serializer = self.get_serializer(instance, data=request.data, partial=partial)
#         serializer.is_valid(raise_exception=True)
#         self.perform_update(serializer)

#         article_id = serializer.instance.id
#         body = serializer.validated_data.get("body", "")
#         title = serializer.validated_data.get("title", "")
#         print("記事タイトルの更新は" + title)
#         if not body:
#             return Response({"detail": "body が空です"}, status=status.HTTP_400_BAD_REQUEST)
#         # 2. 本文をクリーニング
#         text_only = BeautifulSoup(body, "html.parser").get_text()
#         cleaned_text = re.sub(r"\s+", " ", text_only).strip()

#         # 3. Pinecone クライアント準備
#         try:
#             client = OpenAI(api_key=settings.OPENAI_API_KEY)
#             pc = Pinecone(api_key=settings.PINECONE_API_KEY)
#             index = pc.Index("my-index")

#             # 4. 既存ベクトル削除（記事IDで始まるものを全部消す）
#             # namespace を使っていない場合は、チャンク数を保存しておいて range で列挙する方が安全です
#             # 簡易的には delete(filter=...) を使う
#             index.delete(filter={"article_id": str(article_id)})

#             # 5. チャンク化
#             chunks = chunk_text(cleaned_text, chunk_size=200, overlap=50)

#             # 6. Embedding を作成 & Pinecone に保存
#             vectors = []
#             for i, chunk in enumerate(chunks):
#                 emb = client.embeddings.create(input=chunk, model="text-embedding-3-small")
#                 vectors.append({
#                     "id": f"{article_id}-{i}",
#                     "values": emb.data[0].embedding,
#                     "metadata": {"text": chunk, "article_id": str(article_id),"title":str(title)}
#                 })
#             index.upsert(vectors=vectors)
#         except Exception as e:  # 🔽 修正: 例外キャッチ
#             return Response({"detail": f"予期しないエラーが発生しました。改善しない場合はお問い合わせください。"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#         return Response(serializer.data, status=status.HTTP_200_OK)

#     def get_serializer_class(self):
#         if self.action in ["create", "update", "partial_update"]:
#             return BlogArticleWriteSerializer
#         return BlogArticleReadSerializer
    
# def chunk_text(text: str, chunk_size: int = 200, overlap: int = 50) -> list[str]:
#     """
#     文字列を chunk_size ごとに分割し、overlap だけ重複を持たせる。
#     末尾の余りがあれば最後の chunk_size 分を追加する。
#     """
#     chunks = []
#     start = 0
#     text_length = len(text)

#     while start < text_length:
#         end = start + chunk_size
#         chunk = text[start:end]
#         chunks.append(chunk)

#         if end >= text_length:
#             break

#         start = end - overlap  # overlap 分戻って次のチャンク開始

#     return chunks


# class BlogArticleFilterView(ListAPIView):
#     authentication_classes = ()
#     permission_classes = (AllowAny,)
#     serializer_class = BlogArticleSerializer
#     filter_backends = [SearchFilter]
#     search_fields = ["title", "body"]  # ← キーワード検索対象

#     def get_queryset(self):
#         queryset = BlogArticle.objects.all()
#         tag = self.request.query_params.get("tag")
#         if tag:
#             queryset = queryset.filter(tags__name=tag)
#         return queryset


from bs4 import BeautifulSoup
import re

from django.conf import settings
from openai import OpenAI, AuthenticationError, RateLimitError, APIError
from pinecone import Pinecone
from pinecone.core.client.exceptions import UnauthorizedException, PineconeApiException

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
class PostViewSet(BaseModelViewSet):
    #permission_classes = [IsAdminOrReadOnly]
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
                    "metadata": {#ベクトルに付ける追加情報
                        "text": chunk,#このベクトルの元になった本文チャンク
                        "post_id": str(post_id),#このベクトルがどの投稿に紐づくかを保存
                        "title": str(title),#投稿タイトルをメタデータとして保存
                    },
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

        try:
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)#Pineconeクライアントを作成
            index = pc.Index("my-index")#my-indexを取得
            index.delete(filter={"post_id": str(post_id)})#inecone 内のデータを削除
        except Exception:
            return Response(
                {"detail": "削除処理中にエラーが発生しました。"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        self.perform_destroy(instance)#Django側のDBから、対象の投稿オブジェクトを削除
        return Response(status=status.HTTP_204_NO_CONTENT)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)#部分更新かどうかを取得:PATCH→TRUE、PUT→False
        instance = self.get_object()#更新対象の投稿データを取得

        serializer = self.get_serializer(#Selializerのインスタンスを返す
            instance,#現在の投稿データを serializer に渡す
            data=request.data,#送信データ
            partial=partial,#部分更新を許可するかどうかを指定
        )
        serializer.is_valid(raise_exception=True)#送られてきたデータが正しいかチェック
        self.perform_update(serializer)#DB上の投稿データを更新

        #更新後のID、コメント、タイトルを取得
        post_id = serializer.instance.id
        comment = serializer.validated_data.get("comment", instance.comment)
        title = serializer.validated_data.get("title", instance.title)

        #コメントが空だった場合の、処理
        if not comment:
            return Response(
                {"detail": "comment が空です。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        text_only = BeautifulSoup(comment, "html.parser").get_text()#コメントをテキスト本文のみにする
        cleaned_text = re.sub(r"\s+", " ", text_only).strip()#余分な空白や改行を整理

        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            pc = Pinecone(api_key=settings.PINECONE_API_KEY)
            index = pc.Index("my-index")

            index.delete(filter={"post_id": str(post_id)})#Pinecone にある古いベクトルデータを削除

            chunks = chunk_text(cleaned_text, chunk_size=200, overlap=50)#投稿文からチャンクを作成

            vectors = []
            for i, chunk in enumerate(chunks):
                emb = client.embeddings.create(#文章のベクトル化
                    input=chunk,
                    model="text-embedding-3-small",
                )
                vectors.append({
                    "id": f"{post_id}-{i}",
                    "values": emb.data[0].embedding,
                    "metadata": {
                        "text": chunk,
                        "post_id": str(post_id),
                        "title": str(title),
                    },
                })

            index.upsert(vectors=vectors)#作成したベクトルデータを Pinecone に登録

        except Exception:
            return Response(
                {"detail": "更新処理中にエラーが発生しました。"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return PostWriteSerializer
        return PostReadSerializer


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




