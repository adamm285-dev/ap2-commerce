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
  openCheckoutMandateToken?: string;
  openPaymentMandateToken?: string;
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
  tierId?: string;
  checkoutJwt?: string;
  checkoutHash?: string;
  nonce?: string;
  offerId?: string;
  openCheckoutMandateToken?: string;
  openPaymentMandateToken?: string;
  openMandateSource?: 'trusted_surface' | 'auto_demo';
}

export interface DeckPurchaseOptions {
  subscriptionId?: string;
  principalEntity?: string;
  contractorName?: string;
  capability?: string;
  agreedMonthlyRate?: number;
  monthlyBudgetCap?: number;
  negotiation?: AgentNegotiationResponse;
  tierId?: string;
  buyerEmail?: string;
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
  httpStatus: number;
  httpStatusText: string;
  rawResponse: any;
  sentRequest?: any;
}

/** Thrown when the backend can't complete a call; nothing was purchased, provisioned or locked. */
export class BackendUnavailableError extends Error {
  httpStatus?: number;
  httpStatusText?: string;
  rawResponse?: any;
  sentRequest?: any;

  constructor(message: string, httpStatus?: number, httpStatusText?: string, rawResponse?: any, sentRequest?: any) {
    super(message);
    this.name = 'BackendUnavailableError';
    this.httpStatus = httpStatus;
    this.httpStatusText = httpStatusText;
    this.rawResponse = rawResponse;
    this.sentRequest = sentRequest;
  }
}

export const PAYPAL_CONFIG = {
  clientId: import.meta.env.VITE_PAYPAL_CLIENT_ID || 'test',
  planId: import.meta.env.VITE_PAYPAL_PLAN_ID || 'P-4KA989014W524233ANLCRSFQ',
  planIdBatch: import.meta.env.VITE_PAYPAL_PLAN_ID_BATCH || 'P-68L14988XW5641721NLCRSFQ',
  planIdGateway: import.meta.env.VITE_PAYPAL_PLAN_ID_GATEWAY || 'P-4KA989014W524233ANLCRSFQ',
  planIdCluster: import.meta.env.VITE_PAYPAL_PLAN_ID_CLUSTER || 'P-77627096S5279500YNLCRSFY',
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
  if (lower.includes('batch') || lower.includes('worker') || lower.includes('49.99')) {
    return {
      tierName: 'High-Throughput Batch Worker',
      planName: 'High-Throughput Batch Worker ($49.99/mo)',
      catalogPrice: 49.99,
      planId: PAYPAL_CONFIG.planIdBatch,
    };
  }
  if (lower.includes('cluster') || lower.includes('security') || lower.includes('enterprise') || lower.includes('179.99')) {
    return {
      tierName: 'Enterprise Cluster Node',
      planName: 'Enterprise Cluster Node ($179.99/mo)',
      catalogPrice: 179.99,
      planId: PAYPAL_CONFIG.planIdCluster,
    };
  }
  return {
    tierName: 'Dedicated AI Service Gateway',
    planName: 'Dedicated AI Service Gateway ($79.99/mo)',
    catalogPrice: 79.99,
    planId: PAYPAL_CONFIG.planIdGateway,
  };
}

/**
 * Autonomous Buyer Agent evaluates whether the seller's terms fall within
 * the buyer's explicit programmatic spending mandate.
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

  const openCheckoutToken: string | undefined = request.openCheckoutMandateToken;
  const openPaymentToken: string | undefined = request.openPaymentMandateToken;
  const openMandateSource: 'trusted_surface' | 'auto_demo' | undefined =
    openCheckoutToken && openPaymentToken ? 'trusted_surface' : undefined;

  let failureReason = 'network error';
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

    if (!res.ok) {
      failureReason = `HTTP ${res.status}`;
    }
    if (res.ok) {
      const data = await res.json();
      const approved = data.approved ?? false;
      const counterAvailable = Boolean(data.counter_offer_available ?? data.counterOfferAvailable);
      const counterAmount = data.counter_offer_amount ?? data.counterOfferAmount;
      const counterTierRaw = data.counter_offer_tier ?? data.counterOfferTier;
      const counterTier = counterTierRaw || 'High-Throughput Batch Worker';
      const isCounterOffer = !approved && counterAvailable;
      const finalMonthlyRate = approved
        ? sellerMonthlyRate
        : (counterAmount || sellerMonthlyRate);
      const resolvedPlanId = data.plan_id || data.planId;
      const resolvedCounterPlanId = data.counter_offer_plan_id || data.counterOfferPlanId;
      const agreedPlanId = approved
        ? (resolvedPlanId || (finalMonthlyRate === 49.99 ? PAYPAL_CONFIG.planIdBatch : finalMonthlyRate === 179.99 ? PAYPAL_CONFIG.planIdCluster : PAYPAL_CONFIG.planIdGateway))
        : (resolvedCounterPlanId || PAYPAL_CONFIG.planIdBatch);

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

      const targetTierId = approved
        ? (data.tier_id || data.tierId || 'ap2-gateway')
        : (data.counter_offer_tier_id || data.counterOfferTierId || 'ap2-batch');

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
        tierId: targetTierId,
        checkoutJwt: data.checkout_jwt || data.checkoutJwt,
        checkoutHash: data.checkout_hash || data.checkoutHash || data.mandateProofHash || data.mandate_proof_hash,
        nonce: data.nonce,
        offerId: data.offer_id || data.offerId,
        openCheckoutMandateToken: openCheckoutToken,
        openPaymentMandateToken: openPaymentToken,
        openMandateSource: openMandateSource,
      };
    }
  } catch (err) {
    console.warn('[AP2 Agent] Seller backend not reachable; nothing was negotiated:', err);
  }

  // Fail closed: without the seller backend there is no negotiation and no mandate
  return {
    agreedPlanId: selectedTier.planId,
    agreedPlanName: requestedPlanName,
    monthlyFee: sellerMonthlyRate,
    mandateSatisfied: false,
    kycRequired: true,
    message: `[BuyerAgent]: Seller backend unavailable (${failureReason}). Nothing was negotiated and no mandate was created.`,
    sellerMcpEndpoint: PAYPAL_CONFIG.mcpServerUrl,
    isLiveBackend: false,
    isCounterOffer: false,
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
    if (!adminKey) {
      return true;
    }
    const headers: Record<string, string> = { 'Content-Type': 'application/json', 'X-Admin-Key': adminKey };
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
  principalEntity: string = 'Acme Compute Co',
  _capability: string = 'Dedicated AI Service Gateway',
  _regionCluster: string = 'us-east-1',
  contractorEmail: string = 'merchant@example.com'
): Promise<ProvisioningResult> {
  let failureReason = 'network error';
  let httpStatus: number | undefined;
  let httpStatusText: string | undefined;
  let rawResponse: any;
  const sentRequest = {
    subscriptionId: subscriptionId,
    contractorEmail: contractorEmail,
  };

  try {
    const res = await fetch('/api/agent/provision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sentRequest),
    });

    httpStatus = res.status;
    httpStatusText = res.statusText;
    const rawText = await res.text();
    try {
      rawResponse = JSON.parse(rawText);
    } catch {
      rawResponse = rawText;
    }

    if (!res.ok) {
      failureReason = `HTTP ${res.status}`;
    } else {
      const data = rawResponse;
      return {
        success: true,
        subscriptionId: data.subscriptionId || subscriptionId,
        allocatedDid: data.assignedDid,
        carrierRespOrg: data.carrier || 'AP2 Autonomous Node Registry',
        kycBoundEntity: principalEntity,
        tcpaGuardActive: true,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        isLiveBackend: true,
        httpStatus: res.status,
        httpStatusText: res.statusText,
        rawResponse: data,
        sentRequest,
      };
    }
  } catch (err: any) {
    console.warn('[AP2 Agent] Provisioning backend not reachable:', err);
    if (!httpStatus && err?.status) {
      httpStatus = err.status;
    }
    if (!httpStatusText && err?.statusText) {
      httpStatusText = err.statusText;
    }
    if (!rawResponse && err?.message) {
      rawResponse = { error: err.message };
    }
  }

  throw new BackendUnavailableError(
    `Provisioning backend unavailable (${failureReason}); no node was provisioned.`,
    httpStatus,
    httpStatusText,
    rawResponse,
    sentRequest
  );
}

/**
 * Executes full AP2 v0.2 purchase flow for the deck simulator:
 * Trusted Surface limits -> Buyer Agent closes mandates -> seller_agent.purchase_subscription
 * -> node provisioning.
 */
export async function executeDeckAp2Purchase(
  options: DeckPurchaseOptions
): Promise<ProvisioningResult> {
  const capLower = (options.capability || '').toLowerCase();
  let tierId = options.tierId || 'ap2-gateway';
  if (!options.tierId) {
    if (options.agreedMonthlyRate) {
      if (Math.abs(options.agreedMonthlyRate - 49.99) < 0.05) tierId = 'ap2-batch';
      else if (Math.abs(options.agreedMonthlyRate - 179.99) < 0.05) tierId = 'ap2-cluster';
      else tierId = 'ap2-gateway';
    } else if (capLower.includes('batch') || capLower.includes('solo') || capLower.includes('starter')) {
      tierId = 'ap2-batch';
    } else if (capLower.includes('cluster') || capLower.includes('enterprise')) {
      tierId = 'ap2-cluster';
    }
  }

  const agreedPrice = options.agreedMonthlyRate ?? (tierId === 'ap2-batch' ? 49.99 : tierId === 'ap2-cluster' ? 179.99 : 79.99);
  const buyerEmail = options.buyerEmail || 'merchant@example.com';
  const sentRequest = {
    tierId: tierId,
    agreedMonthlyRate: agreedPrice,
    buyerEmail: buyerEmail,
    contractorName: options.contractorName || 'AutonomousBuyerAgent',
    businessEntity: options.principalEntity || 'Acme Compute Co',
    monthlyBudgetCap: options.monthlyBudgetCap || 100.0,
    checkoutJwt: options.negotiation?.checkoutJwt,
    checkoutHash: options.negotiation?.checkoutHash,
    nonce: options.negotiation?.nonce,
    offerId: options.negotiation?.offerId,
    openCheckoutMandateToken: options.negotiation?.openCheckoutMandateToken,
    openPaymentMandateToken: options.negotiation?.openPaymentMandateToken,
    paypalSubscriptionId: options.subscriptionId,
  };

  let failureReason = 'network error';
  let httpStatus: number | undefined;
  let httpStatusText: string | undefined;
  let rawResponse: any;

  try {
    const res = await fetch('/api/agent/deck-purchase', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sentRequest),
    });

    httpStatus = res.status;
    httpStatusText = res.statusText;
    const rawText = await res.text();
    try {
      rawResponse = JSON.parse(rawText);
    } catch {
      rawResponse = rawText;
    }

    if (!res.ok) {
      failureReason = `HTTP ${res.status}`;
    } else {
      const data = rawResponse;
      return {
        success: true,
        subscriptionId: data.subscriptionId || options.subscriptionId || '',
        allocatedDid: data.assignedDid,
        carrierRespOrg: data.carrier || 'AP2 Autonomous Node Registry',
        kycBoundEntity: options.principalEntity || 'Acme Compute Co',
        tcpaGuardActive: true,
        timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
        isLiveBackend: true,
        httpStatus: res.status,
        httpStatusText: res.statusText,
        rawResponse: data,
        sentRequest,
      };
    }
  } catch (err: any) {
    console.warn('[AP2 Agent] AP2 purchase backend not reachable:', err);
    if (!httpStatus && err?.status) {
      httpStatus = err.status;
    }
    if (!httpStatusText && err?.statusText) {
      httpStatusText = err.statusText;
    }
    if (!rawResponse && err?.message) {
      rawResponse = { error: err.message };
    }
  }

  throw new BackendUnavailableError(
    `AP2 purchase backend unavailable (${failureReason}); nothing was purchased or provisioned.`,
    httpStatus,
    httpStatusText,
    rawResponse,
    sentRequest
  );
}

export interface DispatchLockResult {
  success: boolean;
  slotLockedUntil: string;
  nodeAssigned: string;
  territoryZone: string;
  paypalTransactionId: string;
  isLiveBackend?: boolean;
  httpStatus: number;
  httpStatusText: string;
  rawResponse: any;
  sentRequest?: any;
}

/**
 * Atomically reserves an appointment window across territory zones.
 * Note: Stores an unverified caller-supplied PayPal transaction reference;
 * does not verify deposit status against PayPal.
 * Calls FastAPI backend at POST /api/agent/dispatch/lock-slot with client-side fallback.
 */
export async function lockDispatchSlot(
  jobId: string,
  territoryZone: string,
  slotStartIso: string,
  paypalTransactionId: string
): Promise<DispatchLockResult> {
  let failureReason = 'network error';
  let httpStatus: number | undefined;
  let httpStatusText: string | undefined;
  let rawResponse: any;
  const sentRequest = {
    jobId,
    territoryZone,
    slotStartIso,
    paypalTransactionId,
  };

  try {
    const res = await fetch('/api/agent/dispatch/lock-slot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sentRequest),
    });

    httpStatus = res.status;
    httpStatusText = res.statusText;
    const rawText = await res.text();
    try {
      rawResponse = JSON.parse(rawText);
    } catch {
      rawResponse = rawText;
    }

    if (!res.ok) {
      failureReason = `HTTP ${res.status}`;
    } else {
      const data = rawResponse;
      return {
        success: data.success,
        slotLockedUntil: data.slotLockedUntil,
        nodeAssigned: data.nodeAssigned,
        territoryZone: data.territoryZone,
        paypalTransactionId,
        isLiveBackend: true,
        httpStatus: res.status,
        httpStatusText: res.statusText,
        rawResponse: data,
        sentRequest,
      };
    }
  } catch (err: any) {
    console.warn('[Dispatch Lock] Backend not reachable:', err);
    if (!httpStatus && err?.status) {
      httpStatus = err.status;
    }
    if (!httpStatusText && err?.statusText) {
      httpStatusText = err.statusText;
    }
    if (!rawResponse && err?.message) {
      rawResponse = { error: err.message };
    }
  }

  throw new BackendUnavailableError(
    `Slot lock backend unavailable (${failureReason}); no slot was locked.`,
    httpStatus,
    httpStatusText,
    rawResponse,
    sentRequest
  );
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

export interface FleetLedgerResponse {
  transactions: A2aTransaction[];
  simulatedFleetNotice?: string;
  count: number;
}

/**
 * Fetches dynamic enterprise fleet ledger and simulated fleet notice from SQLite via GET /api/fleet/ledger?profile=ap2.
 */
export async function fetchFleetLedgerData(): Promise<FleetLedgerResponse> {
  try {
    const res = await fetch('/api/fleet/ledger?profile=ap2');
    if (res.ok) {
      const data = await res.json();
      return {
        transactions: Array.isArray(data.transactions) ? data.transactions : [],
        simulatedFleetNotice: data.simulated_fleet_notice,
        count: data.count ?? (Array.isArray(data.transactions) ? data.transactions.length : 0),
      };
    }
  } catch (err) {
    console.warn('[Fleet Ledger] Live backend not reachable:', err);
  }
  return { transactions: [], count: 0 };
}

/**
 * Fetches dynamic enterprise fleet ledger from SQLite via GET /api/fleet/ledger?profile=ap2.
 */
export async function fetchFleetLedger(): Promise<A2aTransaction[]> {
  const data = await fetchFleetLedgerData();
  return data.transactions;
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
 * Reserves a territory dispatch slot for an enterprise node via POST /api/agent/dispatch/lock-slot.
 * Note: Stores an unverified caller-supplied deposit transaction reference.
 */
export async function lockTerritorySlot(
  jobId: string,
  territoryZone: string,
  slotStartIso: string,
  paypalTransactionId: string
): Promise<DispatchLockResult> {
  return lockDispatchSlot(jobId, territoryZone, slotStartIso, paypalTransactionId);
}

