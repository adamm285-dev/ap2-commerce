import { useState, useEffect } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  X,
  Play,
  Fingerprint,
  Lock,
  Terminal,
  RotateCcw,
} from 'lucide-react';

export interface AttackVector {
  id: string;
  name: string;
  category: 'PRICE_INFLATION' | 'IDENTITY_HIJACK' | 'BUDGET_CAP_BREACH' | 'UNTAMPERED_CONTROL';
  description: string;
  tamperedField: string;
  originalValue: string | number;
  tamperedValue: string | number;
  applyTamper: (basePayload: Record<string, any>) => Record<string, any>;
}

const ATTACK_VECTORS: AttackVector[] = [
  {
    id: 'atk-01',
    name: '1. +1¢ Price Inflation Attack (Merchant Tampering)',
    category: 'PRICE_INFLATION',
    description: 'Buyer agent signed mandate proof for $79.99/mo. Modifies agreed_price_usd to $80.00 (+1¢ drift) without re-signing.',
    tamperedField: 'agreed_price_usd',
    originalValue: 79.99,
    tamperedValue: 80.00,
    applyTamper: (base) => ({ ...base, agreed_price_usd: 80.00 }),
  },
  {
    id: 'atk-02',
    name: '2. Principal Entity Identity Hijack (Syndicate Spoof)',
    category: 'IDENTITY_HIJACK',
    description: 'Modifies the signed business_name from the authorized buyer entity to an unauthorized entity.',
    tamperedField: 'business_name',
    originalValue: 'Acme Compute Co',
    tamperedValue: 'Demo Attacker Corp',
    applyTamper: (base) => ({ ...base, business_name: 'Demo Attacker Corp' }),
  },
  {
    id: 'atk-03',
    name: '3. Spending Cap Policy Breach (Rogue Agent Overspend)',
    category: 'BUDGET_CAP_BREACH',
    description: 'Lowers monthly_cap_usd to $60.00 while keeping agreed_price_usd at $79.99, violating the budget cap policy check.',
    tamperedField: 'monthly_cap_usd',
    originalValue: 100.00,
    tamperedValue: 60.00,
    applyTamper: (base) => ({ ...base, monthly_cap_usd: 60.00, agreed_price_usd: 79.99 }),
  },
  {
    id: 'ctrl-04',
    name: '4. Untampered Control Payload (Valid Signature & Budget)',
    category: 'UNTAMPERED_CONTROL',
    description: 'Submits the exact canonical payload and signature returned by /api/crypto/sample-proof with zero modifications.',
    tamperedField: 'agreed_price_usd',
    originalValue: 79.99,
    tamperedValue: 79.99,
    applyTamper: (base) => ({ ...base }),
  },
];

export interface AdversarialTamperModalProps {
  isOpen: boolean;
  onClose: () => void;
}

// MOCK(M-014): uses the anti-tamper demo signer and verifier endpoints (/api/crypto/sample-proof, /api/crypto/verify-tamper)
export function AdversarialTamperModal({ isOpen, onClose }: AdversarialTamperModalProps) {
  const [selectedVector, setSelectedVector] = useState<AttackVector>(ATTACK_VECTORS[0]);
  const [sampleProof, setSampleProof] = useState<{
    canonical_payload: Record<string, any>;
    signature: string;
    public_key?: string;
    kid?: string;
    algorithm?: string;
  } | null>(null);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [probeResult, setProbeResult] = useState<{
    status: 'IDLE' | 'INTERCEPTED' | 'ACCEPTED' | 'ERROR';
    durationMs: number;
    statusCode: number | null;
    reason: string | null;
    detail: string | null;
    logLines: string[];
  }>({
    status: 'IDLE',
    durationMs: 0,
    statusCode: null,
    reason: null,
    detail: null,
    logLines: [],
  });

  const loadSampleProof = async () => {
    setSampleError(null);
    try {
      const res = await fetch('/api/crypto/sample-proof?profile=ap2');
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} loading sample proof`);
      }
      const data = await res.json();
      if (!data || !data.canonical_payload || !data.signature) {
        throw new Error('Sample proof response missing canonical_payload or signature');
      }
      setSampleProof(data);
      return data;
    } catch (err: any) {
      const msg = err?.message || 'Failed to contact backend for sample proof';
      setSampleError(msg);
      setSampleProof(null);
      return null;
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadSampleProof();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const runVerificationProbe = async (overrideUntampered = false) => {
    setIsRunning(true);
    setProbeResult({
      status: 'IDLE',
      durationMs: 0,
      statusCode: null,
      reason: null,
      detail: null,
      logLines: [],
    });

    const startTime = performance.now();
    try {
      const currentSample = sampleProof || (await loadSampleProof());
      if (!currentSample || !currentSample.canonical_payload || !currentSample.signature) {
        const elapsed = Math.round((performance.now() - startTime) * 10) / 10;
        const errMsg = sampleError || 'Failed to load sample proof from /api/crypto/sample-proof';
        setProbeResult({
          status: 'ERROR',
          durationMs: elapsed,
          statusCode: null,
          reason: 'REQUEST_FAILED',
          detail: errMsg,
          logLines: [`Error: ${errMsg}`],
        });
        return;
      }

      const payloadToSend = overrideUntampered
        ? { ...currentSample.canonical_payload }
        : selectedVector.applyTamper(currentSample.canonical_payload);

      const res = await fetch('/api/crypto/verify-tamper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          payload: payloadToSend,
          signature: currentSample.signature,
        }),
      });
      const elapsed = Math.round((performance.now() - startTime) * 10) / 10;

      if (!res.ok) {
        setProbeResult({
          status: 'ERROR',
          durationMs: elapsed,
          statusCode: res.status,
          reason: `HTTP_${res.status}`,
          detail: `Request to /api/crypto/verify-tamper failed with HTTP ${res.status}`,
          logLines: [`Request failed: HTTP ${res.status}`],
        });
        return;
      }

      const data = await res.json();
      if (typeof data?.valid !== 'boolean') {
        setProbeResult({
          status: 'ERROR',
          durationMs: elapsed,
          statusCode: null,
          reason: 'INVALID_RESPONSE',
          detail: 'Backend response did not include a boolean "valid" field.',
          logLines: ['Error: Backend response missing "valid" verdict field.'],
        });
        return;
      }

      const isAccepted = data.valid === true;
      const statusCode = typeof data.status_code === 'number' ? data.status_code : null;
      const reason = typeof data.reason === 'string' ? data.reason : null;
      const detail = typeof data.detail === 'string' ? data.detail : null;
      const respPayload = data.payload || payloadToSend;

      const logs: string[] = [
        `POST /api/crypto/verify-tamper (${elapsed}ms RTT)`,
        `verdict: ${isAccepted ? 'ACCEPTED (valid=true)' : 'INTERCEPTED (valid=false)'}`,
        `status_code: ${statusCode !== null ? statusCode : 'not available'}`,
        `reason: ${reason || 'not available'}`,
        `detail: ${detail || 'not available'}`,
        `provided_signature: ${data.provided_signature || currentSample.signature}`,
        `payload.${selectedVector.tamperedField}: ${JSON.stringify(respPayload?.[selectedVector.tamperedField])}`,
      ];

      setProbeResult({
        status: isAccepted ? 'ACCEPTED' : 'INTERCEPTED',
        durationMs: elapsed,
        statusCode,
        reason,
        detail,
        logLines: logs,
      });
    } catch (err: any) {
      const elapsed = Math.round((performance.now() - startTime) * 10) / 10;
      const errMsg = err?.message || 'Network error contacting /api/crypto/verify-tamper';
      setProbeResult({
        status: 'ERROR',
        durationMs: elapsed,
        statusCode: null,
        reason: 'NETWORK_ERROR',
        detail: errMsg,
        logLines: [`Network / request error: ${errMsg}`],
      });
    } finally {
      setIsRunning(false);
    }
  };

  const handleFireProbe = () => runVerificationProbe(false);
  const handleVerifyUntampered = () => runVerificationProbe(true);

  const handleReset = () => {
    setProbeResult({
      status: 'IDLE',
      durationMs: 0,
      statusCode: null,
      reason: null,
      detail: null,
      logLines: [],
    });
  };

  const baseFieldVal =
    sampleProof?.canonical_payload?.[selectedVector.tamperedField] ?? selectedVector.originalValue;
  const tamperedPreviewPayload = sampleProof?.canonical_payload
    ? selectedVector.applyTamper(sampleProof.canonical_payload)
    : null;
  const previewTamperedVal =
    tamperedPreviewPayload?.[selectedVector.tamperedField] ?? selectedVector.tamperedValue;

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
                  LIVE /api/crypto/verify-tamper
                </span>
              </div>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
                Sends signed or tampered mandate payloads to POST /api/crypto/verify-tamper and renders the backend verdict.
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
          {/* Protocol Context Callout (M-014 vs AP2 v0.2 ES256) */}
          <div
            style={{
              padding: '10px 14px',
              borderRadius: '10px',
              backgroundColor: 'rgba(56, 189, 248, 0.08)',
              border: '1px solid rgba(56, 189, 248, 0.25)',
              fontSize: '11px',
              color: '#cbd5e1',
              lineHeight: 1.45,
            }}
          >
            <strong style={{ color: '#38bdf8' }}>Sandbox Scope (M-014):</strong> This sandbox exercises canonical JSON tamper detection via{' '}
            <code style={{ color: '#f8fafc' }}>/api/crypto/sample-proof</code> &amp;{' '}
            <code style={{ color: '#f8fafc' }}>/api/crypto/verify-tamper</code> (<code style={{ color: '#94a3b8' }}>demo-anti-tamper-ed25519</code>).
            Live subscription purchases on <code style={{ color: '#f8fafc' }}>seller_agent.purchase_subscription</code> enforce two-step{' '}
            <strong style={{ color: '#34d399' }}>AP2 v0.2 ES256 (P-256) SD-JWT</strong> Open + Closed Mandate chains and SHA-256{' '}
            <code style={{ color: '#f8fafc' }}>checkout_hash</code> binding.
          </div>

          {/* Vector Selection Cards */}
          <div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Select Threat Scenario (Adversarial Probe)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
              {ATTACK_VECTORS.map((v) => {
                const isSelected = selectedVector.id === v.id;
                const isControl = v.category === 'UNTAMPERED_CONTROL';
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
                      backgroundColor: isSelected
                        ? isControl
                          ? 'rgba(16, 185, 129, 0.1)'
                          : 'rgba(239, 68, 68, 0.1)'
                        : '#111827',
                      border: isSelected
                        ? isControl
                          ? '1px solid #10b981'
                          : '1px solid #ef4444'
                        : '1px solid #1f2937',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: isSelected ? (isControl ? '#6ee7b7' : '#fca5a5') : '#f8fafc', marginBottom: '6px' }}>
                        {v.name}
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: 1.4 }}>
                        {v.description}
                      </div>
                    </div>
                    <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10px', color: '#64748b' }}>
                      <span style={{ fontFamily: 'monospace' }}>Field: {v.tamperedField}</span>
                      <span style={{ color: isSelected ? (isControl ? '#10b981' : '#ef4444') : '#475569', fontWeight: 700 }}>
                        {isSelected ? '● ACTIVE' : 'SELECT'}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Interactive Inspection Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '16px' }}>
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
                  <Fingerprint size={14} color="#38bdf8" /> Signed Canonical Mandate vs Request Payload
                </span>
                <span style={{ fontSize: '10px', fontFamily: 'monospace', color: '#64748b' }}>
                  {sampleProof?.algorithm || 'Ed25519'} ({sampleProof?.kid || 'demo-anti-tamper-ed25519'})
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
                <div style={{ color: '#64748b', fontSize: '10px' }}>// Signed Canonical Field Value:</div>
                <div style={{ color: '#34d399', backgroundColor: 'rgba(16, 185, 129, 0.1)', padding: '6px 8px', borderRadius: '4px' }}>
                  "{selectedVector.tamperedField}": {JSON.stringify(baseFieldVal)}
                </div>
                <div style={{ color: '#64748b', fontSize: '10px' }}>// Submitted Payload Field Value:</div>
                <div
                  style={{
                    color: selectedVector.category === 'UNTAMPERED_CONTROL' ? '#34d399' : '#f87171',
                    backgroundColor: selectedVector.category === 'UNTAMPERED_CONTROL' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.15)',
                    padding: '6px 8px',
                    borderRadius: '4px',
                    border: selectedVector.category === 'UNTAMPERED_CONTROL' ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid rgba(239, 68, 68, 0.3)',
                  }}
                >
                  "{selectedVector.tamperedField}": {JSON.stringify(previewTamperedVal)}
                </div>
                <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '4px', wordBreak: 'break-all' }}>
                  Signature: <span style={{ color: '#38bdf8' }}>{sampleProof?.signature ? `${sampleProof.signature.slice(0, 32)}...` : (sampleError ? `Error: ${sampleError}` : 'Loading...')}</span>
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '4px', flexWrap: 'wrap' }}>
                <button
                  onClick={handleFireProbe}
                  disabled={isRunning}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: 'none',
                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                    color: '#fff',
                    fontSize: '12px',
                    fontWeight: 700,
                    cursor: isRunning ? 'not-allowed' : 'pointer',
                    boxShadow: '0 4px 12px rgba(239, 68, 68, 0.3)',
                    opacity: isRunning ? 0.7 : 1,
                  }}
                >
                  <Play size={14} fill="#fff" /> {isRunning ? 'Verifying...' : 'Fire Selected Probe'}
                </button>
                <button
                  onClick={handleVerifyUntampered}
                  disabled={isRunning}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: '1px solid rgba(16, 185, 129, 0.4)',
                    backgroundColor: 'rgba(16, 185, 129, 0.15)',
                    color: '#34d399',
                    fontSize: '12px',
                    fontWeight: 700,
                    cursor: isRunning ? 'not-allowed' : 'pointer',
                  }}
                >
                  <ShieldCheck size={14} /> Verify Untampered
                </button>
                {probeResult.status !== 'IDLE' && (
                  <button
                    onClick={handleReset}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '10px 12px',
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
                  <Terminal size={14} color="#34d399" /> Backend Verification Response
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
                    INTERCEPTED ({probeResult.durationMs}ms)
                  </span>
                )}
                {probeResult.status === 'ACCEPTED' && (
                  <span
                    style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      backgroundColor: 'rgba(16, 185, 129, 0.2)',
                      color: '#34d399',
                      border: '1px solid rgba(16, 185, 129, 0.4)',
                    }}
                  >
                    ACCEPTED ({probeResult.durationMs}ms)
                  </span>
                )}
                {probeResult.status === 'ERROR' && (
                  <span
                    style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: '9999px',
                      backgroundColor: 'rgba(245, 158, 11, 0.2)',
                      color: '#fbbf24',
                      border: '1px solid rgba(245, 158, 11, 0.4)',
                    }}
                  >
                    ERROR ({probeResult.durationMs}ms)
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
                    <span>Select a scenario and click "Fire Selected Probe" or "Verify Untampered" to call /api/crypto/verify-tamper.</span>
                  </div>
                ) : (
                  probeResult.logLines.map((line, idx) => {
                    const isError = probeResult.status === 'INTERCEPTED' || probeResult.status === 'ERROR';
                    const isPassed = probeResult.status === 'ACCEPTED';
                    return (
                      <div
                        key={idx}
                        style={{
                          color: isError ? '#f87171' : isPassed ? '#34d399' : '#cbd5e1',
                          fontWeight: idx === 1 ? 700 : 400,
                          wordBreak: 'break-all',
                        }}
                      >
                        {line}
                      </div>
                    );
                  })
                )}
              </div>

              {/* Verdict Summary Footer */}
              {probeResult.status !== 'IDLE' && (
                <div
                  style={{
                    backgroundColor:
                      probeResult.status === 'ACCEPTED'
                        ? 'rgba(16, 185, 129, 0.1)'
                        : probeResult.status === 'ERROR'
                        ? 'rgba(245, 158, 11, 0.1)'
                        : 'rgba(239, 68, 68, 0.1)',
                    border:
                      probeResult.status === 'ACCEPTED'
                        ? '1px solid rgba(16, 185, 129, 0.25)'
                        : probeResult.status === 'ERROR'
                        ? '1px solid rgba(245, 158, 11, 0.25)'
                        : '1px solid rgba(239, 68, 68, 0.25)',
                    borderRadius: '8px',
                    padding: '8px 12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    fontSize: '11px',
                  }}
                >
                  <span
                    style={{
                      color:
                        probeResult.status === 'ACCEPTED'
                          ? '#6ee7b7'
                          : probeResult.status === 'ERROR'
                          ? '#fcd34d'
                          : '#fca5a5',
                      fontWeight: 600,
                    }}
                  >
                    Verdict: <strong style={{ color: '#fff', fontFamily: 'monospace' }}>{probeResult.status}</strong>
                    {probeResult.statusCode !== null ? ` (HTTP ${probeResult.statusCode})` : ''}
                    {probeResult.reason ? ` — ${probeResult.reason}` : ''}
                  </span>
                </div>
              )}
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
