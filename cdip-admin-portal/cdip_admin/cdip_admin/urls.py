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
from django.contrib import admin
from django.urls import path, include
from api.views import public, private, private_scoped, OrganizationsListView
from website.views import welcome, date, about, index, logout, profile
from django.contrib.staticfiles.urls import staticfiles_urlpatterns


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', welcome, name='welcome'),
    path('date', date),
    path('about', about),
    path('integrations/', include('integrations.urls')),
    path('organizations/', include('organizations.urls')),
    path('', index),
    path('logout', logout),
    path('', include('django.contrib.auth.urls')),
    path('', include('social_django.urls')),
    path('profile/', profile, name='profile'),
    path('api/public', public),
    path('api/private', private),
    path('api/private-scoped', private_scoped),
    path('api/organizations/', OrganizationsListView.as_view(), name='organization_list'),
]


urlpatterns += staticfiles_urlpatterns()
