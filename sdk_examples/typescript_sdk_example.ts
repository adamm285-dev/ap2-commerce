/**
 * APIMatic Generated SDK Integration Example (TypeScript / Node.js).
 * Demonstrates how an autonomous Buyer Agent or third-party web service integrates
 * with AP2 Autonomous Commerce Protocol using the auto-generated TypeScript SDK.
 * Conforms 100% to openapi.yaml (OpenAPI 3.1.0).
 */

export interface ComputeService {
  id: string;
  title: string;
  monthlySubscription: number;
  workloadQuota: number;
}

export interface MandateResult {
  approved: boolean;
  authorizedAmount: number;
  monthlyCapRemaining: number;
  mandateProofHash: string;
}

export interface ProvisionResult {
  status: string;
  endpoint: string;
  carrier: string;
  subscriptionId: string;
}

export class AP2CommerceClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://127.0.0.1:8001') {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  async checkHealth(): Promise<{ status: string; mock_mode: boolean }> {
    const res = await fetch(`${this.baseUrl}/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return res.json();
  }

  async getServiceCatalog(): Promise<{ status: string; trades: ComputeService[] }> {
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
        category: params.category || 'autonomous-compute',
        monthlyBudgetCap: params.monthlyBudgetCap ?? 100.0,
      }),
    });
    if (!res.ok) throw new Error(`Mandate evaluation failed: ${res.statusText}`);
    return res.json();
  }

  async provisionComputeNode(params: {
    subscriptionId: string;
    contractorEmail: string;
  }): Promise<ProvisionResult> {
    const res = await fetch(`${this.baseUrl}/api/agent/provision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subscriptionId: params.subscriptionId,
        contractorEmail: params.contractorEmail,
      }),
    });
    if (!res.ok) throw new Error(`Compute node provisioning failed: ${res.statusText}`);
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
        contractorName: params.contractorName || 'Autonomous Compute Buyer',
        businessEntity: params.businessEntity || 'Nexus Autonomous Systems Corp',
        allocatedDid: params.allocatedDid || 'mcp+https://gateway-01.ap2.market',
        tradeVertical: params.tradeVertical || 'Autonomous Cloud Compute',
        monthlySubscriptionFee: params.monthlyFee || 79.99,
        paypalSubscriptionId: params.paypalSubId || 'I-AUTONOMOUS-8902',
        contractorEmail: params.contractorEmail || 'agent-alpha@nexus-systems.io',
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

  const client = new AP2CommerceClient();

  const health = await client.checkHealth();
  console.log(`1. Health Check: ${health.status} (Mock: ${health.mock_mode})`);

  const catalog = await client.getServiceCatalog();
  const service = catalog.trades[0];
  console.log(`2. Catalog Inquiry: Selected '${service.title}' at $${service.monthlySubscription}/mo`);

  const mandate = await client.evaluateSpendingMandate({
    buyerAgentId: 'agent-ts-buyer-01',
    amount: service.monthlySubscription,
    monthlyBudgetCap: 100.0,
  });
  console.log(`3. Mandate Check: Approved=${mandate.approved} (Proof: ${mandate.mandateProofHash.substring(0, 16)}...)`);

  console.log('\n✅ APIMatic TypeScript SDK Client Verified Successfully!\n');
}

// Export for module use or run if main
if (typeof require !== 'undefined' && require.main === module) {
  runTypeScriptAgent().catch(console.error);
}
