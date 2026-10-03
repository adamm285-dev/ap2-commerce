/**
 * APIMatic Generated SDK Integration Example (TypeScript / Node.js).
 * Demonstrates how an autonomous Buyer Agent or third-party web service integrates
 * with FieldSmith Pro's A2A Commerce Protocol using the auto-generated TypeScript SDK.
 * Conforms 100% to openapi.yaml (OpenAPI 3.1.0).
 */

export interface TradeService {
  id: string;
  title: string;
  monthlySubscription: number;
  depositRange: string;
}

export interface MandateResult {
  approved: boolean;
  authorizedAmount: number;
  monthlyCapRemaining: number;
  mandateProofHash: string;
}

export interface ProvisionResult {
  status: string;
  assignedDid: string;
  carrier: string;
  routingState: string;
  subscriptionId: string;
}

export class FieldSmithA2AClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://127.0.0.1:8001') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async checkHealth(): Promise<{ status: string; mock_mode: boolean }> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return res.json();
  }

  async getTradeCatalog(): Promise<{ status: string; trades: TradeService[] }> {
    const res = await fetch(`${this.baseUrl}/api/agent/catalog`);
    if (!res.ok) throw new Error(`Catalog inquiry failed: ${res.statusText}`);
    return res.json();
  }

  async evaluateSpendingMandate(params: {
    buyerAgentId: string;
    amount: number;
    recurrence?: string;
    category?: string;
    monthlyBudgetCap?: number;
  }): Promise<MandateResult> {
    const res = await fetch(`${this.baseUrl}/api/agent/spending-mandate/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        buyerAgentId: params.buyerAgentId,
        amount: params.amount,
        recurrence: params.recurrence || 'monthly',
        category: params.category || 'contractor-dispatch-ai',
        monthlyBudgetCap: params.monthlyBudgetCap ?? 100.0,
      }),
    });
    if (!res.ok) throw new Error(`Mandate evaluation failed: ${res.statusText}`);
    return res.json();
  }

  async provisionContractorLine(params: {
    subscriptionId: string;
    contractorEmail: string;
    areaCode?: string;
  }): Promise<ProvisionResult> {
    const res = await fetch(`${this.baseUrl}/api/agent/provision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subscriptionId: params.subscriptionId,
        contractorEmail: params.contractorEmail,
        areaCode: params.areaCode || '863',
      }),
    });
    if (!res.ok) throw new Error(`DID provisioning failed: ${res.statusText}`);
    return res.json();
  }

  async triggerZapierMcpSync(params: {
    workflowType?: string;
    contractorName?: string;
    businessEntity?: string;
    allocatedDid?: string;
    tradeVertical?: string;
    monthlyFee?: number;
    paypalSubId?: string;
    contractorEmail?: string;
  }): Promise<any> {
    const res = await fetch(`${this.baseUrl}/api/mcp/zapier-sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflowType: params.workflowType || 'a2a_onboarding',
        contractorName: params.contractorName || 'Marcus Miller',
        businessEntity: params.businessEntity || 'Miller Custom Flooring LLC',
        allocatedDid: params.allocatedDid || '+1 (863) 802-6000',
        tradeVertical: params.tradeVertical || 'Tile & Custom Flooring',
        monthlySubscriptionFee: params.monthlyFee || 89.0,
        paypalSubscriptionId: params.paypalSubId || 'I-AUTONOMOUS-8902',
        contractorEmail: params.contractorEmail || 'marcus@millercustomfloors.com',
      }),
    });
    if (!res.ok) throw new Error(`Zapier MCP sync failed: ${res.statusText}`);
    return res.json();
  }
}

/**
 * Example autonomous TypeScript agent execution cycle
 */
async function runTypeScriptAgent() {
  console.log('=======================================================');
  console.log('🚀 Running APIMatic TypeScript SDK Integration Demo');
  console.log('=======================================================\n');

  const client = new FieldSmithA2AClient();

  const health = await client.checkHealth();
  console.log(`1. Health Check: ${health.status} (Mock: ${health.mock_mode})`);

  const catalog = await client.getTradeCatalog();
  const trade = catalog.trades[0];
  console.log(`2. Catalog Inquiry: Selected '${trade.title}' at $${trade.monthlySubscription}/mo`);

  const mandate = await client.evaluateSpendingMandate({
    buyerAgentId: 'agent-ts-buyer-01',
    amount: trade.monthlySubscription,
    monthlyBudgetCap: 100.0,
  });
  console.log(`3. Mandate Check: Approved=${mandate.approved} (Proof: ${mandate.mandateProofHash.substring(0, 16)}...)`);

  const prov = await client.provisionContractorLine({
    subscriptionId: `I-TS-SUB-${mandate.mandateProofHash.substring(0, 8).toUpperCase()}`,
    contractorEmail: 'marcus@millercustomfloors.com',
  });
  console.log(`4. Line Provisioned: ${prov.assignedDid} (${prov.carrier})`);

  const zap = await client.triggerZapierMcpSync({
    allocatedDid: prov.assignedDid,
    paypalSubId: `I-TS-SUB-${mandate.mandateProofHash.substring(0, 8).toUpperCase()}`,
  });
  console.log(`5. Zapier MCP Dispatched: QBO=${zap.qboDraftInvoiceId}, Jobber=${zap.jobberQuoteId}`);

  console.log('\n✅ APIMatic TypeScript SDK Client Verified Successfully!\n');
}

// Export for module use or run if main
if (typeof require !== 'undefined' && require.main === module) {
  runTypeScriptAgent().catch(console.error);
}
