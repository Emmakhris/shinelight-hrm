from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view()),
    path("login/", views.LoginView.as_view()),
    path("mfa/setup/", views.MfaSetupView.as_view()),
    path("mfa/sms/", views.MfaSmsView.as_view()),
    path("mfa/verify/", views.MfaVerifyView.as_view()),
    path("refresh/", views.RefreshView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("me/", views.MeView.as_view()),
    path("change-password/", views.ChangePasswordView.as_view()),
    path("password-reset/", views.PasswordResetRequestView.as_view()),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view()),
]
