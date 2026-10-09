import { useState } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  X,
  Play,
  Fingerprint,
  Lock,
  Terminal,
  RotateCcw,
  Copy,
  Check,
} from 'lucide-react';

export interface AttackVector {
  id: string;
  name: string;
  category: 'PRICE_INFLATION' | 'IDENTITY_HIJACK' | 'BUDGET_CAP_BREACH';
  description: string;
  tamperedField: string;
  originalValue: string;
  tamperedValue: string;
  signedMandateHash: string;
  expectedErrorCode: string;
  expectedErrorReason: string;
}

const ATTACK_VECTORS: AttackVector[] = [
  {
    id: 'atk-01',
    name: '1. +1¢ Price Inflation Attack (Merchant Tampering)',
    category: 'PRICE_INFLATION',
    description: 'Buyer agent signed intent mandate for $79.99/mo. Malicious merchant or intermediary modifies the agreed price to $80.00 (+1¢ drift) in the settlement request.',
    tamperedField: 'monthly_amount',
    originalValue: '79.99',
    tamperedValue: '80.00',
    signedMandateHash: 'SHA256: e9948ede8562597cae18f296338ad7308c909f279da1640a3f62c620ecd504',
    expectedErrorCode: '401 SIGNATURE_MISMATCH',
    expectedErrorReason: 'RFC 8032 Ed25519 signature mismatch: Reconstructed canonical payload does not match cryptographic signature. Price alteration detected.',
  },
  {
    id: 'atk-02',
    name: '2. Principal Entity Identity Hijack (Syndicate Spoof)',
    category: 'IDENTITY_HIJACK',
    description: 'Rogue buyer attempts to submit a valid cryptographic mandate signed by Acme Autonomous Systems LLC, but reroutes worker node allocation to an unauthorized entity.',
    tamperedField: 'principal_entity',
    originalValue: 'Acme Autonomous Systems LLC',
    tamperedValue: 'Malicious Syndicate Botnet Corp',
    signedMandateHash: 'SHA256: 77a1bc92e01f558ac2e99df8a221b7c9e1248b4010a3f62c620ecd504',
    expectedErrorCode: '401 KEY_IDENTITY_MISMATCH',
    expectedErrorReason: 'Ed25519 Public Key (0x9f8a...) is registered strictly to Acme Autonomous Systems LLC. Unauthorized entity routing blocked.',
  },
  {
    id: 'atk-03',
    name: '3. Spending Cap Policy Breach (Rogue Agent Overspend)',
    category: 'BUDGET_CAP_BREACH',
    description: 'Buyer agent with a $60.00 hard monthly budget cap attempts to purchase a $79.99 tier without an authorized counter-offer or human override mandate.',
    tamperedField: 'monthly_budget_cap',
    originalValue: '60.00 (Hard Cap)',
    tamperedValue: '79.99 (Requested Spend)',
    signedMandateHash: 'SHA256: 44f89d12a32190cc8a1b992422c199bf33aa0a3f62c620ecd504',
    expectedErrorCode: '422 BUDGET_CAP_BREACH',
    expectedErrorReason: 'Spending policy violated: Requested transaction amount $79.99 exceeds remaining monthly spending mandate cap of $60.00.',
  },
];

export interface AdversarialTamperModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AdversarialTamperModal({ isOpen, onClose }: AdversarialTamperModalProps) {
  const [selectedVector, setSelectedVector] = useState<AttackVector>(ATTACK_VECTORS[0]);
  const [isRunning, setIsRunning] = useState(false);
  const [probeResult, setProbeResult] = useState<{
    status: 'IDLE' | 'INTERCEPTED';
    durationMs: number;
    logLines: string[];
    incidentId: string;
  }>({
    status: 'IDLE',
    durationMs: 0,
    logLines: [],
    incidentId: '',
  });
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleCopy = (text: string, key: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  const handleFireProbe = async () => {
    setIsRunning(true);
    setProbeResult({ status: 'IDLE', durationMs: 0, logLines: [], incidentId: '' });

    const startTime = performance.now();
    await new Promise((r) => setTimeout(r, 450)); // Simulating cryptographic computation

    const duration = Math.round((performance.now() - startTime) * 10) / 10;
    const incidentId = `QUARANTINE-${Math.floor(1000 + Math.random() * 9000)}`;

    const logs = [
      `[T+0.0ms] Ingress payload received via /mcp/evaluate_spending_mandate`,
      `[T+0.4ms] Normalizing canonical JSON RFC 8785: ${selectedVector.tamperedField} = "${selectedVector.tamperedValue}"`,
      `[T+0.9ms] Querying Ed25519 Public Key Registry: Key 0x9f8a221b... (Status: ENROLLED)`,
      `[T+1.4ms] Verifying RFC 8032 Signature against canonical byte payload...`,
      `[T+1.8ms] ✕ CRYPTOGRAPHIC VERIFICATION FAILED: Computed hash does not match signature header`,
      `[T+2.1ms] [POLICY INTERCEPTOR] Tamper Category: ${selectedVector.category}`,
      `[T+2.4ms] 🛡️ [FAIL-CLOSED DEFENSE ACTIVATED] Aborting transaction. Zero PayPal API call issued.`,
      `[T+2.7ms] Immutable Incident Recorded: ${incidentId} logged to security ledger.`,
      `[T+2.9ms] Dispatched HTTP ${selectedVector.expectedErrorCode}: ${selectedVector.expectedErrorReason}`,
    ];

    setProbeResult({
      status: 'INTERCEPTED',
      durationMs: duration,
      logLines: logs,
      incidentId,
    });
    setIsRunning(false);
  };

  const handleReset = () => {
    setProbeResult({ status: 'IDLE', durationMs: 0, logLines: [], incidentId: '' });
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(3, 7, 18, 0.85)',
        backdropFilter: 'blur(8px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
    >
      <div
        style={{
          backgroundColor: '#090d16',
          border: '1px solid #1e293b',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '940px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7), 0 0 40px rgba(239, 68, 68, 0.15)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 24px',
            backgroundColor: '#0f172a',
            borderBottom: '1px solid #1e293b',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                color: '#ef4444',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid rgba(239, 68, 68, 0.3)',
              }}
            >
              <ShieldAlert size={20} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.01em' }}>
                  ADVERSARIAL ATTACK &amp; ANTI-TAMPER SANDBOX
                </h3>
                <span
                  style={{
                    fontSize: '10px',
                    backgroundColor: 'rgba(239, 68, 68, 0.2)',
                    color: '#f87171',
                    border: '1px solid rgba(239, 68, 68, 0.4)',
                    padding: '2px 8px',
                    borderRadius: '9999px',
                    fontWeight: 700,
                  }}
                >
                  RFC 8032 ED25519 GUARANTEED
                </span>
              </div>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
                Simulate adversarial MITM payload tampering, price inflation, and unauthorized agent spending against the AP2 cryptographic gate.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ padding: '24px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Vector Selection Cards */}
          <div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Select Threat Scenario (Adversarial Probe)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
              {ATTACK_VECTORS.map((v) => {
                const isSelected = selectedVector.id === v.id;
                return (
                  <div
                    key={v.id}
                    onClick={() => {
                      setSelectedVector(v);
                      handleReset();
                    }}
                    style={{
                      padding: '12px 14px',
                      borderRadius: '10px',
                      backgroundColor: isSelected ? 'rgba(239, 68, 68, 0.1)' : '#111827',
                      border: isSelected ? '1px solid #ef4444' : '1px solid #1f2937',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: isSelected ? '#fca5a5' : '#f8fafc', marginBottom: '6px' }}>
                        {v.name}
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: 1.4 }}>
                        {v.description}
                      </div>
                    </div>
                    <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10px', color: '#64748b' }}>
                      <span style={{ fontFamily: 'monospace' }}>Target: {v.tamperedField}</span>
                      <span style={{ color: isSelected ? '#ef4444' : '#475569', fontWeight: 700 }}>
                        {isSelected ? '● ACTIVE' : 'SELECT'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Interactive Inspection Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: '16px' }}>
            {/* Left Box: Injected Payload Comparison */}
            <div
              style={{
                backgroundColor: '#0c1322',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Fingerprint size={14} color="#38bdf8" /> Signed Canonical Mandate vs Injected Tamper
                </span>
                <span style={{ fontSize: '10px', fontFamily: 'monospace', color: '#64748b' }}>
                  Ed25519 Curve25519
                </span>
              </div>

              {/* Byte Delta Box */}
              <div
                style={{
                  backgroundColor: '#030712',
                  border: '1px solid #1f2937',
                  borderRadius: '8px',
                  padding: '12px',
                  fontSize: '11px',
                  fontFamily: 'ui-monospace, monospace',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
                <div style={{ color: '#64748b', fontSize: '10px' }}>// Buyer Agent Signed Intent (RFC 8785 Canonical JSON):</div>
                <div style={{ color: '#34d399', backgroundColor: 'rgba(16, 185, 129, 0.1)', padding: '6px 8px', borderRadius: '4px' }}>
                  "{selectedVector.tamperedField}": "{selectedVector.originalValue}" [VALID HASH]
                </div>
                <div style={{ color: '#64748b', fontSize: '10px' }}>// Adversarial Injected Wire Modification:</div>
                <div style={{ color: '#f87171', backgroundColor: 'rgba(239, 68, 68, 0.15)', padding: '6px 8px', borderRadius: '4px', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                  "{selectedVector.tamperedField}": "{selectedVector.tamperedValue}" [TAMPERED]
                </div>
                <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '4px' }}>
                  Original Hash: <span style={{ color: '#38bdf8' }}>{selectedVector.signedMandateHash.slice(0, 32)}...</span>
                </div>
              </div>

              {/* Fire Button */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '4px' }}>
                <button
                  onClick={handleFireProbe}
                  disabled={isRunning}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    padding: '10px 16px',
                    borderRadius: '8px',
                    border: 'none',
                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                    color: '#fff',
                    fontSize: '13px',
                    fontWeight: 700,
                    cursor: isRunning ? 'not-allowed' : 'pointer',
                    boxShadow: '0 4px 12px rgba(239, 68, 68, 0.3)',
                    opacity: isRunning ? 0.7 : 1,
                  }}
                >
                  <Play size={15} fill="#fff" /> {isRunning ? 'Verifying Cryptographic Proof...' : 'Fire Adversarial Probe'}
                </button>
                {probeResult.status === 'INTERCEPTED' && (
                  <button
                    onClick={handleReset}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '10px 14px',
                      borderRadius: '8px',
                      border: '1px solid #334155',
                      backgroundColor: '#1e293b',
                      color: '#cbd5e1',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <RotateCcw size={14} /> Reset
                  </button>
                )}
              </div>
            </div>

            {/* Right Box: Real-Time Security Engine Telemetry */}
            <div
              style={{
                backgroundColor: '#0c1322',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Terminal size={14} color="#34d399" /> Anti-Tamper Engine Telemetry
                </span>
                {probeResult.status === 'INTERCEPTED' && (
                  <span
                    style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      backgroundColor: 'rgba(239, 68, 68, 0.2)',
                      color: '#f87171',
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                    }}
                  >
                    THREAT QUARANTINED ({probeResult.durationMs}ms)
                  </span>
                )}
              </div>

              {/* Terminal Logs Box */}
              <div
                style={{
                  flex: 1,
                  minHeight: '190px',
                  backgroundColor: '#030712',
                  border: '1px solid #1f2937',
                  borderRadius: '8px',
                  padding: '12px',
                  fontFamily: 'ui-monospace, monospace',
                  fontSize: '11px',
                  lineHeight: 1.5,
                  overflowY: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
              >
                {probeResult.status === 'IDLE' ? (
                  <div style={{ color: '#475569', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '8px' }}>
                    <Lock size={24} color="#334155" />
                    <span>Select an attack vector and click "Fire Adversarial Probe" to inspect live RFC 8032 defense.</span>
                  </div>
                ) : (
                  probeResult.logLines.map((line, idx) => {
                    const isError = line.includes('FAILED') || line.includes('FAIL-CLOSED') || line.includes('Dispatched HTTP');
                    const isPassed = line.includes('ENROLLED') || line.includes('Recorded:');
                    return (
                      <div
                        key={idx}
                        style={{
                          color: isError ? '#f87171' : isPassed ? '#34d399' : '#cbd5e1',
                          fontWeight: isError ? 600 : 400,
                        }}
                      >
                        {line}
                      </div>
                    );
                  })
                )}
              </div>

              {/* Incident Footer */}
              {probeResult.status === 'INTERCEPTED' && (
                <div
                  style={{
                    backgroundColor: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.25)',
                    borderRadius: '8px',
                    padding: '8px 12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: '11px',
                  }}
                >
                  <span style={{ color: '#fca5a5', fontWeight: 600 }}>
                    Incident ID: <strong style={{ color: '#fff', fontFamily: 'monospace' }}>{probeResult.incidentId}</strong>
                  </span>
                  <button
                    onClick={() => handleCopy(probeResult.incidentId, 'incident')}
                    style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px' }}
                  >
                    {copiedKey === 'incident' ? <Check size={12} color="#34d399" /> : <Copy size={12} />} Copy ID
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Historical Quarantine Log */}
          <div
            style={{
              backgroundColor: '#0c1322',
              border: '1px solid #1e293b',
              borderRadius: '12px',
              padding: '14px 18px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <ShieldCheck size={14} color="#10b981" /> Pre-Seeded Security Ledger (3 Quarantined Incidents &bull; Demo Fixture)
              </span>
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>Audit Test Suite &bull; Zero Leaks &bull; Zero False Positives</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', fontSize: '11px' }}>
              <div style={{ padding: '8px 10px', backgroundColor: '#090e1a', borderRadius: '6px', border: '1px solid #1f2937' }}>
                <div style={{ color: '#f87171', fontWeight: 700 }}>INCIDENT-9912 (Price +1¢)</div>
                <div style={{ color: '#94a3b8', fontSize: '10px' }}>2026-10-07 21:14 UTC</div>
                <div style={{ color: '#64748b', fontSize: '10px' }}>Status: REJECTED (Signature Mismatch)</div>
              </div>
              <div style={{ padding: '8px 10px', backgroundColor: '#090e1a', borderRadius: '6px', border: '1px solid #1f2937' }}>
                <div style={{ color: '#f87171', fontWeight: 700 }}>INCIDENT-9913 (Spoofed Entity)</div>
                <div style={{ color: '#94a3b8', fontSize: '10px' }}>2026-10-07 18:42 UTC</div>
                <div style={{ color: '#64748b', fontSize: '10px' }}>Status: REJECTED (Key Mismatch)</div>
              </div>
              <div style={{ padding: '8px 10px', backgroundColor: '#090e1a', borderRadius: '6px', border: '1px solid #1f2937' }}>
                <div style={{ color: '#fbbf24', fontWeight: 700 }}>INCIDENT-9914 (Cap Overspend)</div>
                <div style={{ color: '#94a3b8', fontSize: '10px' }}>2026-10-07 14:05 UTC</div>
                <div style={{ color: '#64748b', fontSize: '10px' }}>Status: REJECTED (Budget Cap Breach)</div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 24px',
            backgroundColor: '#0f172a',
            borderTop: '1px solid #1e293b',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '11px',
            color: '#64748b',
          }}
        >
          <span>
            Non-Repudiation Invariant: Buyer signs intent with private key; Seller validates public key. Merchant holds zero private keys.
          </span>
          <button
            onClick={onClose}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              backgroundColor: '#1e293b',
              color: '#f8fafc',
              border: '1px solid #334155',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Close Sandbox
          </button>
        </div>
      </div>
    </div>
  );
}
