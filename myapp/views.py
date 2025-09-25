from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from django.conf import settings
from rest_framework.permissions import IsAdminUser
from .models import Tag,UploadedFile,BlogArticle
from .serializers import TagSerializer,UploadedFileSerializer,BlogArticleSerializer
from rest_framework import viewsets,permissions
from .exceptions import custom_handle_exception  # 追加
from .permissions import IsAdminOrReadOnly

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)

    ## 埋め込みベクトル化する対象テキストを定義
    text = "この記事の内容..."
    # # OpenAIの埋め込みAPIを呼び出してベクトルを生成
    embedding_vector = client.embeddings.create(
        model="text-embedding-3-small",#使用する埋め込みモデル（1536次元）
        input=text#入力テキストを指定
    ).data[0].embedding# レスポンスから最初のembeddingベクトル（数値配列）を取得

    #既存のPineconeインデックス「my-index」に接続する
    index = pc.Index("my-index")

    #ベクトルをインデックスに保存または更新（upsert = insert or update）
    index.upsert(vectors=[
        ("article-123", embedding_vector, {"text": text})#ID "article-123" に対応するベクトルとメタデータ（text）を登録
    ])

    # 保存状況を確認
    stats = index.describe_index_stats()# インデックスの統計情報を取得（ベクトル件数や次元数など）
    print("Index stats:", stats)# コンソールに統計情報を出力

    # クエリ
    result = index.query(
        vector=embedding_vector,# Pineconeにクエリを投げ、類似ベクトル検索を実行
        top_k=3,# 類似度の高い上位3件を取得
        include_metadata=True# 結果にメタデータ（textなど）も含める
    )
    print("Query result:", result)# 検索結果をコンソールに出力

    user = request.user
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
    })
    
class TagViewSet(viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [IsAdminUser]  # 管理者のみ許可

    def handle_exception(self, exc):
        # 共通の例外処理を利用
        response = custom_handle_exception(exc, context=self)
        if response:
            return response
        return super().handle_exception(exc)

class UploadedFileViewSet(viewsets.ModelViewSet):
    queryset = UploadedFile.objects.all()
    serializer_class = UploadedFileSerializer
    permission_classes = [IsAdminOrReadOnly]
    
    def handle_exception(self, exc):
        # 共通の例外処理を利用
        response = custom_handle_exception(exc, context=self)
        if response:
            return response
        return super().handle_exception(exc)
    

class BlogArticleViewSet(viewsets.ModelViewSet):
    queryset = BlogArticle.objects.all().order_by("-created_at")
    serializer_class = BlogArticleSerializer
    permission_classes = [IsAdminOrReadOnly]