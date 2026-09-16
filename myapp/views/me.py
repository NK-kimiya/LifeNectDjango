from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from myapp.permissions import IsActiveAccount
from myapp.serializers.user import UserProfileSerializer


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