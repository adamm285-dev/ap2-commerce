import { useState, useMemo, useCallback, useEffect } from 'react';
import { AgStudioLicenseManager } from 'ag-studio';
import type { AgDataSourcesDefinition, AgStudioMode } from 'ag-studio';
import { PayPalScriptProvider, PayPalButtons } from '@paypal/react-paypal-js';
import {
  ShieldCheck,
  Sliders,
  X,
  Lock,
  LayoutGrid,
  Calendar,
  Network,
  Cpu,
  Layers,
  ChevronDown,
  ChevronUp,
  Clock,
  Server,
  Sparkles,
  Play,
} from 'lucide-react';
import {
  initialA2aTransactions,
  kycAuditData,
  nodeClusterData,
  buildTradeImpactFromTransactions,
  type A2aTransaction,
} from './data/telemetryData';
import {
  evaluateAgentNegotiation,
  resetMandateLedger,
  executeProvisioningAfterSubscription,
  fetchFleetLedger,
  PAYPAL_CONFIG,
  type AgentNegotiationRequest,
  type AgentNegotiationResponse,
  type ProvisioningResult,
} from './services/paypalAgentService';
import { BryntumDispatchScheduler } from './components/BryntumDispatchScheduler';
import { ZapierMcpView } from './components/ZapierMcpView';
import { SellerCopilotView } from './components/SellerCopilotView';
import { EnterpriseFleetLedger } from './components/EnterpriseFleetLedger';
import { type NodeSettingsData } from './components/NodeSettingsView';
import './App.css';

// 1. Initialize AG Studio License if supplied via environment
const studioLicenseKey = import.meta.env.VITE_AG_STUDIO_LICENSE_KEY;
if (studioLicenseKey) {
  AgStudioLicenseManager.setLicenseKey(studioLicenseKey);
  console.log('[AG Studio]: License key registered.');
} else {
  console.log('[AG Studio]: Running in local developer trial mode.');
}

import ap2LogoUrl from './assets/ap2_logo.jpg';

// Bespoke AP2 Protocol Brand Logo Component (Circuit Medallion)
function Ap2Logo({ size = 38 }: { size?: number }) {
  return (
    <img
      src={ap2LogoUrl}
      alt="AP2 Autonomous Agent Protocol"
      style={{
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: '8px',
        objectFit: 'cover',
        display: 'block',
        boxShadow: '0 0 12px rgba(56, 189, 248, 0.45)',
      }}
    />
  );
}

export function App() {
  const [activeTab, setActiveTab] = useState<'copilot' | 'fleet-ledger' | 'bryntum' | 'ag-studio' | 'zapier' | 'settings'>('copilot');
  const [ledgerViewMode, setLedgerViewMode] = useState<'grid' | 'studio'>('grid');
  const [mode, setMode] = useState<AgStudioMode>('view');

  const handleNavigateTab = (tab: 'copilot' | 'fleet-ledger' | 'ag-studio' | 'bryntum' | 'zapier' | 'settings') => {
    if (tab === 'ag-studio') {
      setActiveTab('fleet-ledger');
      setLedgerViewMode('studio');
    } else if (tab === 'fleet-ledger') {
      setActiveTab('fleet-ledger');
      setLedgerViewMode('grid');
    } else if (tab === 'settings') {
      setActiveTab('copilot');
    } else {
      setActiveTab(tab);
    }
  };
  const [transactions, setTransactions] = useState<A2aTransaction[]>(initialA2aTransactions);
  const [activeSetupStep, setActiveSetupStep] = useState<number>(1);
  const [isSetupGuideCollapsed, setIsSetupGuideCollapsed] = useState<boolean>(true);
  const [isDashboardMetricsCollapsed, setIsDashboardMetricsCollapsed] = useState<boolean>(true);
  const [schedulerViewMode, setSchedulerViewMode] = useState<'timeline' | 'matrix'>('timeline');
  const [isScheduleMetricsCollapsed, setIsScheduleMetricsCollapsed] = useState<boolean>(false);
  const [mcpScenario, setMcpScenario] = useState<'a2a' | 'workload'>('a2a');
  const [isMcpControlsCollapsed, setIsMcpControlsCollapsed] = useState<boolean>(false);
  const [lastFetchTime, setLastFetchTime] = useState<string>(() => new Date().toISOString().slice(11, 19) + ' UTC');

  const activeTransactions = useMemo(() => {
    return transactions.filter((t) => t.status === 'ACTIVE_STREAMING');
  }, [transactions]);
  const pendingTransactions = useMemo(() => {
    return transactions.filter((t) => t.status !== 'ACTIVE_STREAMING');
  }, [transactions]);

  const totalMrr = useMemo(() => {
    const raw = activeTransactions.reduce((sum, t) => sum + (t.monthly_amount || 0), 0);
    return Math.round(raw * 100) / 100;
  }, [activeTransactions]);
  const activeLinesCount = activeTransactions.length;
  const pendingLinesCount = pendingTransactions.length;
  const totalAutonomousGmv = Math.round(totalMrr * 12 * 100) / 100;

  const [isPendingDepositLocked, setIsPendingDepositLocked] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isNegotiating, setIsNegotiating] = useState(false);
  const [negotiationResult, setNegotiationResult] = useState<AgentNegotiationResponse | null>(null);
  const [provisioningResult, setProvisioningResult] = useState<ProvisioningResult | null>(null);
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [paypalError, setPaypalError] = useState<string | null>(null);

  // Form state for AP2 Buyer Agent simulation
  const [contractorName, setContractorName] = useState('agent:acme-procure');
  const [businessEntity, setBusinessEntity] = useState('Acme Autonomous Systems LLC');
  const [tradeVertical, setTradeVertical] = useState('Dedicated AI Service Gateway');
  const [maxMonthlyBudget, setMaxMonthlyBudget] = useState(100.0);
  const [operatingMarket, setOperatingMarket] = useState('US-East Cluster (Ashburn, VA - 863)');
  const [preferredAreaCode, setPreferredAreaCode] = useState('863');

  // Dynamic trade impact dataset computed from live active transactions (Batch -> Gateway -> Cluster)
  const dynamicTradeImpact = useMemo(() => {
    return buildTradeImpactFromTransactions(transactions);
  }, [transactions]);


  // Memoize data sources to maintain reference stability for AG Studio
  const studioData: AgDataSourcesDefinition = useMemo(() => {
    return {
      sources: [
        {
          id: 'transactions',
          data: transactions,
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
            { id: 'kyc_status', name: 'Signature & Policy State', format: 'textFormat' },
            { id: 'kyc_legal_entity', name: 'Principal Entity', format: 'textFormat' },
            { id: 'allocated_did', name: 'Worker Node Endpoint', format: 'textFormat' },
            { id: 'tcpa_guard', name: 'Anti-Tamper & Spending Guard', format: 'textFormat' },
            { id: 'status', name: 'Subscription State', format: 'textFormat' },
          ],
        },
        {
          id: 'trade_impact',
          data: dynamicTradeImpact,
          fields: [
            { id: 'trade', name: 'Service Capability', format: 'textFormat' },
            { id: 'active_agents', name: 'Connected Buyer Agents', format: 'integerFormat' },
            { id: 'mandates_cleared', name: 'Mandates Settled', format: 'integerFormat' },
            { id: 'monthly_settlement', name: 'Monthly M2M Volume ($/mo)', format: 'currencyFormat' },
            { id: 'annualized_gmv', name: 'Autonomous AP2 GMV ($ ARR)', format: 'currencyFormat' },
            { id: 'recovered_revenue', name: 'Autonomous AP2 GMV ($ ARR)', format: 'currencyFormat' },
            { id: 'leads_captured', name: 'Workload Tasks Fulfilled', format: 'integerFormat' },
            { id: 'missed_calls_prevented', name: 'Tamper Attempts Blocked', format: 'integerFormat' },
            { id: 'subscription_cost', name: 'PayPal Cost ($79.99/mo)', format: 'currencyFormat' },
            { id: 'roi_multiple', name: 'AP2 Settlement Multiplier (x)', format: 'decimalFormat' },
          ],
        },
        {
          id: 'kyc_audit',
          data: kycAuditData,
          fields: [
            { id: 'allocated_did', name: 'Node Endpoint', format: 'textFormat' },
            { id: 'carrier_resporg', name: 'Worker Enclave', format: 'textFormat' },
            { id: 'tcr_campaign_id', name: 'Cluster Enclave ID', format: 'textFormat' },
            { id: 'subscriber_legal_name', name: 'Principal Entity', format: 'textFormat' },
            { id: 'paypal_payer_id', name: 'PayPal Payer ID', format: 'textFormat' },
            { id: 'autodialer_blocked', name: 'Replay Nonce Monotonic Active', format: 'booleanFormat' },
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
            { id: 'tcr_brand', name: 'Security Enclave', format: 'textFormat' },
            { id: 'tcr_campaign_id', name: 'Cluster Specification', format: 'textFormat' },
            { id: 'monthly_quota_minutes', name: 'Monthly Quota (Hours)', format: 'integerFormat' },
            { id: 'stir_shaken_level', name: 'Execution Protocol', format: 'textFormat' },
            { id: 'inbound_routing_mode', name: 'Routing Interface', format: 'textFormat' },
          ],
        },
      ],
    };
  }, [transactions, dynamicTradeImpact]);

  // Hydrate fleet transactions and verify initial state from SQLite backend with periodic background polling
  useEffect(() => {
    let mounted = true;
    async function loadInitialFleet() {
      const liveTxns = await fetchFleetLedger();
      if (mounted && liveTxns.length > 0) {
        setTransactions(liveTxns);
        setLastFetchTime(new Date().toISOString().slice(11, 19) + ' UTC');
        const pendingEntry = liveTxns.find((t) => t.id === 'TXN-AP2-9021' || t.id === 'AP2-TXN-9021' || t.principal_entity === 'Nexus Autonomous Systems Corp' || t.contractor_name === 'Acme Autonomous Systems LLC');
        if (pendingEntry && pendingEntry.status === 'ACTIVE_STREAMING') {
          setIsPendingDepositLocked(true);
        }
      }
    }
    loadInitialFleet();

    const intervalId = setInterval(async () => {
      if (!mounted) return;
      const liveTxns = await fetchFleetLedger();
      if (mounted && liveTxns.length > 0) {
        setTransactions((prev) => {
          const isPendingElevatedLocally = prev.some((t) => (t.id === 'TXN-AP2-9021' || t.id === 'AP2-TXN-9021') && t.status === 'ACTIVE_STREAMING');
          const localExtraRows = prev.filter((t) => !liveTxns.some((lt) => lt.id === t.id));

          let merged = liveTxns.map((lt) => {
            if ((lt.id === 'TXN-AP2-9021' || lt.id === 'AP2-TXN-9021') && isPendingElevatedLocally) {
              const localElevated = prev.find((t) => t.id === lt.id);
              return localElevated || { ...lt, status: 'ACTIVE_STREAMING' };
            }
            return lt;
          });
          if (localExtraRows.length > 0) {
            merged = [...localExtraRows, ...merged];
          }
          return merged;
        });
      }
    }, 10000);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, []);

  const handleRefreshFleet = useCallback(async () => {
    const liveTxns = await fetchFleetLedger();
    if (liveTxns.length > 0) {
      setTransactions((prev) => {
        const isPendingElevatedLocally = prev.some((t) => (t.id === 'TXN-AP2-9021' || t.id === 'AP2-TXN-9021') && t.status === 'ACTIVE_STREAMING');
        const localExtraRows = prev.filter((t) => !liveTxns.some((lt) => lt.id === t.id));

        let merged = liveTxns.map((lt) => {
          if ((lt.id === 'TXN-AP2-9021' || lt.id === 'AP2-TXN-9021') && isPendingElevatedLocally) {
            const localElevated = prev.find((t) => t.id === lt.id);
            return localElevated || { ...lt, status: 'ACTIVE_STREAMING' };
          }
          return lt;
        });
        if (localExtraRows.length > 0) {
          merged = [...localExtraRows, ...merged];
        }
        return merged;
      });
      setLastFetchTime(new Date().toISOString().slice(11, 19) + ' UTC');
      const pendingEntry = liveTxns.find((t) => t.id === 'TXN-AP2-9021' || t.id === 'AP2-TXN-9021' || t.principal_entity === 'Nexus Autonomous Systems Corp' || t.contractor_name === 'Acme Autonomous Systems LLC');
      if (pendingEntry && pendingEntry.status === 'ACTIVE_STREAMING') {
        setIsPendingDepositLocked(true);
      }
    }
  }, []);

  // Start Autonomous Negotiation Simulation
  const handleStartNegotiation = useCallback(async () => {
    setIsNegotiating(true);
    setProvisioningResult(null);

    const req: AgentNegotiationRequest = {
      contractorName,
      businessEntity,
      tradeVertical,
      maxMonthlyBudget,
    };

    const res = await evaluateAgentNegotiation(req);
    setNegotiationResult(res);
    setIsNegotiating(false);
  }, [contractorName, businessEntity, tradeVertical, maxMonthlyBudget]);

  // Complete Subscription & Provision Line: Mutates existing transaction in place (Orange -> Green)
  const handleSubscriptionApproved = useCallback(
    async (subId: string) => {
      setIsProvisioning(true);
      try {
        const agreedMonthlyAmount = negotiationResult?.monthlyFee ?? 79.99;
        
        // Map to exact tier name based on agreed monthly amount
        let actualTier = 'Dedicated AI Service Gateway';
        let canonicalPlanName = 'Dedicated AI Service Gateway ($79.99/mo)';

        if (Math.abs(agreedMonthlyAmount - 49.99) < 0.05) {
          actualTier = 'High-Throughput Batch Worker';
          canonicalPlanName = 'High-Throughput Batch Worker ($49.99/mo)';
        } else if (Math.abs(agreedMonthlyAmount - 179.99) < 0.05) {
          actualTier = 'Enterprise Cluster Node';
          canonicalPlanName = 'Enterprise Cluster Node ($179.99/mo)';
        } else {
          actualTier = 'Dedicated AI Service Gateway';
          canonicalPlanName = 'Dedicated AI Service Gateway ($79.99/mo)';
        }

        const agreedPlanName = negotiationResult?.agreedPlanName || canonicalPlanName;

        const result = await executeProvisioningAfterSubscription(
          subId,
          businessEntity,
          actualTier,
          preferredAreaCode
        );
        setProvisioningResult(result);

        // Mutate existing record in place so the row transitions from PENDING_DEPOSIT -> ACTIVE_STREAMING
        setTransactions((prev) => {
          const idx = prev.findIndex((t) => t.id === 'TXN-AP2-9021' || t.id === 'AP2-TXN-9021' || t.contractor_name === contractorName || t.principal_entity === 'Nexus Autonomous Systems Corp' || t.contractor_name === 'Acme Autonomous Systems LLC');
          if (idx !== -1) {
            const updated = [...prev];
            updated[idx] = {
              ...updated[idx],
              timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
              monthly_amount: agreedMonthlyAmount,
              trade_vertical: actualTier,
              service_plan: agreedPlanName,
              paypal_sub_id: subId,
              kyc_status: 'VERIFIED (PayPal Identity Bound)',
              allocated_did: result.allocatedDid,
              tcpa_guard: 'RFC 8032 ED25519 VERIFIED (ANTI-TAMPER PASS)',
              status: 'ACTIVE_STREAMING',
            };
            return updated;
          }

          // Fallback if not found in list: prepend new entry
          const newTxn: A2aTransaction = {
            id: `TXN-${Math.floor(1000 + Math.random() * 9000)}`,
            timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
            buyer_agent: `AutonomousBuyerAgent-${contractorName.split(' ')[0]}-${actualTier.replace(/\s+/g, '')}`,
            principal_entity: businessEntity,
            contractor_name: contractorName,
            trade_vertical: actualTier,
            service_plan: agreedPlanName,
            monthly_amount: agreedMonthlyAmount,
            paypal_sub_id: subId,
            kyc_status: 'VERIFIED (PayPal Identity Bound)',
            kyc_legal_entity: businessEntity,
            allocated_did: result.allocatedDid,
            tcpa_guard: 'RFC 8032 ED25519 VERIFIED (ANTI-TAMPER PASS)',
            status: 'ACTIVE_STREAMING',
          };
          return [newTxn, ...prev];
        });

        // Also lock AP2 pending workload slot in Bryntum Dispatch
        setIsPendingDepositLocked(true);
      } finally {
        setIsProvisioning(false);
      }
    },
    [contractorName, businessEntity, tradeVertical, preferredAreaCode, negotiationResult]
  );

  return (
    <div className="app-container">
      {/* Executive Header Card */}
      <header
        className="app-header"
        style={{
          margin: '10px 16px 0 16px',
          borderRadius: '12px',
          border: '1px solid #1e293b',
          backgroundColor: '#0f172a',
          padding: '10px 16px',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            width: '100%',
            gap: '16px',
            flexWrap: 'nowrap',
          }}
        >
          {/* Left Column: Brand & Command Center Sub-Header */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              minWidth: 0,
              flexShrink: 1,
            }}
          >
            {/* Brand Section */}
            <div className="brand-section" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div className="brand-icon-wrapper" style={{ flexShrink: 0, width: '38px', height: '38px' }}>
                <Ap2Logo size={32} />
              </div>
              <div className="brand-titles" style={{ minWidth: 0 }}>
                <h1 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc', letterSpacing: '-0.02em', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  AP2 Seller Operations Deck
                </h1>
                <p className="brand-subtitle" style={{ fontSize: '11px', color: '#94a3b8', margin: '4px 0 0 0', letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  Autonomous Agent Payments Protocol (AP2) Commerce &bull; Turnkey FastMCP Merchant Node &bull; PayPal Subscriptions
                </p>
              </div>
            </div>
          </div>

          {/* Right Column: Merged Button Set & Live Telemetry Metrics */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-start',
              gap: '6px',
              flexShrink: 0,
            }}
          >
            {/* The Merged Button Set + Side Actions */}
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
              {/* Unified Merged Button Box: Rows are merged into a single cohesive set */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  backgroundColor: '#1e293b',
                  borderRadius: '8px',
                  border: '1px solid #334155',
                  padding: '3px',
                  width: '370px',
                  boxSizing: 'border-box',
                }}
              >
                {/* Row 1: Primary Navigation Tabs */}
                <div style={{ display: 'flex', alignItems: 'center', height: '30px', width: '100%' }}>
                  <button
                    onClick={() => setActiveTab('copilot')}
                    style={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '5px',
                      padding: '0 8px',
                      height: '100%',
                      borderRadius: '5px',
                      border: 'none',
                      backgroundColor: activeTab === 'copilot' ? '#0284c7' : 'transparent',
                      color: activeTab === 'copilot' ? '#fff' : '#94a3b8',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      boxSizing: 'border-box',
                    }}
                  >
                    <Cpu size={13} /> Setup
                  </button>
                  <button
                    onClick={() => {
                      setActiveTab('fleet-ledger');
                      setLedgerViewMode('grid');
                    }}
                    style={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '5px',
                      padding: '0 8px',
                      height: '100%',
                      borderRadius: '5px',
                      border: 'none',
                      backgroundColor: (activeTab === 'fleet-ledger' || activeTab === 'ag-studio') ? '#0284c7' : 'transparent',
                      color: (activeTab === 'fleet-ledger' || activeTab === 'ag-studio') ? '#fff' : '#94a3b8',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      boxSizing: 'border-box',
                    }}
                  >
                    <LayoutGrid size={13} /> Dashboard
                  </button>
                  <button
                    onClick={() => setActiveTab('bryntum')}
                    style={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '5px',
                      padding: '0 8px',
                      height: '100%',
                      borderRadius: '5px',
                      border: 'none',
                      backgroundColor: activeTab === 'bryntum' ? '#0284c7' : 'transparent',
                      color: activeTab === 'bryntum' ? '#fff' : '#94a3b8',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      boxSizing: 'border-box',
                    }}
                  >
                    <Calendar size={13} /> Workloads
                  </button>
                  <button
                    onClick={() => setActiveTab('zapier')}
                    style={{
                      flex: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '5px',
                      padding: '0 8px',
                      height: '100%',
                      borderRadius: '5px',
                      border: 'none',
                      backgroundColor: activeTab === 'zapier' ? '#0284c7' : 'transparent',
                      color: activeTab === 'zapier' ? '#fff' : '#94a3b8',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      boxSizing: 'border-box',
                    }}
                  >
                    <Network size={13} /> MCP
                  </button>
                </div>

                {/* Merged Gray Line & Row 2: Secondary View Switchers (Every tab has a custom Row 2) */}
                <div style={{ height: '1px', backgroundColor: '#334155', margin: '3px 0', width: '100%' }} />

                {/* Tab 1 Setup: FastMCP Status */}
                {activeTab === 'copilot' && (
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '30px', width: '100%', padding: '0 8px' }}>
                    <span style={{ fontSize: '11px', fontWeight: 600, color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }} />
                      FastMCP Active &bull; {typeof window !== 'undefined' && window.location.port ? `Port ${window.location.port}` : 'Live'} &bull; RFC 8032 Ed25519
                    </span>
                  </div>
                )}

                {/* Tab 2 Dashboard: Live Operational Grid vs AG Studio BI Suite */}
                {(activeTab === 'fleet-ledger' || activeTab === 'ag-studio') && (
                  <div style={{ display: 'flex', alignItems: 'center', height: '30px', width: '100%' }}>
                    <button
                      onClick={() => {
                        setActiveTab('fleet-ledger');
                        setLedgerViewMode('grid');
                      }}
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        padding: '0 10px',
                        height: '100%',
                        borderRadius: '5px',
                        border: 'none',
                        backgroundColor: ledgerViewMode === 'grid' ? '#0284c7' : 'transparent',
                        color: ledgerViewMode === 'grid' ? '#ffffff' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        boxSizing: 'border-box',
                        transition: 'all 0.15s ease',
                      }}
                      title="Live high-density operational ledger"
                    >
                      <LayoutGrid size={13} /> Live Operational Grid
                    </button>
                    <button
                      onClick={() => {
                        setActiveTab('fleet-ledger');
                        setLedgerViewMode('studio');
                      }}
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        padding: '0 10px',
                        height: '100%',
                        borderRadius: '5px',
                        border: 'none',
                        backgroundColor: ledgerViewMode === 'studio' ? '#0284c7' : 'transparent',
                        color: ledgerViewMode === 'studio' ? '#ffffff' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        boxSizing: 'border-box',
                        transition: 'all 0.15s ease',
                      }}
                      title="Interactive AG Studio report designer"
                    >
                      <Layers size={13} />
                      <span>AG Studio BI Suite</span>
                      <span
                        style={{
                          fontSize: '9px',
                          fontWeight: 700,
                          backgroundColor: ledgerViewMode === 'studio' ? 'rgba(255, 255, 255, 0.2)' : 'rgba(56, 189, 248, 0.15)',
                          color: ledgerViewMode === 'studio' ? '#ffffff' : '#38bdf8',
                          padding: '1px 5px',
                          borderRadius: '3px',
                          letterSpacing: '0.02em',
                        }}
                      >
                        Sponsor
                      </span>
                    </button>
                  </div>
                )}

                {/* Tab 3 Schedule: Bryntum Sponsor vs Node Grid */}
                {activeTab === 'bryntum' && (
                  <div style={{ display: 'flex', alignItems: 'center', height: '30px', width: '100%' }}>
                    <button
                      onClick={() => setSchedulerViewMode('timeline')}
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        padding: '0 10px',
                        height: '100%',
                        borderRadius: '5px',
                        border: 'none',
                        backgroundColor: schedulerViewMode === 'timeline' ? '#0284c7' : 'transparent',
                        color: schedulerViewMode === 'timeline' ? '#ffffff' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        boxSizing: 'border-box',
                        transition: 'all 0.15s ease',
                      }}
                      title="Bryntum Scheduler Pro (Hackathon Official Sponsor Engine)"
                    >
                      <Clock size={12} color={schedulerViewMode === 'timeline' ? '#ffffff' : '#94a3b8'} />
                      <span>Bryntum</span>
                      <span
                        style={{
                          fontSize: '9px',
                          fontWeight: 700,
                          backgroundColor: schedulerViewMode === 'timeline' ? 'rgba(255, 255, 255, 0.2)' : 'rgba(56, 189, 248, 0.15)',
                          color: schedulerViewMode === 'timeline' ? '#ffffff' : '#38bdf8',
                          padding: '1px 5px',
                          borderRadius: '3px',
                          letterSpacing: '0.02em',
                        }}
                      >
                        Sponsor
                      </span>
                    </button>
                    <button
                      onClick={() => setSchedulerViewMode('matrix')}
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        padding: '0 10px',
                        height: '100%',
                        borderRadius: '5px',
                        border: 'none',
                        backgroundColor: schedulerViewMode === 'matrix' ? '#0284c7' : 'transparent',
                        color: schedulerViewMode === 'matrix' ? '#ffffff' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        boxSizing: 'border-box',
                        transition: 'all 0.15s ease',
                      }}
                      title="Compact Node Card Grid View"
                    >
                      <Server size={12} color={schedulerViewMode === 'matrix' ? '#ffffff' : '#94a3b8'} />
                      <span>Node Grid</span>
                    </button>
                  </div>
                )}

                {/* Tab 4 MCP: AP2 Settlement vs Workload Dispatch */}
                {activeTab === 'zapier' && (
                  <div style={{ display: 'flex', alignItems: 'center', height: '30px', width: '100%' }}>
                    <button
                      onClick={() => setMcpScenario('a2a')}
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        padding: '0 10px',
                        height: '100%',
                        borderRadius: '5px',
                        border: 'none',
                        backgroundColor: mcpScenario === 'a2a' ? '#0284c7' : 'transparent',
                        color: mcpScenario === 'a2a' ? '#ffffff' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        boxSizing: 'border-box',
                        transition: 'all 0.15s ease',
                      }}
                      title="Autonomous AP2 Agent Onboarding & Settlement Chain"
                    >
                      <Sparkles size={12} color={mcpScenario === 'a2a' ? '#fde047' : '#94a3b8'} />
                      <span>AP2 Settlement</span>
                    </button>
                    <button
                      onClick={() => setMcpScenario('workload')}
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        padding: '0 10px',
                        height: '100%',
                        borderRadius: '5px',
                        border: 'none',
                        backgroundColor: mcpScenario === 'workload' ? '#0284c7' : 'transparent',
                        color: mcpScenario === 'workload' ? '#ffffff' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                        boxSizing: 'border-box',
                        transition: 'all 0.15s ease',
                      }}
                      title="AP2 Workload Execution Dispatch Dossier"
                    >
                      <Play size={12} color={mcpScenario === 'workload' ? '#38bdf8' : '#94a3b8'} />
                      <span>Workload Dispatch</span>
                    </button>
                  </div>
                )}
              </div>

              {/* Side Actions Column: Simulate button on Row 1, Expand/Collapse toggle on Row 2 */}
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  alignItems: 'flex-start',
                }}
              >
                <button
                  className="btn-simulate"
                  onClick={() => setIsModalOpen(true)}
                  style={{
                    height: '36px',
                    padding: '0 14px',
                    fontSize: '12px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    boxSizing: 'border-box',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <Sliders size={14} /> Simulate AP2 Purchase
                </button>

                {/* Expand / Collapse Button (Uniform across all 4 Tabs) */}
                <button
                  onClick={() => {
                    if (activeTab === 'copilot') {
                      setIsSetupGuideCollapsed((prev) => !prev);
                    } else if (activeTab === 'fleet-ledger' || activeTab === 'ag-studio') {
                      setIsDashboardMetricsCollapsed((prev) => !prev);
                    } else if (activeTab === 'bryntum') {
                      setIsScheduleMetricsCollapsed((prev) => !prev);
                    } else if (activeTab === 'zapier') {
                      setIsMcpControlsCollapsed((prev) => !prev);
                    }
                  }}
                  style={{
                    height: '30px',
                    padding: '0 12px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '6px',
                    color:
                      (activeTab === 'copilot' && isSetupGuideCollapsed) ||
                      ((activeTab === 'fleet-ledger' || activeTab === 'ag-studio') && isDashboardMetricsCollapsed) ||
                      (activeTab === 'bryntum' && isScheduleMetricsCollapsed) ||
                      (activeTab === 'zapier' && isMcpControlsCollapsed)
                        ? '#38bdf8'
                        : '#94a3b8',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    boxSizing: 'border-box',
                    transition: 'all 0.15s ease',
                  }}
                  title={
                    (activeTab === 'copilot' && isSetupGuideCollapsed) ||
                    ((activeTab === 'fleet-ledger' || activeTab === 'ag-studio') && isDashboardMetricsCollapsed) ||
                    (activeTab === 'bryntum' && isScheduleMetricsCollapsed) ||
                    (activeTab === 'zapier' && isMcpControlsCollapsed)
                      ? 'Expand Cards'
                      : 'Collapse Cards'
                  }
                >
                  {(activeTab === 'copilot' && isSetupGuideCollapsed) ||
                  ((activeTab === 'fleet-ledger' || activeTab === 'ag-studio') && isDashboardMetricsCollapsed) ||
                  (activeTab === 'bryntum' && isScheduleMetricsCollapsed) ||
                  (activeTab === 'zapier' && isMcpControlsCollapsed) ? (
                    <ChevronDown size={13} />
                  ) : (
                    <ChevronUp size={13} />
                  )}
                  <span>
                    {(activeTab === 'copilot' && isSetupGuideCollapsed) ||
                    ((activeTab === 'fleet-ledger' || activeTab === 'ag-studio') && isDashboardMetricsCollapsed) ||
                    (activeTab === 'bryntum' && isScheduleMetricsCollapsed) ||
                    (activeTab === 'zapier' && isMcpControlsCollapsed)
                      ? 'Expand'
                      : 'Collapse'}
                  </span>
                </button>
              </div>
            </div>

            {/* Row 3: Live Summary Metrics Strip (Clean telemetry for every tab) */}
            {activeTab === 'copilot' && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  fontSize: '11px',
                  color: '#94a3b8',
                  paddingLeft: '4px',
                  paddingTop: '2px',
                  whiteSpace: 'nowrap',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Daemon:</span>
                  <span style={{ color: '#38bdf8', fontFamily: 'monospace', fontWeight: 700 }}>{typeof window !== 'undefined' && window.location.origin ? `${window.location.origin}/mcp` : 'http://127.0.0.1:8001/mcp'}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Tools:</span>
                  <span style={{ color: '#f8fafc', fontWeight: 700 }}>5 FastMCP Tools</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Status:</span>
                  <span style={{ color: '#34d399', fontWeight: 700 }}>Online ({typeof window !== 'undefined' && window.location.port ? `Port ${window.location.port}` : 'Live'})</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Auth:</span>
                  <span style={{ color: '#38bdf8', fontWeight: 700 }}>RFC 8032</span>
                </div>
              </div>
            )}

            {(activeTab === 'fleet-ledger' || activeTab === 'ag-studio') && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  fontSize: '11px',
                  color: '#94a3b8',
                  paddingLeft: '4px',
                  paddingTop: '2px',
                  whiteSpace: 'nowrap',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>MRR:</span>
                  <span style={{ color: '#f8fafc', fontWeight: 700 }}>${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mo</span>
                  <span style={{ color: '#34d399', fontSize: '10px' }}>({activeLinesCount} active &middot; {pendingLinesCount} pending)</span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Subscriptions:</span>
                  <span style={{ color: '#f8fafc', fontWeight: 700 }}>{activeLinesCount} Active</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Annual GMV:</span>
                  <span style={{ color: '#38bdf8', fontWeight: 700 }}>${totalAutonomousGmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ARR</span>
                </div>
              </div>
            )}

            {activeTab === 'bryntum' && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  fontSize: '11px',
                  color: '#94a3b8',
                  paddingLeft: '4px',
                  paddingTop: '2px',
                  whiteSpace: 'nowrap',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Sync:</span>
                  <span style={{ color: '#34d399', fontFamily: 'monospace', fontWeight: 700 }}>{lastFetchTime}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Worker Nodes:</span>
                  <span style={{ color: '#f8fafc', fontWeight: 700 }}>5 Nodes</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>SLA:</span>
                  <span style={{ color: '#38bdf8', fontWeight: 700 }}>99.98% Latency</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Active:</span>
                  <span style={{ color: '#34d399', fontWeight: 700 }}>Node-01 ($79.99)</span>
                </div>
              </div>
            )}

            {activeTab === 'zapier' && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  fontSize: '11px',
                  color: '#94a3b8',
                  paddingLeft: '4px',
                  paddingTop: '2px',
                  whiteSpace: 'nowrap',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Bridge:</span>
                  <span style={{ color: '#38bdf8', fontWeight: 700 }}>Zapier FastMCP</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>ERP:</span>
                  <span style={{ color: '#f8fafc', fontWeight: 700 }}>QBO GL 6300</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>EventBus:</span>
                  <span style={{ color: '#34d399', fontWeight: 700 }}>CloudEvents v1.0</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b', fontWeight: 600 }}>Transport:</span>
                  <span style={{ color: '#38bdf8', fontWeight: 700 }}>SSE Stream</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="studio-canvas-container">
        {activeTab === 'copilot' && (
          <SellerCopilotView
            contractorName={contractorName}
            businessEntity={businessEntity}
            tradeVertical={tradeVertical}
            areaCode={preferredAreaCode}
            budgetCap={maxMonthlyBudget}
            activeStep={activeSetupStep}
            onSelectStep={setActiveSetupStep}
            isGuideCollapsed={isSetupGuideCollapsed}
            onToggleGuideCollapsed={() => setIsSetupGuideCollapsed((prev) => !prev)}
            onNavigateTab={handleNavigateTab}
            onSaveSettings={(newSettings: NodeSettingsData) => {
              setBusinessEntity(newSettings.businessEntity);
              setTradeVertical(newSettings.tradeVertical);
            }}
            onA2aCompleted={({ subscriptionId, allocatedDid }) => {
              setTransactions((prev) => {
                const idx = prev.findIndex((t) => t.contractor_name === contractorName);
                if (idx !== -1) {
                  const updated = [...prev];
                  const agreedRate = maxMonthlyBudget < 79.99 ? 49.99 : 79.99;
                  const planTitle = agreedRate === 49.99 ? 'AP2 Solo Node (125k Executions/mo)' : 'AP2 Enterprise Cluster (500k Executions/mo)';
                  updated[idx] = {
                    ...updated[idx],
                    timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
                    service_plan: planTitle,
                    monthly_amount: agreedRate,
                    paypal_sub_id: subscriptionId,
                    kyc_status: 'VERIFIED (PayPal Identity Bound)',
                    allocated_did: allocatedDid,
                    tcpa_guard: 'RFC 8032 ED25519 VERIFIED (ANTI-TAMPER PASS)',
                    status: 'ACTIVE_STREAMING',
                  };
                  return updated;
                }
                return prev;
              });
              setIsPendingDepositLocked(true);
            }}
          />
        )}

        {(activeTab === 'fleet-ledger' || activeTab === 'ag-studio') && (
          <EnterpriseFleetLedger
            transactions={transactions}
            tradeImpactData={dynamicTradeImpact}
            kycAuditData={kycAuditData}
            studioData={studioData}
            studioMode={mode}
            onSetStudioMode={setMode}
            onSimulateClick={() => setIsModalOpen(true)}
            onInspectTrace={() => {
              setActiveTab('copilot');
            }}
            onNavigateTab={handleNavigateTab}
            onRefreshData={handleRefreshFleet}
            viewMode={activeTab === 'ag-studio' ? 'studio' : ledgerViewMode}
            onViewModeChange={setLedgerViewMode}
            isTopMetricsCollapsed={isDashboardMetricsCollapsed}
            onToggleTopMetrics={() => setIsDashboardMetricsCollapsed((prev) => !prev)}
          />
        )}

        {activeTab === 'bryntum' && (
          <BryntumDispatchScheduler
            isDepositLocked={isPendingDepositLocked}
            viewMode={schedulerViewMode}
            onViewModeChange={setSchedulerViewMode}
            isMetricsCollapsed={isScheduleMetricsCollapsed}
            onToggleMetrics={() => setIsScheduleMetricsCollapsed((prev) => !prev)}
            onToggleDepositLock={(locked) => {
              setIsPendingDepositLocked(locked);
              setTransactions((prev) => {
                const idx = prev.findIndex((t) => t.id === 'TXN-AP2-9021' || t.id === 'AP2-TXN-9021' || t.principal_entity === 'Nexus Autonomous Systems Corp' || t.contractor_name === 'Acme Autonomous Systems LLC');
                if (idx !== -1) {
                  const updated = [...prev];
                  updated[idx] = {
                    ...updated[idx],
                    timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
                    status: locked ? 'ACTIVE_STREAMING' : 'PENDING_DEPOSIT',
                    kyc_status: locked ? 'VERIFIED (PayPal Identity Bound)' : 'PENDING_MANDATE_SIGNATURE',
                    allocated_did: locked ? 'node-cluster-01.ap2.net' : 'node-cluster-01.ap2.net',
                    tcpa_guard: locked ? 'RFC 8032 ED25519 VERIFIED (ANTI-TAMPER PASS)' : 'PENDING_AUTHORIZATION',
                    paypal_sub_id: locked
                      ? updated[idx].paypal_sub_id.startsWith('I-')
                        ? updated[idx].paypal_sub_id
                        : 'I-BW452NX993L2'
                      : 'AWAITING_PAYPAL_TOKEN',
                  };
                  return updated;
                }
                return prev;
              });
            }}
          />
        )}

        {activeTab === 'zapier' && (
          <ZapierMcpView
            contractorName={contractorName}
            businessEntity={businessEntity}
            allocatedDid={provisioningResult?.allocatedDid || 'node-cluster-01.ap2.net:8443'}
            tradeVertical={tradeVertical}
            monthlyFee={79.99}
            paypalSubscriptionId={provisioningResult?.subscriptionId || 'I-AUTONOMOUS-8902'}
            isDepositLocked={isPendingDepositLocked}
            activeScenario={mcpScenario}
            onScenarioChange={setMcpScenario}
            isControlsCollapsed={isMcpControlsCollapsed}
            onToggleControls={() => setIsMcpControlsCollapsed((prev) => !prev)}
          />
        )}
      </main>

      {/* Modal: AP2 Agentic Commerce Negotiation & Subscription Simulator */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>
                <Sliders size={18} /> AP2 Buyer Agent Procurement Simulator
              </h3>
              <button className="btn-close" onClick={() => setIsModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              <p style={{ fontSize: '13px', color: '#94a3b8' }}>
                Simulate how an external <strong>Autonomous Buyer Agent</strong> discovers seller node capabilities,
                verifies cryptographic spending mandate caps, negotiates with the AP2 Seller FastMCP Server, and executes a
                recurring PayPal billing agreement with verified RFC 8032 Ed25519 attestations.
              </p>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '12px',
                  backgroundColor: '#0f172a',
                  padding: '14px',
                  borderRadius: '8px',
                }}
              >
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                    Buyer Agent ID
                  </label>
                  <input
                    type="text"
                    value={contractorName}
                    onChange={(e) => setContractorName(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px',
                      borderRadius: '4px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: '#fff',
                      fontSize: '13px',
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                    Principal Legal Entity
                  </label>
                  <input
                    type="text"
                    value={businessEntity}
                    onChange={(e) => setBusinessEntity(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px',
                      borderRadius: '4px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: '#fff',
                      fontSize: '13px',
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                    Service Capability Tier
                  </label>
                  <select
                    value={tradeVertical}
                    onChange={(e) => setTradeVertical(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px',
                      borderRadius: '4px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: '#fff',
                      fontSize: '13px',
                    }}
                  >
                    <option value="Dedicated AI Service Gateway">Dedicated AI Service Gateway ($79.99/mo)</option>
                    <option value="High-Throughput Batch Worker">High-Throughput Batch Worker ($49.99/mo)</option>
                    <option value="Autonomous Security Audit Cluster">Autonomous Security Audit Cluster ($179.99/mo)</option>
                    <option value="Vector RAG Ingestion Pipeline">Vector RAG Ingestion Pipeline ($79.99/mo)</option>
                    <option value="Real-Time Audio Telephony Streamer">Real-Time Audio Telephony Streamer ($79.99/mo)</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                    Max Monthly Spending Mandate ($)
                  </label>
                  <input
                    type="number"
                    value={maxMonthlyBudget}
                    onChange={(e) => setMaxMonthlyBudget(parseFloat(e.target.value) || 0)}
                    style={{
                      width: '100%',
                      padding: '8px',
                      borderRadius: '4px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: '#fff',
                      fontSize: '13px',
                    }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                    Target Execution Cluster
                  </label>
                  <select
                    value={operatingMarket}
                    onChange={(e) => {
                      const val = e.target.value;
                      setOperatingMarket(val);
                      const match = val.match(/\((\d{3})\)/);
                      if (match) {
                        setPreferredAreaCode(match[1]);
                      }
                    }}
                    style={{
                      width: '100%',
                      padding: '8px',
                      borderRadius: '4px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: '#fff',
                      fontSize: '13px',
                    }}
                  >
                    <option value="US-East Cluster (Ashburn, VA - 863)">US-East Cluster (Ashburn, VA - 863)</option>
                    <option value="US-Central Cluster (Council Bluffs, IA - 515)">US-Central Cluster (Council Bluffs, IA - 515)</option>
                    <option value="US-West Cluster (The Dalles, OR - 541)">US-West Cluster (The Dalles, OR - 541)</option>
                    <option value="EU-West Cluster (Frankfurt, DE - 49)">EU-West Cluster (Frankfurt, DE - 49)</option>
                    <option value="AP-East Cluster (Tokyo, JP - 81)">AP-East Cluster (Tokyo, JP - 81)</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                    Assigned Gateway Route / Port
                  </label>
                  <input
                    type="text"
                    maxLength={3}
                    placeholder="e.g. 863, 515, 541"
                    value={preferredAreaCode}
                    onChange={(e) => setPreferredAreaCode(e.target.value.replace(/\D/g, '').slice(0, 3))}
                    style={{
                      width: '100%',
                      padding: '8px',
                      borderRadius: '4px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: '#38bdf8',
                      fontWeight: 600,
                      fontSize: '13px',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                <button
                  className="btn-simulate"
                  style={{
                    flex: 1,
                    justifyContent: 'center',
                    padding: '10px',
                    backgroundColor: negotiationResult?.mandateSatisfied
                      ? '#064e3b'
                      : isNegotiating
                      ? '#1e293b'
                      : undefined,
                    color: negotiationResult?.mandateSatisfied ? '#34d399' : undefined,
                    border: negotiationResult?.mandateSatisfied ? '1px solid #059669' : undefined,
                    cursor: negotiationResult?.mandateSatisfied ? 'not-allowed' : 'pointer',
                    opacity: negotiationResult?.mandateSatisfied ? 0.85 : 1,
                  }}
                  onClick={handleStartNegotiation}
                  disabled={isNegotiating || Boolean(negotiationResult?.mandateSatisfied)}
                >
                  {isNegotiating
                    ? 'Evaluating Mandate & Seller FastMCP...'
                    : negotiationResult?.mandateSatisfied
                    ? `✓ 1. Mandate Policy Verified ($${negotiationResult.monthlyFee.toFixed(2)}/mo)`
                    : '1. Run AP2 Autonomous Negotiation'}
                </button>
                <button
                  onClick={async () => {
                    const buyerAgentId = `BuyerAgent-${contractorName.split(' ')[0]}-${tradeVertical.replace(/\s+/g, '')}`;
                    await resetMandateLedger(buyerAgentId);
                    setNegotiationResult(null);
                    setProvisioningResult(null);
                    setPaypalError(null);
                    setIsPendingDepositLocked(false);
                    setTransactions((prev) => {
                      const idx = prev.findIndex((t) => t.contractor_name === contractorName);
                      if (idx !== -1) {
                        const updated = [...prev];
                        updated[idx] = {
                          ...updated[idx],
                          timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
                          paypal_sub_id: 'AWAITING_PAYPAL_TOKEN',
                          kyc_status: 'PENDING_KYC_VERIFICATION',
                          allocated_did: 'AWAITING_DEPOSIT',
                          tcpa_guard: 'PENDING ACTIVATION',
                          status: 'PENDING_DEPOSIT',
                        };
                        return updated;
                      }
                      return prev;
                    });
                  }}
                  title="Reset spending mandate ledger and restore buyer agent to pending status"
                  style={{
                    backgroundColor: '#1e293b',
                    color: '#94a3b8',
                    border: '1px solid #334155',
                    borderRadius: '6px',
                    padding: '0 12px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    fontWeight: 600,
                  }}
                >
                  ↺ Reset Mandate
                </button>
              </div>

              {negotiationResult && (
                <div className="negotiation-panel">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>Protocol Verification:</span>
                    <span style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '10px',
                      backgroundColor: negotiationResult.isLiveBackend ? '#065f46' : '#854d0e',
                      color: negotiationResult.isLiveBackend ? '#34d399' : '#fde047',
                    }}>
                      {negotiationResult.isLiveBackend ? `● FastAPI Backend Connected (${typeof window !== 'undefined' && window.location.port ? `Port ${window.location.port}` : 'Live'})` : '○ Local Simulation Mode'}
                    </span>
                  </div>
                  <div className="negotiation-line">[BuyerAgent]: Ingesting task requirements & cryptographic budget ceiling...</div>
                  <div className="negotiation-line">[BuyerAgent]: Querying AP2 Seller FastMCP Catalog: {negotiationResult.sellerMcpEndpoint}</div>
                  <div className="negotiation-line">[SellerMCP]: Quoted Capability: {negotiationResult.requestedPlanName || negotiationResult.agreedPlanName} @ ${(negotiationResult.requestedMonthlyRate ?? negotiationResult.monthlyFee).toFixed(2)}/mo</div>
                  {negotiationResult.isCounterOffer && (
                    <div className="negotiation-line warning" style={{ fontWeight: 600 }}>
                      {negotiationResult.counterOfferMessage}
                    </div>
                  )}
                  <div className={`negotiation-line ${negotiationResult.mandateSatisfied ? 'success' : 'warning'}`}>
                    {negotiationResult.message}
                  </div>
                  {negotiationResult.mandateToken && (
                    <div className="negotiation-line success" style={{ wordBreak: 'break-all', fontSize: '11px' }}>
                      [Ed25519 Mandate Signature]: {negotiationResult.mandateToken}
                    </div>
                  )}
                  {negotiationResult.mandateSatisfied && (
                    <div className="negotiation-line success">
                      [AP2 Protocol]: Spending mandate approved. Ready for delegated PayPal subscription authorization.
                    </div>
                  )}
                </div>
              )}

              {/* AP2 Cryptographic & Legal Policy Shield */}
              <div className="kyc-verification-box">
                <Lock size={18} color="#34d399" style={{ flexShrink: 0, marginTop: '2px' }} />
                <div className="kyc-details">
                  <h4>Cryptographic Mandate &amp; RFC 8032 Security Guard</h4>
                  <p>
                    Workloads are provisioned strictly via verified buyer agent Ed25519 signatures and authenticated PayPal billing agreements.
                    Execution nodes enforce strict monotonic replay counters and anti-tamper hash verification &mdash; zero unauthorized overages, zero fraudulent executions.
                  </p>
                </div>
              </div>

              {/* Interactive PayPal Payment Integration */}
              {negotiationResult && negotiationResult.mandateSatisfied && !provisioningResult && (
                <div
                  className="paypal-interactive-wrapper"
                  style={{
                    marginTop: '16px',
                    border: '1px solid #0284c7',
                    backgroundColor: 'rgba(2, 132, 199, 0.08)',
                    borderRadius: '8px',
                    padding: '16px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                    <span
                      style={{
                        backgroundColor: '#0284c7',
                        color: '#fff',
                        fontSize: '11px',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '4px',
                      }}
                    >
                      STEP 2
                    </span>
                    <h4 style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                      Authorize Settlement &amp; Provision Worker Node (Sandbox)
                    </h4>
                  </div>
                  <p style={{ fontSize: '11px', color: '#94a3b8', margin: '6px 0 12px 0' }}>
                    Authorizes ${negotiationResult.monthlyFee.toFixed(2)}/month recurring service contract ({negotiationResult.agreedPlanName}). Upon authorization, the Seller Node binds execution capacity to <strong>{businessEntity}</strong> in the sandbox harness.
                  </p>

                  {/* Primary Instant Simulated Approval Button */}
                  <button
                    onClick={() => {
                      const simulatedSubId = `I-AUTONOMOUS-${Math.floor(100000 + Math.random() * 900000)}`;
                      handleSubscriptionApproved(simulatedSubId);
                    }}
                    disabled={isProvisioning}
                    style={{
                      width: '100%',
                      padding: '12px 16px',
                      backgroundColor: isProvisioning ? '#1e293b' : '#2563eb',
                      color: '#ffffff',
                      border: 'none',
                      borderRadius: '6px',
                      fontWeight: 600,
                      fontSize: '13px',
                      cursor: isProvisioning ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      marginBottom: '8px',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
                    }}
                  >
                    {isProvisioning ? (
                      'Allocating Worker Node & Binding Attestation...'
                    ) : (
                      <>
                        <ShieldCheck size={16} /> Authorize ${negotiationResult.monthlyFee.toFixed(2)}/mo (Simulate approval — no PayPal call)
                      </>
                    )}
                  </button>

                  {PAYPAL_CONFIG.clientId !== 'test' && (
                    <div style={{ marginTop: '10px' }}>
                      <div style={{ textAlign: 'center', fontSize: '10px', color: '#64748b', marginBottom: '8px' }}>
                        &mdash; OR USE OFFICIAL PAYPAL SANDBOX BUTTON &mdash;
                      </div>
                      <div style={{ width: '100%', maxWidth: '320px', margin: '0 auto' }}>
                        <PayPalScriptProvider
                          options={{
                            clientId: PAYPAL_CONFIG.clientId,
                            vault: true,
                            intent: 'subscription',
                          }}
                        >
                          <PayPalButtons
                            style={{ layout: 'vertical', color: 'blue', shape: 'rect', label: 'subscribe' }}
                            createSubscription={(_data, actions) => {
                              return actions.subscription.create({
                                plan_id: negotiationResult.agreedPlanId || PAYPAL_CONFIG.planId,
                              });
                            }}
                            onApprove={async (data) => {
                              const subId = data.subscriptionID || `I-PP${Math.floor(100000 + Math.random() * 900000)}`;
                              await handleSubscriptionApproved(subId);
                            }}
                            onError={(err) => {
                              console.warn('[PayPal]: Sandbox interaction warning:', err);
                              setPaypalError('PayPal Sandbox error. Use the Instant Sandbox Simulation button above.');
                            }}
                          />
                        </PayPalScriptProvider>
                      </div>
                    </div>
                  )}

                  {paypalError && (
                    <div style={{ fontSize: '11px', color: '#f87171', marginTop: '6px', textAlign: 'center' }}>
                      {paypalError}
                    </div>
                  )}
                </div>
              )}

              {/* Provisioning Success Confirmation */}
              {provisioningResult && (
                <div
                  style={{
                    backgroundColor: 'rgba(16, 185, 129, 0.15)',
                    border: '1px solid #10b981',
                    borderRadius: '8px',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#34d399', fontWeight: 700 }}>
                    <ShieldCheck size={20} />
                    <span>AP2 Transaction Complete &amp; Worker Node Live!</span>
                  </div>
                  <div style={{ fontSize: '12px', color: '#f8fafc', lineHeight: 1.6 }}>
                    <div>
                      <strong>PayPal Subscription:</strong>{' '}
                      <span style={{ color: '#38bdf8' }}>{provisioningResult.subscriptionId}</span>
                    </div>
                    <div>
                      <strong>Allocated Endpoint:</strong>{' '}
                      <span style={{ color: '#fbbf24' }}>{provisioningResult.allocatedDid}</span>
                    </div>
                    <div>
                      <strong>Execution Node Cluster:</strong> {provisioningResult.carrierRespOrg}
                    </div>
                    <div>
                      <strong>Principal Entity:</strong> {provisioningResult.kycBoundEntity}
                    </div>
                    <div>
                      <strong>Cryptographic Policy Guard:</strong>{' '}
                      <span style={{ color: '#34d399' }}>RFC 8032 ED25519 VERIFIED (ANTI-TAMPER PASS)</span>
                    </div>
                  </div>
                  <button
                    className="btn-simulate"
                    style={{ alignSelf: 'flex-start', marginTop: '8px' }}
                    onClick={() => setIsModalOpen(false)}
                  >
                    View in Operations Deck
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
