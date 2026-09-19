from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from myapp.permissions import IsActiveAccount
from myapp.serializers.user import UserProfileSerializer
from myapp.services.cloudflare_r2 import delete_object, CloudflareR2Error
from rest_framework import status

class MeView(APIView):
    permission_classes = [IsAuthenticated,IsActiveAccount]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    
    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

def delete(self, request):
    user = request.user
    avatar_key = user.avatar_key

    user.delete()

    if avatar_key:
        try:
            delete_object(avatar_key)
        except CloudflareR2Error:
            pass

    return Response(
        {"detail": "アカウントを削除しました。"},
        status=status.HTTP_200_OK,
    )