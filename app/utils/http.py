"""Shared HTTP utilities — consistent User-Agent for external API calls."""
import httpx

# Common User-Agent for SEC EDGAR (required for access)
SEC_USER_AGENT = "PharmaCatalystAlert/1.0 (admin@pharma-edge.com)"
SEC_HEADERS = {"User-Agent": SEC_USER_AGENT}


def sec_client(timeout: int = 20) -> httpx.Client:
    """Return an httpx.Client pre-configured for SEC EDGAR requests."""
    return httpx.Client(timeout=timeout, headers=SEC_HEADERS)
