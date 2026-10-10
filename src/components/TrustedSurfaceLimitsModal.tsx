import React, { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  X,
  Lock,
  Key,
  CheckCircle2,
  Calendar,
  DollarSign,
  Layers,
  Copy,
  Check,
  ExternalLink,
} from 'lucide-react';

export interface TrustedSurfaceLimitsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialEmail?: string;
  initialBudgetCap?: number;
  onMandatesSigned?: (tokens: {
    openCheckoutToken: string;
    openPaymentToken: string;
    constraints: any;
  }) => void;
}

export const TrustedSurfaceLimitsModal: React.FC<TrustedSurfaceLimitsModalProps> = ({
  isOpen,
  onClose,
  initialEmail = 'agent-alpha@nexus-systems.io',
  initialBudgetCap = 60.0,
  onMandatesSigned,
}) => {
  const [buyerEmail, setBuyerEmail] = useState(initialEmail);
  const [monthlyBudgetCap, setMonthlyBudgetCap] = useState(initialBudgetCap);
  const [yearlyCeiling, setYearlyCeiling] = useState(initialBudgetCap * 12);
  const [allowedTiers, setAllowedTiers] = useState<string[]>([
    'ap2-batch',
    'ap2-gateway',
  ]);
  const [validityHours, setValidityHours] = useState(24);
  const [humanConfirmed, setHumanConfirmed] = useState(true);

  const [isSigning, setIsSigning] = useState(false);
  const [signedResult, setSignedResult] = useState<any | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleTierToggle = (tierId: string) => {
    setAllowedTiers((prev) =>
      prev.includes(tierId)
        ? prev.filter((t) => t !== tierId)
        : [...prev, tierId]
    );
  };

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleSignLimits = async () => {
    if (!humanConfirmed) {
      setErrorMsg('Explicit human confirmation is required. Agents cannot self-authorize.');
      return;
    }
    setErrorMsg(null);
    setIsSigning(true);

    try {
      const resp = await fetch('/api/trusted-surface/sign-limits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          buyer_email: buyerEmail,
          monthly_budget_cap: monthlyBudgetCap,
          yearly_budget_ceiling: yearlyCeiling,
          allowed_tiers: allowedTiers,
          validity_hours: validityHours,
          human_confirmed: true,
        }),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.detail?.reason || errData.detail || 'Signing failed');
      }

      const data = await resp.json();
      setSignedResult(data);
      if (onMandatesSigned) {
        onMandatesSigned({
          openCheckoutToken: data.open_checkout_mandate_token,
          openPaymentToken: data.open_payment_mandate_token,
          constraints: data.constraints,
        });
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to sign open mandates.');
    } finally {
      setIsSigning(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(15, 23, 42, 0.85)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: '20px',
      }}
    >
      <div
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          width: '100%',
          maxWidth: '780px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #1e293b',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: '#0f172a',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#38bdf8',
              }}
            >
              <ShieldCheck size={18} />
            </div>
            <div>
              <div style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
                AP2 Trusted Surface — Spending Limits & Open Mandates
              </div>
              <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                Non-Agentic Human Authorization Interface • Google AP2 v0.2 Protocol
              </div>
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
              display: 'flex',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Invariant Banner */}
        <div
          style={{
            padding: '10px 20px',
            backgroundColor: 'rgba(2, 132, 199, 0.08)',
            borderBottom: '1px solid rgba(2, 132, 199, 0.2)',
            fontSize: '12px',
            color: '#7dd3fc',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Lock size={14} />
          <span>
            <strong>Mandate Segregation Invariant:</strong> AI Agents cannot self-authorize financial ceilings. The human owner signs the Open Mandates here using an ES256 P-256 key.
          </span>
        </div>

        {/* Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
            {/* Buyer Billing Email */}
            <div>
              <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '6px', fontWeight: 500 }}>
                Human Owner / Buyer Email
              </label>
              <input
                type="email"
                value={buyerEmail}
                onChange={(e) => setBuyerEmail(e.target.value)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  color: '#fff',
                  fontSize: '13px',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Monthly Budget Cap */}
            <div>
              <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '6px', fontWeight: 500 }}>
                Monthly Spending Cap (AmountRange.max)
              </label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: '10px', top: '10px', color: '#64748b', fontSize: '13px' }}>$</span>
                <input
                  type="number"
                  step="0.01"
                  value={monthlyBudgetCap}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value) || 0;
                    setMonthlyBudgetCap(val);
                    setYearlyCeiling(val * 12);
                  }}
                  style={{
                    width: '100%',
                    padding: '9px 12px 9px 24px',
                    borderRadius: '6px',
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    color: '#fff',
                    fontSize: '13px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>

            {/* Annual Ceiling */}
            <div>
              <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '6px', fontWeight: 500 }}>
                Yearly Spending Ceiling (payment.budget)
              </label>
              <div style={{ position: 'relative' }}>
                <span style={{ position: 'absolute', left: '10px', top: '10px', color: '#64748b', fontSize: '13px' }}>$</span>
                <input
                  type="number"
                  step="0.01"
                  value={yearlyCeiling}
                  onChange={(e) => setYearlyCeiling(parseFloat(e.target.value) || 0)}
                  style={{
                    width: '100%',
                    padding: '9px 12px 9px 24px',
                    borderRadius: '6px',
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    color: '#fff',
                    fontSize: '13px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>

            {/* Validity Duration */}
            <div>
              <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '6px', fontWeight: 500 }}>
                Authorization Validity Window (exp)
              </label>
              <select
                value={validityHours}
                onChange={(e) => setValidityHours(parseInt(e.target.value) || 24)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  color: '#fff',
                  fontSize: '13px',
                  boxSizing: 'border-box',
                }}
              >
                <option value={1}>1 Hour (Ephemeral Task Window)</option>
                <option value={12}>12 Hours (Single Shift)</option>
                <option value={24}>24 Hours (Standard 1-Day Window)</option>
                <option value={168}>7 Days (Extended Onboarding)</option>
              </select>
            </div>
          </div>

          {/* Allowed Line Items / Compute Tiers */}
          <div style={{ marginBottom: '18px' }}>
            <label style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '8px', fontWeight: 500 }}>
              Authorized Compute Tiers (checkout.line_items)
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
              {[
                { id: 'ap2-batch', title: 'High-Throughput Batch Worker', price: '$49.99/mo' },
                { id: 'ap2-gateway', title: 'Dedicated AI Service Gateway', price: '$79.99/mo' },
                { id: 'ap2-cluster', title: 'Enterprise Cluster Node', price: '$179.99/mo' },
              ].map((tier) => {
                const checked = allowedTiers.includes(tier.id);
                return (
                  <div
                    key={tier.id}
                    onClick={() => handleTierToggle(tier.id)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '8px',
                      backgroundColor: checked ? 'rgba(56, 189, 248, 0.1)' : '#1e293b',
                      border: checked ? '1px solid #0284c7' : '1px solid #334155',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '8px',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {}}
                      style={{ marginTop: '2px', accentColor: '#0284c7' }}
                    />
                    <div>
                      <div style={{ fontSize: '12px', fontWeight: 600, color: checked ? '#38bdf8' : '#e2e8f0' }}>
                        {tier.title}
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                        {tier.price} • ID: <code>{tier.id}</code>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Protocol Binding Summary Card */}
          <div
            style={{
              padding: '12px 14px',
              backgroundColor: '#1e293b',
              borderRadius: '8px',
              border: '1px solid #334155',
              fontSize: '12px',
              color: '#cbd5e1',
              marginBottom: '18px',
              lineHeight: '1.6',
            }}
          >
            <div style={{ fontWeight: 600, color: '#f8fafc', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Layers size={14} color="#38bdf8" /> Cryptographic Mandate Enforcements:
            </div>
            <div>• <strong>Recurrence Cadence:</strong> <code>payment.agent_recurrence = MONTHLY (max 12)</code></div>
            <div>• <strong>Allowed Payee & Merchant:</strong> <code>merchant-ap2-autonomous</code> (Strict ID match)</div>
            <div>• <strong>Key Binding:</strong> <code>cnf.jwk</code> binds the AI Buyer Agent holder key to prevent replay</div>
          </div>

          {/* Human Confirmation Guard */}
          <div
            style={{
              padding: '12px 14px',
              backgroundColor: humanConfirmed ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)',
              border: humanConfirmed ? '1px solid rgba(34, 197, 94, 0.3)' : '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              marginBottom: '18px',
              cursor: 'pointer',
            }}
            onClick={() => setHumanConfirmed(!humanConfirmed)}
          >
            <input
              type="checkbox"
              checked={humanConfirmed}
              onChange={(e) => setHumanConfirmed(e.target.checked)}
              style={{ width: '16px', height: '16px', accentColor: '#22c55e' }}
            />
            <div style={{ fontSize: '12px', color: humanConfirmed ? '#86efac' : '#fca5a5' }}>
              <strong>Human Intent Confirmation:</strong> I hereby explicitly authorize the AI Buyer Agent to negotiate and commit recurring funds up to <strong>${monthlyBudgetCap.toFixed(2)}/month</strong>.
            </div>
          </div>

          {errorMsg && (
            <div
              style={{
                padding: '10px 14px',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid #ef4444',
                borderRadius: '6px',
                fontSize: '12px',
                color: '#fca5a5',
                marginBottom: '16px',
              }}
            >
              {errorMsg}
            </div>
          )}

          {/* Action Button */}
          <button
            onClick={handleSignLimits}
            disabled={isSigning || !humanConfirmed}
            style={{
              width: '100%',
              padding: '12px 16px',
              borderRadius: '8px',
              backgroundColor: humanConfirmed ? '#0284c7' : '#475569',
              color: '#ffffff',
              border: 'none',
              fontSize: '14px',
              fontWeight: 600,
              cursor: humanConfirmed ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              transition: 'background-color 0.15s ease',
            }}
          >
            {isSigning ? (
              <>Signing Open Mandates with ES256...</>
            ) : (
              <>
                <Key size={16} /> ✍️ Sign & Mint Open Mandates (Human Click)
              </>
            )}
          </button>

          {/* Signed Result Preview */}
          {signedResult && (
            <div
              style={{
                marginTop: '20px',
                padding: '16px',
                backgroundColor: 'rgba(15, 23, 42, 0.95)',
                borderRadius: '8px',
                border: '1px solid #22c55e',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#4ade80', fontSize: '13px', fontWeight: 600 }}>
                  <CheckCircle2 size={16} /> Open Mandates Authenticated & Issued!
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                  Issuer: <code>{signedResult.owner_kid}</code>
                </div>
              </div>

              {/* Tokens breakdown */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '11px' }}>
                <div style={{ backgroundColor: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', color: '#38bdf8', fontWeight: 600 }}>
                    <span>Open Checkout Mandate (mandate.checkout.open.1):</span>
                    <button
                      onClick={() => handleCopy(signedResult.open_checkout_mandate_token, 'chk')}
                      style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px' }}
                    >
                      {copiedKey === 'chk' ? <Check size={12} color="#4ade80" /> : <Copy size={12} />}
                      {copiedKey === 'chk' ? 'Copied' : 'Copy Token'}
                    </button>
                  </div>
                  <div style={{ fontFamily: 'monospace', wordBreak: 'break-all', color: '#94a3b8', maxHeight: '48px', overflowY: 'hidden' }}>
                    {signedResult.open_checkout_mandate_token.slice(0, 100)}...
                  </div>
                </div>

                <div style={{ backgroundColor: '#1e293b', padding: '10px', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', color: '#38bdf8', fontWeight: 600 }}>
                    <span>Open Payment Mandate (mandate.payment.open.1):</span>
                    <button
                      onClick={() => handleCopy(signedResult.open_payment_mandate_token, 'pay')}
                      style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px' }}
                    >
                      {copiedKey === 'pay' ? <Check size={12} color="#4ade80" /> : <Copy size={12} />}
                      {copiedKey === 'pay' ? 'Copied' : 'Copy Token'}
                    </button>
                  </div>
                  <div style={{ fontFamily: 'monospace', wordBreak: 'break-all', color: '#94a3b8', maxHeight: '48px', overflowY: 'hidden' }}>
                    {signedResult.open_payment_mandate_token.slice(0, 100)}...
                  </div>
                </div>
              </div>

              <button
                onClick={onClose}
                style={{
                  marginTop: '12px',
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#22c55e',
                  color: '#0f172a',
                  border: 'none',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                Forward Signed Open Mandates to AI Buyer Agent →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
