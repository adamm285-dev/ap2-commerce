/**
 * Zapier MCP (Model Context Protocol) Integration Service
 *
 * Dispatches autonomous downline business actions to enterprise back-office tools
 * (QuickBooks Online, CloudEvents v1.0 EventBus, Zapier Catch-Hooks) when an autonomous
 * AP2 Agent subscription or workload execution dispatch is verified.
 *
 * Connects to FastAPI backend at POST /api/mcp/zapier-sync matching OpenAPI 3.1.0.
 */

export interface A2aBuyerOnboarding {
  buyerAgentName?: string;
  principalEntity?: string;
  allocatedEndpoint?: string;
  serviceCapability?: string;
  monthlyFee: number;
  paypalSubscriptionId: string;
  principalEmail?: string;
  // Backward compatibility fields
  contractorName?: string;
  businessEntity?: string;
  allocatedDid?: string;
  tradeVertical?: string;
  contractorEmail?: string;
}

export type A2aContractorOnboarding = A2aBuyerOnboarding;

export interface QualifiedLead {
  requesterName: string;
  clientEndpoint: string;
  propertyAddress: string;
  tradeVertical: string;
  scopeSummary: string;
  territoryZone: string;
  appointmentTime: string;
  paymentAmount: number;
  paypalTransactionId: string;
}

export interface ZapierMcpActionLog {
  actionId: string;
  toolName: string;
  targetApp: 'QuickBooks Online' | 'CloudEvents v1.0' | 'Zapier MCP EventBus' | 'Google Workspace' | 'Enterprise ERP' | 'Google Calendar';
  status: 'PENDING' | 'EXECUTED' | 'GENERATED' | 'DRY_RUN' | 'DELIVERED' | 'FAILED' | 'BLOCKED' | 'SIMULATED';
  payloadSummary: string;
  timestamp: string;
}

export interface ZapierExecutionResult {
  success: boolean;
  jobId: string;
  logs: ZapierMcpActionLog[];
  isLiveBackend?: boolean;
  error?: string;
  cloudeventsPayload?: any;
  erpPayload?: any;
  qboPayload?: any;
  webhookEnvelope?: {
    headers: Record<string, string>;
    body: any;
    status: number | null;
    targetUrl: string;
    deliveryId: string;
    dryRun?: boolean;
  };
  webhookDryRun?: boolean;
  webhookDispatched?: boolean;
  webhookStatusCode?: number | null;
  webhookError?: string | null;
}

/**
 * Executes the 2-step Zapier MCP automation chain for AP2 Autonomous Agent Onboarding:
 * 1. QuickBooks Online: Prepares SaaS software purchase export package (GL 6300: Software & SaaS)
 * 2. Webhook / EventBus: Dispatches authentic HMAC-SHA256 signed webhook envelope (or dry-run export)
 */
// MOCK(M-020): client-side AP2-SYNC-<random> job ID and demo fallback fields for onboarding sync
export async function executeZapierA2aWorkflow(
  buyer: A2aBuyerOnboarding
): Promise<ZapierExecutionResult> {
  const syncId = `AP2-SYNC-${Math.floor(10000 + Math.random() * 90000)}`;
  const now = () => new Date().toISOString().replace('T', ' ').substring(0, 19);
  const agentName = buyer.buyerAgentName || buyer.contractorName || 'AutonomousBuyerAgent';
  const entity = buyer.principalEntity || buyer.businessEntity || 'Demo Buyer Corp';
  const endpoint = buyer.allocatedEndpoint || buyer.allocatedDid || 'mcp+https://gateway-01.example.com/mcp';
  const capability = buyer.serviceCapability || buyer.tradeVertical || 'Dedicated AI Service Gateway';
  const email = buyer.principalEmail || buyer.contractorEmail || 'merchant@example.com';

  try {
    const res = await fetch('/api/mcp/zapier-sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workflowType: 'a2a_onboarding',
        jobId: syncId,
        contractorName: agentName,
        businessEntity: entity,
        allocatedDid: endpoint,
        tradeVertical: capability,
        monthlySubscriptionFee: buyer.monthlyFee,
        paypalSubscriptionId: buyer.paypalSubscriptionId,
        contractorEmail: email,
      }),
    });

    if (res.ok) {
      const data = await res.json();

      const webhookStatus: ZapierMcpActionLog['status'] = data.webhookDryRun
        ? 'DRY_RUN'
        : data.webhookDispatched
        ? 'DELIVERED'
        : data.webhookError
        ? (data.webhookError.includes('SSRF') || data.webhookError.includes('blocked') ? 'BLOCKED' : 'FAILED')
        : 'FAILED';

      const webhookSummary = data.webhookDryRun
        ? `Dry run: computed authentic HMAC-SHA256 signature for export bundle (0 network calls dispatched)`
        : data.webhookDispatched
        ? `Dispatched HMAC-SHA256 signed webhook envelope to ${data.webhookTargetUrl || 'target'} (HTTP ${data.webhookStatusCode})`
        : `Webhook dispatch blocked/failed: ${data.webhookError || 'unknown error'}`;

      const logs: ZapierMcpActionLog[] = [
        {
          actionId: data.qboDraftInvoiceId || '',
          toolName: 'zapier_mcp_qbo_record_expense',
          targetApp: 'QuickBooks Online',
          status: 'GENERATED',
          payloadSummary: `Generated QuickBooks Online v3 Purchase payload ($${buyer.monthlyFee.toFixed(2)}/mo) under GL 6300: Software & SaaS for ${entity} (Sub: ${buyer.paypalSubscriptionId})`,
          timestamp: now(),
        },
        {
          actionId: data.webhookDeliveryId || '',
          toolName: 'zapier_mcp_eventbus_export',
          targetApp: 'Zapier MCP EventBus',
          status: webhookStatus,
          payloadSummary: webhookSummary,
          timestamp: now(),
        },
      ];

      const webhookEnvelope = {
        headers: data.webhookHeaders || {},
        body: {
          event: 'a2a.subscription.provisioned',
          contractor: {
            name: agentName,
            entity: entity,
            email: email,
          },
          subscription: {
            paypal_subscription_id: buyer.paypalSubscriptionId,
            monthly_fee: buyer.monthlyFee,
            currency: 'USD',
            allocated_did: endpoint,
            trade_vertical: capability,
          },
          erp_export: data.erpPayload,
          qbo_export: data.qboPayload,
        },
        status: data.webhookStatusCode ?? null,
        targetUrl: data.webhookTargetUrl || 'none (dry run)',
        deliveryId: data.webhookDeliveryId || '',
        dryRun: data.webhookDryRun ?? true,
      };

      return {
        success: true,
        jobId: syncId,
        logs,
        isLiveBackend: true,
        erpPayload: data.erpPayload,
        qboPayload: data.qboPayload,
        webhookEnvelope,
        webhookDryRun: data.webhookDryRun,
        webhookDispatched: data.webhookDispatched,
        webhookStatusCode: data.webhookStatusCode,
        webhookError: data.webhookError,
      };
    }
  } catch (err) {
    console.warn('[Zapier MCP AP2] Back-office backend not reachable:', err);
  }

  // Fail closed: report that nothing ran instead of inventing completed actions
  return {
    success: false,
    jobId: syncId,
    logs: [],
    isLiveBackend: false,
    error: 'Back-office backend unavailable; nothing was exported.',
  };
}

/**
 * Executes the 3-step Zapier MCP automation chain for AP2 Workload Execution Dispatch:
 * 1. CloudEvents v1.0: Publishes com.ap2.settlement.workload.dispatched with 50,000 token quota
 * 2. QuickBooks Online: Records micro-settlement receipt against PayPal Vault MIT
 * 3. Zapier MCP EventBus: Routes workload execution payload to dedicated hardware cluster
 */
export async function executeZapierMcpWorkflow(
  lead: QualifiedLead
): Promise<ZapierExecutionResult> {
  // MOCK(M-020): workload dispatch is simulated entirely in the browser; no backend call
  const dispatchId = `DISPATCH-${Math.floor(10000 + Math.random() * 90000)}`;
  const now = () => new Date().toISOString().replace('T', ' ').substring(0, 19);
  const capability = lead.tradeVertical || 'Dedicated AI Service Gateway';
  const targetNode = lead.clientEndpoint || 'mcp+https://gateway-01.example.com/mcp';
  const scope = lead.propertyAddress || 'Autonomous AP2 Workload Execution';

  await new Promise((resolve) => setTimeout(resolve, 600));

  const workloadCloudEventsPayload = {
    specversion: '1.0',
    id: `ce-workload-${Math.floor(100000 + Math.random() * 900000)}`,
    source: 'https://api.ap2protocol.org/mcp/seller',
    type: 'com.ap2.settlement.workload.dispatched',
    datacontenttype: 'application/json',
    time: new Date().toISOString(),
    subject: `workload_50k_tokens`,
    data: {
      requesting_agent: lead.requesterName,
      target_node: targetNode,
      service_capability: capability,
      workload_scope: scope,
      settlement_amount: lead.paymentAmount,
      paypal_transaction_id: lead.paypalTransactionId,
      token_quota: 50000,
      sla_target: 'sub-350ms',
      cluster_zone: lead.territoryZone,
    },
  };

  const workloadQboPayload = {
    Invoice: {
      CustomerRef: { value: '202', name: lead.requesterName },
      Line: [
        {
          Amount: lead.paymentAmount,
          DetailType: 'SalesItemLineDetail',
          Description: `Autonomous Workload Settlement: ${capability} (${scope})`,
          SalesItemLineDetail: {
            ItemRef: { value: '1', name: 'AI Compute & Token Quota' },
            UnitPrice: lead.paymentAmount,
            Qty: 1,
          },
        },
      ],
      TxnDate: new Date().toISOString().substring(0, 10),
      PrivateNote: `AP2 Workload Settled via PayPal: ${lead.paypalTransactionId} | Cluster: ${lead.territoryZone}`,
    },
    purchase_id: `QBO-INV-${Math.floor(1000 + Math.random() * 9000)}`,
  };

  const logs: ZapierMcpActionLog[] = [
    {
      actionId: `CE-${Math.floor(1000 + Math.random() * 9000)}`,
      toolName: 'zapier_mcp_cloudevents_dispatch_workload',
      targetApp: 'CloudEvents v1.0',
      status: 'SIMULATED',
      payloadSummary: `Dispatched CloudEvents v1.0 payload to ${targetNode} for 50,000 token workload (${capability})`,
      timestamp: now(),
    },
    {
      actionId: workloadQboPayload.purchase_id,
      toolName: 'zapier_mcp_qbo_record_receipt',
      targetApp: 'QuickBooks Online',
      status: 'SIMULATED',
      payloadSummary: `Generated QBO invoice & settlement receipt for $${lead.paymentAmount.toFixed(2)} via PayPal (Txn: ${lead.paypalTransactionId})`,
      timestamp: now(),
    },
    {
      actionId: `EB-${Math.floor(1000 + Math.random() * 9000)}`,
      toolName: 'zapier_mcp_eventbus_route_enclave',
      targetApp: 'Zapier MCP EventBus',
      status: 'SIMULATED',
      payloadSummary: `Routed execution credentials to ${lead.territoryZone} with execution target sub-350ms`,
      timestamp: now(),
    },
  ];

  return {
    success: true,
    jobId: dispatchId,
    logs,
    isLiveBackend: false,
    cloudeventsPayload: workloadCloudEventsPayload,
    erpPayload: workloadCloudEventsPayload,
    qboPayload: workloadQboPayload,
  };
}
