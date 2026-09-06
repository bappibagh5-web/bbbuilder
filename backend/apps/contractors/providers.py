from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ContractorResult:
    display_name: str
    city: str
    province: str
    website: str = ""
    phone: str = ""
    email: str = ""
    external_place_id: str = ""
    metadata: dict = field(default_factory=dict)


class ContractorDiscoveryProvider(Protocol):
    name: str

    def search(self, *, trade_key, city, province, radius_km, keywords): ...


class FakeContractorDiscoveryProvider:
    name = "fake"

    def search(self, *, trade_key, city, province, radius_km, keywords):
        label = trade_key.replace("-", " ").title()
        return [
            ContractorResult(
                display_name=f"Demo {label} Contractors",
                city=city,
                province=province,
                website=f"https://demo-{trade_key}.invalid",
                phone="604-555-0100",
                external_place_id=f"fake-{trade_key}-{city.casefold()}",
                metadata={"fixture": True},
            )
        ]


class GooglePlacesContractorDiscoveryProvider:
    name = "google_places"

    def search(self, **kwargs):
        raise RuntimeError("Google Places contractor discovery is not configured.")


def provider_for(name):
    if name == "fake":
        return FakeContractorDiscoveryProvider()
    if name == "google_places":
        return GooglePlacesContractorDiscoveryProvider()
    raise RuntimeError("Unsupported contractor discovery provider.")
