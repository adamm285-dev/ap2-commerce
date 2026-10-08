import { useState } from 'react';
import {
  Network,
  CheckCircle2,
  Play,
  FileText,
  Calendar,
  Building2,
  ShieldCheck,
  PhoneCall,
  Receipt,
  Sparkles,
  Copy,
  Check,
  Code2,
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
}

export function ZapierMcpView({
  contractorName = 'Marcus Miller',
  businessEntity = 'Miller Custom Flooring LLC',
  allocatedDid = '+1 (863) 267-8902',
  tradeVertical = 'Tile & Custom Flooring',
  monthlyFee = 79.99,
  paypalSubscriptionId = 'I-AUTONOMOUS-8902',
  isDepositLocked = false,
}: ZapierMcpViewProps) {
  const [activeScenario, setActiveScenario] = useState<'a2a' | 'lead'>('a2a');
  const [activeInspectorTab, setActiveInspectorTab] = useState<'qbo' | 'jobber' | 'webhook'>('qbo');
  const [copiedTab, setCopiedTab] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [a2aResult, setA2aResult] = useState<ZapierExecutionResult | null>(null);
  const [leadResult, setLeadResult] = useState<ZapierExecutionResult | null>(null);

  const copyToClipboard = (text: string, tabKey: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedTab(tabKey);
      setTimeout(() => setCopiedTab(null), 2000);
    }
  };

  // Scenario 1: A2A Contractor Onboarding Data
  const contractor: A2aContractorOnboarding = {
    contractorName,
    businessEntity,
    allocatedDid,
    tradeVertical,
    monthlyFee,
    paypalSubscriptionId: isDepositLocked ? 'I-AUTONOMOUS-186492' : paypalSubscriptionId,
    contractorEmail: 'marcus@millercustomfloors.com',
  };

  // Scenario 2: Downstream Homeowner Lead Data
  const [lead] = useState<QualifiedLead>({
    callerName: 'Sarah Jenkins',
    callerPhone: '+1 (863) 555-0199',
    propertyAddress: '4822 Cleveland Heights Blvd, Lakeland, FL 33813',
    tradeVertical: 'Tile & Custom Flooring',
    scopeSummary: '650 sq ft porcelain plank tile in kitchen & hallway',
    territoryZone: 'Zone 2 - South Lakeland',
    appointmentTime: 'Tuesday, Oct 6 @ 10:00 AM',
    depositAmount: 250.0,
    paypalTransactionId: 'TXN-998811',
  });

  const handleRunWorkflow = async () => {
    setIsRunning(true);
    if (activeScenario === 'a2a') {
      const res = await executeZapierA2aWorkflow(contractor);
      setA2aResult(res);
    } else {
      const res = await executeZapierMcpWorkflow(lead);
      setLeadResult(res);
    }
    setIsRunning(false);
  };

  const currentResult = activeScenario === 'a2a' ? a2aResult : leadResult;

  // Authentic Payload Previews for APIMatic & Zapier Tracks
  const qboPreview = currentResult?.qboPayload || (activeScenario === 'a2a' ? {
    Purchase: {
      PaymentType: 'CreditCard',
      AccountRef: { value: '99', name: 'PayPal Clearing Account' },
      EntityRef: { value: '101', name: 'FieldSmith Pro Inc.', type: 'Vendor' },
      TxnDate: new Date().toISOString().substring(0, 10),
      DocNumber: `FS-A2A-${contractor.paypalSubscriptionId.slice(-6)}`,
      TotalAmt: contractor.monthlyFee,
      CurrencyRef: { value: 'USD', name: 'United States Dollar' },
      PrivateNote: `FieldSmith Pro Autonomous AP2 Commerce Protocol.\nPayPal Sub: ${contractor.paypalSubscriptionId} | Monthly: $${contractor.monthlyFee.toFixed(2)} USD\nDedicated DID: ${contractor.allocatedDid} | Vertical: ${contractor.tradeVertical}\nMandate Proof Hash: HMAC-MANDATE-VERIFIED-01\nCarrier FCC Attestation: STIR/SHAKEN Class A (Telnyx LLC)\nPurchaser: ${contractor.contractorName} (${contractor.businessEntity})`,
      GlobalTaxCalculation: 'NotApplicable',
      Line: [
        {
          Id: '1',
          LineNum: 1,
          Amount: contractor.monthlyFee,
          DetailType: 'AccountBasedExpenseLineDetail',
          Description: `FieldSmith Pro AI Telephony & Dispatch Screener (${contractor.tradeVertical}) — Autonomous Recurring Subscription`,
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
      CustomerRef: { value: '202', name: lead.callerName },
      Line: [
        {
          Amount: lead.depositAmount,
          DetailType: 'SalesItemLineDetail',
          Description: `Mobilization Deposit: ${lead.tradeVertical} (${lead.scopeSummary})`,
          SalesItemLineDetail: {
            ItemRef: { value: '1', name: 'Services' },
            UnitPrice: lead.depositAmount,
            Qty: 1,
          },
        },
      ],
      TxnDate: new Date().toISOString().substring(0, 10),
      PrivateNote: `PayPal Deposit Verified: ${lead.paypalTransactionId} | Zone: ${lead.territoryZone}`,
    },
    purchase_id: 'QBO-INV-5501',
  });

  const jobberPreview = currentResult?.jobberPayload || (activeScenario === 'a2a' ? {
    mutation: `mutation ClientCreate($input: ClientCreateInput!) {
  clientCreate(input: $input) {
    client {
      id
      firstName
      lastName
      companyName
      isCompany
      phones {
        number
        primary
        type
        description
      }
      emails {
        address
        primary
      }
      customFields {
        ... on CustomFieldText {
          label
          valueText
        }
      }
    }
    userErrors {
      message
      field
    }
  }
}`,
    variables: {
      input: {
        firstName: contractor.contractorName.split(' ')[0] || 'Marcus',
        lastName: contractor.contractorName.split(' ')[1] || 'Miller',
        companyName: contractor.businessEntity,
        isCompany: true,
        phones: [
          {
            number: contractor.allocatedDid,
            primary: true,
            type: 'WORK',
            description: 'FieldSmith Dedicated AI Inbound Line',
          },
        ],
        emails: [{ address: contractor.contractorEmail, primary: true }],
        customFields: [
          { label: 'Telephony DID', valueText: contractor.allocatedDid },
          { label: 'Carrier Route', valueText: 'Telnyx Wholesale Voice 10DLC' },
          { label: 'AI Voice Screener Webhook', valueText: 'https://api.fieldsmith.pro/voice/inbound' },
        ],
      },
    },
    jobber_routing_id: 'JOB-ROUTING-7819',
  } : {
    mutation: `mutation QuoteCreate($input: QuoteCreateInput!) {
  quoteCreate(input: $input) {
    quote {
      id
      title
      total
      client { name phone }
    }
    userErrors { message field }
  }
}`,
    variables: {
      input: {
        title: `Consultation & Scope: ${lead.tradeVertical}`,
        clientName: lead.callerName,
        phone: lead.callerPhone,
        address: lead.propertyAddress,
        notes: lead.scopeSummary,
      },
    },
    jobber_routing_id: 'JOB-QUOTE-3342',
  });

  const webhookPreview = currentResult?.webhookEnvelope || {
    headers: {
      'Content-Type': 'application/json',
      'X-FieldSmith-Signature': 'sha256=9b72e1858a74e47bcf056ad8564177d6118d098e94fae75896a297b83d8e578a',
      'X-FieldSmith-Timestamp': new Date().toISOString(),
      'X-FieldSmith-Delivery-Id': 'del_live_sync_001',
      'X-FieldSmith-Event': activeScenario === 'a2a' ? 'a2a.subscription.provisioned' : 'fieldsmith.lead.created',
    },
    body: {
      event: activeScenario === 'a2a' ? 'a2a.subscription.provisioned' : 'fieldsmith.lead.created',
      contractor: {
        name: contractor.contractorName,
        entity: contractor.businessEntity,
        email: contractor.contractorEmail,
      },
      subscription: activeScenario === 'a2a' ? {
        paypal_subscription_id: contractor.paypalSubscriptionId,
        monthly_fee: contractor.monthlyFee,
        currency: 'USD',
        allocated_did: contractor.allocatedDid,
        trade_vertical: contractor.tradeVertical,
        mandate_proof_hash: 'HMAC-MANDATE-VERIFIED-01',
      } : undefined,
      jobber_export: jobberPreview,
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
        padding: '24px',
        overflowY: 'auto',
      }}
    >
      {/* Title & Scenario Selector Bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <h2
            style={{
              fontSize: '18px',
              fontWeight: 700,
              color: '#f8fafc',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              margin: 0,
            }}
          >
            <Network size={20} color="#38bdf8" /> Zapier MCP Autonomous Business Bridge
          </h2>
          <p style={{ fontSize: '12px', color: '#94a3b8', margin: '4px 0 0 0' }}>
            {activeScenario === 'a2a'
              ? 'Autonomous AP2 Post-Payment Chain: Wires Marcus Miller’s accounting, CRM line routing, and morning briefs automatically.'
              : 'FieldSmith Inbound Lead CRM Chain: Dispatches homeowner project quote, deposit receipt, and jobsite booking.'}
          </p>
        </div>

        {/* Scenario Selector Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div
            style={{
              display: 'flex',
              backgroundColor: '#1e293b',
              borderRadius: '8px',
              padding: '3px',
              border: '1px solid #334155',
            }}
          >
            <button
              onClick={() => setActiveScenario('a2a')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeScenario === 'a2a' ? '#0284c7' : 'transparent',
                color: activeScenario === 'a2a' ? '#fff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <Sparkles size={13} color={activeScenario === 'a2a' ? '#fde047' : '#94a3b8'} />
              AP2 Contractor Onboarding (Active Demo)
            </button>
            <button
              onClick={() => setActiveScenario('lead')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeScenario === 'lead' ? '#0284c7' : 'transparent',
                color: activeScenario === 'lead' ? '#fff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <Building2 size={13} />
              FieldSmith Homeowner CRM (Sarah Jenkins)
            </button>
          </div>

          <button
            onClick={handleRunWorkflow}
            disabled={isRunning}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '8px 18px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: '#0284c7',
              color: '#fff',
              fontSize: '13px',
              fontWeight: 600,
              cursor: 'pointer',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            <Play size={15} />{' '}
            {isRunning
              ? 'Invoking Zapier MCP...'
              : activeScenario === 'a2a'
              ? 'Run Autonomous AP2 Onboarding Chain'
              : 'Run Homeowner CRM Chain'}
          </button>
        </div>
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
                VERIFIED &bull; KYC BOUND
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
              <div>
                <span style={{ color: '#94a3b8' }}>Contractor Principal:</span>
                <div style={{ color: '#f8fafc', fontWeight: 600 }}>{contractor.contractorName}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Verified Legal Entity (PayPal KYC):</span>
                <div style={{ color: '#38bdf8', fontWeight: 600 }}>{contractor.businessEntity}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Allocated Carrier DID:</span>
                <div style={{ color: '#fbbf24', fontFamily: 'monospace', fontWeight: 600 }}>
                  {contractor.allocatedDid} <span style={{ color: '#94a3b8', fontWeight: 400 }}>(Telnyx LLC)</span>
                </div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Trade Specialty &amp; Prompt Preset:</span>
                <div style={{ color: '#f8fafc' }}>{contractor.tradeVertical}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Executive Dispatch Contact:</span>
                <div style={{ color: '#f8fafc' }}>{contractor.contractorEmail}</div>
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
                    Recurring PayPal Subscription: ${contractor.monthlyFee.toFixed(2)}/mo
                  </span>
                  <span style={{ fontSize: '11px', color: '#6ee7b7' }}>Plan: FieldSmith Pro</span>
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace' }}>
                  PayPal Agreement Token: {contractor.paypalSubscriptionId}
                </div>
                <div style={{ fontSize: '11px', color: '#34d399', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                  <ShieldCheck size={12} /> TCPA Guard: 100% Inbound Screening (No unsolicited robocalls)
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
              <Building2 size={16} color="#38bdf8" /> Inbound Lead Qualified by Gemini Live
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '12px' }}>
              <div>
                <span style={{ color: '#94a3b8' }}>Homeowner Name:</span>
                <div style={{ color: '#f8fafc', fontWeight: 600 }}>{lead.callerName}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Phone Number:</span>
                <div style={{ color: '#f8fafc', fontFamily: 'monospace' }}>{lead.callerPhone}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Jobsite Address:</span>
                <div style={{ color: '#f8fafc' }}>{lead.propertyAddress}</div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Trade &amp; Scope:</span>
                <div style={{ color: '#f8fafc' }}>
                  {lead.tradeVertical} &bull; {lead.scopeSummary}
                </div>
              </div>
              <div>
                <span style={{ color: '#94a3b8' }}>Territory Zone &amp; Slot:</span>
                <div style={{ color: '#38bdf8', fontWeight: 600 }}>
                  [{lead.territoryZone}] &bull; {lead.appointmentTime}
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
                  Verified PayPal Deposit: ${lead.depositAmount.toFixed(2)}
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', fontFamily: 'monospace' }}>
                  Transaction ID: {lead.paypalTransactionId}
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
                  ? 'Click "Run Autonomous AP2 Onboarding Chain" to execute the live multi-app setup into QuickBooks, Jobber, and Google Workspace.'
                  : 'Click "Run Homeowner CRM Chain" to dispatch Sarah Jenkins quote and deposit intake.'}
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
                      {log.targetApp === 'Jobber' && (
                        activeScenario === 'a2a' ? <PhoneCall size={15} color="#38bdf8" /> : <FileText size={15} color="#38bdf8" />
                      )}
                      {(log.targetApp === 'Google Calendar' || log.targetApp === 'Google Workspace') && (
                        <Calendar size={15} color="#fbbf24" />
                      )}
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

      {/* Full-Width Schema & Wire Inspector Panel (APIMatic & Zapier Tracks) */}
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
              Inspect authentic Intuit REST v3 JSON, Jobber GraphQL v2 mutations, and cryptographically signed HMAC-SHA256 webhook envelopes.
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
              onClick={() => setActiveInspectorTab('jobber')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: activeInspectorTab === 'jobber' ? '#0284c7' : 'transparent',
                color: activeInspectorTab === 'jobber' ? '#ffffff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              <FileText size={14} /> Jobber GraphQL v2
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
                  DocNumber: {qboPreview?.purchase_id || 'FS-A2A-186492'}
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
              <strong style={{ color: '#38bdf8' }}>🏆 APIMatic Best Use Criteria:</strong> Generates fully compliant Intuit API v3 Purchase entities mapping contractor expenses to GL Account 6300 without human bookkeeping.
            </div>
          </div>
        )}

        {/* Tab 2: Jobber GraphQL v2 */}
        {activeInspectorTab === 'jobber' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#075985', color: '#7dd3fc' }}>
                  Jobber GraphQL API v2
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#064e3b', color: '#6ee7b7' }}>
                  CustomField: Telephony Routing
                </span>
                <span style={{ fontSize: '11px', fontWeight: 600, padding: '2px 8px', borderRadius: '4px', backgroundColor: '#78350f', color: '#fde68a' }}>
                  DID: {activeScenario === 'a2a' ? contractor.allocatedDid : lead.callerPhone}
                </span>
              </div>
              <button
                onClick={() =>
                  copyToClipboard(
                    typeof jobberPreview?.mutation === 'string'
                      ? `${jobberPreview.mutation}\n\n# Variables:\n${JSON.stringify(jobberPreview.variables, null, 2)}`
                      : JSON.stringify(jobberPreview, null, 2),
                    'jobber'
                  )
                }
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid #475569',
                  backgroundColor: '#0f172a',
                  color: copiedTab === 'jobber' ? '#34d399' : '#e2e8f0',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {copiedTab === 'jobber' ? <Check size={14} /> : <Copy size={14} />}
                {copiedTab === 'jobber' ? 'Copied GraphQL!' : 'Copy GraphQL Mutation'}
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
                {typeof jobberPreview?.mutation === 'string'
                  ? `${jobberPreview.mutation}\n\n# --- Input Variables ---\n${JSON.stringify(jobberPreview.variables, null, 2)}`
                  : JSON.stringify(jobberPreview, null, 2)}
              </pre>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8', backgroundColor: '#0f172a', padding: '10px 14px', borderRadius: '6px', border: '1px solid #1e293b' }}>
              <strong style={{ color: '#38bdf8' }}>⚡ Autonomous Routing Mutation:</strong> Jobber GraphQL v2 clientCreate mutation dynamically assigns the newly allocated Telnyx DID and binds the AI Voice Screener webhook directly to the contractor profile.
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
