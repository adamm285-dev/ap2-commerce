import os

# Ensure A2A_MANDATE_SECRET and ADMIN_API_KEY are populated prior to importing backend.config in CI/test environments
os.environ.setdefault("A2A_MANDATE_SECRET", "ci_test_mandate_secret_key_32_chars_long")
os.environ.setdefault("ADMIN_API_KEY", "ci_admin_secret_token_key_for_testing")
os.environ.setdefault("MOCK_EXTERNAL_APIS", "true")

import pytest
from ..config import settings
from ..services.paypal_service import paypal_service
from ..services.telnyx_provisioner import telnyx_provisioner
from ..services.zapier_mcp_dispatcher import zapier_mcp_dispatcher

@pytest.fixture(autouse=True)
def configure_mock_mode_for_unit_tests(monkeypatch):
    """
    Ensures unit and regression tests run deterministically against the mock contract layer,
    preventing unit tests from making live network calls to external sandbox endpoints.
    """
    monkeypatch.setattr(settings, "mock_external_apis", True)
    if not settings.admin_api_key or not settings.admin_api_key.strip():
        monkeypatch.setattr(settings, "admin_api_key", "ci_admin_secret_token_key_for_testing")
    monkeypatch.setattr(paypal_service, "mock_mode", True)
    monkeypatch.setattr(telnyx_provisioner, "mock_mode", True)
    monkeypatch.setattr(zapier_mcp_dispatcher, "mock_mode", True)


@pytest.fixture(autouse=True)
def isolate_database_for_each_test():
    """
    Ensures each unit and regression test runs against a clean database state and clean proxies,
    preventing state leakage across tests while preserving schema and default seeds.
    """
    from ..database import reset_all_data
    from ..services.mandate_evaluator import ledger
    from ..server import clear_processed_webhooks

    reset_all_data()
    ledger.reset()
    clear_processed_webhooks()
    yield
    reset_all_data()
    ledger.reset()
    clear_processed_webhooks()
