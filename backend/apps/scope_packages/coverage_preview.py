import re
from collections import Counter, defaultdict

from django.db.models import Count, Prefetch

from apps.analysis.models import (
    ProjectIntelligenceSnapshot,
    ProjectIntelligenceSnapshotEntry,
    ProjectIntelligenceSnapshotProvenance,
)

from .models import ScopePackage

PREVIEW_RULE_VERSION = 5

PACKAGE_RULES = (
    (
        "miscellaneous-metals",
        "Miscellaneous Metals",
        (
            "miscellaneous metal",
            "misc metal",
            "steel angle",
            "metal angle",
            "metal bracket",
            "lintel",
            "unistrut",
            "angles welded",
        ),
    ),
    (
        "steel-stud-framing",
        "Steel Stud Framing",
        (
            "steel stud",
            "steel studs",
            "metal stud",
            "metal studs",
            "stud framing",
            "partition framing",
            "slip track",
            "deflection clip",
        ),
    ),
    (
        "backing-blocking",
        "Backing / Blocking",
        ("backing", "blocking", "plywood substrate", "wood grounds"),
    ),
    ("drywall", "Drywall", ("drywall", "gypsum board", "gyp board", "plasterboard")),
    (
        "mudding-taping",
        "Mudding & Taping",
        (
            "mudding",
            "taping",
            "joint compound",
            "level 5 finish",
            "level 4 finish",
            "level 5 drywall finish",
            "level 4 drywall finish",
        ),
    ),
    (
        "act-ceilings",
        "T-Bar / ACT Ceilings",
        (
            "t-bar",
            "acoustic ceiling",
            "acoustical ceiling",
            "ceiling tile",
            "act ceiling",
            "suspended ceiling",
        ),
    ),
    (
        "doors-frames-hardware",
        "Doors / Frames / Hardware",
        (
            "door hardware",
            "door frame",
            "door cylinder",
            "door cylinders",
            "locksmith",
            "door closer",
            "doors and frames",
            "door schedule",
        ),
    ),
    (
        "glazing-storefront",
        "Glazing / Storefront",
        ("glazing", "storefront", "shopfront", "glass door", "glass panel"),
    ),
    (
        "millwork",
        "Millwork",
        ("millwork", "casework", "cabinet", "cash desk", "plinth", "display fixture"),
    ),
    (
        "flooring",
        "Flooring",
        (
            "flooring",
            "floor finish",
            "floor tile",
            "vinyl",
            "carpet",
            "floor sealer",
            "floor adhesive",
            "slab moisture",
        ),
    ),
    (
        "painting-finishes",
        "Painting / Finishes",
        (
            "painting",
            "paint finish",
            "painted",
            "coating",
            "wall finish",
            "sprayed to match",
        ),
    ),
    (
        "specialties",
        "Specialties",
        (
            "security grille",
            "security shutter",
            "roller shutter",
            "pocket gate",
            "washroom accessory",
            "specialty equipment",
            "sliding shutter",
            "shutter",
            "aeroflex",
            "stockroom racking",
        ),
    ),
    (
        "plumbing",
        "Plumbing",
        (
            "plumbing",
            "water closet",
            "lavatory",
            "washroom fixture",
            "washroom",
            "water heater",
            "vav",
            "backflow",
            "floor drain",
            "hub drain",
            "sanitary",
            "domestic water",
        ),
    ),
    (
        "hvac-mechanical",
        "HVAC / Mechanical",
        (
            "hvac",
            "mechanical",
            "duct",
            "ducts",
            "diffuser",
            "air handling",
            "rooftop unit",
            "rtu",
            "thermostat",
            "ventilation",
            "exhaust fan",
            "air balance",
            "bas",
        ),
    ),
    (
        "fire-protection",
        "Fire Protection / Sprinklers",
        ("sprinkler", "sprinklers", "fire protection", "nfpa 13"),
    ),
    (
        "lighting",
        "Lighting",
        (
            "lighting",
            "luminaire",
            "light fixture",
            "lamp",
            "downlight",
            "occupancy sensor",
            "cable holder",
            "cable holders",
            "track light",
            "emergency light",
            "dimming",
            "dimmer",
            "dimmers",
            "driver",
            "drivers",
            "lm-79",
            "trac-master",
            "trac-lites",
            "led",
        ),
    ),
    (
        "fire-alarm",
        "Fire Alarm",
        ("fire alarm", "smoke detector", "alarm interface", "shutdown interface"),
    ),
    (
        "low-voltage-data",
        "Low Voltage / Data",
        (
            "low voltage",
            "data cabling",
            "structured cabling",
            "network",
            "poe",
            "wap",
            "dayforce",
            "cable management",
            "it rack",
            "pos",
            "traffic counter",
            "shoppertrak",
        ),
    ),
    (
        "security",
        "Security",
        (
            "security camera",
            "security cameras",
            "security sensor",
            "security sensors",
            "camera device",
            "cctv",
            "eas",
            "rfid",
            "access control",
            "intrusion",
        ),
    ),
    (
        "av",
        "AV",
        (
            "audio visual",
            "av / it",
            "av equipment",
            "digital screen",
            "digital screens",
            "ordering screen",
            "ordering screens",
            "lcd",
            "television",
            " tv ",
            "speaker",
        ),
    ),
    (
        "signage",
        "Signage",
        (
            "signage",
            "blade sign",
            "illuminated sign",
            "sign power",
            "wayfinding",
            "lightbox",
            "light box",
            "flyposter",
            "flyposters",
        ),
    ),
    (
        "roofing",
        "Roofing",
        ("roofing", "roof membrane", "roof curb", "flashing", "roof penetration"),
    ),
    (
        "firestopping",
        "Firestopping",
        ("firestop", "fire stopping", "fire-stopping", "fire separation penetration"),
    ),
    (
        "civil-site",
        "Civil / Site Work",
        ("civil", "site work", "site servicing", "trenching", "excavation", "grading", "sidewalk"),
    ),
    (
        "structural",
        "Structural",
        (
            "structural",
            "hss",
            "framing members",
            "steel support",
            "equipment support",
            "roof opening",
            "seismic",
            "anchorage",
        ),
    ),
    (
        "demolition",
        "Demolition",
        ("demolition", "demolish", "remove existing", "selective removal"),
    ),
    (
        "closeout",
        "Closeout",
        (
            "closeout",
            "as-built",
            "as built",
            "o&m",
            "operation and maintenance",
            "warranty",
            "guarantee",
            "training",
            "commissioning",
        ),
    ),
    (
        "electrical-power",
        "Electrical Power",
        (
            "electrical",
            "power supply",
            "power connection",
            "power & data socket loop",
            "power and data socket loop",
            "socket loop",
            "receptacle",
            "disconnect",
            "feeder",
            "circuit",
            "panel",
            "grounding",
            "cable tray",
            "cable trays",
            "cable whips",
            "remote power",
            "24vdc",
            "120v",
            "347v",
            "0-10v wires",
            "cover plate",
            "transformer",
            "junction box",
            "cable whip",
            "cable management",
        ),
    ),
)

NON_SCOPE_TERMS = (
    "manufacturer contact",
    "landlord contact",
    "contractor / entrepreneur identity",
    "document revision date",
    "document / signature date",
    "quote / document date",
    "unit price example",
    "payment terms",
    "manufacturer reservation",
    "code of conduct",
    "connected-control components may be supplied",
    "listings and location suitability",
    "photometric content provided",
)

DOCUMENT_STATUS_TERMS = (
    "drawing issue",
    "issued for construction",
    "for construction date",
    "stage 2 issue",
    "document title",
    "drawing / plan name",
    "do not scale drawing",
    "drawing shall not be scaled",
)

GENERIC_SUBJECT_RE = re.compile(
    r"^[a-z /&-]+:\s*(project_fact|scope_trade|responsibility|commercial|permit_inspection|"
    r"bid_condition|coordination|submittal|submittal_closeout|demolition|schedule|permit|"
    r"supply[ _]install)$"
)

HEADING_ONLY_VALUES = {
    "mercantile",
    "sprinklered",
    "no",
    "yes",
    "for construction",
    "issued for construction",
    "for bids, landlord review & permit",
}

HISTORICAL_COVERAGE = {
    "Demolition": {"demolition"},
    "Doors / Hardware": {"doors-frames-hardware"},
    "Electrical": {"electrical-power"},
    "Environmental / Hazardous Materials": {"environmental-hazardous-materials"},
    "Fire Protection / Sprinkler": {"fire-protection"},
    "General Requirements": {"general-requirements"},
    "Low Voltage / Security / AV": {"low-voltage-data", "security", "av"},
    "Plumbing": {"plumbing"},
    "Specialty Equipment / Security Grilles": {"specialties"},
    "Storefront / Architectural Millwork": {"glazing-storefront", "millwork"},
}

EXPECTED_SCOPE_COVERAGE = (
    ("miscellaneous-metals", "Miscellaneous Metals"),
    ("steel-stud-framing", "Steel Stud Framing"),
    ("backing-blocking", "Backing / Blocking"),
    ("drywall", "Drywall"),
    ("mudding-taping", "Mudding & Taping"),
    ("act-ceilings", "T-Bar / ACT Ceilings"),
    ("doors-frames-hardware", "Doors / Frames / Hardware"),
    ("glazing-storefront", "Glazing / Storefront"),
    ("millwork", "Millwork"),
    ("flooring", "Flooring"),
    ("painting-finishes", "Painting / Finishes"),
    ("specialties", "Specialties"),
    ("plumbing", "Plumbing"),
    ("hvac-mechanical", "HVAC / Mechanical"),
    ("fire-protection", "Fire Protection / Sprinklers"),
    ("electrical-power", "Electrical Power"),
    ("lighting", "Lighting"),
    ("fire-alarm", "Fire Alarm"),
    ("low-voltage-data", "Low Voltage / Data"),
    ("security", "Security"),
    ("av", "AV"),
    ("signage", "Signage"),
    ("roofing", "Roofing"),
    ("firestopping", "Firestopping"),
    ("civil-site", "Civil / Site Work"),
    ("closeout", "Closeout"),
)


def _normalized(value):
    return " ".join((value or "").casefold().split())


def _contains_term(text, term):
    """Match taxonomy terms as words/phrases, not accidental substrings."""
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term.strip())}(?![a-z0-9])", text))


def _responsibility(text):
    if re.search(
        r"costs?\s+(?:are\s+)?charged\s+to\s+(?:the\s+)?(?:electrical|mechanical)\s+contractor",
        text,
    ):
        return "supply_install"
    if re.search(r"(?:electrical|mechanical)\s+contractor\s+(?:is\s+)?responsible", text):
        return "supply_install"
    if re.search(
        r"supplied\s+by\s+(?:the\s+)?vendor.+installed\s+by\s+(?:the\s+)?contractor", text
    ):
        return "install_only"
    rules = (
        (("owner supplied", "owner-supplied", "by owner"), "owner_supplied"),
        (
            (
                "landlord supplied",
                "landlord-supplied",
                "by landlord",
                "landlord to provide",
            ),
            "landlord_supplied",
        ),
        (("existing to remain",), "existing_to_remain"),
        (("relocate", "reuse", "re-use"), "relocate_reuse"),
        (
            (
                "by others",
                "structural engineer to",
                "installed by nutech",
                "installed by echo",
                "installed by controltek",
                "installed by locksmith",
                "landlord contractor",
                "landlord's contractor",
            ),
            "by_others",
        ),
        (("install only", "installation only"), "install_only"),
        (
            (
                "supply and install",
                "supply & install",
                "supply/install",
                "contractor to provide",
                "contractor shall provide",
                "contractor shall install",
                "this contractor shall",
                "general contractor shall",
                "general contractor to",
                "g.c. to provide",
                "g.c. shall provide",
                "gc to provide",
                "g.c. is responsible",
                "gc is responsible",
                "g.c. to install",
                "gc to install",
            ),
            "supply_install",
        ),
    )
    for terms, result in rules:
        if any(term in text for term in terms):
            return result
    return "unclear"


def _item_type(text, package_key):
    checks = (
        (("demolition", "demolish", "remove existing"), "demolition"),
        (("submittal", "shop drawing"), "submittals"),
        (("closeout", "as-built", "as built", "o&m", "warranty"), "closeout"),
        (("test", "inspection", "commission"), "testing"),
        (("permit",), "permits"),
        (("coordinate", "coordination", "interface"), "coordination"),
        (("control", "thermostat", "dimming"), "controls"),
        (("equipment", "unit", "fixture"), "equipment"),
    )
    for terms, result in checks:
        if any(term in text for term in terms):
            return result
    return "general" if package_key == "general-requirements" else "supply_install"


def _is_non_scope(entry, text):
    if text.strip(" .:-") in HEADING_ONLY_VALUES:
        return True
    if len(text) <= 60 and text.upper() == text and not _is_actionable(text.casefold()):
        return True
    if any(term in text for term in NON_SCOPE_TERMS):
        return True
    if entry.category == "date_deadline" and any(
        term in text for term in ("issue date", "revision date", "signature date", "document date")
    ):
        return True
    if any(term in text for term in DOCUMENT_STATUS_TERMS):
        return True
    if entry.category == "project_fact" and "for construction" in text and len(text) < 140:
        return True
    if entry.category == "scope_trade" and "see drawing" in text and "referenced" in text:
        return True
    if entry.category == "date_deadline" and any(
        term in text
        for term in (
            "for bids",
            "landlord review & permit",
            "for ll review",
            "bids and permit",
            "for construction",
            "stage 2",
        )
    ):
        return True
    if (
        entry.category == "project_fact"
        and any(
            term in text
            for term in (
                "contact:",
                "signature present",
                "unit a2",
                "occupants (total)",
                "sq.ft.",
                "sqft",
                "drawing scale",
            )
        )
        and not any(
            term in text
            for term in (
                "install",
                "provide",
                "required",
                "retain",
                "unistrut",
                "power",
                "data",
                "door",
            )
        )
    ):
        return True
    return entry.category == "commercial" and any(
        term in text for term in ("quote", "price", "payment", "shipping", "freight")
    )


def _is_project_wide(text):
    return any(
        term in text
        for term in (
            "general contractor",
            "g.c.",
            "all work",
            "all subcontractors",
            "building code",
            "site visit",
            "site verification",
            "verify all dimensions",
            "verify dimensions on site",
            "verify existing conditions",
            "errors and omissions",
            "landlord review",
            "landlord agreement",
            "permit",
            "inspection",
            "barricade",
            "hoarding",
            "work hours",
            "field conditions",
        )
    )


def _is_actionable(text):
    return any(
        term in text
        for term in (
            "install",
            "supply",
            "provide",
            "connect",
            "mount",
            "coordinate",
            "verify",
            "remove",
            "relocate",
            "repair",
            "submit",
            "test",
            "required",
            "responsible",
            "by others",
            "not stated",
            "unclear",
        )
    )


def _is_active_fire_protection(text):
    return any(
        term in text
        for term in (
            "sprinkler",
            "fire protection contractor",
            "fire protection system",
            "nfpa 13",
            "hydrostatic",
            "fire department connection",
            "fdc",
            "riser",
            "drain down",
            "sprinkler piping",
        )
    )


def _is_passive_fire_protection(text):
    return any(
        term in text
        for term in (
            "fire rating",
            "fire-rated",
            "fire rated",
            "beam fire protection",
            "fireproof insulation",
            "fireproof wall",
            "fireproof floor",
            "rated assembly",
        )
    )


def _atomic_values(value):
    """Split only explicit list clauses; never manufacture text not present in the finding."""
    bullet_parts = [
        part.strip() for part in re.split(r"\s*\n\s*[-•]\s*", value or "") if part.strip()
    ]
    parts = []
    for part in bullet_parts:
        clauses = [
            clause.strip()
            for clause in re.split(r"\s*;\s*(?=costs?\s+(?:are\s+)?charged\b)", part, flags=re.I)
            if clause.strip()
        ]
        parts.extend(clauses)
    return parts or [value or ""]


def _classify(entry, provenance, value=None):
    finding = entry.finding
    subject = _normalized(finding.subject)
    semantic_subject = "" if GENERIC_SUBJECT_RE.match(subject) else subject
    effective_value = entry.effective_value if value is None else value
    value_text = _normalized(effective_value)
    text = value_text
    if _is_non_scope(entry, text):
        return (), text
    if (
        entry.category == "permit_inspection"
        and "general construction building permit" in text
        and "corresponding subtrades" in text
    ):
        return (("general-requirements", "General Requirements"),), text
    matches = []
    for key, label, terms in PACKAGE_RULES:
        if any(_contains_term(text, term) for term in terms):
            matches.append((key, label))

    if not matches and semantic_subject:
        text = _normalized(f"{semantic_subject} {effective_value}")
        for key, label, terms in PACKAGE_RULES:
            if any(_contains_term(text, term) for term in terms):
                matches.append((key, label))

    passive_fire = _is_passive_fire_protection(text) and not _is_active_fire_protection(text)
    if passive_fire:
        matches = [match for match in matches if match[0] != "fire-protection"]
        if not matches:
            matches.append(("general-requirements", "General Requirements"))

    if "framing" in text and "field review" in text:
        matches = [("structural", "Structural")]

    if (
        not matches
        and _is_project_wide(text)
        and entry.category
        in {
            "bid_condition",
            "landlord_requirement",
            "permit_inspection",
            "project_fact",
            "responsibility",
            "submittal_closeout",
            "open_question",
        }
    ):
        matches.append(("general-requirements", "General Requirements"))
    if not matches and _is_actionable(text):
        disciplines = {row.document_revision.document.discipline for row in provenance}
        fallback = {
            "mechanical": ("hvac-mechanical", "HVAC / Mechanical"),
            "plumbing": ("plumbing", "Plumbing"),
            "fire_protection": ("fire-protection", "Fire Protection / Sprinklers"),
            "electrical": ("electrical-power", "Electrical Power"),
            "structural": ("structural", "Structural"),
            "low_voltage_data": ("low-voltage-data", "Low Voltage / Data"),
            "security": ("security", "Security"),
            "av": ("av", "AV"),
            "signage": ("signage", "Signage"),
        }
        matches.extend(fallback[value] for value in sorted(disciplines) if value in fallback)
    if not matches and entry.category in {
        "bid_condition",
        "landlord_requirement",
        "open_question",
        "permit_inspection",
        "responsibility",
        "submittal_closeout",
    }:
        matches.append(("general-requirements", "General Requirements"))
    if not matches and entry.category == "date_deadline" and "survey" in text:
        matches.append(("general-requirements", "General Requirements"))
    if (
        not matches
        and entry.category == "owner_third_party_item"
        and any(
            term in text
            for term in (
                "owner-supplied materials",
                "owner supplied materials",
                "landlord services",
            )
        )
    ):
        matches.append(("general-requirements", "General Requirements"))
    if (
        not matches
        and entry.category == "project_fact"
        and any(term in text for term in ("egress", "barrier-free", "occupant load"))
    ):
        matches.append(("general-requirements", "General Requirements"))
    return tuple(dict.fromkeys(matches)), text


def _canonical_item_key(entry, text, value=None):
    if (
        "landlord" in text
        and "permit" in text
        and any(term in text for term in ("obtain", "approval", "review", "coordinate", "required"))
    ):
        return "coordinate-landlord-review-and-permit-approval"
    if any(term in text for term in ("verify all dimensions", "verify dimensions on site")):
        return "verify-project-dimensions"
    return (
        re.sub(
            r"[^a-z0-9]+",
            "-",
            _normalized(
                f"{entry.finding.subject}-{entry.effective_value if value is None else value}"
            ),
        )[:140].strip("-")
        or f"entry-{entry.pk}"
    )


def _client_title(entry, description):
    subject = (entry.finding.subject or "").strip()
    normalized_subject = _normalized(subject)
    if description.strip() != (entry.effective_value or "").strip():
        return description.strip(" -")[:140] or "Scope requirement"
    if (
        subject
        and not GENERIC_SUBJECT_RE.match(normalized_subject)
        and normalized_subject not in HEADING_ONLY_VALUES
    ):
        return subject
    first_line = (description or "Scope requirement").splitlines()[0].strip(" -")
    return first_line[:140] or "Scope requirement"


def _provenance_payload(row):
    revision = row.document_revision
    return {
        "snapshot_provenance_id": row.pk,
        "document_id": revision.document_id,
        "document_title": revision.document.title,
        "document_type": revision.document.category,
        "discipline": revision.document.discipline,
        "document_revision_id": revision.pk,
        "revision_label": revision.revision_label,
        "page_number": row.document_page.page_number,
        "sheet_number": row.drawing_sheet.sheet_number if row.drawing_sheet else "",
        "evidence_excerpt": row.finding_source.evidence_excerpt,
        "visual_evidence_description": row.finding_source.visual_evidence_description,
    }


def latest_approved_snapshot(project):
    provenance = ProjectIntelligenceSnapshotProvenance.objects.select_related(
        "document_revision__document", "document_page", "drawing_sheet", "finding_source"
    )
    entries = ProjectIntelligenceSnapshotEntry.objects.select_related("finding").prefetch_related(
        Prefetch("provenance", queryset=provenance)
    )
    return (
        ProjectIntelligenceSnapshot.objects.filter(
            project=project,
            approval__isnull=False,
        )
        .select_related("approval")
        .prefetch_related(Prefetch("entries", queryset=entries))
        .order_by("-version", "-id")
        .first()
    )


def build_scope_coverage_preview(project):
    snapshot = latest_approved_snapshot(project)
    if snapshot is None:
        return None
    packages = defaultdict(dict)
    mapped_entries = set()
    non_scope = []
    unmapped = []
    coordination = []
    consolidated_duplicates = 0
    bundled_findings_split = 0
    non_actionable_clauses_removed = 0
    passive_fire_items_removed = 0
    trade_assignments_refined = 0

    entries = [entry for entry in snapshot.entries.all() if entry.included_in_intelligence]
    for entry in entries:
        provenance = list(entry.provenance.all())
        clauses = _atomic_values(entry.effective_value)
        original_destinations, _ = _classify(entry, provenance, entry.effective_value)
        original_destination_keys = {key for key, _ in original_destinations}
        clause_results = []
        for clause in clauses:
            destinations, text = _classify(entry, provenance, clause)
            clause_results.append((clause, destinations, text))
            if {key for key, _ in destinations} != original_destination_keys:
                trade_assignments_refined += 1
            original_text = _normalized(f"{entry.finding.subject} {clause}")
            if (
                _is_passive_fire_protection(original_text)
                and not _is_active_fire_protection(original_text)
                and all(key != "fire-protection" for key, _ in destinations)
            ):
                passive_fire_items_removed += 1
        actionable_results = [result for result in clause_results if result[1]]
        if len(actionable_results) > 1:
            bundled_findings_split += 1
        summary = {
            "snapshot_entry_id": entry.pk,
            "finding_id": entry.finding_id,
            "category": entry.category,
            "subject": entry.finding.subject,
            "effective_value": entry.effective_value,
        }
        if not actionable_results:
            original_text = _normalized(f"{entry.finding.subject} {entry.effective_value}")
            clause_texts = [text for _, _, text in clause_results]
            is_non_scope = all(_is_non_scope(entry, text) for text in clause_texts)
            (non_scope if is_non_scope or _is_non_scope(entry, original_text) else unmapped).append(
                summary
            )
            continue
        mapped_entries.add(entry.pk)
        non_actionable_clauses_removed += len(clauses) - len(actionable_results)
        for clause, destinations, text in actionable_results:
            clause_summary = {**summary, "effective_value": clause}
            if len(destinations) > 1:
                coordination.append(
                    {**clause_summary, "packages": [label for _, label in destinations]}
                )
            responsibility = _responsibility(text)
            for key, label in destinations:
                item_key = _canonical_item_key(entry, text, clause)
                existing = packages[(key, label)].get(item_key)
                source_rows = [_provenance_payload(row) for row in provenance]
                if existing:
                    consolidated_duplicates += 1
                    existing["coordination_required"] = (
                        existing["coordination_required"] or len(destinations) > 1
                    )
                    existing["approved_entry_ids"].append(entry.pk)
                    known = {row["snapshot_provenance_id"] for row in existing["provenance"]}
                    existing["provenance"].extend(
                        row for row in source_rows if row["snapshot_provenance_id"] not in known
                    )
                    continue
                packages[(key, label)][item_key] = {
                    "item_key": item_key,
                    "item_type": _item_type(text, key),
                    "responsibility": responsibility,
                    "coordination_required": len(destinations) > 1,
                    "category": entry.category,
                    "title": _client_title(entry, clause),
                    "description": clause,
                    "approved_entry_ids": [entry.pk],
                    "provenance": source_rows,
                }

    package_payload = []
    for (key, label), item_map in sorted(packages.items(), key=lambda value: value[0][1]):
        items = list(item_map.values())
        package_payload.append(
            {
                "trade_key": key,
                "name": label,
                "scope_item_count": len(items),
                "approved_entry_count": len(
                    {entry_id for item in items for entry_id in item["approved_entry_ids"]}
                ),
                "responsibility_counts": dict(Counter(item["responsibility"] for item in items)),
                "responsibility_explicit_count": sum(
                    item["responsibility"] != "unclear" for item in items
                ),
                "responsibility_not_stated_count": sum(
                    item["responsibility"] == "unclear" for item in items
                ),
                "source_document_count": len(
                    {source["document_id"] for item in items for source in item["provenance"]}
                ),
                "source_page_count": len(
                    {
                        (source["document_revision_id"], source["page_number"])
                        for item in items
                        for source in item["provenance"]
                    }
                ),
                "items": items,
            }
        )
    total = len(entries)
    current_generation = list(
        ScopePackage.objects.filter(project=project, lifecycle=ScopePackage.Lifecycle.ACTIVE)
        .values("trade_category")
        .annotate(item_count=Count("current_version__scope_items"))
        .order_by("trade_category")
    )
    historical_keys = {
        key
        for row in current_generation
        for key in HISTORICAL_COVERAGE.get(row["trade_category"], set())
    }
    preview_keys = {package["trade_key"] for package in package_payload}
    project_wide = next(
        (package for package in package_payload if package["trade_key"] == "general-requirements"),
        {
            "trade_key": "general-requirements",
            "name": "Project-wide Requirements",
            "scope_item_count": 0,
            "approved_entry_count": 0,
            "responsibility_counts": {},
            "responsibility_explicit_count": 0,
            "responsibility_not_stated_count": 0,
            "source_document_count": 0,
            "source_page_count": 0,
            "items": [],
        },
    )
    project_wide["name"] = "Project-wide Requirements"
    trade_packages = [
        package for package in package_payload if package["trade_key"] != "general-requirements"
    ]
    expected_coverage = []
    package_by_key = {package["trade_key"]: package for package in trade_packages}
    for key, label in EXPECTED_SCOPE_COVERAGE:
        item_count = package_by_key.get(key, {}).get("scope_item_count", 0)
        expected_coverage.append(
            {
                "trade_key": key,
                "name": label,
                "status": "found" if item_count >= 3 else "limited" if item_count else "not_found",
                "scope_item_count": item_count,
            }
        )
    all_items = [item for package in package_payload for item in package["items"]]
    responsibility_counts = Counter(item["responsibility"] for item in all_items)
    return {
        "source_snapshot_id": snapshot.pk,
        "source_snapshot_version": snapshot.version,
        "approval_id": snapshot.approval.pk,
        "taxonomy_version": PREVIEW_RULE_VERSION,
        "total_approved_entries": total,
        "proposed_package_count": len(trade_packages),
        "proposed_scope_item_count": sum(item["scope_item_count"] for item in trade_packages),
        "project_wide_requirement_count": project_wide["scope_item_count"],
        "total_requirement_count": sum(item["scope_item_count"] for item in package_payload),
        "mapped_entry_count": len(mapped_entries),
        "unmapped_entry_count": len(unmapped),
        "non_scope_informational_count": len(non_scope),
        "source_coverage_percent": round((len(mapped_entries) / total * 100) if total else 0, 1),
        "unclear_responsibility_count": responsibility_counts["unclear"],
        "coordination_entry_count": len(coordination),
        "duplicate_obligations_consolidated": consolidated_duplicates,
        "bundled_findings_split": bundled_findings_split,
        "non_actionable_clauses_removed": non_actionable_clauses_removed,
        "passive_fire_items_removed_from_sprinklers": passive_fire_items_removed,
        "trade_assignments_refined": trade_assignments_refined,
        "responsibility_counts": dict(responsibility_counts),
        "responsibility_explicit_count": len(all_items) - responsibility_counts["unclear"],
        "responsibility_not_stated_count": responsibility_counts["unclear"],
        "external_responsibility_count": sum(
            responsibility_counts[key]
            for key in ("owner_supplied", "landlord_supplied", "by_others")
        ),
        "current_generation_package_count": len(current_generation),
        "current_generation_scope_item_count": sum(row["item_count"] for row in current_generation),
        "new_package_names": [
            package["name"]
            for package in trade_packages
            if package["trade_key"] not in historical_keys
        ],
        "historical_packages_no_longer_supported": [
            row["trade_category"]
            for row in current_generation
            if not (HISTORICAL_COVERAGE.get(row["trade_category"], set()) & preview_keys)
        ],
        "packages": trade_packages,
        "project_wide_requirements": project_wide,
        "expected_scope_coverage": expected_coverage,
        "coordination_groups": coordination,
        "ambiguous_items": [item for item in unmapped if item["category"] == "open_question"],
        "unmapped_items": unmapped,
        "non_scope_informational_items": non_scope,
    }
