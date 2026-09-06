from dataclasses import dataclass

from .models import Company, ScopeContractorCandidate

EXACT_TRADE_WEIGHT = 30
LOCAL_CITY_WEIGHT = 20
INTERNAL_NETWORK_WEIGHT = 18
WEBSITE_WEIGHT = 5
PHONE_WEIGHT = 5
SHORTLISTED_WEIGHT = 5


@dataclass(frozen=True)
class CandidateRanking:
    score: int
    reasons: tuple[str, ...]
    google_rating: float | None
    google_review_count: int | None


def _matching_capability(candidate):
    capabilities = candidate.company.trade_capabilities.all()
    return next(
        (
            capability
            for capability in capabilities
            if capability.is_active and capability.trade_key == candidate.scope_package.trade_key
        ),
        None,
    )


def _google_quality(capability):
    if capability is None or capability.source_type != Company.Source.DISCOVERED:
        return None, None
    metadata = capability.source_metadata if isinstance(capability.source_metadata, dict) else {}
    rating = metadata.get("rating")
    review_count = metadata.get("review_count")
    if isinstance(rating, bool) or not isinstance(rating, (int, float)):
        rating = None
    if isinstance(review_count, bool) or not isinstance(review_count, int):
        review_count = None
    return float(rating) if rating is not None else None, review_count


def rank_candidate(candidate: ScopeContractorCandidate) -> CandidateRanking:
    score = 0
    reasons = []
    capability = _matching_capability(candidate)
    rating, review_count = _google_quality(capability)

    if capability is not None:
        score += EXACT_TRADE_WEIGHT
        reasons.append("Exact trade match")
    if (
        candidate.company.city
        and candidate.project.city
        and candidate.company.city.casefold() == candidate.project.city.casefold()
    ):
        score += LOCAL_CITY_WEIGHT
        reasons.append("Local to project")
    if candidate.company.source_type == Company.Source.INTERNAL:
        score += INTERNAL_NETWORK_WEIGHT
        reasons.append("Internal network")
    if candidate.company.website:
        score += WEBSITE_WEIGHT
        reasons.append("Website available")
    if candidate.company.phone:
        score += PHONE_WEIGHT
        reasons.append("Phone available")
    if rating is not None:
        if rating >= 4.5:
            score += 12
            reasons.append("Strong Google rating")
        elif rating >= 4.0:
            score += 8
            reasons.append("Positive Google rating")
        elif rating >= 3.5:
            score += 4
            reasons.append("Google rating signal")
    if review_count is not None:
        if review_count >= 100:
            score += 10
            reasons.append("Established review history")
        elif review_count >= 25:
            score += 6
            reasons.append("Established review history")
        elif review_count >= 5:
            score += 3
            reasons.append("Review history available")
    if candidate.status == ScopeContractorCandidate.Status.SHORTLISTED:
        score += SHORTLISTED_WEIGHT
        reasons.append("Shortlisted by BB Builders")

    return CandidateRanking(
        score=min(score, 100),
        reasons=tuple(reasons),
        google_rating=rating,
        google_review_count=review_count,
    )
