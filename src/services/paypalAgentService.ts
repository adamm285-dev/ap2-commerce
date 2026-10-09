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
  planId: import.meta.env.VITE_PAYPAL_PLAN_ID || 'P-5ML4271244454362WXNWU5NQ',
  environment: (import.meta.env.VITE_PAYPAL_ENV || 'sandbox') as 'sandbox' | 'production',
  mcpServerUrl: 'https://mcp.sandbox.paypal.com/sse',
};

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
  const valueEstimate = request.workloadValueEstimate || request.missedCallLossEstimate || 500;
  const sellerMonthlyRate = request.maxMonthlyBudget >= 179.99
    ? 179.99
    : request.maxMonthlyBudget >= 79.99
    ? 79.99
    : 49.99;
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
      const finalMonthlyRate = approved
        ? sellerMonthlyRate
        : (data.counter_offer_amount || sellerMonthlyRate);
      const agreedPlanId = data.counter_offer_plan_id || (sellerMonthlyRate === 49.99 ? 'P-AP2-BATCH-WORKER' : sellerMonthlyRate === 179.99 ? 'P-AP2-CLUSTER-NODE' : PAYPAL_CONFIG.planId);
      const agreedPlanName = data.counter_offer_tier
        ? `${data.counter_offer_tier} (${capabilityName})`
        : sellerMonthlyRate === 49.99
        ? `High-Throughput Batch Worker ($49.99/mo)`
        : sellerMonthlyRate === 179.99
        ? `Enterprise Cluster Node ($179.99/mo)`
        : `Dedicated AI Service Gateway ($79.99/mo)`;

      const message = approved
        ? `[BuyerAgent]: Mandate approved by FastAPI ($${sellerMonthlyRate}/mo <= $${request.maxMonthlyBudget}/mo cap). Autonomous compute ROI value $${valueEstimate}/mo.`
        : data.counter_offer_available
        ? `[BuyerAgent]: Counter-offer accepted for $${finalMonthlyRate}/mo (${data.counter_offer_tier}) within budget cap $${request.maxMonthlyBudget}/mo.`
        : `[BuyerAgent]: REJECTED. Offered rate ($${sellerMonthlyRate}) exceeds buyer budget cap ($${request.maxMonthlyBudget}).`;

      return {
        agreedPlanId: agreedPlanId,
        agreedPlanName: agreedPlanName,
        monthlyFee: finalMonthlyRate,
        mandateSatisfied: approved || Boolean(data.counter_offer_available),
        kycRequired: true,
        message: data.reason || message,
        sellerMcpEndpoint: PAYPAL_CONFIG.mcpServerUrl,
        mandateToken: data.mandateProofHash || data.counter_offer_mandate_hash,
        isLiveBackend: true,
      };
    }
  } catch (err) {
    console.warn('[AP2 Agent] Live backend not reachable, using local mandate simulation:', err);
  }

  // Graceful client-side fallback
  const isBudgetAcceptable = sellerMonthlyRate <= request.maxMonthlyBudget;
  const fallbackPlanName = sellerMonthlyRate === 49.99
    ? `High-Throughput Batch Worker ($49.99/mo)`
    : sellerMonthlyRate === 179.99
    ? `Enterprise Cluster Node ($179.99/mo)`
    : `Dedicated AI Service Gateway ($79.99/mo)`;
  const fallbackPlanId = sellerMonthlyRate === 49.99 ? 'P-AP2-BATCH-WORKER' : sellerMonthlyRate === 179.99 ? 'P-AP2-CLUSTER-NODE' : PAYPAL_CONFIG.planId;
  return {
    agreedPlanId: fallbackPlanId,
    agreedPlanName: fallbackPlanName,
    monthlyFee: sellerMonthlyRate,
    mandateSatisfied: isBudgetAcceptable,
    kycRequired: true,
    message: isBudgetAcceptable
      ? `[BuyerAgent]: Mandate satisfied ($${sellerMonthlyRate}/mo <= $${request.maxMonthlyBudget}/mo cap). Autonomous compute value $${valueEstimate}/mo.`
      : `[BuyerAgent]: REJECTED. Offered rate ($${sellerMonthlyRate}) exceeds local buyer cap ($${request.maxMonthlyBudget}).`,
    sellerMcpEndpoint: PAYPAL_CONFIG.mcpServerUrl,
    mandateToken: isBudgetAcceptable ? 'MANDATE-SIMULATED-LOCAL-TOKEN' : undefined,
    isLiveBackend: false,
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
  _capability: string = 'Dedicated AI Service Gateway',
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
  const sampleEndpoints = [
    'mcp+https://gateway-01.acme-systems.io/mcp',
    'mcp+https://batch-worker-02.acme-systems.io/mcp',
    'mcp+https://cluster-01.acme-systems.io/mcp',
    'mcp+https://node-mesh-04.acme-systems.io/mcp',
  ];
  const allocatedDid = sampleEndpoints[Math.floor(Math.random() * sampleEndpoints.length)];

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

  return {
    success: true,
    slotLockedUntil: slotStartIso,
    crewAssigned: 'Zone 1 - North Lakeland',
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

