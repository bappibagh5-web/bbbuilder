"""Versioned, deterministic plain-text RFQ preview; no delivery or persistence."""

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.scope_packages.models import ScopeItem

from .models import InvitationCampaign

RFQ_TEMPLATE_VERSION = 3
COMPANY_PLACEHOLDER = "{{companyName}}"
COUNTRY_DISPLAY = {"CA": "Canada", "US": "United States"}


@dataclass(frozen=True)
class RFQPreview:
    template_version: int
    campaign_id: int
    source_scope_version_id: int
    source_scope_version: int
    trade: str
    package_title: str
    package_summary: str
    subject: str
    body: str
    inclusions: tuple[str, ...]
    exclusions: tuple[str, ...]
    clarifications: tuple[str, ...]
    coordination_requirements: tuple[str, ...]
    general_requirements: tuple[str, ...]
    omitted_unrelated_count: int
    bid_deadline: str | None
    questions_deadline: str | None

    def as_dict(self):
        return asdict(self)


def _format_deadline(value: datetime | None, project_timezone: str) -> str | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        raise ValidationError("RFQ deadlines must include a timezone.")
    return timezone.localtime(value, ZoneInfo(project_timezone)).isoformat(timespec="minutes")


def _lines(values: tuple[str, ...]) -> str:
    return (
        "\n".join(f"- {item}" for item in values)
        if values
        else "Not specified in this scope version."
    )


def _unique(values):
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


_HVAC_SUBJECT = re.compile(
    r"\b(?:hvac|mechanical|ventilation|ducts?|ductwork|diffusers?|thermostats?|"
    r"dampers?|exhaust fans?|air conditioning|air handling|rooftop units?|rtu|"
    r"airflow|air balancing|temperature sensors?|control wiring)\b",
    re.IGNORECASE,
)
_OTHER_SUBJECT = re.compile(
    r"\b(?:glass|glazing|storefront|luminaires?|lighting fixtures?|cable trays?|"
    r"conduits?|hydraulic calculations?|sprinkler heads?|plumbing pipes?|"
    r"water hammer arrestors?|hot water tanks?|track lighting|bonding connections?)\b",
    re.IGNORECASE,
)
_OTHER_TRADE_WARRANTY = re.compile(
    r"\b(?:luminaires?|lighting fixtures?)\b.*\bwarrant\w*"
    r"|\bwarrant\w*.*\b(?:luminaires?|lighting fixtures?)\b",
    re.IGNORECASE,
)
_OTHER_TRADE_WORK = re.compile(
    r"\b(?:cable trays?|conduits?|bonding connections?|water hammer arrestors?|"
    r"hot water tanks?|glass|glazing|hydraulic calculations?)\b",
    re.IGNORECASE,
)
_COORDINATION_CUE = re.compile(
    r"\b(?:coordinat\w*|clash\w*|conflict\w*|interfer\w*|clearance\w*|"
    r"clear\s+(?:new|existing|base|the)|interface\w*)\b",
    re.IGNORECASE,
)
_SUPPORTING_ONLY = re.compile(
    r"@|\b(?:email|e-mail|phone|contact info|manufacturer contact)\b", re.IGNORECASE
)
_UNCERTAINTY = re.compile(
    r"\b(?:confirm\w*|verif\w*|could not be confirmed|cannot be confirmed|"
    r"not specified|unclear|unknown|tbc|to be determined|limited access|"
    r"who is responsible|responsibility not stated|follow[- ]up)\b",
    re.IGNORECASE,
)
_HVAC_ASSIGNMENT = re.compile(
    r"\b(?:hvac|mechanical|ventilation) contractor\b|\bby (?:the )?hvac contractor\b",
    re.IGNORECASE,
)
_CONFIRMED_WORK = re.compile(
    r"\b(?:shall|must|provide|install|supply|furnish|remove|clean|paint|"
    r"test(?:ing)?|balanc\w*|connect|mount|comply|hire|dismantle|indicate)\b",
    re.IGNORECASE,
)
_GENERAL_REQUIREMENT = re.compile(
    r"\b(?:submittals?|shop drawings?|cut sheets?|samples?|closeout|"
    r"operation\s*(?:and|&)\s*maintenance|o\s*(?:and|&)\s*m|"
    r"copies|brochures?|manuals?|warrant\w*|permits?|inspection|codes?|"
    r"repair or replace public|no components may be abandoned|refer to .+ drawings)\b",
    re.IGNORECASE,
)


def _classify_scope_items(scope):
    """Prefer immutable item metadata over the generated flat inclusion mirror."""
    items = list(scope.scope_items.all())
    if not items:
        return _unique(scope.inclusions), _unique(scope.clarifications), (), (), 0

    inclusions = []
    clarifications = list(scope.clarifications)
    coordination = []
    general = []
    omitted = 0
    descriptions = {item.description.strip() for item in items}
    # Explicit human additions outside the generated item mirror remain inclusions.
    inclusions.extend(value for value in scope.inclusions if value.strip() not in descriptions)

    for item in items:
        text = item.description.strip()
        if not text:
            continue
        hvac_package = scope.package.trade_key in {"hvac", "hvac-mechanical"}
        own_subject = not hvac_package or bool(_HVAC_SUBJECT.search(text))
        assigned_hvac = hvac_package and bool(_HVAC_ASSIGNMENT.search(text))
        unrelated = bool(
            _SUPPORTING_ONLY.search(text)
            or _OTHER_TRADE_WARRANTY.search(text)
            or (
                hvac_package
                and _OTHER_TRADE_WORK.search(text)
                and not (own_subject and _COORDINATION_CUE.search(text))
            )
            or (hvac_package and _OTHER_SUBJECT.search(text) and not own_subject)
            or (
                hvac_package
                and not own_subject
                and item.responsibility == ScopeItem.Responsibility.BY_OTHERS
            )
        )
        if unrelated:
            omitted += 1
        elif _UNCERTAINTY.search(text):
            clarifications.append(text)
        elif (
            own_subject
            and _COORDINATION_CUE.search(text)
            and (item.item_type == ScopeItem.ItemType.COORDINATION or item.coordination_required)
        ):
            coordination.append(text)
        elif _GENERAL_REQUIREMENT.search(text) or item.item_type in {
            ScopeItem.ItemType.SUBMITTALS,
            ScopeItem.ItemType.CLOSEOUT,
        }:
            general.append(text)
        elif item.responsibility == ScopeItem.Responsibility.BY_OTHERS and not assigned_hvac:
            omitted += 1
        elif (
            own_subject
            and _CONFIRMED_WORK.search(text)
            and (
                assigned_hvac
                or item.responsibility
                in {
                    ScopeItem.Responsibility.SUPPLY_INSTALL,
                    ScopeItem.Responsibility.INSTALL_ONLY,
                    ScopeItem.Responsibility.RELOCATE_REUSE,
                }
                or hvac_package
            )
        ):
            inclusions.append(text)
        else:
            omitted += 1
    return (
        _unique(inclusions),
        _unique(clarifications),
        _unique(coordination),
        _unique(general),
        omitted,
    )


def build_rfq_preview(*, campaign: InvitationCampaign) -> RFQPreview:
    """Use the campaign's exact historical version, never package.current_version."""
    campaign = InvitationCampaign.objects.select_related(
        "project", "scope_version", "scope_package"
    ).get(pk=campaign.pk)
    project = campaign.project
    scope = campaign.scope_version
    if (
        scope.package_id != campaign.scope_package_id
        or campaign.scope_package.project_id != project.pk
    ):
        raise ValidationError("Campaign scope binding is invalid.")
    if campaign.organization_id != project.organization_id:
        raise ValidationError("Campaign organization binding is invalid.")
    if (
        project.questions_deadline
        and project.bid_deadline
        and project.questions_deadline > project.bid_deadline
    ):
        raise ValidationError("Questions deadline cannot be after the bid deadline.")

    bid_deadline = _format_deadline(project.bid_deadline, project.project_timezone)
    questions_deadline = _format_deadline(project.questions_deadline, project.project_timezone)
    inclusions, clarifications, coordination, general, omitted_count = _classify_scope_items(scope)
    exclusions = _unique(scope.exclusions)
    location = (
        ", ".join(
            part
            for part in (
                project.city,
                project.province_state,
                COUNTRY_DISPLAY.get(project.country.upper(), project.country),
            )
            if part
        )
        or "Location not provided"
    )
    subject = (
        f"Bid Invitation – {campaign.trade_category} – {project.name} ({project.project_number})"
    )
    body = "\n".join(
        (
            f"Hello {COMPANY_PLACEHOLDER},",
            "",
            f"BB Builders requests subcontractor pricing for the {campaign.trade_category} "
            f"scope for {project.name} ({project.project_number}) in {location}.",
            f"Trade package: {scope.title} (Ready V{scope.version}).",
            "",
            "Scope inclusions:",
            _lines(inclusions),
            "",
            "Scope exclusions:",
            _lines(exclusions),
            "",
            "Clarifications / needs confirmation:",
            _lines(clarifications),
            "",
            "Coordination requirements (not confirmed trade scope):",
            _lines(coordination),
            "",
            "General / project requirements:",
            _lines(general),
            "",
            f"Bid due: {bid_deadline or 'Not provided; confirm with BB Builders.'}",
            f"Questions due: {questions_deadline or 'Not provided; confirm with BB Builders.'}",
            "",
            "Please clearly identify your base bid, taxes, inclusions, exclusions, "
            "allowances, alternates, permit responsibility, schedule, and bid validity. "
            "State any assumptions or items requiring clarification.",
            "",
            "Thank you,",
            "BB Builders Estimating",
        )
    )
    return RFQPreview(
        template_version=RFQ_TEMPLATE_VERSION,
        campaign_id=campaign.pk,
        source_scope_version_id=scope.pk,
        source_scope_version=scope.version,
        trade=campaign.trade_category,
        package_title=scope.title,
        package_summary=scope.description,
        subject=subject,
        body=body,
        inclusions=inclusions,
        exclusions=exclusions,
        clarifications=clarifications,
        coordination_requirements=coordination,
        general_requirements=general,
        omitted_unrelated_count=omitted_count,
        bid_deadline=bid_deadline,
        questions_deadline=questions_deadline,
    )
