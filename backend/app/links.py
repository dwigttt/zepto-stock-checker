"""Extract the Zepto product variant id (pvid) from shared links."""

import re
from urllib.parse import parse_qs, urlparse

UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
PVID_RE = re.compile(rf"/pvid/({UUID})")
UUID_RE = re.compile(UUID)

ZEPTO_HOSTS = ("zepto.com", "zeptonow.com", "zepto.app.link", "app.link")


def extract_pvid(text: str) -> str | None:
    """Pull a pvid out of a URL or pasted text without any network calls."""
    m = PVID_RE.search(text)
    if m:
        return m.group(1).lower()
    # Branch.io deep links carry the id in deep_link_value / $deeplink_path etc.
    try:
        qs = parse_qs(urlparse(text.strip()).query)
    except ValueError:
        return None
    for values in qs.values():
        for v in values:
            m = UUID_RE.search(v)
            if m and "/pvid/" not in v:
                return m.group(0).lower()
    return None


def first_url(text: str) -> str | None:
    """Find the first http(s) URL in a pasted share blob."""
    m = re.search(r"https?://\S+", text)
    return m.group(0).rstrip(".,;)\"'") if m else None


def looks_like_zepto(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in ZEPTO_HOSTS)
