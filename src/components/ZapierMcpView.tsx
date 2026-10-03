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
  const [isRunning, setIsRunning] = useState(false);
  const [a2aResult, setA2aResult] = useState<ZapierExecutionResult | null>(null);
  const [leadResult, setLeadResult] = useState<ZapierExecutionResult | null>(null);

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
              ? 'Autonomous A2A Post-Payment Chain: Wires Marcus Miller’s accounting, CRM line routing, and morning briefs automatically.'
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
              A2A Contractor Onboarding (Active Demo)
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
              ? 'Run Autonomous A2A Onboarding Chain'
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
                <ShieldCheck size={16} color="#34d399" /> Autonomous A2A Subscriber State
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
                  ? 'Click "Run Autonomous A2A Onboarding Chain" to execute the live multi-app setup into QuickBooks, Jobber, and Google Workspace.'
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
    </div>
  );
}

export default ZapierMcpView;
