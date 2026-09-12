import hashlib
import re
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from apps.projects.audit import record_event
from apps.scope_packages.models import ScopePackage, ScopePackageVersion
from apps.scope_packages.trades import CONTRACTOR_ELIGIBLE_TRADE_KEYS

from .models import Company, Contact, DiscoveryRequest, ScopeContractorCandidate, TradeCapability
from .providers import BUSINESS_RADIUS_MILES, SearchCenter, build_search_queries, provider_for

COORDINATE_QUANTUM = Decimal("0.000001")


def coordinate_decimal(value):
    """Convert provider coordinates to the precision supported by our storage model."""
    return Decimal(str(value)).quantize(COORDINATE_QUANTUM, rounding=ROUND_HALF_UP)


def project_location_query(project):
    parts = (
        project.site_address_line_1,
        project.site_address_line_2,
        project.city,
        project.province_state,
        project.postal_zip_code,
        project.country,
    )
    value = ", ".join(part.strip() for part in parts if part and part.strip())
    if not project.city or not project.province_state:
        raise ValidationError("Add the project city and province before searching contractors.")
    return value


def project_location_key(project):
    return hashlib.sha256(project_location_query(project).casefold().encode("utf-8")).hexdigest()


def resolve_project_center(project, provider):
    key = project_location_key(project)
    cached = (
        DiscoveryRequest.objects.filter(
            project=project,
            project_location_key=key,
            center_latitude__isnull=False,
            center_longitude__isnull=False,
        )
        .order_by("-requested_at")
        .first()
    )
    if cached:
        return (
            SearchCenter(
                float(cached.center_latitude),
                float(cached.center_longitude),
                cached.center_reference,
            ),
            key,
            True,
        )
    return provider.resolve_center(location_query=project_location_query(project)), key, False


def build_trade_coverage(*, project, candidate_queryset=None, minimum_target=None):
    target = settings.CONTRACTOR_MIN_SHORTLIST_TARGET if minimum_target is None else minimum_target
    packages = (
        ScopePackage.objects.filter(
            project=project,
            lifecycle=ScopePackage.Lifecycle.ACTIVE,
            current_version__status=ScopePackageVersion.Status.READY,
        )
        .select_related("current_version")
        .order_by("trade_category", "id")
    )
    queryset = candidate_queryset
    if queryset is None:
        queryset = ScopeContractorCandidate.objects.filter(
            project=project,
            scope_package__lifecycle=ScopePackage.Lifecycle.ACTIVE,
            scope_version=F("scope_package__current_version"),
        )
    counts = Counter()
    shortlisted = Counter()
    for package_id, status_value in queryset.values_list("scope_package_id", "status"):
        if status_value != ScopeContractorCandidate.Status.REJECTED:
            counts[package_id] += 1
        if status_value == ScopeContractorCandidate.Status.SHORTLISTED:
            shortlisted[package_id] += 1
    return {
        "minimum_shortlist_target": target,
        "trades": [
            {
                "scope_package": package.pk,
                "trade_key": package.trade_key,
                "trade_category": package.trade_category,
                "title": package.current_version.title,
                "candidates_found": counts[package.pk],
                "shortlisted_count": shortlisted[package.pk],
                "coverage_status": (
                    "ready" if shortlisted[package.pk] >= target else "needs_more_candidates"
                ),
            }
            for package in packages
        ],
    }


def normalize_domain(value):
    value = value.strip().casefold()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").removeprefix("www.")


def normalize_phone(value):
    return "".join(re.findall(r"\d", value))


def contact_is_ready(company):
    return (
        company.contacts.filter(is_active=True, is_primary=True)
        .exclude(email="", phone="")
        .exists()
    )


@transaction.atomic
def create_contact(*, company, project, actor, values):
    email = values.get("email", "").strip()
    phone = normalize_phone(values.get("phone", ""))
    existing = None
    if email:
        existing = company.contacts.filter(email__iexact=email).first()
    if existing is None and phone:
        existing = next(
            (
                contact
                for contact in company.contacts.exclude(phone="")
                if normalize_phone(contact.phone) == phone
            ),
            None,
        )
    if existing is not None:
        return existing, False
    contact = Contact(company=company, **values)
    if not contact.is_active:
        contact.is_primary = False
    displaced = []
    if contact.is_primary:
        displaced = list(
            company.contacts.filter(is_active=True, is_primary=True).values_list("pk", flat=True)
        )
        company.contacts.filter(pk__in=displaced).update(is_primary=False)
    contact.full_clean()
    contact.save()
    record_event(
        organization=company.organization,
        project=project,
        actor=actor,
        action_code="contractor_contact.created",
        target=contact,
        metadata={"company_id": company.pk, "displaced_primary_contact_ids": displaced},
    )
    return contact, True


@transaction.atomic
def update_contact(*, contact, project, actor, values):
    changed_fields = []
    previous_active = contact.is_active
    for field, value in values.items():
        if getattr(contact, field) != value:
            setattr(contact, field, value)
            changed_fields.append(field)
    if not contact.is_active and contact.is_primary:
        contact.is_primary = False
        if "is_primary" not in changed_fields:
            changed_fields.append("is_primary")
    displaced = []
    if contact.is_active and contact.is_primary:
        displaced = list(
            contact.company.contacts.filter(is_active=True, is_primary=True)
            .exclude(pk=contact.pk)
            .values_list("pk", flat=True)
        )
        contact.company.contacts.filter(pk__in=displaced).update(is_primary=False)
    if not changed_fields:
        return contact, False
    contact.full_clean()
    contact.save(update_fields=(*changed_fields, "updated_at"))
    state_action = "updated"
    if previous_active != contact.is_active:
        state_action = "reactivated" if contact.is_active else "deactivated"
    record_event(
        organization=contact.company.organization,
        project=project,
        actor=actor,
        action_code=f"contractor_contact.{state_action}",
        target=contact,
        metadata={
            "company_id": contact.company_id,
            "changed_fields": sorted(changed_fields),
            "displaced_primary_contact_ids": displaced,
        },
    )
    return contact, True


def normalized_name(value):
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def dedupe_company(organization, result, provider_name):
    if result.external_place_id:
        match = Company.objects.filter(
            organization=organization,
            external_provider=provider_name,
            external_place_id=result.external_place_id,
        ).first()
        if match:
            return match
    domain = normalize_domain(result.website)
    if domain:
        matches = Company.objects.filter(organization=organization, domain=domain)
        if matches.count() == 1:
            return matches.first()
        if matches.exists():
            return None
    phone = normalize_phone(result.phone)
    if phone:
        matches = Company.objects.filter(organization=organization, normalized_phone=phone)
        if matches.count() == 1:
            return matches.first()
        if matches.exists():
            return None
    matches = [
        company
        for company in Company.objects.filter(organization=organization, city__iexact=result.city)
        if normalized_name(company.display_name) == normalized_name(result.display_name)
    ]
    return matches[0] if len(matches) == 1 else None


def internal_companies(*, organization, trade_key, city, province):
    capabilities = TradeCapability.objects.filter(
        company__organization=organization,
        company__is_active=True,
        is_active=True,
        trade_key=trade_key,
    ).select_related("company")
    return [
        cap.company
        for cap in capabilities
        if (not cap.province or cap.province.casefold() == province.casefold())
        and (
            not cap.service_cities
            or city.casefold() in {item.casefold() for item in cap.service_cities}
        )
    ]


@transaction.atomic
def discover_contractors(*, project, package, actor, keywords=None):
    if (
        package.project_id != project.pk
        or package.current_version.status != ScopePackageVersion.Status.READY
    ):
        raise ValidationError("Only Ready scope packages in this project can be searched.")
    if package.trade_key not in CONTRACTOR_ELIGIBLE_TRADE_KEYS:
        raise ValidationError("This scope trade is not available for contractor search.")
    keywords = list(dict.fromkeys(item.strip() for item in (keywords or []) if item.strip()))
    provider_name = settings.CONTRACTOR_DISCOVERY_PROVIDER
    provider = provider_for(provider_name)
    center, location_key, center_cached = resolve_project_center(project, provider)
    city = project.city
    province = project.province_state
    country = project.country
    terms = build_search_queries(
        trade_key=package.trade_key,
        city=city,
        province=province,
        country=country,
        keywords=keywords,
    )
    request = DiscoveryRequest.objects.create(
        project=project,
        scope_package=package,
        scope_version=package.current_version,
        trade_key=package.trade_key,
        city=city,
        province=province,
        radius_km=322,
        radius_miles=BUSINESS_RADIUS_MILES,
        project_location_key=location_key,
        center_latitude=coordinate_decimal(center.latitude),
        center_longitude=coordinate_decimal(center.longitude),
        center_reference=center.reference,
        keywords=keywords,
        search_terms=terms,
        provider=provider_name,
        requested_by=actor,
    )
    companies = list(
        internal_companies(
            organization=project.organization,
            trade_key=package.trade_key,
            city=city,
            province=province,
        )
    )
    outcome = provider.search(
        trade_key=package.trade_key,
        city=city,
        province=province,
        country=country,
        center=center,
        radius_miles=BUSINESS_RADIUS_MILES,
        keywords=keywords,
    )
    for result in outcome.results:
        company = dedupe_company(project.organization, result, provider_name)
        if company is None:
            company = Company.objects.create(
                organization=project.organization,
                display_name=result.display_name,
                website=result.website,
                phone=result.phone,
                email=result.email,
                address=result.address,
                city=result.city,
                province=result.province,
                postal_code=result.postal_code,
                country=result.country,
                source_type=Company.Source.DISCOVERED,
                external_provider=provider_name,
                external_place_id=result.external_place_id,
                latitude=(
                    coordinate_decimal(result.latitude) if result.latitude is not None else None
                ),
                longitude=(
                    coordinate_decimal(result.longitude) if result.longitude is not None else None
                ),
                created_by=actor,
                updated_by=actor,
            )
        else:
            changed = []
            if company.latitude is None and result.latitude is not None:
                company.latitude = coordinate_decimal(result.latitude)
                changed.append("latitude")
            if company.longitude is None and result.longitude is not None:
                company.longitude = coordinate_decimal(result.longitude)
                changed.append("longitude")
            if changed:
                company.updated_by = actor
                company.save(update_fields=(*changed, "updated_by", "updated_at"))
        capability, capability_created = TradeCapability.objects.get_or_create(
            company=company,
            trade_key=package.trade_key,
            defaults={
                "keywords": keywords,
                "service_cities": [city],
                "province": province,
                "source_type": company.source_type,
                "source_metadata": {"provider": provider_name, **result.metadata},
            },
        )
        if (
            not capability_created
            and capability.source_type == Company.Source.DISCOVERED
            and provider_name == "google_places"
        ):
            refreshed_metadata = {
                **capability.source_metadata,
                "provider": provider_name,
                **result.metadata,
            }
            if capability.source_metadata != refreshed_metadata:
                capability.source_metadata = refreshed_metadata
                capability.save(update_fields=("source_metadata", "updated_at"))
        if company not in companies:
            companies.append(company)
    for company in companies:
        ScopeContractorCandidate.objects.get_or_create(
            project=project,
            scope_package=package,
            scope_version=package.current_version,
            company=company,
            defaults={"created_by": actor, "updated_by": actor},
        )
    request.result_count = len(companies)
    search_request_count = outcome.metadata.get("provider_request_count", 0)
    geocode_request_count = 0 if center_cached or provider_name == "fake" else 1
    request.provider_metadata = {
        "internal_first": True,
        "business_radius_miles": BUSINESS_RADIUS_MILES,
        "project_center": {
            "latitude": center.latitude,
            "longitude": center.longitude,
            "reference": center.reference,
            "cached": center_cached,
        },
        **outcome.metadata,
        "query_count": len(terms),
        "search_request_count": search_request_count,
        "geocode_request_count": geocode_request_count,
        "provider_request_count": search_request_count + geocode_request_count,
        "external_result_count": sum(
            company.source_type == Company.Source.DISCOVERED for company in companies
        ),
    }
    request.save(update_fields=("result_count", "provider_metadata"))
    record_event(
        organization=project.organization,
        project=project,
        actor=actor,
        action_code="contractor_discovery.completed",
        target=request,
        metadata={
            "scope_package_id": package.pk,
            "result_count": len(companies),
            "provider": provider_name,
            "business_radius_miles": BUSINESS_RADIUS_MILES,
            "scope_version_id": package.current_version_id,
            "provider_request_count": search_request_count + geocode_request_count,
            "raw_result_count": outcome.metadata.get("raw_result_count", 0),
            "outside_radius_filtered_count": outcome.metadata.get(
                "outside_radius_filtered_count", 0
            ),
            "deduplicated_count": outcome.metadata.get("deduplicated_count", 0),
        },
    )
    return request


@transaction.atomic
def set_candidate_status(*, candidate, status, actor):
    if status not in ScopeContractorCandidate.Status.values:
        raise ValidationError("Invalid candidate status.")
    if candidate.status == status:
        return candidate, False
    candidate.status = status
    candidate.updated_by = actor
    candidate.save(update_fields=("status", "updated_by", "updated_at"))
    record_event(
        organization=candidate.project.organization,
        project=candidate.project,
        actor=actor,
        action_code=f"contractor_candidate.{status}",
        target=candidate,
        metadata={
            "scope_package_id": candidate.scope_package_id,
            "company_id": candidate.company_id,
        },
    )
    return candidate, True
