from rest_framework import permissions

class IsAdminOrReadOnly(permissions.BasePermission):
    message = "ログインが必要です。"

    def has_permission(self, request, view):
        # 未ログインなら GET も含めてすべて拒否
        if not request.user or not request.user.is_authenticated:
            return False

        # 凍結中・停止中なら拒否
        if (
            getattr(request.user, "account_status", None)
            != request.user.AccountStatus.ACTIVE
        ):
            self.message = "このアカウントは現在凍結中です。"
            return False

        # GET, HEAD, OPTIONS はログイン済みなら許可
        if request.method in permissions.SAFE_METHODS:
            return True

        # POST, PUT, PATCH, DELETE は管理者だけ許可
        return (
            request.user.is_staff
            or getattr(request.user, "role", None) == "admin"
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
