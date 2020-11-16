from django.contrib import admin

# Register your models here.
from clients.models import ClientScope, InboundClientResource, OutboundClientResource

admin.site.register(ClientScope)
admin.site.register(InboundClientResource)
admin.site.register(OutboundClientResource)

