import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TradeDefinition:
    key: str
    label: str


HVAC = TradeDefinition("hvac-mechanical", "HVAC / Mechanical")
PLUMBING = TradeDefinition("plumbing", "Plumbing")
FIRE_PROTECTION = TradeDefinition("fire-protection", "Fire Protection / Sprinkler")
GENERAL = TradeDefinition("general-requirements", "General Requirements")
DEMOLITION = TradeDefinition("demolition", "Demolition")
ENVIRONMENTAL = TradeDefinition(
    "environmental-hazardous-materials", "Environmental / Hazardous Materials"
)
STOREFRONT = TradeDefinition(
    "storefront-architectural-millwork", "Storefront / Architectural Millwork"
)
ELECTRICAL = TradeDefinition("electrical", "Electrical")
LOW_VOLTAGE = TradeDefinition("low-voltage-security-av", "Low Voltage / Security / AV")
DOORS_HARDWARE = TradeDefinition("doors-hardware", "Doors / Hardware")
SPECIALTY_EQUIPMENT = TradeDefinition(
    "specialty-equipment-security-grilles", "Specialty Equipment / Security Grilles"
)

CURRENT_RULE_VERSION = 3

FIRE_TERMS = ("sprinkler", "nfpa 13", "fire protection")
PLUMBING_TERMS = (
    "plumbing",
    "water heater",
    "fixture",
    "sewer",
    "hub drain",
    "floor drain",
    "lavatory",
    "washroom",
)
HVAC_TERMS = (
    "ventilation",
    "duct",
    "ductwork",
    "diffuser",
    "grille",
    "vav",
    "thermostat",
    "building automation system",
    "landlord's bas",
    "landlord bas",
    "exhaust fan",
    "air balance",
    "testing and balancing",
)


def trades_for_entry(entry):
    """Return controlled trade destinations from approved finding text."""
    return tuple(dict.fromkeys(item.trade for item in scope_items_for_entry(entry)))


@dataclass(frozen=True)
class ScopeItemDefinition:
    key: str
    trade: TradeDefinition
    item_type: str
    title: str
    description: str
    responsibility: str


def _item(key, trade, item_type, title, description):
    return ScopeItemDefinition(
        key,
        trade,
        item_type,
        title,
        description,
        _responsibility_for_text(f"{title} {description}"),
    )


def _responsibility_for_text(text):
    normalized = " ".join((text or "").casefold().split())
    if re.search(r"\bexisting\b.{0,80}\bto remain\b", normalized):
        return "existing_to_remain"
    rules = (
        (("owner supplied", "owner-supplied"), "owner_supplied"),
        (("landlord supplied", "landlord-supplied"), "landlord_supplied"),
        (("existing to remain",), "existing_to_remain"),
        (("relocate", "reuse", "re-use"), "relocate_reuse"),
        (("by others",), "by_others"),
        (("install only", "installation only"), "install_only"),
        (("supply and install", "supply & install", "supply/install"), "supply_install"),
    )
    for terms, responsibility in rules:
        if any(term in normalized for term in terms):
            return responsibility
    return "unclear"


def scope_items_for_entry(entry):
    """Deterministically decompose one approved entry into grounded bid-scope items."""
    subject = (entry.finding.subject or "").casefold()
    value = entry.effective_value
    rules = (
        (
            "drawing issuance",
            (
                _item(
                    "confirm-drawing-issue-status",
                    GENERAL,
                    "general",
                    "Confirm drawing issue status",
                    value,
                ),
            ),
        ),
        (
            "permit responsibility",
            (
                _item(
                    "coordinate-permit-responsibilities",
                    GENERAL,
                    "permits",
                    "Coordinate permit responsibilities",
                    value,
                ),
                _item(
                    "obtain-sprinkler-permit",
                    FIRE_PROTECTION,
                    "permits",
                    "Obtain sprinkler permit",
                    value,
                ),
            ),
        ),
        (
            "owner-supplied materials",
            (
                _item(
                    "receive-unpackage-owner-materials",
                    GENERAL,
                    "coordination",
                    "Receive and unpackage owner-supplied materials",
                    value,
                ),
                _item(
                    "count-owner-materials",
                    GENERAL,
                    "general",
                    "Count owner-supplied materials",
                    value,
                ),
                _item(
                    "inspect-owner-materials",
                    GENERAL,
                    "general",
                    "Inspect owner-supplied materials",
                    value,
                ),
                _item(
                    "install-coordinate-owner-materials",
                    GENERAL,
                    "supply_install",
                    "Install and coordinate owner-supplied materials",
                    value,
                ),
            ),
        ),
        (
            "verify dimensions",
            (
                _item(
                    "verify-dimensions-levels",
                    GENERAL,
                    "general",
                    "Verify dimensions and levels",
                    value,
                ),
                _item(
                    "report-dimension-discrepancies",
                    GENERAL,
                    "coordination",
                    "Report dimensional discrepancies",
                    value,
                ),
            ),
        ),
        (
            "demolition responsibilities",
            (
                _item(
                    "demolish-leasehold-improvements",
                    DEMOLITION,
                    "demolition",
                    "Demolish leasehold improvements",
                    value,
                ),
                _item(
                    "remove-demolition-debris",
                    DEMOLITION,
                    "demolition",
                    "Remove demolition debris",
                    value,
                ),
                _item(
                    "dispose-demolition-debris",
                    DEMOLITION,
                    "demolition",
                    "Dispose of demolition debris",
                    value,
                ),
                _item(
                    "coordinate-demolition-phasing",
                    DEMOLITION,
                    "coordination",
                    "Coordinate demolition phasing",
                    value,
                ),
                _item(
                    "coordinate-mep-demolition",
                    DEMOLITION,
                    "coordination",
                    "Coordinate associated MEP demolition",
                    value,
                ),
            ),
        ),
        (
            "controlled substance removal",
            (
                _item(
                    "coordinate-controlled-substance-removal",
                    ENVIRONMENTAL,
                    "coordination",
                    "Coordinate controlled-substance removal",
                    value,
                ),
            ),
        ),
        (
            "landlord deliverable",
            (
                _item(
                    "coordinate-landlord-shell-delivery",
                    GENERAL,
                    "coordination",
                    "Coordinate landlord shell and redemise work",
                    value,
                ),
            ),
        ),
        (
            "survey after demolition",
            (
                _item(
                    "complete-post-demolition-survey",
                    GENERAL,
                    "testing",
                    "Complete and return post-demolition survey",
                    value,
                ),
            ),
        ),
        (
            "plumbing fixtures",
            (
                _item(
                    "provide-water-closets",
                    PLUMBING,
                    "supply_install",
                    "Provide water closets",
                    value,
                ),
                _item(
                    "provide-lavatories", PLUMBING, "supply_install", "Provide lavatories", value
                ),
                _item(
                    "provide-barrier-free-washroom",
                    PLUMBING,
                    "supply_install",
                    "Provide barrier-free washroom fixtures",
                    value,
                ),
            ),
        ),
        (
            "shopfront fascia",
            (
                _item(
                    "install-shopfront-fascia",
                    STOREFRONT,
                    "supply_install",
                    "Install shopfront fascia",
                    value,
                ),
                _item(
                    "apply-shopfront-finishes",
                    STOREFRONT,
                    "supply_install",
                    "Apply specified shopfront finishes",
                    value,
                ),
            ),
        ),
        (
            "concealed blocking",
            (
                _item(
                    "install-bulkhead-blocking",
                    STOREFRONT,
                    "supply_install",
                    "Install concealed bulkhead blocking",
                    value,
                ),
                _item(
                    "install-bulkhead-bracing",
                    STOREFRONT,
                    "supply_install",
                    "Install bulkhead bracing",
                    value,
                ),
                _item(
                    "install-screen-lightbox-blocking",
                    STOREFRONT,
                    "supply_install",
                    "Install blocking for suspended screens and lightboxes",
                    value,
                ),
            ),
        ),
        (
            "footwear ordering screens",
            (
                _item(
                    "provide-screen-poe",
                    ELECTRICAL,
                    "supply_install",
                    "Provide PoE for footwear ordering screens",
                    value,
                ),
                _item(
                    "provide-screen-continuous-power",
                    ELECTRICAL,
                    "supply_install",
                    "Provide 24-hour power for footwear ordering screens",
                    value,
                ),
            ),
        ),
        (
            "security/av installers",
            (
                _item(
                    "coordinate-security-installer",
                    LOW_VOLTAGE,
                    "coordination",
                    "Coordinate nominated security installer",
                    value,
                ),
                _item(
                    "coordinate-eas-installer",
                    LOW_VOLTAGE,
                    "coordination",
                    "Coordinate nominated EAS installer",
                    value,
                ),
                _item(
                    "coordinate-cabling-av-it-installer",
                    LOW_VOLTAGE,
                    "coordination",
                    "Coordinate nominated cabling, AV and IT installer",
                    value,
                ),
                _item(
                    "coordinate-speaker-installer",
                    LOW_VOLTAGE,
                    "coordination",
                    "Coordinate nominated speaker installer",
                    value,
                ),
            ),
        ),
        (
            "citiloc re-keying",
            (
                _item(
                    "coordinate-rekeying",
                    DOORS_HARDWARE,
                    "coordination",
                    "Coordinate re-keying supply and installation",
                    value,
                ),
            ),
        ),
        (
            "mobilflex",
            (
                _item(
                    "install-security-grilles",
                    SPECIALTY_EQUIPMENT,
                    "supply_install",
                    "Install owner-supplied security grilles",
                    value,
                ),
            ),
        ),
        (
            "unistrut and threaded rod",
            (
                _item(
                    "provide-suspended-item-unistrut",
                    ELECTRICAL,
                    "supply_install",
                    "Provide unistrut for suspended electrical items",
                    value,
                ),
                _item(
                    "provide-threaded-rod",
                    ELECTRICAL,
                    "supply_install",
                    "Provide threaded rod for suspended items",
                    value,
                ),
            ),
        ),
        (
            "track lighting mounting",
            (
                _item(
                    "provide-track-lighting-support",
                    ELECTRICAL,
                    "supply_install",
                    "Provide threaded-rod and unistrut track-lighting supports",
                    value,
                ),
            ),
        ),
    )
    for term, items in rules:
        if term in subject:
            return items
    destinations = _destinations(subject) or _destinations(value.casefold()) or (GENERAL,)
    return tuple(
        _item(
            f"approved-entry-{getattr(entry, 'pk', 'unpersisted')}-{trade.key}",
            trade,
            "general",
            entry.finding.subject.strip() or trade.label,
            value,
        )
        for trade in destinations
    )


def _destinations(text):
    destinations = []
    if any(term in text for term in FIRE_TERMS):
        destinations.append(FIRE_PROTECTION)
    if any(term in text for term in PLUMBING_TERMS) and not any(
        term in text for term in FIRE_TERMS
    ):
        destinations.append(PLUMBING)
    if any(term in text for term in HVAC_TERMS):
        destinations.append(HVAC)
    return tuple(destinations)
