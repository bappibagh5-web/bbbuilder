CANONICAL_TRADE_REGISTRY = (
    ("av", "AV", ("commercial AV contractor", "audio visual contractor")),
    (
        "backing-blocking",
        "Backing / Blocking",
        ("commercial backing blocking contractor", "rough carpentry contractor"),
    ),
    (
        "civil-site",
        "Civil / Site Work",
        ("commercial civil site contractor", "site work contractor"),
    ),
    (
        "closeout",
        "Closeout",
        ("construction closeout services contractor", "commercial deficiency contractor"),
    ),
    (
        "demolition",
        "Demolition",
        ("commercial demolition contractor", "interior demolition contractor"),
    ),
    (
        "doors-frames-hardware",
        "Doors / Frames / Hardware",
        ("commercial door hardware contractor", "doors frames hardware contractor"),
    ),
    ("drywall", "Drywall", ("commercial drywall contractor", "drywall contractor")),
    (
        "electrical-power",
        "Electrical Power",
        ("commercial electrical contractor", "electrical contractor"),
    ),
    (
        "fire-alarm",
        "Fire Alarm",
        ("commercial fire alarm contractor", "fire alarm systems contractor"),
    ),
    (
        "fire-protection",
        "Fire Protection / Sprinklers",
        ("sprinkler contractor", "fire protection contractor"),
    ),
    ("flooring", "Flooring", ("commercial flooring contractor", "flooring installer")),
    (
        "glazing-storefront",
        "Glazing / Storefront",
        ("commercial glazing contractor", "storefront glass contractor"),
    ),
    (
        "hvac-mechanical",
        "HVAC / Mechanical",
        ("commercial HVAC contractor", "mechanical contractor"),
    ),
    (
        "lighting",
        "Lighting",
        ("commercial lighting contractor", "lighting installation contractor"),
    ),
    (
        "low-voltage-data",
        "Low Voltage / Data",
        ("commercial low voltage contractor", "data cabling contractor"),
    ),
    (
        "millwork",
        "Millwork",
        ("commercial millwork contractor", "architectural millwork contractor"),
    ),
    (
        "miscellaneous-metals",
        "Miscellaneous Metals",
        ("miscellaneous metals contractor", "commercial metal fabrication contractor"),
    ),
    (
        "mudding-taping",
        "Mudding & Taping",
        ("commercial drywall finishing contractor", "mudding taping contractor"),
    ),
    (
        "painting-finishes",
        "Painting / Finishes",
        ("commercial painting contractor", "commercial finishes contractor"),
    ),
    ("plumbing", "Plumbing", ("commercial plumber", "plumbing contractor")),
    ("roofing", "Roofing", ("commercial roofing contractor", "roofing contractor")),
    (
        "security",
        "Security",
        ("commercial security systems contractor", "security installation contractor"),
    ),
    ("signage", "Signage", ("commercial signage contractor", "sign installation contractor")),
    (
        "specialties",
        "Specialties",
        ("commercial building specialties contractor", "architectural specialties contractor"),
    ),
    (
        "steel-stud-framing",
        "Steel Stud Framing",
        ("metal stud framing contractor", "commercial framing contractor"),
    ),
    (
        "structural",
        "Structural",
        ("commercial structural contractor", "structural steel contractor"),
    ),
    (
        "act-ceilings",
        "T-Bar / ACT Ceilings",
        ("acoustic ceiling contractor", "suspended ceiling contractor"),
    ),
)

TRADE_CHOICES = tuple((key, label) for key, label, _ in CANONICAL_TRADE_REGISTRY)
TRADE_QUERY_TERMS = {key: terms for key, _, terms in CANONICAL_TRADE_REGISTRY}
CONTRACTOR_ELIGIBLE_TRADE_KEYS = frozenset(TRADE_QUERY_TERMS)
