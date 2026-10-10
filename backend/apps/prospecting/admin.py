from django.contrib import admin

from .models import (
    ProspectCampaign,
    ProspectCampaignRecipient,
    ProspectCampaignVersion,
    ProspectDeliveryAttempt,
    ProspectImport,
    ProspectingDiscoveryResult,
    ProspectingDiscoveryRun,
    ProspectingSettings,
    ProspectList,
    ProspectListEntry,
    ProspectMessage,
    ProspectProviderEmail,
    ProspectReply,
    ProspectSequenceStep,
    ProspectSequenceStepVersion,
    ProspectSuppression,
    ProspectTag,
    ProspectUnsubscribeToken,
)

admin.site.register(ProspectList)
admin.site.register(ProspectListEntry)
admin.site.register(ProspectTag)
admin.site.register(ProspectingDiscoveryRun)
admin.site.register(ProspectingDiscoveryResult)
admin.site.register(ProspectImport)
admin.site.register(ProspectingSettings)
admin.site.register(ProspectCampaign)
admin.site.register(ProspectCampaignVersion)
admin.site.register(ProspectSequenceStep)
admin.site.register(ProspectSequenceStepVersion)
admin.site.register(ProspectCampaignRecipient)
admin.site.register(ProspectMessage)
admin.site.register(ProspectDeliveryAttempt)
admin.site.register(ProspectProviderEmail)
admin.site.register(ProspectReply)
admin.site.register(ProspectSuppression)
admin.site.register(ProspectUnsubscribeToken)
