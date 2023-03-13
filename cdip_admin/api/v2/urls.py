from django.conf.urls import url
from rest_framework_swagger.views import get_swagger_view
from . import views
from rest_framework.routers import DefaultRouter
router = DefaultRouter()
router.register('organization', views.OrganizationView, basename="organications")
schema_view = get_swagger_view(title="CDIP ADMIN API V2")

urlpatterns = [
    url(r"^docs/", schema_view),
]
urlpatterns += router.urls
