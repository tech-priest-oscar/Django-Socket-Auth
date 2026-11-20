from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from accounts.custom_functions import decodeJWT


class IsAuthenticatedCustom(BasePermission):
    def has_permission(self, request, view):
        http_auth = request.headers.get("authorization")
        if not http_auth:
            raise AuthenticationFailed("Auth token not provided!")
        try:
            user = decodeJWT(http_auth)
        except Exception as err:
            raise AuthenticationFailed("Auth token invalid or expired!") from err

        if not user:
            raise AuthenticationFailed("Auth token invalid or expired!")
        request.user = user
        if request.user and request.user.is_authenticated:
            return True
        return False
