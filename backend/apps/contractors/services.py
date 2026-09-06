import re
from collections import Counter
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.projects.audit import record_event
from apps.scope_packages.models import ScopePackage, ScopePackageVersion

from .models import Company, Contact, DiscoveryRequest, ScopeContractorCandidate, TradeCapability
from .providers import build_search_queries, provider_for


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
        queryset = ScopeContractorCandidate.objects.filter(project=project)
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
def discover_contractors(
    *, project, package, actor, city, province, country="Canada", radius_km=None, keywords=None
):
    if (
        package.project_id != project.pk
        or package.current_version.status != ScopePackageVersion.Status.READY
    ):
        raise ValidationError("Only Ready scope packages in this project can be searched.")
    keywords = list(dict.fromkeys(item.strip() for item in (keywords or []) if item.strip()))
    provider_name = settings.CONTRACTOR_DISCOVERY_PROVIDER
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
        radius_km=radius_km,
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
    for result in provider_for(provider_name).search(
        trade_key=package.trade_key,
        city=city,
        province=province,
        country=country,
        radius_km=radius_km,
        keywords=keywords,
    ):
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
                country=result.country,
                source_type=Company.Source.DISCOVERED,
                external_provider=provider_name,
                external_place_id=result.external_place_id,
                created_by=actor,
                updated_by=actor,
            )
            TradeCapability.objects.create(
                company=company,
                trade_key=package.trade_key,
                keywords=keywords,
                service_cities=[city],
                province=province,
                source_type=Company.Source.DISCOVERED,
                source_metadata={"provider": provider_name, **result.metadata},
            )
        if company not in companies:
            companies.append(company)
    for company in companies:
        ScopeContractorCandidate.objects.get_or_create(
            project=project,
            scope_package=package,
            company=company,
            defaults={"created_by": actor, "updated_by": actor},
        )
    request.result_count = len(companies)
    request.provider_metadata = {
        "internal_first": True,
        "query_count": len(terms),
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
