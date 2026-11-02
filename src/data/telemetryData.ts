import type { AgDataSourcesDefinition, AgReportState } from 'ag-studio';

export interface CatalogPlan {
  id: string;
  name: string;
  price: number;
  tasks: number;
}

export const CATALOG_PLANS: readonly CatalogPlan[] = [
  {
    id: 'ap2-batch',
    name: 'High-Throughput Batch Worker',
    price: 49.99,
    tasks: 125,
  },
  {
    id: 'ap2-gateway',
    name: 'Dedicated AI Service Gateway',
    price: 79.99,
    tasks: 450,
  },
  {
    id: 'ap2-cluster',
    name: 'Enterprise Cluster Node',
    price: 179.99,
    tasks: 1200,
  },
] as const;

export interface A2aTransaction {
  id: string;
  timestamp: string;
  buyer_agent: string;
  principal_entity: string;
  contractor_name: string; // Compatibility alias for principal_entity
  trade_vertical: string; // Capability / Execution Service
  service_plan: string; // Service Plan Tier
  monthly_amount: number;
  paypal_sub_id: string;
  kyc_status: string;
  kyc_legal_entity: string; // Compatibility alias
  allocated_did: string; // Worker node endpoint / execution cluster
  tcpa_guard: string; // Cryptographic Proof / Anti-Tamper
  status: string;
  mandate_proof?: string;
  anti_tamper_hash?: string;
  node_cluster?: string;
  data_source?: string;
}

// MOCK(M-018): hardcoded dashboard transactions
export const initialA2aTransactions: A2aTransaction[] = [
  {
    id: 'TXN-AP2-9021',
    timestamp: '2026-10-02 02:14:22',
    buyer_agent: 'AutonomousBuyerAgent-Alpha-Batch',
    principal_entity: 'Demo Buyer Corp',
    contractor_name: 'AutonomousBuyerAgent-Alpha-Batch',
    trade_vertical: 'High-Throughput Batch Worker',
    service_plan: 'High-Throughput Batch Worker ($49.99/mo)',
    monthly_amount: 49.99,
    paypal_sub_id: 'Awaiting PayPal Token',
    kyc_status: 'Pending Mandate Challenge',
    kyc_legal_entity: 'Demo Buyer Corp',
    allocated_did: 'Awaiting Endpoint',
    tcpa_guard: 'PENDING ES256 ACTIVATION',
    mandate_proof: 'ES256 Awaiting Nonce Signature',
    anti_tamper_hash: 'SHA256: 00000000... (PENDING)',
    node_cluster: 'Node-01: High-Throughput Batch Worker',
    status: 'PENDING_DEPOSIT',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9022',
    timestamp: '2026-10-02 01:45:10',
    buyer_agent: 'AutonomousBuyerAgent-Demo-Gateway',
    principal_entity: 'Demo Enterprise Inc',
    contractor_name: 'AutonomousBuyerAgent-Demo-Gateway',
    trade_vertical: 'Dedicated AI Service Gateway',
    service_plan: 'Dedicated AI Service Gateway ($79.99/mo)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-BW452NX993L2',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Enterprise Inc',
    allocated_did: 'mcp+https://gateway-01.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 98499e3f5739d987 (PASS)',
    node_cluster: 'Node-02: Dedicated AI Service Gateway',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9023',
    timestamp: '2026-10-01 23:18:44',
    buyer_agent: 'AutonomousBuyerAgent-Security-Cluster',
    principal_entity: 'Example Security Co',
    contractor_name: 'AutonomousBuyerAgent-Security-Cluster',
    trade_vertical: 'Enterprise Cluster Node',
    service_plan: 'Enterprise Cluster Node ($179.99/mo)',
    monthly_amount: 179.99,
    paypal_sub_id: 'I-SC994ZZ331A8',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Example Security Co',
    allocated_did: 'mcp+https://cluster-01.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 77a1bc92e01f558a (PASS)',
    node_cluster: 'Node-03: Enterprise Cluster Node',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9024',
    timestamp: '2026-10-01 21:02:15',
    buyer_agent: 'AutonomousBuyerAgent-Valence-Gateway',
    principal_entity: 'Example Intelligence LLC',
    contractor_name: 'AutonomousBuyerAgent-Valence-Gateway',
    trade_vertical: 'Dedicated AI Service Gateway',
    service_plan: 'Dedicated AI Service Gateway ($79.99/mo)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-VG551PP882B4',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Example Intelligence LLC',
    allocated_did: 'mcp+https://gateway-02.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 44f89d12a32190cc (PASS)',
    node_cluster: 'Node-04: Dedicated AI Service Gateway',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9025',
    timestamp: '2026-10-01 19:30:00',
    buyer_agent: 'AutonomousBuyerAgent-Labs-Batch',
    principal_entity: 'Example Labs',
    contractor_name: 'AutonomousBuyerAgent-Labs-Batch',
    trade_vertical: 'High-Throughput Batch Worker',
    service_plan: 'High-Throughput Batch Worker ($49.99/mo)',
    monthly_amount: 49.99,
    paypal_sub_id: 'I-CX119CC447T1',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Example Labs',
    allocated_did: 'mcp+https://batch-02.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 8812fa49d91244bb (PASS)',
    node_cluster: 'Node-05: High-Throughput Batch Worker',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9026',
    timestamp: '2026-10-01 16:11:58',
    buyer_agent: 'AutonomousBuyerAgent-Audit-Cluster',
    principal_entity: 'Demo Audit Labs',
    contractor_name: 'AutonomousBuyerAgent-Audit-Cluster',
    trade_vertical: 'Enterprise Cluster Node',
    service_plan: 'Enterprise Cluster Node ($179.99/mo)',
    monthly_amount: 179.99,
    paypal_sub_id: 'I-HY882GG990W3',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Audit Labs',
    allocated_did: 'mcp+https://cluster-02.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 22c199bf884112e1 (PASS)',
    node_cluster: 'Node-06: Enterprise Cluster Node',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9027',
    timestamp: '2026-10-01 14:05:32',
    buyer_agent: 'AutonomousBuyerAgent-Vector-Batch',
    principal_entity: 'Demo Vector Co',
    contractor_name: 'AutonomousBuyerAgent-Vector-Batch',
    trade_vertical: 'High-Throughput Batch Worker',
    service_plan: 'High-Throughput Batch Worker ($49.99/mo)',
    monthly_amount: 49.99,
    paypal_sub_id: 'I-VT771MM220K1',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Vector Co',
    allocated_did: 'mcp+https://batch-03.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 55d01249bba10033 (PASS)',
    node_cluster: 'Node-07: High-Throughput Batch Worker',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9028',
    timestamp: '2026-10-01 11:42:19',
    buyer_agent: 'AutonomousBuyerAgent-Compute-Gateway',
    principal_entity: 'Example Compute PBC',
    contractor_name: 'AutonomousBuyerAgent-Compute-Gateway',
    trade_vertical: 'Dedicated AI Service Gateway',
    service_plan: 'Dedicated AI Service Gateway ($79.99/mo)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-DF449EE881V9',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Example Compute PBC',
    allocated_did: 'mcp+https://gateway-03.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 44b99812cc009941 (PASS)',
    node_cluster: 'Node-08: Dedicated AI Service Gateway',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9029',
    timestamp: '2026-10-01 09:15:40',
    buyer_agent: 'AutonomousBuyerAgent-Cloud-Cluster',
    principal_entity: 'Demo Cloud Solutions',
    contractor_name: 'AutonomousBuyerAgent-Cloud-Cluster',
    trade_vertical: 'Enterprise Cluster Node',
    service_plan: 'Enterprise Cluster Node ($179.99/mo)',
    monthly_amount: 179.99,
    paypal_sub_id: 'I-MR662SS331B2',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Cloud Solutions',
    allocated_did: 'mcp+https://cluster-03.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 99e1284fa0024bb1 (PASS)',
    node_cluster: 'Node-09: Enterprise Cluster Node',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9030',
    timestamp: '2026-10-01 08:30:12',
    buyer_agent: 'AutonomousBuyerAgent-Agentic-Gateway',
    principal_entity: 'Demo Agentic Ltd',
    contractor_name: 'AutonomousBuyerAgent-Agentic-Gateway',
    trade_vertical: 'Dedicated AI Service Gateway',
    service_plan: 'Dedicated AI Service Gateway ($79.99/mo)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-CD551AA994M7',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Agentic Ltd',
    allocated_did: 'mcp+https://gateway-04.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 33f9901aa88231cd (PASS)',
    node_cluster: 'Node-10: Dedicated AI Service Gateway',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9031',
    timestamp: '2026-09-30 22:50:04',
    buyer_agent: 'AutonomousBuyerAgent-Omni-Batch',
    principal_entity: 'Demo Model Corp',
    contractor_name: 'AutonomousBuyerAgent-Omni-Batch',
    trade_vertical: 'High-Throughput Batch Worker',
    service_plan: 'High-Throughput Batch Worker ($49.99/mo)',
    monthly_amount: 49.99,
    paypal_sub_id: 'I-OM882JJ115X4',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Model Corp',
    allocated_did: 'mcp+https://batch-04.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 88cc441299dfa002 (PASS)',
    node_cluster: 'Node-11: High-Throughput Batch Worker',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9032',
    timestamp: '2026-09-30 20:18:27',
    buyer_agent: 'AutonomousBuyerAgent-Inference-Gateway',
    principal_entity: 'Example Inference Co',
    contractor_name: 'AutonomousBuyerAgent-Inference-Gateway',
    trade_vertical: 'Dedicated AI Service Gateway',
    service_plan: 'Dedicated AI Service Gateway ($79.99/mo)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-PR331DD772Z8',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Example Inference Co',
    allocated_did: 'mcp+https://gateway-05.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 11ff889200aa9922 (PASS)',
    node_cluster: 'Node-12: Dedicated AI Service Gateway',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9033',
    timestamp: '2026-09-30 18:04:55',
    buyer_agent: 'AutonomousBuyerAgent-Quant-Batch',
    principal_entity: 'Demo Scale Labs',
    contractor_name: 'AutonomousBuyerAgent-Quant-Batch',
    trade_vertical: 'High-Throughput Batch Worker',
    service_plan: 'High-Throughput Batch Worker ($49.99/mo)',
    monthly_amount: 49.99,
    paypal_sub_id: 'I-QS224RR661K3',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Scale Labs',
    allocated_did: 'mcp+https://batch-05.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 44ee0091aa331188 (PASS)',
    node_cluster: 'Node-13: High-Throughput Batch Worker',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
  {
    id: 'TXN-AP2-9034',
    timestamp: '2026-09-30 15:22:10',
    buyer_agent: 'AutonomousBuyerAgent-Reasoning-Gateway',
    principal_entity: 'Demo Reasoning Group',
    contractor_name: 'AutonomousBuyerAgent-Reasoning-Gateway',
    trade_vertical: 'Dedicated AI Service Gateway',
    service_plan: 'Dedicated AI Service Gateway ($79.99/mo)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-AR118CC559W2',
    kyc_status: 'VERIFIED (ES256 Mandate Bound)',
    kyc_legal_entity: 'Demo Reasoning Group',
    allocated_did: 'mcp+https://gateway-06.example.com/mcp',
    tcpa_guard: '100% ES256 SIGNED MANDATE',
    mandate_proof: 'Demo data (not verified)',
    anti_tamper_hash: 'SHA256: 77cc991200bb2244 (PASS)',
    node_cluster: 'Node-14: Dedicated AI Service Gateway',
    status: 'ACTIVE_STREAMING',
    data_source: 'Demo data',
  },
];

export interface TradeImpact {
  trade: string; // Service capability
  service_capability?: string;
  missed_calls_prevented: number; // Tamper attempts rejected
  leads_captured: number; // Workload tasks fulfilled
  annualized_gmv: number;
  monthly_settlement: number;
  active_agents: number; // Connected buyer agents
  active_buyer_agents?: number;
  mandates_cleared: number;
  recovered_revenue: number;
  subscription_cost: number;
  roi_multiple: number;
  sla_compliance?: string;
}

export function buildTradeImpactFromTransactions(transactions: A2aTransaction[]): TradeImpact[] {
  const activeRows = transactions.filter((t) => t.status === 'ACTIVE_STREAMING');
  const tierOrder = CATALOG_PLANS.map((plan) => ({
    trade: plan.name,
    planRate: plan.price,
    taskQuota: plan.tasks,
  }));

  const knownTiers = new Set(tierOrder.map((t) => t.trade));

  function getTierForTransaction(t: A2aTransaction): string {
    // 1. By trade_vertical when it names a known tier
    if (t.trade_vertical && knownTiers.has(t.trade_vertical)) {
      return t.trade_vertical;
    }
    // 2. Otherwise by price
    const amount = t.monthly_amount ?? 0;
    if (Math.abs(amount - CATALOG_PLANS[0].price) < 0.05) return CATALOG_PLANS[0].name;
    if (Math.abs(amount - CATALOG_PLANS[2].price) < 0.05) return CATALOG_PLANS[2].name;
    return CATALOG_PLANS[1].name;
  }

  return tierOrder.map((tier) => {
    const activeForTier = activeRows.filter((t) => getTierForTransaction(t) === tier.trade);
    const count = activeForTier.length;
    const monthlySettlement = activeForTier.reduce((sum, t) => sum + (t.monthly_amount ?? tier.planRate), 0);
    const roundedMonthly = Math.round(monthlySettlement * 100) / 100;
    const annualized = Math.round(roundedMonthly * 12 * 100) / 100;

    return {
      trade: tier.trade,
      service_capability: `${tier.trade} ($${tier.planRate}/mo)`,
      active_agents: count,
      active_buyer_agents: count,
      mandates_cleared: count,
      monthly_settlement: roundedMonthly,
      annualized_gmv: annualized,
      recovered_revenue: annualized,
      leads_captured: tier.taskQuota * count,
      missed_calls_prevented: 0,
      subscription_cost: tier.planRate,
      roi_multiple: 12.0,
    };
  });
}

export const tradeImpactData: TradeImpact[] = buildTradeImpactFromTransactions(initialA2aTransactions);


export interface KycAuditRecord {
  allocated_did: string;
  carrier_resporg: string;
  tcr_campaign_id: string;
  subscriber_legal_name: string;
  paypal_payer_id: string;
  autodialer_blocked: boolean;
  statutory_shield_status: string;
  agent_key_id?: string;
  ed25519_fingerprint?: string;
  nonce_state?: string;
}

// MOCK(M-018): hardcoded KYC audit records
export const kycAuditData: KycAuditRecord[] = [
  {
    allocated_did: 'node-cluster-01.ap2.net',
    carrier_resporg: 'AP2 Autonomous Worker Enclave',
    tcr_campaign_id: 'AP2-CLUSTER-ALPHA',
    subscriber_legal_name: 'Acme Compute Co',
    paypal_payer_id: 'PAYER-ACME-8912',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (Zero Budget Overrun / ES256 Bound)',
    agent_key_id: 'es256:key:0x9f8a221b',
    ed25519_fingerprint: 'SHA256:7c9e1248...b401',
    nonce_state: 'Replay Protected (Monotonic #1492)',
  },
  {
    allocated_did: 'node-cluster-02.ap2.net',
    carrier_resporg: 'AP2 Autonomous Worker Enclave',
    tcr_campaign_id: 'AP2-CLUSTER-BETA',
    subscriber_legal_name: 'Demo Enterprise Inc',
    paypal_payer_id: 'PAYER-APEX-3391',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (Zero Budget Overrun / ES256 Bound)',
    agent_key_id: 'es256:key:0x7b2c5510',
    ed25519_fingerprint: 'SHA256:8812fa49...10cc',
    nonce_state: 'Replay Protected (Monotonic #1493)',
  },
  {
    allocated_did: 'node-cluster-03.ap2.net',
    carrier_resporg: 'AP2 Autonomous Worker Enclave',
    tcr_campaign_id: 'AP2-CLUSTER-GAMMA',
    subscriber_legal_name: 'Example Security Co',
    paypal_payer_id: 'PAYER-SENTINEL-4410',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (Zero Budget Overrun / ES256 Bound)',
    agent_key_id: 'es256:key:0x3d4e8891',
    ed25519_fingerprint: 'SHA256:44f89d12...88bb',
    nonce_state: 'Replay Protected (Monotonic #1494)',
  },
  {
    allocated_did: 'node-cluster-04.ap2.net',
    carrier_resporg: 'AP2 Autonomous Worker Enclave',
    tcr_campaign_id: 'AP2-CLUSTER-DELTA',
    subscriber_legal_name: 'Example Stream Co',
    paypal_payer_id: 'PAYER-STREAM-7723',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (Zero Budget Overrun / ES256 Bound)',
    agent_key_id: 'es256:key:0x8a1b9924',
    ed25519_fingerprint: 'SHA256:22c199bf...33aa',
    nonce_state: 'Replay Protected (Monotonic #1495)',
  },
];

export interface NodeClusterRecord {
  allocated_did: string;
  lata: string;
  market_region: string;
  tcr_brand: string;
  tcr_campaign_id: string;
  monthly_quota_minutes: number;
  stir_shaken_level: string;
  inbound_routing_mode: string;
  node_cluster?: string;
  concurrency_capacity?: string;
}

// MOCK(M-018): hardcoded node-cluster data
export const nodeClusterData: NodeClusterRecord[] = [
  {
    allocated_did: 'node-cluster-01.ap2.net',
    lata: 'Node-01: High-Speed LLM Inference Gateway',
    market_region: 'US-East Multi-Region Cluster',
    tcr_brand: 'AP2 Protocol Node',
    tcr_campaign_id: 'AP2-CLUSTER-ALPHA',
    monthly_quota_minutes: 5000,
    stir_shaken_level: 'Attestation Tier A (Cryptographic Mandate)',
    inbound_routing_mode: 'MCP Stream (Gemini 3.8 / Sub-350ms)',
    node_cluster: 'Node-01: High-Speed Inference Cluster',
    concurrency_capacity: '1,500 requests/sec',
  },
  {
    allocated_did: 'node-cluster-02.ap2.net',
    lata: 'Node-02: Batch Data & Document RAG Pipeline',
    market_region: 'US-East High-Memory Cluster',
    tcr_brand: 'AP2 Protocol Node',
    tcr_campaign_id: 'AP2-CLUSTER-BETA',
    monthly_quota_minutes: 5000,
    stir_shaken_level: 'Attestation Tier A (Cryptographic Mandate)',
    inbound_routing_mode: 'High-Throughput Vector Embedding (1M chunks/batch)',
    node_cluster: 'Node-02: Batch Data & RAG Pipeline',
    concurrency_capacity: '800 batches/sec',
  },
  {
    allocated_did: 'node-cluster-03.ap2.net',
    lata: 'Node-03: Autonomous Code & Security Audit Cluster',
    market_region: 'US-Central Sandbox Node',
    tcr_brand: 'AP2 Protocol Node',
    tcr_campaign_id: 'AP2-CLUSTER-GAMMA',
    monthly_quota_minutes: 5000,
    stir_shaken_level: 'Attestation Tier A (Cryptographic Mandate)',
    inbound_routing_mode: 'Sandbox Code Execution & Smart Contract Verifier',
    node_cluster: 'Node-03: Security & Code Audit Cluster',
    concurrency_capacity: '500 audits/sec',
  },
  {
    allocated_did: 'node-cluster-04.ap2.net',
    lata: 'Node-04: Real-Time Stream Processing Node',
    market_region: 'US-East Edge Streaming Pops',
    tcr_brand: 'AP2 Protocol Node',
    tcr_campaign_id: 'AP2-CLUSTER-DELTA',
    monthly_quota_minutes: 5000,
    stir_shaken_level: 'Attestation Tier A (Cryptographic Mandate)',
    inbound_routing_mode: 'Full-Duplex Real-Time Stream Bridge',
    node_cluster: 'Node-04: Real-Time Stream Processing Node',
    concurrency_capacity: '1,200 concurrent streams',
  },
  {
    allocated_did: 'node-cluster-05.ap2.net',
    lata: 'Node-05: Human-in-the-Loop Expert QA Desk',
    market_region: 'Global Distributed Operator Fleet',
    tcr_brand: 'AP2 Protocol Node',
    tcr_campaign_id: 'AP2-CLUSTER-EPSILON',
    monthly_quota_minutes: 5000,
    stir_shaken_level: 'Attestation Tier A (Cryptographic Mandate)',
    inbound_routing_mode: 'Supervised Verification Desk & Outlier Triage',
    node_cluster: 'Node-05: Human-in-the-Loop Expert QA Desk',
    concurrency_capacity: '50 concurrent human reviews',
  },
];

export const a2aDataSources: AgDataSourcesDefinition = {
  sources: [
    {
      id: 'transactions',
      data: initialA2aTransactions,
      fields: [
        { id: 'id', name: 'Transaction ID', format: 'textFormat' },
        { id: 'timestamp', name: 'Timestamp', format: 'textFormat' },
        { id: 'buyer_agent', name: 'Buyer Agent ID', format: 'textFormat' },
        { id: 'principal_entity', name: 'Principal Entity', format: 'textFormat' },
        { id: 'contractor_name', name: 'Principal Entity', format: 'textFormat' },
        { id: 'trade_vertical', name: 'Service Capability', format: 'textFormat' },
        { id: 'service_plan', name: 'Service Plan Tier', format: 'textFormat' },
        { id: 'monthly_amount', name: 'Monthly Fee', format: 'currencyFormat' },
        { id: 'paypal_sub_id', name: 'PayPal Sub ID', format: 'textFormat' },
        { id: 'kyc_status', name: 'Identity & Signature Status', format: 'textFormat' },
        { id: 'allocated_did', name: 'Execution Cluster Node', format: 'textFormat' },
        { id: 'tcpa_guard', name: 'Anti-Tamper & Spending Guard', format: 'textFormat' },
        { id: 'status', name: 'Subscription State', format: 'textFormat' },
      ],
    },
    {
      id: 'trade_impact',
      data: tradeImpactData,
      fields: [
        { id: 'trade', name: 'Service Capability', format: 'textFormat' },
        { id: 'active_agents', name: 'Connected Buyer Agents', format: 'integerFormat' },
        { id: 'mandates_cleared', name: 'Mandates Settled', format: 'integerFormat' },
        { id: 'monthly_settlement', name: 'Monthly M2M Volume ($/mo)', format: 'currencyFormat' },
        { id: 'annualized_gmv', name: 'Autonomous AP2 GMV ($ ARR)', format: 'currencyFormat' },
        { id: 'recovered_revenue', name: 'Autonomous AP2 GMV ($ ARR)', format: 'currencyFormat' },
        { id: 'leads_captured', name: 'Workload Tasks Fulfilled', format: 'integerFormat' },
        { id: 'missed_calls_prevented', name: 'Tamper Attempts Rejected', format: 'integerFormat' },
        { id: 'subscription_cost', name: 'PayPal Plan Cost ($/mo)', format: 'currencyFormat' },
        { id: 'roi_multiple', name: 'AP2 Settlement Multiplier (x)', format: 'decimalFormat' },
      ],
    },
    {
      id: 'kyc_audit',
      data: kycAuditData,
      fields: [
        { id: 'allocated_did', name: 'Node Endpoint', format: 'textFormat' },
        { id: 'carrier_resporg', name: 'Worker Enclave', format: 'textFormat' },
        { id: 'tcr_campaign_id', name: 'Cluster ID', format: 'textFormat' },
        { id: 'subscriber_legal_name', name: 'Principal Entity', format: 'textFormat' },
        { id: 'paypal_payer_id', name: 'PayPal Payer ID', format: 'textFormat' },
        { id: 'autodialer_blocked', name: 'Replay Protection Active', format: 'booleanFormat' },
        { id: 'statutory_shield_status', name: 'Anti-Tamper Verification', format: 'textFormat' },
      ],
    },
    {
      id: 'node_clusters',
      data: nodeClusterData,
      fields: [
        { id: 'allocated_did', name: 'Node Endpoint', format: 'textFormat' },
        { id: 'lata', name: 'Worker Cluster Name', format: 'textFormat' },
        { id: 'market_region', name: 'Deployment Region', format: 'textFormat' },
        { id: 'tcr_brand', name: 'Protocol Brand', format: 'textFormat' },
        { id: 'tcr_campaign_id', name: 'Cluster ID', format: 'textFormat' },
        { id: 'monthly_quota_minutes', name: 'Monthly Quota (Hours)', format: 'integerFormat' },
        { id: 'stir_shaken_level', name: 'Enclave Security Level', format: 'textFormat' },
        { id: 'inbound_routing_mode', name: 'Execution Interface', format: 'textFormat' },
      ],
    },
  ],
};

export const initialDashboardState: AgReportState = {
  selectedPageId: 'fleet-telemetry',
  panels: {
    filters: { collapsed: true },
  },
  pages: [
    {
      id: 'fleet-telemetry',
      widgets: {
        'kpi-mrr': {
          type: 'value',
          dataMapping: {
            value: [{ id: 'trade_impact.monthly_settlement', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Active Protocol MRR' },
          },
        },
        'kpi-leads': {
          type: 'value',
          dataMapping: {
            value: [{ id: 'trade_impact.mandates_cleared', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Mandates Settled' },
          },
        },
        'kpi-revenue': {
          type: 'value',
          dataMapping: {
            value: [{ id: 'trade_impact.annualized_gmv', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Autonomous AP2 GMV' },
          },
        },
        'kpi-tcpa': {
          type: 'value',
          dataMapping: {
            value: [{ id: 'trade_impact.active_agents', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Connected Buyer Agents' },
          },
        },
        'chart-recovered-revenue': {
          type: 'bar-chart-grouped',
          dataMapping: {
            categoryKey: [{ id: 'trade_impact.trade' }],
            valueKey: [{ id: 'trade_impact.annualized_gmv', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Autonomous AP2 Commerce Volume by Capability ($ ARR)' },
            subtitle: { enabled: true, text: 'Contract Run-Rate Settled via PayPal Subscriptions Rails' },
          },
        },
        'chart-lead-distribution': {
          type: 'donut-chart',
          dataMapping: {
            categoryKey: [{ id: 'trade_impact.trade' }],
            valueKey: [{ id: 'trade_impact.annualized_gmv', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'AP2 Settlement Share by Capability' },
            subtitle: { enabled: true, text: 'Autonomous Run-Rate GMV Breakdown' },
            style: {
              theme: {
                common: {
                  legend: {
                    enabled: true,
                    position: 'right',
                  },
                },
              },
            },
          },
        },
        'grid-a2a-ledger': {
          type: 'grid',
          dataMapping: {
            cols: [
              { id: 'transactions.id' },
              { id: 'transactions.timestamp' },
              { id: 'transactions.buyer_agent' },
              { id: 'transactions.principal_entity' },
              { id: 'transactions.trade_vertical' },
              { id: 'transactions.service_plan' },
              { id: 'transactions.monthly_amount' },
              { id: 'transactions.paypal_sub_id' },
              { id: 'transactions.kyc_status' },
              { id: 'transactions.allocated_did' },
              { id: 'transactions.status' },
            ],
          },
          format: {
            title: { enabled: true, text: 'Autonomous AP2 Protocol Settlement Ledger' },
            subtitle: { enabled: true, text: 'Machine-to-Machine Subscription & Enclave Attestation Ledger' },
          },
        },
      },
      widgetLayout: {
        'kpi-mrr': { xTrack: 0, yTrack: 0, xSpan: 6, ySpan: 7 },
        'kpi-leads': { xTrack: 6, yTrack: 0, xSpan: 6, ySpan: 7 },
        'kpi-revenue': { xTrack: 12, yTrack: 0, xSpan: 6, ySpan: 7 },
        'kpi-tcpa': { xTrack: 18, yTrack: 0, xSpan: 6, ySpan: 7 },
        'chart-recovered-revenue': { xTrack: 0, yTrack: 7, xSpan: 14, ySpan: 14 },
        'chart-lead-distribution': { xTrack: 14, yTrack: 7, xSpan: 10, ySpan: 14 },
        'grid-a2a-ledger': { xTrack: 0, yTrack: 21, xSpan: 24, ySpan: 16 },
      },
    },
    {
      id: 'mandate-kyc-guard',
      widgets: {
        'grid-kyc-audit': {
          type: 'grid',
          dataMapping: {
            cols: [
              { id: 'kyc_audit.allocated_did' },
              { id: 'kyc_audit.carrier_resporg' },
              { id: 'kyc_audit.subscriber_legal_name' },
              { id: 'kyc_audit.paypal_payer_id' },
              { id: 'kyc_audit.autodialer_blocked' },
              { id: 'kyc_audit.statutory_shield_status' },
            ],
          },
          format: {
            title: { enabled: true, text: 'ES256 Mandate & Anti-Tamper Audit Registry' },
            subtitle: { enabled: true, text: 'AP2 Cryptographic Mandate & Monotonic Nonce Attestation' },
          },
        },
      },
      widgetLayout: {
        'grid-kyc-audit': { xTrack: 0, yTrack: 0, xSpan: 24, ySpan: 18 },
      },
    },
    {
      id: 'node-clusters-registry',
      widgets: {
        'grid-node-clusters': {
          type: 'grid',
          dataMapping: {
            cols: [
              { id: 'node_clusters.allocated_did' },
              { id: 'node_clusters.lata' },
              { id: 'node_clusters.market_region' },
              { id: 'node_clusters.tcr_brand' },
              { id: 'node_clusters.tcr_campaign_id' },
              { id: 'node_clusters.monthly_quota_minutes' },
              { id: 'node_clusters.stir_shaken_level' },
              { id: 'node_clusters.inbound_routing_mode' },
            ],
          },
          format: {
            title: { enabled: true, text: 'Autonomous Worker Node Clusters & Routing Registry' },
            subtitle: { enabled: true, text: 'Enclave Node Capacity & MCP Execution Attestation' },
          },
        },
      },
      widgetLayout: {
        'grid-node-clusters': { xTrack: 0, yTrack: 0, xSpan: 24, ySpan: 18 },
      },
    },
  ],
};
