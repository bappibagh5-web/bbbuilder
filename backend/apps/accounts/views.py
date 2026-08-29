import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.organizations.services import active_memberships_for_user


def _membership_payload(membership):
    return {
        "id": membership.pk,
        "role": membership.role,
        "organization": {
            "id": membership.organization_id,
            "name": membership.organization.name,
            "slug": membership.organization.slug,
        },
    }


def _user_payload(user):
    return {
        "id": user.pk,
        "email": user.email,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "memberships": [_membership_payload(item) for item in active_memberships_for_user(user)],
    }


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@require_GET
@ensure_csrf_cookie
def csrf(request):
    return JsonResponse({"csrfToken": get_token(request)})


@require_POST
@csrf_protect
def login_view(request):
    payload = _json_body(request)
    if not isinstance(payload, dict):
        return JsonResponse({"detail": "Invalid JSON request."}, status=400)

    email = str(payload.get("email", "")).strip()
    password = payload.get("password")
    if not email or not isinstance(password, str):
        return JsonResponse({"detail": "Email and password are required."}, status=400)

    user = authenticate(request, email=email, password=password)
    if user is None or not user.is_active:
        return JsonResponse({"detail": "Invalid email or password."}, status=401)

    login(request, user)
    return JsonResponse({"user": _user_payload(user)})


@require_POST
@csrf_protect
def logout_view(request):
    logout(request)
    return JsonResponse({"detail": "Logged out."})


@require_GET
def me(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    return JsonResponse({"user": _user_payload(request.user)})
