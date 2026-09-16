from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    message = "このアカウントは現在凍結中です。"
    def has_permission(self, request, view):#ログイン済みユーザーの場合
        if request.user and request.user.is_authenticated:#アカウント状態が activeでない場合
            if (
                getattr(request.user, "account_status", None)
                != request.user.AccountStatus.ACTIVE
            ):
                return False
        if request.method in permissions.SAFE_METHODS:  # GET, HEAD, OPTIONS
            return True
        return (#POST, PUT, PATCH, DELETE は、ログイン済みかつ管理者だけ許可
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or getattr(request.user, "role", None) == "admin")
        )

class IsAdminUserRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (
                request.user.is_staff
                or getattr(request.user, "role", None) == "admin"
            )
        )

class IsActiveAccount(permissions.BasePermission):
    message = "このアカウントは現在凍結中です。"

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:#未ログインユーザーの場合
            return True

        return (#ログイン済みユーザーの場合、account_status が ACTIVE なら許可
            getattr(request.user, "account_status", None)
            == request.user.AccountStatus.ACTIVE
        )
