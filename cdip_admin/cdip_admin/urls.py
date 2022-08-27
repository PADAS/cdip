"""cdip_admin URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf.urls import url
from django.contrib import admin
from django.urls import path, include
from website.views import welcome, date, about, index, login_view, logout_view
from django.contrib.staticfiles.urls import staticfiles_urlpatterns


urlpatterns = [
    path("grappelli/", include("grappelli.urls")),
    path("admin/", admin.site.urls),
    path("", welcome, name="welcome"),
    path("date", date),
    path("about", about, name="about"),
    path("integrations/", include("integrations.urls")),
    path("organizations/", include("organizations.urls")),
    path("accounts/", include("accounts.urls")),
    path("clients/", include("clients.urls")),
    path("api/", include("api.urls")),
    path("", index),
    path("login/?", login_view),
    path("oidc-logout", login_view),
    path("logout/", logout_view),
    path("", include("django.contrib.auth.urls")),
    path("", include("social_django.urls")),
]

handler403 = "cdip_admin.views.custom_error_403"

urlpatterns += staticfiles_urlpatterns()
