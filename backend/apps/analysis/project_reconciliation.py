import re
from collections import Counter, defaultdict

TRADE_BY_DISCIPLINE = {
    "architectural": "Architectural / Interiors",
    "structural": "Structural",
    "mechanical": "HVAC / Mechanical",
    "plumbing": "Plumbing",
    "electrical": "Electrical",
    "fire_protection": "Fire Protection / Sprinkler",
    "low_voltage": "Low Voltage / Data",
    "security": "Security",
    "av": "AV",
    "civil": "Civil / Site",
    "roofing": "Roofing",
    "interiors": "Architectural / Interiors",
}

TRADE_TERMS = (
    ("Fire Protection / Sprinkler", ("sprinkler", "fire protection", "nfpa 13")),
    ("Plumbing", ("plumbing", "sanitary", "lavatory", "water closet", "floor drain")),
    ("HVAC / Mechanical", ("hvac", "duct", "ventilation", "diffuser", "thermostat", "air balance")),
    ("Electrical", ("electrical", "lighting", "luminaire", "receptacle", "panelboard", "power")),
    ("Low Voltage / Data", ("data cabling", "low voltage", "structured cabling", "network")),
    ("Security", ("security", "cctv", "access control", "eas")),
    ("Structural", ("structural", "steel", "joist", "beam", "seismic")),
    (
        "Architectural / Interiors",
        ("architectural", "partition", "ceiling", "flooring", "millwork", "door"),
    ),
)

TOPIC_TERMS = (
    ("demolition", ("demol", "remove existing")),
    ("existing-work", ("existing to remain", "relocate", "reuse", "re-use")),
    (
        "supply-install",
        ("supply and install", "supply & install", "provide and install", "furnish and install"),
    ),
    ("testing-commissioning", ("test", "commission", "balance", "inspection")),
    ("permit", ("permit", "authority having jurisdiction", " ahj")),
    ("submittal", ("submittal", "shop drawing", "product data")),
    ("closeout", ("closeout", "as-built", "warranty", "operation and maintenance")),
    ("coordination", ("coordinate", "coordination", "interface", "conflict")),
    ("owner-landlord", ("owner supplied", "landlord", "by owner")),
    ("schedule", ("deadline", "schedule", "duration", "lead time")),
    ("commercial", ("price", "cost", "allowance", "tax", "payment")),
)

ACTION_TERMS = tuple(term for _, terms in TOPIC_TERMS for term in terms) + (
    "install",
    "provide",
    "furnish",
    "connect",
    "disconnect",
    "protect",
    "submit",
)

CONTACT_TERMS = (
    "contact",
    "email",
    "e-mail",
    "telephone",
    "phone",
    "website",
    "www.",
    "sales representative",
    "design@",
)

SCOPE_IMPACT_TERMS = ACTION_TERMS + (
    "required",
    "responsible",
    "warranty",
    "lead time",
    "delivery",
    "payment",
    "price",
    "cost",
)

DEADLINE_TERMS = (
    "bid deadline",
    "tender close",
    "submission deadline",
    "due date",
    "completion deadline",
    "milestone",
)

ISSUE_REVISION_TERMS = (
    "issue date",
    "issued for construction",
    "issued for permit",
    "revision date",
    "rev date",
    "revised",
    "manufacturer revision",
    "specification revision",
)

AMBIGUOUS_RESPONSIBILITY_TERMS = (
    "tbc",
    "to be confirmed",
    "not specified",
    "not stated",
    "unclear",
    "unknown",
    "who is responsible",
    "confirm responsibility",
)


def _normalized(value):
    return " ".join(str(value or "").casefold().split())


def _trade_for(document, candidate):
    text = _normalized(f"{candidate.get('subject', '')} {candidate.get('value', '')}")
    for trade, terms in TRADE_TERMS:
        if any(term in text for term in terms):
            return trade
    return TRADE_BY_DISCIPLINE.get(document.discipline, "General Requirements")


def _topic_for(candidate):
    text = _normalized(f"{candidate.get('subject', '')} {candidate.get('value', '')}")
    for topic, terms in TOPIC_TERMS:
        if any(term in text for term in terms):
            return topic
    return candidate.get("category", "project_fact")


def _value_field(candidate):
    text = _normalized(f"{candidate.get('subject', '')} {candidate.get('value', '')}")
    ordered_fields = (
        ("contact-reference", CONTACT_TERMS),
        ("warranty", ("warranty", "guarantee", "defect period")),
        ("payment-terms", ("net 30", "payment", "deposit", "invoice")),
        ("shipping-delivery", ("shipping", "delivery", "freight", "lead time")),
        ("pricing", ("price", "pricing", "cost", "quotation", "quote", "allowance")),
        ("product-compatibility", ("compatible", "compatibility", "approved equal")),
        ("drawing-coordination", ("drawing", "coordinate", "coordination", "verify on site")),
        ("submittal", ("submittal", "shop drawing", "product data")),
        ("closeout", ("closeout", "as-built", "operation and maintenance", "o&m")),
        ("permit-inspection", ("permit", "inspection", "authority having jurisdiction")),
        ("owner-landlord", ("owner supplied", "landlord", "by owner")),
        ("supply-install", ("supply and install", "provide and install", "furnish and install")),
        ("install-only", ("install only", "owner supplied contractor installed")),
        ("existing-relocate", ("existing to remain", "relocate", "reuse", "re-use")),
    )
    for field, terms in ordered_fields:
        if any(term in text for term in terms):
            return field
    return _topic_for(candidate)


def _supporting_only(priority, document, candidate):
    text = _normalized(f"{candidate.get('subject', '')} {candidate.get('value', '')}")
    contact_reference = any(term in text for term in CONTACT_TERMS) and not any(
        term in text for term in SCOPE_IMPACT_TERMS
    )
    passive_product_fact = (
        (priority == "generic_supporting" or document.category == "specifications")
        and candidate.get("category") == "project_fact"
        and not any(term in text for term in ACTION_TERMS)
    )
    issue_or_revision_metadata = (
        candidate.get("category") == "date_deadline"
        and any(term in text for term in ISSUE_REVISION_TERMS)
        and not any(term in text for term in DEADLINE_TERMS)
    )
    manufacturer_revision_metadata = (
        any(term in text for term in ("manufacturer", "product", "specification", "catalog"))
        and any(term in text for term in ("revision", "revised", "rev date"))
        and not any(term in text for term in SCOPE_IMPACT_TERMS)
    )
    return (
        contact_reference
        or passive_product_fact
        or issue_or_revision_metadata
        or manufacturer_revision_metadata
    )


def _triaged_support(candidate):
    text = _normalized(f"{candidate.get('subject', '')} {candidate.get('value', '')}")
    responsibility_categories = {
        "responsibility",
        "owner_third_party_item",
        "landlord_requirement",
    }
    if candidate.get("category") in responsibility_categories and any(
        term in text for term in AMBIGUOUS_RESPONSIBILITY_TERMS
    ):
        return "uncertain"
    return candidate.get("support", "uncertain")


def _ground_evidence(page, task, evidence):
    sheet = getattr(page, "drawing_sheet", None)
    if (
        evidence.get("document_page_id") != page.pk
        or evidence.get("page_number") != page.page_number
        or evidence.get("drawing_sheet_id") not in (None, sheet.pk if sheet else None)
    ):
        return None
    excerpt = evidence.get("evidence_excerpt", "")
    if excerpt:
        if excerpt in page.native_text:
            return evidence
        chunks = excerpt.split()
        if not chunks:
            return None
        matches = list(
            re.finditer(r"\s+".join(re.escape(chunk) for chunk in chunks), page.native_text)
        )
        if len(matches) != 1:
            if evidence.get("visual_evidence_description") and task.input_mode in (
                "vision",
                "native_text_vision",
            ):
                return {**evidence, "evidence_excerpt": ""}
            return None
        return {**evidence, "evidence_excerpt": matches[0].group(0)}
    if evidence.get("visual_evidence_description") and task.input_mode in (
        "vision",
        "native_text_vision",
    ):
        return evidence
    return None


def reconcile_project_set_page_results(run):
    """Consolidate saved grounded page candidates without mutating the run."""
    manifest = {item["document_id"]: item for item in run.input_manifest.get("documents", [])}
    records = []
    dispositions = Counter(
        {
            "duplicate": 0,
            "invalid": 0,
            "supporting_only": 0,
            "consolidated": 0,
        }
    )
    source_candidate_count = 0
    source_reference_count = 0
    omissions = []
    seen = {}
    tasks = run.task_runs.filter(task_type="page_analysis", status="succeeded").select_related(
        "document_page__drawing_sheet", "document_page__document_revision__document"
    )
    for task in tasks:
        page = task.document_page
        document = page.document_revision.document
        priority = manifest.get(document.pk, {}).get("source_priority", "generic_supporting")
        for candidate_index, candidate in enumerate(
            (task.structured_result or {}).get("candidates", []), start=1
        ):
            source_candidate_count += 1
            source_reference_count += len(candidate.get("evidence", []))
            source_ref = {"task_id": task.pk, "candidate_index": candidate_index}
            evidence = []
            for item in candidate.get("evidence", []):
                grounded = _ground_evidence(page, task, item)
                if grounded is not None:
                    evidence.append(grounded)
            if not evidence:
                dispositions["invalid"] += 1
                omissions.append({**source_ref, "reason": "invalid"})
                continue
            if _supporting_only(priority, document, candidate):
                dispositions["supporting_only"] += 1
                omissions.append({**source_ref, "reason": "supporting_only"})
                continue
            identity = (
                candidate.get("category", ""),
                _normalized(candidate.get("subject")),
                _normalized(candidate.get("value")),
            )
            if identity in seen:
                record = seen[identity]
                record["evidence"].extend(
                    item for item in evidence if item not in record["evidence"]
                )
                record["document_ids"].add(document.pk)
                record["disciplines"].add(document.discipline or "unknown")
                dispositions["duplicate"] += 1
                omissions.append({**source_ref, "reason": "duplicate"})
                continue
            record = {
                "candidate": {**candidate, "support": _triaged_support(candidate)},
                "evidence": evidence,
                "trade": _trade_for(document, candidate),
                "topic": _topic_for(candidate),
                "field": _value_field(candidate),
                "obligation": (
                    _normalized(candidate.get("subject"))
                    if candidate.get("category")
                    in {"responsibility", "owner_third_party_item", "landlord_requirement"}
                    else ""
                ),
                "source_entity": (
                    f"document:{document.pk}"
                    if priority in {"generic_supporting", "project_supporting"}
                    else "project"
                ),
                "document_ids": {document.pk},
                "disciplines": {document.discipline or "unknown"},
                "source_ref": source_ref,
            }
            seen[identity] = record
            records.append(record)

    groups = defaultdict(list)
    for record in records:
        groups[
            (
                record["trade"],
                record["candidate"]["category"],
                record["topic"],
                record["field"],
                record["obligation"],
                record["source_entity"],
            )
        ].append(record)
    items = []
    for (
        trade,
        category,
        topic,
        _field,
        _obligation,
        _source_entity,
    ), members in sorted(groups.items()):
        chunk, size, evidence_count = [], 0, 0
        max_chunk_size = (
            1
            if category
            in {
                "date_deadline",
                "open_question",
            }
            else 4
        )
        for member in members:
            value_size = len(member["candidate"]["value"].strip()) + 3
            member_evidence = len(member["evidence"])
            if chunk and (
                len(chunk) >= max_chunk_size
                or size + value_size > 1800
                or evidence_count + member_evidence > 100
            ):
                items.append(_consolidate_chunk(trade, category, topic, chunk))
                dispositions["consolidated"] += len(chunk) - 1
                omissions.extend(
                    {**member["source_ref"], "reason": "consolidated"} for member in chunk[1:]
                )
                chunk, size, evidence_count = [], 0, 0
            chunk.append(member)
            size += value_size
            evidence_count += member_evidence
        if chunk:
            items.append(_consolidate_chunk(trade, category, topic, chunk))
            dispositions["consolidated"] += len(chunk) - 1
            omissions.extend(
                {**member["source_ref"], "reason": "consolidated"} for member in chunk[1:]
            )

    coverage = {
        "documents": Counter(),
        "disciplines": Counter(),
        "trades": Counter(),
        "categories": Counter(),
    }
    for document_id, item in manifest.items():
        coverage["documents"][document_id] = 0
        coverage["disciplines"][item.get("discipline") or "unknown"] += 0
    for item in items:
        coverage["trades"][item["trade"]] += 1
        coverage["categories"][item["candidate"]["category"]] += 1
        for value in item["disciplines"]:
            coverage["disciplines"][value] += 1
        for value in item["document_ids"]:
            coverage["documents"][value] += 1
    return {
        "candidates": [item["candidate"] for item in items],
        "items": items,
        "dispositions": dict(dispositions),
        "omissions": omissions,
        "coverage": {key: dict(value) for key, value in coverage.items()},
        "source_candidate_count": source_candidate_count,
        "source_reference_count": source_reference_count,
        "grounded_candidate_count": len(records),
        "consolidated_finding_count": len(items),
        "provenance_reference_count": sum(len(item["candidate"]["evidence"]) for item in items),
    }


def _consolidate_chunk(trade, category, topic, members):
    values = list(dict.fromkeys(member["candidate"]["value"].strip() for member in members))
    evidence = []
    for member in members:
        for item in member["evidence"]:
            if item not in evidence:
                evidence.append(item)
    subject = (
        members[0]["candidate"]["subject"]
        if len(members) == 1
        else f"{trade}: {topic.replace('-', ' ')}"
    )
    support_order = {"explicit": 0, "strongly_supported": 1, "inferred": 2, "uncertain": 3}
    return {
        "trade": trade,
        "topic": topic,
        "document_ids": sorted({value for member in members for value in member["document_ids"]}),
        "disciplines": sorted({value for member in members for value in member["disciplines"]}),
        "candidate": {
            "category": category,
            "subject": subject[:200],
            "value": "\n- ".join(values)[:2000],
            "support": max(
                (member["candidate"]["support"] for member in members),
                key=lambda value: support_order[value],
            ),
            "evidence": evidence[:100],
        },
    }
