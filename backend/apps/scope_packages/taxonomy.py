from dataclasses import dataclass


@dataclass(frozen=True)
class TradeDefinition:
    key: str
    label: str


HVAC = TradeDefinition("hvac-mechanical", "HVAC / Mechanical")
PLUMBING = TradeDefinition("plumbing", "Plumbing")
FIRE_PROTECTION = TradeDefinition("fire-protection", "Fire Protection / Sprinkler")
GENERAL = TradeDefinition("general-requirements", "General Requirements")

CURRENT_RULE_VERSION = 2

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
    subject = (entry.finding.subject or "").casefold()
    subject_destinations = _destinations(subject)
    if subject_destinations:
        return subject_destinations
    return _destinations(entry.effective_value.casefold()) or (GENERAL,)


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
