from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


class GlobalLoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        login_path = reverse("login")
        is_login = request.path == login_path
        if not settings.REQUIRE_LOGIN:
            if is_login:
                return redirect("core:map")
            return self.get_response(request)
        if is_login or request.user.is_authenticated:
            response = self.get_response(request)
        elif request.headers.get("HX-Request") == "true":
            response = HttpResponse(headers={"HX-Redirect": login_path})
        else:
            response = redirect(login_path)
        # Protected files and pages must be checked again after logout.
        response.headers["Cache-Control"] = "private, no-store"
        return response
