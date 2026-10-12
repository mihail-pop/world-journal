from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class GlobalLoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        login_path = reverse("login")
        if not settings.REQUIRE_LOGIN:
            if request.path_info == login_path:
                return redirect("core:map")
            return self.get_response(request)
        if request.path_info == login_path or request.user.is_authenticated:
            return self.get_response(request)
        return redirect("login")