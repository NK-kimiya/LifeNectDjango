from .tag import TagSerializer
from .uploaded_file import UploadedFileReadSerializer, UploadedFileWriteSerializer
from .article import BlogArticleReadSerializer, BlogArticleWriteSerializer

# 既存コードの互換用（list/retrieve で参照される想定）
UploadedFileSerializer = UploadedFileReadSerializer
BlogArticleSerializer = BlogArticleReadSerializer

__all__ = [
    "TagSerializer",
    "UploadedFileReadSerializer",
    "UploadedFileWriteSerializer",
    "BlogArticleReadSerializer",
    "BlogArticleWriteSerializer",
    # 互換
    "UploadedFileSerializer",
    "BlogArticleSerializer",
]
