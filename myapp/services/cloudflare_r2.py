import os
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from django.conf import settings


ALLOWED_POST_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

ALLOWED_AVATAR_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


#R2 専用エラークラス
class CloudflareR2Error(Exception):
    pass

#投稿画像のMIMEタイプを検証
def validate_post_image_content_type(content_type: str) -> str:
    if content_type not in ALLOWED_POST_IMAGE_CONTENT_TYPES:
        raise CloudflareR2Error("Unsupported post image content type.")

    return ALLOWED_POST_IMAGE_CONTENT_TYPES[content_type]

#投稿画像用のR2キーを生成
def generate_post_image_key(user_id: int, content_type: str) -> str:
    extension = validate_post_image_content_type(content_type)
    filename = f"{uuid.uuid4()}{extension}"

    return f"posts/users/{user_id}/images/{filename}"

#R2 クライアント作成ブロック
def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.CLOUDFLARE_R2_ENDPOINT_URL,
        aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
        region_name=getattr(settings, "CLOUDFLARE_R2_REGION", "auto"),
    )

#画像 MIME type 検証ブロック
def validate_avatar_content_type(content_type: str) -> str:
    if content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
        raise CloudflareR2Error("Unsupported avatar content type.")

    return ALLOWED_AVATAR_CONTENT_TYPES[content_type]

#avatar 用 object key 生成
def generate_avatar_key(user_id: int, content_type: str) -> str:
    '''
    user_id：どのユーザーの画像化を示すかを識別するためのID
    content_type：画像のMIMEタイプ（例："image/jpeg"）
    '''
    extension = validate_avatar_content_type(content_type)
    filename = f"{uuid.uuid4()}{extension}"#例：8d8f1b5c-6c4b-4c33-9b9a-1b4a7c0d5b12.png

    return f"users/{user_id}/avatar/{filename}"

#アップロード用署名 URL 作成
def generate_presigned_upload_url(key: str, content_type: str) -> str:
    '''
    key：R2 に保存するファイルの場所
    content_type：アップロードする画像の種類
    '''
    validate_avatar_content_type(content_type)

    client = get_r2_client()

    try:
        return client.generate_presigned_url(#R2 に対して使える署名付き URL を作成し、その URL を返す
            ClientMethod="put_object",#署名付き URL で許可する操作
            Params={
                "Bucket": settings.CLOUDFLARE_R2_BUCKET_NAME,
                "Key": key,
                # "ContentType": content_type,
            },
            ExpiresIn=settings.CLOUDFLARE_R2_PRESIGNED_URL_EXPIRES,#署名付き URL の有効期限
        )
    except ClientError as exc:#try の中で boto3 / R2 関連のエラーが起きた場合に受け取る
        raise CloudflareR2Error("Failed to generate upload URL.") from exc

#投稿画像用のアップロード署名URL
def generate_post_image_upload_url(user_id: int, content_type: str) -> dict:
    key = generate_post_image_key(user_id, content_type)

    upload_url = generate_presigned_upload_url(
        key=key,
        content_type=content_type,
    )

    return {
        "upload_url": upload_url,
        "image_key": key,
        "content_type": content_type,
        "expires_in": settings.CLOUDFLARE_R2_PRESIGNED_URL_EXPIRES,
    }

#表示用署名 URL 作成
def generate_presigned_read_url(key: str | None) -> str | None:
    if not key:
        return None

    client = get_r2_client()

    try:
        return client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": settings.CLOUDFLARE_R2_BUCKET_NAME,
                "Key": key,
            },
            ExpiresIn=settings.CLOUDFLARE_R2_PRESIGNED_URL_EXPIRES,
        )
    except ClientError as exc:
        raise CloudflareR2Error("Failed to generate read URL.") from exc

#投稿画像用の読み取り署名URL
def generate_post_image_read_url(image_key: str | None) -> str | None:
    return generate_presigned_read_url(image_key)


#R2 オブジェクト削除ブロック
def delete_object(key: str | None) -> None:
    if not key:
        return

    client = get_r2_client()

    try:
        client.delete_object(
            Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME,
            Key=key,
        )
    except ClientError as exc:
        raise CloudflareR2Error("Failed to delete object.") from exc

#投稿画像を削除する
def delete_post_image(image_key: str | None) -> None:
    delete_object(image_key)