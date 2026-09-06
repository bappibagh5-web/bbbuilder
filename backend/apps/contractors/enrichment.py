import ipaddress
import re
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from django.conf import settings

from .services import normalize_phone

MAX_RESPONSE_BYTES = 1_048_576
CONTACT_PATH_WORDS = ("contact", "team", "staff", "about", "people")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


class PublicPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text_parts = []
        self._href = None
        self._anchor_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href", "")
            self._anchor_parts = []

    def handle_data(self, data):
        value = " ".join(data.split())
        if value:
            self.text_parts.append(value)
            if self._href is not None:
                self._anchor_parts.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._anchor_parts).strip()))
            self._href = None
            self._anchor_parts = []


def _public_hostname(hostname):
    if not hostname:
        return False
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            return False
    return True


def _safe_public_url(value, *, expected_hostname=None):
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if expected_hostname and parsed.hostname.casefold().removeprefix(
        "www."
    ) != expected_hostname.casefold().removeprefix("www."):
        return False
    return _public_hostname(parsed.hostname)


def fetch_public_html(url):
    if not _safe_public_url(url):
        return None
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BB-Builders-Contact-Discovery/1.0"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.CONTACT_ENRICHMENT_TIMEOUT_SECONDS
        ) as response:
            final_url = response.geturl()
            source_host = urlparse(url).hostname
            if not _safe_public_url(final_url, expected_hostname=source_host):
                return None
            if "text/html" not in response.headers.get("Content-Type", "").casefold():
                return None
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return None
            charset = response.headers.get_content_charset() or "utf-8"
            return final_url, body.decode(charset, errors="replace")
    except (OSError, ValueError, urllib.error.URLError):
        return None


def _source_label(url, root_url):
    if url == root_url:
        return "Company website"
    path = urlparse(url).path.casefold()
    if "team" in path or "staff" in path or "people" in path:
        return "Team page"
    if "contact" in path:
        return "Contact page"
    return "Company website"


def _name_and_title(anchor, email):
    clean = " ".join(anchor.split()).strip(" -|:")
    generic = {"email", "contact", "contact us", "send email", email.casefold()}
    if not clean or clean.casefold() in generic or "@" in clean:
        local = email.split("@", 1)[0].casefold()
        title = (
            "Estimating"
            if any(word in local for word in ("estimating", "bids", "quotes", "tenders"))
            else "General inquiries"
        )
        return title, title
    parts = clean.split()
    if 2 <= len(parts) <= 5 and all(re.search(r"[A-Za-z]", part) for part in parts):
        return clean, ""
    return "General inquiries", ""


def enrich_company_contacts(company, *, fetcher=fetch_public_html):
    root_url = company.website.strip()
    if not root_url:
        return {"suggestions": [], "pages_checked": []}
    if "://" not in root_url:
        root_url = f"https://{root_url}"
    root_host = urlparse(root_url).hostname
    pending = [root_url]
    visited = []
    pages = []
    while pending and len(visited) < settings.CONTACT_ENRICHMENT_MAX_PAGES:
        url = pending.pop(0)
        if url in visited:
            continue
        visited.append(url)
        fetched = fetcher(url)
        if not fetched:
            continue
        final_url, html = fetched
        parser = PublicPageParser()
        parser.feed(html)
        pages.append((final_url, parser))
        for href, label in parser.links:
            candidate = urljoin(final_url, href.split("#", 1)[0])
            searchable = f"{urlparse(candidate).path} {label}".casefold()
            if (
                any(word in searchable for word in CONTACT_PATH_WORDS)
                and candidate not in visited
                and candidate not in pending
                and _safe_public_url(candidate, expected_hostname=root_host)
            ):
                pending.append(candidate)

    suggestions = []
    existing_emails = {
        value.casefold()
        for value in company.contacts.exclude(email="").values_list("email", flat=True)
    }
    existing_phones = {
        normalize_phone(value)
        for value in company.contacts.exclude(phone="").values_list("phone", flat=True)
    }
    seen_emails = set()
    for page_url, parser in pages:
        page_emails = []
        mail_anchors = {}
        phones = []
        for href, label in parser.links:
            if href.casefold().startswith("mailto:"):
                email = href[7:].split("?", 1)[0].strip()
                if EMAIL_RE.fullmatch(email):
                    page_emails.append(email)
                    mail_anchors[email.casefold()] = label
            elif href.casefold().startswith("tel:"):
                phone = href[4:].strip()
                if normalize_phone(phone):
                    phones.append(phone)
        page_emails.extend(EMAIL_RE.findall(" ".join(parser.text_parts)))
        for email in sorted(
            set(page_emails),
            key=lambda item: (
                not any(
                    word in item.casefold() for word in ("estimating", "bids", "quotes", "tenders")
                ),
                item.casefold(),
            ),
        ):
            normalized_email = email.casefold()
            if normalized_email in seen_emails or normalized_email in existing_emails:
                continue
            phone = next(
                (item for item in phones if normalize_phone(item) not in existing_phones), ""
            )
            name, title = _name_and_title(mail_anchors.get(normalized_email, ""), email)
            fields = ["email"]
            if phone:
                fields.append("phone")
            if name not in {"General inquiries", "Estimating"}:
                fields.append("name")
            suggestions.append(
                {
                    "name": name,
                    "title": title,
                    "email": email,
                    "phone": phone,
                    "is_primary": True,
                    "is_active": True,
                    "sources": [
                        {
                            "label": _source_label(page_url, root_url),
                            "url": page_url,
                            "fields": fields,
                        }
                    ],
                }
            )
            seen_emails.add(normalized_email)
    return {
        "suggestions": suggestions,
        "pages_checked": [url for url, _ in pages],
    }
