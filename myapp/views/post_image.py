from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from myapp.services.cloudflare_r2 import (
    CloudflareR2Error,
    generate_post_image_upload_url,
)


class PostImageUploadUrlView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        content_type = request.data.get("content_type")

        if not content_type:
            return Response(
                {"detail": "content_type is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = generate_post_image_upload_url(
                user_id=request.user.id,
                content_type=content_type,
            )
        except CloudflareR2Error as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(data, status=status.HTTP_200_OK)