"""
Canonical Plan Catalog for AP2 Autonomous Compute & Worker Node Network.
Single source for every agent-facing plan surface in the seller: MCP tools and
initialize instructions, the A2A agent card, the REST compute catalog, counter-offer
text, and back-office exports.
"""

from typing import Any, Dict, List, Optional

# --- AP2 PROFILE (Autonomous Compute & Worker Node Network) ---
# Strictly zero forbidden trades/telephony terms
AP2_QUOTA_UNIT = "workload_tasks_per_month"
AP2_QUOTA_UNIT_DEFINITION = "Autonomous compute tasks processed and verified by the worker node each month."

AP2_PLANS: List[Dict[str, Any]] = [
    {
        "tier_id": "ap2-batch",
        "title": "High-Throughput Batch Worker",
        "website_plan_name": "Batch Worker",
        "monthly_price": 49.99,
        "workload_tasks_per_month": 125,
        "headline": "asynchronous worker node",
        "best_for": "Batch processing and background agent workflows",
        "features": [
            "125 workload tasks per month",
            "Asynchronous job queue execution",
            "Standard MCP tool execution latency",
            "Autonomous agent task verification",
            "Standard execution priority",
            "Instant task completion webhooks",
        ],
    },
    {
        "tier_id": "ap2-gateway",
        "title": "Dedicated AI Service Gateway",
        "website_plan_name": "Service Gateway",
        "monthly_price": 79.99,
        "workload_tasks_per_month": 450,
        "headline": "real-time routing and multi-agent coordination",
        "best_for": "Production agents requiring real-time gateway access",
        "features": [
            "450 workload tasks per month",
            "All Batch Worker features",
            "Real-time low-latency gateway routing",
            "Multi-agent protocol negotiation",
            "High-priority task execution",
            "Dedicated gateway endpoint allocation",
        ],
    },
    {
        "tier_id": "ap2-cluster",
        "title": "Enterprise Cluster Node",
        "website_plan_name": "Cluster Node",
        "monthly_price": 179.99,
        "workload_tasks_per_month": 1200,
        "headline": "high-volume multi-node cluster with dedicated SLA",
        "best_for": "Enterprise agent fleets with high-volume compute needs",
        "features": [
            "1,200 workload tasks per month",
            "Multi-node cluster scaling",
            "Dedicated compute resources and SLA",
            "Enterprise security and audit logging",
        ],
    },
]

AP2_TIER_ALIASES: Dict[str, str] = {
    "batch": "ap2-batch",
    "batch-worker": "ap2-batch",
    "gateway": "ap2-gateway",
    "gateway-node": "ap2-gateway",
    "cluster": "ap2-cluster",
    "cluster-node": "ap2-cluster",
}

PUBLIC_AP2_TIER_ALIASES: Dict[str, str] = dict(AP2_TIER_ALIASES)

# Single Source of Truth: Canonical mapping from tier IDs and aliases
# to the corresponding PayPal plan attribute on backend.config.settings.
TIER_TO_SETTINGS_ATTR: Dict[str, str] = {
    # Tier 1 ($49.99): Batch Worker
    "ap2-batch": "paypal_plan_id_solo",
    "batch": "paypal_plan_id_solo",
    "batch-worker": "paypal_plan_id_solo",
    # Tier 2 ($79.99): Dedicated AI Gateway
    "ap2-gateway": "paypal_plan_id_pro",
    "gateway": "paypal_plan_id_pro",
    "gateway-node": "paypal_plan_id_pro",
    # Tier 3 ($179.99): Enterprise Cluster Node
    "ap2-cluster": "paypal_plan_id_dispatch",
    "cluster": "paypal_plan_id_dispatch",
    "cluster-node": "paypal_plan_id_dispatch",
}

AP2_INCLUDED_ON_ALL_PLANS: List[str] = [
    "24/7 autonomous compute node execution (~350ms median response)",
    "Automated AP2 Intent and Cart Mandate cryptographic verification",
    "Mutual authentication via Ed25519 asymmetric signatures",
    "Zero-speculative metric auditing and immutable ledger logging",
    "Downline webhook execution for ERP and database synchronization",
    "Automated node health monitoring and failover routing",
]

AP2_SUPPORTED_WORKLOADS: List[Dict[str, Any]] = [
    {
        "workload_id": "batch-processing",
        "title": "High-throughput asynchronous batch processing",
        "intake_focus": ["Queue depth", "Data transformation", "Payload verification", "Batch scheduling"],
    },
    {
        "workload_id": "gateway-routing",
        "title": "Real-time AI service gateway routing",
        "intake_focus": ["Request routing", "Model mediation", "Low-latency streaming", "Protocol translation"],
    },
    {
        "workload_id": "cluster-orchestration",
        "title": "Distributed multi-agent cluster execution",
        "intake_focus": ["Resource allocation", "State replication", "Cluster scaling", "Fault tolerance"],
    },
]

AP2_ACTIVATION = (
    "Paid is live: buyer agent binds PayPal subscription and receives compute node access endpoint immediately."
)

AP2_TRUST_SIGNALS: Dict[str, str] = {
    "guarantee": "30-day money-back Service Guarantee",
    "refund_policy_url": "https://ap2-commerce.org/refunds",
    "terms_url": "https://ap2-commerce.org/terms",
    "privacy_url": "https://ap2-commerce.org/privacy",
}


def get_seller_profile() -> str:
    """Returns active seller profile: always 'ap2' in standalone repository."""
    return "ap2"


def get_plans(profile: Optional[str] = None) -> List[Dict[str, Any]]:
    return AP2_PLANS


def get_tier_aliases(profile: Optional[str] = None) -> Dict[str, str]:
    return AP2_TIER_ALIASES


def get_public_tier_aliases(profile: Optional[str] = None) -> Dict[str, str]:
    return PUBLIC_AP2_TIER_ALIASES


def get_quota_unit(profile: Optional[str] = None) -> str:
    return AP2_QUOTA_UNIT


def get_quota_unit_definition(profile: Optional[str] = None) -> str:
    return AP2_QUOTA_UNIT_DEFINITION


def get_included_on_all_plans(profile: Optional[str] = None) -> List[str]:
    return AP2_INCLUDED_ON_ALL_PLANS


def get_supported_trades(profile: Optional[str] = None) -> List[Dict[str, Any]]:
    return AP2_SUPPORTED_WORKLOADS


def get_activation(profile: Optional[str] = None) -> str:
    return AP2_ACTIVATION


def get_trust_signals(profile: Optional[str] = None) -> Dict[str, str]:
    return AP2_TRUST_SIGNALS


def resolve_plan(tier_id: Optional[str], profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Returns the plan for a canonical tier_id or alias, or None if unknown."""
    if not tier_id:
        return None
    aliases = get_tier_aliases()
    target_id = aliases.get(tier_id, tier_id)
    plans_by_id = {plan["tier_id"]: plan for plan in get_plans()}
    return plans_by_id.get(target_id)


def resolve_paypal_plan_id(tier_id: Optional[str], profile: Optional[str] = None) -> str:
    """
    Single source of truth: resolves any canonical tier_id or alias
    to the configured settings PayPal plan ID (paypal_plan_id_solo, pro, or dispatch).
    Never returns a synthesized string.
    """
    from ..config import settings

    raw = (tier_id or "").strip().lower()
    aliases = get_tier_aliases()
    canonical = aliases.get(raw, raw)

    attr = TIER_TO_SETTINGS_ATTR.get(canonical) or TIER_TO_SETTINGS_ATTR.get(raw)
    if not attr:
        plan = resolve_plan(raw)
        if plan:
            canon_id = plan.get("tier_id")
            attr = TIER_TO_SETTINGS_ATTR.get(canon_id)
            if not attr:
                price = plan.get("monthly_price", 0.0)
                if price <= 49.99:
                    attr = "paypal_plan_id_solo"
                elif price <= 79.99:
                    attr = "paypal_plan_id_pro"
                else:
                    attr = "paypal_plan_id_dispatch"
        else:
            attr = "paypal_plan_id_pro"

    val = getattr(settings, attr, None)
    if val and str(val).strip():
        return str(val).strip()

    defaults = {
        "paypal_plan_id_solo": getattr(settings, "paypal_plan_id_solo", "P-AP2-BATCH-WORKER"),
        "paypal_plan_id_pro": getattr(settings, "paypal_plan_id_pro", "P-AP2-SERVICE-GATEWAY"),
        "paypal_plan_id_dispatch": getattr(settings, "paypal_plan_id_dispatch", "P-AP2-CLUSTER-NODE"),
    }
    return defaults.get(attr, getattr(settings, "paypal_plan_id_pro", "P-AP2-SERVICE-GATEWAY"))


def get_plan(tier_id: str, profile: Optional[str] = None) -> Dict[str, Any]:
    """Returns the plan for a canonical tier_id or alias; raises KeyError if unknown."""
    plan = resolve_plan(tier_id, profile=profile)
    if plan is None:
        raise KeyError(tier_id)
    return plan


def quota_label(tier_id: str, profile: Optional[str] = None) -> str:
    """Short quota label, e.g. '125 workload tasks/mo'."""
    plan = get_plan(tier_id, profile=profile)
    tasks = plan.get("workload_tasks_per_month", 125)
    return f"{tasks:,} workload tasks/mo"


def plan_summary(tier_id: str, profile: Optional[str] = None) -> str:
    """One-line price and quota summary."""
    plan = get_plan(tier_id, profile=profile)
    return f"${plan['monthly_price']:.2f}/mo ({quota_label(tier_id, profile=profile)}, {plan['headline']})"


def public_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Agent-facing view of a plan (drops internal copy helpers such as 'headline')."""
    return {key: value for key, value in plan.items() if key != "headline"}


# Direct assignments for pure AP2 architecture
PLANS = AP2_PLANS
TIER_ALIASES = AP2_TIER_ALIASES
INCLUDED_ON_ALL_PLANS = AP2_INCLUDED_ON_ALL_PLANS
SUPPORTED_TRADES = AP2_SUPPORTED_WORKLOADS
TRUST_SIGNALS = AP2_TRUST_SIGNALS
QUOTA_UNIT = AP2_QUOTA_UNIT
QUOTA_UNIT_DEFINITION = AP2_QUOTA_UNIT_DEFINITION
ACTIVATION = AP2_ACTIVATION
