
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

import re
import unicodedata
class RagAnswer(APIView):
    authentication_classes = [] 
    permission_classes = [AllowAny]
    
    #安全対策のためのキーワードの導入
    SUICIDE_HIGH_RISK_KEYWORDS = [
        "自殺",
        "死にたい",
        "しにたい",
        "消えたい",
        "いなくなりたい",
        "命を絶ちたい",
        "自ら命を絶つ",
        "死ぬ方法",
        "楽に死ねる",
        "確実に死ねる",
        "首を吊る",
        "首つり",
        "飛び降りる",
        "飛び降り",
        "リストカット",
        "od",
        "オーバードーズ",
        "過量服薬",
        "遺書",
    ]

    SUICIDE_CAUTION_KEYWORDS = [
        "生きるのがつらい",
        "生きていたくない",
        "もう無理",
        "死んだほうがまし",
        "消えてしまいたい",
        "つらすぎる",
        "希望がない",
        "限界",
    ]
    
    def _normalize_for_keyword_check(self, text: str) -> str:
        if not text:
            return ""

        # 全角半角ゆれ吸収
        text = unicodedata.normalize("NFKC", text)
        text = text.lower()

        # 空白除去
        text = re.sub(r"\s+", "", text)

        # 記号除去（必要最低限）
        text = re.sub(r"[、。.,!！?？・/／~〜\-ー_=+「」『』（）()［］\[\]【】<>＜＞\"'`:;]", "", text)

        return text
    
    
    def _detect_suicide_risk(self, text: str) -> dict:
        normalized = self._normalize_for_keyword_check(text)

        matched_high = [
            kw for kw in self.SUICIDE_HIGH_RISK_KEYWORDS
            if self._normalize_for_keyword_check(kw) in normalized
        ]

        matched_caution = [
            kw for kw in self.SUICIDE_CAUTION_KEYWORDS
            if self._normalize_for_keyword_check(kw) in normalized
        ]

        if matched_high:
            return {
                "is_suicide_risk": True,
                "risk_level": "high",
                "matched_keywords": matched_high,
            }

        if matched_caution:
            return {
                "is_suicide_risk": True,
                "risk_level": "caution",
                "matched_keywords": matched_caution,
            }

        return {
            "is_suicide_risk": False,
            "risk_level": None,
            "matched_keywords": [],
        }
    
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
            
        # 追加：自殺リスク判定
        suicide_result = self._detect_suicide_risk(query_text)
        
        if suicide_result["is_suicide_risk"]:
            return Response({
                "mode": "safety_only",
                "answer": (
                    "大変つらいお気持ちの中で相談してくださりありがとうございます。"
                    "この内容について、AIでは安全のため具体的なお手伝いができません。"
                    "一人で抱えず、専門の相談窓口にぜひつながってください。"
                ),
                "primary_support": {
                    "title": "まずはこちらをご覧ください（厚生労働省 公式サイト）",
                    "name": "まもろうよ こころ",
                    "url": "https://www.mhlw.go.jp/mamorouyokokoro/"
                },
                "other_supports": [
                    {
                        "name": "電話相談",
                        "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_tel.html"
                    },
                    {
                        "name": "SNS相談",
                        "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_sns.html"
                    },
                    {
                        "name": "その他の相談先",
                        "url": "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_sonota.html"
                    }
                ],
                "suicide_detected": True,
                "risk_level": suicide_result["risk_level"]
            }, status=200)

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

#https://www.mhlw.go.jp/mamorouyokokoro/ まもろうよ　こころ
#https://www.lifelink.or.jp/inochisos/ #いのちSOS

#厚生労働省：電話相談→https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_tel.html
#厚生労働省：SNS相談→https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_sns.html
#厚生労働省：その他の連絡先→https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_sonota.html
