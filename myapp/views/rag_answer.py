
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from myapp.models import Post
from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError
import pinecone
from typing import Any, Dict, List

from pinecone.core.client.exceptions import UnauthorizedException, PineconeApiException 

import traceback
import sys

import re
import unicodedata
import json

HIGH_THRESHOLD = 0.5
MID_THRESHOLD = 0.6
LOWER_LIMIT = 0.4

SUICIDE_DETECTION_PROMPT = """
    あなたは安全判定AIです。

    ユーザーの発言が「自殺や自傷行為を示唆しているか」を判定してください。

    重要:
    - 単なるネガティブ感情（つらい、しんどい、疲れた）は検知しない
    - 明確または暗に「死にたい」「消えたい」「生きる意味がない」などの意図がある場合のみ検知する
    - 方法の相談・準備・計画を含む場合は高リスク

    以下のJSON形式で回答してください:

    {
    "suicide_detected": true or false,
    "risk_level": "low" | "medium" | "high",
    "reason": "簡潔な理由"
    }

    ユーザー発言:
    """

client = OpenAI(api_key=settings.OPENAI_API_KEY)

class RagAnswer(APIView):

    def _get_root_post(self, post: Post) -> Post:
        current = post

        while current.parent_post_id:
            current = current.parent_post

        return current

    #function：Post オブジェクトを、フロントに返しやすい JSON 形式の辞書に変換する
    def _serialize_post_reference(self, post: Post, excerpt=None, score=None):
        return {
            #投稿の基本情報
            "id": str(post.id),
            "title": post.title,
            "comment": post.comment,
            "excerpt": excerpt,
            #親投稿と種別を判定
            "parent_post": str(post.parent_post_id) if post.parent_post_id else None,
            "type": "reply" if post.parent_post_id else "post",
            #返信数と作成日時を入れる部分
            "comment_count": post.replies.count(),
            "created_at": post.created_at.isoformat(),
            #投稿者情報
            "user": {
                "id": post.user.id,
                "nickname": post.user.nickname,
                "email": post.user.email,
            } if post.user else None,
            "score": score,
            #タグ一覧を入れる部分
            "tags": [
                {
                    "id": tag.id,
                    "name": tag.name,
                }
                for tag in post.tags.all()
            ],
        }
 

    def detect_suicide_with_llm(self,user_input: str):
        prompt = SUICIDE_DETECTION_PROMPT + user_input

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 軽量でOK
            messages=[
                {"role": "system", "content": "あなたは安全判定AIです"},
                {"role": "user", "content": prompt}
            ],
            temperature=0  # 判定なのでブレさせない
        )

        content = response.choices[0].message.content

        try:
            content = re.sub(r"```json|```", "", content).strip()
            result = json.loads(content)
            return result
        except:
            # フォールバック（失敗時は安全側に倒す）
            return {
                "suicide_detected": False,
                "risk_level": "low"
            }
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
                model="gpt-4o-mini",  # 既存のChatモデルに合わせる
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

        
        pc = pinecone.Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(settings.PINECONE_INDEX_NAME)
            
        query_vec = self._embed(client, query_text)
        matches = self._search_pinecone(index, query_vec, top_k=5) 

        
        filtered_matches = [
            m for m in matches
            if m.get("score", 0.0) >= HIGH_THRESHOLD  # ← 0.5以上
        ]

        context_text = "\n\n".join(
            m.get("metadata", {}).get("text", "")
            for m in filtered_matches
            if m.get("metadata", {}).get("text")
        )
        
        use_context = bool(context_text.strip())

        for m in filtered_matches:
            print("score:", m.get("score"), "title:", m.get("metadata", {}).get("title"))

        print("取得件数:", len(matches))
        print("使用件数（0.5以上）:", len(filtered_matches))

        
        for m in filtered_matches:
            print("score:", m.get("score"), "title:", m.get("metadata", {}).get("title"))
        reference_candidates = [
            {
                "post_id": m.get("metadata", {}).get("post_id"),
                "title": m.get("metadata", {}).get("title"),
                "excerpt": m.get("metadata", {}).get("text"),
                "parent_post": m.get("metadata", {}).get("parent_post"),
                "type": m.get("metadata", {}).get("type"),
                "score": m.get("score"),
            }
            for m in filtered_matches
            if m.get("metadata", {}).get("post_id")
        ]

        post_ids = []
        for item in reference_candidates:
            if item["post_id"] not in post_ids:
                post_ids.append(item["post_id"])

        posts = Post.objects.filter(id__in=post_ids).select_related("user", "parent_post")
        post_map = {str(post.id): post for post in posts}

        #返却用リストと重複チェック用セットを用意する部分
        references = []
        seen_matched_post_ids = set()

        #検索結果候補を1件ずつ処理
        for item in reference_candidates:
            post_id = item["post_id"]

            #同じ投稿/コメントの重複を除外
            if post_id in seen_matched_post_ids:
                continue

            seen_matched_post_ids.add(post_id)

            #DBから実際の Post を取得
            try:
                matched_post = (
                    Post.objects
                    .select_related("user", "parent_post")
                    .prefetch_related("tags")
                    .get(id=post_id)
                )
            except Post.DoesNotExist:
                continue

            #属している親掲示板を取得
            board_post = self._get_root_post(matched_post)

            #フロントへ返す形に整形して追加
            references.append({
                "matched_message": self._serialize_post_reference(
                    matched_post,
                    excerpt=item["excerpt"],
                    score=item["score"],
                ),
                "board_post": self._serialize_post_reference(
                    board_post,
                    excerpt=None,
                    score=None,
                ),
            })

        
        question_for_answer = query_text
       
        messages = [
                {
                    "role": "system",
                    "content": """
            あなたは安全配慮型AIです。

            以下を必ず実行してください：

            1. 自殺リスクの判定
            2. 問題なければ質問に回答

            出力は必ずJSON:

            {
            "suicide_detected": true/false,
            "risk_level": "low|medium|high",
            "answer": "回答内容"
            }

            ルール:
            - ネガティブ感情だけでは検知しない
            - 自殺意図がある場合のみtrue
            - trueの場合は具体的回答をしない
            
            ルール：
            answerはHTML形式で出力してください。
            以下のルールを守ってください：
            -参考情報があれば、参考情報を優先して回答する。
            - 段落は <p> タグを使う
            - 箇条書きは <ul><li> を使う
            - 改行だけでなく構造化する
            - 危険なタグ（scriptなど）は使わない
            """
                },
                {
                    "role": "user",
                    "content": f"""
            [質問]
            {question_for_answer}

            [参考情報]
            {context_text if use_context else "なし"}
            """
                }
            ]
            
        try:
            print("Sending request to AI service...")
            print(messages)
            response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=1000,
                    response_format={"type": "json_object"}
                )
            
            # JSONパース
            content = response.choices[0].message.content

            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # 念のための保険
                result = {
                    "suicide_detected": False,
                    "risk_level": "low",
                    "answer": "回答の解析に失敗しました。もう一度お試しください。"
                }
                
            except json.JSONDecodeError:
                 result = {
                    "suicide_detected": False,
                    "answer": content   # ←これが重要！！
                }
            
            if result["suicide_detected"]:
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
            answer = result.get("answer", "回答を生成できませんでした。")

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

        return Response({
            "answer": answer,
            "references": references,
        }, status=200)

#https://www.mhlw.go.jp/mamorouyokokoro/ まもろうよ　こころ
#https://www.lifelink.or.jp/inochisos/ #いのちSOS

#厚生労働省：電話相談→https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_tel.html
#厚生労働省：SNS相談→https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_sns.html
#厚生労働省：その他の連絡先→https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/hukushi_kaigo/seikatsuhogo/jisatsu/soudan_sonota.html
