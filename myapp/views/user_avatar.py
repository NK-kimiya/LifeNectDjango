from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from myapp.serializers.user import UserAvatarUpdateSerializer
from myapp.services.cloudflare_r2 import (
    CloudflareR2Error,
    delete_object,
    generate_avatar_key,
    generate_presigned_upload_url,
)


class UserAvatarUploadUrlView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        content_type = request.data.get("content_type")

        if not content_type:
            return Response(
                {"detail": "content_type is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            key = generate_avatar_key(request.user.id, content_type)
            upload_url = generate_presigned_upload_url(key, content_type)
        except CloudflareR2Error as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "avatar_key": key,
                "upload_url": upload_url,
                "content_type": content_type,
            },
            status=status.HTTP_200_OK,
        )


class UserAvatarView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        old_avatar_key = request.user.avatar_key

        serializer = UserAvatarUpdateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        if old_avatar_key and old_avatar_key != user.avatar_key:
            try:
                delete_object(old_avatar_key)
            except CloudflareR2Error:
                pass

        return Response(
            {
                "id": user.id,
                "avatar_key": user.avatar_key,
                "avatar_content_type": user.avatar_content_type,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request):
        old_avatar_key = request.user.avatar_key

        if old_avatar_key:
            try:
                delete_object(old_avatar_key)
            except CloudflareR2Error:
                return Response(
                    {"detail": "Failed to delete avatar."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        request.user.avatar_key = None
        request.user.avatar_content_type = None
        request.user.save(
            update_fields=[
                "avatar_key",
                "avatar_content_type",
            ]
        )

        return Response(status=status.HTTP_204_NO_CONTENT)