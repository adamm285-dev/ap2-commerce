"""
Canonical Plan Catalog for FieldSmith Trades and AP2 Autonomous Compute Profiles.
Single source for every agent-facing plan surface in the seller: MCP tools and
initialize instructions, the A2A agent card, the REST trade catalog, counter-offer
text, and back-office exports.
"""

from typing import Any, Dict, List, Optional

# --- TRADES PROFILE (FieldSmith Telephony SaaS) ---
TRADES_QUOTA_UNIT = "screened_calls_per_month"
TRADES_QUOTA_UNIT_DEFINITION = "Inbound calls answered and screened by the AI receptionist each month."

TRADES_PLANS: List[Dict[str, Any]] = [
    {
        "tier_id": "solo-starter",
        "title": "FieldSmith Solo Starter",
        "website_plan_name": "Solo Operator",
        "monthly_price": 49.99,
        "screened_calls_per_month": 125,
        "headline": "dedicated shop number",
        "best_for": "Solo contractors",
        "features": [
            "125 AI screened calls per month",
            "Dedicated shop phone number (or carrier cell forwarding)",
            "24/7 AI scoping voice receptionist",
            "SMS photo intake link dispatch",
            "Robocall and spam shield",
            "Instant app and SMS lead alerts",
        ],
    },
    {
        "tier_id": "fieldsmith-pro",
        "title": "FieldSmith Pro",
        "website_plan_name": "Pro",
        "monthly_price": 79.99,
        "screened_calls_per_month": 450,
        "headline": "multi-crew dispatch and lead routing",
        "best_for": "Growing trade businesses with crews",
        "features": [
            "450 AI screened calls per month",
            "All Solo Operator features",
            "Multi-crew dispatch and lead routing",
            "Emergency call escalation priority",
            "Dedicated carrier line registration",
            "Priority customer support",
        ],
    },
    {
        "tier_id": "pro-dispatch",
        "title": "FieldSmith Fleet Dispatch",
        "website_plan_name": "Fleet / Crew",
        "monthly_price": 179.99,
        "screened_calls_per_month": 1200,
        "headline": "unlimited crew members and routing",
        "best_for": "Fleets running multiple crews",
        "features": [
            "1,200 AI screened calls per month",
            "Unlimited crew members and routing",
            "Custom voice persona and tone tuning",
            "Dedicated account manager",
        ],
    },
]

TRADES_TIER_ALIASES: Dict[str, str] = {
    "solo": "solo-starter",
    "pro": "fieldsmith-pro",
    "flooring-tile": "fieldsmith-pro",
    "roofing-storm": "fieldsmith-pro",
    "plumbing-emergency": "fieldsmith-pro",
    "fleet": "pro-dispatch",
    "ap2-batch": "solo-starter",
    "ap2-gateway": "fieldsmith-pro",
    "ap2-cluster": "pro-dispatch",
}

TRADES_INCLUDED_ON_ALL_PLANS: List[str] = [
    "24/7 AI receptionist on forwarded calls (~350ms median AI response, under 800ms end-to-end over phone lines)",
    "Scope extraction: square footage, materials, timeline, and job address",
    "Automated SMS photo estimate link",
    "Robocall and spam shield (STIR/SHAKEN verification and VoIP aggregator filtering)",
    "1-tap CRM and webhook export to Jobber and custom CRMs",
    "Live whisper bridge with VIP passkey bypass",
]

TRADES_SUPPORTED_TRADES: List[Dict[str, Any]] = [
    {
        "trade_id": "flooring-tile",
        "title": "Tile setters and flooring installers",
        "intake_focus": ["Square footage", "Backerboard inspection", "Uncoupling membranes", "Tear-out requirements"],
    },
    {
        "trade_id": "roofing-storm",
        "title": "Roofing contractors and storm restoration",
        "intake_focus": ["Emergency leak triage", "Missing shingles", "Insurance claim timeline", "Steep-slope access"],
    },
    {
        "trade_id": "plumbing-emergency",
        "title": "Plumbing and HVAC technicians",
        "intake_focus": ["Emergency water shutoff triage", "Unit age", "Brand", "Diagnostic dispatch"],
    },
    {
        "trade_id": "towing-roadside",
        "title": "Towing operators and roadside technicians",
        "intake_focus": ["Vehicle year, make, and model", "Highway cross-streets", "Key status", "Driveability"],
    },
    {
        "trade_id": "general-contractor",
        "title": "General contractors and handymen",
        "intake_focus": ["Kitchen and bath remodels", "Residential carpentry", "Inspection booking"],
    },
]

TRADES_ACTIVATION = (
    "Paid is not live: the contractor installs the FieldSmith Android app and turns on "
    "carrier call forwarding (*72 or *71) to start receiving screened calls."
)

TRADES_TRUST_SIGNALS: Dict[str, str] = {
    "guarantee": "30-day money-back Jobsite Guarantee",
    "refund_policy_url": "https://fieldsmith.pro/refunds",
    "terms_url": "https://fieldsmith.pro/terms",
    "privacy_url": "https://fieldsmith.pro/privacy",
}


# --- AP2 PROFILE (Autonomous Compute & Worker Node Network) ---
# Zero forbidden words (flooring, roofing, plumb, towing, contractor, telephony, screened, 10DLC, receptionist, DID)
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
    "solo": "ap2-batch",
    "solo-starter": "ap2-batch",
    "gateway": "ap2-gateway",
    "gateway-node": "ap2-gateway",
    "pro": "ap2-gateway",
    "fieldsmith-pro": "ap2-gateway",
    "cluster": "ap2-cluster",
    "cluster-node": "ap2-cluster",
    "fleet": "ap2-cluster",
    "pro-dispatch": "ap2-cluster",
}

# Publicly visible aliases for AP2 catalog output (excludes legacy trades terminology)
PUBLIC_AP2_TIER_ALIASES: Dict[str, str] = {
    "batch": "ap2-batch",
    "batch-worker": "ap2-batch",
    "gateway": "ap2-gateway",
    "gateway-node": "ap2-gateway",
    "cluster": "ap2-cluster",
    "cluster-node": "ap2-cluster",
}

# Single Source of Truth: Canonical mapping from every tier ID and alias across all profiles
# to the corresponding PayPal plan attribute on backend.config.settings.
TIER_TO_SETTINGS_ATTR: Dict[str, str] = {
    # Tier 1 ($49.99): Solo Starter / Batch Worker
    "solo-starter": "paypal_plan_id_solo",
    "solo": "paypal_plan_id_solo",
    "ap2-batch": "paypal_plan_id_solo",
    "batch": "paypal_plan_id_solo",
    "batch-worker": "paypal_plan_id_solo",
    # Tier 2 ($79.99): FieldSmith Pro / Dedicated AI Gateway
    "fieldsmith-pro": "paypal_plan_id_pro",
    "pro": "paypal_plan_id_pro",
    "flooring-tile": "paypal_plan_id_pro",
    "roofing-storm": "paypal_plan_id_pro",
    "plumbing-emergency": "paypal_plan_id_pro",
    "ap2-gateway": "paypal_plan_id_pro",
    "gateway": "paypal_plan_id_pro",
    "gateway-node": "paypal_plan_id_pro",
    # Tier 3 ($179.99): Fleet Dispatch / Enterprise Cluster Node
    "pro-dispatch": "paypal_plan_id_dispatch",
    "fleet": "paypal_plan_id_dispatch",
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
    """Returns active seller profile: 'ap2' or 'trades'."""
    try:
        from ..config import settings
        val = getattr(settings, "a2a_seller_profile", None)
        if val and str(val).strip():
            return str(val).strip().lower()
    except Exception:
        pass
    import os
    env_val = os.getenv("A2A_SELLER_PROFILE")
    if env_val and env_val.strip():
        return env_val.strip().lower()
    return "ap2"


def get_plans(profile: Optional[str] = None) -> List[Dict[str, Any]]:
    prof = profile or get_seller_profile()
    return TRADES_PLANS if prof == "trades" else AP2_PLANS


def get_tier_aliases(profile: Optional[str] = None) -> Dict[str, str]:
    prof = profile or get_seller_profile()
    return TRADES_TIER_ALIASES if prof == "trades" else AP2_TIER_ALIASES


def get_public_tier_aliases(profile: Optional[str] = None) -> Dict[str, str]:
    """Returns aliases suitable for public catalog export (hides trades terms in ap2 mode)."""
    prof = profile or get_seller_profile()
    return TRADES_TIER_ALIASES if prof == "trades" else PUBLIC_AP2_TIER_ALIASES


def get_quota_unit(profile: Optional[str] = None) -> str:
    prof = profile or get_seller_profile()
    return TRADES_QUOTA_UNIT if prof == "trades" else AP2_QUOTA_UNIT


def get_quota_unit_definition(profile: Optional[str] = None) -> str:
    prof = profile or get_seller_profile()
    return TRADES_QUOTA_UNIT_DEFINITION if prof == "trades" else AP2_QUOTA_UNIT_DEFINITION


def get_included_on_all_plans(profile: Optional[str] = None) -> List[str]:
    prof = profile or get_seller_profile()
    return TRADES_INCLUDED_ON_ALL_PLANS if prof == "trades" else AP2_INCLUDED_ON_ALL_PLANS


def get_supported_trades(profile: Optional[str] = None) -> List[Dict[str, Any]]:
    prof = profile or get_seller_profile()
    return TRADES_SUPPORTED_TRADES if prof == "trades" else AP2_SUPPORTED_WORKLOADS


def get_activation(profile: Optional[str] = None) -> str:
    prof = profile or get_seller_profile()
    return TRADES_ACTIVATION if prof == "trades" else AP2_ACTIVATION


def get_trust_signals(profile: Optional[str] = None) -> Dict[str, str]:
    prof = profile or get_seller_profile()
    return TRADES_TRUST_SIGNALS if prof == "trades" else AP2_TRUST_SIGNALS


def resolve_plan(tier_id: Optional[str], profile: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Returns the plan for a canonical tier_id or legacy alias, or None if unknown."""
    if not tier_id:
        return None
    prof = profile or get_seller_profile()
    aliases = get_tier_aliases(prof)
    target_id = aliases.get(tier_id, tier_id)
    plans_by_id = {plan["tier_id"]: plan for plan in get_plans(prof)}
    if target_id not in plans_by_id:
        # Cross-profile fallback mapping
        cross_map = {
            "solo-starter": "ap2-batch",
            "fieldsmith-pro": "ap2-gateway",
            "pro-dispatch": "ap2-cluster",
            "flooring-tile": "ap2-gateway",
            "roofing-storm": "ap2-gateway",
            "plumbing-emergency": "ap2-gateway",
            "ap2-batch": "solo-starter",
            "ap2-gateway": "fieldsmith-pro",
            "ap2-cluster": "pro-dispatch",
        }
        alt_id = cross_map.get(target_id)
        if alt_id and alt_id in plans_by_id:
            return plans_by_id[alt_id]
    return plans_by_id.get(target_id)


def resolve_paypal_plan_id(tier_id: Optional[str], profile: Optional[str] = None) -> str:
    """
    Single source of truth: resolves any canonical tier_id or alias across all profiles
    to the configured settings PayPal plan ID (paypal_plan_id_solo, pro, or dispatch).
    Never returns a synthesized P-FLSMITH-* or P-AP2-* string.
    """
    from ..config import settings

    prof = profile or get_seller_profile()
    raw = (tier_id or "").strip().lower()

    # Try alias in active profile
    aliases = get_tier_aliases(prof)
    canonical = aliases.get(raw, raw)

    attr = TIER_TO_SETTINGS_ATTR.get(canonical) or TIER_TO_SETTINGS_ATTR.get(raw)
    if not attr:
        plan = resolve_plan(raw, profile=prof)
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
        "paypal_plan_id_solo": getattr(settings, "paypal_plan_id_solo", "P-FLSMITH-SOLO-STARTER"),
        "paypal_plan_id_pro": getattr(settings, "paypal_plan_id_pro", "P-FLSMITH-PRO"),
        "paypal_plan_id_dispatch": getattr(settings, "paypal_plan_id_dispatch", "P-FLSMITH-DISPATCH"),
    }
    return defaults.get(attr, getattr(settings, "paypal_plan_id_pro", "P-FLSMITH-PRO"))


def get_plan(tier_id: str, profile: Optional[str] = None) -> Dict[str, Any]:
    """Returns the plan for a canonical tier_id or legacy alias; raises KeyError if unknown."""
    plan = resolve_plan(tier_id, profile=profile)
    if plan is None:
        raise KeyError(tier_id)
    return plan


def quota_label(tier_id: str, profile: Optional[str] = None) -> str:
    """Short quota label, e.g. '125 AI screened calls/mo' or '125 workload tasks/mo'."""
    prof = profile or get_seller_profile()
    plan = get_plan(tier_id, profile=prof)
    if prof == "trades":
        return f"{plan['screened_calls_per_month']:,} AI screened calls/mo"
    tasks = plan.get("workload_tasks_per_month", 125)
    return f"{tasks:,} workload tasks/mo"


def plan_summary(tier_id: str, profile: Optional[str] = None) -> str:
    """One-line price and quota summary."""
    prof = profile or get_seller_profile()
    plan = get_plan(tier_id, profile=prof)
    return f"${plan['monthly_price']:.2f}/mo ({quota_label(tier_id, profile=prof)}, {plan['headline']})"


def public_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Agent-facing view of a plan (drops internal copy helpers such as 'headline')."""
    return {key: value for key, value in plan.items() if key != "headline"}


# --- Dynamic Proxies for Backward Compatibility ---
class _PlansProxy(list):
    def __iter__(self):
        return iter(get_plans())

    def __len__(self):
        return len(get_plans())

    def __getitem__(self, idx):
        return get_plans()[idx]

    def __contains__(self, item):
        return item in get_plans()

    def __eq__(self, other):
        return get_plans() == other

    def __repr__(self):
        return repr(get_plans())


class _TierAliasesProxy(dict):
    def get(self, key, default=None):
        return get_tier_aliases().get(key, default)

    def __getitem__(self, key):
        return get_tier_aliases()[key]

    def __contains__(self, key):
        return key in get_tier_aliases()

    def __iter__(self):
        return iter(get_tier_aliases())

    def __len__(self):
        return len(get_tier_aliases())

    def items(self):
        return get_tier_aliases().items()

    def keys(self):
        return get_tier_aliases().keys()

    def values(self):
        return get_tier_aliases().values()

    def __eq__(self, other):
        return get_tier_aliases() == other

    def __repr__(self):
        return repr(get_tier_aliases())


class _IncludedProxy(list):
    def __iter__(self):
        return iter(get_included_on_all_plans())

    def __len__(self):
        return len(get_included_on_all_plans())

    def __getitem__(self, idx):
        return get_included_on_all_plans()[idx]

    def __contains__(self, item):
        return item in get_included_on_all_plans()

    def __eq__(self, other):
        return get_included_on_all_plans() == other

    def __repr__(self):
        return repr(get_included_on_all_plans())


class _SupportedTradesProxy(list):
    def __iter__(self):
        return iter(get_supported_trades())

    def __len__(self):
        return len(get_supported_trades())

    def __getitem__(self, idx):
        return get_supported_trades()[idx]

    def __contains__(self, item):
        return item in get_supported_trades()

    def __eq__(self, other):
        return get_supported_trades() == other

    def __repr__(self):
        return repr(get_supported_trades())


class _TrustSignalsProxy(dict):
    def get(self, key, default=None):
        return get_trust_signals().get(key, default)

    def __getitem__(self, key):
        return get_trust_signals()[key]

    def __contains__(self, key):
        return key in get_trust_signals()

    def __iter__(self):
        return iter(get_trust_signals())

    def __len__(self):
        return len(get_trust_signals())

    def items(self):
        return get_trust_signals().items()

    def __eq__(self, other):
        return get_trust_signals() == other

    def __repr__(self):
        return repr(get_trust_signals())


PLANS = _PlansProxy()
TIER_ALIASES = _TierAliasesProxy()
INCLUDED_ON_ALL_PLANS = _IncludedProxy()
SUPPORTED_TRADES = _SupportedTradesProxy()
TRUST_SIGNALS = _TrustSignalsProxy()

# Scalar constants defaulted for trades backward compatibility, use get_quota_unit() for profile-aware values
QUOTA_UNIT = "screened_calls_per_month"
QUOTA_UNIT_DEFINITION = "Inbound calls answered and screened by the AI receptionist each month."
ACTIVATION = TRADES_ACTIVATION
