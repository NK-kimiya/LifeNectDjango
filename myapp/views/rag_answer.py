
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from openai import OpenAI
import pinecone

class RagAnswer(APIView):
    authentication_classes = [] 
    permission_classes = [AllowAny]

    def post(self, request):
        query_text = request.data.get("text", "")
        if not query_text:
            return Response({"error": "text is required"}, status=400)

        # ✅ OpenAI クライアント初期化（Chat形式用）
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        # ✅ クエリの埋め込みを作成（v3モデル）
        embedding_response = client.embeddings.create(
            input=query_text,
            model="text-embedding-3-small"
        )
        embedding = embedding_response.data[0].embedding

        # ✅ Pinecone 初期化 & インデックス取得
        pc = pinecone.Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index("my-index")

        # ✅ Pinecone検索 & スコアフィルタ
        query_result = index.query(
            vector=embedding,
            top_k=3,
            include_metadata=True
        )

        filtered_matches = query_result.matches[:3]

        # ✅ メタデータを自然文に変換
        contexts = []
        for match in filtered_matches:
            meta = match.get("metadata", {})
            body = meta.get("text", "[本文なし]")  # ← ここ修正
            contexts.append(f"【本文】{body}")

        context_text = "\n\n".join(contexts)
        print("参考情報" + context_text)

        # ✅ Chat形式用の messages を作成
        messages = [
            {
                "role": "system",
                "content": "あなたは親切なカウンセラーです。質問に対して丁寧な敬語で、分かりやすく回答してください。"
            },
            {
                "role": "user",
                "content": f"""以下の情報を参考に、質問に答えてください。
・まず結論を述べてください。
・必要に応じて箇条書きで整理してください。
・途中で終わらないように、最後までしっかり出力してください。

[質問]
{query_text}

[参考情報]
{context_text}
"""
            }
        ]

        # ✅ Chatモデル（gpt-3.5-turbo）で生成
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # ← Chat形式モデルに変更
            messages=messages,
            max_tokens=1000  # ← トークン数維持
        )

        answer = response.choices[0].message.content.strip()

        return Response({"answer": answer}, status=200)