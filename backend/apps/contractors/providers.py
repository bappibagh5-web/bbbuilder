import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings

GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACES_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.primaryType",
        "places.types",
        "places.rating",
        "places.userRatingCount",
    )
)
GOOGLE_PLACES_TIMEOUT_SECONDS = 30
GOOGLE_PLACES_PAGE_SIZE = 10

TRADE_QUERY_TERMS = {
    "hvac-mechanical": ("commercial HVAC contractor", "mechanical contractor"),
    "plumbing": ("commercial plumber", "plumbing contractor"),
    "fire-protection": ("sprinkler contractor", "fire protection contractor"),
    "general-requirements": (),
}


class ContractorProviderError(RuntimeError):
    """Safe provider error whose message may cross the API boundary."""


@dataclass(frozen=True)
class ContractorResult:
    display_name: str
    city: str
    province: str
    website: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    country: str = "Canada"
    external_place_id: str = ""
    metadata: dict = field(default_factory=dict)


class ContractorDiscoveryProvider(Protocol):
    name: str

    def search(self, *, trade_key, city, province, country, radius_km, keywords): ...


def trade_query_terms(trade_key):
    return TRADE_QUERY_TERMS.get(trade_key, ())


def build_search_queries(*, trade_key, city, province, country, keywords):
    country_name = "Canada" if country.strip().upper() == "CA" else country.strip()
    location = " ".join(part.strip() for part in (city, province, country_name) if part.strip())
    additions = " ".join(dict.fromkeys(item.strip() for item in keywords if item.strip()))
    return [
        " ".join(part for part in (term, additions, location) if part)
        for term in trade_query_terms(trade_key)
    ]


def map_google_place(place, *, city, province, country, query):
    display_name = place.get("displayName", {}).get("text", "").strip()
    place_id = place.get("id", "").strip()
    if not display_name or not place_id:
        return None
    metadata = {
        "query": query,
        "primary_type": place.get("primaryType", ""),
        "types": place.get("types", [])[:10],
    }
    if isinstance(place.get("rating"), (int, float)):
        metadata["rating"] = place["rating"]
    if isinstance(place.get("userRatingCount"), int):
        metadata["review_count"] = place["userRatingCount"]
    return ContractorResult(
        display_name=display_name,
        city=city,
        province=province,
        country="Canada" if country.strip().upper() == "CA" else country,
        address=place.get("formattedAddress", "").strip(),
        phone=place.get("nationalPhoneNumber", "").strip(),
        website=place.get("websiteUri", "").strip(),
        external_place_id=place_id,
        metadata=metadata,
    )


class FakeContractorDiscoveryProvider:
    name = "fake"

    def search(self, *, trade_key, city, province, country="Canada", radius_km, keywords):
        label = trade_key.replace("-", " ").title()
        return [
            ContractorResult(
                display_name=f"Demo {label} Contractors",
                city=city,
                province=province,
                country=country,
                website=f"https://demo-{trade_key}.invalid",
                phone="604-555-0100",
                external_place_id=f"fake-{trade_key}-{city.casefold()}",
                metadata={"fixture": True},
            )
        ]


class GooglePlacesContractorDiscoveryProvider:
    name = "google_places"

    def __init__(self, *, api_key=None, opener=None):
        self.api_key = api_key if api_key is not None else settings.GOOGLE_PLACES_API_KEY
        self.opener = opener or urllib.request.urlopen

    def search(self, *, trade_key, city, province, country="Canada", radius_km, keywords):
        queries = build_search_queries(
            trade_key=trade_key,
            city=city,
            province=province,
            country=country,
            keywords=keywords,
        )
        if not queries:
            return []
        if not self.api_key:
            raise ContractorProviderError("Contractor search is not configured.")

        results = []
        seen_place_ids = set()
        for query in queries:
            request = urllib.request.Request(
                GOOGLE_PLACES_TEXT_SEARCH_URL,
                data=json.dumps(
                    {
                        "textQuery": query,
                        "pageSize": GOOGLE_PLACES_PAGE_SIZE,
                        "languageCode": "en",
                        "regionCode": "CA"
                        if country.casefold() == "canada"
                        else country[:2].upper(),
                        "includePureServiceAreaBusinesses": True,
                    }
                ).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": GOOGLE_PLACES_FIELD_MASK,
                },
                method="POST",
            )
            try:
                with self.opener(request, timeout=GOOGLE_PLACES_TIMEOUT_SECONDS) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError("Unexpected provider response shape.")
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                ValueError,
            ) as error:
                raise ContractorProviderError(
                    "Contractor search is temporarily unavailable."
                ) from error
            for place in payload.get("places", []):
                result = map_google_place(
                    place, city=city, province=province, country=country, query=query
                )
                if result and result.external_place_id not in seen_place_ids:
                    seen_place_ids.add(result.external_place_id)
                    results.append(result)
        return results


def provider_for(name):
    if name == "fake":
        return FakeContractorDiscoveryProvider()
    if name == "google_places":
        return GooglePlacesContractorDiscoveryProvider()
    raise ContractorProviderError("Contractor search provider is not configured.")
