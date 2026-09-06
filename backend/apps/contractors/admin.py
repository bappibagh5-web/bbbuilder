from django.contrib import admin

from .models import Company, Contact, DiscoveryRequest, ScopeContractorCandidate, TradeCapability

admin.site.register(Company)
admin.site.register(Contact)
admin.site.register(TradeCapability)
admin.site.register(ScopeContractorCandidate)
admin.site.register(DiscoveryRequest)
