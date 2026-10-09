from django.urls import path, include
from oauth2_provider import views as provider

from . import views
from .oidc import AccountAuthorizationView, AccountTokenView

provider_urls = [
    path('authorize/', AccountAuthorizationView.as_view(), name='authorize'),
    path('token/', AccountTokenView.as_view(), name='token'),
    path('userinfo/', provider.UserInfoView.as_view(), name='user-info'),
    path('.well-known/openid-configuration', provider.ConnectDiscoveryInfoView.as_view(), name='oidc-connect-discovery-info'),
    path('.well-known/jwks.json', provider.JwksInfoView.as_view(), name='jwks-info'),
]

urlpatterns = [
    path('account-api/session/', views.site_session, name='account-site-session'),
    path('account-api/login/', views.site_login, name='account-site-login'),
    path('account-api/callback/', views.site_callback, name='account-site-callback'),
    path('account-api/logout/', views.site_logout, name='account-site-logout'),
    path('accounts/o/', include((provider_urls, 'oauth2_provider'), namespace='oauth2_provider')),
    path('accounts/login/', views.account_login, name='account-login'),
    path('accounts/register/', views.account_register, name='account-register'),
    path('accounts/send-code/', views.account_send_code, name='account-send-code'),
    path('accounts/reset-password/', views.account_reset_password, name='account-reset-password'),
    path('accounts/profile/', views.account_profile, name='account-profile'),
    path('accounts/unimind/', views.unimind_entry, name='account-unimind'),
    path('accounts/select/', views.account_select, name='account-select'),
    path('accounts/logout-all/', views.account_logout_all, name='account-logout-all'),
    path('account-api/center/<str:action>/', views.site_center, name='account-site-center'),
]
