
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

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        OpenAI.api_key = settings.OPENAI_API_KEY
        response = client.embeddings.create(
            input=query_text,
            model="text-embedding-3-small"
        )
        embedding = response.data[0].embedding

        # Pineconeへクエリ（すでに初期化済みと仮定）
        pc = pinecone.Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index("my-index")

        query_result = index.query(
            vector=embedding,
            top_k=3,
            include_metadata=True
        )

        results = [
            {
                "id": match["id"],
                "score": match["score"],
                "metadata": match.get("metadata", {})
            }
            for match in query_result["matches"]
        ]
        
        prompt = f'''以下の質問に以下の情報をベースにして敬語で答えて下さい。なお、回答は最後まで出力してください。途中で終わらないようにしてください。
        [ユーザーの質問]
        {query_text}

        [情報]
        {results}
        '''
        
        print(prompt)
        response = client.completions.create(
            model="gpt-3.5-turbo-instruct",
            prompt=prompt,
            max_tokens=800
        )
        answer = response.choices[0].text

        return Response({"answer": answer}, status=200)