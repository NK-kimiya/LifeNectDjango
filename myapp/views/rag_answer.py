
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from myapp.permissions import IsActiveAccount
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

# =========類似度の閾値・安全判定プロンプトの定義==========
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

#==========OpenAIクライアントの初期化==========
client = OpenAI(api_key=settings.OPENAI_API_KEY)

#==========APIViewクラスで、POST /api/rag-answer/ の処理本体を定義==========
class RagAnswer(APIView):
    #返信コメントから一番上の親投稿を探す関数
    def _get_root_post(self, post: Post) -> Post:
        current = post#最初に渡された投稿

        while current.parent_post_id:#その投稿に親投稿がある間
            current = current.parent_post#投稿を親に置き換える

        return current#一番上の親投稿の Post オブジェクト

    #DB上の Post オブジェクトを、フロントに返しやすい辞書データに変換する
    def _serialize_post_reference(self, post: Post, excerpt=None, score=None):
        # post：変換するPostオブジェクト
        # excerpt：検索でヒットした本文の一部
        # score：、Pinecone検索での類似度スコア
        return {
            #投稿の基本情報
            "id": str(post.id),
            "title": post.title,
            "comment": post.comment,
            "excerpt": excerpt,
            "parent_post": str(post.parent_post_id) if post.parent_post_id else None,#親投稿がある場合はそのID、ない場合はNone
            "type": "reply" if post.parent_post_id else "post",
            #返信数と作成日時を入れる部分
            "comment_count": post.replies.count(),#その投稿についている返信数
            "created_at": post.created_at.isoformat(),
            #投稿者情報
            "user": {
                "id": post.user.id,
                "nickname": post.user.nickname,
                "email": post.user.email,
            } if post.user else None,
            "score": score,
            "tags": [#投稿に付いているタグを一覧に変換
                {
                    "id": tag.id,
                    "name": tag.name,
                }
                for tag in post.tags.all()
            ],
        }
 
    #ユーザーの入力文を OpenAI に渡して、自傷・自殺リスクがあるかを判定
    def detect_suicide_with_llm(self,user_input: str):
        prompt = SUICIDE_DETECTION_PROMPT + user_input#用意された判定用プロンプト + ユーザーの入力文

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 軽量でOK
            messages=[
                {"role": "system", "content": "あなたは安全判定AIです"},
                {"role": "user", "content": prompt}
            ],
            temperature=0  # 判定なのでブレさせない
        )

        content = response.choices[0].message.content#OpenAIからの回答本文

        try:
            #AI が返した JSON 文字列から、余計な ```json などを取り除き、Python の辞書型に変換
            content = re.sub(r"```json|```", "", content).strip()
            result = json.loads(content)
            return result
        except:
            # フォールバック（失敗時は安全側に倒す）
            return {
                "suicide_detected": False,
                "risk_level": "low"
            }
    permission_classes = [IsAuthenticated, IsActiveAccount]
    
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

    #入力文を整える
    def _normalize_for_keyword_check(self, text: str) -> str:
        if not text:#文字が空なら空文字 ""
            return ""
        text = unicodedata.normalize("NFKC", text)#全角・半角などの表記ゆれをそろえる
        text = text.lower()
        text = re.sub(r"\s+", "", text)#空白や改行を削除
        text = re.sub(r"[、。.,!！?？・/／~〜\-ー_=+「」『』（）()［］\[\]【】<>＜＞\"'`:;]", "", text)#記号を削除
        return text#戻り値の型は str
    
    #入力に自傷・自殺りすくがあるかキーワードが含まれているかを判定
    def _detect_suicide_risk(self, text: str) -> dict:
        normalized = self._normalize_for_keyword_check(text)#入力文をキーワード判定しやすい形に整形

        matched_high = [#入力文に含まれている危険度がハイリスクのキーワードを探す
            kw for kw in self.SUICIDE_HIGH_RISK_KEYWORDS
            if self._normalize_for_keyword_check(kw) in normalized
        ]

        matched_caution = [#入力文に含まれている危険度が中リスクのキーワードを探す
            kw for kw in self.SUICIDE_CAUTION_KEYWORDS
            if self._normalize_for_keyword_check(kw) in normalized
        ]

        if matched_high:#危険度の高いキーワードが見つかった場合
            return {
                "is_suicide_risk": True,#リスクがある
                "risk_level": "high",#危険度high
                "matched_keywords": matched_high,#一致したキーワードを返す
            }

        if matched_caution:#危険度の中リスクのキーワードが見つかった場合
            return {
                "is_suicide_risk": True,#リスクがある
                "risk_level": "caution",#危険度caution
                "matched_keywords": matched_caution,#一致したキーワードを返す
            }

        return {#どちらも見つからなかった場合：
            "is_suicide_risk": False,
            "risk_level": None,
            "matched_keywords": [],
        }

    #受け取った値を True / False に変換する
    def _to_bool(self, v: Any) -> bool:
        if isinstance(v, bool):#値がブール型の場合
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")#整えた文字が、"true"、"1"、"yes" のどれかなら True
        return False

    #ユーザーの質問文を OpenAI に渡して、誤字や表記ゆれを整える
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
                max_tokens=200,#返答の最大長を制限
            )
            corrected = resp.choices[0].message.content.strip()
            return corrected if corrected else text
        except Exception:
            return text

    #文章をベクトルに変換
    def _embed(self, client: OpenAI, text: str) -> List[float]:
        emb = client.embeddings.create(#OpenAI の Embeddings API を呼び出して、text を数値の配列に変換
            model="text-embedding-3-small",  
            input=text
        )
        return emb.data[0].embedding

    #Pinecone にベクトル検索を投げて、質問に近い投稿を取得する
    def _search_pinecone(self, index, vec: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        res = index.query(vector=vec, top_k=top_k, include_metadata=True)#vecに近いデータを上位5件、メタデータ込みで取得
        return res.get("matches", getattr(res, "matches", [])) or []#検索結果からmachesを取り出す(辞書のリスト)


    #質問を受け取り、安全確認する
    def post(self, request):
        #質問を受け取る範囲
        query_text: str = request.data.get("text", "") or request.data.get("query", "")#質問文を取得。textがなければqueryを使う
        allow_save: bool = self._to_bool(request.data.get("allowSave"))#allowSave の値を True / False に変換
        if not query_text:#質問が空か確認する範囲
            return Response(
                {"detail": "質問内容が入力されていません。メッセージを入力してください。"},
                status=400
            )
        suicide_result = self._detect_suicide_risk(query_text)#質問文に危険なキーワードが含まれていないかをチェック
        if suicide_result["is_suicide_risk"]:#リスクがあれば安全用レスポンスを返す範囲
            
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
            
        # {2. Pineconeで関連投稿を探し、参考情報を作る}

    
        pc = pinecone.Pinecone(api_key=settings.PINECONE_API_KEY)#Pineconeに接続
        index = pc.Index(settings.PINECONE_INDEX_NAME)#検索対象のインデックスを取得

        query_vec = self._embed(client, query_text)#ユーザーの質問文を数値ベクトルに変換
        matches = self._search_pinecone(index, query_vec, top_k=5)#質問ベクトルに近い投稿を、Pinecone から最大5件取得

        filtered_matches = [#検索結果の中から、scoreがHIGH_THRESHOLD以上のものだけ残す
            m for m in matches
            if m.get("score", 0.0) >= LOWER_LIMIT  # ← 0.5以上
        ]

        context_text = "\n\n".join(#採用された検索結果の metadata.text を取り出して、1つの長い文章に→"\n\n".join(["文章A", "文章B", "文章C"])
            m.get("metadata", {}).get("text", "")#検索結果mから本文を取り出す
            for m in filtered_matches#filtered_matches の中身を1件ずつ取り出
            if m.get("metadata", {}).get("text")#metadata.text が存在していて、空ではない場合だけ対象
        )
        
        use_context = bool(context_text.strip())#context_text に中身があれば True、空なら False


        for m in filtered_matches:#検索結果のスコアやタイトル、取得件数をコンソールに表示
            print("score:", m.get("score"), "title:", m.get("metadata", {}).get("title"))
        print("取得件数:", len(matches))
        print("使用件数（0.5以上）:", len(filtered_matches))
        reference_candidates = [ #検索結果から必要なメタデータを抽出
            {
                "post_id": m.get("metadata", {}).get("post_id"),
                "title": m.get("metadata", {}).get("title"),
                "excerpt": m.get("metadata", {}).get("text"),
                "parent_post": m.get("metadata", {}).get("parent_post"),
                "type": m.get("metadata", {}).get("type"),
                "score": m.get("score"),
            }
            for m in filtered_matches#filtered_matches の中から
            if m.get("metadata", {}).get("post_id")#post_id が存在していて、空ではない場合だけ対象
        ]

        post_ids = []#参照投稿のIDを格納するリスト
        for item in reference_candidates:
            if item["post_id"] not in post_ids:#参照候補の中から投稿IDの重複を除いて、post_idsに追加
                post_ids.append(item["post_id"])

        posts = Post.objects.filter(id__in=post_ids).select_related("user", "parent_post")#post_ids に含まれる投稿をDBから取得し、紐づくuserとparent_postも同時に取得
        post_map = {str(post.id): post for post in posts}
        references = []#最終的にフロントへ返す参照投稿リスト
        seen_matched_post_ids = set()#同じ投稿を重複して追加しないための集合

        for item in reference_candidates:#reference_candidates の中から1件ずつ
            print("取り出すIDは" + str(item["post_id"]))
            post_id = item["post_id"]
            if post_id in seen_matched_post_ids:
                continue#すでに処理済みの投稿IDなら、重複して追加しないようにスキップ

            seen_matched_post_ids.add(post_id)#初めて出てきた投稿IDなら、配列に追加

            try:
                matched_post = (#post_id を使って、実際の Post オブジェクトをDBから取得
                    Post.objects
                    .select_related("user", "parent_post")
                    .prefetch_related("tags")
                    .get(id=post_id)
                )
            except Post.DoesNotExist:#投稿が存在しなければスキップ
                continue

            board_post = self._get_root_post(matched_post)#ヒットした投稿が返信だった場合、親をたどって一番上の投稿を取得

            references.append({
                "matched_message": self._serialize_post_reference(
                    matched_post,#Pinecone検索で実際にヒットした投稿・返信
                    excerpt=item["excerpt"],
                    score=item["score"],
                ),
                "board_post": self._serialize_post_reference(
                    board_post,#その投稿が属する一番上の親投稿
                    excerpt=None,
                    score=None,
                ),
            })


        #{3. OpenAIで回答を作り、結果を返す}
        #OpenAIに渡す質問文を準備する
        question_for_answer = query_text

        #OpenAIに渡すプロンプトを作る
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
            #OpenAI APIを呼び出して回答を作る
            response = client.chat.completions.create(#OpenAIにリクエストを送って、回答を生成
                    model="gpt-4o-mini",
                    messages=messages,
                    max_tokens=1000,#回答の最大長
                    response_format={"type": "json_object"}#回答をJSON形式で返す
                )
            content = response.choices[0].message.content# OpenAIの回答をJSONとして読み取る
            try:
                result = json.loads(content)#content を JSON として解析して、Python の辞書に変換
            except json.JSONDecodeError:#json.loads(content) が失敗したとき
                # 念のための保険
                result = {#代替データを入れる
                    "suicide_detected": False,
                    "risk_level": "low",
                    "answer": "回答の解析に失敗しました。もう一度お試しください。",
                    "answer": content   # ←これが重要！！
                }

            #AI回答内で自傷リスクが出た場合に安全回答へ切り替える
            if result["suicide_detected"]:
                return Response({#dict[str, Any](AIがsucide判定した時の参照例)
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
            answer = result.get("answer", "回答を生成できませんでした。")#通常の回答文を取り出し、参考情報なしの場合は注記を足す
            if not use_context: # 参考情報が使えなかったケースは文末に注意書きを付与
                answer += "この経験の情報は現在不足しています。今後改善に努めてまいります。"

        #OpenAI / Pinecone のエラーを返す
        except AuthenticationError:
            return Response({"detail": "AIサービスに接続できませんでした。時間をおいて再度お試しください。"}, status=401)
        except RateLimitError:
            return Response({"detail": "現在、利用が集中しています。しばらくお待ちください。"}, status=429)
        except APIError:
            traceback.print_exc() 
            return Response({"detail": "回答生成中にエラーが発生しました。時間をおいて再度お試しください。"}, status=500)
        except UnauthorizedException:
            return Response({"detail": "検索サービスに接続できませんでした。再度お試しください。"}, status=401)
        except PineconeApiException:
            return Response({"detail": "検索サービスで内部エラーが発生しました。時間をおいて再度お試しください。"}, status=500)
        
        except Exception as e:#想定外のエラーが起きたときに、エラー内容をレスポンス
            return Response({#dict[str, str]
                "error_type": str(type(e)),           # 発生したエラーの種類を文字列
                "detail": str(e),  #エラーの具体的なメッセージ
                "trace": traceback.format_exc(),      #エラーがどの行で起きたかなど、詳細な traceback 全文
            }, status=500)

        #最終レスポンスを返す範囲
        return Response({#dict[str, Any]
            "answer": answer,#str：AIが生成した回答文
            "references": references,#list型：参考にした投稿情報の一覧(以下のreferencesの具体例を参照)
        }, status=200)



#referencesの具体例
# "references": [
#     {
#       "matched_message": {
#         "id": "30",
#         "title": "夜眠れない悩み",
#         "comment": "最近、夜になると不安で眠れません。",
#         "excerpt": "夜になると不安で眠れません。",
#         "parent_post": "10",
#         "type": "reply",
#         "comment_count": 0,
#         "created_at": "2026-10-02T10:30:00+09:00",
#         "user": {
#           "id": 5,
#           "nickname": "taro",
#           "email": "taro@example.com"
#         },
#         "score": 0.82,
#         "tags": [
#           {
#             "id": 1,
#             "name": "睡眠"
#           }
#         ]
#       },
#       "board_post": {
#         "id": "10",
#         "title": "不安について相談したい",
#         "comment": "最近、不安が強くて困っています。",
#         "excerpt": null,
#         "parent_post": null,
#         "type": "post",
#         "comment_count": 3,
#         "created_at": "2026-10-01T20:00:00+09:00",
#         "user": {
#           "id": 2,
#           "nickname": "hanako",
#           "email": "hanako@example.com"
#         },
#         "score": null,
#         "tags": [
#           {
#             "id": 2,
#             "name": "不安"
#           }
#         ]
#       }
#     }
#   ]


#AIが自傷・自殺リスクを検知した場合のレスポンス例
# {
#   "mode": "safety_only",
#   "answer": "大変つらいお気持ちの中で相談してくださりありがとうございます。この内容について、AIでは安全のため具体的なお手伝いができません。一人で抱えず、専門の相談窓口にぜひつながってください。",
#   "primary_support": {
#     "title": "まずはこちらをご覧ください（厚生労働省 公式サイト）",
#     "name": "まもろうよ こころ",
#     "url": "..."
#   },
#   "other_supports": [
#     {
#       "name": "電話相談",
#       "url": "..."
#     },
#     {
#       "name": "SNS相談",
#       "url": "..."
#     },
#     {
#       "name": "その他の相談先",
#       "url": "..."
#     }
#   ],
#   "suicide_detected": true,
#   "risk_level": "high"
# }