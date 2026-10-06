import os

# Ensure A2A_MANDATE_SECRET is populated prior to importing backend.config in CI/test environments
os.environ.setdefault("A2A_MANDATE_SECRET", "ci_test_mandate_secret_key_32_chars_long")
os.environ.setdefault("MOCK_EXTERNAL_APIS", "true")

import pytest
from backend.config import settings
from backend.services.paypal_service import paypal_service
from backend.services.telnyx_provisioner import telnyx_provisioner
from backend.services.zapier_mcp_dispatcher import zapier_mcp_dispatcher

@pytest.fixture(autouse=True)
def configure_mock_mode_for_unit_tests(monkeypatch):
    """
    Ensures unit and regression tests run deterministically against the mock contract layer,
    preventing unit tests from making live network calls to external sandbox endpoints.
    """
    monkeypatch.setattr(settings, "mock_external_apis", True)
    monkeypatch.setattr(paypal_service, "mock_mode", True)
    monkeypatch.setattr(telnyx_provisioner, "mock_mode", True)
    monkeypatch.setattr(zapier_mcp_dispatcher, "mock_mode", True)
