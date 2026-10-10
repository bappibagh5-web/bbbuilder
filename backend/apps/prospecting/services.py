from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.contractors.models import TradeCapability
from apps.contractors.providers import (
    ContractorResult,
    build_search_queries,
    provider_for,
)
from apps.contractors.services import (
    coordinate_decimal,
    dedupe_company,
    upsert_discovered_company,
)
from apps.projects.audit import record_event

from .models import (
    ProspectingDiscoveryResult,
    ProspectingDiscoveryRun,
    ProspectList,
    ProspectListEntry,
    ProspectListEntryTag,
    ProspectTag,
)

MAX_PROSPECTING_RADIUS_MILES = 200


def _location_query(*, city, province, country):
    parts = [str(value).strip() for value in (city, province, country) if str(value).strip()]
    if len(parts) < 2:
        raise ValidationError("Enter a city and province/state for discovery.")
    return ", ".join(parts)


@transaction.atomic
def run_discovery(
    *, organization, actor, trade_key, query, keywords, city, province, country, radius_miles
):
    provider_name = settings.CONTRACTOR_DISCOVERY_PROVIDER
    provider = provider_for(provider_name)
    radius_miles = radius_miles or 50
    if radius_miles < 1 or radius_miles > MAX_PROSPECTING_RADIUS_MILES:
        raise ValidationError(
            f"Search radius must be between 1 and {MAX_PROSPECTING_RADIUS_MILES} miles."
        )
    keywords = list(dict.fromkeys(value.strip() for value in keywords if value.strip()))
    if query.strip() and query.strip() not in keywords:
        keywords.insert(0, query.strip())
    location_query = _location_query(city=city, province=province, country=country)
    center = provider.resolve_center(location_query=location_query)
    terms = build_search_queries(
        trade_key=trade_key,
        city=city,
        province=province,
        country=country,
        keywords=keywords,
    )
    run = ProspectingDiscoveryRun.objects.create(
        organization=organization,
        query=query.strip(),
        trade_key=trade_key,
        keywords=keywords,
        city=city.strip(),
        province=province.strip(),
        country=country.strip(),
        radius_miles=radius_miles,
        provider=provider_name,
        requested_by=actor,
    )
    outcome = provider.search(
        trade_key=trade_key,
        city=city.strip(),
        province=province.strip(),
        country=country.strip(),
        center=center,
        radius_miles=radius_miles,
        keywords=keywords,
    )
    results = []
    for result in outcome.results:
        company = dedupe_company(organization, result, provider_name)
        results.append(
            ProspectingDiscoveryResult(
                run=run,
                company=company,
                display_name=result.display_name,
                website=result.website,
                phone=result.phone,
                address=result.address,
                city=result.city,
                province=result.province,
                postal_code=result.postal_code,
                country=result.country,
                external_place_id=result.external_place_id,
                latitude=(
                    coordinate_decimal(result.latitude) if result.latitude is not None else None
                ),
                longitude=(
                    coordinate_decimal(result.longitude) if result.longitude is not None else None
                ),
                source_url=result.website,
                provider_metadata=result.metadata,
            )
        )
    ProspectingDiscoveryResult.objects.bulk_create(results)
    run.result_count = len(results)
    run.completed_at = timezone.now()
    run.provider_metadata = {
        "query_count": len(terms),
        "provider_request_count": outcome.metadata.get("provider_request_count", 0),
        "raw_result_count": outcome.metadata.get("raw_result_count", len(results)),
        "outside_radius_filtered_count": outcome.metadata.get("outside_radius_filtered_count", 0),
        "deduplicated_count": outcome.metadata.get("deduplicated_count", 0),
        "partial_failure_count": outcome.metadata.get("partial_failure_count", 0),
        "center_reference": center.reference,
    }
    run.save(update_fields=("result_count", "completed_at", "provider_metadata"))
    record_event(
        organization=organization,
        project=None,
        actor=actor,
        action_code="prospecting.discovery.completed",
        target=run,
        metadata={
            "trade_key": trade_key,
            "provider": provider_name,
            "result_count": len(results),
            "radius_miles": radius_miles,
        },
    )
    return run


def result_as_provider_value(result):
    return ContractorResult(
        display_name=result.display_name,
        website=result.website,
        phone=result.phone,
        address=result.address,
        city=result.city,
        province=result.province,
        postal_code=result.postal_code,
        country=result.country,
        external_place_id=result.external_place_id,
        latitude=float(result.latitude) if result.latitude is not None else None,
        longitude=float(result.longitude) if result.longitude is not None else None,
        metadata=result.provider_metadata,
    )


@transaction.atomic
def add_discovery_results(*, prospect_list, run, result_ids, actor):
    if prospect_list.organization_id != run.organization_id:
        raise ValidationError("Discovery run and prospect list must belong to one organization.")
    if prospect_list.status != ProspectList.Status.ACTIVE:
        raise ValidationError("Archived prospect lists cannot accept new prospects.")
    results = list(run.results.filter(pk__in=result_ids).select_related("company"))
    if len(results) != len(set(result_ids)):
        raise ValidationError("One or more selected discovery results are unavailable.")
    entries = []
    for result in results:
        company, _ = upsert_discovered_company(
            organization=prospect_list.organization,
            result=result_as_provider_value(result),
            provider_name=run.provider,
            actor=actor,
        )
        if result.company_id != company.pk:
            result.company = company
            result.save(update_fields=("company",))
        TradeCapability.objects.get_or_create(
            company=company,
            trade_key=run.trade_key,
            defaults={
                "keywords": run.keywords,
                "service_cities": [run.city],
                "province": run.province,
                "source_type": company.source_type,
                "source_metadata": {
                    "provider": run.provider,
                    "prospecting_discovery_run_id": run.pk,
                },
            },
        )
        entry, created = ProspectListEntry.objects.get_or_create(
            prospect_list=prospect_list,
            company=company,
            defaults={
                "source_type": run.provider,
                "source_reference": result.external_place_id,
                "source_metadata": {
                    "discovery_run_id": run.pk,
                    "trade_key": run.trade_key,
                },
                "source_url": result.source_url,
                "added_by": actor,
            },
        )
        if not created and not entry.is_active:
            entry.is_active = True
            entry.removed_by = None
            entry.removed_at = None
            entry.source_type = run.provider
            entry.source_reference = result.external_place_id
            entry.source_metadata = {
                "discovery_run_id": run.pk,
                "trade_key": run.trade_key,
            }
            entry.source_url = result.source_url
            entry.save(
                update_fields=(
                    "is_active",
                    "removed_by",
                    "removed_at",
                    "source_type",
                    "source_reference",
                    "source_metadata",
                    "source_url",
                    "updated_at",
                )
            )
        if created:
            record_event(
                organization=prospect_list.organization,
                project=None,
                actor=actor,
                action_code="prospect.added",
                target=entry,
                metadata={
                    "prospect_list_id": prospect_list.pk,
                    "company_id": company.pk,
                    "discovery_run_id": run.pk,
                },
            )
        entries.append(entry)
    return entries


@transaction.atomic
def update_entry(*, entry, actor, status=None, notes=None, tag_names=None, primary_contact=None):
    previous_status = entry.status
    contact_changed = primary_contact is not None and primary_contact.pk != entry.primary_contact_id
    if status is not None:
        entry.status = status
    if notes is not None:
        entry.notes = notes
    if primary_contact is not None:
        if primary_contact.company_id != entry.company_id:
            raise ValidationError("Selected contact must belong to this prospect company.")
        entry.primary_contact = primary_contact
    entry.save()
    if tag_names is not None:
        tags = []
        for raw_name in tag_names:
            name = " ".join(raw_name.split())
            if not name:
                continue
            tag, _ = ProspectTag.objects.get_or_create(
                organization=entry.prospect_list.organization, name=name
            )
            tags.append(tag)
        ProspectListEntryTag.objects.filter(entry=entry).exclude(tag__in=tags).delete()
        for tag in tags:
            ProspectListEntryTag.objects.get_or_create(entry=entry, tag=tag)
    if previous_status != entry.status:
        record_event(
            organization=entry.prospect_list.organization,
            project=None,
            actor=actor,
            action_code="prospect.status_changed",
            target=entry,
            metadata={
                "prospect_list_id": entry.prospect_list_id,
                "company_id": entry.company_id,
                "previous_status": previous_status,
                "new_status": entry.status,
            },
        )
    if contact_changed:
        record_event(
            organization=entry.prospect_list.organization,
            project=None,
            actor=actor,
            action_code="prospect.contact_selected",
            target=entry,
            metadata={
                "prospect_list_id": entry.prospect_list_id,
                "company_id": entry.company_id,
                "contact_id": primary_contact.pk,
            },
        )
    return entry
