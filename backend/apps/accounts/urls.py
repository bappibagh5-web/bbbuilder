from django.urls import path

from .views import csrf, login_view, logout_view, me

urlpatterns = [
    path("csrf/", csrf, name="auth-csrf"),
    path("login/", login_view, name="auth-login"),
    path("logout/", logout_view, name="auth-logout"),
    path("me/", me, name="auth-me"),
]
