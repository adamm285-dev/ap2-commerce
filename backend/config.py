"""
Configuration settings for the FieldSmith Pro A2A Commerce & Multi-Agent Backend.
Loads environment variables safely from .env with fallback to mock mode when keys are omitted.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Project root directory (.env file lives one level up from /backend)
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH if ENV_PATH.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

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

    # Telnyx Telephony & 10DLC (Optional)
    telnyx_api_key: str = Field(default="", alias="TELNYX_API_KEY")
    telnyx_messaging_profile_id: str = Field(
        default="", alias="TELNYX_MESSAGING_PROFILE_ID"
    )
    # Live Telnyx Ordering Safety Breaker (Defaults to False; orders must be explicitly enabled)
    enable_live_telnyx_orders: bool = Field(default=False, alias="ENABLE_LIVE_TELNYX_ORDERS")

    # Zapier Model Context Protocol / NLA (Optional)
    zapier_nla_api_key: str = Field(default="", alias="ZAPIER_NLA_API_KEY")

    # Back-Office Webhook / Catch-Hook Export Endpoint (Optional, e.g. Zapier / Make / Webhook.site)
    webhook_export_url: str = Field(default="", alias="WEBHOOK_EXPORT_URL")

    # Cryptographic salt for signing buyer mandate proof tokens (HMAC-SHA256)
    a2a_mandate_secret: str = Field(
        default="",
        alias="A2A_MANDATE_SECRET",
    )

    # Asymmetric Ed25519 Signing Keys (AP2 Protocol)
    a2a_seller_private_key: str = Field(default="", alias="A2A_SELLER_PRIVATE_KEY")
    a2a_private_key: str = Field(default="", alias="A2A_PRIVATE_KEY")
    a2a_buyer_public_key: str = Field(default="", alias="A2A_BUYER_PUBLIC_KEY")

    # Admin API Key for administrative endpoints (mandate reset, ledger management)
    admin_api_key: str = Field(default="", alias="ADMIN_API_KEY")

    # PayPal Recurring Billing Plan IDs (optional overrides for live sandbox plans)
    paypal_plan_id_solo: str = Field(default="P-FLSMITH-SOLO-STARTER", alias="PAYPAL_PLAN_ID_SOLO")
    paypal_plan_id_pro: str = Field(default="P-FLSMITH-PRO", alias="PAYPAL_PLAN_ID_PRO")
    paypal_plan_id_dispatch: str = Field(default="P-FLSMITH-DISPATCH", alias="PAYPAL_PLAN_ID_DISPATCH")

    # Persistent SQLite database path (defaults to backend/data/a2a_commerce.db)
    a2a_db_path: str = Field(default="", alias="A2A_DB_PATH")


settings = Settings()


def get_db_path() -> Path:
    """Returns the resolved database path, ensuring parent directory exists."""
    if settings.a2a_db_path and settings.a2a_db_path.strip():
        if settings.a2a_db_path.strip() == ":memory:":
            return Path(":memory:")
        p = Path(settings.a2a_db_path.strip())
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    data_dir = ROOT_DIR / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "a2a_commerce.db"

# Automatically force mock mode if required keys are missing
if not settings.paypal_client_id or not settings.paypal_client_secret:
    settings.mock_external_apis = True

# Fail fast at startup if critical mandate signing secret is missing
if not settings.a2a_mandate_secret or not settings.a2a_mandate_secret.strip():
    raise RuntimeError(
        "CRITICAL SECURITY CONFIGURATION ERROR: A2A_MANDATE_SECRET is missing. "
        "A secure random secret must be configured in .env."
    )

