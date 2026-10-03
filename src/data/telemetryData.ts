import type { AgDataSourcesDefinition, AgReportState } from 'ag-studio';

export interface A2aTransaction {
  id: string;
  timestamp: string;
  buyer_agent: string;
  contractor_name: string;
  trade_vertical: string;
  service_plan: string;
  monthly_amount: number;
  paypal_sub_id: string;
  kyc_status: string;
  kyc_legal_entity: string;
  allocated_did: string;
  tcpa_guard: string;
  status: string;
}

export const initialA2aTransactions: A2aTransaction[] = [
  {
    id: 'TXN-9021',
    timestamp: '2026-10-02 02:14:22',
    buyer_agent: 'AutonomousBuyerAgent-Marcus-Tile',
    contractor_name: 'Marcus Miller',
    trade_vertical: 'Tile & Flooring',
    service_plan: 'AI Screener Pro (1 Dedicated Line)',
    monthly_amount: 79.99,
    paypal_sub_id: 'AWAITING_PAYPAL_TOKEN',
    kyc_status: 'PENDING_KYC_VERIFICATION',
    kyc_legal_entity: 'Miller Custom Flooring LLC',
    allocated_did: 'AWAITING_DEPOSIT',
    tcpa_guard: 'PENDING ACTIVATION',
    status: 'PENDING_DEPOSIT',
  },
  {
    id: 'TXN-9022',
    timestamp: '2026-10-02 01:45:10',
    buyer_agent: 'AutonomousBuyerAgent-Dave-Plumbing',
    contractor_name: 'Dave Vance',
    trade_vertical: 'Emergency Plumbing',
    service_plan: 'AI Screener Dispatch (GPS + Deposit)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-PL782MK110Q9',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Vance Rapid Drain & Plumbing Inc',
    allocated_did: '+1 (863) 356-7801',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9023',
    timestamp: '2026-10-01 23:18:44',
    buyer_agent: 'AutonomousBuyerAgent-Elena-Roofing',
    contractor_name: 'Elena Rostova',
    trade_vertical: 'Roofing & Storm',
    service_plan: 'AI Screener Commercial (Photo Scope)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-RF994ZZ331A8',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Apex Storm & Roofing Specialists',
    allocated_did: '+1 (863) 356-7802',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9024',
    timestamp: '2026-10-01 21:02:15',
    buyer_agent: 'AutonomousBuyerAgent-Hank-Towing',
    contractor_name: 'Hank Schrader',
    trade_vertical: 'Towing & Roadside',
    service_plan: 'AI Screener Dispatch (24/7 Roadside)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-TW551PP882B4',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Schrader Heavy Duty Towing LLC',
    allocated_did: '+1 (863) 356-7803',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9025',
    timestamp: '2026-10-01 19:30:00',
    buyer_agent: 'AutonomousBuyerAgent-Sam-HVAC',
    contractor_name: 'Samira Khan',
    trade_vertical: 'HVAC & Mechanical',
    service_plan: 'AI Screener Pro (Seasonal Dispatch)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-HV119CC447T1',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Khan Climate & Cooling Co',
    allocated_did: '+1 (863) 356-7804',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9026',
    timestamp: '2026-10-01 16:11:58',
    buyer_agent: 'AutonomousBuyerAgent-Pamela-Accounting',
    contractor_name: 'Pamela Green',
    trade_vertical: 'Contractor Tax & Bookkeeping',
    service_plan: 'AI Screener Receptionist (Sole Prop)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-TX882GG990W3',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Express 1040 Inc',
    allocated_did: '+1 (863) 356-7805',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9027',
    timestamp: '2026-10-01 14:05:32',
    buyer_agent: 'AutonomousBuyerAgent-Carlos-Roofing',
    contractor_name: 'Carlos Mendez',
    trade_vertical: 'Roofing & Storm',
    service_plan: 'AI Screener Commercial (Storm Triage)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-RF771MM220K1',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Mendez Hurricane Roofing Corp',
    allocated_did: '+1 (863) 356-7806',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9028',
    timestamp: '2026-10-01 11:42:19',
    buyer_agent: 'AutonomousBuyerAgent-Wyatt-Towing',
    contractor_name: 'Wyatt Earp',
    trade_vertical: 'Towing & Roadside',
    service_plan: 'AI Screener Dispatch (24/7 Heavy Duty)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-TW449EE881V9',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Tombstone 24/7 Heavy Wrecker LLC',
    allocated_did: '+1 (863) 356-7807',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9029',
    timestamp: '2026-10-01 09:15:40',
    buyer_agent: 'AutonomousBuyerAgent-Brett-Tile',
    contractor_name: 'Brett Sterling',
    trade_vertical: 'Tile & Flooring',
    service_plan: 'AI Screener Pro (Commercial Stone)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-FL662SS331B2',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Sterling Master Tile & Stone LLC',
    allocated_did: '+1 (863) 356-7808',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9030',
    timestamp: '2026-10-01 08:30:12',
    buyer_agent: 'AutonomousBuyerAgent-Tariq-Plumbing',
    contractor_name: 'Tariq Al-Mansoor',
    trade_vertical: 'Emergency Plumbing',
    service_plan: 'AI Screener Dispatch (Hydro-Jetting)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-PL551AA994M7',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Lakeland Hydro-Jetting & Drain Services',
    allocated_did: '+1 (863) 356-7809',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9031',
    timestamp: '2026-09-30 22:50:04',
    buyer_agent: 'AutonomousBuyerAgent-Sarah-HVAC',
    contractor_name: 'Sarah Jenkins',
    trade_vertical: 'HVAC & Mechanical',
    service_plan: 'AI Screener Pro (24/7 Compressor Failover)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-HV882JJ115X4',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Citrus State HVAC Pros LLC',
    allocated_did: '+1 (863) 356-7810',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9032',
    timestamp: '2026-09-30 20:18:27',
    buyer_agent: 'AutonomousBuyerAgent-Declan-Roofing',
    contractor_name: 'Declan Brooks',
    trade_vertical: 'Roofing & Storm',
    service_plan: 'AI Screener Commercial (Industrial Metal)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-RF331DD772Z8',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Brooks Commercial Metal Roofing Inc',
    allocated_did: '+1 (863) 356-7811',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9033',
    timestamp: '2026-09-30 18:04:55',
    buyer_agent: 'AutonomousBuyerAgent-Mateo-Plumbing',
    contractor_name: 'Mateo Rossi',
    trade_vertical: 'Emergency Plumbing',
    service_plan: 'AI Screener Dispatch (Slab Leak Camera)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-PL224RR661K3',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Suncoast Pipe & Slab Leak Detection',
    allocated_did: '+1 (863) 356-7812',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  },
  {
    id: 'TXN-9034',
    timestamp: '2026-09-30 15:22:10',
    buyer_agent: 'AutonomousBuyerAgent-Brandon-Roofing',
    contractor_name: 'Brandon Cole',
    trade_vertical: 'Roofing & Storm',
    service_plan: 'AI Screener Commercial (Insurance Restoration)',
    monthly_amount: 79.99,
    paypal_sub_id: 'I-RF118CC559W2',
    kyc_status: 'VERIFIED (PayPal Identity Bound)',
    kyc_legal_entity: 'Ridgeview Roofing & Restoration Inc',
    allocated_did: '+1 (863) 356-7813',
    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
    status: 'ACTIVE_STREAMING',
  }
];

export interface TradeImpact {
  trade: string;
  missed_calls_prevented: number;
  leads_captured: number;
  annualized_gmv: number;
  monthly_settlement: number;
  active_agents: number;
  mandates_cleared: number;
  recovered_revenue: number;
  subscription_cost: number;
  roi_multiple: number;
}

export const tradeImpactData: TradeImpact[] = [
  {
    trade: 'Roofing & Storm',
    missed_calls_prevented: 12,
    leads_captured: 9,
    annualized_gmv: 3839.52,
    monthly_settlement: 319.96,
    active_agents: 4,
    mandates_cleared: 48,
    recovered_revenue: 3839.52,
    subscription_cost: 79.99,
    roi_multiple: 4.8,
  },
  {
    trade: 'Emergency Plumbing',
    missed_calls_prevented: 24,
    leads_captured: 21,
    annualized_gmv: 2879.64,
    monthly_settlement: 239.97,
    active_agents: 3,
    mandates_cleared: 36,
    recovered_revenue: 2879.64,
    subscription_cost: 79.99,
    roi_multiple: 3.6,
  },
  {
    trade: 'Towing & Roadside',
    missed_calls_prevented: 31,
    leads_captured: 29,
    annualized_gmv: 1919.76,
    monthly_settlement: 159.98,
    active_agents: 2,
    mandates_cleared: 24,
    recovered_revenue: 1919.76,
    subscription_cost: 79.99,
    roi_multiple: 2.4,
  },
  {
    trade: 'HVAC & Mechanical',
    missed_calls_prevented: 16,
    leads_captured: 13,
    annualized_gmv: 1919.76,
    monthly_settlement: 159.98,
    active_agents: 2,
    mandates_cleared: 24,
    recovered_revenue: 1919.76,
    subscription_cost: 79.99,
    roi_multiple: 2.4,
  },
  {
    trade: 'Tile & Flooring',
    missed_calls_prevented: 18,
    leads_captured: 14,
    annualized_gmv: 1919.76,
    monthly_settlement: 159.98,
    active_agents: 2,
    mandates_cleared: 24,
    recovered_revenue: 1919.76,
    subscription_cost: 79.99,
    roi_multiple: 2.4,
  },
  {
    trade: 'Contractor Tax & Bookkeeping',
    missed_calls_prevented: 8,
    leads_captured: 6,
    annualized_gmv: 959.88,
    monthly_settlement: 79.99,
    active_agents: 1,
    mandates_cleared: 12,
    recovered_revenue: 959.88,
    subscription_cost: 79.99,
    roi_multiple: 1.2,
  },
];

export interface KycAuditRecord {
  allocated_did: string;
  carrier_resporg: string;
  tcr_campaign_id: string;
  subscriber_legal_name: string;
  paypal_payer_id: string;
  autodialer_blocked: boolean;
  statutory_shield_status: string;
}

export const kycAuditData: KycAuditRecord[] = [
  {
    allocated_did: '+1 (863) 267-8902',
    carrier_resporg: 'Telnyx (Wholesale RespOrg)',
    tcr_campaign_id: '4b3001a0-c5af-db76-3128-a88a3d668ff6',
    subscriber_legal_name: 'Marcus Miller (Miller Custom Flooring LLC)',
    paypal_payer_id: 'PAYER-MM8912',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (ZERO TCPA EXPOSURE)',
  },
  {
    allocated_did: '+1 (863) 356-7801',
    carrier_resporg: 'Telnyx (Wholesale RespOrg)',
    tcr_campaign_id: '4b3001a0-c5af-db76-3128-a88a3d668ff6',
    subscriber_legal_name: 'Dave Vance (Vance Rapid Drain & Plumbing Inc)',
    paypal_payer_id: 'PAYER-DV3391',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (ZERO TCPA EXPOSURE)',
  },
  {
    allocated_did: '+1 (863) 356-7802',
    carrier_resporg: 'Telnyx (Wholesale RespOrg)',
    tcr_campaign_id: '4b3001a0-c5af-db76-3128-a88a3d668ff6',
    subscriber_legal_name: 'Elena Rostova (Apex Storm & Roofing Specialists)',
    paypal_payer_id: 'PAYER-ER4410',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (ZERO TCPA EXPOSURE)',
  },
  {
    allocated_did: '+1 (863) 356-7803',
    carrier_resporg: 'Telnyx (Wholesale RespOrg)',
    tcr_campaign_id: '4b3001a0-c5af-db76-3128-a88a3d668ff6',
    subscriber_legal_name: 'Hank Schrader (Schrader Heavy Duty Towing LLC)',
    paypal_payer_id: 'PAYER-HS7723',
    autodialer_blocked: true,
    statutory_shield_status: '100% PASS (ZERO TCPA EXPOSURE)',
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
        { id: 'contractor_name', name: 'Contractor', format: 'textFormat' },
        { id: 'trade_vertical', name: 'Trade Vertical', format: 'textFormat' },
        { id: 'service_plan', name: 'Service Plan', format: 'textFormat' },
        { id: 'monthly_amount', name: 'Monthly Fee', format: 'currencyFormat' },
        { id: 'paypal_sub_id', name: 'PayPal Sub ID', format: 'textFormat' },
        { id: 'kyc_status', name: 'KYC Status', format: 'textFormat' },
        { id: 'kyc_legal_entity', name: 'Verified Legal Entity', format: 'textFormat' },
        { id: 'allocated_did', name: 'Allocated DID', format: 'textFormat' },
        { id: 'tcpa_guard', name: 'TCPA Compliance Guard', format: 'textFormat' },
        { id: 'status', name: 'Subscription State', format: 'textFormat' },
      ],
    },
    {
      id: 'trade_impact',
      data: tradeImpactData,
      fields: [
        { id: 'trade', name: 'Trade Vertical', format: 'textFormat' },
        { id: 'active_agents', name: 'Autonomous Buyer Agents', format: 'integerFormat' },
        { id: 'mandates_cleared', name: 'Mandates Settled', format: 'integerFormat' },
        { id: 'monthly_settlement', name: 'Monthly M2M Volume ($/mo)', format: 'currencyFormat' },
        { id: 'annualized_gmv', name: 'Autonomous A2A GMV ($ ARR)', format: 'currencyFormat' },
        { id: 'recovered_revenue', name: 'Autonomous A2A GMV ($ ARR)', format: 'currencyFormat' },
        { id: 'leads_captured', name: 'Booked Leads Intake', format: 'integerFormat' },
        { id: 'missed_calls_prevented', name: 'Robocalls Filtered', format: 'integerFormat' },
        { id: 'subscription_cost', name: 'PayPal Cost ($79.99/mo)', format: 'currencyFormat' },
        { id: 'roi_multiple', name: 'A2A Settlement Multiplier (x)', format: 'decimalFormat' },
      ],
    },
    {
      id: 'kyc_audit',
      data: kycAuditData,
      fields: [
        { id: 'allocated_did', name: 'Assigned DID Phone', format: 'textFormat' },
        { id: 'carrier_resporg', name: 'Carrier RespOrg', format: 'textFormat' },
        { id: 'tcr_campaign_id', name: '10DLC TCR Campaign', format: 'textFormat' },
        { id: 'subscriber_legal_name', name: 'KYC Verified Subscriber', format: 'textFormat' },
        { id: 'paypal_payer_id', name: 'PayPal Verified Payer ID', format: 'textFormat' },
        { id: 'autodialer_blocked', name: 'Autodialer Lock (FCC/TCPA)', format: 'booleanFormat' },
        { id: 'statutory_shield_status', name: 'Statutory Shield Status', format: 'textFormat' },
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
            value: [{ id: 'transactions.monthly_amount', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Active Fleet MRR' },
            subtitle: { enabled: true, text: '14 Stream Lines' },
          },
        },
        'kpi-leads': {
          type: 'value',
          dataMapping: {
            value: [{ id: 'trade_impact.mandates_cleared', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Mandates Settled' },
            subtitle: { enabled: true, text: '168 Autonomous Cycles' },
          },
        },
        'kpi-revenue': {
          type: 'value',
          dataMapping: {
            value: [{ id: 'trade_impact.annualized_gmv', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Autonomous A2A GMV' },
            subtitle: { enabled: true, text: '100% M2M Settled ($13.4k ARR)' },
          },
        },
        'kpi-tcpa': {
          type: 'value',
          dataMapping: {
            value: [{ id: 'trade_impact.active_agents', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Autonomous Buyer Agents' },
            subtitle: { enabled: true, text: '100% Policy Guarded' },
          },
        },
        'chart-recovered-revenue': {
          type: 'bar-chart-grouped',
          dataMapping: {
            categoryKey: [{ id: 'trade_impact.trade' }],
            valueKey: [{ id: 'trade_impact.annualized_gmv', aggregation: 'sum' }],
          },
          format: {
            title: { enabled: true, text: 'Autonomous A2A Commerce Volume by Trade ($ ARR)' },
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
            title: { enabled: true, text: 'A2A Settlement Share by Trade' },
            subtitle: { enabled: true, text: 'Autonomous GMV Breakdown' },
          },
        },
        'grid-a2a-ledger': {
          type: 'grid',
          dataMapping: {
            cols: [
              { id: 'transactions.id' },
              { id: 'transactions.timestamp' },
              { id: 'transactions.contractor_name' },
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
            title: { enabled: true, text: 'Autonomous A2A Commerce Audit Ledger' },
            subtitle: { enabled: true, text: 'Machine-to-Machine Subscription & Carrier Attestation Ledger' },
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
      id: 'telecom-kyc-guard',
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
            title: { enabled: true, text: 'Carrier 10DLC & KYC Compliance Registry' },
            subtitle: { enabled: true, text: 'Telnyx Wholesale RespOrg & TCR Campaign Attestation' },
          },
        },
      },
      widgetLayout: {
        'grid-kyc-audit': { xTrack: 0, yTrack: 0, xSpan: 24, ySpan: 18 },
      },
    },
  ],
};
