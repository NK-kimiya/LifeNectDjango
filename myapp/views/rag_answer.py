
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError
import pinecone
from typing import Any, Dict, List

from pinecone.core.client.exceptions import UnauthorizedException, PineconeApiException 
from myapp.models import ChatLog

import traceback
import sys
class RagAnswer(APIView):
    authentication_classes = [] 
    permission_classes = [AllowAny]
    
    def _to_bool(self, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return False
    
    def _normalize_query(self, client: OpenAI, text: str) -> str:
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "あなたはスペル修正器です。ユーザーの入力の誤字・タイプミス・"
                        "半角/全角の揺れ・不要な空白・表記ゆれを正規化してください。"
                        "固有名詞や専門用語は不確かな場合は変更しないでください。"
                        "出力は修正済みテキストのみを返し、説明は書かないでください。"
                    ),
                },
                {"role": "user", "content": text},
            ]
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",  # 既存のChatモデルに合わせる
                messages=messages,
                temperature=0,
                max_tokens=200,
            )
            corrected = resp.choices[0].message.content.strip()
            return corrected if corrected else text
        except Exception:
            return text
        
    def _embed(self, client: OpenAI, text: str) -> List[float]:
        emb = client.embeddings.create(
            model="text-embedding-3-small",  # 既存に合わせてください
            input=text
        )
        return emb.data[0].embedding
    
    def _search_pinecone(self, index, vec: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        res = index.query(vector=vec, top_k=top_k, include_metadata=True)
        return res.get("matches", getattr(res, "matches", [])) or []

    def post(self, request):
        query_text: str = request.data.get("text", "") or request.data.get("query", "")
        allow_save: bool = self._to_bool(request.data.get("allowSave"))
        
     
        if not query_text:
            return Response(
                {"detail": "質問内容が入力されていません。メッセージを入力してください。"},
                status=400
            )

        # ✅ OpenAI クライアント初期化（Chat形式用）

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        pc = pinecone.Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(settings.PINECONE_INDEX_NAME)
            
        query_vec = self._embed(client, query_text)
        matches = self._search_pinecone(index, query_vec, top_k=5) 
        
        id_title_list = [
        { 
        "id": int(m.get("metadata", {}).get("article_id")) 
              if m.get("metadata", {}).get("article_id") is not None else None,
        "title": m.get("metadata", {}).get("title")
        }
       for m in matches
       if m.get("metadata", {}).get("title") and m.get("metadata", {}).get("article_id")
       ]
        
        unique_titles = {}
        for item in id_title_list:
            title = item["title"]
            if title not in unique_titles:
                unique_titles[title] = item["id"]
        
        unique_id_title_list = [{"title": t, "id": i} for t, i in unique_titles.items()]
        print("全件（重複排除済み）:", unique_id_title_list)
        question_for_answer = query_text
            
        scores = [m.get("score", 0.0) for m in matches]
        max_score = max([m.get("score", 0.0) for m in matches], default=0.0)
            

        context_text = "\n\n".join(
                    m.get("metadata", {}).get("text", "") for m in matches
                    if m.get("metadata", {}).get("text")
        )
        best_match = max(matches, key=lambda m: m.get("score", 0.0))
        top_title = best_match.get("metadata", {}).get("title")
        print("類似度が近い記事のタイトル："+str(top_title))
        use_context = use_context = bool(context_text.strip())
                
        # elif LOWER_LIMIT <= max_score < THRESHOLD:
        #         corrected = self._normalize_query(client, query_text)
        #         print("補正した結果は：" + corrected)
        #         print("補正した結果は："+corrected)
                
        #         original_scores = [m.get("score", 0.0) for m in matches]
        #         print(f"補正前のスコア: {original_scores} (最大: {max_score})")
        #         corrected_vec = self._embed(client, corrected)
        #         matches2 = self._search_pinecone(index, corrected_vec, top_k=5)
                
        #         corrected_scores = [m.get("score", 0.0) for m in matches2]
        #         max_score_corrected = max(corrected_scores) if corrected_scores else 0.0
        #         print(f"補正後のスコア: {corrected_scores} (最大: {max_score_corrected})")
        #         best = [m for m in matches2 if m.get("score", 0.0) >= THRESHOLD]
        #         if best:
        #             context_text = "\n\n".join(
        #                m.get("metadata", {}).get("text", "") for m in best
        #                if m.get("metadata", {}).get("text")
        #             )
        #             question_for_answer = corrected  # ← プロンプトには補正文を使う
        #             use_context = True
        #         else:
        #             print("補正してもダメでした。")
        #             # 補正してもダメ → 許可時のみ保存
        #             if allow_save:
        #                 ChatLog.objects.create(question=query_text, allow_save=True)
        if max_score < 0.5 and allow_save:
                ChatLog.objects.create(question=query_text)
        
        if use_context:
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
        {question_for_answer}

        [参考情報]
        {context_text}
        """
                }
            ]
        else:
            messages = [
                {
                    "role": "system",
                    "content": "あなたは親切なカウンセラーです。質問に対して丁寧な敬語で、分かりやすく回答してください。"
                },
                {
                    "role": "user",
                    "content": f"""質問に答えてください。
        ・まず結論を述べてください。
        ・必要に応じて箇条書きで整理してください。
        ・途中で終わらないように、最後までしっかり出力してください。

        [質問]
        {question_for_answer}
        """
                }
            ]
            

        try:
            response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=1000
                )
            answer = response.choices[0].message.content.strip()

            # 参考情報が使えなかったケースは文末に注意書きを付与（任意）
            if not use_context:
                answer += "この経験の情報は現在不足しています。今後改善に努めてまいります。"

        except AuthenticationError:
            return Response({"detail": "AIサービスに接続できませんでした。時間をおいて再度お試しください。"}, status=401)
        except RateLimitError:
            return Response({"detail": "現在、利用が集中しています。しばらくお待ちください。"}, status=429)
        except APIError:
            return Response({"detail": "回答生成中にエラーが発生しました。時間をおいて再度お試しください。"}, status=500)
        except UnauthorizedException:
            return Response({"detail": "検索サービスに接続できませんでした。再度お試しください。"}, status=401)
        except PineconeApiException:
            return Response({"detail": "検索サービスで内部エラーが発生しました。時間をおいて再度お試しください。"}, status=500)
        
        except Exception as e:
            return Response({
                "error_type": str(type(e)),           # 例: <class 'TypeError'>
                "error_message": str(e),              # 例: can only concatenate str (not "float") to str
                "trace": traceback.format_exc(),      # Traceback全文
            }, status=500)

        return Response({"answer": answer,"article":unique_id_title_list}, status=200)