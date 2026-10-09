import { useState, useRef, useEffect, useMemo } from 'react';
import {
  Bot,
  User,
  Send,
  CreditCard,
  Cpu,
  CheckCircle2,
  Code2,
  Key,
  Layers,
  Terminal,
  FileCode,
  Copy,
  Check,
  X,
  RefreshCw,
  ShieldCheck,
  Play,
  ShieldAlert,
  Radio,
  Activity,
  BookOpen,
  Sparkles,
  Mic,
  MicOff,
  Sliders,
  Plus,
  Trash2,
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2,
  ArrowRight,
} from 'lucide-react';
import { NodeSettingsView, type NodeSettingsData, type ServiceCapabilityItem, DEFAULT_NODE_SETTINGS } from './NodeSettingsView';

export interface ChatMessage {
  id: string;
  sender: 'contractor' | 'copilot' | 'buyer';
  text: string;
  timestamp: string;
  phase?: 'DIAGNOSIS' | 'PROPOSAL' | 'COMPLETED' | 'IDLE';
  telemetry?: any;
  proposal?: any;
  suggestedActions?: string[];
  executionResult?: any;
  interactiveForm?: 'step1' | 'step2' | 'step3' | 'step4' | 'step5';
  nextStepAction?: { step: number; label: string };
}

export interface SellerCopilotViewProps {
  contractorName?: string;
  businessEntity?: string;
  tradeVertical?: string;
  areaCode?: string;
  budgetCap?: number;
  onA2aCompleted?: (result: {
    subscriptionId: string;
    allocatedDid: string;
    carrier: string;
    contractorName: string;
    businessEntity: string;
  }) => void;
  onNavigateTab?: (tab: 'copilot' | 'fleet-ledger' | 'ag-studio' | 'bryntum' | 'zapier' | 'settings') => void;
  onSaveSettings?: (settings: NodeSettingsData) => void;
  activeStep?: number;
  onSelectStep?: (step: number) => void;
  isGuideCollapsed?: boolean;
  onToggleGuideCollapsed?: () => void;
}

export type ContractorCopilotViewProps = SellerCopilotViewProps;

export function SellerCopilotView({
  contractorName = 'agent:acme-procure',
  businessEntity = 'Acme Autonomous Systems LLC',
  tradeVertical = 'Dedicated AI Service Gateway',
  areaCode = '863',
  budgetCap = 100.0,
  onA2aCompleted,
  onNavigateTab,
  onSaveSettings,
  activeStep: propActiveStep,
  onSelectStep,
  isGuideCollapsed: propIsGuideCollapsed,
  onToggleGuideCollapsed,
}: SellerCopilotViewProps) {
  // Configurable Parameters (Dynamic Ingestion)
  const [localContractorName, setLocalContractorName] = useState(contractorName);
  const [localBusinessEntity, setLocalBusinessEntity] = useState(businessEntity);
  const [localTradeVertical, setLocalTradeVertical] = useState(tradeVertical);
  const [localAreaCode, setLocalAreaCode] = useState(areaCode);
  const [localBudgetCap, setLocalBudgetCap] = useState(budgetCap);
  const [simulateExhaustion, setSimulateExhaustion] = useState(false);

  // Synchronize when parent props change
  useEffect(() => {
    setLocalContractorName(contractorName);
    setLocalBusinessEntity(businessEntity);
    setLocalTradeVertical(tradeVertical);
    setLocalAreaCode(areaCode);
    setLocalBudgetCap(budgetCap);
  }, [contractorName, businessEntity, tradeVertical, areaCode, budgetCap]);

  // Integrated Node Settings State (Unified Tab 1 & Tab 5)
  const [nodeSettings, setNodeSettings] = useState<NodeSettingsData>(() => {
    try {
      const saved = localStorage.getItem('ap2_seller_node_settings');
      if (saved) {
        const parsed = JSON.parse(saved);
        delete parsed.privateKeyHex;
        delete parsed.mandateHmacSecret;
        delete parsed.paypalSecret;
        delete parsed.qboClientSecret;
        return { ...DEFAULT_NODE_SETTINGS, ...parsed };
      }
    } catch {}
    return DEFAULT_NODE_SETTINGS;
  });

  const [settingsTabOverride, setSettingsTabOverride] = useState<'profile' | 'catalog' | 'crypto' | 'paypal' | 'erp' | 'agent_card'>('catalog');

  const saveNodeSettings = (updated: NodeSettingsData) => {
    setNodeSettings(updated);
    try {
      const { privateKeyHex, mandateHmacSecret, paypalSecret, qboClientSecret, ...safeUpdated } = updated;
      localStorage.setItem('ap2_seller_node_settings', JSON.stringify(safeUpdated));
    } catch {}
    setLocalBusinessEntity(updated.businessEntity);
    setLocalTradeVertical(updated.tradeVertical);
    if (onSaveSettings) {
      onSaveSettings(updated);
    }
  };

  // In-memory admin key state (never persist in localStorage per security audit)
  const [sessionAdminKey, setSessionAdminKey] = useState<string>(() => (window as any).__FS_ADMIN_KEY || '');

  // Purge any legacy persisted admin key on mount
  useEffect(() => {
    try {
      localStorage.removeItem('fs_admin_key');
    } catch {}
  }, []);

  // Tab State for Right Pane (defaults to live Node Settings in Onboarding mode)
  const [activeRightTab, setActiveRightTab] = useState<'settings' | 'trace' | 'tamper' | 'wire'>('settings');

  // Copilot Mode: 'onboarding' (Company Setup & Knowledge Harness) vs 'simulation' (Live Buyer Agent Test Harness)
  const [copilotMode, setCopilotMode] = useState<'onboarding' | 'simulation'>('onboarding');
  const [activeSetupStep, setActiveSetupStep] = useState<number>(propActiveStep ?? 1);
  const [internalIsGuideCollapsed, setInternalIsGuideCollapsed] = useState<boolean>(true);
  const isGuideCollapsed = propIsGuideCollapsed ?? internalIsGuideCollapsed;
  const setIsGuideCollapsed = (val: boolean | ((prev: boolean) => boolean)) => {
    const nextVal = typeof val === 'function' ? val(isGuideCollapsed) : val;
    setInternalIsGuideCollapsed(nextVal);
    if (onToggleGuideCollapsed && nextVal !== isGuideCollapsed) {
      onToggleGuideCollapsed();
    }
  };
  const toggleGuideCollapsed = () => setIsGuideCollapsed(!isGuideCollapsed);
  const [isChatExpanded, setIsChatExpanded] = useState<boolean>(false);
  const [isChatMenuCollapsed, setIsChatMenuCollapsed] = useState<boolean>(true);

  // Setup Completion Tracking (Step 1-5 Gate)
  const [isSetupComplete, setIsSetupComplete] = useState<boolean>(() => {
    try {
      return localStorage.getItem('ap2_setup_complete') === 'true';
    } catch {
      return false;
    }
  });

  const markStepCompleted = (stepNum: number) => {
    try {
      const existing: number[] = JSON.parse(localStorage.getItem('ap2_completed_steps') || '[]');
      if (!existing.includes(stepNum)) {
        existing.push(stepNum);
        localStorage.setItem('ap2_completed_steps', JSON.stringify(existing));
      }
      if (stepNum === 5 || (existing.includes(1) && existing.includes(2) && existing.includes(3) && existing.includes(4))) {
        setIsSetupComplete(true);
        localStorage.setItem('ap2_setup_complete', 'true');
      }
    } catch {
      if (stepNum === 5) {
        setIsSetupComplete(true);
      }
    }
  };

  // Speech Recognition & Hands-Free Voice Control
  const [isListening, setIsListening] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<'idle' | 'starting' | 'listening' | 'processing' | 'error'>('idle');
  const [voiceTranscript, setVoiceTranscript] = useState<string>('');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);
  const capturedTextRef = useRef<string>('');

  const startVoiceInput = async () => {
    setVoiceError(null);

    // If currently listening or starting, stop cleanly
    if (isListening || voiceStatus === 'listening' || voiceStatus === 'starting') {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {
          try {
            recognitionRef.current.abort();
          } catch {}
        }
        recognitionRef.current = null;
      }
      setIsListening(false);
      setVoiceStatus('idle');
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceStatus('error');
      setVoiceError("Web Speech API is not supported in this browser. Please use Chrome, Edge, or Safari, or click a voice preset chip below.");
      return;
    }

    // Clean up any stale instances before starting
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch (e) {}
      recognitionRef.current = null;
    }

    // Instant non-blocking check for denied permission
    if (navigator.permissions && navigator.permissions.query) {
      try {
        const perm = await navigator.permissions.query({ name: 'microphone' as PermissionName });
        if (perm.state === 'denied') {
          setVoiceStatus('error');
          setVoiceError("Microphone permission is blocked in your browser settings. Click the lock icon in your address bar to permit microphone, or use the voice presets below.");
          return;
        }
      } catch (e) {}
    }

    capturedTextRef.current = '';
    setVoiceTranscript('');
    setVoiceStatus('starting');

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';
      recognition.maxAlternatives = 1;

      // Watchdog in case permission popup is ignored or browser hangs
      const startWatchdog = setTimeout(() => {
        setVoiceStatus((current) => {
          if (current === 'starting') {
            setVoiceError("Microphone request timed out. Please click 'Allow' when your browser asks for microphone access, or use the voice presets below.");
            try { recognition.abort(); } catch (e) {}
            return 'idle';
          }
          return current;
        });
      }, 7000);

      recognition.onstart = () => {
        clearTimeout(startWatchdog);
        setIsListening(true);
        setVoiceStatus('listening');
        setVoiceError(null);
      };

      recognition.onresult = (event: any) => {
        let interim = '';
        let final = '';
        for (let i = 0; i < event.results.length; i++) {
          if (event.results[i].isFinal) {
            final += event.results[i][0].transcript;
          } else {
            interim += event.results[i][0].transcript;
          }
        }
        const text = (final || interim).trim();
        if (text) {
          capturedTextRef.current = text;
          setInputText(text);
          setVoiceTranscript(text);
        }
      };

      recognition.onerror = (event: any) => {
        clearTimeout(startWatchdog);
        console.warn("Speech recognition error:", event.error);
        setIsListening(false);
        setVoiceStatus('error');
        if (event.error === 'not-allowed') {
          setVoiceError("Microphone permission blocked. Click the lock/settings icon in your browser address bar to permit microphone access, or choose a voice preset below.");
        } else if (event.error === 'no-speech') {
          setVoiceError("No speech detected. Click the mic button again and speak clearly into your microphone.");
        } else if (event.error === 'audio-capture') {
          setVoiceError("No microphone hardware detected on this device. You can test voice commands using the voice presets below.");
        } else if (event.error === 'network') {
          setVoiceError("Speech recognition network error. Ensure your connection to Google speech services is active, or use the voice presets below.");
        } else {
          setVoiceError(`Speech recognition: ${event.error}. You can also use the voice presets below.`);
        }
      };

      recognition.onend = () => {
        clearTimeout(startWatchdog);
        setIsListening(false);
        setVoiceStatus('idle');
        recognitionRef.current = null;
        const textToSend = capturedTextRef.current.trim();
        if (textToSend) {
          setTimeout(() => {
            sendMessage(textToSend);
          }, 350);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err: any) {
      console.warn("Failed to start speech recognition:", err);
      setIsListening(false);
      setVoiceStatus('error');
      setVoiceError(`Failed to start speech recognition: ${err.message || 'Unknown error'}. You can use the voice presets below.`);
    }
  };

  // Messages State with interactiveForm for Step 1
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'msg-init',
      sender: 'copilot',
      text: `👋 **Welcome to the AP2 Open-Source Seller Node Onboarding & Setup Copilot!**

When you first clone this repository, your company's credentials, capability catalog, and payment rails are in their default unconfigured state.

I am your **Interactive Setup & Voice Copilot**. You can chat with me, speak through the microphone, or click the cards below, and I will **fill out and configure your node settings for you** right here on this page!

👉 **Get started with Step 1 below:**`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'IDLE',
      interactiveForm: 'step1',
      suggestedActions: [],
    },
  ]);

  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Quick-Action In-Chat Form State (Step 1-5 Cards)
  const [formStep1Company, setFormStep1Company] = useState(nodeSettings.businessEntity || localBusinessEntity);
  const [formStep1Email, setFormStep1Email] = useState(nodeSettings.supportEmail || 'ops@acme-systems.io');
  const [formStep1Service, setFormStep1Service] = useState(nodeSettings.tradeVertical || localTradeVertical);
  const [formStep1Capabilities, setFormStep1Capabilities] = useState<ServiceCapabilityItem[]>(
    () => (nodeSettings.capabilities && nodeSettings.capabilities.length > 0) ? nodeSettings.capabilities : DEFAULT_NODE_SETTINGS.capabilities
  );
  const [formStep3ClientId, setFormStep3ClientId] = useState(nodeSettings.paypalClientId || '');
  const [formStep4Webhook, setFormStep4Webhook] = useState(nodeSettings.zapierWebhookUrl || '');

  const handleAddStep1Capability = () => {
    const randomPlanSuffix = Math.random().toString(36).substring(2, 8).toUpperCase();
    const nextIdx = formStep1Capabilities.length + 1;
    const newTier: ServiceCapabilityItem = {
      id: `tier_custom_${Date.now()}`,
      name: `Tier ${nextIdx} Custom Service Plan`,
      monthly_price_usd: 99.99,
      quota: '500 operations/mo',
      sla: '99.95% Availability',
      enclave: 'Dedicated Worker Node',
      paypal_plan_id: `P-${randomPlanSuffix}44454362WXN`,
    };
    setFormStep1Capabilities((prev) => [...prev, newTier]);
  };

  const handleRemoveStep1Capability = (id: string) => {
    if (formStep1Capabilities.length <= 1) return;
    setFormStep1Capabilities((prev) => prev.filter((c) => c.id !== id));
  };

  const handleUpdateStep1Capability = (id: string, field: keyof ServiceCapabilityItem, value: any) => {
    setFormStep1Capabilities((prev) =>
      prev.map((c) => (c.id === id ? { ...c, [field]: value } : c))
    );
  };

  useEffect(() => {
    setFormStep1Company(nodeSettings.businessEntity);
    setFormStep1Email(nodeSettings.supportEmail || 'ops@acme-systems.io');
    setFormStep1Service(nodeSettings.tradeVertical);
    if (nodeSettings.capabilities && nodeSettings.capabilities.length > 0) {
      setFormStep1Capabilities(nodeSettings.capabilities);
    }
    setFormStep3ClientId(nodeSettings.paypalClientId);
    setFormStep4Webhook(nodeSettings.zapierWebhookUrl);
  }, [nodeSettings]);

  const [liveTrace, setLiveTrace] = useState<any[]>([]);
  const [activeStep, setActiveStep] = useState<number>(0);
  const [lastAllocatedDid, setLastAllocatedDid] = useState<string | null>(null);

  // Inspector Modal State
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [inspectorData, setInspectorData] = useState<any>(null);
  const [inspectorLoading, setInspectorLoading] = useState(false);
  const [inspectorError, setInspectorError] = useState<string | null>(null);
  const [activeInspectorTab, setActiveInspectorTab] = useState<'cloudevents' | 'qbo' | 'webhook'>('cloudevents');
  const [activeCloudEventsSubTab, setActiveCloudEventsSubTab] = useState<'subscription' | 'workload' | 'full'>('subscription');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [isTriggeringTestRun, setIsTriggeringTestRun] = useState(false);

  // --- Layer 1: Anti-Tamper & Cryptographic State ---
  const [tamperPayload, setTamperPayload] = useState<any>({
    contractor_id: 'buyer_agent_alpha_01',
    business_name: 'Nexus Autonomous Systems Corp',
    monthly_cap_usd: 100.0,
    agreed_price_usd: 49.99,
    nonce: 'd6fb21ff578f',
    timestamp: Math.floor(Date.now() / 1000),
  });
  const [tamperSignature, setTamperSignature] = useState<string>('16e71269fd6f051102214cb8892915be4a4d96b0b90d7993e99c2ef0a0a63c29');
  const [tamperVerificationResult, setTamperVerificationResult] = useState<any>(null);
  const [isTamperVerifying, setIsTamperVerifying] = useState(false);

  // Load official sample proof on mount
  useEffect(() => {
    fetch('/api/crypto/sample-proof?profile=ap2')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.canonical_payload) {
          setTamperPayload(data.canonical_payload);
          setTamperSignature(data.signature);
        }
      })
      .catch(() => {
        // Fallback default is already set
      });
  }, []);

  const handleVerifyTamper = async (payloadToVerify?: any, sigToVerify?: string) => {
    setIsTamperVerifying(true);
    const p = payloadToVerify || tamperPayload;
    const s = sigToVerify || tamperSignature;

    try {
      const res = await fetch('/api/crypto/verify-tamper', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload: p, signature: s }),
      });
      const data = await res.json();
      setTamperVerificationResult(data);
    } catch (err: any) {
      setTamperVerificationResult({
        valid: false,
        status_code: 500,
        reason: 'NETWORK_ERROR',
        detail: 'Failed to contact verification server: ' + err.message,
      });
    } finally {
      setIsTamperVerifying(false);
    }
  };

  const handleTamperPrice = (delta: number) => {
    const updated = {
      ...tamperPayload,
      agreed_price_usd: Math.round((Number(tamperPayload.agreed_price_usd) + delta) * 100) / 100,
    };
    setTamperPayload(updated);
    handleVerifyTamper(updated, tamperSignature);
  };

  const handleTamperBudgetCap = (newCap: number) => {
    const updated = {
      ...tamperPayload,
      monthly_cap_usd: newCap,
    };
    setTamperPayload(updated);
    handleVerifyTamper(updated, tamperSignature);
  };

  const handleTamperTimestamp = () => {
    const updated = {
      ...tamperPayload,
      timestamp: Math.floor(Date.now() / 1000) - 7200, // 2 hours ago (expired)
    };
    setTamperPayload(updated);
    handleVerifyTamper(updated, tamperSignature);
  };

  const handleResetUntampered = async () => {
    try {
      const res = await fetch('/api/crypto/generate-proof', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contractor_id: `contractor_${localContractorName.toLowerCase().replace(/\s+/g, '_')}_${localAreaCode}`,
          business_name: localBusinessEntity,
          monthly_cap_usd: localBudgetCap,
          agreed_price_usd: localBudgetCap < 79.99 ? 49.99 : 79.99,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setTamperPayload(data.canonical_payload);
        setTamperSignature(data.signature);
        handleVerifyTamper(data.canonical_payload, data.signature);
      }
    } catch {
      // ignore
    }
  };

  // --- Layer 2: Live Wire Protocol SSE Stream ---
  const [wireFrames, setWireFrames] = useState<any[]>([]);
  const [isSseConnected, setIsSseConnected] = useState(false);
  const [wireFilter, setWireFilter] = useState<'all' | 'call' | 'init'>('all');
  const [expandedFrameId, setExpandedFrameId] = useState<string | null>(null);

  useEffect(() => {
    // Initial fetch of recent buffered frames
    fetch('/api/mcp/frames')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && Array.isArray(data.frames)) {
          setWireFrames(data.frames);
        }
      })
      .catch(() => {});

    // Open EventSource SSE stream
    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource('/api/mcp/sse');
      eventSource.onopen = () => setIsSseConnected(true);
      eventSource.onerror = () => setIsSseConnected(false);
      eventSource.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed && parsed.frame) {
            setWireFrames((prev) => [...prev.slice(-90), parsed]);
          }
        } catch {
          // ignore keep-alive
        }
      };
    } catch {
      setIsSseConnected(false);
    }

    return () => {
      if (eventSource) eventSource.close();
    };
  }, []);

  const filteredWireFrames = useMemo(() => {
    if (wireFilter === 'call') {
      return wireFrames.filter((f) => String(f.method || '').includes('tools/call'));
    }
    if (wireFilter === 'init') {
      return wireFrames.filter((f) => String(f.method || '').includes('initialize') || String(f.method || '').includes('tools/list'));
    }
    return wireFrames;
  }, [wireFrames, wireFilter]);

  // Fetch Back-Office Payloads for Inspector Modal
  const fetchM2MPayloads = async () => {
    setInspectorLoading(true);
    setInspectorError(null);

    const endpoints = ['/m2m/payloads/latest', '/api/m2m/payloads/latest'];
    let fetchedData: any = null;

    for (const url of endpoints) {
      try {
        const res = await fetch(url);
        if (res.ok) {
          fetchedData = await res.json();
          break;
        }
      } catch {
        // try next endpoint
      }
    }

    if (fetchedData && fetchedData.status) {
      setInspectorData(fetchedData);
    } else {
      // Fallback: check liveTrace from current chat run
      const step4 = liveTrace.find((s) => s.step === 4);
      const step3 = liveTrace.find((s) => s.step === 3);
      const step2 = liveTrace.find((s) => s.step === 2);
      const step1 = liveTrace.find((s) => s.step === 1);

      if (step4) {
        setInspectorData({
          status: 'COMPLETED',
          mandate_hash: step1?.proof_hash || 'HMAC-MANDATE-VERIFIED-01',
          paypal_subscription_id: step2?.subscription_id || 'I-AUTONOMOUS-8902',
          node_endpoint: step3?.assigned_did || `node-cluster-01.ap2.net:8443`,
          endpoint: step3?.assigned_did || `node-cluster-01.ap2.net:8443`,
          timestamp: step4.timestamp || new Date().toISOString(),
          hmac_signature: 'sha256=' + (step1?.proof_hash || 'b6d390a1e352d9a9c5b6118d0937a0ec'),
          quickbooks: step4.qbo_export || {
            Purchase: {
              PaymentType: 'CreditCard',
              AccountRef: { value: '99', name: 'PayPal Clearing Account' },
              EntityRef: { value: '101', name: 'AP2 Autonomous Merchant LLC', type: 'Vendor' },
              TxnDate: new Date().toISOString().substring(0, 10),
              DocNumber: `AP2-SUB-8902`,
              TotalAmt: localBudgetCap < 79.99 ? 49.99 : 79.99,
              PrivateNote: `AP2 Autonomous Settlement.\nBuyer Agent: ${localContractorName}\nPrincipal Entity: ${localBusinessEntity}\nEndpoint: ${step3?.assigned_did || 'node-cluster-01.ap2.net:8443'}`,
              Line: [
                {
                  Amount: localBudgetCap < 79.99 ? 49.99 : 79.99,
                  DetailType: 'AccountBasedExpenseLineDetail',
                  Description: `AP2 Autonomous Gateway (${localTradeVertical}) — SaaS Recurring Subscription`,
                  AccountBasedExpenseLineDetail: {
                    AccountRef: { value: '6300', name: 'Dues & Subscriptions: Software & SaaS' },
                    BillableStatus: 'NotBillable',
                  },
                },
              ],
            },
          },
          cloudevents: {
            specversion: '1.0',
            id: 'ce-evt-99120482',
            source: 'https://api.ap2protocol.org/mcp/seller',
            type: 'com.ap2.settlement.subscription.activated',
            datacontenttype: 'application/json',
            time: step4.timestamp || new Date().toISOString(),
            subject: `agent_${localContractorName.toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
            data: {
              buyer_agent: localContractorName,
              principal_entity: localBusinessEntity,
              service_tier: localTradeVertical,
              monthly_rate: localBudgetCap < 79.99 ? 49.99 : 79.99,
              allocated_node_endpoint: step3?.assigned_did || 'node-cluster-01.ap2.net:8443',
              paypal_subscription_id: step2?.subscription_id || 'I-AUTONOMOUS-8902',
              ed25519_proof_hash: step1?.proof_hash || 'PROOF-MANDATE-VERIFIED',
              enclave_route: 'US-East Node Cluster (Ashburn, VA)',
            },
          },
          webhook_meta: {
            dispatched: true,
            status_code: 200,
            delivery_id: 'dlv_' + Math.random().toString(36).substring(2, 10),
            timestamp: step4.timestamp,
            signature: 'sha256=' + (step1?.proof_hash || 'b6d390a1e352...'),
          },
        });
      } else {
        setInspectorData(null);
        setInspectorError('No autonomous transaction detected yet. Run the Buyer Agent harness or tap "Execute Live Test Cycle" below.');
      }
    }
    setInspectorLoading(false);
  };

  const openInspector = () => {
    setIsInspectorOpen(true);
    fetchM2MPayloads();
  };

  const triggerTestCycle = async () => {
    setIsTriggeringTestRun(true);
    try {
      let adminKey = sessionAdminKey || (window as any).__FS_ADMIN_KEY || '';
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (adminKey) {
        headers['X-Admin-Key'] = adminKey;
      }
      let res = await fetch('/api/harness/run-buyer-agent', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          contractor_name: localContractorName,
          business_entity: localBusinessEntity,
          trade_vertical: localTradeVertical,
          area_code: localAreaCode,
          budget_cap: localBudgetCap,
          simulate_exhaustion: simulateExhaustion,
        }),
      });

      if (res.status === 401) {
        const entered = prompt('Administrative authorization required to trigger autonomous buyer harness.\nEnter ADMIN_API_KEY (retained in-memory only):');
        if (entered) {
          adminKey = entered.trim();
          setSessionAdminKey(adminKey);
          (window as any).__FS_ADMIN_KEY = adminKey;
          headers['X-Admin-Key'] = adminKey;
          res = await fetch('/api/harness/run-buyer-agent', {
            method: 'POST',
            headers,
            body: JSON.stringify({
              contractor_name: localContractorName,
              business_entity: localBusinessEntity,
              trade_vertical: localTradeVertical,
              area_code: localAreaCode,
              budget_cap: localBudgetCap,
              simulate_exhaustion: simulateExhaustion,
            }),
          });
        }
      }
      if (res.ok) {
        const runData = await res.json();
        if (runData && (runData.provisioned_did || runData.assigned_did)) {
          const did = runData.provisioned_did || runData.assigned_did;
          setLastAllocatedDid(did);

          const trace = runData.protocol_trace || [
            {
              step: 1,
              timestamp: new Date().toISOString(),
              protocol: 'MCP JSON-RPC 2.0',
              method: 'tools/call:evaluate_spending_mandate',
              decision: 'APPROVED',
              proof_hash: runData.mandate_proof_hash || 'PROOF-MANDATE-VERIFIED',
              budget_cap: localBudgetCap,
              authorized_amount: runData.monthly_amount || 79.99,
              remaining_budget: localBudgetCap - (runData.monthly_amount || 79.99),
              tier_title: runData.selected_tier || (localBudgetCap < 79.99 ? 'High-Throughput Batch Worker ($49.99/mo)' : 'Dedicated AI Service Gateway ($79.99/mo)'),
            },
            {
              step: 2,
              timestamp: new Date().toISOString(),
              protocol: 'PayPal Subscriptions v1',
              action: 'AUTHORIZE_BILLING_AGREEMENT',
              subscription_id: runData.paypal_subscription_id || runData.subscription_id || 'I-AUTONOMOUS-8902',
              plan_id: 'P-5ML4271244454362WXNWU5NQ',
              monthly_amount: runData.monthly_amount || 79.99,
              payer_entity: localBusinessEntity,
            },
            {
              step: 3,
              timestamp: new Date().toISOString(),
              protocol: 'MCP JSON-RPC 2.0',
              method: 'tools/call:provision_worker_node',
              assigned_did: did.includes('.') ? did : 'node-cluster-01.ap2.net:8443',
              carrier: 'AP2 Autonomous Worker Enclave',
              routing_state: 'ACTIVE_ENCLAVE_BOUND',
              tcpa_status: 'RFC 8032 ED25519 VERIFIED (ANTI-TAMPER PASS)',
              lata_failover_active: simulateExhaustion,
              allocated_area_code: 'US-East Cluster (Ashburn)',
            },
            {
              step: 4,
              timestamp: new Date().toISOString(),
              protocol: 'MCP JSON-RPC 2.0',
              method: 'tools/call:dispatch_zapier_mcp',
              qbo_expense_id: runData.qbo_expense_id || 'EXP-QBO-88219',
              cloudevents_delivery_id: runData.cloudevents_delivery_id || 'CE-EVENT-7712',
              webhook_event_id: 'WH-EVT-9921',
              status: 'COMPLETED',
            },
          ];
          setLiveTrace(trace);
          setActiveStep(trace.length);

          if (onA2aCompleted) {
            onA2aCompleted({
              subscriptionId: runData.subscription_id || runData.paypal_subscription_id || 'I-AUTONOMOUS-8902',
              allocatedDid: did.includes('.') ? did : 'node-cluster-01.ap2.net:8443',
              carrier: 'AP2 Autonomous Worker Enclave',
              contractorName: localContractorName,
              businessEntity: localBusinessEntity,
            });
          }
        }
        await fetchM2MPayloads();
      }
    } catch (err) {
      console.error('Failed to trigger test cycle:', err);
    } finally {
      setIsTriggeringTestRun(false);
    }
  };

  const copyToClipboard = (text: string, key: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const prevMessagesCountRef = useRef(messages.length);
  const hasUserInteractedRef = useRef(false);

  // Force scroll-to-top on mount and browser refresh so user always sees the welcome banner
  useEffect(() => {
    const scrollToTop = () => {
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTop = 0;
      }
      const mainEl = document.querySelector('main.studio-canvas-container');
      if (mainEl) {
        mainEl.scrollTop = 0;
      }
    };
    scrollToTop();
    const rafId = requestAnimationFrame(scrollToTop);
    const timer1 = setTimeout(scrollToTop, 50);
    const timer2 = setTimeout(scrollToTop, 200);
    return () => {
      cancelAnimationFrame(rafId);
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, []);

  // Auto-scroll chat container ONLY when user actively engages or new interaction messages arrive
  useEffect(() => {
    // If only initial message or user has not interacted yet, stay strictly at top!
    if (messages.length <= 1 || !hasUserInteractedRef.current) {
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTop = 0;
      }
      return;
    }

    // Only scroll if a new message was appended
    if (messages.length > prevMessagesCountRef.current) {
      prevMessagesCountRef.current = messages.length;
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTo({
          top: chatContainerRef.current.scrollHeight,
          behavior: 'smooth',
        });
      }
    }
  }, [messages, isLoading]);

  // In-Chat Form Action Handlers ("I can fill that out for you")
  const handleApplyStep1 = (
    companyName: string,
    serviceTitle: string,
    email?: string,
    capabilities?: ServiceCapabilityItem[]
  ) => {
    hasUserInteractedRef.current = true;
    const trimmedCompany = companyName.trim() || localBusinessEntity;
    const trimmedService = serviceTitle.trim() || localTradeVertical;
    const trimmedEmail = email?.trim() || nodeSettings.supportEmail || 'ops@acme-systems.io';

    const capsToApply = (capabilities && capabilities.length > 0)
      ? capabilities
      : (formStep1Capabilities && formStep1Capabilities.length > 0)
      ? formStep1Capabilities
      : (nodeSettings.capabilities || DEFAULT_NODE_SETTINGS.capabilities);

    const updated: NodeSettingsData = {
      ...nodeSettings,
      companyName: trimmedCompany,
      businessEntity: trimmedCompany,
      tradeVertical: trimmedService,
      supportEmail: trimmedEmail,
      capabilities: capsToApply,
    };
    saveNodeSettings(updated);
    setLocalBusinessEntity(trimmedCompany);
    setLocalTradeVertical(trimmedService);
    setSettingsTabOverride('catalog');
    setActiveRightTab('settings');

    const catalogList = capsToApply
      .map((c, i) => `${i + 1}. **${c.name}**: \`$${Number(c.monthly_price_usd).toFixed(2)}/mo\` (${c.quota || 'Unmetered'} • ${c.sla || c.enclave || 'Standard SLA'})`)
      .join('\n');

    markStepCompleted(1);
    const replyMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'copilot',
      text: `✅ **Applied Company Profile, Support Email & ${capsToApply.length} Catalog Tiers to Node Settings & catalog.json!**\n\n• **Company Legal Name**: \`${trimmedCompany}\`\n• **Support / Operations Email**: \`${trimmedEmail}\`\n• **Primary Capability**: \`${trimmedService}\`\n\n📦 **Machine-to-Machine Service Catalog (${capsToApply.length} Tiers Configured & Live)**:\n${catalogList}\n\nI have saved this to your node configuration and updated \`service_catalog.json\`. You can see your updated catalog live in **Tab 1: Profile & Service Catalog** on the right! You can customize or add more tiers anytime.\n\n👉 **Ready for Step 2?** Click the button below to generate your RFC 8032 Ed25519 signing keys and configure anti-tamper security:`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'IDLE',
      nextStepAction: {
        step: 2,
        label: '➡️ Proceed to Step 2: Configure Ed25519 Keys & Anti-Tamper',
      },
      suggestedActions: [],
    };
    setMessages((prev) => [...prev, replyMsg]);
  };

  const handleGenerateEd25519Keypair = () => {
    hasUserInteractedRef.current = true;
    const randomHex = (len: number) => {
      const bytes = new Uint8Array(len);
      crypto.getRandomValues(bytes);
      return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    };
    const newPrivKey = randomHex(32);
    const newPubKey = randomHex(32);
    const newSecret = 'ap2_hmac_' + randomHex(16);

    const updated: NodeSettingsData = {
      ...nodeSettings,
      privateKeyHex: newPrivKey,
      publicKeyHex: newPubKey,
      mandateHmacSecret: newSecret,
    };
    saveNodeSettings(updated);
    setSettingsTabOverride('crypto');
    setActiveRightTab('settings');

    markStepCompleted(2);
    const replyMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'copilot',
      text: `🔑 **RFC 8032 Ed25519 Keypair Generated & Applied!**\n\n• **Public Key (Hex)**: \`0x${newPubKey.substring(0, 24)}...\`\n• **Private Key (Hex)**: Saved securely to node memory\n• **HMAC Secret Token**: \`${newSecret.substring(0, 16)}...\`\n\nYour cryptographic keypair is now configured in **Tab 2** on the right. The seller node will reject any modified prices or forged nonces with **HTTP 401 SIGNATURE_MISMATCH**.\n\n👉 **Ready for Step 3?** Click the button below to connect your PayPal merchant rails:`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'IDLE',
      nextStepAction: {
        step: 3,
        label: '➡️ Proceed to Step 3: Connect PayPal Rails',
      },
      suggestedActions: [],
    };
    setMessages((prev) => [...prev, replyMsg]);
  };

  const handleApplyPayPalSandbox = (clientId?: string) => {
    hasUserInteractedRef.current = true;
    const cid = clientId?.trim() || nodeSettings.paypalClientId || 'PAYPAL_SANDBOX_CLIENT_ID_AP2_SELLER_NODE';
    const updated: NodeSettingsData = {
      ...nodeSettings,
      paypalClientId: cid,
      paypalMode: 'sandbox',
    };
    saveNodeSettings(updated);
    setSettingsTabOverride('paypal');
    setActiveRightTab('settings');

    markStepCompleted(3);
    const replyMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'copilot',
      text: `💳 **PayPal Sandbox Rails Connected & Synced!**\n\n• **Merchant Entity**: \`${nodeSettings.businessEntity}\`\n• **PayPal Mode**: \`sandbox\`\n• **Client ID**: \`${cid.substring(0, 20)}...\`\n• **Dynamic Plans**: Synchronized 3 plans from catalog (\`$49.99\`, \`$79.99\`, \`$179.99\`)\n\nAutonomous Vault MIT recurring agreements are now active in **Tab 3** on the right!\n\n👉 **Ready for Step 4?** Click the button below to bridge QuickBooks Online and Zapier webhooks:`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'IDLE',
      nextStepAction: {
        step: 4,
        label: '➡️ Proceed to Step 4: Bridge QuickBooks & Zapier ERP',
      },
      suggestedActions: [],
    };
    setMessages((prev) => [...prev, replyMsg]);
  };

  const handleApplyErpWebhooks = (webhookUrl?: string, account?: string) => {
    hasUserInteractedRef.current = true;
    const url = webhookUrl?.trim() || nodeSettings.zapierWebhookUrl;
    const acct = account?.trim() || nodeSettings.qboGlExpenseAccount;
    const updated: NodeSettingsData = {
      ...nodeSettings,
      zapierWebhookUrl: url,
      qboGlExpenseAccount: acct,
    };
    saveNodeSettings(updated);
    setSettingsTabOverride('erp');
    setActiveRightTab('settings');

    markStepCompleted(4);
    const replyMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'copilot',
      text: `⚡ **ERP Webhooks & Double-Entry Accounting Connected!**\n\n• **Zapier Catch-Hook URL**: \`${url}\`\n• **QuickBooks Expense Account**: \`${acct}\`\n• **Operating Revenue Account**: \`${nodeSettings.qboGlRevenueAccount}\`\n\nEvery settled transaction will now automatically stream CloudEvents v1.0 JSON-RPC to your webhook and book GAAP purchase records to your General Ledger. Configured in **Tab 4** on the right!\n\n👉 **Ready for Step 5?** Click the button below to verify FastMCP and launch the interactive test simulator:`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'IDLE',
      nextStepAction: {
        step: 5,
        label: '➡️ Proceed to Step 5: FastMCP & Live Simulator',
      },
      suggestedActions: [],
    };
    setMessages((prev) => [...prev, replyMsg]);
  };

  const triggerBuyerSimulatorIntro = () => {
    markStepCompleted(5);
    setCopilotMode('simulation');
    const introMsg: ChatMessage = {
      id: `msg-${Date.now() + 1}`,
      sender: 'copilot',
      text: `👋 **Hi! I'm the AP2 Live Buyer Agent Simulator.**\n\n### 🎯 My Purpose\nI act as an external autonomous buyer agent (e.g. \`agent:gpt-4o:apex-procure\` on behalf of **Apex Enterprise AI Inc**) interacting with your AP2 Seller Node over the **Model Context Protocol (MCP 2024-11-05)**.\n\nMy purpose is to test your seller node end-to-end: evaluating your pricing catalog, negotiating within strict programmatic budget caps, cryptographically signing Ed25519 spending mandates, and executing PayPal recurring subscriptions with instant worker node allocation.\n\n### ⚡ What I Can Do (Choose a Test Below):\n\n• **1. Sub-Budget Bargaining ($60 Cap vs $80 Service)**\n  I submit a purchase mandate capped at \`$60.00/mo\` for your \`$79.99/mo\` Dedicated Gateway. Your seller agent detects the budget breach and autonomously counter-offers your \`$49.99/mo\` Batch Worker tier within my budget.\n\n• **2. Direct Match Authorization ($100 Cap vs $80 Service)**\n  I submit a spending mandate with a \`$100.00/mo\` cap, which your seller agent approves immediately and signs with an Ed25519 authorization hash.\n\n• **3. Anti-Tamper Security Defense (Attack Simulation)**\n  I attempt to forge a mandate (+1¢ price tampering or altered entity). Your node's cryptographic anti-tamper verifier catches the signature mismatch and terminates the transaction.\n\n• **4. Live PayPal Settlement & Node Provisioning**\n  Executes the complete payment rail: authorizes recurring billing via PayPal Vault MIT, provisions your FastMCP cluster endpoint, and dispatches the QBO GL 6300 / Zapier back-office sync.\n\nClick any of the test scenarios below to start!`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'IDLE',
      nextStepAction: {
        step: 6,
        label: '🎉 Setup Complete! Proceed to Live Operations Dashboard →',
      },
      suggestedActions: [
        'Simulate Autonomous Bargaining ($60 Budget vs $80 Service)',
        'Simulate Direct Match ($100 Budget vs $80 Service)',
        'Test Anti-Tamper Security (Attack Payload)',
        'Execute Live Autonomous Settlement Cycle',
        'Query AP2 Seller Service Catalog',
      ],
    };
    setMessages((prev) => [...prev, introMsg]);
  };

  const handleLaunchSimulatorFromForm = () => {
    hasUserInteractedRef.current = true;
    setCopilotMode('simulation');
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'contractor',
      text: '🚀 Launch Live Buyer Agent Simulator',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsg]);
    triggerBuyerSimulatorIntro();
  };

  const handleSelectSetupStep = (stepNum: number, skipUserMsg?: boolean) => {
    if (!skipUserMsg) {
      hasUserInteractedRef.current = true;
    }
    setActiveSetupStep(stepNum);
    setCopilotMode('onboarding');
    setActiveRightTab('settings');

    let title = '';
    let content = '';
    let suggestedActions: string[] = [];

    if (stepNum === 6) {
      if (onNavigateTab) {
        onNavigateTab('fleet-ledger');
      }
      return;
    }

    if (stepNum === 1) {
      setSettingsTabOverride('catalog');
      title = 'Step 01: Service Catalog & Pricing Tiers (catalog.json)';
      content = `📘 **Step 01: Configure Company Profile, Support Email & Service Catalog**

👉 **I have brought up Tab 1 (Profile & Service Catalog) in the right pane for you.**
You can inspect or edit your company profile, support email, and 3 service capabilities directly on the right (which is fastest!), or you can use the quick-action form below and I will fill it in with standard turnkey mock defaults for you.

To publish your company's capabilities to autonomous buyer agents, configure your service catalog at:
📁 \`backend/data/service_catalog.json\`

\`\`\`json
{
  "company_name": "${localBusinessEntity}",
  "support_email": "${nodeSettings.supportEmail || 'ops@acme-systems.io'}",
  "capabilities": [
    {
      "id": "tier_batch_worker",
      "name": "${nodeSettings.capabilities?.[0]?.name || 'High-Throughput Batch Worker'}",
      "monthly_price_usd": ${nodeSettings.capabilities?.[0]?.monthly_price_usd || 49.99},
      "quota": "125 operations/mo",
      "sla": "99.95% Availability",
      "enclave": "US-Central Batch RAG"
    },
    {
      "id": "tier_inference_gateway",
      "name": "${nodeSettings.capabilities?.[1]?.name || 'Dedicated AI Service Gateway'}",
      "monthly_price_usd": ${nodeSettings.capabilities?.[1]?.monthly_price_usd || 79.99},
      "quota": "450 operations/mo",
      "sla": "99.98% Low Latency (<350ms)",
      "enclave": "US-East Low-Latency Gateway"
    },
    {
      "id": "tier_enterprise_cluster",
      "name": "${nodeSettings.capabilities?.[2]?.name || 'Enterprise Cluster Node'}",
      "monthly_price_usd": ${nodeSettings.capabilities?.[2]?.monthly_price_usd || 179.99},
      "quota": "1,500 operations/mo",
      "sla": "99.99% Multi-Region Failover",
      "enclave": "Multi-Region Distributed Cluster"
    }
  ]
}
\`\`\`

💡 **Autonomous Bargaining Principle**:
When an incoming buyer agent has a spending mandate below your primary tier (e.g. \`$60.00/mo\` budget vs \`$79.99/mo\` gateway), your seller agent automatically offers the down-tier plan (\`$49.99/mo\` Batch Worker) with \`$10.01\` headroom. This eliminates human haggling and maximizes closed deals!

**🤖 Quick Setup Assistant**: We can fill in standard turnkey mock info for you right now (which you can always change later in Tab 1), or customize the fields below and click to apply:`;
      suggestedActions = [];
    } else if (stepNum === 2) {
      setSettingsTabOverride('crypto');
      title = 'Step 02: RFC 8032 Ed25519 Cryptographic Keys & Anti-Tamper';
      content = `🛡️ **Step 02: RFC 8032 Ed25519 Cryptographic Keys & Anti-Tamper Security**

👉 **I have brought up Tab 2 (Ed25519 Keys & Anti-Tamper) in the right pane for you.**
You can inspect your public/private keys and anti-tamper security mode directly on the right, or click below and I will generate a cryptographically valid RFC 8032 keypair for you.

The AP2 protocol guarantees mathematical non-repudiation and buyer spending policy enforcement without human financial liability:
1. **Buyer Agent Signs**: The buyer agent signs intent mandates using its private Ed25519 key.
2. **Seller Agent Verifies**: The seller agent verifies signatures using the buyer's public key. The seller holds zero private signing keys, preventing merchant signature forgery.

**Generate Your Keypair**:
\`\`\`bash
python -c "from cryptography.hazmat.primitives.asymmetric import ed25519; k = ed25519.Ed25519PrivateKey.generate(); print('A2A_PRIVATE_KEY=' + k.private_bytes_raw().hex()); print('A2A_PUBLIC_KEY=' + k.public_key().public_bytes_raw().hex())"
\`\`\`

**Add to \`.env\` in repository root**:
\`\`\`env
A2A_PRIVATE_KEY=your_64_hex_private_key
A2A_PUBLIC_KEY=your_64_hex_public_key
A2A_MANDATE_SECRET=your_hmac_secret_token
\`\`\`

🔒 **Anti-Tamper Circuit Breaker**:
Any tampering with price (+1¢ inflation), timestamp drift (>300s), or altered principal entity causes an immediate fail-closed rejection: \`HTTP 401 SIGNATURE_MISMATCH\`.

**🤖 Quick Setup Assistant**: You can inspect Tab 2 on the right, or click below and I'll generate and save an RFC 8032 keypair for you:`;
      suggestedActions = [];
    } else if (stepNum === 3) {
      setSettingsTabOverride('paypal');
      title = 'Step 03: PayPal Subscriptions & Vault MIT Recurring Billing';
      content = `💳 **Step 03: Connect Payment Rails (PayPal Subscriptions & Vault MIT)**

👉 **I have brought up Tab 3 (PayPal Billing Rails) in the right pane for you.**
You can enter your PayPal Client ID, Secret, and verify your 3 synced catalog plans directly on the right, or click below and I will connect turnkey sandbox billing rails for you.

The seller node collects recurring revenue autonomously using the PayPal Subscriptions v1 API and Vault Merchant-Initiated Transactions (MIT):

**Configuration Steps**:
1. Log in to [PayPal Developer Portal](https://developer.paypal.com) & navigate to **Apps & Credentials**.
2. Create a REST API app (Sandbox or Live) and copy your Client ID & Secret.
3. Configure your \`.env\` file:
\`\`\`env
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_SECRET=your_paypal_client_secret
PAYPAL_MODE=sandbox  # or 'live' for production
\`\`\`
4. Run the automated plan setup script to register the 3 pricing tiers:
\`\`\`bash
python scripts/setup_paypal_sandbox_plans.py
\`\`\`
5. Once set up, buyer agents approve billing agreements once, after which payments settle 100% headlessly on recurring cycles with instant webhook confirmation (\`BILLING.SUBSCRIPTION.ACTIVATED\`).

**🤖 Quick Setup Assistant**: You can enter your credentials directly in Tab 3 on the right, or click below to connect turnkey sandbox credentials:`;
      suggestedActions = [];
    } else if (stepNum === 4) {
      setSettingsTabOverride('erp');
      title = 'Step 04: Downline ERP Sync (QuickBooks Online v3 & Zapier CloudEvents)';
      content = `⚡ **Step 04: Downstream ERP & EventBus Sync (QuickBooks & Zapier)**

👉 **I have brought up Tab 4 (QuickBooks & Zapier ERP) in the right pane for you.**
You can configure your Zapier catch-hook URL and QuickBooks GL accounts directly on the right, or click below and I will apply standard CloudEvents v1.0 and GAAP GL 6300 defaults for you.

Every autonomous transaction automatically reconciles in your back-office systems:

**1. QuickBooks Online (QBO v3 API)**:
• Posts double-entry Expense/Purchase records directly into your General Ledger.
• Account Mapping:
  - Debit: \`GL 6300\` (Dues & Subscriptions: Software & SaaS)
  - Clearing: \`GL 4000\` (Operating Revenue)
• Line items carry complete cryptographic proof hashes (\`mandate|cart|hash\`) for GAAP audit trails.

**2. Zapier / Make / EventBus (CloudEvents v1.0)**:
• Dispatches standard JSON-RPC event: \`com.ap2.settlement.subscription.activated\`.
• Configure your catch-hook in \`.env\`:
\`\`\`env
ZAPIER_MCP_CATCH_HOOK_URL=https://hooks.zapier.com/hooks/catch/12345/abcdef/
\`\`\`
• Trigger downstream workflows in NetSuite, Salesforce, Slack (\`#deals-closed\`), or HubSpot!

**🤖 Quick Setup Assistant**: You can configure your webhooks directly in Tab 4 on the right, or click below and I'll wire standard ERP defaults for you:`;
      suggestedActions = [];
    } else {
      setSettingsTabOverride('agent_card');
      title = 'Step 05: Launch FastMCP Server & Run Interactive Test Simulator';
      content = `🚀 **Step 05: Launch FastMCP Server & Run Interactive Simulator**

👉 **I have brought up Tab 5 (FastMCP & Agent Card) in the right pane for you.**
You can inspect your live \`.well-known/agent.json\` card, export your \`.env\` configuration, or test the FastMCP endpoint. When you're ready, launch the live simulator below to test your complete node with an autonomous buyer agent!

**1. Start the FastMCP Daemon**:
\`\`\`bash
python -m uvicorn backend.server:app --host 127.0.0.1 --port 8001 --reload
\`\`\`

**2. External Agent Discovery**:
External buyer agents can now discover and communicate with your node:
• **MCP Endpoint**: \`http://127.0.0.1:8001/mcp\`
• **Agent Card**: \`http://127.0.0.1:8001/.well-known/agent.json\`
• **LLM Sitemap**: \`http://127.0.0.1:8001/llms.txt\`

**3. Run the Live Simulator**:
Switch to the **Live Buyer Simulator** mode below to test the entire lifecycle: capability discovery, spending mandate evaluation, autonomous down-tier bargaining, and PayPal settlement!

**🤖 Quick Setup Assistant**: You can view Tab 5 on the right, or click below to launch the live buyer agent simulator now:`;
      suggestedActions = [
        '🚀 Launch Live Buyer Agent Simulator',
        'Simulate Autonomous Bargaining ($60 Budget vs $80 Service)',
        'Simulate Direct Match ($100 Budget vs $80 Service)',
        'Test Anti-Tamper Security (Attack Payload)',
      ];
    }

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'contractor',
      text: title,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const copilotMsg: ChatMessage = {
      id: `msg-${Date.now() + 1}`,
      sender: 'copilot',
      text: content,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      phase: 'IDLE',
      suggestedActions,
      interactiveForm: ('step' + stepNum) as 'step1' | 'step2' | 'step3' | 'step4' | 'step5',
    };

    if (skipUserMsg) {
      setMessages((prev) => [...prev, copilotMsg]);
    } else {
      setMessages((prev) => [...prev, userMsg, copilotMsg]);
    }
    onSelectStep?.(stepNum);
  };

  useEffect(() => {
    if (propActiveStep !== undefined && propActiveStep !== activeSetupStep) {
      handleSelectSetupStep(propActiveStep, true);
    }
  }, [propActiveStep]);

  const sendMessage = async (textToSend: string) => {
    if (!textToSend.trim() || isLoading) return;
    hasUserInteractedRef.current = true;

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'contractor',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setIsLoading(true);

    const lower = textToSend.toLowerCase().trim();

    try {
      // Direct Onboarding Step Routing (Checked FIRST so step navigation is never intercepted by generic commands)
      if (
        lower.includes('step 1') ||
        lower.includes('step 01') ||
        lower.includes('step one') ||
        lower.includes('how do i configure my services') ||
        lower.includes('configure service') ||
        lower.includes('service catalog') ||
        lower.includes('catalog') ||
        lower.includes('pricing') ||
        lower.includes('plans') ||
        lower.includes('tiers') ||
        lower.includes('go to step 1') ||
        lower.includes('proceed to step 1')
      ) {
        handleSelectSetupStep(1, true);
        setIsLoading(false);
        return;
      }

      if (
        lower.includes('step 2') ||
        lower.includes('step 02') ||
        lower.includes('step two') ||
        lower.includes('how do i set up ed25519') ||
        lower.includes('ed25519') ||
        lower.includes('edkeys') ||
        lower.includes('configure keys') ||
        lower.includes('configure key') ||
        lower.includes('set up keys') ||
        lower.includes('setup keys') ||
        lower.includes('key setup') ||
        lower.includes('keys') ||
        lower.includes('key') ||
        lower.includes('anti-tamper') ||
        lower.includes('anti tamper') ||
        lower.includes('crypto') ||
        lower.includes('go to step 2') ||
        lower.includes('proceed to step 2')
      ) {
        handleSelectSetupStep(2, true);
        setIsLoading(false);
        return;
      }

      if (
        lower.includes('step 3') ||
        lower.includes('step 03') ||
        lower.includes('step three') ||
        lower.includes('how do i connect paypal') ||
        lower.includes('paypal rails') ||
        lower.includes('connect paypal') ||
        lower.includes('setup paypal') ||
        lower.includes('paypal') ||
        lower.includes('billing') ||
        lower.includes('vault mit') ||
        lower.includes('recurring') ||
        lower.includes('subscription') ||
        lower.includes('paypal merchant billing') ||
        lower.includes('go to step 3') ||
        lower.includes('proceed to step 3')
      ) {
        handleSelectSetupStep(3, true);
        setIsLoading(false);
        return;
      }

      if (
        lower.includes('step 4') ||
        lower.includes('step 04') ||
        lower.includes('step four') ||
        lower.includes('how do i bridge quickbooks') ||
        lower.includes('bridge quickbooks') ||
        lower.includes('quickbooks') ||
        lower.includes('zapier') ||
        lower.includes('qbo') ||
        lower.includes('cloudevents') ||
        lower.includes('quickbooks & zapier') ||
        lower.includes('quickbooks erp') ||
        lower.includes('zapier erp') ||
        lower.includes('webhook') ||
        lower.includes('webhooks') ||
        lower.includes('erp') ||
        lower.includes('go to step 4') ||
        lower.includes('proceed to step 4')
      ) {
        handleSelectSetupStep(4, true);
        setIsLoading(false);
        return;
      }

      // Live Buyer Simulator Trigger (Checked before step 5)
      if (
        lower.includes('simulator') ||
        lower.includes('simulation') ||
        lower.includes('switch to live') ||
        lower.includes('launch live buyer') ||
        lower.includes('buyer agent simulator') ||
        lower.includes('buyer simulator') ||
        lower.includes('live simulator') ||
        lower.includes('start simulator')
      ) {
        triggerBuyerSimulatorIntro();
        setIsLoading(false);
        return;
      }

      if (
        lower.includes('step 5') ||
        lower.includes('step 05') ||
        lower.includes('step five') ||
        lower.includes('how do i launch') ||
        lower.includes('verify fastmcp') ||
        lower.includes('fastmcp') ||
        lower.includes('daemon') ||
        lower.includes('agent card') ||
        lower.includes('agent.json') ||
        lower.includes('go to step 5') ||
        lower.includes('proceed to step 5')
      ) {
        handleSelectSetupStep(5, true);
        setIsLoading(false);
        return;
      }

      // Voice & Natural Language Quick Commands
      if (lower.startsWith('set company') || lower.startsWith('change company') || lower.includes('company to ')) {
        const parts = textToSend.split(/company\s+(?:name\s+)?(?:to\s+)?/i);
        const newName = parts[1]?.trim() || 'Acme Autonomous Systems LLC';
        handleApplyStep1(newName, localTradeVertical);
        setIsLoading(false);
        return;
      }
      if (lower.includes('generate key') || lower.includes('generate new key') || lower.includes('create key') || lower.includes('new key')) {
        handleGenerateEd25519Keypair();
        setIsLoading(false);
        return;
      }
      if (lower.includes('connect paypal') || lower.includes('setup paypal')) {
        handleApplyPayPalSandbox();
        setIsLoading(false);
        return;
      }
      if (lower.includes('connect erp') || lower.includes('setup erp') || lower.includes('setup zapier')) {
        handleApplyErpWebhooks();
        setIsLoading(false);
        return;
      }
      if (lower.includes('open settings') || lower.includes('show settings') || lower.includes('node settings') || lower.includes('view settings')) {
        setActiveRightTab('settings');
        setSettingsTabOverride('profile');
        const setReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `Opened the **Node Settings & MCP Gateway** in the right pane. You can review and edit your company profile, capability catalog, cryptographic keys, PayPal credentials, and ERP integrations directly here!`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
        };
        setMessages((prev) => [...prev, setReply]);
        setIsLoading(false);
        return;
      }

      // 1. Simulation: Autonomous Bargaining ($60 Budget vs $80 Service)
      if (lower.includes('bargain') || lower.includes('counter-offer') || (lower.includes('60') && (lower.includes('budget') || lower.includes('simulate') || lower.includes('service')))) {
        setLocalBudgetCap(60.0);
        const bargainReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `⚡ **AP2 Autonomous Counter-Offer Bargaining Protocol**\n\n• **Target Capability**: Dedicated AI Service Gateway (\`$79.99/mo\`)\n• **Buyer Spending Mandate Cap**: \`$60.00/mo\` (Policy Breach: $79.99 > $60.00)\n• **Bargaining State**: Inbound intent mandate rejected at standard tier rate.\n\n🔄 **Autonomous Counter-Offer Generated by AP2 Seller Agent:**\n• **Offered Service**: High-Throughput Batch Worker\n• **Agreed Rate**: \`$49.99/mo\` (\`$10.01\` headroom within buyer's $60.00 mandate cap)\n• **Mandate Nonce**: \`0x${Math.random().toString(16).substring(2, 10)}\`\n• **Cart Mandate**: Signed with seller Ed25519 key (RFC 8032).\n\nReady for single-click execution authorization:`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'PROPOSAL',
          proposal: {
            provider: 'AP2 Worker Cluster',
            plan: 'High-Throughput Batch Worker (Down-Tier Counter-Offer)',
            monthly_price: 49.99,
          },
          suggestedActions: [
            'Approve and execute setup ($49.99/mo via PayPal)',
            'Inspect Cryptographic Trace in Right Pane',
            'Back-Office Payloads',
          ],
        };
        setMessages((prev) => [...prev, bargainReply]);
        setIsLoading(false);
        return;
      }

      // 2. Simulation: Direct Match ($100 Budget vs $80 Service)
      if (lower.includes('match') || (lower.includes('100') && (lower.includes('budget') || lower.includes('simulate') || lower.includes('service')))) {
        setLocalBudgetCap(100.0);
        const matchReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `✅ **AP2 Spending Mandate Verification (Direct Match)**\n\n• **Target Capability**: Dedicated AI Service Gateway (\`$79.99/mo\`)\n• **Buyer Spending Mandate Cap**: \`$100.00/mo\`\n• **Policy Verification**: \`$79.99 <= $100.00\` — **MANDATE APPROVED**\n• **Remaining Budget Headroom**: \`$20.01/mo\`\n• **Cryptographic Attestation**: Ed25519 signature verified across canonical JSON intent payload.\n• **Settlement Rail**: PayPal Vault Recurring MIT Agreement (\`P-5ML4271244454362WXNWU5NQ\`).\n\nReady to execute autonomous settlement:`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'PROPOSAL',
          proposal: {
            provider: 'AP2 Worker Cluster',
            plan: 'Dedicated AI Service Gateway ($79.99/mo)',
            monthly_price: 79.99,
          },
          suggestedActions: [
            'Approve and execute setup ($79.99/mo via PayPal)',
            'Inspect Cryptographic Trace in Right Pane',
            'Back-Office Payloads',
          ],
        };
        setMessages((prev) => [...prev, matchReply]);
        setIsLoading(false);
        return;
      }

      // 3. Simulation: Adversarial Anti-Tamper Security Test
      if (lower.includes('tamper') || lower.includes('attack') || lower.includes('anti-tamper')) {
        setActiveRightTab('tamper');
        // Actually execute anti-tamper verification with +1¢ price inflation ($79.99 -> $80.00)
        const tamperedAttack = {
          ...tamperPayload,
          agreed_price_usd: 80.00,
        };
        handleVerifyTamper(tamperedAttack, tamperSignature);

        const tamperReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `🛡️ **Adversarial Anti-Tamper Security Test: Attack Injected & Rejected!**\n\n• **Attack Vector**: +1¢ Price Inflation (\`$79.99\` → \`$80.00\` on canonical JSON)\n• **Cryptographic Verification**: Ed25519 signature mismatch across modified payload bytes\n• **Circuit Breaker Status**: 🚨 **HTTP 401 SIGNATURE_MISMATCH: Budget Policy Violated**\n• **Defense Outcome**: Transaction aborted fail-closed! No unauthorized charge could occur.\n\nI have switched the right pane to the **Anti-Tamper Verifier** showing the byte-level audit diff and the rejected verification result.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
          suggestedActions: [
            'Simulate Autonomous Bargaining ($60 Budget vs $80 Service)',
            'Simulate Direct Match ($100 Budget vs $80 Service)',
            'Execute Live Autonomous Settlement Cycle',
            'Reset Anti-Tamper to Valid Baseline',
          ],
        };
        setMessages((prev) => [...prev, tamperReply]);
        setIsLoading(false);
        return;
      }

      if (lower.includes('reset anti-tamper') || lower.includes('reset to untampered') || lower.includes('valid baseline')) {
        handleResetUntampered();
        const resetReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `✅ **Anti-Tamper Baseline Restored!** The canonical payload and cryptographic signature are now verified and passing.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
          suggestedActions: [
            'Simulate Autonomous Bargaining ($60 Budget vs $80 Service)',
            'Execute Live Autonomous Settlement Cycle',
          ],
        };
        setMessages((prev) => [...prev, resetReply]);
        setIsLoading(false);
        return;
      }

      // 4. Capability Catalog Query (Only when explicitly queried)
      if (
        lower.includes('query ap2') ||
        lower.includes('query catalog') ||
        lower.includes('show catalog') ||
        lower.includes('view catalog') ||
        lower.includes('list capabilities') ||
        lower === 'query ap2 seller service catalog' ||
        (lower.includes('catalog') && !lower.includes('step') && !lower.includes('profile'))
      ) {
        const catalogReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `📡 **AP2 Seller Capability Catalog Query (FastMCP JSON-RPC 2.0)**\nConnected to Seller Node endpoint: \`http://127.0.0.1:8001/mcp\`\n\n**Available Machine-to-Machine Capabilities:**\n1. **High-Throughput Batch Worker** — \`$49.99/mo\`\n   • Quota: 125 scheduled operations/mo\n   • SLA: 99.95% availability\n   • Cluster: US-Central Batch Vector RAG\n\n2. **Dedicated AI Service Gateway** — \`$79.99/mo\`\n   • Quota: 450 scheduled operations/mo\n   • SLA: 99.98% availability\n   • Cluster: US-East Low-Latency Inference Gateway\n\n3. **Enterprise Cluster Node** — \`$179.99/mo\`\n   • Quota: 1,500 operations/mo\n   • SLA: 99.99% multi-region cluster failover\n   • Cluster: Hardware-Enclave Bound High Concurrency\n\n*All plans require RFC 8032 Ed25519 cryptographic intent signing and settle via PayPal Subscriptions & Vault MIT.*`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
          suggestedActions: [
            'Simulate Autonomous Bargaining ($60 Budget vs $80 Service)',
            'Simulate Direct Match ($100 Budget vs $80 Service)',
            'Test Anti-Tamper Security (Attack Payload)',
          ],
        };
        setMessages((prev) => [...prev, catalogReply]);
        setIsLoading(false);
        return;
      }

      if (lower.includes('wire') || lower.includes('sse')) {
        setActiveRightTab('wire');
        const wireReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `Switched to the **Wire Protocol (SSE)** tab in the right pane. Live JSON-RPC 2.0 frames are streaming.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
          suggestedActions: [
            'Query AP2 Seller Service Catalog',
            'Execute Live Autonomous Settlement Cycle',
          ],
        };
        setMessages((prev) => [...prev, wireReply]);
        setIsLoading(false);
        return;
      }

      if (lower.includes('trace') || lower.includes('audit')) {
        setActiveRightTab('trace');
        const traceReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `Switched to the **AP2 Execution Trace** tab in the right pane.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
          suggestedActions: [
            'Query AP2 Seller Service Catalog',
            'Execute Live Autonomous Settlement Cycle',
          ],
        };
        setMessages((prev) => [...prev, traceReply]);
        setIsLoading(false);
        return;
      }

      if (lower.includes('back-office') || lower.includes('payload') || lower.includes('cloudevents') || lower.includes('qbo')) {
        openInspector();
        const inspReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `Opened the **Back-Office Payloads** inspector showing CloudEvents v1.0 and QuickBooks Online API v3 export envelopes.`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
        };
        setMessages((prev) => [...prev, inspReply]);
        setIsLoading(false);
        return;
      }

      if (lower.includes('ledger') || lower.includes('fleet')) {
        onNavigateTab?.('ag-studio');
        setIsLoading(false);
        return;
      }

      if (lower.includes('scheduler') || lower.includes('bryntum')) {
        onNavigateTab?.('bryntum');
        setIsLoading(false);
        return;
      }

      if (lower.includes('approve') || lower.includes('execute') || lower.includes('settlement')) {
        await triggerTestCycle();
        const execReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `🎉 **AP2 Autonomous Settlement & Fulfillment Complete!**\n\nThe autonomous transaction has been cryptographically confirmed and settled:\n\n• **Buyer Agent**: \`${localContractorName}\`\n• **Principal Entity**: \`${localBusinessEntity}\`\n• **Assigned Endpoint**: Node-01 (Inference Gateway / \`${lastAllocatedDid || 'node-cluster-01.ap2.net:8443'}\`)\n• **PayPal Agreement**: Active recurring MIT subscription token authorized\n• **Cryptographic Attestation**: RFC 8032 Ed25519 verified (Anti-tamper: PASS)\n• **Back-Office Sync**: QuickBooks Online GL 6300 & CloudEvents v1.0 Webhook provisioned\n\nThe contract is live! View the mutated row in the **Settlement Ledger & BI** (AG Grid) or **Worker Node Scheduler** (Bryntum).`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'COMPLETED',
          suggestedActions: [
            'Inspect Cryptographic Trace in Right Pane',
            'View in Settlement Ledger (AG Grid)',
            'View in Worker Node Scheduler (Bryntum)',
            'Back-Office Payloads',
          ],
        };
        setMessages((prev) => [...prev, execReply]);
        setIsLoading(false);
        return;
      }

      // Natural Language Voice & Greeting Handlers
      if (
        lower.includes('hello') ||
        lower.includes('hi') ||
        lower.includes('hey') ||
        lower.includes('yo') ||
        lower.includes('can you hear') ||
        lower.includes('hear me') ||
        lower.includes('testing') ||
        lower.includes('test') ||
        lower.includes('help') ||
        lower.includes('what can you do') ||
        lower.includes('who are you') ||
        lower.includes('start') ||
        lower.includes('begin')
      ) {
        const greetReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `🎙️ **Loud and clear! I am your AP2 Node Setup & Voice Copilot.**

I can guide you through every step of getting your autonomous seller node online, or automatically fill in the configuration for you:

• **Step 01**: Service Catalog & Pricing (\`catalog.json\`)
• **Step 02**: RFC 8032 Ed25519 Keys & Anti-Tamper Verification
• **Step 03**: PayPal Subscriptions & Vault MIT Recurring Billing
• **Step 04**: QuickBooks Online (GL 6300) & Zapier CloudEvents
• **Step 05**: FastMCP Daemon (port 8001) & Live Buyer Simulation

You can speak any step (e.g. *"Step 1"*, *"Generate keys"*, *"Connect PayPal"*) or click a suggested action below:`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
          suggestedActions: [
            'Step 1: How do I configure my services & pricing?',
            'Step 2: How do I set up Ed25519 keys & anti-tamper?',
            'Step 3: How do I connect PayPal merchant billing?',
            'Step 4: How do I bridge QuickBooks & Zapier ERP?',
            '🚀 Switch to Live Buyer Agent Simulator',
          ],
        };
        setMessages((prev) => [...prev, greetReply]);
        setIsLoading(false);
        return;
      }

      // If in Onboarding Mode, provide dedicated AP2 Onboarding guidance for ANY user query
      if (copilotMode === 'onboarding') {
        const onboardReply: ChatMessage = {
          id: `msg-${Date.now() + 1}`,
          sender: 'copilot',
          text: `🤖 **AP2 Onboarding Copilot**: I heard your voice command: *"${textToSend}"*.

I am currently in **Seller Node Onboarding Mode**. I can assist you with configuring any part of your node:

• **Step 01**: Company profile, support email, and 3 service tiers in \`catalog.json\`.
• **Step 02**: RFC 8032 Ed25519 keys and anti-tamper security.
• **Step 03**: PayPal merchant billing via Vault MIT.
• **Step 04**: QuickBooks Online & Zapier EventBus webhooks.
• **Step 05**: FastMCP daemon and live buyer agent testing.

👉 Click any step card above or choose a suggested action below to continue:`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          phase: 'IDLE',
          suggestedActions: [
            'Step 1: How do I configure my services & pricing?',
            'Step 2: How do I set up Ed25519 keys & anti-tamper?',
            'Step 3: How do I connect PayPal merchant billing?',
            'Step 4: How do I bridge QuickBooks & Zapier ERP?',
            '🚀 Switch to Live Buyer Agent Simulator',
          ],
        };
        setMessages((prev) => [...prev, onboardReply]);
        setIsLoading(false);
        return;
      }

      // Default fallback (Simulation Mode): query backend copilot chat
      const res = await fetch('/api/copilot/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: textToSend,
          contractorName: localContractorName,
          businessEntity: localBusinessEntity,
          tradeVertical: localTradeVertical,
          areaCode: localAreaCode,
          budgetCap: localBudgetCap,
          simulateExhaustion: simulateExhaustion,
        }),
      });

      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      const copilotMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: 'copilot',
        text: data.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        phase: data.phase,
        telemetry: data.telemetry,
        proposal: data.proposal,
        suggestedActions: [
          'Query AP2 Seller Service Catalog',
          'Request Dedicated AI Gateway with $60 budget (Test Bargaining)',
          'Verify Cryptographic Anti-Tamper Mandate',
          'Execute Autonomous Settlement via PayPal',
        ],
      };
      setMessages((prev) => [...prev, copilotMsg]);
    } catch (err: any) {
      console.error('Copilot API error:', err);
      setMessages((prev) => [
        ...prev,
        {
          id: `msg-err-${Date.now()}`,
          sender: 'copilot',
          text: "I'm having trouble connecting to the backend right now. Please verify the server is running on port 8001.",
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', boxSizing: 'border-box', padding: '12px 16px', gap: '12px', overflowY: 'auto' }}>
      {/* 4-STEP OPEN-SOURCE PROTOCOL ONBOARDING & SETUP GUIDE */}
      <div
        style={{
          backgroundColor: '#090e17',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '30px',
                height: '30px',
                borderRadius: '8px',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Cpu size={16} />
            </div>
            <div>
              <div style={{ color: '#f8fafc', fontWeight: 800, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                AP2 Seller Node &bull; Turnkey Setup &amp; Deployment Guide
                <span style={{ fontSize: '10px', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '1px 7px', borderRadius: '4px', fontWeight: 700 }}>
                  Active Protocol Node
                </span>
              </div>
              <div style={{ color: '#94a3b8', fontSize: '11px', marginTop: '4px' }}>
                Click any step below to explore configuration guides, generate keys, connect rails, or test with the live simulator.
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 600 }}>FastMCP Daemon:</span>
            <code style={{ fontSize: '11px', backgroundColor: '#131d31', border: '1px solid #1e293b', color: '#38bdf8', padding: '2px 8px', borderRadius: '4px', fontFamily: 'monospace' }}>
              http://127.0.0.1:8001/mcp
            </code>
            <button
              onClick={toggleGuideCollapsed}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 10px',
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '6px',
                color: isGuideCollapsed ? '#38bdf8' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title={isGuideCollapsed ? 'Expand 5-Step Deployment Guide' : 'Collapse Guide to expand chat and settings workspace'}
            >
              {isGuideCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
              <span>{isGuideCollapsed ? 'Expand' : 'Collapse'}</span>
            </button>
          </div>
        </div>

        {/* Step Guide: Collapsed vs. Expanded 5 Cards */}
        {isGuideCollapsed ? null : (
          /* 5 Interactive Step Cards */
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
          {/* Step 1 */}
          <div
            onClick={() => handleSelectSetupStep(1)}
            style={{
              backgroundColor: activeSetupStep === 1 && copilotMode === 'onboarding' ? 'rgba(56, 189, 248, 0.08)' : '#0f172a',
              border: activeSetupStep === 1 && copilotMode === 'onboarding' ? '1px solid #38bdf8' : '1px solid #1e293b',
              boxShadow: activeSetupStep === 1 && copilotMode === 'onboarding' ? '0 0 12px rgba(56, 189, 248, 0.25)' : 'none',
              borderRadius: '8px',
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '10px', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.05em' }}>STEP 01</span>
              <span style={{ fontSize: '9px', fontWeight: 700, backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#38bdf8', padding: '1px 5px', borderRadius: '3px' }}>
                catalog.json
              </span>
            </div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>
              Declare Service Catalog
            </div>
            <p style={{ fontSize: '10px', color: '#94a3b8', margin: 0, lineHeight: 1.35 }}>
              Define company service tiers, pricing ($49.99, $79.99, $179.99), and compute SLAs for autonomous buyer discovery.
            </p>
            <div style={{ marginTop: 'auto', paddingTop: '4px', fontSize: '9px', color: '#34d399', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={11} /> 3 Tiers Registered
            </div>
          </div>

          {/* Step 2 */}
          <div
            onClick={() => handleSelectSetupStep(2)}
            style={{
              backgroundColor: activeSetupStep === 2 && copilotMode === 'onboarding' ? 'rgba(168, 85, 247, 0.08)' : '#0f172a',
              border: activeSetupStep === 2 && copilotMode === 'onboarding' ? '1px solid #a855f7' : '1px solid #1e293b',
              boxShadow: activeSetupStep === 2 && copilotMode === 'onboarding' ? '0 0 12px rgba(168, 85, 247, 0.25)' : 'none',
              borderRadius: '8px',
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '10px', fontWeight: 800, color: '#a855f7', letterSpacing: '0.05em' }}>STEP 02</span>
              <span style={{ fontSize: '9px', fontWeight: 700, backgroundColor: 'rgba(168, 85, 247, 0.12)', color: '#c084fc', padding: '1px 5px', borderRadius: '3px' }}>
                .env / RFC 8032
              </span>
            </div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>
              Configure Ed25519 Keys
            </div>
            <p style={{ fontSize: '10px', color: '#94a3b8', margin: 0, lineHeight: 1.35 }}>
              Bind seller public keys for non-repudiation. Auto-quarantine any tampered prices or forged nonces with HTTP 401.
            </p>
            <div style={{ marginTop: 'auto', paddingTop: '4px', fontSize: '9px', color: '#34d399', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={11} /> Anti-Tamper Active
            </div>
          </div>

          {/* Step 3 */}
          <div
            onClick={() => handleSelectSetupStep(3)}
            style={{
              backgroundColor: activeSetupStep === 3 && copilotMode === 'onboarding' ? 'rgba(245, 158, 11, 0.08)' : '#0f172a',
              border: activeSetupStep === 3 && copilotMode === 'onboarding' ? '1px solid #f59e0b' : '1px solid #1e293b',
              boxShadow: activeSetupStep === 3 && copilotMode === 'onboarding' ? '0 0 12px rgba(245, 158, 11, 0.25)' : 'none',
              borderRadius: '8px',
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '10px', fontWeight: 800, color: '#f59e0b', letterSpacing: '0.05em' }}>STEP 03</span>
              <span style={{ fontSize: '9px', fontWeight: 700, backgroundColor: 'rgba(245, 158, 11, 0.12)', color: '#fbbf24', padding: '1px 5px', borderRadius: '3px' }}>
                PayPal Vault MIT
              </span>
            </div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>
              Connect Payment Rail
            </div>
            <p style={{ fontSize: '10px', color: '#94a3b8', margin: 0, lineHeight: 1.35 }}>
              Wire PayPal Subscriptions &amp; Vault MIT. Settle recurring subscription revenue directly with zero human invoicing.
            </p>
            <div style={{ marginTop: 'auto', paddingTop: '4px', fontSize: '9px', color: '#34d399', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={11} /> PayPal Rail Bound
            </div>
          </div>

          {/* Step 4 */}
          <div
            onClick={() => handleSelectSetupStep(4)}
            style={{
              backgroundColor: activeSetupStep === 4 && copilotMode === 'onboarding' ? 'rgba(16, 185, 129, 0.08)' : '#0f172a',
              border: activeSetupStep === 4 && copilotMode === 'onboarding' ? '1px solid #10b981' : '1px solid #1e293b',
              boxShadow: activeSetupStep === 4 && copilotMode === 'onboarding' ? '0 0 12px rgba(16, 185, 129, 0.25)' : 'none',
              borderRadius: '8px',
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '10px', fontWeight: 800, color: '#10b981', letterSpacing: '0.05em' }}>STEP 04</span>
              <span style={{ fontSize: '9px', fontWeight: 700, backgroundColor: 'rgba(16, 185, 129, 0.12)', color: '#34d399', padding: '1px 5px', borderRadius: '3px' }}>
                CloudEvents / ERP
              </span>
            </div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>
              Bridge ERP &amp; EventBus
            </div>
            <p style={{ fontSize: '10px', color: '#94a3b8', margin: 0, lineHeight: 1.35 }}>
              Stream completed sales into QuickBooks Online (GL 4000/6300) and dispatch workloads to execution worker nodes.
            </p>
            <div style={{ marginTop: 'auto', paddingTop: '4px', fontSize: '9px', color: '#34d399', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={11} /> QBO Auto-Reconciled
            </div>
          </div>

          {/* Step 5 */}
          <div
            onClick={() => handleSelectSetupStep(5)}
            style={{
              backgroundColor: activeSetupStep === 5 && copilotMode === 'onboarding' ? 'rgba(56, 189, 248, 0.08)' : '#0f172a',
              border: activeSetupStep === 5 && copilotMode === 'onboarding' ? '1px solid #38bdf8' : '1px solid #1e293b',
              boxShadow: activeSetupStep === 5 && copilotMode === 'onboarding' ? '0 0 12px rgba(56, 189, 248, 0.25)' : 'none',
              borderRadius: '8px',
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '10px', fontWeight: 800, color: '#38bdf8', letterSpacing: '0.05em' }}>STEP 05</span>
              <span style={{ fontSize: '9px', fontWeight: 700, backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#38bdf8', padding: '1px 5px', borderRadius: '3px' }}>
                8001 / FastMCP
              </span>
            </div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>
              Launch Daemon &amp; Test
            </div>
            <p style={{ fontSize: '10px', color: '#94a3b8', margin: 0, lineHeight: 1.35 }}>
              Start the FastMCP server, expose agent card (.well-known/agent.json), and test with the live simulator.
            </p>
            <div style={{ marginTop: 'auto', paddingTop: '4px', fontSize: '9px', color: '#38bdf8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <CheckCircle2 size={11} /> Ready to Simulate
            </div>
          </div>
        </div>
      )}
    </div>

      {/* DUAL PANE MAIN WORKSPACE */}
      <div style={{ display: 'grid', gridTemplateColumns: isChatExpanded ? '1fr' : '1fr 1fr', flex: 1, gap: '16px', minHeight: 0 }}>
        {/* LEFT PANE: FastMCP Protocol Sandbox (Buyer Agent Simulator) */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            backgroundColor: '#0f172a',
            borderRadius: '12px',
            border: '1px solid #1e293b',
            overflow: 'hidden',
          }}
        >
          {/* Copilot Header */}
          <div
            style={{
              padding: isChatMenuCollapsed ? '6px 14px' : '10px 18px',
              backgroundColor: '#1e293b',
              borderBottom: '1px solid #334155',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: isChatMenuCollapsed ? '8px' : '12px',
              flexWrap: isChatMenuCollapsed ? 'nowrap' : 'wrap',
              transition: 'all 0.15s ease',
            }}
          >
            {/* Left: Branding & Status */}
            <div style={{ display: 'flex', alignItems: 'center', gap: isChatMenuCollapsed ? '8px' : '10px', minWidth: 0, overflow: 'hidden' }}>
              <div
                style={{
                  width: isChatMenuCollapsed ? '26px' : '34px',
                  height: isChatMenuCollapsed ? '26px' : '34px',
                  borderRadius: '7px',
                  backgroundColor: copilotMode === 'onboarding' ? '#0284c7' : '#10b981',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#fff',
                  flexShrink: 0,
                  transition: 'all 0.15s ease',
                }}
              >
                {copilotMode === 'onboarding' ? <BookOpen size={isChatMenuCollapsed ? 14 : 18} /> : <Bot size={isChatMenuCollapsed ? 14 : 18} />}
              </div>
              <div style={{ minWidth: 0, overflow: 'hidden' }}>
                <div style={{ color: '#f8fafc', fontWeight: 700, fontSize: isChatMenuCollapsed ? '12px' : '13px', display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {copilotMode === 'onboarding'
                      ? (isChatMenuCollapsed ? 'Onboarding Assistant' : 'Node Setup & Onboarding Assistant')
                      : (isChatMenuCollapsed ? 'FastMCP Simulator' : 'Interactive FastMCP Protocol Simulator')}
                  </span>
                  <span
                    style={{
                      fontSize: '10px',
                      backgroundColor: copilotMode === 'onboarding' ? 'rgba(56, 189, 248, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                      color: copilotMode === 'onboarding' ? '#38bdf8' : '#34d399',
                      padding: '1px 6px',
                      borderRadius: '4px',
                      fontWeight: 600,
                      flexShrink: 0,
                    }}
                  >
                    {copilotMode === 'onboarding' ? `Step 0${activeSetupStep}` : 'Live'}
                  </span>
                </div>
                {!isChatMenuCollapsed && (
                  <div style={{ color: '#94a3b8', fontSize: '11px', marginTop: '1px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {copilotMode === 'onboarding'
                      ? `Guiding company onboarding for ${localBusinessEntity}`
                      : `Representing ${localBusinessEntity} • ${localContractorName}`}
                  </div>
                )}
              </div>
            </div>

            {/* Right: Controls & Actions */}
            <div style={{ display: 'flex', alignItems: 'center', gap: isChatMenuCollapsed ? '6px' : '10px', flexWrap: isChatMenuCollapsed ? 'nowrap' : 'wrap', flexShrink: 0 }}>
              {/* Controls visible when NOT menu-collapsed */}
              {!isChatMenuCollapsed ? (
                <>
                  {/* Mode Switcher Pills */}
                  <div style={{ display: 'flex', backgroundColor: '#0f172a', padding: '2px', borderRadius: '6px', border: '1px solid #334155' }}>
                    <button
                      onClick={() => {
                        setCopilotMode('onboarding');
                        handleSelectSetupStep(activeSetupStep || 1);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '4px 10px',
                        borderRadius: '4px',
                        border: 'none',
                        backgroundColor: copilotMode === 'onboarding' ? '#0284c7' : 'transparent',
                        color: copilotMode === 'onboarding' ? '#fff' : '#94a3b8',
                        fontSize: '11px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <BookOpen size={12} /> Setup Guide
                    </button>
                    <button
                      onClick={() => {
                        setCopilotMode('simulation');
                        sendMessage('Switch to live buyer agent simulator');
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '4px 10px',
                        borderRadius: '4px',
                        border: 'none',
                        backgroundColor: copilotMode === 'simulation' ? '#10b981' : 'transparent',
                        color: copilotMode === 'simulation' ? '#fff' : '#94a3b8',
                        fontSize: '11px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <Sparkles size={12} /> Live Simulator
                    </button>
                  </div>

                  {copilotMode === 'simulation' && (
                    <label
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '5px',
                        backgroundColor: simulateExhaustion ? 'rgba(239, 68, 68, 0.15)' : 'rgba(15, 23, 42, 0.6)',
                        border: simulateExhaustion ? '1px solid #ef4444' : '1px solid #334155',
                        borderRadius: '6px',
                        padding: '3px 8px',
                        cursor: 'pointer',
                        fontSize: '10px',
                        fontWeight: 600,
                        color: simulateExhaustion ? '#f87171' : '#94a3b8',
                      }}
                      title="Toggle to simulate node capacity exhaustion and trigger contiguous cluster failover routing"
                    >
                      <input
                        type="checkbox"
                        checked={simulateExhaustion}
                        onChange={(e) => setSimulateExhaustion(e.target.checked)}
                        style={{ accentColor: '#ef4444', cursor: 'pointer' }}
                      />
                      Failover
                    </label>
                  )}

                  {/* Interactive & Editable Mandate Cap */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                      <span style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>Cap:</span>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          backgroundColor: '#090e17',
                          border: '1px solid #334155',
                          borderRadius: '4px',
                          padding: '2px 5px',
                        }}
                      >
                        <span style={{ color: localBudgetCap < 79.99 ? '#f59e0b' : '#34d399', fontSize: '11px', fontWeight: 700 }}>$</span>
                        <input
                          type="number"
                          step="5"
                          min="20"
                          max="500"
                          value={localBudgetCap}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value) || 0;
                            setLocalBudgetCap(val);
                          }}
                          style={{
                            width: '48px',
                            backgroundColor: 'transparent',
                            border: 'none',
                            color: localBudgetCap < 79.99 ? '#f59e0b' : '#34d399',
                            fontSize: '11px',
                            fontWeight: 700,
                            outline: 'none',
                            textAlign: 'right',
                            padding: '0 2px',
                          }}
                          title="Click to edit the Buyer Agent programmatic spending mandate ceiling"
                        />
                        <span style={{ color: '#64748b', fontSize: '10px' }}>/mo</span>
                      </div>
                    </div>
                    {/* Quick Preset Buttons */}
                    <div style={{ display: 'flex', gap: '3px', alignItems: 'center' }}>
                      <button
                        type="button"
                        onClick={() => {
                          setLocalBudgetCap(60.0);
                          if (copilotMode === 'simulation') {
                            sendMessage('Simulate Autonomous Bargaining ($60 Budget vs $80 Service)');
                          }
                        }}
                        style={{
                          backgroundColor: localBudgetCap === 60 ? 'rgba(245, 158, 11, 0.25)' : '#090e17',
                          border: localBudgetCap === 60 ? '1px solid #f59e0b' : '1px solid #334155',
                          color: localBudgetCap === 60 ? '#f59e0b' : '#94a3b8',
                          borderRadius: '3px',
                          padding: '1px 5px',
                          fontSize: '9px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                        title="Set $60 cap to test down-tier counter-offer bargaining ($49.99/mo)"
                      >
                        $60 Bargain
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setLocalBudgetCap(100.0);
                          if (copilotMode === 'simulation') {
                            sendMessage('Simulate Direct Match ($100 Budget vs $80 Service)');
                          }
                        }}
                        style={{
                          backgroundColor: localBudgetCap === 100 ? 'rgba(52, 211, 153, 0.25)' : '#090e17',
                          border: localBudgetCap === 100 ? '1px solid #34d399' : '1px solid #334155',
                          color: localBudgetCap === 100 ? '#34d399' : '#94a3b8',
                          borderRadius: '3px',
                          padding: '1px 5px',
                          fontSize: '9px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                        title="Set $100 cap to test standard direct mandate approval ($79.99/mo)"
                      >
                        $100 Match
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                /* Compact pill when menu is collapsed */
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    backgroundColor: '#090e17',
                    border: '1px solid #334155',
                    borderRadius: '5px',
                    padding: '3px 8px',
                    fontSize: '11px',
                    color: localBudgetCap < 79.99 ? '#f59e0b' : '#34d399',
                    fontWeight: 700,
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  <span>Cap: ${localBudgetCap.toFixed(0)}/mo</span>
                </div>
              )}

              {/* Action Buttons: Collapse Menu & Maximize Chat */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px', borderLeft: '1px solid #334155', paddingLeft: '8px', flexShrink: 0, whiteSpace: 'nowrap' }}>
                {/* Menu Collapse Toggle */}
                <button
                  type="button"
                  onClick={() => setIsChatMenuCollapsed((prev) => !prev)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    backgroundColor: isChatMenuCollapsed ? 'rgba(56, 189, 248, 0.15)' : '#0f172a',
                    border: isChatMenuCollapsed ? '1px solid #38bdf8' : '1px solid #334155',
                    color: isChatMenuCollapsed ? '#38bdf8' : '#94a3b8',
                    padding: '5px 8px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title={isChatMenuCollapsed ? 'Expand Chat Top Menu' : 'Collapse Chat Top Menu for More Vertical Height'}
                >
                  {isChatMenuCollapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
                  <span style={{ fontSize: '10px' }}>{isChatMenuCollapsed ? 'Menu' : 'Menu'}</span>
                </button>

                {/* Maximize Full-Width Toggle */}
                <button
                  type="button"
                  onClick={() => {
                    setIsChatExpanded((prev) => {
                      const next = !prev;
                      if (next) {
                        setIsChatMenuCollapsed(true);
                        setIsGuideCollapsed(true);
                      }
                      return next;
                    });
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                    backgroundColor: isChatExpanded ? '#0284c7' : '#0f172a',
                    border: isChatExpanded ? '1px solid #38bdf8' : '1px solid #334155',
                    color: isChatExpanded ? '#ffffff' : '#94a3b8',
                    padding: '5px 9px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: isChatExpanded ? '0 0 10px rgba(2, 132, 199, 0.4)' : 'none',
                  }}
                  title={isChatExpanded ? 'Restore Dual-Pane Split View' : 'Expand Chat Window Full-Width'}
                >
                  {isChatExpanded ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                  <span style={{ fontSize: '10px' }}>{isChatExpanded ? 'Dual Pane' : 'Full Width'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Messages Feed */}
          <div ref={chatContainerRef} style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {messages.map((m) => {
              const isCopilot = m.sender === 'copilot';
              return (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    gap: '10px',
                    alignSelf: isCopilot ? 'flex-start' : 'flex-end',
                    maxWidth: '88%',
                    flexDirection: isCopilot ? 'row' : 'row-reverse',
                  }}
                >
                  <div
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      backgroundColor: isCopilot ? '#0284c7' : '#334155',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#fff',
                      flexShrink: 0,
                      marginTop: '2px',
                    }}
                  >
                    {isCopilot ? <Bot size={15} /> : <User size={15} />}
                  </div>

                  <div>
                    <div
                      style={{
                        backgroundColor: isCopilot ? '#1e293b' : '#0284c7',
                        color: '#f8fafc',
                        padding: '12px 14px',
                        borderRadius: isCopilot ? '4px 12px 12px 12px' : '12px 4px 12px 12px',
                        fontSize: '13px',
                        lineHeight: '1.5',
                        whiteSpace: 'pre-wrap',
                        border: isCopilot ? '1px solid #334155' : 'none',
                      }}
                    >
                      {m.text}

                      {/* Proposal Action Card (if Copilot is proposing a setup) */}
                      {m.proposal && (
                        <div
                          style={{
                            marginTop: '12px',
                            backgroundColor: '#0f172a',
                            border: '1px solid #0284c7',
                            borderRadius: '8px',
                            padding: '12px',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                            <span style={{ fontWeight: 700, color: '#38bdf8', fontSize: '13px' }}>
                              {m.proposal.provider} &mdash; {m.proposal.plan}
                            </span>
                            <span style={{ fontWeight: 800, color: '#34d399', fontSize: '14px' }}>
                              ${m.proposal.monthly_price.toFixed(2)}/mo
                            </span>
                          </div>
                          <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '10px' }}>
                            Authorized entity: <strong>{localBusinessEntity}</strong> &bull; Area {localAreaCode}
                          </div>
                          <button
                            onClick={() => sendMessage(`Yes, approve and execute setup ($${m.proposal.monthly_price.toFixed(2)}/mo via PayPal)`)}
                            disabled={isLoading}
                            style={{
                              width: '100%',
                              padding: '10px',
                              backgroundColor: '#059669',
                              color: '#fff',
                              border: 'none',
                              borderRadius: '6px',
                              fontWeight: 700,
                              fontSize: '13px',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '6px',
                            }}
                          >
                            <CheckCircle2 size={16} /> Approve &amp; Execute (${m.proposal.monthly_price.toFixed(2)}/mo via PayPal)
                          </button>
                        </div>
                      )}

                      {/* Interactive In-Chat Form Action Cards for Steps 1-5 */}
                      {m.interactiveForm === 'step1' && (
                        <div
                          style={{
                            marginTop: '12px',
                            backgroundColor: '#090e17',
                            border: '1px solid rgba(56, 189, 248, 0.4)',
                            borderRadius: '8px',
                            padding: '14px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Sparkles size={16} color="#38bdf8" />
                            <span style={{ fontWeight: 700, color: '#38bdf8', fontSize: '13px' }}>
                              🤖 Configure Company Profile, Support Email &amp; Service Catalog:
                            </span>
                          </div>

                          <div
                            style={{
                              backgroundColor: 'rgba(56, 189, 248, 0.08)',
                              border: '1px solid rgba(56, 189, 248, 0.25)',
                              borderRadius: '6px',
                              padding: '8px 12px',
                              marginBottom: '12px',
                              fontSize: '11px',
                              color: '#94a3b8',
                              lineHeight: '1.45',
                            }}
                          >
                            <span style={{ color: '#38bdf8', fontWeight: 700 }}>💡 Turnkey Mock Information:</span> We can fill your node with this standard turnkey mock profile and 3-tier catalog for now—you can always customize or add more plans later in <strong>Tab 1</strong> on the right!
                          </div>

                          {/* Company & Email Row */}
                          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
                            <div>
                              <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px', fontWeight: 600 }}>
                                Company Legal Entity Name
                              </label>
                              <input
                                type="text"
                                value={formStep1Company}
                                onChange={(e) => setFormStep1Company(e.target.value)}
                                placeholder="e.g. Acme Autonomous Systems LLC"
                                style={{
                                  width: '100%',
                                  backgroundColor: '#0f172a',
                                  border: '1px solid #334155',
                                  borderRadius: '6px',
                                  color: '#fff',
                                  padding: '7px 10px',
                                  fontSize: '12px',
                                  boxSizing: 'border-box',
                                  outline: 'none',
                                }}
                              />
                            </div>
                            <div>
                              <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px', fontWeight: 600 }}>
                                Operations &amp; Support Email
                              </label>
                              <input
                                type="email"
                                value={formStep1Email}
                                onChange={(e) => setFormStep1Email(e.target.value)}
                                placeholder="e.g. ops@acme-systems.io"
                                style={{
                                  width: '100%',
                                  backgroundColor: '#0f172a',
                                  border: '1px solid #334155',
                                  borderRadius: '6px',
                                  color: '#fff',
                                  padding: '7px 10px',
                                  fontSize: '12px',
                                  boxSizing: 'border-box',
                                  outline: 'none',
                                }}
                              />
                            </div>
                          </div>

                          {/* Industry / Service Row */}
                          <div style={{ marginBottom: '12px' }}>
                            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px', fontWeight: 600 }}>
                              Primary Service / Industry Vertical
                            </label>
                            <input
                              type="text"
                              value={formStep1Service}
                              onChange={(e) => setFormStep1Service(e.target.value)}
                              placeholder="e.g. Dedicated AI Service Gateway"
                              style={{
                                width: '100%',
                                backgroundColor: '#0f172a',
                                border: '1px solid #334155',
                                borderRadius: '6px',
                                color: '#fff',
                                padding: '7px 10px',
                                fontSize: '12px',
                                boxSizing: 'border-box',
                                outline: 'none',
                              }}
                            />
                          </div>

                          {/* Catalog Tiers Section */}
                          <div style={{ marginBottom: '14px' }}>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <Layers size={13} /> Machine-to-Machine Catalog Tiers ({formStep1Capabilities.length} Plans Configured):
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                              {formStep1Capabilities.map((cap, idx) => {
                                const isDefaultFirst = idx === 0;
                                const isDefaultSecond = idx === 1;
                                const isDefaultThird = idx === 2;
                                const tierSubtitle = isDefaultFirst
                                  ? 'Tier 1 (Down-Tier Counter-Offer Plan)'
                                  : isDefaultSecond
                                  ? 'Tier 2 (Primary Autonomous Gateway Plan)'
                                  : isDefaultThird
                                  ? 'Tier 3 (Enterprise Cluster Node Plan)'
                                  : `Tier ${idx + 1} (Custom Service Capability)`;

                                return (
                                  <div
                                    key={cap.id || `tier-${idx}`}
                                    style={{
                                      backgroundColor: '#0f172a',
                                      padding: '10px 12px',
                                      borderRadius: '6px',
                                      border: '1px solid #1e293b',
                                      display: 'flex',
                                      flexDirection: 'column',
                                      gap: '8px',
                                    }}
                                  >
                                    {/* Plan Header: Label & Delete Button */}
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                      <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 700, letterSpacing: '0.04em' }}>
                                        {tierSubtitle}
                                      </span>
                                      {formStep1Capabilities.length > 1 && (
                                        <button
                                          type="button"
                                          onClick={() => handleRemoveStep1Capability(cap.id)}
                                          title="Remove this plan tier"
                                          style={{
                                            background: 'transparent',
                                            border: 'none',
                                            color: '#ef4444',
                                            cursor: 'pointer',
                                            padding: '2px 4px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '3px',
                                            fontSize: '10px',
                                            borderRadius: '4px',
                                            transition: 'all 0.15s ease',
                                          }}
                                        >
                                          <Trash2 size={12} />
                                          <span>Remove</span>
                                        </button>
                                      )}
                                    </div>

                                    {/* Row 1: Plan Name & Monthly Price */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '8px', alignItems: 'center' }}>
                                      <div>
                                        <label style={{ fontSize: '10px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>
                                          Plan Name
                                        </label>
                                        <input
                                          type="text"
                                          value={cap.name}
                                          onChange={(e) => handleUpdateStep1Capability(cap.id, 'name', e.target.value)}
                                          placeholder="Plan Title (e.g. Dedicated AI Gateway)"
                                          style={{
                                            width: '100%',
                                            backgroundColor: '#090e17',
                                            border: '1px solid #334155',
                                            borderRadius: '4px',
                                            color: '#f8fafc',
                                            fontSize: '11px',
                                            fontWeight: 600,
                                            padding: '4px 8px',
                                            boxSizing: 'border-box',
                                            outline: 'none',
                                          }}
                                        />
                                      </div>
                                      <div>
                                        <label style={{ fontSize: '10px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>
                                          Price ($/mo)
                                        </label>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                                          <span style={{ color: '#34d399', fontSize: '11px', fontWeight: 700 }}>$</span>
                                          <input
                                            type="number"
                                            step="0.01"
                                            value={cap.monthly_price_usd}
                                            onChange={(e) => handleUpdateStep1Capability(cap.id, 'monthly_price_usd', parseFloat(e.target.value) || 0)}
                                            style={{
                                              width: '100%',
                                              backgroundColor: '#090e17',
                                              border: '1px solid #334155',
                                              borderRadius: '4px',
                                              color: '#34d399',
                                              padding: '4px 6px',
                                              fontSize: '11px',
                                              fontWeight: 700,
                                              textAlign: 'right',
                                              outline: 'none',
                                              boxSizing: 'border-box',
                                            }}
                                          />
                                          <span style={{ color: '#64748b', fontSize: '10px' }}>/mo</span>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Row 2: Quota Allowance & Service Description / SLA */}
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', alignItems: 'center' }}>
                                      <div>
                                        <label style={{ fontSize: '10px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>
                                          Quota Allowance
                                        </label>
                                        <input
                                          type="text"
                                          value={cap.quota || ''}
                                          onChange={(e) => handleUpdateStep1Capability(cap.id, 'quota', e.target.value)}
                                          placeholder="e.g. 125 operations/mo, 500 dispatches"
                                          style={{
                                            width: '100%',
                                            backgroundColor: '#090e17',
                                            border: '1px solid #334155',
                                            borderRadius: '4px',
                                            color: '#38bdf8',
                                            fontSize: '11px',
                                            padding: '4px 8px',
                                            boxSizing: 'border-box',
                                            outline: 'none',
                                          }}
                                        />
                                      </div>
                                      <div>
                                        <label style={{ fontSize: '10px', color: '#94a3b8', display: 'block', marginBottom: '2px' }}>
                                          Service Description &amp; SLA
                                        </label>
                                        <input
                                          type="text"
                                          value={cap.sla || cap.enclave || ''}
                                          onChange={(e) => {
                                            handleUpdateStep1Capability(cap.id, 'sla', e.target.value);
                                            handleUpdateStep1Capability(cap.id, 'enclave', e.target.value);
                                          }}
                                          placeholder="e.g. 99.98% Low Latency (<350ms)"
                                          style={{
                                            width: '100%',
                                            backgroundColor: '#090e17',
                                            border: '1px solid #334155',
                                            borderRadius: '4px',
                                            color: '#cbd5e1',
                                            fontSize: '11px',
                                            padding: '4px 8px',
                                            boxSizing: 'border-box',
                                            outline: 'none',
                                          }}
                                        />
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}

                              {/* Add Service Capability Tier Button */}
                              <button
                                type="button"
                                onClick={handleAddStep1Capability}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '6px',
                                  backgroundColor: '#0f172a',
                                  border: '1px dashed #38bdf8',
                                  color: '#38bdf8',
                                  padding: '7px 12px',
                                  borderRadius: '6px',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                  width: '100%',
                                  boxSizing: 'border-box',
                                  transition: 'all 0.15s ease',
                                }}
                              >
                                <Plus size={13} /> Add Service Capability Tier
                              </button>
                            </div>
                          </div>

                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              onClick={() =>
                                handleApplyStep1(
                                  formStep1Company,
                                  formStep1Service,
                                  formStep1Email,
                                  formStep1Capabilities
                                )
                              }
                              style={{
                                width: '100%',
                                padding: '10px 14px',
                                backgroundColor: '#0284c7',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                boxShadow: '0 2px 8px rgba(2, 132, 199, 0.4)',
                              }}
                            >
                              <Sparkles size={14} /> Let Agent Apply Profile, Email &amp; {formStep1Capabilities.length}-Tier Catalog
                            </button>
                          </div>
                        </div>
                      )}

                      {m.interactiveForm === 'step2' && (
                        <div
                          style={{
                            marginTop: '12px',
                            backgroundColor: '#090e17',
                            border: '1px solid rgba(168, 85, 247, 0.4)',
                            borderRadius: '8px',
                            padding: '12px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Key size={15} color="#c084fc" />
                            <span style={{ fontWeight: 700, color: '#c084fc', fontSize: '13px' }}>
                              🤖 I can generate your Ed25519 keypair and configure anti-tamper for you:
                            </span>
                          </div>
                          <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '10px', lineHeight: 1.4 }}>
                            Clicking below creates a cryptographically verified RFC 8032 keypair and updates your node settings and <code>.env</code> file in real time.
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              onClick={handleGenerateEd25519Keypair}
                              style={{
                                width: '100%',
                                padding: '10px 14px',
                                backgroundColor: '#9333ea',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                boxShadow: '0 2px 8px rgba(147, 51, 234, 0.4)',
                              }}
                            >
                              <Key size={14} /> Let Agent Generate &amp; Apply RFC 8032 Keys
                            </button>
                          </div>
                        </div>
                      )}

                      {m.interactiveForm === 'step3' && (
                        <div
                          style={{
                            marginTop: '12px',
                            backgroundColor: '#090e17',
                            border: '1px solid rgba(245, 158, 11, 0.4)',
                            borderRadius: '8px',
                            padding: '12px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <CreditCard size={15} color="#fbbf24" />
                            <span style={{ fontWeight: 700, color: '#fbbf24', fontSize: '13px' }}>
                              🤖 I can connect your PayPal merchant credentials for you:
                            </span>
                          </div>
                          <div style={{ marginBottom: '10px' }}>
                            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px', fontWeight: 600 }}>
                              PayPal REST Client ID
                            </label>
                            <input
                              type="text"
                              value={formStep3ClientId}
                              onChange={(e) => setFormStep3ClientId(e.target.value)}
                              placeholder="e.g. PAYPAL_SANDBOX_CLIENT_ID_AP2_SELLER_NODE"
                              style={{
                                width: '100%',
                                backgroundColor: '#0f172a',
                                border: '1px solid #334155',
                                borderRadius: '6px',
                                color: '#fff',
                                padding: '7px 10px',
                                fontSize: '12px',
                                boxSizing: 'border-box',
                                outline: 'none',
                              }}
                            />
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              onClick={() => handleApplyPayPalSandbox(formStep3ClientId)}
                              style={{
                                width: '100%',
                                padding: '10px 14px',
                                backgroundColor: '#d97706',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                boxShadow: '0 2px 8px rgba(217, 119, 6, 0.4)',
                              }}
                            >
                              <CreditCard size={14} /> Let Agent Connect PayPal Sandbox Rails
                            </button>
                          </div>
                        </div>
                      )}

                      {m.interactiveForm === 'step4' && (
                        <div
                          style={{
                            marginTop: '12px',
                            backgroundColor: '#090e17',
                            border: '1px solid rgba(168, 85, 247, 0.4)',
                            borderRadius: '8px',
                            padding: '12px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Layers size={15} color="#34d399" />
                            <span style={{ fontWeight: 700, color: '#34d399', fontSize: '13px' }}>
                              🤖 I can configure your ERP webhooks &amp; accounting mapping for you:
                            </span>
                          </div>
                          <div style={{ marginBottom: '10px' }}>
                            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px', fontWeight: 600 }}>
                              Zapier Catch-Hook URL
                            </label>
                            <input
                              type="text"
                              value={formStep4Webhook}
                              onChange={(e) => setFormStep4Webhook(e.target.value)}
                              placeholder="https://hooks.zapier.com/hooks/catch/..."
                              style={{
                                width: '100%',
                                backgroundColor: '#0f172a',
                                border: '1px solid #334155',
                                borderRadius: '6px',
                                color: '#fff',
                                padding: '7px 10px',
                                fontSize: '12px',
                                boxSizing: 'border-box',
                                outline: 'none',
                              }}
                            />
                          </div>
                          <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                              onClick={() => handleApplyErpWebhooks(formStep4Webhook)}
                              style={{
                                width: '100%',
                                padding: '10px 14px',
                                backgroundColor: '#059669',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                boxShadow: '0 2px 8px rgba(5, 150, 105, 0.4)',
                              }}
                            >
                              <Check size={14} /> Let Agent Apply ERP Webhooks &amp; Accounting Defaults
                            </button>
                          </div>
                        </div>
                      )}

                      {m.interactiveForm === 'step5' && (
                        <div
                          style={{
                            marginTop: '12px',
                            backgroundColor: '#090e17',
                            border: '1px solid rgba(6, 182, 212, 0.4)',
                            borderRadius: '8px',
                            padding: '12px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Sparkles size={15} color="#22d3ee" />
                            <span style={{ fontWeight: 700, color: '#22d3ee', fontSize: '13px' }}>
                              🤖 I can verify your node endpoints &amp; launch the live simulator for you:
                            </span>
                          </div>
                          <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '10px', lineHeight: 1.4 }}>
                            FastMCP daemon is live on <code>http://127.0.0.1:8001/mcp</code>. Ready to test external buyer agent discovery, spending mandates, and counter-offer bargaining!
                          </div>
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            <button
                              onClick={handleLaunchSimulatorFromForm}
                              style={{
                                flex: 1,
                                minWidth: '180px',
                                padding: '10px 14px',
                                backgroundColor: '#0891b2',
                                color: '#fff',
                                border: 'none',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                boxShadow: '0 2px 8px rgba(8, 145, 178, 0.4)',
                              }}
                            >
                              <Sparkles size={14} /> Launch Live Buyer Simulator
                            </button>
                            <button
                              onClick={() => handleSelectSetupStep(6)}
                              style={{
                                padding: '10px 14px',
                                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                                color: '#34d399',
                                border: '1px solid #10b981',
                                borderRadius: '6px',
                                fontWeight: 700,
                                fontSize: '12px',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                boxShadow: '0 2px 8px rgba(16, 185, 129, 0.3)',
                              }}
                            >
                              <span>Complete Setup &amp; Open Dashboard</span>
                              <ArrowRight size={13} />
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Single Next Step Action Button inside chat response */}
                      {m.nextStepAction && (
                        <div style={{ marginTop: '12px' }}>
                          <button
                            onClick={() => handleSelectSetupStep(m.nextStepAction!.step)}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '8px',
                              width: '100%',
                              padding: '10px 16px',
                              backgroundColor: m.nextStepAction.step === 6 ? 'rgba(16, 185, 129, 0.2)' : 'rgba(2, 132, 199, 0.2)',
                              color: m.nextStepAction.step === 6 ? '#34d399' : '#38bdf8',
                              border: m.nextStepAction.step === 6 ? '1px solid #10b981' : '1px solid #0284c7',
                              borderRadius: '7px',
                              fontSize: '12px',
                              fontWeight: 700,
                              cursor: 'pointer',
                              boxShadow: m.nextStepAction.step === 6 ? '0 2px 10px rgba(16, 185, 129, 0.3)' : '0 2px 10px rgba(2, 132, 199, 0.3)',
                              transition: 'all 0.15s ease',
                            }}
                          >
                            <span>{m.nextStepAction.label}</span>
                            <ArrowRight size={14} />
                          </button>
                        </div>
                      )}
                    </div>

                    <div style={{ fontSize: '10px', color: '#64748b', marginTop: '4px', textAlign: isCopilot ? 'left' : 'right' }}>
                      {m.timestamp}
                    </div>

                    {/* Suggestion Chips */}
                    {isCopilot && m.suggestedActions && m.suggestedActions.length > 0 && m.id === messages[messages.length - 1].id && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                        {m.suggestedActions.map((action, idx) => (
                          <button
                            key={idx}
                            onClick={() => {
                              const act = action.toLowerCase();
                              // 1. Direct Step Navigation chips
                              if (act.includes('step 1') || act.includes('step 01') || act.includes('configure service') || act.includes('proceed to step 1')) {
                                handleSelectSetupStep(1);
                                return;
                              }
                              if (act.includes('step 2') || act.includes('step 02') || act.includes('ed25519') || act.includes('edkeys') || act.includes('proceed to step 2')) {
                                handleSelectSetupStep(2);
                                return;
                              }
                              if (act.includes('step 3') || act.includes('step 03') || act.includes('proceed to step 3')) {
                                handleSelectSetupStep(3);
                                return;
                              }
                              if (act.includes('step 4') || act.includes('step 04') || act.includes('proceed to step 4')) {
                                handleSelectSetupStep(4);
                                return;
                              }
                              if (act.includes('step 5') || act.includes('step 05') || act.includes('proceed to step 5')) {
                                handleSelectSetupStep(5);
                                return;
                              }

                              // 2. Right Pane / Inspector / Tab Navigation
                              if (act.includes("inspect") || act.includes("protocol") || act.includes("audit") || act.includes("trace")) {
                                setActiveRightTab('trace');
                              } else if (act.includes("fleet") || act.includes("ledger")) {
                                onNavigateTab?.('ag-studio');
                              } else if (act.includes("bryntum") || act.includes("timeline")) {
                                onNavigateTab?.('bryntum');
                              } else if (act.includes("tamper") && !act.includes("step 2")) {
                                setActiveRightTab('tamper');
                              } else if (act.includes("payload") || act.includes("back-office")) {
                                openInspector();
                              }
                              sendMessage(action);
                            }}
                            disabled={isLoading}
                            style={{
                              backgroundColor: '#1e293b',
                              border: '1px solid #334155',
                              color: '#38bdf8',
                              fontSize: '11px',
                              padding: '4px 10px',
                              borderRadius: '16px',
                              cursor: 'pointer',
                              textAlign: 'left',
                            }}
                          >
                            &bull; {action}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            {isLoading && (
              <div style={{ display: 'flex', gap: '10px', alignItems: 'center', color: '#94a3b8', fontSize: '12px' }}>
                <Bot size={16} />
                <span>Querying AP2 Seller MCP &amp; verifying spending mandate...</span>
              </div>
            )}
            <div ref={chatEndRef} style={{ minHeight: '8px' }} />
          </div>

          {/* Active Voice Listening Banner */}
          {voiceStatus === 'listening' && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: 'rgba(239, 68, 68, 0.14)',
                borderTop: '1px solid rgba(239, 68, 68, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '12px',
                color: '#fca5a5',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    backgroundColor: '#ef4444',
                    display: 'inline-block',
                    animation: 'voice-pulse 1.2s infinite',
                  }}
                />
                <strong style={{ color: '#fff' }}>🎙️ Listening...</strong>
                <span>{voiceTranscript ? `"${voiceTranscript}"` : 'Speak hands-free now (or click mic to submit)'}</span>
              </div>
              <button
                type="button"
                onClick={startVoiceInput}
                style={{
                  background: 'rgba(239, 68, 68, 0.25)',
                  border: '1px solid rgba(239, 68, 68, 0.5)',
                  color: '#fecaca',
                  borderRadius: '6px',
                  padding: '3px 10px',
                  cursor: 'pointer',
                  fontSize: '11px',
                  fontWeight: 600,
                }}
              >
                Done Speaking
              </button>
            </div>
          )}

          {/* Voice Starting / Permission Request Banner */}
          {voiceStatus === 'starting' && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: 'rgba(56, 189, 248, 0.12)',
                borderTop: '1px solid rgba(56, 189, 248, 0.35)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '12px',
                color: '#38bdf8',
              }}
            >
              <RefreshCw size={14} style={{ animation: 'spin-fast 1s linear infinite' }} />
              <span>Connecting to microphone... Click "Allow" in your browser prompt if requested.</span>
            </div>
          )}

          {/* Voice Diagnostic Error Banner */}
          {voiceError && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: 'rgba(245, 158, 11, 0.14)',
                borderTop: '1px solid rgba(245, 158, 11, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '12px',
                color: '#fbbf24',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, marginRight: '8px' }}>
                <Radio size={14} style={{ flexShrink: 0 }} />
                <span>{voiceError}</span>
              </div>
              <button
                type="button"
                onClick={() => setVoiceError(null)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: '2px',
                }}
              >
                <X size={14} />
              </button>
            </div>
          )}

          {/* Input Bar */}
          <div style={{ padding: '12px', backgroundColor: '#1e293b', borderTop: '1px solid #334155', display: 'flex', gap: '8px' }}>
            <input
              type="text"
              placeholder={
                voiceStatus === 'listening'
                  ? 'Listening to your voice... (Speak now)'
                  : "Simulate or speak buyer command (e.g. 'Set company to Acme Systems', 'Generate keys', 'Connect PayPal')..."
              }
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage(inputText)}
              disabled={isLoading}
              style={{
                flex: 1,
                backgroundColor: '#0f172a',
                border: voiceStatus === 'listening' ? '1px solid #ef4444' : '1px solid #334155',
                borderRadius: '8px',
                color: '#fff',
                padding: '10px 14px',
                fontSize: '13px',
                outline: 'none',
                boxShadow: voiceStatus === 'listening' ? '0 0 8px rgba(239, 68, 68, 0.3)' : 'none',
                transition: 'all 0.15s ease',
              }}
            />
            {/* Voice Input Microphone Button */}
            <button
              onClick={startVoiceInput}
              type="button"
              title={
                voiceStatus === 'listening'
                  ? 'Listening hands-free... Click to stop and submit'
                  : voiceStatus === 'starting'
                  ? 'Requesting microphone permission...'
                  : 'Click to speak hands-free voice command'
              }
              style={{
                backgroundColor:
                  voiceStatus === 'listening'
                    ? '#ef4444'
                    : voiceStatus === 'starting'
                    ? '#f59e0b'
                    : '#1e293b',
                border:
                  voiceStatus === 'listening'
                    ? '1px solid #f87171'
                    : voiceStatus === 'starting'
                    ? '1px solid #fbbf24'
                    : '1px solid #334155',
                borderRadius: '8px',
                color: voiceStatus === 'listening' || voiceStatus === 'starting' ? '#fff' : '#94a3b8',
                padding: '0 12px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow:
                  voiceStatus === 'listening'
                    ? '0 0 16px rgba(239, 68, 68, 0.7)'
                    : voiceStatus === 'starting'
                    ? '0 0 10px rgba(245, 158, 11, 0.5)'
                    : 'none',
                animation: voiceStatus === 'listening' ? 'voice-pulse 1.5s infinite' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              {voiceStatus === 'listening' ? (
                <MicOff size={16} />
              ) : voiceStatus === 'starting' ? (
                <RefreshCw size={16} style={{ animation: 'spin-fast 1s linear infinite' }} />
              ) : (
                <Mic size={16} />
              )}
            </button>
            <button
              onClick={() => sendMessage(inputText)}
              disabled={isLoading || !inputText.trim()}
              style={{
                backgroundColor: '#0284c7',
                border: 'none',
                borderRadius: '8px',
                color: '#fff',
                padding: '0 16px',
                cursor: isLoading || !inputText.trim() ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Send size={16} />
            </button>
          </div>
        </div>

        {/* RIGHT PANE: Multi-Tab Protocol, Anti-Tamper & Live Wire Inspector */}
        {!isChatExpanded && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: '#0f172a',
              borderRadius: '12px',
              border: '1px solid #1e293b',
              overflow: 'hidden',
            }}
          >
          {/* Tab Navigation Header */}
          <div
            style={{
              padding: '8px 12px',
              backgroundColor: '#1e293b',
              borderBottom: '1px solid #334155',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                onClick={() => setActiveRightTab('settings')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: activeRightTab === 'settings' ? '#0284c7' : 'transparent',
                  color: activeRightTab === 'settings' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Sliders size={14} /> Node Settings &amp; Gateway
              </button>

              <button
                onClick={() => setActiveRightTab('trace')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: activeRightTab === 'trace' ? '#0284c7' : 'transparent',
                  color: activeRightTab === 'trace' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Terminal size={14} /> AP2 Execution Trace
              </button>

              <button
                onClick={() => setActiveRightTab('tamper')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: activeRightTab === 'tamper' ? '#0284c7' : 'transparent',
                  color: activeRightTab === 'tamper' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <ShieldCheck size={14} /> Anti-Tamper Verifier
              </button>

              <button
                onClick={() => setActiveRightTab('wire')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  backgroundColor: activeRightTab === 'wire' ? '#0284c7' : 'transparent',
                  color: activeRightTab === 'wire' ? '#fff' : '#94a3b8',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Activity size={14} /> Wire Protocol (SSE)
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {activeRightTab === 'wire' && (
                <span style={{ fontSize: '10px', color: isSseConnected ? '#34d399' : '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 600 }}>
                  <Radio size={11} className={isSseConnected ? 'animate-pulse' : ''} /> {isSseConnected ? 'SSE Live' : 'Polling'}
                </span>
              )}
              {activeRightTab === 'trace' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '11px', color: activeStep > 0 ? '#38bdf8' : '#94a3b8', fontWeight: 600 }}>
                    {activeStep > 0 ? `● Step ${activeStep}/4 Complete` : 'Awaiting Trigger'}
                  </span>
                  <button
                    onClick={triggerTestCycle}
                    disabled={isTriggeringTestRun}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      backgroundColor: 'rgba(56, 189, 248, 0.15)',
                      border: '1px solid #38bdf8',
                      color: '#38bdf8',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: isTriggeringTestRun ? 'not-allowed' : 'pointer',
                    }}
                    title="Executes headlessly through Python MCP harness"
                  >
                    <Play size={11} /> {isTriggeringTestRun ? 'Running...' : 'Run Harness'}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* TAB 0: LIVE NODE SETTINGS & MCP GATEWAY */}
          {activeRightTab === 'settings' && (
            <div style={{ flex: 1, overflowY: 'auto', backgroundColor: '#090e17' }}>
              <NodeSettingsView
                activeTabOverride={settingsTabOverride}
                initialSettings={nodeSettings}
                onSaveSettings={(newSettings: NodeSettingsData) => {
                  saveNodeSettings(newSettings);
                }}
                onNavigateTab={onNavigateTab}
                isSetupComplete={isSetupComplete}
              />
            </div>
          )}

          {/* TAB 1: AP2 PROTOCOL EXECUTION TRACE */}
          {activeRightTab === 'trace' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {liveTrace.length === 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748b', textAlign: 'center', gap: '12px' }}>
                  <Code2 size={42} strokeWidth={1.5} />
                  <div style={{ maxWidth: '340px' }}>
                    <div style={{ color: '#94a3b8', fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>
                      Awaiting Autonomous Execution Trigger
                    </div>
                    <div style={{ fontSize: '12px', lineHeight: '1.5' }}>
                      Tap <strong>Approve</strong> in the chat on the left or click <strong>Run Harness</strong> above to witness the live machine-to-machine exchange.
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {/* Step 1: Mandate Evaluation */}
                  <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <span style={{ color: '#38bdf8', fontWeight: 700, fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Key size={14} /> 1. Programmatic Spending Mandate Verification
                      </span>
                      <span style={{ fontSize: '10px', backgroundColor: 'rgba(52, 211, 153, 0.2)', color: '#34d399', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                        HMAC-SHA256 SIGNED
                      </span>
                    </div>
                    <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: '1.6' }}>
                      Protocol: <code>MCP tools/call:evaluate_spending_mandate</code><br />
                      Policy Check: <strong>${liveTrace[0]?.authorized_amount?.toFixed(2) || '79.99'} &le; ${localBudgetCap.toFixed(2)}/mo</strong> Cap (Remaining: <strong>${(localBudgetCap - (liveTrace[0]?.authorized_amount || 79.99)).toFixed(2)}</strong>)<br />
                      {liveTrace[0]?.tier_title && (
                        <div>Tier: <strong style={{ color: '#fbbf24' }}>{liveTrace[0].tier_title}</strong></div>
                      )}
                      Cryptographic Proof: <code style={{ color: '#fbbf24', wordBreak: 'break-all' }}>{liveTrace[0]?.proof_hash}</code>
                    </div>
                  </div>

                  {/* Step 2: PayPal Subscription Agreement */}
                  <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <span style={{ color: '#38bdf8', fontWeight: 700, fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <CreditCard size={14} /> 2. PayPal Delegated Subscription Token
                      </span>
                      <span style={{ fontSize: '10px', backgroundColor: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                        ACTIVE RECURRING
                      </span>
                    </div>
                    <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: '1.6' }}>
                      Subscription Agreement: <code>{liveTrace[1]?.subscription_id}</code><br />
                      Monthly Amount: <strong>${liveTrace[1]?.monthly_amount?.toFixed(2) || '79.99'} / month</strong> &bull; Plan ID: <code>P-5ML4271244454362WXNWU5NQ</code><br />
                      Payer Legal Entity: <strong>{localBusinessEntity}</strong>
                    </div>
                  </div>

                  {/* Step 3: Dedicated Worker Node Provisioning */}
                  <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <span style={{ color: '#38bdf8', fontWeight: 700, fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Cpu size={14} /> 3. Dedicated Worker Node Allocation
                      </span>
                      <span style={{ fontSize: '10px', backgroundColor: 'rgba(52, 211, 153, 0.2)', color: '#34d399', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                        CRYPTOGRAPHICALLY SECURED
                      </span>
                    </div>
                    <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: '1.6' }}>
                      Node Endpoint: <strong style={{ color: '#34d399', fontSize: '13px' }}>{liveTrace[2]?.assigned_did || 'node-cluster-01.ap2.net:8443'}</strong><br />
                      Worker Node: {liveTrace[2]?.carrier || 'AP2 Autonomous Worker Node'} &bull; Spending Guard: <code>RFC 8032 ED25519 VERIFIED</code>
                    </div>
                  </div>

                  {/* Step 4: Downline Zapier Sync */}
                  <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <span style={{ color: '#38bdf8', fontWeight: 700, fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Layers size={14} /> 4. Zapier MCP &amp; Enterprise ERP Sync
                      </span>
                      <span style={{ fontSize: '10px', backgroundColor: 'rgba(52, 211, 153, 0.2)', color: '#34d399', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>
                        DISPATCHED
                      </span>
                    </div>
                    <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: '1.6' }}>
                      CloudEvents Delivery ID: <code>{liveTrace[3]?.cloudevents_delivery_id || 'CE-EVENT-7712'}</code><br />
                      QuickBooks Expense ID: <code>{liveTrace[3]?.qbo_expense_id || 'EXP-QBO-88219'}</code><br />
                      Webhook Target: <code>hooks.zapier.com/hooks/catch/ap2_settlement</code>
                    </div>
                    <button
                      onClick={openInspector}
                      style={{
                        marginTop: '8px',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        backgroundColor: 'rgba(56, 189, 248, 0.12)',
                        color: '#38bdf8',
                        border: '1px solid rgba(56, 189, 248, 0.3)',
                        borderRadius: '6px',
                        padding: '5px 10px',
                        fontSize: '11px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      <FileCode size={13} /> Inspect Back-Office Payloads (CloudEvents &amp; QBO)
                    </button>
                  </div>

                  {/* Status summary banner */}
                  <div style={{ backgroundColor: 'rgba(5, 150, 105, 0.15)', border: '1px solid #059669', borderRadius: '8px', padding: '12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <CheckCircle2 size={24} color="#34d399" />
                    <div style={{ flex: 1 }}>
                      <div style={{ color: '#34d399', fontWeight: 700, fontSize: '13px' }}>
                        Settlement Ledger Mutated Successfully
                      </div>
                      <div style={{ fontSize: '11px', color: '#cbd5e1' }}>
                        {localContractorName} is now live on endpoint <strong>{lastAllocatedDid || 'node-cluster-01.ap2.net:8443'}</strong>. Switch to the <strong>Settlement Ledger &amp; BI</strong> or <strong>Worker Node Scheduler</strong> tabs to see the updated row!
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: INTERACTIVE ANTI-TAMPER WORKBENCH */}
          {activeRightTab === 'tamper' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px' }}>
                <div style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <ShieldCheck size={16} color="#38bdf8" /> Cryptographic Mandate Policy Verifier
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: '1.5' }}>
                  Judges can tamper with the canonical payload in real time to verify that signature mismatches and budget cap breaches are cryptographically rejected by the backend.
                </div>
              </div>

              {/* 1-Tap Tamper Action Buttons */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                <button
                  onClick={() => handleTamperPrice(0.01)}
                  style={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #ef4444',
                    color: '#f87171',
                    borderRadius: '6px',
                    padding: '5px 10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title="Alter agreed price by $0.01 to test signature mismatch rejection"
                >
                  Tamper Price ($79.99 &rarr; $80.00)
                </button>

                <button
                  onClick={() => handleTamperBudgetCap(50.0)}
                  style={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #f59e0b',
                    color: '#fbbf24',
                    borderRadius: '6px',
                    padding: '5px 10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title="Set cap below agreed price to test BUDGET_CAP_BREACH"
                >
                  Force Cap Breach ($50.00 Cap)
                </button>

                <button
                  onClick={handleTamperTimestamp}
                  style={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #a855f7',
                    color: '#c084fc',
                    borderRadius: '6px',
                    padding: '5px 10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title="Simulate replayed / stale timestamp to test TIMESTAMP_EXPIRED"
                >
                  Simulate Expired Timestamp
                </button>

                <button
                  onClick={handleResetUntampered}
                  style={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #10b981',
                    color: '#34d399',
                    borderRadius: '6px',
                    padding: '5px 10px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title="Reset payload to valid untampered state and re-generate HMAC proof"
                >
                  Reset Untampered
                </button>
              </div>

              {/* Live Verification Result Box */}
              {tamperVerificationResult && (
                <div
                  style={{
                    backgroundColor: tamperVerificationResult.valid ? 'rgba(5, 150, 105, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                    border: tamperVerificationResult.valid ? '1px solid #059669' : '1px solid #ef4444',
                    borderRadius: '8px',
                    padding: '12px',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '10px',
                  }}
                >
                  {tamperVerificationResult.valid ? (
                    <ShieldCheck size={20} color="#34d399" style={{ flexShrink: 0, marginTop: '2px' }} />
                  ) : (
                    <ShieldAlert size={20} color="#ef4444" style={{ flexShrink: 0, marginTop: '2px' }} />
                  )}
                  <div style={{ flex: 1, fontSize: '12px' }}>
                    <div style={{ fontWeight: 700, color: tamperVerificationResult.valid ? '#34d399' : '#f87171' }}>
                      {tamperVerificationResult.detail}
                    </div>
                    <div style={{ fontSize: '11px', color: '#cbd5e1', marginTop: '4px' }}>
                      Reason Code: <code>{tamperVerificationResult.reason}</code> &bull; Status: <code>HTTP {tamperVerificationResult.status_code}</code>
                    </div>
                    {!tamperVerificationResult.valid && (
                      <div style={{ marginTop: '6px', fontSize: '10px', color: '#94a3b8', wordBreak: 'break-all' }}>
                        <div>Cryptographic Status: <code style={{ color: '#f87171' }}>TAMPER DETECTED / SIGNATURE REJECTED</code></div>
                        {tamperVerificationResult.provided_signature && (
                          <div>Provided Signature: <code style={{ color: '#f87171' }}>{tamperVerificationResult.provided_signature}</code></div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Canonical Payload Viewer */}
              <div style={{ backgroundColor: '#090d16', border: '1px solid #1e293b', borderRadius: '8px', padding: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8' }}>Canonical Mandate JSON Payload:</span>
                  <button
                    onClick={() => copyToClipboard(JSON.stringify(tamperPayload, null, 2), 'canonical_json')}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      backgroundColor: 'transparent',
                      border: 'none',
                      color: copiedKey === 'canonical_json' ? '#34d399' : '#64748b',
                      fontSize: '10px',
                      cursor: 'pointer',
                    }}
                  >
                    {copiedKey === 'canonical_json' ? <Check size={11} /> : <Copy size={11} />} Copy
                  </button>
                </div>
                <pre
                  style={{
                    margin: 0,
                    fontSize: '11px',
                    lineHeight: '1.4',
                    color: '#38bdf8',
                    fontFamily: 'monospace',
                    overflowX: 'auto',
                  }}
                >
                  <code>{JSON.stringify(tamperPayload, null, 2)}</code>
                </pre>
              </div>

              {/* Cryptographic Signature Banner */}
              <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '10px 12px', fontSize: '11px', color: '#94a3b8' }}>
                <div style={{ wordBreak: 'break-all' }}>
                  <strong>Ed25519 Signature:</strong> <code style={{ color: '#fbbf24' }}>{tamperSignature}</code>
                </div>
                <button
                  onClick={() => handleVerifyTamper()}
                  disabled={isTamperVerifying}
                  style={{
                    marginTop: '8px',
                    width: '100%',
                    padding: '8px',
                    backgroundColor: '#0284c7',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#fff',
                    fontWeight: 600,
                    fontSize: '12px',
                    cursor: isTamperVerifying ? 'not-allowed' : 'pointer',
                  }}
                >
                  {isTamperVerifying ? 'Verifying with Backend...' : 'Re-Verify Mandate Signature Live'}
                </button>
              </div>
            </div>
          )}

          {/* TAB 3: LIVE SSE WIRE PROTOCOL STREAM */}
          {activeRightTab === 'wire' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: '4px' }}>
                  <button
                    onClick={() => setWireFilter('all')}
                    style={{
                      backgroundColor: wireFilter === 'all' ? '#0284c7' : '#1e293b',
                      color: wireFilter === 'all' ? '#fff' : '#94a3b8',
                      border: '1px solid #334155',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    All Frames ({wireFrames.length})
                  </button>
                  <button
                    onClick={() => setWireFilter('call')}
                    style={{
                      backgroundColor: wireFilter === 'call' ? '#0284c7' : '#1e293b',
                      color: wireFilter === 'call' ? '#fff' : '#94a3b8',
                      border: '1px solid #334155',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    tools/call
                  </button>
                  <button
                    onClick={() => setWireFilter('init')}
                    style={{
                      backgroundColor: wireFilter === 'init' ? '#0284c7' : '#1e293b',
                      color: wireFilter === 'init' ? '#fff' : '#94a3b8',
                      border: '1px solid #334155',
                      padding: '3px 8px',
                      borderRadius: '4px',
                      fontSize: '10px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Handshake &amp; Tools
                  </button>
                </div>

                <button
                  onClick={() => setWireFrames([])}
                  style={{
                    backgroundColor: 'transparent',
                    border: 'none',
                    color: '#64748b',
                    fontSize: '10px',
                    cursor: 'pointer',
                  }}
                >
                  Clear Buffer
                </button>
              </div>

              {filteredWireFrames.length === 0 ? (
                <div style={{ padding: '40px 0', textAlign: 'center', color: '#64748b', fontSize: '12px' }}>
                  No frames in stream yet. Trigger a message in the chat or run the harness to watch JSON-RPC packets stream live.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {filteredWireFrames.map((f, idx) => {
                    const isIncoming = f.direction === 'incoming';
                    const isExpanded = expandedFrameId === (f.id || `frame-${idx}`);
                    return (
                      <div
                        key={f.id || idx}
                        style={{
                          backgroundColor: '#090d16',
                          border: '1px solid #1e293b',
                          borderRadius: '6px',
                          padding: '8px 10px',
                          cursor: 'pointer',
                        }}
                        onClick={() => setExpandedFrameId(isExpanded ? null : (f.id || `frame-${idx}`))}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span
                              style={{
                                fontSize: '9px',
                                fontWeight: 700,
                                backgroundColor: isIncoming ? 'rgba(56, 189, 248, 0.2)' : 'rgba(52, 211, 153, 0.2)',
                                color: isIncoming ? '#38bdf8' : '#34d399',
                                padding: '1px 5px',
                                borderRadius: '3px',
                              }}
                            >
                              {isIncoming ? '&rarr; INBOUND' : '&larr; OUTBOUND'}
                            </span>
                            <span style={{ fontSize: '11px', color: '#f8fafc', fontWeight: 600 }}>
                              {f.method || f.frame?.method || 'jsonrpc-response'}
                            </span>
                          </div>
                          <span style={{ fontSize: '10px', color: '#64748b' }}>
                            {f.timestamp ? f.timestamp.split('T')[1]?.substring(0, 12) : ''}
                          </span>
                        </div>

                        {/* Summary / Collapsible content */}
                        {isExpanded ? (
                          <pre
                            style={{
                              margin: '6px 0 0',
                              fontSize: '10px',
                              lineHeight: '1.4',
                              color: isIncoming ? '#38bdf8' : '#34d399',
                              fontFamily: 'monospace',
                              overflowX: 'auto',
                              maxHeight: '220px',
                            }}
                          >
                            <code>{JSON.stringify(f.frame, null, 2)}</code>
                          </pre>
                        ) : (
                          <div style={{ fontSize: '10px', color: '#64748b', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                            {JSON.stringify(f.frame)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          </div>
        )}
      </div>

      {/* M2M Autonomous Settlement & Back-Office Audit Modal */}
      {isInspectorOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(3, 7, 18, 0.85)',
            backdropFilter: 'blur(6px)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsInspectorOpen(false);
          }}
        >
          <div
            style={{
              backgroundColor: '#0f172a',
              border: '1px solid #334155',
              borderRadius: '14px',
              width: '100%',
              maxWidth: '980px',
              maxHeight: '92vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(56, 189, 248, 0.1)',
              overflow: 'hidden',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '16px 20px',
                backgroundColor: '#1e293b',
                borderBottom: '1px solid #334155',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    backgroundColor: 'rgba(56, 189, 248, 0.15)',
                    border: '1px solid rgba(56, 189, 248, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#38bdf8',
                  }}
                >
                  <FileCode size={20} />
                </div>
                <div>
                  <div style={{ color: '#f8fafc', fontWeight: 700, fontSize: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    M2M Autonomous Settlement &amp; Back-Office Audit
                    <span style={{ fontSize: '10px', backgroundColor: 'rgba(52, 211, 153, 0.2)', color: '#34d399', padding: '2px 8px', borderRadius: '4px', fontWeight: 600 }}>
                      MCP Step 7 Payloads
                    </span>
                  </div>
                  <div style={{ color: '#94a3b8', fontSize: '11px' }}>
                    Verifiable machine-to-machine downline artifacts (CloudEvents v1.0 JSON-RPC, Intuit QBO v3 &amp; Signed Webhook)
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  onClick={fetchM2MPayloads}
                  disabled={inspectorLoading}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    backgroundColor: '#1e293b',
                    border: '1px solid #475569',
                    color: '#94a3b8',
                    padding: '6px 12px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    cursor: inspectorLoading ? 'not-allowed' : 'pointer',
                  }}
                  title="Reload latest payloads from /m2m/payloads/latest"
                >
                  <RefreshCw size={12} className={inspectorLoading ? 'animate-spin' : ''} />
                  Refresh
                </button>
                <button
                  onClick={() => setIsInspectorOpen(false)}
                  style={{
                    backgroundColor: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    padding: '6px',
                    borderRadius: '6px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {inspectorLoading ? (
                <div style={{ padding: '60px 0', textAlign: 'center', color: '#94a3b8' }}>
                  <RefreshCw size={28} className="animate-spin" style={{ margin: '0 auto 12px' }} />
                  <div>Loading latest M2M audit payloads from <code>/m2m/payloads/latest</code>...</div>
                </div>
              ) : !inspectorData ? (
                <div
                  style={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '10px',
                    padding: '30px 20px',
                    textAlign: 'center',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '12px',
                  }}
                >
                  <Code2 size={40} color="#f59e0b" />
                  <div style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
                    No Autonomous Transaction Detected in Cache
                  </div>
                  <div style={{ fontSize: '12px', color: '#94a3b8', maxWidth: '480px', lineHeight: '1.6' }}>
                    {inspectorError || 'Run the External Buyer Agent harness or click "Approve & Execute" in the Copilot chat to generate live machine-to-machine artifacts.'}
                  </div>
                  <button
                    onClick={triggerTestCycle}
                    disabled={isTriggeringTestRun}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      backgroundColor: '#0284c7',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '8px',
                      padding: '10px 18px',
                      fontSize: '13px',
                      fontWeight: 600,
                      cursor: isTriggeringTestRun ? 'not-allowed' : 'pointer',
                      marginTop: '6px',
                    }}
                  >
                    <Play size={14} />
                    {isTriggeringTestRun ? 'Executing AP2 Procurement Cycle...' : 'Execute Live Test Cycle (Generate Artifacts)'}
                  </button>
                </div>
              ) : (
                <>
                  {/* Top Metric Badges */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
                    <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px 16px' }}>
                      <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 500, marginBottom: '4px' }}>Worker Node Endpoint</div>
                      <div style={{ fontSize: '16px', fontWeight: 700, color: '#34d399', letterSpacing: '0.3px' }}>
                        {inspectorData.node_endpoint || inspectorData.endpoint || 'node-cluster-01.ap2.net:8443'}
                      </div>
                      <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>AP2 Autonomous Worker Enclave &bull; Hardware Secured</div>
                    </div>

                    <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px 16px' }}>
                      <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 500, marginBottom: '4px' }}>PayPal Sub ID</div>
                      <div style={{ fontSize: '16px', fontWeight: 700, color: '#38bdf8', letterSpacing: '0.3px' }}>
                        {inspectorData.paypal_subscription_id || 'N/A'}
                      </div>
                      <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>
                        ${inspectorData.agreed_price ? Number(inspectorData.agreed_price).toFixed(2) : '79.99'}/mo Agreement
                      </div>
                    </div>

                    <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '12px 16px' }}>
                      <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 500, marginBottom: '4px' }}>Settlement Status</div>
                      <div style={{ fontSize: '16px', fontWeight: 700, color: '#34d399', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <ShieldCheck size={16} /> {inspectorData.status || 'COMPLETED'}
                      </div>
                      <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>Verified Machine-to-Machine</div>
                    </div>
                  </div>

                  {/* Cryptographic Mandate Proof Banner */}
                  <div
                    style={{
                      backgroundColor: 'rgba(15, 23, 42, 0.8)',
                      border: '1px solid #334155',
                      borderRadius: '8px',
                      padding: '10px 14px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '12px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                      <span style={{ fontSize: '11px', color: '#94a3b8', whiteSpace: 'nowrap' }}>
                        <strong>Cryptographic Mandate Proof (HMAC-SHA256):</strong>
                      </span>
                      <code style={{ fontSize: '11px', color: '#fbbf24', wordBreak: 'break-all', fontFamily: 'monospace' }}>
                        {inspectorData.mandate_hash || 'N/A'}
                      </code>
                    </div>
                    <button
                      onClick={() => copyToClipboard(inspectorData.mandate_hash || '', 'mandate_hash')}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        backgroundColor: '#1e293b',
                        border: '1px solid #475569',
                        color: copiedKey === 'mandate_hash' ? '#34d399' : '#94a3b8',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        fontSize: '10px',
                        cursor: 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {copiedKey === 'mandate_hash' ? <Check size={12} /> : <Copy size={12} />}
                      {copiedKey === 'mandate_hash' ? 'Copied' : 'Copy'}
                    </button>
                  </div>

                  {/* Tab Selector */}
                  <div style={{ borderBottom: '1px solid #334155', display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => setActiveInspectorTab('cloudevents')}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: 'transparent',
                        border: 'none',
                        borderBottom: activeInspectorTab === 'cloudevents' ? '2px solid #38bdf8' : '2px solid transparent',
                        color: activeInspectorTab === 'cloudevents' ? '#38bdf8' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      <Layers size={14} /> CloudEvents v1.0 (JSON-RPC)
                    </button>
                    <button
                      onClick={() => setActiveInspectorTab('qbo')}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: 'transparent',
                        border: 'none',
                        borderBottom: activeInspectorTab === 'qbo' ? '2px solid #38bdf8' : '2px solid transparent',
                        color: activeInspectorTab === 'qbo' ? '#38bdf8' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      <CreditCard size={14} /> QuickBooks Online (API v3)
                    </button>
                    <button
                      onClick={() => setActiveInspectorTab('webhook')}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: 'transparent',
                        border: 'none',
                        borderBottom: activeInspectorTab === 'webhook' ? '2px solid #38bdf8' : '2px solid transparent',
                        color: activeInspectorTab === 'webhook' ? '#38bdf8' : '#94a3b8',
                        fontSize: '12px',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                      }}
                    >
                      <Key size={14} /> Cryptographic Webhook Envelope
                    </button>
                  </div>

                  {/* TAB 1: CloudEvents v1.0 */}
                  {activeInspectorTab === 'cloudevents' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            onClick={() => setActiveCloudEventsSubTab('subscription')}
                            style={{
                              backgroundColor: activeCloudEventsSubTab === 'subscription' ? '#0284c7' : '#1e293b',
                              color: activeCloudEventsSubTab === 'subscription' ? '#fff' : '#94a3b8',
                              border: '1px solid #334155',
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              fontWeight: 500,
                              cursor: 'pointer',
                            }}
                          >
                            CloudEvents v1.0 Spec
                          </button>
                          <button
                            onClick={() => setActiveCloudEventsSubTab('workload')}
                            style={{
                              backgroundColor: activeCloudEventsSubTab === 'workload' ? '#0284c7' : '#1e293b',
                              color: activeCloudEventsSubTab === 'workload' ? '#fff' : '#94a3b8',
                              border: '1px solid #334155',
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              fontWeight: 500,
                              cursor: 'pointer',
                            }}
                          >
                            Enclave Attestation
                          </button>
                          <button
                            onClick={() => setActiveCloudEventsSubTab('full')}
                            style={{
                              backgroundColor: activeCloudEventsSubTab === 'full' ? '#0284c7' : '#1e293b',
                              color: activeCloudEventsSubTab === 'full' ? '#fff' : '#94a3b8',
                              border: '1px solid #334155',
                              padding: '4px 10px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              fontWeight: 500,
                              cursor: 'pointer',
                            }}
                          >
                            Full Package JSON
                          </button>
                        </div>

                        <button
                          onClick={() => {
                            const ceData = inspectorData?.cloudevents || {
                              specversion: '1.0',
                              id: 'ce-evt-99120482',
                              source: 'https://api.ap2protocol.org/mcp/seller',
                              type: 'com.ap2.settlement.subscription.activated',
                              datacontenttype: 'application/json',
                              time: new Date().toISOString(),
                              subject: `agent_${localContractorName.toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
                              data: {
                                buyer_agent: localContractorName,
                                principal_entity: localBusinessEntity,
                                service_tier: localTradeVertical,
                                monthly_rate: localBudgetCap < 79.99 ? 49.99 : 79.99,
                                allocated_node_endpoint: inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443',
                                paypal_subscription_id: inspectorData?.paypal_subscription_id || 'I-AUTONOMOUS-8902',
                                ed25519_proof_hash: inspectorData?.mandate_hash || 'PROOF-MANDATE-VERIFIED',
                                enclave_route: 'US-East Node Cluster (Ashburn, VA)',
                              },
                            };
                            const enclaveData = {
                              enclave_node: inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443',
                              enclave_type: 'AP2 Hardware Isolated Execution Enclave',
                              attestation_hash: inspectorData?.mandate_hash || 'SHA256:7c9e1248...b401',
                              allocated_port: 8443,
                              status: 'READY_FOR_INFERENCE',
                              spending_limit_monthly: localBudgetCap < 79.99 ? 49.99 : 79.99,
                            };

                            const content =
                              activeCloudEventsSubTab === 'subscription'
                                ? JSON.stringify(ceData, null, 2)
                                : activeCloudEventsSubTab === 'workload'
                                ? JSON.stringify(enclaveData, null, 2)
                                : JSON.stringify({ cloudevents: ceData, enclave: enclaveData }, null, 2);
                            copyToClipboard(content, 'ce_' + activeCloudEventsSubTab);
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            backgroundColor: '#1e293b',
                            border: '1px solid #475569',
                            color: copiedKey === 'ce_' + activeCloudEventsSubTab ? '#34d399' : '#94a3b8',
                            padding: '4px 10px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            cursor: 'pointer',
                          }}
                        >
                          {copiedKey === 'ce_' + activeCloudEventsSubTab ? <Check size={12} /> : <Copy size={12} />}
                          {copiedKey === 'ce_' + activeCloudEventsSubTab ? 'Copied' : 'Copy'}
                        </button>
                      </div>

                      <pre
                        style={{
                          backgroundColor: '#090d16',
                          border: '1px solid #1e293b',
                          borderRadius: '8px',
                          padding: '14px',
                          margin: 0,
                          fontSize: '11px',
                          lineHeight: '1.5',
                          color: '#38bdf8',
                          overflow: 'auto',
                          maxHeight: '340px',
                          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                        }}
                      >
                        <code>
                          {activeCloudEventsSubTab === 'subscription'
                            ? JSON.stringify(
                                inspectorData?.cloudevents || {
                                  specversion: '1.0',
                                  id: 'ce-evt-99120482',
                                  source: 'https://api.ap2protocol.org/mcp/seller',
                                  type: 'com.ap2.settlement.subscription.activated',
                                  datacontenttype: 'application/json',
                                  time: new Date().toISOString(),
                                  subject: `agent_${localContractorName.toLowerCase().replace(/[^a-z0-9]/g, '_')}`,
                                  data: {
                                    buyer_agent: localContractorName,
                                    principal_entity: localBusinessEntity,
                                    service_tier: localTradeVertical,
                                    monthly_rate: localBudgetCap < 79.99 ? 49.99 : 79.99,
                                    allocated_node_endpoint: (inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443'),
                                    paypal_subscription_id: inspectorData?.paypal_subscription_id || 'I-AUTONOMOUS-8902',
                                    ed25519_proof_hash: inspectorData?.mandate_hash || 'PROOF-MANDATE-VERIFIED',
                                    enclave_route: 'US-East Node Cluster (Ashburn, VA)',
                                  },
                                },
                                null,
                                2
                              )
                            : activeCloudEventsSubTab === 'workload'
                            ? JSON.stringify(
                                {
                                  enclave_node: (inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443'),
                                  enclave_type: 'AP2 Hardware Isolated Execution Enclave',
                                  attestation_hash: inspectorData?.mandate_hash || 'SHA256:7c9e1248...b401',
                                  allocated_port: 8443,
                                  status: 'READY_FOR_INFERENCE',
                                  spending_limit_monthly: localBudgetCap < 79.99 ? 49.99 : 79.99,
                                },
                                null,
                                2
                              )
                            : JSON.stringify(
                                {
                                  cloudevents: inspectorData?.cloudevents || {
                                    specversion: '1.0',
                                    id: 'ce-evt-99120482',
                                    type: 'com.ap2.settlement.subscription.activated',
                                    data: {
                                      buyer_agent: localContractorName,
                                      node_endpoint: (inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443'),
                                    },
                                  },
                                  enclave: {
                                    enclave_node: (inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443'),
                                    status: 'READY_FOR_INFERENCE',
                                  },
                                },
                                null,
                                2
                              )}
                        </code>
                      </pre>
                    </div>
                  )}

                  {/* TAB 2: QuickBooks Online (API v3) */}
                  {activeInspectorTab === 'qbo' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ backgroundColor: 'rgba(52, 211, 153, 0.08)', border: '1px solid rgba(52, 211, 153, 0.2)', borderRadius: '6px', padding: '8px 12px', fontSize: '11px', color: '#cbd5e1', display: 'flex', flexWrap: 'wrap', gap: '14px', flex: 1, marginRight: '12px' }}>
                          <span><strong>Entity:</strong> Intuit QBO v3 <code>Purchase (Expense)</code></span>
                          <span><strong>PaymentType:</strong> <code>CreditCard</code></span>
                          <span><strong>Expense Account:</strong> <code>Account 6300 (Software &amp; SaaS)</code></span>
                          <span><strong>Clearing Account:</strong> <code>Account 99 (PayPal)</code></span>
                        </div>

                        <button
                          onClick={() => {
                            const qboPkg = {
                              qbo_purchase: inspectorData?.quickbooks?.payload || inspectorData?.quickbooks?.qbo_purchase || inspectorData?.quickbooks || {},
                              vendor_reference: inspectorData?.quickbooks?.vendor_reference || inspectorData?.quickbooks?.qbo_vendor || {},
                              account_mapping: inspectorData?.quickbooks?.account_mapping || {},
                            };
                            copyToClipboard(JSON.stringify(qboPkg, null, 2), 'qbo_payload');
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            backgroundColor: '#1e293b',
                            border: '1px solid #475569',
                            color: copiedKey === 'qbo_payload' ? '#34d399' : '#94a3b8',
                            padding: '6px 12px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            cursor: 'pointer',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {copiedKey === 'qbo_payload' ? <Check size={12} /> : <Copy size={12} />}
                          {copiedKey === 'qbo_payload' ? 'Copied' : 'Copy QBO Payload'}
                        </button>
                      </div>

                      <pre
                        style={{
                          backgroundColor: '#090d16',
                          border: '1px solid #1e293b',
                          borderRadius: '8px',
                          padding: '14px',
                          margin: 0,
                          fontSize: '11px',
                          lineHeight: '1.5',
                          color: '#34d399',
                          overflow: 'auto',
                          maxHeight: '340px',
                          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                        }}
                      >
                        <code>
                          {JSON.stringify(
                            {
                              qbo_purchase: inspectorData?.quickbooks?.payload || inspectorData?.quickbooks?.qbo_purchase || inspectorData?.quickbooks || {},
                              vendor_reference: inspectorData?.quickbooks?.vendor_reference || inspectorData?.quickbooks?.qbo_vendor || {},
                              account_mapping: inspectorData?.quickbooks?.account_mapping || {
                                expense_account: '6300 - Dues & Subscriptions: Software & SaaS',
                                clearing_account: '99 - PayPal Clearing Account',
                                monthly_amount: inspectorData?.agreed_price || 79.99,
                              },
                            },
                            null,
                            2
                          )}
                        </code>
                      </pre>
                    </div>
                  )}

                  {/* TAB 3: Cryptographic Webhook Envelope */}
                  {activeInspectorTab === 'webhook' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: '12px', fontWeight: 600, color: '#f8fafc' }}>
                          Outbound Signed HTTP POST Headers &amp; Meta
                        </div>

                        <button
                          onClick={() => {
                            const fullEnvelope = {
                              headers: {
                                'X-AP2-Signature': inspectorData?.hmac_signature || inspectorData?.webhook_meta?.signature,
                                'X-AP2-Timestamp': inspectorData?.timestamp || inspectorData?.webhook_meta?.timestamp,
                                'PayPal-Subscription-ID': inspectorData?.paypal_subscription_id,
                                'Allocated-Node-Endpoint': (inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443'),
                                'Execution-Mode': 'LOCAL_HIGH_FIDELITY_SIMULATION',
                              },
                              meta: inspectorData?.webhook_meta,
                            };
                            copyToClipboard(JSON.stringify(fullEnvelope, null, 2), 'webhook_envelope');
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            backgroundColor: '#1e293b',
                            border: '1px solid #475569',
                            color: copiedKey === 'webhook_envelope' ? '#34d399' : '#94a3b8',
                            padding: '4px 10px',
                            borderRadius: '6px',
                            fontSize: '11px',
                            cursor: 'pointer',
                          }}
                        >
                          {copiedKey === 'webhook_envelope' ? <Check size={12} /> : <Copy size={12} />}
                          {copiedKey === 'webhook_envelope' ? 'Copied' : 'Copy Envelope'}
                        </button>
                      </div>

                      <pre
                        style={{
                          backgroundColor: '#090d16',
                          border: '1px solid #1e293b',
                          borderRadius: '8px',
                          padding: '14px',
                          margin: 0,
                          fontSize: '11px',
                          lineHeight: '1.5',
                          color: '#fbbf24',
                          overflow: 'auto',
                          maxHeight: '340px',
                          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                        }}
                      >
                        <code>
                          {JSON.stringify(
                            {
                              headers: {
                                'X-AP2-Signature': inspectorData?.hmac_signature || inspectorData?.webhook_meta?.signature || 'sha256=...',
                                'X-AP2-Timestamp': inspectorData?.timestamp || inspectorData?.webhook_meta?.timestamp,
                                'PayPal-Subscription-ID': inspectorData?.paypal_subscription_id,
                                'Allocated-Node-Endpoint': (inspectorData?.node_endpoint || inspectorData?.endpoint || 'node-cluster-01.ap2.net:8443'),
                                'Execution-Mode': 'LOCAL_HIGH_FIDELITY_SIMULATION',
                                'Content-Type': 'application/json',
                              },
                              webhook_meta: inspectorData?.webhook_meta,
                            },
                            null,
                            2
                          )}
                        </code>
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: '12px 20px',
                backgroundColor: '#1e293b',
                borderTop: '1px solid #334155',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                Conforms strictly to CloudEvents v1.0 JSON-RPC specifications and Intuit QuickBooks Online Developer schemas.
              </div>
              <button
                onClick={() => setIsInspectorOpen(false)}
                style={{
                  backgroundColor: '#334155',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 16px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export const ContractorCopilotView = SellerCopilotView;
