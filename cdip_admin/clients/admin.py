from django.contrib import admin

# Register your models here.
from clients.models import *

admin.site.register(ClientProfile)
# admin.site.register(AuthorizationScope)
# admin.site.register(InboundClientResource)
# admin.site.register(OutboundClientResource)
# admin.site.register(ClientAudienceScope)
# admin.site.register(InboundClientScope)
# admin.site.register(OutboundClientScope)

