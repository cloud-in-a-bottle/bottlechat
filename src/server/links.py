from typing import Any

from litestar import Request

# The router terminates TLS and tells the app which scheme the browser used.  The zone may be
# plain http (mDNS `.local` domains, the local test harness), so don't assume https.
_DEFAULT_SCHEME = "https"


def request_scheme(request: Request[Any, Any, Any]) -> str:
    forwarded = request.headers.get("x-forwarded-proto")
    return forwarded.split(",")[0].strip() if forwarded else _DEFAULT_SCHEME
