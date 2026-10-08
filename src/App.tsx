import { useState, useMemo, useCallback, useEffect } from 'react';
import { AgStudioLicenseManager } from 'ag-studio';
import type { AgDataSourcesDefinition, AgStudioMode } from 'ag-studio';
import { PayPalScriptProvider, PayPalButtons } from '@paypal/react-paypal-js';
import {
  ShieldCheck,
  Zap,
  PhoneCall,
  Sliders,
  X,
  Lock,
  LayoutGrid,
  Calendar,
  Network,
  Bot,
} from 'lucide-react';
import {
  initialA2aTransactions,
  tradeImpactData,
  kycAuditData,
  telecomTrunkData,
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
import { ContractorCopilotView } from './components/ContractorCopilotView';
import { EnterpriseFleetLedger } from './components/EnterpriseFleetLedger';
import './App.css';

// 1. Initialize AG Studio License if supplied via environment
const studioLicenseKey = import.meta.env.VITE_AG_STUDIO_LICENSE_KEY;
if (studioLicenseKey) {
  AgStudioLicenseManager.setLicenseKey(studioLicenseKey);
  console.log('[AG Studio]: License key registered.');
} else {
  console.log('[AG Studio]: Running in local developer trial mode.');
}

export function App() {
  const [activeTab, setActiveTab] = useState<'copilot' | 'ag-studio' | 'bryntum' | 'zapier'>('copilot');
  const [mode, setMode] = useState<AgStudioMode>('view');
  const [transactions, setTransactions] = useState<A2aTransaction[]>(initialA2aTransactions);
  const [isMarcusDepositLocked, setIsMarcusDepositLocked] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isNegotiating, setIsNegotiating] = useState(false);
  const [negotiationResult, setNegotiationResult] = useState<AgentNegotiationResponse | null>(null);
  const [provisioningResult, setProvisioningResult] = useState<ProvisioningResult | null>(null);
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [paypalError, setPaypalError] = useState<string | null>(null);

  // Form state for Buyer Agent simulation
  const [contractorName, setContractorName] = useState('Marcus Miller');
  const [businessEntity, setBusinessEntity] = useState('Miller Custom Flooring LLC');
  const [tradeVertical, setTradeVertical] = useState('Tile & Flooring');
  const [maxMonthlyBudget, setMaxMonthlyBudget] = useState(100.0);
  const [operatingMarket, setOperatingMarket] = useState('Lakeland / Polk County, FL (863)');
  const [preferredAreaCode, setPreferredAreaCode] = useState('863');

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
            { id: 'contractor_name', name: 'Contractor', format: 'textFormat' },
            { id: 'trade_vertical', name: 'Trade Vertical', format: 'textFormat' },
            { id: 'service_plan', name: 'Service Plan', format: 'textFormat' },
            { id: 'monthly_amount', name: 'Monthly Fee', format: 'currencyFormat' },
            { id: 'paypal_sub_id', name: 'PayPal Sub ID', format: 'textFormat' },
            { id: 'kyc_status', name: 'KYC Status', format: 'textFormat' },
            { id: 'kyc_legal_entity', name: 'Verified Legal Entity', format: 'textFormat' },
            { id: 'allocated_did', name: 'Allocated DID Phone', format: 'textFormat' },
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
            { id: 'annualized_gmv', name: 'Autonomous Agentic GMV ($ ARR)', format: 'currencyFormat' },
            { id: 'recovered_revenue', name: 'Autonomous Agentic GMV ($ ARR)', format: 'currencyFormat' },
            { id: 'leads_captured', name: 'Booked Leads Intake', format: 'integerFormat' },
            { id: 'missed_calls_prevented', name: 'Robocalls Filtered', format: 'integerFormat' },
            { id: 'subscription_cost', name: 'PayPal Cost ($79.99/mo)', format: 'currencyFormat' },
            { id: 'roi_multiple', name: 'AP2 Settlement Multiplier (x)', format: 'decimalFormat' },
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
        {
          id: 'telecom_trunks',
          data: telecomTrunkData,
          fields: [
            { id: 'allocated_did', name: 'Allocated DID Phone', format: 'textFormat' },
            { id: 'lata', name: 'LATA Market Route', format: 'textFormat' },
            { id: 'market_region', name: 'Market Region', format: 'textFormat' },
            { id: 'tcr_brand', name: 'TCR 10DLC Brand', format: 'textFormat' },
            { id: 'tcr_campaign_id', name: 'TCR Campaign ID', format: 'textFormat' },
            { id: 'monthly_quota_minutes', name: 'Monthly Inbound Quota (Min)', format: 'integerFormat' },
            { id: 'stir_shaken_level', name: 'STIR/SHAKEN Level', format: 'textFormat' },
            { id: 'inbound_routing_mode', name: 'Intake Routing Mode', format: 'textFormat' },
          ],
        },
      ],
    };
  }, [transactions]);

  // Hydrate fleet transactions and verify initial state from SQLite backend with periodic background polling
  useEffect(() => {
    let mounted = true;
    async function loadInitialFleet() {
      const liveTxns = await fetchFleetLedger();
      if (mounted && liveTxns.length > 0) {
        setTransactions(liveTxns);
        const marcus = liveTxns.find((t) => t.contractor_name === 'Marcus Miller');
        if (marcus && marcus.status === 'ACTIVE_STREAMING') {
          setIsMarcusDepositLocked(true);
        }
      }
    }
    loadInitialFleet();

    const intervalId = setInterval(async () => {
      if (!mounted) return;
      const liveTxns = await fetchFleetLedger();
      if (mounted && liveTxns.length > 0) {
        setTransactions((prev) => {
          if (prev.length !== liveTxns.length || liveTxns[0]?.id !== prev[0]?.id || liveTxns[0]?.status !== prev[0]?.status) {
            return liveTxns;
          }
          return prev;
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
      setTransactions(liveTxns);
      const marcus = liveTxns.find((t) => t.contractor_name === 'Marcus Miller');
      if (marcus && marcus.status === 'ACTIVE_STREAMING') {
        setIsMarcusDepositLocked(true);
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
      missedCallLossEstimate: 6200.0,
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
        const result = await executeProvisioningAfterSubscription(
          subId,
          businessEntity,
          tradeVertical,
          preferredAreaCode
        );
        setProvisioningResult(result);

        const agreedMonthlyAmount = negotiationResult?.monthlyFee ?? 79.99;
        const agreedPlanName = negotiationResult?.agreedPlanName ?? `FieldSmith Pro - AI Voice Screener (${tradeVertical})`;

        // Mutate Marcus Miller's existing record in place so the row transitions from PENDING_DEPOSIT -> ACTIVE_STREAMING
        setTransactions((prev) => {
          const idx = prev.findIndex((t) => t.contractor_name === contractorName);
          if (idx !== -1) {
            const updated = [...prev];
            updated[idx] = {
              ...updated[idx],
              timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
              monthly_amount: agreedMonthlyAmount,
              service_plan: agreedPlanName,
              paypal_sub_id: subId,
              kyc_status: 'VERIFIED (PayPal Identity Bound)',
              allocated_did: result.allocatedDid,
              tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
              status: 'ACTIVE_STREAMING',
            };
            return updated;
          }

          // Fallback if not found in list: prepend new entry
          const newTxn: A2aTransaction = {
            id: `TXN-${Math.floor(1000 + Math.random() * 9000)}`,
            timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
            buyer_agent: `AutonomousBuyerAgent-${contractorName.split(' ')[0]}-${tradeVertical.replace(/\s+/g, '')}`,
            contractor_name: contractorName,
            trade_vertical: tradeVertical,
            service_plan: agreedPlanName,
            monthly_amount: agreedMonthlyAmount,
            paypal_sub_id: subId,
            kyc_status: 'VERIFIED (PayPal Identity Bound)',
            kyc_legal_entity: businessEntity,
            allocated_did: result.allocatedDid,
            tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
            status: 'ACTIVE_STREAMING',
          };
          return [newTxn, ...prev];
        });

        // Also lock Marcus Miller's slot in Bryntum Dispatch
        setIsMarcusDepositLocked(true);
      } finally {
        setIsProvisioning(false);
      }
    },
    [contractorName, businessEntity, tradeVertical, preferredAreaCode, negotiationResult]
  );

  return (
    <div className="app-container">
      {/* Executive Header */}
      <header className="app-header">
        {/* Brand Section with Live Fleet Status Badge */}
        <div className="brand-section">
          <div className="brand-icon-wrapper">
            <Zap size={22} />
          </div>
          <div className="brand-titles">
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1>FieldSmith Pro &mdash; Autonomous Agentic Commerce &amp; AP2 Operations Deck</h1>
              <span
                style={{
                  fontSize: '10px',
                  backgroundColor: 'rgba(16, 185, 129, 0.15)',
                  color: '#34d399',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  fontWeight: 700,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }} />
                FLEET M2M: ONLINE
              </span>
            </div>
            <p className="brand-subtitle">
              Enterprise Multi-Trade Telephony &bull; Powered by PayPal Agentic Commerce, Zapier MCP, AG Studio &amp; Bryntum
            </p>
          </div>
        </div>

        {/* View Selection Tabs */}
        <div style={{ display: 'flex', alignItems: 'center', backgroundColor: '#1e293b', borderRadius: '8px', padding: '3px', border: '1px solid #334155' }}>
          <button
            onClick={() => setActiveTab('copilot')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: activeTab === 'copilot' ? '#0284c7' : 'transparent',
              color: activeTab === 'copilot' ? '#fff' : '#94a3b8',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <Bot size={14} /> Contractor Copilot
          </button>
          <button
            onClick={() => setActiveTab('ag-studio')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: activeTab === 'ag-studio' ? '#0284c7' : 'transparent',
              color: activeTab === 'ag-studio' ? '#fff' : '#94a3b8',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <LayoutGrid size={14} /> Fleet Ledger Command Center
          </button>
          <button
            onClick={() => setActiveTab('bryntum')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: activeTab === 'bryntum' ? '#0284c7' : 'transparent',
              color: activeTab === 'bryntum' ? '#fff' : '#94a3b8',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <Calendar size={14} /> Bryntum Telephony Fleet Timeline
          </button>
          <button
            onClick={() => setActiveTab('zapier')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: activeTab === 'zapier' ? '#0284c7' : 'transparent',
              color: activeTab === 'zapier' ? '#fff' : '#94a3b8',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <Network size={14} /> Zapier MCP Bridge
          </button>
        </div>

        <div className="header-actions">
          <button className="btn-simulate" onClick={() => setIsModalOpen(true)}>
            <Sliders size={15} /> Simulate AP2 Purchase
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="studio-canvas-container">
        {activeTab === 'copilot' && (
          <ContractorCopilotView
            contractorName={contractorName}
            businessEntity={businessEntity}
            tradeVertical={tradeVertical}
            areaCode={preferredAreaCode}
            budgetCap={maxMonthlyBudget}
            onNavigateTab={(tab) => setActiveTab(tab)}
            onA2aCompleted={({ subscriptionId, allocatedDid }) => {
              setTransactions((prev) => {
                const idx = prev.findIndex((t) => t.contractor_name === contractorName);
                if (idx !== -1) {
                  const updated = [...prev];
                  const agreedRate = maxMonthlyBudget < 79.99 ? 49.99 : 79.99;
                  const planTitle = agreedRate === 49.99 ? 'FieldSmith Solo Starter (125 Calls/mo)' : 'FieldSmith Pro (450 Calls/mo)';
                  updated[idx] = {
                    ...updated[idx],
                    timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
                    service_plan: planTitle,
                    monthly_amount: agreedRate,
                    paypal_sub_id: subscriptionId,
                    kyc_status: 'VERIFIED (PayPal Identity Bound)',
                    allocated_did: allocatedDid,
                    tcpa_guard: '100% INBOUND ONLY (ZERO ROBOCALLS)',
                    status: 'ACTIVE_STREAMING',
                  };
                  return updated;
                }
                return prev;
              });
              setIsMarcusDepositLocked(true);
            }}
          />
        )}

        {activeTab === 'ag-studio' && (
          <EnterpriseFleetLedger
            transactions={transactions}
            tradeImpactData={tradeImpactData}
            kycAuditData={kycAuditData}
            studioData={studioData}
            studioMode={mode}
            onSetStudioMode={setMode}
            onSimulateClick={() => setIsModalOpen(true)}
            onInspectTrace={() => {
              setActiveTab('copilot');
            }}
            onNavigateTab={(tab) => setActiveTab(tab)}
            onRefreshData={handleRefreshFleet}
          />
        )}

        {activeTab === 'bryntum' && (
          <BryntumDispatchScheduler
            isDepositLocked={isMarcusDepositLocked}
            onToggleDepositLock={(locked) => {
              setIsMarcusDepositLocked(locked);
              setTransactions((prev) => {
                const idx = prev.findIndex((t) => t.contractor_name === 'Marcus Miller');
                if (idx !== -1) {
                  const updated = [...prev];
                  updated[idx] = {
                    ...updated[idx],
                    timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
                    status: locked ? 'ACTIVE_STREAMING' : 'PENDING_DEPOSIT',
                    kyc_status: locked ? 'VERIFIED (PayPal Identity Bound)' : 'PENDING_KYC_VERIFICATION',
                    allocated_did: locked ? '+1 (863) 267-8902' : 'AWAITING_DEPOSIT',
                    tcpa_guard: locked ? '100% INBOUND ONLY (ZERO ROBOCALLS)' : 'PENDING ACTIVATION',
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
            allocatedDid={provisioningResult?.allocatedDid || '+1 (863) 267-8902'}
            tradeVertical={tradeVertical}
            monthlyFee={79.99}
            paypalSubscriptionId={provisioningResult?.subscriptionId || 'I-AUTONOMOUS-8902'}
            isDepositLocked={isMarcusDepositLocked}
          />
        )}
      </main>

      {/* Modal: AP2 Agentic Commerce Negotiation & Subscription Simulator */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-card">
            <div className="modal-header">
              <h3>
                <PhoneCall size={18} /> Autonomous Agentic Commerce Simulator (AP2)
              </h3>
              <button className="btn-close" onClick={() => setIsModalOpen(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="modal-body">
              <p style={{ fontSize: '13px', color: '#94a3b8' }}>
                Simulate how a solo contractor&apos;s <strong>Autonomous Buyer Agent</strong> discovers call leaks,
                checks local spending limits, negotiates with FieldSmith&apos;s Seller MCP Server, and executes a
                recurring PayPal subscription with verified KYC identity.
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
                    Contractor Name
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
                    Legal Business Entity
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
                    Trade Vertical
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
                    <option value="Tile & Flooring">Tile &amp; Custom Flooring</option>
                    <option value="Emergency Plumbing">Emergency 24/7 Plumbing</option>
                    <option value="Roofing & Storm">Roofing &amp; Storm Restoration</option>
                    <option value="Towing & Roadside">Towing &amp; Heavy Roadside</option>
                    <option value="HVAC & Mechanical">HVAC &amp; Mechanical Service</option>
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
                    Service Market (City / State)
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
                    <option value="Lakeland / Polk County, FL (863)">Lakeland / Polk County, FL (863)</option>
                    <option value="Tampa / Hillsborough, FL (813)">Tampa / Hillsborough, FL (813)</option>
                    <option value="Orlando / Orange County, FL (407)">Orlando / Orange County, FL (407)</option>
                    <option value="Miami / South Florida, FL (305)">Miami / South Florida, FL (305)</option>
                    <option value="Jacksonville / Duval, FL (904)">Jacksonville / Duval, FL (904)</option>
                    <option value="Atlanta / Metro, GA (404)">Atlanta / Metro, GA (404)</option>
                    <option value="Dallas / Fort Worth, TX (214)">Dallas / Fort Worth, TX (214)</option>
                    <option value="Houston / Harris, TX (713)">Houston / Harris, TX (713)</option>
                    <option value="Austin / Travis, TX (512)">Austin / Travis, TX (512)</option>
                    <option value="Chicago / Cook County, IL (312)">Chicago / Cook County, IL (312)</option>
                    <option value="Denver / Front Range, CO (303)">Denver / Front Range, CO (303)</option>
                    <option value="Phoenix / Maricopa, AZ (480)">Phoenix / Maricopa, AZ (480)</option>
                    <option value="Custom US Market (Any Area Code)">Custom US Market (Any Area Code)</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                    Dedicated 10DLC Area Code
                  </label>
                  <input
                    type="text"
                    maxLength={3}
                    placeholder="e.g. 863, 404, 214"
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
                    ? 'Evaluating Telemetry & Mandate...'
                    : negotiationResult?.mandateSatisfied
                    ? '✓ 1. Negotiation Approved ($79.99/mo)'
                    : '1. Run AP2 Autonomous Negotiation'}
                </button>
                <button
                  onClick={async () => {
                    const buyerAgentId = `BuyerAgent-${contractorName.split(' ')[0]}-${tradeVertical.replace(/\s+/g, '')}`;
                    await resetMandateLedger(buyerAgentId);
                    setNegotiationResult(null);
                    setProvisioningResult(null);
                    setPaypalError(null);
                    setIsMarcusDepositLocked(false);
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
                  title="Reset spending mandate ledger and restore Marcus Miller to pending status"
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
                      {negotiationResult.isLiveBackend ? '● FastAPI Backend Connected (Port 8001)' : '○ Local Simulation Mode'}
                    </span>
                  </div>
                  <div className="negotiation-line">[BuyerAgent]: Ingesting telephony logs... Missed call loss: $6,200/mo.</div>
                  <div className="negotiation-line">[BuyerAgent]: Querying FieldSmith MCP Catalog: {negotiationResult.sellerMcpEndpoint}</div>
                  <div className="negotiation-line">[SellerMCP]: Quoted Plan: {negotiationResult.agreedPlanName} @ ${negotiationResult.monthlyFee}/mo</div>
                  <div className={`negotiation-line ${negotiationResult.mandateSatisfied ? 'success' : 'warning'}`}>
                    {negotiationResult.message}
                  </div>
                  {negotiationResult.mandateToken && (
                    <div className="negotiation-line success" style={{ wordBreak: 'break-all', fontSize: '11px' }}>
                      [HMAC Token]: {negotiationResult.mandateToken}
                    </div>
                  )}
                  {negotiationResult.mandateSatisfied && (
                    <div className="negotiation-line success">
                      [AP2 Protocol]: Spending mandate approved. Ready for delegated PayPal subscription token.
                    </div>
                  )}
                </div>
              )}

              {/* KYC Telecom Protection Notice */}
              <div className="kyc-verification-box">
                <Lock size={18} color="#34d399" style={{ flexShrink: 0, marginTop: '2px' }} />
                <div className="kyc-details">
                  <h4>Statutory KYC Telecom Anchor (FCC &amp; TCPA Guard)</h4>
                  <p>
                    Unlike anonymous bot services, lines are provisioned strictly via verified PayPal subscriber identity.
                    The provisioned line is locked 100% to inbound screening &mdash; zero autodialers, zero unsolicited outbound robocalls.
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
                      Simulate Approval &amp; Line Provisioning (Sandbox)
                    </h4>
                  </div>
                  <p style={{ fontSize: '11px', color: '#94a3b8', margin: '6px 0 12px 0' }}>
                    Simulates approval for $79.99/month recurring plan. Upon simulated approval, the Seller Agent allocates a simulated Telnyx DID bound to <strong>{businessEntity}</strong> in the sandbox harness.
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
                      'Simulating Line Allocation &amp; Binding KYC...'
                    ) : (
                      <>
                        <ShieldCheck size={16} /> Authorize $79.99/mo (Instant Sandbox Simulation)
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
                                plan_id: PAYPAL_CONFIG.planId,
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
                    <span>AP2 Transaction Complete &amp; Telecom Line Live!</span>
                  </div>
                  <div style={{ fontSize: '12px', color: '#f8fafc', lineHeight: 1.6 }}>
                    <div>
                      <strong>PayPal Subscription:</strong>{' '}
                      <span style={{ color: '#38bdf8' }}>{provisioningResult.subscriptionId}</span>
                    </div>
                    <div>
                      <strong>Allocated DID:</strong>{' '}
                      <span style={{ color: '#fbbf24' }}>{provisioningResult.allocatedDid}</span>
                    </div>
                    <div>
                      <strong>Carrier / RespOrg:</strong> {provisioningResult.carrierRespOrg}
                    </div>
                    <div>
                      <strong>KYC Bound Entity:</strong> {provisioningResult.kycBoundEntity}
                    </div>
                    <div>
                      <strong>TCPA Guard:</strong>{' '}
                      <span style={{ color: '#34d399' }}>100% INBOUND ONLY (ZERO AUTODIALING)</span>
                    </div>
                  </div>
                  <button
                    className="btn-simulate"
                    style={{ alignSelf: 'flex-start', marginTop: '8px' }}
                    onClick={() => setIsModalOpen(false)}
                  >
                    View in Dashboard
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
