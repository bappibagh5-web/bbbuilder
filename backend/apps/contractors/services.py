import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.projects.audit import record_event
from apps.scope_packages.models import ScopePackageVersion

from .models import Company, DiscoveryRequest, ScopeContractorCandidate, TradeCapability
from .providers import build_search_queries, provider_for


def normalize_domain(value):
    value = value.strip().casefold()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").removeprefix("www.")


def normalize_phone(value):
    return "".join(re.findall(r"\d", value))


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
