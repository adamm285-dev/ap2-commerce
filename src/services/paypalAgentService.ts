/**
 * PayPal Agentic Commerce Service (AP2 Protocol)
 *
 * Implements the Buyer Agent / Seller Agent protocol using PayPal Subscriptions
 * and the FastAPI backend matching the OpenAPI 3.1.0 contract.
 */

import type { A2aTransaction } from '../data/telemetryData';

export interface AgentNegotiationRequest {
  buyerAgentName?: string;
  principalEntity?: string;
  capability?: string;
  maxMonthlyBudget: number;
  workloadValueEstimate?: number;
  // Backward compatibility fields
  contractorName?: string;
  businessEntity?: string;
  tradeVertical?: string;
  missedCallLossEstimate?: number;
}

export interface AgentNegotiationResponse {
  agreedPlanId: string;
  agreedPlanName: string;
  monthlyFee: number;
  mandateSatisfied: boolean;
  kycRequired: boolean;
  message: string;
  sellerMcpEndpoint: string;
  mandateToken?: string;
  isLiveBackend?: boolean;
  isCounterOffer?: boolean;
  counterOfferMessage?: string;
  requestedMonthlyRate?: number;
  requestedPlanName?: string;
}

export interface ProvisioningResult {
  success: boolean;
  subscriptionId: string;
  allocatedDid: string;
  carrierRespOrg: string;
  kycBoundEntity: string;
  tcpaGuardActive: boolean;
  timestamp: string;
  isLiveBackend?: boolean;
}

export const PAYPAL_CONFIG = {
  clientId: import.meta.env.VITE_PAYPAL_CLIENT_ID || 'test',
  planId: import.meta.env.VITE_PAYPAL_PLAN_ID || 'P-4KA989014W524233ANLCRSFQ',
  planIdSolo: import.meta.env.VITE_PAYPAL_PLAN_ID_SOLO || 'P-68L14988XW5641721NLCRSFQ',
  planIdPro: import.meta.env.VITE_PAYPAL_PLAN_ID_PRO || 'P-4KA989014W524233ANLCRSFQ',
  planIdDispatch: import.meta.env.VITE_PAYPAL_PLAN_ID_DISPATCH || 'P-77627096S5279500YNLCRSFY',
  environment: (import.meta.env.VITE_PAYPAL_ENV || 'sandbox') as 'sandbox' | 'production',
  get mcpServerUrl(): string {
    return typeof window !== 'undefined' && window.location?.origin
      ? `${window.location.origin}/mcp`
      : 'http://127.0.0.1:8001/mcp';
  },
};

export function getCatalogTierDetails(capabilityOrTier: string): {
  tierName: string;
  planName: string;
  catalogPrice: number;
  planId: string;
} {
  const lower = (capabilityOrTier || '').toLowerCase();
  if (lower.includes('batch') || lower.includes('solo') || lower.includes('starter') || lower.includes('49.99')) {
    return {
      tierName: 'High-Throughput Batch Worker',
      planName: 'High-Throughput Batch Worker ($49.99/mo)',
      catalogPrice: 49.99,
      planId: PAYPAL_CONFIG.planIdSolo,
    };
  }
  if (lower.includes('cluster') || lower.includes('security') || lower.includes('dispatch') || lower.includes('enterprise') || lower.includes('179.99')) {
    return {
      tierName: 'Enterprise Cluster Node',
      planName: 'Enterprise Cluster Node ($179.99/mo)',
      catalogPrice: 179.99,
      planId: PAYPAL_CONFIG.planIdDispatch,
    };
  }
  return {
    tierName: 'Dedicated AI Service Gateway',
    planName: 'Dedicated AI Service Gateway ($79.99/mo)',
    catalogPrice: 79.99,
    planId: PAYPAL_CONFIG.planIdPro,
  };
}

/**
 * Autonomous Buyer Agent evaluates whether the seller's terms fall within
 * the buyer's explicit programmatic spending mandate (< $200/mo).
 *
 * Calls FastAPI backend at POST /api/agent/spending-mandate/evaluate
 */
export async function evaluateAgentNegotiation(
  request: AgentNegotiationRequest
): Promise<AgentNegotiationResponse> {
  const agentName = request.buyerAgentName || request.contractorName || 'AutonomousBuyerAgent';
  const capabilityName = request.capability || request.tradeVertical || 'Dedicated AI Service Gateway';
  
  // ALWAYS send the SELECTED tier's catalog price - never pick from budget before asking seller
  const selectedTier = getCatalogTierDetails(capabilityName);
  const sellerMonthlyRate = selectedTier.catalogPrice;
  const requestedPlanName = selectedTier.planName;
  const buyerAgentId = `BuyerAgent-${agentName.replace(/\s+/g, '')}-${capabilityName.replace(/\s+/g, '')}`;

  try {
    const res = await fetch('/api/agent/spending-mandate/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        buyerAgentId: buyerAgentId,
        amount: sellerMonthlyRate,
        recurrence: 'monthly',
        category: 'autonomous-node-service',
        monthlyBudgetCap: request.maxMonthlyBudget,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      const approved = data.approved ?? false;
      const counterAvailable = Boolean(data.counter_offer_available ?? data.counterOfferAvailable);
      const counterAmount = data.counter_offer_amount ?? data.counterOfferAmount;
      const counterTierRaw = data.counter_offer_tier ?? data.counterOfferTier;
      const counterTier = (counterTierRaw === 'Solo Starter' || !counterTierRaw) ? 'High-Throughput Batch Worker' : counterTierRaw;
      const isCounterOffer = !approved && counterAvailable;
      const finalMonthlyRate = approved
        ? sellerMonthlyRate
        : (counterAmount || sellerMonthlyRate);
      const resolvedPlanId = data.plan_id || data.planId;
      const resolvedCounterPlanId = data.counter_offer_plan_id || data.counterOfferPlanId;
      const agreedPlanId = approved
        ? (resolvedPlanId || (finalMonthlyRate === 49.99 ? PAYPAL_CONFIG.planIdSolo : finalMonthlyRate === 179.99 ? PAYPAL_CONFIG.planIdDispatch : PAYPAL_CONFIG.planIdPro))
        : (resolvedCounterPlanId || PAYPAL_CONFIG.planIdSolo);

      const agreedPlanName = isCounterOffer
        ? `${counterTier} ($${finalMonthlyRate.toFixed(2)}/mo)`
        : requestedPlanName;

      const counterOfferMessage = isCounterOffer
        ? `[SellerMCP]: Budget $${request.maxMonthlyBudget.toFixed(2)} < $${sellerMonthlyRate.toFixed(2)} — counter-offer: ${counterTier} $${finalMonthlyRate.toFixed(2)}/mo`
        : undefined;

      const message = approved
        ? `[BuyerAgent]: Mandate approved by FastAPI ($${sellerMonthlyRate.toFixed(2)}/mo <= $${request.maxMonthlyBudget.toFixed(2)}/mo cap).`
        : isCounterOffer
        ? `[BuyerAgent]: Counter-offer accepted for $${finalMonthlyRate.toFixed(2)}/mo (${counterTier}) within budget cap $${request.maxMonthlyBudget.toFixed(2)}/mo.`
        : (data.reason || `[BuyerAgent]: REJECTED. Offered rate ($${sellerMonthlyRate.toFixed(2)}) exceeds buyer budget cap ($${request.maxMonthlyBudget.toFixed(2)}).`);

      return {
        agreedPlanId: agreedPlanId,
        agreedPlanName: agreedPlanName,
        monthlyFee: finalMonthlyRate,
        mandateSatisfied: approved || isCounterOffer,
        kycRequired: true,
        message: message,
        sellerMcpEndpoint: PAYPAL_CONFIG.mcpServerUrl,
        mandateToken: data.mandateProofHash || data.mandate_proof_hash || data.counterOfferMandateHash || data.counter_offer_mandate_hash,
        isLiveBackend: true,
        isCounterOffer: isCounterOffer,
        counterOfferMessage: counterOfferMessage,
        requestedMonthlyRate: sellerMonthlyRate,
        requestedPlanName: requestedPlanName,
      };
    }
  } catch (err) {
    console.warn('[AP2 Agent] Live backend not reachable, using local mandate simulation:', err);
  }

  // Graceful client-side fallback
  const isBudgetAcceptable = sellerMonthlyRate <= request.maxMonthlyBudget;
  const isFallbackCounterOffer = !isBudgetAcceptable && request.maxMonthlyBudget >= 49.99;
  const fallbackMonthlyFee = isBudgetAcceptable
    ? sellerMonthlyRate
    : isFallbackCounterOffer
    ? 49.99
    : sellerMonthlyRate;

  const fallbackPlanName = isFallbackCounterOffer
    ? 'High-Throughput Batch Worker ($49.99/mo)'
    : requestedPlanName;

  const fallbackPlanId = fallbackMonthlyFee === 49.99
    ? PAYPAL_CONFIG.planIdSolo
    : fallbackMonthlyFee === 179.99
    ? PAYPAL_CONFIG.planIdDispatch
    : PAYPAL_CONFIG.planIdPro;

  const fallbackCounterOfferMessage = isFallbackCounterOffer
    ? `[SellerMCP]: Budget $${request.maxMonthlyBudget.toFixed(2)} < $${sellerMonthlyRate.toFixed(2)} — counter-offer: ${fallbackPlanName}`
    : undefined;

  const fallbackMessage = isBudgetAcceptable
    ? `[BuyerAgent]: Mandate satisfied ($${sellerMonthlyRate.toFixed(2)}/mo <= $${request.maxMonthlyBudget.toFixed(2)}/mo cap).`
    : isFallbackCounterOffer
    ? `[BuyerAgent]: Counter-offer accepted for $${fallbackMonthlyFee.toFixed(2)}/mo (High-Throughput Batch Worker) within budget cap $${request.maxMonthlyBudget.toFixed(2)}/mo.`
    : `[BuyerAgent]: REJECTED. Offered rate ($${sellerMonthlyRate.toFixed(2)}) exceeds local buyer cap ($${request.maxMonthlyBudget.toFixed(2)}).`;

  return {
    agreedPlanId: fallbackPlanId,
    agreedPlanName: fallbackPlanName,
    monthlyFee: fallbackMonthlyFee,
    mandateSatisfied: isBudgetAcceptable || isFallbackCounterOffer,
    kycRequired: true,
    message: fallbackMessage,
    sellerMcpEndpoint: PAYPAL_CONFIG.mcpServerUrl,
    mandateToken: (isBudgetAcceptable || isFallbackCounterOffer) ? 'MANDATE-SIMULATED-LOCAL-TOKEN' : undefined,
    isLiveBackend: false,
    isCounterOffer: isFallbackCounterOffer,
    counterOfferMessage: fallbackCounterOfferMessage,
    requestedMonthlyRate: sellerMonthlyRate,
    requestedPlanName: requestedPlanName,
  };
}

/**
 * Resets the spending mandate ledger on the backend.
 */
export async function resetMandateLedger(buyerAgentId?: string): Promise<boolean> {
  try {
    const adminKey = localStorage.getItem('fs_admin_key') || (window as any).__FS_ADMIN_KEY || '';
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (adminKey) {
      headers['X-Admin-Key'] = adminKey;
    }
    const res = await fetch('/api/agent/spending-mandate/reset', {
      method: 'POST',
      headers,
      body: JSON.stringify(buyerAgentId ? { buyerAgentId } : {}),
    });
    return res.ok;
  } catch (err) {
    console.warn('[AP2 Agent] Could not reset mandate ledger:', err);
    return false;
  }
}

/**
 * Seller Agent verifies PayPal Subscription token and provisions an authenticated
 * AP2 MCP node endpoint bound to the buyer's Ed25519 mandate.
 *
 * Calls FastAPI backend at POST /api/agent/provision with client-side fallback.
 */
export async function executeProvisioningAfterSubscription(
  subscriptionId: string,
  principalEntity: string,
  capability: string = 'Dedicated AI Service Gateway',
  _regionCluster: string = 'us-east-1'
): Promise<ProvisioningResult> {
  try {
    const res = await fetch('/api/agent/provision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subscriptionId: subscriptionId,
        contractorEmail: 'merchant@ap2protocol.org',
        areaCode: '863',
      }),
    });

    if (res.ok) {
      const data = await res.json();
      return {
        success: true,
        subscriptionId: data.subscriptionId,
        allocatedDid: data.assignedDid,
        carrierRespOrg: data.carrier || 'AP2 Autonomous Node Registry',
        kycBoundEntity: principalEntity,
        tcpaGuardActive: true,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        isLiveBackend: true,
      };
    }
  } catch (err) {
    console.warn('[AP2 Agent] Live backend not reachable, using local provisioning simulation:', err);
  }

  // Graceful client-side fallback matching AP2 MCP node endpoints
  await new Promise((resolve) => setTimeout(resolve, 600));
  const capLower = (capability || '').toLowerCase();
  let allocatedDid = 'mcp+https://gateway-01.acme-systems.io/mcp';
  if (capLower.includes('batch') || capLower.includes('starter') || capLower.includes('solo') || capLower.includes('49.99')) {
    allocatedDid = 'mcp+https://batch-01.acme-systems.io/mcp';
  } else if (capLower.includes('cluster') || capLower.includes('enterprise') || capLower.includes('179.99')) {
    allocatedDid = 'mcp+https://cluster-01.acme-systems.io/mcp';
  } else {
    allocatedDid = 'mcp+https://gateway-01.acme-systems.io/mcp';
  }

  return {
    success: true,
    subscriptionId,
    allocatedDid,
    carrierRespOrg: 'AP2 Autonomous Node Registry',
    kycBoundEntity: principalEntity,
    tcpaGuardActive: true,
    timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
    isLiveBackend: false,
  };
}

export interface DispatchLockResult {
  success: boolean;
  slotLockedUntil: string;
  crewAssigned: string;
  territoryZone: string;
  paypalTransactionId: string;
  isLiveBackend?: boolean;
}

/**
 * Atomically locks a 75-minute estimate window upon verified PayPal deposit capture.
 * Calls FastAPI backend at POST /api/agent/dispatch/lock-slot with client-side fallback.
 */
export async function lockDispatchSlot(
  leadId: string,
  territoryZone: string,
  slotStartIso: string,
  paypalTransactionId: string
): Promise<DispatchLockResult> {
  try {
    const res = await fetch('/api/agent/dispatch/lock-slot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        leadId,
        territoryZone,
        slotStartIso,
        paypalTransactionId,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      return {
        success: data.success,
        slotLockedUntil: data.slotLockedUntil,
        crewAssigned: data.crewAssigned,
        territoryZone: data.territoryZone,
        paypalTransactionId,
        isLiveBackend: true,
      };
    }
  } catch (err) {
    console.warn('[Dispatch Lock] Live API not reachable, using fallback:', err);
  }

  const defaultCluster = territoryZone && (territoryZone.includes('Cluster') || territoryZone.includes('Node'))
    ? territoryZone
    : 'Cluster Alpha - Dedicated AI Service Gateway';

  return {
    success: true,
    slotLockedUntil: slotStartIso,
    crewAssigned: defaultCluster,
    territoryZone,
    paypalTransactionId,
    isLiveBackend: false,
  };
}

export interface FleetStats {
  total_mrr: number;
  active_lines: number;
  total_subscribers: number;
  annualized_gmv: number;
  mandates_cleared: number;
  compliance_guard: string;
  carrier_resporg: string;
  trade_breakdown: Array<{
    trade: string;
    active_agents: number;
    monthly_settlement: number;
    annualized_gmv: number;
    mandates_cleared: number;
  }>;
}

export interface FleetScheduleResponse {
  status: string;
  count: number;
  resources: Array<{
    id: string;
    name: string;
    entity: string;
    trade: string;
    did: string;
    status: string;
  }>;
  events: Array<{
    id: string;
    resourceId: string;
    name: string;
    startDate: string;
    endDate: string;
    eventColor: string;
    iconCls: string;
    depositStatus: string;
    paypalTxn: string;
  }>;
}

/**
 * Fetches dynamic enterprise fleet ledger from SQLite via GET /api/fleet/ledger?profile=ap2.
 */
export async function fetchFleetLedger(): Promise<A2aTransaction[]> {
  try {
    const res = await fetch('/api/fleet/ledger?profile=ap2');
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.transactions) && data.transactions.length > 0) {
        return data.transactions;
      }
    }
  } catch (err) {
    console.warn('[Fleet Ledger] Live backend not reachable, using fallback:', err);
  }
  return [];
}

/**
 * Fetches real-time fleet aggregates and KPIs from SQLite via GET /api/fleet/stats?profile=ap2.
 */
export async function fetchFleetStats(): Promise<FleetStats | null> {
  try {
    const res = await fetch('/api/fleet/stats?profile=ap2');
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn('[Fleet Stats] Live backend not reachable, using fallback:', err);
  }
  return null;
}

/**
 * Fetches timeline resources, shifts, and appointment locks via GET /api/fleet/schedule?profile=ap2.
 */
export async function fetchFleetSchedule(): Promise<FleetScheduleResponse | null> {
  try {
    const res = await fetch('/api/fleet/schedule?profile=ap2');
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn('[Fleet Schedule] Live backend not reachable, using fallback:', err);
  }
  return null;
}

/**
 * Locks a territory dispatch slot for an enterprise crew via POST /api/agent/dispatch/lock-slot.
 */
export async function lockTerritorySlot(
  leadId: string,
  territoryZone: string,
  slotStartIso: string,
  paypalTransactionId: string
): Promise<DispatchLockResult> {
  return lockDispatchSlot(leadId, territoryZone, slotStartIso, paypalTransactionId);
}

