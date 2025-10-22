# LifeConnect Backend (Django)

This is the backend API for **LifeConnect**, a web application developed with Django and React.  
It provides RESTful APIs for article management and AI chat (RAG integration).

---

## Requirements
- Python 3.11.3
- Django 5.2.6
- pip 22.3.1
- Database: SQLite (default)
- Vector Database: Pinecone
- File Server: Cloudinary
- OS: Windows

---

## 外部サービス

- [OpenAI Platform](https://auth.openai.com/log-in)  
  → OpenAI API key を取得  
- [Pinecone](https://www.pinecone.io/)  
  → Pinecone API key を取得  
- [Cloudinary](https://cloudinary.com/)  
  → Cloud Name / API Key / API Secret を取得  

---

## .envファイルの設定

```env
OPENAI_API_KEY=your_openai_api_key
PINECONE_API_KEY=your_pinecone_api_key

CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_cloudinary_api_key
CLOUDINARY_API_SECRET=your_cloudinary_api_secret

PINECONE_INDEX_NAME=my-index

## Quick Start

# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate    # macOS/Linux
venv\Scripts\activate       # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run migrations
python manage.py migrate

# 4. Start development server
python manage.py runserver

Then open → http://localhost:8000
