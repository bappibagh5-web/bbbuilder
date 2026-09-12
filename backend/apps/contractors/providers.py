import json
import logging
import math
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Protocol

from django.conf import settings

from apps.scope_packages.trades import TRADE_QUERY_TERMS

GOOGLE_PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GOOGLE_PLACES_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.addressComponents",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.primaryType",
        "places.types",
        "places.rating",
        "places.userRatingCount",
        "places.location",
    )
)
GOOGLE_PLACES_TIMEOUT_SECONDS = 30
GOOGLE_PLACES_PAGE_SIZE = 20
GOOGLE_MAX_PAGES_PER_QUERY = 2
GOOGLE_MAX_REQUESTS = 4
BUSINESS_RADIUS_MILES = 200
EARTH_RADIUS_MILES = 3958.7613

logger = logging.getLogger(__name__)


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
    postal_code: str = ""
    country: str = "Canada"
    external_place_id: str = ""
    latitude: float | None = None
    longitude: float | None = None
    distance_miles: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SearchCenter:
    latitude: float
    longitude: float
    reference: str


@dataclass(frozen=True)
class ContractorSearchOutcome:
    results: tuple[ContractorResult, ...]
    metadata: dict


class ContractorDiscoveryProvider(Protocol):
    name: str

    def resolve_center(self, *, location_query): ...

    def search(self, *, trade_key, city, province, country, center, radius_miles, keywords): ...


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
    location = place.get("location") if isinstance(place.get("location"), dict) else {}
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        latitude = longitude = None
    if isinstance(place.get("rating"), (int, float)):
        metadata["rating"] = place["rating"]
    if isinstance(place.get("userRatingCount"), int):
        metadata["review_count"] = place["userRatingCount"]
    components = place.get("addressComponents", [])

    def address_part(*wanted_types, short=False):
        for component in components if isinstance(components, list) else []:
            types = component.get("types", [])
            if any(item in types for item in wanted_types):
                return component.get("shortText" if short else "longText", "").strip()
        return ""

    return ContractorResult(
        display_name=display_name,
        city=address_part("locality", "postal_town") or city,
        province=address_part("administrative_area_level_1", short=True) or province,
        country=address_part("country")
        or ("Canada" if country.strip().upper() == "CA" else country),
        postal_code=address_part("postal_code"),
        address=place.get("formattedAddress", "").strip(),
        phone=place.get("nationalPhoneNumber", "").strip(),
        website=place.get("websiteUri", "").strip(),
        external_place_id=place_id,
        latitude=latitude,
        longitude=longitude,
        metadata=metadata,
    )


def great_circle_miles(lat1, lon1, lat2, lon2):
    values = tuple(map(math.radians, (lat1, lon1, lat2, lon2)))
    lat1r, lon1r, lat2r, lon2r = values
    delta_lat = lat2r - lat1r
    delta_lon = lon2r - lon1r
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1r) * math.cos(lat2r) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1, math.sqrt(haversine)))


def bounding_rectangle(center, radius_miles):
    latitude_delta = radius_miles / 69.0
    longitude_scale = max(math.cos(math.radians(center.latitude)), 0.1)
    longitude_delta = radius_miles / (69.172 * longitude_scale)
    return {
        "low": {
            "latitude": max(-90, center.latitude - latitude_delta),
            "longitude": max(-180, center.longitude - longitude_delta),
        },
        "high": {
            "latitude": min(90, center.latitude + latitude_delta),
            "longitude": min(180, center.longitude + longitude_delta),
        },
    }


class FakeContractorDiscoveryProvider:
    name = "fake"

    def resolve_center(self, *, location_query):
        return SearchCenter(49.2827, -123.1207, location_query)

    def search(
        self, *, trade_key, city, province, country="Canada", center, radius_miles, keywords
    ):
        label = trade_key.replace("-", " ").title()
        return ContractorSearchOutcome(
            results=(
                ContractorResult(
                    display_name=f"Demo {label} Contractors",
                    city=city,
                    province=province,
                    country=country,
                    website=f"https://demo-{trade_key}.invalid",
                    phone="604-555-0100",
                    external_place_id=f"fake-{trade_key}-{city.casefold()}",
                    latitude=center.latitude,
                    longitude=center.longitude,
                    distance_miles=0,
                    metadata={"fixture": True},
                ),
            ),
            metadata={
                "provider_request_count": 0,
                "raw_result_count": 1,
                "outside_radius_filtered_count": 0,
                "deduplicated_count": 0,
            },
        )


class GooglePlacesContractorDiscoveryProvider:
    name = "google_places"

    def __init__(self, *, api_key=None, opener=None):
        self.api_key = api_key if api_key is not None else settings.GOOGLE_PLACES_API_KEY
        self.opener = opener or urllib.request.urlopen

    def _request(self, payload, field_mask=GOOGLE_PLACES_FIELD_MASK):
        request = urllib.request.Request(
            GOOGLE_PLACES_TEXT_SEARCH_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": field_mask,
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=GOOGLE_PLACES_TIMEOUT_SECONDS) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise ValueError("Unexpected provider response shape.")
                return result
        except urllib.error.HTTPError as error:
            provider_status = "unknown"
            try:
                error_payload = json.loads(error.read().decode("utf-8"))
                provider_status = str(error_payload.get("error", {}).get("status", "unknown"))
            except (UnicodeDecodeError, ValueError, AttributeError):
                pass
            logger.warning(
                "Google Places request failed: http_status=%s provider_status=%s",
                error.code,
                provider_status,
            )
            raise ContractorProviderError(
                "Google contractor search is temporarily unavailable."
            ) from error
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            logger.warning("Google Places request failed: category=%s", type(error).__name__)
            raise ContractorProviderError(
                "Google contractor search is temporarily unavailable."
            ) from error

    def resolve_center(self, *, location_query):
        if not self.api_key:
            raise ContractorProviderError("Contractor search is not configured.")
        payload = self._request(
            {"textQuery": location_query, "pageSize": 1, "languageCode": "en", "regionCode": "CA"},
            "places.id,places.formattedAddress,places.location",
        )
        places = payload.get("places", [])
        if not places:
            raise ContractorProviderError("The project location could not be resolved.")
        place = places[0]
        location = place.get("location", {})
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            raise ContractorProviderError("The project location could not be resolved.")
        return SearchCenter(latitude, longitude, place.get("formattedAddress", location_query))

    def search(
        self, *, trade_key, city, province, country="Canada", center, radius_miles, keywords
    ):
        queries = build_search_queries(
            trade_key=trade_key,
            city=city,
            province=province,
            country=country,
            keywords=keywords,
        )
        if not queries:
            raise ContractorProviderError(
                "This scope trade is not available for contractor search."
            )
        if not self.api_key:
            raise ContractorProviderError("Contractor search is not configured.")

        results = []
        seen_place_ids = set()
        raw_result_count = 0
        outside_radius = 0
        duplicates = 0
        request_count = 0
        partial_failure_count = 0
        rectangle = bounding_rectangle(center, radius_miles)
        for query in queries:
            page_token = None
            for _ in range(GOOGLE_MAX_PAGES_PER_QUERY):
                if request_count >= GOOGLE_MAX_REQUESTS:
                    break
                request_payload = {
                    "textQuery": query,
                    "pageSize": GOOGLE_PLACES_PAGE_SIZE,
                    "languageCode": "en",
                    "regionCode": "CA" if country.casefold() == "canada" else country[:2].upper(),
                    "includePureServiceAreaBusinesses": True,
                    "locationRestriction": {"rectangle": rectangle},
                }
                if page_token:
                    request_payload["pageToken"] = page_token
                request_count += 1
                try:
                    payload = self._request(request_payload)
                except ContractorProviderError:
                    if not results:
                        raise
                    partial_failure_count += 1
                    break
                places = payload.get("places", [])
                raw_result_count += len(places)
                for place in places:
                    result = map_google_place(
                        place, city=city, province=province, country=country, query=query
                    )
                    if result is None or result.latitude is None or result.longitude is None:
                        outside_radius += 1
                        continue
                    distance = great_circle_miles(
                        center.latitude, center.longitude, result.latitude, result.longitude
                    )
                    if distance > radius_miles:
                        outside_radius += 1
                        continue
                    if result.external_place_id in seen_place_ids:
                        duplicates += 1
                        continue
                    seen_place_ids.add(result.external_place_id)
                    results.append(
                        replace(
                            result,
                            distance_miles=round(distance, 1),
                            metadata={**result.metadata, "distance_miles": round(distance, 1)},
                        )
                    )
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
        return ContractorSearchOutcome(
            results=tuple(results),
            metadata={
                "provider_request_count": request_count,
                "raw_result_count": raw_result_count,
                "outside_radius_filtered_count": outside_radius,
                "deduplicated_count": duplicates,
                "partial_failure_count": partial_failure_count,
            },
        )


def provider_for(name):
    if name == "fake":
        return FakeContractorDiscoveryProvider()
    if name == "google_places":
        return GooglePlacesContractorDiscoveryProvider()
    raise ContractorProviderError("Contractor search provider is not configured.")
