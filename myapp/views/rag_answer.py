
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError
import pinecone

from pinecone.core.client.exceptions import UnauthorizedException, PineconeApiException 

class RagAnswer(APIView):
    authentication_classes = [] 
    permission_classes = [AllowAny]

    def post(self, request):
        query_text = request.data.get("text", "")
        if not query_text:
            return Response(
                {"detail": "質問内容が入力されていません。メッセージを入力してください。"},
                status=400
            )

        # ✅ OpenAI クライアント初期化（Chat形式用）
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)

            # ✅ クエリの埋め込みを作成（v3モデル）
            embedding_response = client.embeddings.create(
                input=query_text,
                model="text-embedding-3-small"
            )
            embedding = embedding_response.data[0].embedding
        except AuthenticationError:
            return Response(
                {"detail": "AIサービスに接続できません。ログイン情報を確認してください。"},
                status=401
            )
        except RateLimitError:
            return Response(
                {"detail": "現在、全体の利用量が上限に達したため処理できません。"
                           "復旧対応を行っておりますので、しばらくお待ちください。"},
                status=429
            )
        except APIError:
            return Response(
                {"detail": "AIサービス利用中にエラーが発生しました。時間をおいて再度お試しください。"},
                status=500
            )
        # ✅ Pinecone 初期化 & インデックス取得
        try:
            pc = pinecone.Pinecone(api_key=settings.PINECONE_API_KEY)
            index = pc.Index("my-index")

            # ✅ Pinecone検索 & スコアフィルタ
            query_result = index.query(
                vector=embedding,
                top_k=3,
                include_metadata=True
            )
        
        except UnauthorizedException:
            return Response(
                {"detail": "検索サービスに接続できませんでした。再度お試しください。"},
                status=401
            )
        except PineconeApiException:  # ← 修正
            return Response(
                {"detail": "検索サービスで内部エラーが発生しました。時間をおいて再度お試しください。"},
                status=500
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
        
        try:
            # ✅ Chatモデル（gpt-3.5-turbo）で生成
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",  # ← Chat形式モデルに変更
                messages=messages,
                max_tokens=1000  # ← トークン数維持
            )
            print("OpenAI response:", response)
        
            answer = response.choices[0].message.content.strip()
       
        except AuthenticationError:
            return Response(
                {"detail": "AIサービスに接続できませんでした。時間をおいて再度お試しください。"},
                status=401
            )
        except RateLimitError:
            return Response(
                {"detail": "現在、利用が集中しています。しばらくお待ちください。"},
                status=429
            )
        except APIError:
            return Response(
                {"detail": "回答生成中にエラーが発生しました。時間をおいて再度お試しください。"},
                status=500
            )
        except Exception as e:
            return Response(
                {"detail": f"予期しないエラーが発生しました: {str(e)}"},
                status=500
            )

        return Response({"answer": answer}, status=200)