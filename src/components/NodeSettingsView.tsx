import { useState, useEffect } from 'react';
import {
  Building,
  CreditCard,
  Key,
  Layers,
  Check,
  Copy,
  Save,
  RefreshCw,
  FileCode,
  Globe,
  Sliders,
  Sparkles,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  ArrowRight,
  Lock,
} from 'lucide-react';

export interface ServiceCapabilityItem {
  id: string;
  name: string;
  monthly_price_usd: number;
  quota: string;
  sla: string;
  enclave: string;
  paypal_plan_id?: string;
}

export interface NodeSettingsData {
  // Company Profile
  companyName: string;
  businessEntity: string;
  tradeVertical: string;
  supportEmail: string;
  primaryRegion: string;
  currency: string;
  mcpPort: number;
  mcpPath: string;

  // Cryptographic Keys (RFC 8032)
  publicKeyHex: string;
  privateKeyHex: string;
  mandateHmacSecret: string;
  antiTamperMode: 'strict' | 'permissive';

  // PayPal Billing Rails
  paypalClientId: string;
  paypalSecret: string;
  paypalMode: 'sandbox' | 'live';
  paypalTier1PlanId: string;
  paypalTier2PlanId: string;
  paypalTier3PlanId: string;

  // QuickBooks Online v3
  qboClientId: string;
  qboClientSecret: string;
  qboRealmId: string;
  qboGlExpenseAccount: string;
  qboGlRevenueAccount: string;

  // Zapier & CRM Webhooks
  zapierWebhookUrl: string;
  crmPlatform: 'salesforce' | 'hubspot' | 'none';
  crmWebhookUrl: string;
  slackWebhookUrl: string;

  // Capabilities Store Catalog
  capabilities: ServiceCapabilityItem[];
}

export const DEFAULT_NODE_SETTINGS: NodeSettingsData = {
  companyName: 'Acme Autonomous Systems LLC',
  businessEntity: 'Acme Autonomous Systems LLC',
  tradeVertical: 'Dedicated AI Compute & Vector RAG',
  supportEmail: 'ops@example.com',
  primaryRegion: 'US-East (N. Virginia)',
  currency: 'USD',
  mcpPort: 8001,
  mcpPath: '/mcp',

  publicKeyHex: '',
  privateKeyHex: '',
  mandateHmacSecret: 'ap2_secret_hmac_2026_mandate_verification_token',
  antiTamperMode: 'strict',

  paypalClientId: 'PAYPAL_SANDBOX_CLIENT_ID_AP2_SELLER_NODE',
  paypalSecret: 'PAYPAL_SANDBOX_SECRET_KEY_HEADLESS_MIT',
  paypalMode: 'sandbox',
  paypalTier1PlanId: 'P-5ML4271244454362WXNWU5NQ',
  paypalTier2PlanId: 'P-1GH8273644454362WXNWU7ZZ',
  paypalTier3PlanId: 'P-9KL9921444454362WXNWU9AA',

  qboClientId: 'AB1168923489123847',
  qboClientSecret: 'qbo_sec_99341298412893',
  qboRealmId: '93414520938412',
  qboGlExpenseAccount: '6300 (Dues & Subscriptions: SaaS)',
  qboGlRevenueAccount: '4000 (Operating Revenue: AP2 Subscriptions)',

  zapierWebhookUrl: 'https://hooks.zapier.com/hooks/catch/1928341/b38df9a/',
  crmPlatform: 'salesforce',
  crmWebhookUrl: 'https://api.salesforce.com/services/data/v60.0/sobjects/Contract/',
  slackWebhookUrl: 'https://hooks.slack.com/services/T00/B00/X00',

  capabilities: [
    {
      id: 'tier_batch_worker',
      name: 'High-Throughput Batch Worker',
      monthly_price_usd: 49.99,
      quota: '125 operations/mo',
      sla: '',
      enclave: 'US-Central Batch RAG',
      paypal_plan_id: 'P-5ML4271244454362WXNWU5NQ',
    },
    {
      id: 'tier_inference_gateway',
      name: 'Dedicated AI Service Gateway',
      monthly_price_usd: 79.99,
      quota: '450 operations/mo',
      sla: '',
      enclave: 'US-East Low-Latency Gateway',
      paypal_plan_id: 'P-1GH8273644454362WXNWU7ZZ',
    },
    {
      id: 'tier_enterprise_cluster',
      name: 'Enterprise Cluster Node',
      monthly_price_usd: 179.99,
      quota: '1,200 operations/mo',
      sla: '',
      enclave: 'Multi-Region Distributed Cluster',
      paypal_plan_id: 'P-9KL9921444454362WXNWU9AA',
    },
  ],
};

interface NodeSettingsViewProps {
  onSaveSettings?: (settings: NodeSettingsData) => void;
  activeTabOverride?: 'catalog' | 'crypto' | 'paypal' | 'erp' | 'agent_card' | 'profile';
  initialSettings?: NodeSettingsData;
  onNavigateTab?: (tab: 'copilot' | 'fleet-ledger' | 'ag-studio' | 'bryntum' | 'zapier' | 'settings') => void;
  isSetupComplete?: boolean;
}

export function NodeSettingsView({ onSaveSettings, activeTabOverride, initialSettings, onNavigateTab, isSetupComplete: propIsSetupComplete }: NodeSettingsViewProps) {
  const [internalIsSetupComplete, setInternalIsSetupComplete] = useState<boolean>(() => {
    try {
      return localStorage.getItem('ap2_setup_complete') === 'true';
    } catch {
      return false;
    }
  });
  const isSetupComplete = propIsSetupComplete !== undefined ? propIsSetupComplete : internalIsSetupComplete;

  const [settings, setSettings] = useState<NodeSettingsData>(() => {
    if (initialSettings) return initialSettings;
    try {
      const saved = localStorage.getItem('ap2_seller_node_settings');
      if (saved) {
        const parsed = JSON.parse(saved);
        // Exclude secrets loaded from legacy localStorage
        delete parsed.privateKeyHex;
        delete parsed.mandateHmacSecret;
        delete parsed.paypalSecret;
        delete parsed.qboClientSecret;
        return { ...DEFAULT_NODE_SETTINGS, ...parsed };
      }
    } catch {
      // ignore
    }
    return DEFAULT_NODE_SETTINGS;
  });

  // Purge any residual secrets from localStorage on mount (ADR-079 / Security Audit)
  useEffect(() => {
    try {
      const saved = localStorage.getItem('ap2_seller_node_settings');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.privateKeyHex || parsed.mandateHmacSecret || parsed.paypalSecret || parsed.qboClientSecret) {
          delete parsed.privateKeyHex;
          delete parsed.mandateHmacSecret;
          delete parsed.paypalSecret;
          delete parsed.qboClientSecret;
          localStorage.setItem('ap2_seller_node_settings', JSON.stringify(parsed));
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const [activeSettingsTab, setActiveSettingsTab] = useState<'catalog' | 'crypto' | 'paypal' | 'erp' | 'agent_card'>('catalog');

  useEffect(() => {
    if (initialSettings) {
      setSettings(initialSettings);
    }
  }, [initialSettings]);

  useEffect(() => {
    if (activeTabOverride) {
      if (activeTabOverride === 'profile') {
        setActiveSettingsTab('catalog');
      } else {
        setActiveSettingsTab(activeTabOverride as any);
      }
    }
  }, [activeTabOverride]);
  const [saveBanner, setSaveBanner] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [showPaypalSecret, setShowPaypalSecret] = useState(false);

  // Helper to copy strings
  const copyToClipboard = (text: string, key: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  // Generate real RFC 8032 Ed25519 keypair via WebCrypto SubtleCrypto
  const generateNewKeypair = async () => {
    try {
      if (window?.crypto?.subtle) {
        const keyPair = (await window.crypto.subtle.generateKey(
          { name: 'Ed25519' },
          true,
          ['sign', 'verify']
        )) as CryptoKeyPair;
        const rawPub = await window.crypto.subtle.exportKey('raw', keyPair.publicKey);
        const pkcs8Priv = await window.crypto.subtle.exportKey('pkcs8', keyPair.privateKey);

        const pubHex = Array.from(new Uint8Array(rawPub), (b) => b.toString(16).padStart(2, '0')).join('');
        // RFC 8032 Ed25519 private seed is the trailing 32 bytes of the PKCS#8 export
        const privHex = Array.from(new Uint8Array(pkcs8Priv).slice(-32), (b) => b.toString(16).padStart(2, '0')).join('');

        setSettings((prev) => ({
          ...prev,
          privateKeyHex: privHex,
          publicKeyHex: pubHex,
        }));

        setSaveBanner('🔑 New RFC 8032 Ed25519 Keypair Generated! (Retained in-memory only)');
        setTimeout(() => setSaveBanner(null), 4000);
        return;
      }
      throw new Error('WebCrypto subtle Ed25519 not available');
    } catch (err) {
      console.error('WebCrypto Ed25519 generation failed:', err);
      setSaveBanner('⚠️ WebCrypto Ed25519 not supported in this browser context.');
      setTimeout(() => setSaveBanner(null), 4000);
    }
  };

  // Add capability tier
  const handleAddCapability = () => {
    const randomPlanSuffix = Math.random().toString(36).substring(2, 8).toUpperCase();
    const newTier: ServiceCapabilityItem = {
      id: `tier_custom_${Date.now()}`,
      name: 'Custom Agent Execution Cluster',
      monthly_price_usd: 99.99,
      quota: '600 operations/mo',
      sla: '99.99% Availability',
      enclave: 'US-East Secure Enclave',
      paypal_plan_id: `P-${randomPlanSuffix}44454362WXN`,
    };
    setSettings((prev) => ({
      ...prev,
      capabilities: [...prev.capabilities, newTier],
    }));
  };

  // Remove capability tier
  const handleRemoveCapability = (id: string) => {
    setSettings((prev) => ({
      ...prev,
      capabilities: prev.capabilities.filter((c) => c.id !== id),
    }));
  };

  // Update capability tier
  const handleUpdateCapability = (index: number, field: keyof ServiceCapabilityItem, value: any) => {
    setSettings((prev) => {
      const updated = [...prev.capabilities];
      updated[index] = { ...updated[index], [field]: value };
      return { ...prev, capabilities: updated };
    });
  };

  // Update capability PayPal Plan ID and sync to legacy tier plan IDs
  const handleUpdateCapabilityPlanId = (index: number, planId: string) => {
    setSettings((prev) => {
      const updated = [...prev.capabilities];
      updated[index] = { ...updated[index], paypal_plan_id: planId };
      const nextState = { ...prev, capabilities: updated };
      if (index === 0) nextState.paypalTier1PlanId = planId;
      if (index === 1) nextState.paypalTier2PlanId = planId;
      if (index === 2) nextState.paypalTier3PlanId = planId;
      return nextState;
    });
  };

  // Save Settings to LocalStorage & Dispatch (Secrets sanitized per audit)
  const handleSave = () => {
    try {
      // Exclude sensitive secrets from localStorage persistence per ADR-079 / audit
      const { privateKeyHex, mandateHmacSecret, paypalSecret, qboClientSecret, ...safeSettings } = settings;
      localStorage.setItem('ap2_seller_node_settings', JSON.stringify(safeSettings));
    } catch {
      // ignore
    }
    if (onSaveSettings) {
      onSaveSettings(settings);
    }
    setSaveBanner('✓ Node Settings & MCP Gateway Config Saved (Secrets retained in-memory only)!');
    setTimeout(() => setSaveBanner(null), 4000);
  };

  // Reset to default
  const handleResetToDefault = () => {
    setSettings(DEFAULT_NODE_SETTINGS);
    try {
      const { privateKeyHex, mandateHmacSecret, paypalSecret, qboClientSecret, ...safeDefaults } = DEFAULT_NODE_SETTINGS;
      localStorage.setItem('ap2_seller_node_settings', JSON.stringify(safeDefaults));
      localStorage.removeItem('ap2_setup_complete');
      localStorage.removeItem('ap2_completed_steps');
    } catch {
      // ignore
    }
    setInternalIsSetupComplete(false);
    if (onSaveSettings) {
      onSaveSettings(DEFAULT_NODE_SETTINGS);
    }
    setSaveBanner('↺ Settings Reset to Turnkey Defaults!');
    setTimeout(() => setSaveBanner(null), 4000);
  };

  // Generated Agent Card JSON
  const agentCardJson = JSON.stringify(
    {
      protocol: 'AP2-Agent-Protocol',
      version: '1.4.1',
      node_id: `node_${settings.companyName.toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
      provider: {
        legal_name: settings.businessEntity,
        trade_vertical: settings.tradeVertical,
        contact_email: settings.supportEmail,
        region: settings.primaryRegion,
      },
      endpoints: {
        mcp_transport: `http://127.0.0.1:${settings.mcpPort}${settings.mcpPath}`,
        agent_card: `http://127.0.0.1:${settings.mcpPort}/.well-known/agent.json`,
        llms_txt: `http://127.0.0.1:${settings.mcpPort}/llms.txt`,
      },
      cryptography: {
        algorithm: 'RFC 8032 Ed25519',
        public_key: settings.publicKeyHex,
        anti_tamper_circuit_breaker: settings.antiTamperMode === 'strict' ? 'FAIL_CLOSED_HTTP_401' : 'WARN_ONLY',
      },
      settlement_rails: {
        paypal_subscriptions: {
          enabled: true,
          mode: settings.paypalMode,
          supported_currencies: [settings.currency],
          merchant_vault_mit: true,
        },
      },
      capabilities: settings.capabilities,
    },
    null,
    2
  );

  // Escape helper for .env values
  const escapeEnv = (val: string | number | undefined | null) => {
    if (val === undefined || val === null) return '';
    return String(val)
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '\\"')
      .replace(/\r?\n/g, '\\n');
  };

  // Generated .env snippet
  const envSnippet = `# ====================================================================
# AP2 AUTONOMOUS SELLER NODE CONFIGURATION (.env)
# Provider: ${escapeEnv(settings.businessEntity)}
# Generated: ${new Date().toISOString()}
# ====================================================================

# 1. Company & FastMCP Daemon
A2A_COMPANY_NAME="${escapeEnv(settings.companyName)}"
A2A_BUSINESS_ENTITY="${escapeEnv(settings.businessEntity)}"
A2A_TRADE_VERTICAL="${escapeEnv(settings.tradeVertical)}"
FAST_MCP_PORT=${Number(settings.mcpPort) || 8001}
FAST_MCP_PATH="${escapeEnv(settings.mcpPath)}"

# 2. Cryptographic Identity (RFC 8032 Ed25519)
A2A_PUBLIC_KEY="${escapeEnv(settings.publicKeyHex)}"
A2A_PRIVATE_KEY="${escapeEnv(settings.privateKeyHex)}"
A2A_MANDATE_SECRET="${escapeEnv(settings.mandateHmacSecret)}"

# 3. PayPal Merchant Credentials (Vault MIT)
PAYPAL_CLIENT_ID="${escapeEnv(settings.paypalClientId)}"
PAYPAL_SECRET="${escapeEnv(settings.paypalSecret)}"
PAYPAL_MODE="${escapeEnv(settings.paypalMode)}"

# 4. QuickBooks Online v3 API
QBO_CLIENT_ID="${escapeEnv(settings.qboClientId)}"
QBO_CLIENT_SECRET="${escapeEnv(settings.qboClientSecret)}"
QBO_REALM_ID="${escapeEnv(settings.qboRealmId)}"
QBO_GL_EXPENSE_ACCOUNT="${escapeEnv(settings.qboGlExpenseAccount)}"
QBO_GL_REVENUE_ACCOUNT="${escapeEnv(settings.qboGlRevenueAccount)}"

# 5. Zapier & CloudEvents EventBus
ZAPIER_MCP_CATCH_HOOK_URL="${escapeEnv(settings.zapierWebhookUrl)}"
CRM_WEBHOOK_URL="${escapeEnv(settings.crmWebhookUrl)}"
SLACK_WEBHOOK_URL="${escapeEnv(settings.slackWebhookUrl)}"
`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', boxSizing: 'border-box', padding: '12px 14px', gap: '10px', overflowY: 'auto', backgroundColor: '#090e17' }}>
      {/* Top Banner Notification */}
      {saveBanner && (
        <div
          style={{
            backgroundColor: '#065f46',
            color: '#a7f3d0',
            padding: '10px 20px',
            borderRadius: '8px',
            fontSize: '12px',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            border: '1px solid #059669',
            boxShadow: '0 4px 12px rgba(6, 95, 70, 0.3)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={16} />
            <span>{saveBanner}</span>
          </div>
          <button onClick={() => setSaveBanner(null)} style={{ background: 'none', border: 'none', color: '#a7f3d0', cursor: 'pointer' }}>
            ✕
          </button>
        </div>
      )}

      {/* Settings Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backgroundColor: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: '10px',
          padding: '10px 14px',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '38px',
              height: '38px',
              borderRadius: '10px',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              color: '#38bdf8',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Sliders size={20} />
          </div>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 800, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
              Node Settings &amp; MCP Gateway Hub
              <span style={{ fontSize: '10px', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                Live Controller
              </span>
            </div>
            <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '2px' }}>
              Configure your business profile, service catalog pricing, cryptographic keys, PayPal credentials, and QuickBooks/CRM webhooks.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            onClick={handleResetToDefault}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#1e293b',
              color: '#94a3b8',
              border: '1px solid #334155',
              padding: '7px 12px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
            title="Reset back to standard turnkey test defaults"
          >
            <RefreshCw size={13} /> Defaults
          </button>

          <button
            onClick={handleSave}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              backgroundColor: '#0284c7',
              color: '#fff',
              border: 'none',
              padding: '7px 16px',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(2, 132, 199, 0.4)',
            }}
          >
            <Save size={14} /> Save Node Settings
          </button>
        </div>
      </div>

      {/* Tab Navigation Grid: 2 Rows x 3 Columns */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '6px',
          borderBottom: '1px solid #1e293b',
          paddingBottom: '8px',
          width: '100%',
          boxSizing: 'border-box',
          flexShrink: 0,
        }}
      >
        {[
          { key: 'catalog', label: '1. Profile & Catalog', icon: Layers },
          { key: 'crypto', label: '2. Ed25519 Keys', icon: Key },
          { key: 'paypal', label: '3. PayPal Rails', icon: CreditCard },
          { key: 'erp', label: '4. QuickBooks & CRM', icon: Globe },
          { key: 'agent_card', label: '5. FastMCP Card', icon: FileCode },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSettingsTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveSettingsTab(tab.key as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '5px',
                height: '32px',
                padding: '0 6px',
                borderRadius: '6px',
                border: isActive ? '1px solid #0284c7' : '1px solid #1e293b',
                backgroundColor: isActive ? 'rgba(2, 132, 199, 0.15)' : '#0f172a',
                color: isActive ? '#38bdf8' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                width: '100%',
                boxSizing: 'border-box',
                transition: 'all 0.15s ease',
              }}
              title={tab.label}
            >
              <Icon size={13} style={{ flexShrink: 0 }} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tab.label}</span>
            </button>
          );
        })}

        {/* 6th Button: Proceed to Next Page (Dashboard / Operations Deck) */}
        <button
          disabled={!isSetupComplete}
          onClick={() => {
            if (isSetupComplete && onNavigateTab) {
              onNavigateTab('fleet-ledger');
            }
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '5px',
            height: '32px',
            padding: '0 6px',
            borderRadius: '6px',
            border: isSetupComplete ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid #334155',
            backgroundColor: isSetupComplete ? 'rgba(16, 185, 129, 0.15)' : '#0f172a',
            color: isSetupComplete ? '#34d399' : '#64748b',
            fontSize: '11px',
            fontWeight: 700,
            cursor: isSetupComplete ? 'pointer' : 'not-allowed',
            opacity: isSetupComplete ? 1 : 0.6,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            width: '100%',
            boxSizing: 'border-box',
            transition: 'all 0.15s ease',
          }}
          title={isSetupComplete ? "Setup Complete — Launch AP2 Operations Deck & Fleet Ledger" : "Complete Setup Steps 1–5 to unlock Dashboard"}
        >
          {!isSetupComplete && <Lock size={12} style={{ flexShrink: 0, opacity: 0.7 }} />}
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>6. Proceed to Dashboard</span>
          {isSetupComplete && <ArrowRight size={13} style={{ flexShrink: 0 }} />}
        </button>
      </div>

      {/* Tab 1: Business Profile & Service Catalog (Combined) */}
      {(activeSettingsTab === 'catalog' || (activeSettingsTab as string) === 'profile') && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Section 1A: Company Legal Entity & FastMCP Daemon Config */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ borderBottom: '1px solid #1e293b', paddingBottom: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Building size={16} color="#38bdf8" /> Company Legal Entity &amp; FastMCP Daemon Config
                </h3>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>
                  This identity is presented to external autonomous buyer agents in contract negotiations, discoverability cards, and invoices.
                </div>
              </div>
              <span style={{ fontSize: '10px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                Step 1: Node Identity
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                  Company Display Name
                </label>
                <input
                  type="text"
                  value={settings.companyName}
                  onChange={(e) => setSettings({ ...settings, companyName: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '12px' }}
                  placeholder="e.g. Acme Autonomous Systems LLC"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                  Legal Entity (Invoicing &amp; KYC)
                </label>
                <input
                  type="text"
                  value={settings.businessEntity}
                  onChange={(e) => setSettings({ ...settings, businessEntity: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '12px' }}
                  placeholder="e.g. Acme Autonomous Systems LLC"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                  Industry / Service Vertical
                </label>
                <input
                  type="text"
                  value={settings.tradeVertical}
                  onChange={(e) => setSettings({ ...settings, tradeVertical: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '12px' }}
                  placeholder="e.g. Dedicated AI Compute & Vector RAG"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                  Operations &amp; Dispute Email
                </label>
                <input
                  type="email"
                  value={settings.supportEmail}
                  onChange={(e) => setSettings({ ...settings, supportEmail: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '12px' }}
                  placeholder="e.g. ops@example.com"
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                  Primary Enclave Region
                </label>
                <select
                  value={settings.primaryRegion}
                  onChange={(e) => setSettings({ ...settings, primaryRegion: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '12px' }}
                >
                  <option value="US-East (N. Virginia)">US-East (N. Virginia)</option>
                  <option value="US-Central (Iowa)">US-Central (Iowa)</option>
                  <option value="US-West (Oregon)">US-West (Oregon)</option>
                  <option value="Europe-West (Frankfurt)">Europe-West (Frankfurt)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                  FastMCP Daemon Port &amp; Route
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="number"
                    value={settings.mcpPort}
                    onChange={(e) => setSettings({ ...settings, mcpPort: parseInt(e.target.value) || 8001 })}
                    style={{ width: '100px', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#38bdf8', fontSize: '12px', fontFamily: 'monospace' }}
                  />
                  <input
                    type="text"
                    value={settings.mcpPath}
                    onChange={(e) => setSettings({ ...settings, mcpPath: e.target.value })}
                    style={{ flex: 1, padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#38bdf8', fontSize: '12px', fontFamily: 'monospace' }}
                  />
                </div>
                <div style={{ marginTop: '6px', padding: '8px 10px', backgroundColor: 'rgba(56, 189, 248, 0.08)', border: '1px solid rgba(56, 189, 248, 0.2)', borderRadius: '6px', fontSize: '11px', color: '#94a3b8', lineHeight: 1.4 }}>
                  <span style={{ color: '#38bdf8', fontWeight: 700 }}>💡 What is this?</span> FastMCP is the Model Context Protocol communication daemon that external buyer agents connect to. Port <code>{settings.mcpPort}</code> is the network port your Python backend listens on, and route <code>{settings.mcpPath}</code> is the standard JSON-RPC 2.0 endpoint. For standard turnkey deployments, keep the default <code>8001</code> and <code>/mcp</code>.
                </div>
              </div>
            </div>
          </div>

          {/* Section 1B: Service Capabilities Catalog (What Buyer Agents Can Purchase) */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #1e293b', paddingBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Layers size={16} color="#10b981" /> Service Capabilities Catalog (What Buyer Agents Can Purchase)
                </h3>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>
                  Published at <code>backend/data/service_catalog.json</code> for autonomous MCP tool discovery.
                </div>
              </div>
              <button
                onClick={handleAddCapability}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  backgroundColor: '#10b981',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                <Plus size={13} /> Add Service Tier
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {settings.capabilities.map((cap, idx) => (
                <div
                  key={cap.id}
                  style={{
                    backgroundColor: '#090e17',
                    border: '1px solid #1e293b',
                    borderRadius: '8px',
                    padding: '14px',
                    display: 'grid',
                    gridTemplateColumns: '1.5fr 1fr 1fr 1fr auto',
                    gap: '12px',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase', fontWeight: 700 }}>Plan Name</span>
                    <input
                      type="text"
                      value={cap.name}
                      onChange={(e) => handleUpdateCapability(idx, 'name', e.target.value)}
                      style={{ width: '100%', marginTop: '4px', padding: '6px 8px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '4px', color: '#f8fafc', fontSize: '12px', fontWeight: 600 }}
                    />
                  </div>

                  <div>
                    <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase', fontWeight: 700 }}>Price ($/mo)</span>
                    <input
                      type="number"
                      step="0.01"
                      value={cap.monthly_price_usd}
                      onChange={(e) => handleUpdateCapability(idx, 'monthly_price_usd', parseFloat(e.target.value) || 0)}
                      style={{ width: '100%', marginTop: '4px', padding: '6px 8px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '4px', color: '#34d399', fontSize: '12px', fontWeight: 700 }}
                    />
                  </div>

                  <div>
                    <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase', fontWeight: 700 }}>Quota Allowance</span>
                    <input
                      type="text"
                      value={cap.quota}
                      onChange={(e) => handleUpdateCapability(idx, 'quota', e.target.value)}
                      style={{ width: '100%', marginTop: '4px', padding: '6px 8px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '4px', color: '#f8fafc', fontSize: '11px' }}
                    />
                  </div>

                  <div>
                    <span style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase', fontWeight: 700 }}>Enclave SLA</span>
                    <input
                      type="text"
                      value={cap.sla}
                      onChange={(e) => handleUpdateCapability(idx, 'sla', e.target.value)}
                      placeholder="e.g. Standard SLA"
                      style={{ width: '100%', marginTop: '4px', padding: '6px 8px', backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '4px', color: '#38bdf8', fontSize: '11px' }}
                    />
                  </div>

                  <div style={{ paddingTop: '16px' }}>
                    <button
                      onClick={() => handleRemoveCapability(cap.id)}
                      disabled={settings.capabilities.length <= 1}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: settings.capabilities.length <= 1 ? '#475569' : '#ef4444',
                        cursor: settings.capabilities.length <= 1 ? 'not-allowed' : 'pointer',
                        padding: '4px',
                      }}
                      title="Remove tier"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Cryptographic Keys (RFC 8032) */}
      {activeSettingsTab === 'crypto' && (
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #1e293b', paddingBottom: '12px' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
                RFC 8032 Ed25519 Asymmetric Keys &amp; Anti-Tamper Security
              </h3>
              <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>
                Guarantees mathematical non-repudiation. Tampered intent mandates fail-closed with HTTP 401 Unauthorized.
              </div>
            </div>

            <button
              onClick={generateNewKeypair}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                backgroundColor: '#7c3aed',
                color: '#fff',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              <Key size={13} /> Generate Fresh Keypair
            </button>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#cbd5e1' }}>
                  Seller Public Key (Hex 64-char) — Shared with Buyer Agents
                </label>
                <button
                  onClick={() => copyToClipboard(settings.publicKeyHex, 'pubkey')}
                  style={{ background: 'none', border: 'none', color: copiedKey === 'pubkey' ? '#34d399' : '#38bdf8', fontSize: '10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                >
                  {copiedKey === 'pubkey' ? <Check size={11} /> : <Copy size={11} />} {copiedKey === 'pubkey' ? 'Copied' : 'Copy Public Key'}
                </button>
              </div>
              <input
                type="text"
                value={settings.publicKeyHex}
                onChange={(e) => setSettings({ ...settings, publicKeyHex: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#38bdf8', fontSize: '11px', fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#cbd5e1' }}>
                  Seller Private Key (Hex 64-char) — Keep Secret on Server Disk
                </label>
                <button
                  onClick={() => copyToClipboard(settings.privateKeyHex, 'privkey')}
                  style={{ background: 'none', border: 'none', color: copiedKey === 'privkey' ? '#34d399' : '#38bdf8', fontSize: '10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                >
                  {copiedKey === 'privkey' ? <Check size={11} /> : <Copy size={11} />} {copiedKey === 'privkey' ? 'Copied' : 'Copy Private Key'}
                </button>
              </div>
              <input
                type="password"
                value={settings.privateKeyHex}
                onChange={(e) => setSettings({ ...settings, privateKeyHex: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#c084fc', fontSize: '11px', fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                Anti-Tamper Circuit Breaker Enforcement Mode
              </label>
              <div style={{ display: 'flex', gap: '12px' }}>
                <label
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 14px',
                    backgroundColor: settings.antiTamperMode === 'strict' ? 'rgba(16, 185, 129, 0.12)' : '#090e17',
                    border: settings.antiTamperMode === 'strict' ? '1px solid #10b981' : '1px solid #334155',
                    borderRadius: '8px',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    checked={settings.antiTamperMode === 'strict'}
                    onChange={() => setSettings({ ...settings, antiTamperMode: 'strict' })}
                    style={{ accentColor: '#10b981' }}
                  />
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>Strict (Fail-Closed HTTP 401)</div>
                    <div style={{ fontSize: '10px', color: '#94a3b8' }}>Rejects any tampered price (+1¢) or expired nonce instantly.</div>
                  </div>
                </label>

                <label
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 14px',
                    backgroundColor: settings.antiTamperMode === 'permissive' ? 'rgba(245, 158, 11, 0.12)' : '#090e17',
                    border: settings.antiTamperMode === 'permissive' ? '1px solid #f59e0b' : '1px solid #334155',
                    borderRadius: '8px',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="radio"
                    checked={settings.antiTamperMode === 'permissive'}
                    onChange={() => setSettings({ ...settings, antiTamperMode: 'permissive' })}
                    style={{ accentColor: '#f59e0b' }}
                  />
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>Permissive (Audit Warning)</div>
                    <div style={{ fontSize: '10px', color: '#94a3b8' }}>Logs tampered payloads to security trace without aborting session.</div>
                  </div>
                </label>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: PayPal Billing Rails */}
      {activeSettingsTab === 'paypal' && (
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{ borderBottom: '1px solid #1e293b', paddingBottom: '12px' }}>
            <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
              PayPal Subscriptions v1 &amp; Vault MIT Credentials
            </h3>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>
              Powers recurring headless subscription revenue directly from buyer agents without human invoicing.
            </div>
          </div>

          {/* Credentials Card */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#cbd5e1' }}>
                  PayPal REST Client ID
                </label>
                <button
                  onClick={() => copyToClipboard(settings.paypalClientId, 'paypal_client_id')}
                  style={{ background: 'none', border: 'none', color: copiedKey === 'paypal_client_id' ? '#34d399' : '#38bdf8', fontSize: '10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                >
                  {copiedKey === 'paypal_client_id' ? <Check size={11} /> : <Copy size={11} />} {copiedKey === 'paypal_client_id' ? 'Copied' : 'Copy ID'}
                </button>
              </div>
              <input
                type="text"
                value={settings.paypalClientId}
                onChange={(e) => setSettings({ ...settings, paypalClientId: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#fbbf24', fontSize: '11px', fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                <label style={{ fontSize: '11px', fontWeight: 600, color: '#cbd5e1' }}>
                  PayPal REST Secret Key
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    onClick={() => setShowPaypalSecret(!showPaypalSecret)}
                    style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '3px' }}
                    title={showPaypalSecret ? 'Hide Secret Key' : 'Reveal Secret Key'}
                  >
                    {showPaypalSecret ? <EyeOff size={12} /> : <Eye size={12} />}
                    {showPaypalSecret ? 'Hide' : 'Reveal'}
                  </button>
                  <button
                    onClick={() => copyToClipboard(settings.paypalSecret, 'paypal_secret')}
                    style={{ background: 'none', border: 'none', color: copiedKey === 'paypal_secret' ? '#34d399' : '#38bdf8', fontSize: '10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
                  >
                    {copiedKey === 'paypal_secret' ? <Check size={11} /> : <Copy size={11} />} {copiedKey === 'paypal_secret' ? 'Copied' : 'Copy Secret'}
                  </button>
                </div>
              </div>
              <input
                type={showPaypalSecret ? 'text' : 'password'}
                value={settings.paypalSecret}
                onChange={(e) => setSettings({ ...settings, paypalSecret: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#fbbf24', fontSize: '11px', fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                PayPal API Mode
              </label>
              <select
                value={settings.paypalMode}
                onChange={(e) => setSettings({ ...settings, paypalMode: e.target.value as any })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '12px' }}
              >
                <option value="sandbox">Sandbox (Testing / Hackathon)</option>
                <option value="live">Live (Production Payments)</option>
              </select>
            </div>
          </div>

          {/* Dynamic Service Catalog Plan IDs */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '4px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  Dynamic PayPal Plan Mappings ({settings.capabilities.length} Active {settings.capabilities.length === 1 ? 'Tier' : 'Tiers'})
                  <span style={{ fontSize: '10px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                    Catalog Synced
                  </span>
                </h4>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                  These plans are dynamically read from your Service Catalog (Tab 1). Add, reprice, or delete tiers in Tab 1 and bind corresponding PayPal Plan IDs here.
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {settings.capabilities.map((cap, idx) => {
                const planId = cap.paypal_plan_id || (idx === 0 ? settings.paypalTier1PlanId : idx === 1 ? settings.paypalTier2PlanId : idx === 2 ? settings.paypalTier3PlanId : '');
                const copyTag = `plan_${cap.id}`;
                return (
                  <div
                    key={cap.id}
                    style={{
                      backgroundColor: '#090e17',
                      border: '1px solid #1e293b',
                      borderRadius: '8px',
                      padding: '12px 16px',
                      display: 'grid',
                      gridTemplateColumns: '1.4fr 1.6fr auto',
                      gap: '14px',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>{cap.name}</span>
                        <span style={{ fontSize: '11px', fontWeight: 800, color: '#34d399', backgroundColor: 'rgba(16, 185, 129, 0.12)', padding: '2px 6px', borderRadius: '4px' }}>
                          ${cap.monthly_price_usd.toFixed(2)}/mo
                        </span>
                      </div>
                      <div style={{ fontSize: '10px', color: '#64748b', marginTop: '3px' }}>
                        Quota: {cap.quota} • {cap.sla}
                      </div>
                    </div>

                    <div>
                      <span style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 700 }}>
                        PayPal Subscription Plan ID
                      </span>
                      <input
                        type="text"
                        value={planId}
                        onChange={(e) => handleUpdateCapabilityPlanId(idx, e.target.value)}
                        placeholder="e.g. P-5ML4271244454362WXNWU5NQ"
                        style={{
                          width: '100%',
                          marginTop: '3px',
                          padding: '6px 10px',
                          backgroundColor: '#0f172a',
                          border: '1px solid #334155',
                          borderRadius: '4px',
                          color: '#38bdf8',
                          fontSize: '11px',
                          fontFamily: 'monospace',
                        }}
                      />
                    </div>

                    <div style={{ paddingTop: '14px' }}>
                      <button
                        onClick={() => copyToClipboard(planId, copyTag)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          backgroundColor: '#1e293b',
                          color: copiedKey === copyTag ? '#34d399' : '#38bdf8',
                          border: '1px solid #334155',
                          padding: '6px 10px',
                          borderRadius: '4px',
                          fontSize: '11px',
                          cursor: 'pointer',
                        }}
                        title="Copy PayPal Plan ID to clipboard"
                      >
                        {copiedKey === copyTag ? <Check size={12} /> : <Copy size={12} />}
                        {copiedKey === copyTag ? 'Copied' : 'Copy ID'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: QuickBooks & CRM Connectors */}
      {activeSettingsTab === 'erp' && (
        <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ borderBottom: '1px solid #1e293b', paddingBottom: '12px' }}>
            <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
              Downstream ERP (QuickBooks Online v3) &amp; CRM Integrations
            </h3>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>
              Every completed transaction automatically posts double-entry records and fires webhooks into your enterprise back office.
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                QuickBooks Online Realm / Company ID
              </label>
              <input
                type="text"
                value={settings.qboRealmId}
                onChange={(e) => setSettings({ ...settings, qboRealmId: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#38bdf8', fontSize: '11px', fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                QBO General Ledger Debit Account
              </label>
              <input
                type="text"
                value={settings.qboGlExpenseAccount}
                onChange={(e) => setSettings({ ...settings, qboGlExpenseAccount: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '11px' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                Zapier MCP Catch-Hook Webhook URL
              </label>
              <input
                type="text"
                value={settings.zapierWebhookUrl}
                onChange={(e) => setSettings({ ...settings, zapierWebhookUrl: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f59e0b', fontSize: '11px', fontFamily: 'monospace' }}
                placeholder="https://hooks.zapier.com/hooks/catch/..."
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                Slack Deal Channel Webhook URL
              </label>
              <input
                type="text"
                value={settings.slackWebhookUrl}
                onChange={(e) => setSettings({ ...settings, slackWebhookUrl: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '11px', fontFamily: 'monospace' }}
                placeholder="https://hooks.slack.com/services/..."
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                CRM Integration Platform
              </label>
              <select
                value={settings.crmPlatform}
                onChange={(e) => setSettings({ ...settings, crmPlatform: e.target.value as any })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '12px' }}
              >
                <option value="salesforce">Salesforce (Platform Events / Opportunities)</option>
                <option value="hubspot">HubSpot (CRM v3 Contacts / Deals)</option>
                <option value="none">Disabled (Local Ledger Only)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#cbd5e1', marginBottom: '6px' }}>
                CRM Ingest Endpoint URL
              </label>
              <input
                type="text"
                value={settings.crmWebhookUrl}
                onChange={(e) => setSettings({ ...settings, crmWebhookUrl: e.target.value })}
                style={{ width: '100%', padding: '8px 12px', backgroundColor: '#090e17', border: '1px solid #334155', borderRadius: '6px', color: '#f8fafc', fontSize: '11px', fontFamily: 'monospace' }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Tab 5: FastMCP & Agent Card Exposer */}
      {activeSettingsTab === 'agent_card' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', minHeight: 0 }}>
          {/* Left: Agent Discovery Card */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div>
                <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#f8fafc' }}>
                  Live Agent Discovery Card (<code>.well-known/agent.json</code>)
                </h4>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                  Served at <code>http://127.0.0.1:{settings.mcpPort}/.well-known/agent.json</code>
                </div>
              </div>
              <button
                onClick={() => copyToClipboard(agentCardJson, 'agent_card')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  backgroundColor: '#1e293b',
                  color: copiedKey === 'agent_card' ? '#34d399' : '#38bdf8',
                  border: '1px solid #334155',
                  padding: '4px 10px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
              >
                {copiedKey === 'agent_card' ? <Check size={12} /> : <Copy size={12} />}
                {copiedKey === 'agent_card' ? 'Copied' : 'Copy JSON'}
              </button>
            </div>
            <pre style={{ flex: 1, margin: 0, padding: '12px', backgroundColor: '#090e17', border: '1px solid #1e293b', borderRadius: '6px', color: '#38bdf8', fontSize: '11px', fontFamily: 'monospace', overflowY: 'auto' }}>
              {agentCardJson}
            </pre>
          </div>

          {/* Right: Generated .env Configuration */}
          <div style={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div>
                <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#f8fafc' }}>
                  Generated Repository <code>.env</code> File
                </h4>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                  Save to your project root to run the FastMCP seller daemon.
                </div>
              </div>
              <button
                onClick={() => copyToClipboard(envSnippet, 'env_file')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  backgroundColor: '#1e293b',
                  color: copiedKey === 'env_file' ? '#34d399' : '#38bdf8',
                  border: '1px solid #334155',
                  padding: '4px 10px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  cursor: 'pointer',
                }}
              >
                {copiedKey === 'env_file' ? <Check size={12} /> : <Copy size={12} />}
                {copiedKey === 'env_file' ? 'Copied' : 'Copy .env'}
              </button>
            </div>
            <pre style={{ flex: 1, margin: 0, padding: '12px', backgroundColor: '#090e17', border: '1px solid #1e293b', borderRadius: '6px', color: '#cbd5e1', fontSize: '11px', fontFamily: 'monospace', overflowY: 'auto' }}>
              {envSnippet}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default NodeSettingsView;
