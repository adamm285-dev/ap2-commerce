"""
Canonical FieldSmith Pro Subscription Plan Catalog.
Single source for every agent-facing plan surface in the seller: MCP tools and
initialize instructions, the A2A agent card, the REST trade catalog, counter-offer
text, and back-office exports. Values mirror the published plan list at
https://fieldsmith.pro/llms.txt; backend/tests/test_plan_catalog.py fails on drift.
"""

from typing import Any, Dict, List, Optional

QUOTA_UNIT = "screened_calls_per_month"
QUOTA_UNIT_DEFINITION = "Inbound calls answered and screened by the AI receptionist each month."

PLANS: List[Dict[str, Any]] = [
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

# Legacy tier_id inputs still accepted by negotiate_tier_terms. The trade IDs predate
# the plan model; every trade is supported on every plan.
TIER_ALIASES: Dict[str, str] = {
    "solo": "solo-starter",
    "pro": "fieldsmith-pro",
    "flooring-tile": "fieldsmith-pro",
    "roofing-storm": "fieldsmith-pro",
    "plumbing-emergency": "fieldsmith-pro",
    "fleet": "pro-dispatch",
}

INCLUDED_ON_ALL_PLANS: List[str] = [
    "24/7 AI receptionist on forwarded calls (~350ms median AI response, under 800ms end-to-end over phone lines)",
    "Scope extraction: square footage, materials, timeline, and job address",
    "Automated SMS photo estimate link",
    "Robocall and spam shield (STIR/SHAKEN verification and VoIP aggregator filtering)",
    "1-tap CRM and webhook export to Jobber and custom CRMs",
    "Live whisper bridge with VIP passkey bypass",
]

SUPPORTED_TRADES: List[Dict[str, Any]] = [
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

ACTIVATION = (
    "Paid is not live: the contractor installs the FieldSmith Android app and turns on "
    "carrier call forwarding (*72 or *71) to start receiving screened calls."
)

TRUST_SIGNALS: Dict[str, str] = {
    "guarantee": "30-day money-back Jobsite Guarantee",
    "refund_policy_url": "https://fieldsmith.pro/refunds",
    "terms_url": "https://fieldsmith.pro/terms",
    "privacy_url": "https://fieldsmith.pro/privacy",
}

_PLANS_BY_ID: Dict[str, Dict[str, Any]] = {plan["tier_id"]: plan for plan in PLANS}


def resolve_plan(tier_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Returns the plan for a canonical tier_id or legacy alias, or None if unknown."""
    if not tier_id:
        return None
    return _PLANS_BY_ID.get(TIER_ALIASES.get(tier_id, tier_id))


def get_plan(tier_id: str) -> Dict[str, Any]:
    """Returns the plan for a canonical tier_id or legacy alias; raises KeyError if unknown."""
    plan = resolve_plan(tier_id)
    if plan is None:
        raise KeyError(tier_id)
    return plan


def quota_label(tier_id: str) -> str:
    """Short quota label, e.g. '125 AI screened calls/mo'."""
    return f"{get_plan(tier_id)['screened_calls_per_month']:,} AI screened calls/mo"


def plan_summary(tier_id: str) -> str:
    """One-line price and quota summary, e.g. '$49.99/mo (125 AI screened calls/mo, dedicated shop number)'."""
    plan = get_plan(tier_id)
    return f"${plan['monthly_price']:.2f}/mo ({quota_label(tier_id)}, {plan['headline']})"


def public_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Agent-facing view of a plan (drops internal copy helpers such as 'headline')."""
    return {key: value for key, value in plan.items() if key != "headline"}
