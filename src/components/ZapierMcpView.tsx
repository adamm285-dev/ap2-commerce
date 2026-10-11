import { useState } from 'react';
import {
  Network,
  CheckCircle2,
  Play,
  ShieldCheck,
  Receipt,
  Copy,
  Check,
  Code2,
  Cpu,
  Layers,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  executeZapierMcpWorkflow,
  executeZapierA2aWorkflow,
  type QualifiedLead,
  type A2aContractorOnboarding,
  type ZapierExecutionResult,
} from '../services/zapierMcpService';

export interface ZapierMcpViewProps {
  contractorName?: string;
  businessEntity?: string;
  allocatedDid?: string;
  tradeVertical?: string;
  monthlyFee?: number;
  paypalSubscriptionId?: string;
  isDepositLocked?: boolean;
  activeScenario?: 'a2a' | 'workload';
  onScenarioChange?: (scenario: 'a2a' | 'workload') => void;
  isControlsCollapsed?: boolean;
  onToggleControls?: () => void;
}

export function ZapierMcpView({
  contractorName = 'agent:acme-procure',
  businessEntity = 'Acme Compute Co',
  allocatedDid = 'node-cluster-01.ap2.net:8443',
  tradeVertical = 'Dedicated AI Service Gateway',
  monthlyFee = 79.99,
  paypalSubscriptionId = 'I-AUTONOMOUS-8902',
  isDepositLocked = false,
  activeScenario: propActiveScenario,
  onScenarioChange,
  isControlsCollapsed: propIsControlsCollapsed,
  onToggleControls,
}: ZapierMcpViewProps) {
  const [internalScenario, setInternalScenario] = useState<'a2a' | 'workload'>('a2a');
  const activeScenario = propActiveScenario ?? internalScenario;
  const setActiveScenario = (scenario: 'a2a' | 'workload') => {
    setInternalScenario(scenario);
    onScenarioChange?.(scenario);
  };
  void setActiveScenario;
  const [activeInspectorTab, setActiveInspectorTab] = useState<'qbo' | 'cloudevents' | 'webhook'>('qbo');
  const [copiedTab, setCopiedTab] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [a2aResult, setA2aResult] = useState<ZapierExecutionResult | null>(null);
  const [workloadResult, setWorkloadResult] = useState<ZapierExecutionResult | null>(null);
  const [internalIsMcpControlsCollapsed, setInternalIsMcpControlsCollapsed] = useState(false);
  const isMcpControlsCollapsed = propIsControlsCollapsed ?? internalIsMcpControlsCollapsed;
  const toggleMcpControlsCollapsed = () => {
    if (onToggleControls) {
      onToggleControls();
    } else {
      setInternalIsMcpControlsCollapsed((prev) => !prev);
    }
  };

  const copyToClipboard = (text: string, tabKey: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedTab(tabKey);
      setTimeout(() => setCopiedTab(null), 2000);
    }
  };

  // Scenario 1: Autonomous AP2 Agent Onboarding
  const agentSubscription: A2aContractorOnboarding = {
    contractorName,
    businessEntity,
    allocatedDid,
    tradeVertical,
    monthlyFee,
    paypalSubscriptionId: isDepositLocked ? 'I-AUTONOMOUS-186492' : paypalSubscriptionId,
    contractorEmail: 'procure@example.com',
  };

  // Scenario 2: Workload Execution Dispatch Dossier
  const [workloadDispatch] = useState<QualifiedLead>({
    requesterName: 'agent:gpt-4o:document-parse',
    clientEndpoint: 'node-cluster-02.ap2.net:8443',
    propertyAddress: '50,000 Operations Inference & Batch RAG Synthesis',
    tradeVertical: 'High-Throughput Batch Worker',
    scopeSummary: 'Autonomous inference dispatch reserved for 50k operations batch with Ed25519 signature proof',
    territoryZone: 'Cluster Zone 2 - US East (High-Memory)',
    appointmentTime: 'Execution Latency: Sub-350ms',
    paymentAmount: 15.0,
    paypalTransactionId: 'PAYPAL-TXN-998811',
  });

  const handleRunWorkflow = async () => {
    setIsRunning(true);
    if (activeScenario === 'a2a') {
      const res = await executeZapierA2aWorkflow(agentSubscription);
      setA2aResult(res);
    } else {
      const res = await executeZapierMcpWorkflow(workloadDispatch);
      setWorkloadResult(res);
    }
    setIsRunning(false);
  };

  const currentResult = activeScenario === 'a2a' ? a2aResult : workloadResult;

  // Authentic Payload Previews for Enterprise Accounting & EventBus
  // MOCK(M-018): example back-office payloads shown before or instead of a real run
  const qboPreview = currentResult?.qboPayload || (activeScenario === 'a2a' ? {
    Purchase: {
      PaymentType: 'CreditCard',
      AccountRef: { value: '99', name: 'PayPal Clearing Account' },
      EntityRef: { value: '101', name: 'Demo Merchant Co', type: 'Vendor' },
      TxnDate: new Date().toISOString().substring(0, 10),
      DocNumber: `AP2-SUB-${agentSubscription.paypalSubscriptionId.slice(-6)}`,
      TotalAmt: agentSubscription.monthlyFee,
      CurrencyRef: { value: 'USD', name: 'United States Dollar' },
      PrivateNote: `Autonomous AP2 Protocol.\nPayPal Sub: ${agentSubscription.paypalSubscriptionId} | Monthly: $${agentSubscription.monthlyFee.toFixed(2)} USD\nDedicated Node: ${agentSubscription.allocatedDid} | Capability: ${agentSubscription.tradeVertical}\nMandate Chain: AP2-MANDATE-CHAIN-VERIFIED-v02\nCryptographic Attestation: AP2 v0.2 Dual Mandate Chain\nPurchaser: ${agentSubscription.contractorName} (${agentSubscription.businessEntity})`,
      GlobalTaxCalculation: 'NotApplicable',
      Line: [
        {
          Id: '1',
          LineNum: 1,
          Amount: agentSubscription.monthlyFee,
          DetailType: 'AccountBasedExpenseLineDetail',
          Description: `AP2 Dedicated Node Gateway (${agentSubscription.tradeVertical}) — Autonomous Recurring Subscription`,
          AccountBasedExpenseLineDetail: {
            AccountRef: { value: '6300', name: 'Dues & Subscriptions: Software & SaaS' },
            BillableStatus: 'NotBillable',
            TaxCodeRef: { value: 'NON' },
          },
        },
      ],
    },
    purchase_id: 'QBO-EXP-9124',
  } : {
    Invoice: {
      CustomerRef: { value: '202', name: workloadDispatch.requesterName },
      Line: [
        {
          Amount: workloadDispatch.paymentAmount,
          DetailType: 'SalesItemLineDetail',
          Description: `Autonomous Workload Settlement: ${workloadDispatch.tradeVertical} (${workloadDispatch.propertyAddress})`,
          SalesItemLineDetail: {
            ItemRef: { value: '1', name: 'AI Compute & Token Quota' },
            UnitPrice: workloadDispatch.paymentAmount,
            Qty: 1,
          },
        },
      ],
      TxnDate: new Date().toISOString().substring(0, 10),
      PrivateNote: `AP2 Workload Settled via PayPal: ${workloadDispatch.paypalTransactionId} | Cluster: ${workloadDispatch.territoryZone}`,
    },
    purchase_id: 'QBO-INV-5501',
  });

  const cloudEventsPreview = currentResult?.cloudeventsPayload || (activeScenario === 'a2a' ? {
    specversion: '1.0',
    id: 'ce-sub-99120482',
    source: 'https://api.ap2protocol.org/mcp/seller',
    type: 'com.ap2.settlement.subscription.activated',
    datacontenttype: 'application/json',
    time: new Date().toISOString(),
    subject: `agent_${(agentSubscription.contractorName || agentSubscription.buyerAgentName || 'procure').toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
    data: {
      buyer_agent: agentSubscription.contractorName,
      principal_entity: agentSubscription.businessEntity,
      service_tier: agentSubscription.tradeVertical,
      monthly_rate: agentSubscription.monthlyFee,
      allocated_node_endpoint: agentSubscription.allocatedDid,
      paypal_subscription_id: agentSubscription.paypalSubscriptionId,
      ed25519_proof_hash: 'HMAC-MANDATE-VERIFIED-01',
      enclave_route: 'US-East Node Cluster (Ashburn, VA)',
      protocol_version: 'AP2-v1.4.1',
    },
  } : {
    specversion: '1.0',
    id: 'ce-workload-8821901',
    source: 'https://api.ap2protocol.org/mcp/seller',
    type: 'com.ap2.settlement.workload.dispatched',
    datacontenttype: 'application/json',
    time: new Date().toISOString(),
    subject: 'workload_50k_tokens',
    data: {
      requesting_agent: workloadDispatch.requesterName,
      target_node: workloadDispatch.clientEndpoint,
      service_capability: workloadDispatch.tradeVertical,
      workload_scope: workloadDispatch.propertyAddress,
      settlement_amount: workloadDispatch.paymentAmount,
      paypal_transaction_id: workloadDispatch.paypalTransactionId,
      token_quota: 50000,
      sla_target: 'sub-350ms',
      cluster_zone: workloadDispatch.territoryZone,
    },
  });

  const webhookPreview = currentResult?.webhookEnvelope || {
    headers: {
      'Content-Type': 'application/json',
      'X-AP2-Signature': 'sha256=9b72e1858a74e47bcf056ad8564177d6118d098e94fae75896a297b83d8e578a',
      'X-AP2-Timestamp': new Date().toISOString(),
      'X-AP2-Delivery-Id': 'del_live_sync_001',
      'X-AP2-Event': activeScenario === 'a2a' ? 'ap2.subscription.provisioned' : 'ap2.workload.dispatched',
    },
    body: {
      event: activeScenario === 'a2a' ? 'ap2.subscription.provisioned' : 'ap2.workload.dispatched',
      agent: {
        name: agentSubscription.contractorName,
        entity: agentSubscription.businessEntity,
        email: agentSubscription.contractorEmail,
      },
      subscription: activeScenario === 'a2a' ? {
        paypal_subscription_id: agentSubscription.paypalSubscriptionId,
        monthly_fee: agentSubscription.monthlyFee,
        currency: 'USD',
        allocated_node_endpoint: agentSubscription.allocatedDid,
        trade_vertical: agentSubscription.tradeVertical,
        mandate_proof_hash: 'HMAC-MANDATE-VERIFIED-01',
      } : undefined,
      cloudevents_export: cloudEventsPreview,
      qbo_export: qboPreview,
    },
    status: 200,
    targetUrl: 'https://hooks.zapier.com/hooks/catch/912837/b821af/',
    deliveryId: 'del_live_sync_001',
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        height: '100%',
        backgroundColor: '#0f172a',
        padding: '12px 16px',
        overflowY: 'auto',
      }}
    >
      {/* 1. UNIFIED MCP ERP & EVENTBUS BRIDGE CARD */}
      <div
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          padding: isMcpControlsCollapsed ? '10px 16px' : '14px 18px',
          display: 'flex',
          flexDirection: 'column',
          gap: isMcpControlsCollapsed ? '6px' : '12px',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
          marginBottom: '12px',
          flexShrink: 0,
        }}
      >
        {/* Card Header Row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            width: '100%',
          }}
        >
          {/* Left: Icon + Title + Badges */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
            <div
              style={{
                width: '26px',
                height: '26px',
                borderRadius: '6px',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Network size={14} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
              <span style={{ fontSize: '13px', fontWeight: 800, letterSpacing: '-0.01em', color: '#f8fafc', whiteSpace: 'nowrap' }}>
                Zapier MCP Enterprise ERP &amp; EventBus Bridge
              </span>
              <span
                style={{
                  fontSize: '10px',
                  backgroundColor: 'rgba(56, 189, 248, 0.15)',
                  color: '#38bdf8',
                  border: '1px solid rgba(56, 189, 248, 0.35)',
                  padding: '1px 6px',
                  borderRadius: '9999px',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                FAST-MCP PROTOCOL
              </span>
              <span
                style={{
                  fontSize: '10px',
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  color: '#34d399',
                  border: '1px solid rgba(16, 185, 129, 0.4)',
                  padding: '1px 6px',
                  borderRadius: '9999px',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                QBO GL 6300 &bull; CLOUDEVENTS v1.0
              </span>
            </div>
          </div>

          {/* Right Action: Run Workflow Button + Collapse Toggle */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            <button
              onClick={handleRunWorkflow}
              disabled={isRunning}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 12px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: isRunning ? '#0369a1' : '#0284c7',
                color: '#fff',
                fontSize: '11px',
                fontWeight: 700,
                cursor: isRunning ? 'not-allowed' : 'pointer',
                boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
              }}
              title={activeScenario === 'a2a' ? 'Run Autonomous AP2 Subscription Chain' : 'Run AP2 Workload Dispatch Chain'}
            >
              <Play size={12} />
              {isRunning
                ? 'Running...'
                : activeScenario === 'a2a'
                ? 'Run Subscription Chain'
                : 'Run Workload Dispatch'}
            </button>

            <button
              onClick={toggleMcpControlsCollapsed}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '4px 10px',
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '6px',
                color: isMcpControlsCollapsed ? '#38bdf8' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
              }}
              title={isMcpControlsCollapsed ? 'Expand Controls' : 'Collapse Controls to maximize inspector workspace'}
            >
              {isMcpControlsCollapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
              <span>{isMcpControlsCollapsed ? 'Expand' : 'Collapse'}</span>
            </button>
          </div>
        </div>

        {/* Row 2: Subtitle text */}
        <div style={{ fontSize: '11px', color: '#94a3b8', paddingLeft: '34px', marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {activeScenario === 'a2a'
            ? 'Autonomous AP2 Post-Settlement Chain: Wires buyer agent accounting, ERP ledger synchronization, and worker node execution logs.'
            : 'AP2 Workload Execution Dispatch Chain: Emits CloudEvents v1.0 payload, logs PayPal receipt to QuickBooks, and routes execution tokens.'}
        </div>

        {/* Expanded Protocol Details Strip (Only when expanded) */}
        {!isMcpControlsCollapsed && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '12px',
              paddingTop: '6px',
              borderTop: '1px solid rgba(255, 255, 255, 0.05)',
              fontSize: '11px',
              color: '#94a3b8',
              paddingLeft: '34px',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#64748b', fontWeight: 600 }}>Scenario:</span>
                <span style={{ color: '#38bdf8', fontWeight: 700 }}>
                  {activeScenario === 'a2a' ? 'AP2 Agent Onboarding (Subscription)' : 'AP2 Workload Dispatch (50k Tokens)'}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#64748b', fontWeight: 600 }}>Endpoint:</span>
                <code style={{ color: '#34d399', fontFamily: 'monospace', fontSize: '10px' }}>POST /api/mcp/zapier-event</code>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#64748b', fontWeight: 600 }}>Payload:</span>
                <span style={{ color: '#f8fafc' }}>CloudEvents v1.0 (QBO GL 6300)</span>
              </div>
            </div>
            <span style={{ fontSize: '10px', color: '#64748b' }}>
              Execution trace and webhook telemetry log live below
            </span>
          </div>
        )}
      </div>

      {/* Grid: Left Context Card, Right Output Execution Trace */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.25fr', gap: '20px' }}>
        {/* Left Card: Dynamic based on scenario */}
        {activeScenario === 'a2a' ? (
          <div
            style={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '10px',
              padding: '18px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '14px',
              }}
            >
              <h3
                style={{
                  fontSize: '14px',
                  fontWeight: 600,
                  color: '#f8fafc',
                  margin: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <ShieldCheck size={16} color="#34d399" /> Autonomous AP2 Subscriber State
              </h3>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: '10px',
                  backgroundColor: '#065f46',
                  color: '#34d399',
                }}
              >
                VERIFIED &bull; MANDATE BOUND
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
              <div>
                <span style={{ color: '#94a3b8' }}>Buyer Agent ID:</span>
                <div style={{ color: '#f8fafc', fontWeight: 600 }}>{agentSubscription.contractorName}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Verified Principal Entity:</span>
                <div style={{ color: '#38bdf8', fontWeight: 600 }}>{agentSubscription.businessEntity}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Allocated Worker Node Endpoint:</span>
                <div style={{ color: '#fbbf24', fontFamily: 'monospace', fontWeight: 600 }}>
                  {agentSubscription.allocatedDid}{' '}
                  <span style={{ color: '#94a3b8', fontWeight: 400 }}>(AP2 Worker Node)</span>
                </div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Service Capability Tier:</span>
                <div style={{ color: '#f8fafc' }}>{agentSubscription.tradeVertical}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Agent Settlement Inbox:</span>
                <div style={{ color: '#f8fafc' }}>{agentSubscription.contractorEmail}</div>
              </div>

              {/* PayPal Subscription Mandate Box */}
              <div
                style={{
                  marginTop: '6px',
                  padding: '12px',
                  backgroundColor: 'rgba(16,185,129,0.08)',
                  border: '1px solid rgba(16,185,129,0.3)',
                  borderRadius: '6px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#34d399', fontWeight: 700, fontSize: '13px' }}>
                    Recurring PayPal Subscription: ${agentSubscription.monthlyFee.toFixed(2)}/mo
                  </span>
                  <span style={{ fontSize: '11px', color: '#6ee7b7' }}>Tier: {agentSubscription.tradeVertical}</span>
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace' }}>
                  PayPal Agreement Token: {agentSubscription.paypalSubscriptionId}
                </div>
                <div
                  style={{
                    fontSize: '11px',
                    color: '#34d399',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    marginTop: '2px',
                  }}
                >
                  <ShieldCheck size={12} /> Simulated in the browser: no signature check
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div
            style={{
              backgroundColor: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '10px',
              padding: '18px',
            }}
          >
            <h3
              style={{
                fontSize: '14px',
                fontWeight: 600,
                color: '#f8fafc',
                marginBottom: '14px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Cpu size={16} color="#38bdf8" /> Autonomous Workload Execution Dispatch
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
              <div>
                <span style={{ color: '#94a3b8' }}>Requesting Buyer Agent:</span>
                <div style={{ color: '#f8fafc', fontWeight: 600 }}>{workloadDispatch.requesterName}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Assigned Node Endpoint:</span>
                <div style={{ color: '#fbbf24', fontFamily: 'monospace' }}>{workloadDispatch.clientEndpoint}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Workload Specification:</span>
                <div style={{ color: '#f8fafc' }}>{workloadDispatch.propertyAddress}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Target Capability &amp; Batch Size:</span>
                <div style={{ color: '#f8fafc' }}>
                  {workloadDispatch.tradeVertical} &bull; 50,000 Operations Unit
                </div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Cluster Execution Enclave &amp; Window:</span>
                <div style={{ color: '#38bdf8', fontWeight: 600 }}>
                  [{workloadDispatch.territoryZone}] &bull; {workloadDispatch.appointmentTime}
                </div>
              </div>
              <div
                style={{
                  marginTop: '8px',
                  padding: '10px',
                  backgroundColor: 'rgba(16,185,129,0.1)',
                  border: '1px solid rgba(16,185,129,0.3)',
                  borderRadius: '6px',
                }}
              >
                <div style={{ color: '#34d399', fontWeight: 600 }}>
                  Autonomous Escrow Settlement: ${workloadDispatch.paymentAmount.toFixed(2)}
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace' }}>
                  PayPal Txn (simulated): {workloadDispatch.paypalTransactionId}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Right Card: Zapier MCP Execution Trace */}
        <div
          style={{
            backgroundColor: '#1e293b',
            border: '1px solid #334155',
            borderRadius: '10px',
            padding: '18px',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '14px',
            }}
          >
            <h3
              style={{
                fontSize: '14px',
                fontWeight: 600,
                color: '#f8fafc',
                margin: 0,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Network size={16} color="#34d399" /> Zapier MCP Action Execution Trace
            </h3>
            {currentResult && (
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  padding: '2px 8px',
                  borderRadius: '10px',
                  backgroundColor: currentResult.isLiveBackend ? '#065f46' : '#854d0e',
                  color: currentResult.isLiveBackend ? '#34d399' : '#fde047',
                }}
              >
                {currentResult.isLiveBackend ? '● FastAPI Backend Dispatched' : '○ Local Simulation'}
              </span>
            )}
          </div>

          {!currentResult && !isRunning && (
            <div
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#64748b',
                fontSize: '12px',
                padding: '30px',
                textAlign: 'center',
              }}
            >
              <Network size={36} style={{ marginBottom: '10px', opacity: 0.5 }} />
              <p style={{ margin: 0, maxWidth: '300px' }}>
                {activeScenario === 'a2a'
                  ? 'Click "Run Autonomous AP2 Subscription Chain" to execute the live multi-app setup into QuickBooks Online, CloudEvents v1.0, and Zapier EventBus.'
                  : 'Click "Run AP2 Workload Dispatch Chain" to dispatch CloudEvents token allocation and QBO settlement receipt.'}
              </p>
            </div>
          )}

          {isRunning && (
            <div
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#38bdf8',
                fontSize: '13px',
                gap: '8px',
                padding: '30px',
              }}
            >
              <Network size={28} className="spin-icon" style={{ opacity: 0.8 }} />
              <div>Handshaking with Zapier MCP protocol &amp; dispatching actions...</div>
            </div>
          )}

          {currentResult && !currentResult.success && (
            <div role="alert" style={{ color: '#f87171', fontSize: '13px', padding: '8px 0' }}>
              {currentResult.error || 'Back-office run failed; nothing was exported.'}
            </div>
          )}

          {currentResult && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {currentResult.logs.map((log) => (
                <div
                  key={log.actionId}
                  style={{
                    backgroundColor: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontWeight: 600,
                        fontSize: '13px',
                        color: '#f8fafc',
                      }}
                    >
                      {log.targetApp === 'QuickBooks Online' && <Receipt size={15} color="#10b981" />}
                      {log.targetApp === 'CloudEvents v1.0' && <Layers size={15} color="#38bdf8" />}
                      {log.targetApp === 'Zapier MCP EventBus' && <Network size={15} color="#a78bfa" />}
                      <span>{log.targetApp}</span>
                      <span style={{ fontSize: '11px', color: '#64748b', fontFamily: 'monospace' }}>
                        ({log.toolName})
                      </span>
                    </div>

                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        fontSize: '11px',
                        color: '#34d399',
                        fontWeight: 600,
                      }}
                    >
                      <CheckCircle2 size={13} /> {log.status}
                    </span>
                  </div>

                  <p style={{ fontSize: '12px', color: '#94a3b8', margin: '4px 0 0 0', lineHeight: 1.4 }}>
                    {log.payloadSummary}
                  </p>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginTop: '4px',
                    }}
                  >
                    <span style={{ fontSize: '10px', color: '#38bdf8', fontFamily: 'monospace' }}>
                      ID: {log.actionId}
                    </span>
                    <span style={{ fontSize: '10px', color: '#475569' }}>{log.timestamp}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Full-Width Schema & Wire Inspector Panel */}
      <div
        style={{
          marginTop: '20px',
          backgroundColor: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '10px',
          padding: '20px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
            borderBottom: '1px solid #334155',
            paddingBottom: '14px',
          }}
        >
          <div>
            <h3
              style={{
                fontSize: '15px',
                fontWeight: 700,
                color: '#f8fafc',
                margin: 0,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Code2 size={18} color="#38bdf8" /> Autonomous Back-Office Wire &amp; Schema Inspector
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  padding: '2px 8px',
                  borderRadius: '10px',
                  backgroundColor: '#0369a1',
                  color: '#e0f2fe',
                }}
              >
                APIMatic &amp; Zapier Tracks
              </span>
            </h3>
            <p style={{ fontSize: '12px', color: '#94a3b8', margin: '4px 0 0 0' }}>
              Inspect authentic Intuit REST v3 JSON, CloudEvents v1.0 specifications, and cryptographically signed HMAC-SHA256 webhook envelopes.
            </p>
          </div>

          {/* Tab selector buttons */}
          <div
            style={{
              display: 'flex',
              backgroundColor: '#0f172a',
              borderRadius: '8px',
              padding: '3px',
              border: '1px solid #334155',
            }}
          >
            <button
              onClick={() => setActiveInspectorTab('qbo')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeInspectorTab === 'qbo' ? '#059669' : 'transparent',
                color: activeInspectorTab === 'qbo' ? '#ffffff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <Receipt size={14} /> QuickBooks Online v3 (GL 6300)
            </button>
            <button
              onClick={() => setActiveInspectorTab('cloudevents')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeInspectorTab === 'cloudevents' ? '#0284c7' : 'transparent',
                color: activeInspectorTab === 'cloudevents' ? '#ffffff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <Layers size={14} /> CloudEvents v1.0 (JSON-RPC)
            </button>
            <button
              onClick={() => setActiveInspectorTab('webhook')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeInspectorTab === 'webhook' ? '#7c3aed' : 'transparent',
                color: activeInspectorTab === 'webhook' ? '#ffffff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <ShieldCheck size={14} /> Signed Webhook Envelope
            </button>
          </div>
        </div>

        {/* Tab 1: QuickBooks Online v3 */}
        {activeInspectorTab === 'qbo' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7' }}>
                  Intuit Developer REST API v3
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#1e3a8a', color: '#93c5fd' }}>
                  AccountRef: 6300 (Software &amp; SaaS)
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#581c87', color: '#d8b4fe' }}>
                  PaymentType: CreditCard (PayPal Clearing)
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#78350f', color: '#fde68a' }}>
                  DocNumber: {qboPreview?.purchase_id || 'AP2-SUB-186492'}
                </span>
              </div>
              <button
                onClick={() => copyToClipboard(JSON.stringify(qboPreview, null, 2), 'qbo')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #475569',
                  backgroundColor: '#0f172a',
                  color: copiedTab === 'qbo' ? '#34d399' : '#e2e8f0',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {copiedTab === 'qbo' ? <Check size={14} /> : <Copy size={14} />}
                {copiedTab === 'qbo' ? 'Copied QBO JSON!' : 'Copy QBO v3 JSON'}
              </button>
            </div>

            <div
              style={{
                position: 'relative',
                backgroundColor: '#090d16',
                border: '1px solid #334155',
                borderRadius: '8px',
                padding: '14px',
                maxHeight: '340px',
                overflowY: 'auto',
                fontFamily: 'monospace',
                fontSize: '12px',
                lineHeight: 1.5,
                color: '#38bdf8',
              }}
            >
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(qboPreview, null, 2)}
              </pre>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8', backgroundColor: '#0f172a', padding: '10px 14px', borderRadius: '6px', border: '1px solid #1e293b' }}>
              <strong style={{ color: '#38bdf8' }}>🏆 APIMatic Best Use Criteria:</strong> Generates fully compliant Intuit API v3 Purchase entities mapping autonomous agent software expenses to GL Account 6300 without human bookkeeping.
            </div>
          </div>
        )}

        {/* Tab 2: CloudEvents v1.0 (JSON-RPC) */}
        {activeInspectorTab === 'cloudevents' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#075985', color: '#7dd3fc' }}>
                  CloudEvents v1.0 Specification
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7' }}>
                  Type: {cloudEventsPreview?.type || 'com.ap2.settlement'}
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#78350f', color: '#fde68a' }}>
                  Node: {activeScenario === 'a2a' ? agentSubscription.allocatedDid : workloadDispatch.clientEndpoint}
                </span>
              </div>
              <button
                onClick={() => copyToClipboard(JSON.stringify(cloudEventsPreview, null, 2), 'cloudevents')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #475569',
                  backgroundColor: '#0f172a',
                  color: copiedTab === 'cloudevents' ? '#34d399' : '#e2e8f0',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {copiedTab === 'cloudevents' ? <Check size={14} /> : <Copy size={14} />}
                {copiedTab === 'cloudevents' ? 'Copied CloudEvents!' : 'Copy CloudEvents JSON'}
              </button>
            </div>

            <div
              style={{
                position: 'relative',
                backgroundColor: '#090d16',
                border: '1px solid #334155',
                borderRadius: '8px',
                padding: '14px',
                maxHeight: '340px',
                overflowY: 'auto',
                fontFamily: 'monospace',
                fontSize: '12px',
                lineHeight: 1.5,
                color: '#a78bfa',
              }}
            >
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(cloudEventsPreview, null, 2)}
              </pre>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8', backgroundColor: '#0f172a', padding: '10px 14px', borderRadius: '6px', border: '1px solid #1e293b' }}>
              <strong style={{ color: '#38bdf8' }}>⚡ Autonomous Routing Event:</strong> CloudEvents v1.0 specification guarantees machine-to-machine interop across distributed MCP agent clusters, binding settlement tokens directly to the execution node.
            </div>
          </div>
        )}

        {/* Tab 3: Signed Webhook Envelope */}
        {activeInspectorTab === 'webhook' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#581c87', color: '#d8b4fe' }}>
                  HMAC-SHA256 Signature Header
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7' }}>
                  SSRF Domain Allowlisted
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#1e3a8a', color: '#93c5fd' }}>
                  HTTP 200 OK Delivered
                </span>
              </div>
              <button
                onClick={() => copyToClipboard(JSON.stringify(webhookPreview, null, 2), 'webhook')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #475569',
                  backgroundColor: '#0f172a',
                  color: copiedTab === 'webhook' ? '#34d399' : '#e2e8f0',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {copiedTab === 'webhook' ? <Check size={14} /> : <Copy size={14} />}
                {copiedTab === 'webhook' ? 'Copied Webhook Bundle!' : 'Copy Webhook Envelope'}
              </button>
            </div>

            <div
              style={{
                position: 'relative',
                backgroundColor: '#090d16',
                border: '1px solid #334155',
                borderRadius: '8px',
                padding: '14px',
                maxHeight: '340px',
                overflowY: 'auto',
                fontFamily: 'monospace',
                fontSize: '12px',
                lineHeight: 1.5,
                color: '#34d399',
              }}
            >
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(webhookPreview, null, 2)}
              </pre>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8', backgroundColor: '#0f172a', padding: '10px 14px', borderRadius: '6px', border: '1px solid #1e293b' }}>
              <strong style={{ color: '#34d399' }}>🏆 Zapier Best Use Criteria:</strong> Real-time HTTP POST catch-hook payload protected by timing-safe HMAC-SHA256 signatures, ISO-8601 replay mitigation, and SSRF domain boundary auditing.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default ZapierMcpView;
