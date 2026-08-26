from collections.abc import Iterator
from pathlib import Path

import pytest
from openhost_test_harness import OpenhostStack

MOCK_GATEWAY_DIR = Path(__file__).parent / "mock_gateway"
LLM_SERVICE_URL = "github.com/imbue-openhost/openhost-bifrost-llm-gateway/services/openai-compat"


def _deploy_gateway(stack: OpenhostStack) -> None:
    """Stand up the openai-compat provider before bottlechat installs, the way an owner would
    install the gateway first."""
    stack.deploy_app(f"file://{MOCK_GATEWAY_DIR}")


@pytest.fixture(scope="session")
def stack() -> Iterator[OpenhostStack]:
    """Build the app's Dockerfile, run it under podman per the manifest, and front it with the
    real OpenHost router — including the v2 service proxy the app uses for inference.

    - stack.url                    — through the router; requires owner auth
    - stack.owner_session          — a requests.Session authenticated as the zone owner
    - stack.playwright_login(page) — log a playwright page in as the owner
    - stack.app_url                — direct to the container (for forging/omitting headers)
    """
    with OpenhostStack(pre_deploy=_deploy_gateway) as s:
        yield s


@pytest.fixture
def gateway_control(stack: OpenhostStack):  # type: ignore[no-untyped-def]
    """Reconfigure the mock gateway (model list, failure mode, streaming speed) for one test."""
    applied: list[dict[str, object]] = []

    def control(**settings: object) -> None:
        applied.append(settings)
        response = stack.owner_session.post(f"{stack.url_for('mock-gateway')}/control", json=settings, timeout=10)
        assert response.status_code == 200, response.text

    yield control

    if applied:
        control(models=["mock/fast-1", "mock/thinker-1"], chat_status=200, chunk_delay=0.0)
