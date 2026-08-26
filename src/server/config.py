import os
from pathlib import Path

import attr

# The service this app consumes for inference.  Any app registering this service URL works;
# Bifrost is the reference provider.
LLM_SERVICE_URL = "github.com/imbue-openhost/openhost-bifrost-llm-gateway/services/openai-compat"
LLM_SHORTNAME = "llm"

# Where the owner goes to install a provider, relative to the zone domain.
PROVIDER_REPO_URL = "https://github.com/cloud-in-a-bottle/bottled-bifrost"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; this app must run under OpenHost (see justfile for local dev)")
    return value


@attr.s(auto_attribs=True, frozen=True)
class Config:
    db_path: Path
    router_url: str
    app_token: str
    app_name: str
    zone_domain: str
    frontend_dir: Path

    @staticmethod
    def from_env() -> "Config":
        frontend_dir = Path(os.environ.get("BOTTLECHAT_FRONTEND_DIR", "frontend/dist")).resolve()
        return Config(
            db_path=Path(_require("OPENHOST_SQLITE_CHATS")),
            router_url=_require("OPENHOST_ROUTER_URL").rstrip("/"),
            app_token=_require("OPENHOST_APP_TOKEN"),
            app_name=_require("OPENHOST_APP_NAME"),
            zone_domain=_require("OPENHOST_ZONE_DOMAIN"),
            frontend_dir=frontend_dir,
        )

    def app_url_for(self, app_name: str, scheme: str) -> str:
        return f"{scheme}://{app_name}.{self.zone_domain}"

    def dashboard_url(self, scheme: str) -> str:
        return f"{scheme}://{self.zone_domain}"
