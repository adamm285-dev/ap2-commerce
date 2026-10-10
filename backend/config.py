"""
Configuration settings for the AP2 Autonomous Commerce & Multi-Agent Backend.
Loads environment variables safely from .env with fallback to mock mode when keys are omitted.
"""

import os
import logging
from pathlib import Path
from typing import Any, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator

logger = logging.getLogger(__name__)

# Project root directory (.env file lives one level up from /backend)
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH if ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App & Seller Name
    app_name: str = Field(default="AP2 Autonomous Commerce Node", alias="APP_NAME")
    seller_name: str = Field(default="AP2 Autonomous Node Network", alias="SELLER_NAME")

    # Seller Profile: 'ap2' for AP2 standalone open-source / hackathon repository
    a2a_seller_profile: Literal["ap2"] = Field(default="ap2", alias="A2A_SELLER_PROFILE")

    # Server network settings
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8001, alias="SERVER_PORT")

    # Operating mode (true = full simulation without external API calls)
    mock_external_apis: bool = Field(default=True, alias="MOCK_EXTERNAL_APIS")

    # PayPal Developer Sandbox Credentials
    paypal_client_id: str = Field(default="", alias="PAYPAL_CLIENT_ID")
    paypal_client_secret: str = Field(default="", alias="PAYPAL_CLIENT_SECRET")
    paypal_webhook_id: str = Field(default="", alias="PAYPAL_WEBHOOK_ID")
    paypal_base_url: str = Field(
        default="https://api-m.sandbox.paypal.com", alias="PAYPAL_BASE_URL"
    )

    # Zapier Model Context Protocol / NLA (Optional)
    zapier_nla_api_key: str = Field(default="", alias="ZAPIER_NLA_API_KEY")

    # Back-Office Webhook / Catch-Hook Export Endpoint (Optional, e.g. Zapier / Make / Webhook.site)
    webhook_export_url: str = Field(default="", alias="WEBHOOK_EXPORT_URL")

    # Cryptographic salt for signing buyer mandate proof tokens (HMAC-SHA256)
    a2a_mandate_secret: str = Field(
        default="",
        alias="A2A_MANDATE_SECRET",
    )

    # Dedicated back-office webhook signing secret (derived from mandate secret if omitted)
    a2a_webhook_secret: str = Field(default="", alias="A2A_WEBHOOK_SECRET")

    # Asymmetric Ed25519 Signing Keys (Legacy AP2 v0.1 compat)
    a2a_seller_private_key: str = Field(default="", alias="A2A_SELLER_PRIVATE_KEY")
    a2a_private_key: str = Field(default="", alias="A2A_PRIVATE_KEY")
    a2a_buyer_public_key: str = Field(default="", alias="A2A_BUYER_PUBLIC_KEY")

    # AP2 v0.2 ES256 ECDSA P-256 Signing Keys (Google Reference Architecture)
    ap2_merchant_private_key_jwk: str = Field(default="", alias="AP2_MERCHANT_PRIVATE_KEY_JWK")
    # Path to a gitignored JWK file; lets separate processes (HTTP server, stdio MCP) share one merchant key
    ap2_merchant_private_key_file: str = Field(default="", alias="AP2_MERCHANT_PRIVATE_KEY_FILE")
    ap2_merchant_key_id: str = Field(default="ap2-merchant-key-1", alias="AP2_MERCHANT_KEY_ID")

    # Admin API Key for administrative endpoints (mandate reset, ledger management)
    admin_api_key: str = Field(default="", alias="ADMIN_API_KEY")

    # PayPal Recurring Billing Plan IDs (optional overrides for live sandbox plans)
    paypal_plan_id_batch: str = Field(default="P-AP2-BATCH-WORKER", alias="PAYPAL_PLAN_ID_BATCH")
    paypal_plan_id_gateway: str = Field(default="P-AP2-SERVICE-GATEWAY", alias="PAYPAL_PLAN_ID_GATEWAY")
    paypal_plan_id_cluster: str = Field(default="P-AP2-CLUSTER-NODE", alias="PAYPAL_PLAN_ID_CLUSTER")

    @model_validator(mode="before")
    @classmethod
    def _fallback_legacy_plan_ids(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        legacy_plan_env_fallbacks = [
            ("PAYPAL_PLAN_ID_SOLO", "PAYPAL_PLAN_ID_BATCH"),
            ("PAYPAL_PLAN_ID_PRO", "PAYPAL_PLAN_ID_GATEWAY"),
            ("PAYPAL_PLAN_ID_DISPATCH", "PAYPAL_PLAN_ID_CLUSTER"),
        ]
        for old_key, new_key in legacy_plan_env_fallbacks:
            old_val = data.get(old_key) or data.get(old_key.lower()) or os.environ.get(old_key)
            new_val = data.get(new_key) or data.get(new_key.lower()) or os.environ.get(new_key)
            if old_val and not new_val:
                logger.warning("Deprecated env var %s in use; please migrate to %s.", old_key, new_key)
                data[new_key] = old_val
                data[new_key.lower()] = old_val
        return data

    @property
    def paypal_plan_id_solo(self) -> str:
        return self.paypal_plan_id_batch

    @paypal_plan_id_solo.setter
    def paypal_plan_id_solo(self, val: str) -> None:
        self.paypal_plan_id_batch = val

    @property
    def paypal_plan_id_pro(self) -> str:
        return self.paypal_plan_id_gateway

    @paypal_plan_id_pro.setter
    def paypal_plan_id_pro(self, val: str) -> None:
        self.paypal_plan_id_gateway = val

    @property
    def paypal_plan_id_dispatch(self) -> str:
        return self.paypal_plan_id_cluster

    @paypal_plan_id_dispatch.setter
    def paypal_plan_id_dispatch(self, val: str) -> None:
        self.paypal_plan_id_cluster = val

    # Persistent SQLite database path (defaults to backend/data/a2a_commerce.db)
    a2a_db_path: str = Field(default="", alias="A2A_DB_PATH")


settings = Settings()


def get_db_path() -> Path:
    """Returns the resolved database path, ensuring parent directory exists."""
    env_path = os.environ.get("A2A_DB_PATH") or settings.a2a_db_path
    if env_path and env_path.strip():
        if env_path.strip() == ":memory:":
            return Path(":memory:")
        p = Path(env_path.strip())
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    data_dir = ROOT_DIR / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "a2a_commerce.db"

# Automatically force mock mode if required keys are missing
# MOCK(M-001): mock mode switches on silently when PayPal keys are missing
if not settings.paypal_client_id or not settings.paypal_client_secret:
    settings.mock_external_apis = True
