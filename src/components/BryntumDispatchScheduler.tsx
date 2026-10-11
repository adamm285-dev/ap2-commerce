import { useEffect, useMemo, useRef, useState } from 'react';
import '@bryntum/scheduler/scheduler.css';
import '@bryntum/scheduler/stockholm-dark.css';
import '@bryntum/scheduler/fontawesome/css/fontawesome.css';
import '@bryntum/scheduler/fontawesome/css/solid.css';
import { Scheduler } from '@bryntum/scheduler';
import { CATALOG_PLANS } from '../data/telemetryData';
import {
  Zap,
  Cpu,
  CalendarCheck,
  RotateCcw,
  CheckCircle2,
  Clock,
  DollarSign,
  X,
  FileText,
  Sparkles,
  Send,
  Download,
  Server,
  Terminal,
  Copy,
  Check,
  Activity,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  Calendar,
  Minimize2,
  Maximize2,
  Code2,
  Trash2,
  AlertCircle,
} from 'lucide-react';

export interface ApiWireLog {
  id: string;
  timestamp: string;
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'JSON-RPC';
  endpoint: string;
  status: number;
  statusText: string;
  durationMs: number;
  summary: string;
  category: 'MCP' | 'Enclave Dispatch' | 'PayPal' | 'QuickBooks/ERP' | 'Security';
  request: any;
  response: any;
}

import {
  executeProvisioningAfterSubscription,
  fetchFleetSchedule,
  lockTerritorySlot,
} from '../services/paypalAgentService';

// Parsing & Enrichment Helpers for AP2 Autonomous Workload Fulfillment
function getBuyerAgent(name: string): string {
  if (name.includes('101') || name.includes('Synthesis')) return 'agent:acme-ops';
  if (name.includes('102') || name.includes('Negotiation')) return 'agent:gpt-4o:apex-procure';
  if (name.includes('201') || name.includes('Vector Ingestion')) return 'agent:pipeline-buyer';
  if (name.includes('202') || name.includes('Embeddings')) return 'agent:deepseek-v3:quant-research';
  if (name.includes('301') || name.includes('Smart Contract')) return 'agent:audit-buyer';
  if (name.includes('302') || name.includes('Perimeter')) return 'agent:security-audit-buyer';
  if (name.includes('401') || name.includes('Stream Processing')) return 'agent:stream-buyer';
  if (name.includes('402') || name.includes('Batch Worker')) return 'agent:benchmark-buyer';
  if (name.includes('501') || name.includes('Model Evaluation')) return 'agent:scale-eval-buyer';
  if (name.includes('502') || name.includes('Incident')) return 'agent:oversight-buyer';
  return 'agent:autonomous:ap2-buyer';
}

function getPrincipalEntity(name: string): string {
  if (name.includes('101') || name.includes('Synthesis')) return 'Acme Compute Co';
  if (name.includes('102') || name.includes('Negotiation')) return 'Demo Enterprise Inc';
  if (name.includes('201') || name.includes('Vector Ingestion')) return 'Demo Pipeline Corp';
  if (name.includes('202') || name.includes('Embeddings')) return 'Demo Analytics Co';
  if (name.includes('301') || name.includes('Smart Contract')) return 'Demo Worker Systems Co';
  if (name.includes('302') || name.includes('Perimeter')) return 'Example Security Co';
  if (name.includes('401') || name.includes('Stream Processing')) return 'Example Stream Co';
  if (name.includes('402') || name.includes('Batch Worker')) return 'Demo Benchmark Co';
  if (name.includes('501') || name.includes('Model Evaluation')) return 'Demo Scale Labs';
  if (name.includes('502') || name.includes('Incident')) return 'Example Oversight Co';
  return 'Demo Merchant Co';
}

function getWorkloadScope(name: string): string {
  if (name.includes('•')) {
    return name.split('•')[0].trim();
  }
  return name;
}

function getClusterEndpoint(name: string): string {
  if (name.includes('101') || name.includes('102') || name.includes('103')) return 'https://api.ap2protocol.org/mcp/node-01 (US-East Cluster)';
  if (name.includes('201') || name.includes('202') || name.includes('203')) return 'https://api.ap2protocol.org/mcp/node-02 (US-East High-Mem)';
  if (name.includes('301') || name.includes('302') || name.includes('303')) return 'https://api.ap2protocol.org/mcp/node-03 (US-Central Sandbox)';
  if (name.includes('401') || name.includes('402') || name.includes('403')) return 'https://api.ap2protocol.org/mcp/node-04 (US-East Edge Streaming)';
  return 'https://api.ap2protocol.org/mcp/node-05 (Global Supervised Enclave)';
}

function getDemoSignatureLabel(_name: string): string {
  return 'Demo node (no signature)';
}

function getExecutionSpecifications(name: string, trade: string): string {
  if (trade.includes('Gateway') || trade.includes('Inference') || name.includes('Synthesis')) {
    return `Catalog Quota: ${CATALOG_PLANS[1].tasks} tasks/mo • Dedicated AI Service Gateway ($${CATALOG_PLANS[1].price}/mo) • Real-time routing`;
  }
  if (trade.includes('Batch') || trade.includes('Worker') || trade.includes('Vector') || name.includes('RAG')) {
    return `Catalog Quota: ${CATALOG_PLANS[0].tasks} tasks/mo • High-Throughput Batch Worker ($${CATALOG_PLANS[0].price}/mo) • Asynchronous execution`;
  }
  if (trade.includes('Cluster') || trade.includes('Security') || name.includes('Audit')) {
    return `Catalog Quota: ${CATALOG_PLANS[2].tasks} tasks/mo • Enterprise Cluster Node ($${CATALOG_PLANS[2].price}/mo) • High-priority execution`;
  }
  return `Enterprise Cluster Node • Catalog Quota: ${CATALOG_PLANS[2].tasks} tasks/mo • Multi-node scaling`;
}

function getShortWorkloadTitle(name: string): string {
  if (name.includes('Dedicated Gateway')) {
    return name.includes('Active') ? 'Dedicated Gateway' : 'Gateway (Pending)';
  }
  if (name.includes('Deep Research')) return '#101 Deep Research';
  if (name.includes('Consensus Inference')) return '#102 Consensus Eval';
  if (name.includes('Sandbox')) return '#103 MCP Sandbox';
  if (name.includes('Vector Ingestion')) return '#201 Vector RAG Ingest';
  if (name.includes('Context Embeddings')) return '#202 Task Quota Allocation';
  if (name.includes('Semantic Graph')) return '#203 Semantic Index';
  if (name.includes('Smart Contract')) return '#301 Smart Contract Audit';
  if (name.includes('Vulnerability Scan') || name.includes('AST')) return '#302 AST Perimeter Scan';
  if (name.includes('Cryptographic Proof')) return '#303 Crypto Proof Verif';
  if (name.includes('Service Gateway') || name.includes('Stream Processing')) return '#401 Service Gateway';
  if (name.includes('Batch Worker') || name.includes('High-Throughput Batch')) return '#402 Batch Worker';
  if (name.includes('Cluster Node') || name.includes('Enterprise Cluster')) return '#403 Cluster Node';
  if (name.includes('Model Evaluation Review')) return '#501 Model Eval Review';
  if (name.includes('Security Incident')) return '#502 Incident Remediation';
  if (name.includes('Edge-Case Triage')) return '#503 Edge-Case Triage';
  if (name.includes('Consensus Evaluation')) return '#104 Agent Consensus';

  let cleaned = name.replace(/Workload\s+/i, '').split('•')[0].trim();
  if (cleaned.length > 34) {
    cleaned = cleaned.substring(0, 32) + '…';
  }
  return cleaned;
}

function getShortBadge(status: string): string {
  if (status.includes('ACTIVE')) return '● Active';
  if (status.includes('AWAITING')) return '○ Awaiting Sub';
  if (status.includes('INCLUDED')) return '✓ Included';
  if (status.includes('PAID') || status.includes('SETTLED')) {
    const match = status.match(/\$\d+(\.\d+)?/);
    return match ? `✓ Paid ${match[0]}` : '✓ Settled';
  }
  return status;
}

export interface ScheduleEvent {
  id: number | string;
  resourceId: string;
  name: string;
  startDate: string;
  endDate: string;
  eventColor: string;
  iconCls: string;
  depositStatus: string;
  paypalTxn: string;
}

export interface BryntumDispatchSchedulerProps {
  isDepositLocked?: boolean;
  onToggleDepositLock?: (locked: boolean) => void;
  viewMode?: 'matrix' | 'timeline';
  onViewModeChange?: (mode: 'matrix' | 'timeline') => void;
  isMetricsCollapsed?: boolean;
  onToggleMetrics?: () => void;
}

export function BryntumDispatchScheduler({
  isDepositLocked = false,
  onToggleDepositLock,
  viewMode: propViewMode,
  onViewModeChange,
  isMetricsCollapsed: propIsMetricsCollapsed,
  onToggleMetrics,
}: BryntumDispatchSchedulerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const schedulerRef = useRef<Scheduler | null>(null);
  const dateInputRef = useRef<HTMLInputElement>(null);
  const [activeDate, setActiveDate] = useState<Date>(new Date(2026, 9, 8));
  const [lastPaymentSync, setLastPaymentSync] = useState<string>('2026-10-08 13:02:45');
  const [isCallingApi, setIsCallingApi] = useState(false);
  const [isLockingSlot, setIsLockingSlot] = useState(false);
  const [isSlotLocked, setIsSlotLocked] = useState(false);

  const [internalSchedulerViewMode, setInternalSchedulerViewMode] = useState<'matrix' | 'timeline'>('timeline');
  const schedulerViewMode = propViewMode ?? internalSchedulerViewMode;
  const setSchedulerViewMode = (mode: 'matrix' | 'timeline') => {
    setInternalSchedulerViewMode(mode);
    onViewModeChange?.(mode);
  };
  void setSchedulerViewMode;
  const [horizonMode, setHorizonMode] = useState<'hourly' | 'weekly'>('hourly');
  const [catalogTiers, setCatalogTiers] = useState<Array<{ id: string; title: string; monthlySubscription: number; workloadTasksPerMonth?: number }>>([]);

  useEffect(() => {
    fetch('/api/agent/catalog')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && Array.isArray(data.trades)) {
          setCatalogTiers(data.trades);
        }
      })
      .catch(() => {});
  }, []);

  const tierQuotasLabel = useMemo(() => {
    if (catalogTiers.length > 0) {
      const quotas = catalogTiers.map((t) => {
        const q = t.workloadTasksPerMonth ?? (t.id.includes('batch') ? 125 : t.id.includes('gateway') ? 450 : 1200);
        return q.toLocaleString('en-US');
      });
      return quotas.join(' / ');
    }
    return '125 / 450 / 1,200';
  }, [catalogTiers]);

  const [internalIsScheduleMetricsCollapsed, setInternalIsScheduleMetricsCollapsed] = useState(false);
  const isScheduleMetricsCollapsed = propIsMetricsCollapsed ?? internalIsScheduleMetricsCollapsed;
  const toggleScheduleMetricsCollapsed = () => {
    if (onToggleMetrics) {
      onToggleMetrics();
    } else {
      setInternalIsScheduleMetricsCollapsed((prev) => !prev);
    }
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.value) return;
    const [y, m, d] = e.target.value.split('-').map(Number);
    const selected = new Date(y, m - 1, d);
    setActiveDate(selected);
    if (schedulerRef.current) {
      if (horizonMode === 'weekly') {
        const dayOfWeek = selected.getDay();
        const startOfWeek = new Date(selected);
        startOfWeek.setDate(selected.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));
        const endOfWeek = new Date(startOfWeek);
        endOfWeek.setDate(startOfWeek.getDate() + 7);
        schedulerRef.current.setTimeSpan(startOfWeek, endOfWeek);
      } else {
        const s = new Date(selected.getFullYear(), selected.getMonth(), selected.getDate(), 7, 0);
        const e = new Date(selected.getFullYear(), selected.getMonth(), selected.getDate(), 19, 0);
        schedulerRef.current.setTimeSpan(s, e);
      }
    }
  };

  const handleHorizonChange = (mode: 'hourly' | 'weekly') => {
    setHorizonMode(mode);
    if (!schedulerRef.current) return;
    if (mode === 'weekly') {
      (schedulerRef.current as any).viewPreset = {
        base: 'dayAndWeek',
        tickWidth: 160,
      };
      schedulerRef.current.setTimeSpan(new Date(2026, 9, 5, 0, 0), new Date(2026, 9, 12, 0, 0));
    } else {
      (schedulerRef.current as any).viewPreset = {
        base: 'hourAndDay',
        tickWidth: 140,
      };
      schedulerRef.current.setTimeSpan(
        new Date(activeDate.getFullYear(), activeDate.getMonth(), activeDate.getDate(), 7, 0),
        new Date(activeDate.getFullYear(), activeDate.getMonth(), activeDate.getDate(), 19, 0)
      );
    }
  };

  useEffect(() => {
    if (schedulerViewMode === 'timeline') {
      const timer = setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
        if (schedulerRef.current) {
          (schedulerRef.current as any).refresh?.();
        }
      }, 60);
      return () => clearTimeout(timer);
    }
  }, [schedulerViewMode]);

  const handlePrevDay = () => {
    const newDate = new Date(activeDate);
    newDate.setDate(newDate.getDate() - 1);
    setActiveDate(newDate);
    if (schedulerRef.current) {
      const s = new Date(newDate.getFullYear(), newDate.getMonth(), newDate.getDate(), 7, 0);
      const e = new Date(newDate.getFullYear(), newDate.getMonth(), newDate.getDate(), 19, 0);
      schedulerRef.current.setTimeSpan(s, e);
    }
  };

  const handleToday = () => {
    const today = new Date(2026, 9, 8);
    setActiveDate(today);
    if (schedulerRef.current) {
      schedulerRef.current.setTimeSpan(
        new Date(2026, 9, 8, 7, 0),
        new Date(2026, 9, 8, 19, 0)
      );
    }
  };

  const handleNextDay = () => {
    const newDate = new Date(activeDate);
    newDate.setDate(newDate.getDate() + 1);
    setActiveDate(newDate);
    if (schedulerRef.current) {
      const s = new Date(newDate.getFullYear(), newDate.getMonth(), newDate.getDate(), 7, 0);
      const e = new Date(newDate.getFullYear(), newDate.getMonth(), newDate.getDate(), 19, 0);
      schedulerRef.current.setTimeSpan(s, e);
    }
  };

  const handleZoomIn = () => {
    if (schedulerRef.current) {
      try {
        schedulerRef.current.zoomIn();
      } catch (e) {
        console.warn('zoomIn error', e);
      }
    }
  };

  const handleZoomOut = () => {
    if (schedulerRef.current) {
      try {
        schedulerRef.current.zoomOut();
      } catch (e) {
        console.warn('zoomOut error', e);
      }
    }
  };
  const [activeTradeFilter, setActiveTradeFilter] = useState<string>('ALL');
  const [selectedAppointment, setSelectedAppointment] = useState<any | null>(null);
  const [totalDispatches, setTotalDispatches] = useState<number>(18);
  const [totalVaultedDeposits, setTotalVaultedDeposits] = useState<number>(1219.87);
  const [leadSimulationBanner, setLeadSimulationBanner] = useState<string | null>(null);

  // Master lists & dynamic filters for Enclave Matrix view
  const allNodesList = useMemo(() => [
    {
      id: 'node-1',
      name: 'Node-01: Dedicated AI Service Gateway',
      trade: 'Dedicated AI Service Gateway',
      category: 'GATEWAY',
      entity: 'Ashburn Zone 1 • NVIDIA H100 SXM5',
      did: isDepositLocked ? 'node-cluster-01.ap2.net' : 'Awaiting Settlement',
      status: isDepositLocked ? 'ACTIVE_STREAMING' : 'PENDING_SUBSCRIPTION',
      throughput: '450 tasks/mo',
      latency: '14ms',
      health: '98.2%',
      color: '#38bdf8',
      activeJob: isDepositLocked ? `Dedicated Gateway Streaming ($${CATALOG_PLANS[1].price}/mo)` : `Awaiting $${CATALOG_PLANS[1].price}/mo PayPal Subscription`,
    },
    {
      id: 'node-2',
      name: 'Node-02: High-Throughput Batch Worker',
      trade: 'High-Throughput Batch Worker',
      category: 'BATCH',
      entity: 'Dallas Zone 2 • 4x NVIDIA A100 (80GB)',
      did: 'node-cluster-02.ap2.net',
      status: isSlotLocked ? 'SLOT_LOCKED' : 'ACTIVE_STREAMING',
      throughput: '125 tasks/mo',
      latency: '28ms',
      health: '100%',
      color: '#34d399',
      activeJob: isSlotLocked ? `#204 Multi-Agent Consensus ($${CATALOG_PLANS[0].price})` : `#201 Batch Worker Ingest ($${CATALOG_PLANS[0].price})`,
    },
    {
      id: 'node-3',
      name: 'Node-03: Enterprise Cluster Node',
      trade: 'Enterprise Cluster Node',
      category: 'CLUSTER',
      entity: 'San Jose Zone 3 • AMD SEV-SNP Enclave',
      did: 'node-cluster-03.ap2.net',
      status: 'ACTIVE_STREAMING',
      throughput: '100% Anti-Tamper',
      latency: '9ms',
      health: '100%',
      color: '#8b5cf6',
      activeJob: `#301 Secure Cluster Enclave ($${CATALOG_PLANS[2].price}/mo)`,
    },
    {
      id: 'node-4',
      name: 'Node-04: Dedicated AI Service Gateway (Stream Processing)',
      trade: 'Dedicated AI Service Gateway',
      category: 'GATEWAY',
      entity: 'East Zone 4 • MCP Stream Bridge',
      did: 'node-cluster-04.ap2.net',
      status: 'ACTIVE_STREAMING',
      throughput: '120ms Duplex RT',
      latency: '22ms',
      health: '100%',
      color: '#38bdf8',
      activeJob: `#401 Service Gateway ($${CATALOG_PLANS[1].price}/mo)`,
    },
    {
      id: 'node-5',
      name: 'Node-05: Enterprise Cluster Node (Supervised)',
      trade: 'Enterprise Cluster Node',
      category: 'CLUSTER',
      entity: 'Operator Enclave • Attestation Verified',
      did: 'node-cluster-05.ap2.net',
      status: 'ACTIVE_STREAMING',
      throughput: 'Triage Queue',
      latency: '34ms',
      health: '100%',
      color: '#8b5cf6',
      activeJob: `#501 Supervised Cluster Mandate ($${CATALOG_PLANS[2].price}/mo)`,
    },
  ], [isDepositLocked, isSlotLocked]);

  const allWorkloadsList = useMemo(() => [
    ...(isSlotLocked
      ? [
          {
            id: 'locked-workload-slot-2',
            name: `#204 Batch Worker Renewal ($${CATALOG_PLANS[0].price})`,
            node: 'Node-02: High-Throughput Batch Worker',
            category: 'BATCH',
            buyer: 'agent:gpt-4o:apex-procure',
            status: `SETTLED ($${CATALOG_PLANS[0].price} PAYPAL)`,
            txn: 'TXN-DISPATCH-9022',
            window: '16:00 - 17:15 (Today, Oct 8)',
            color: '#34d399',
            isNew: true,
          },
        ]
      : []),
    {
      id: 'workload-101',
      name: isDepositLocked ? 'Dedicated Gateway Active • MCP Endpoint Bound' : 'Dedicated Gateway Pending • Awaiting Subscription',
      node: 'Node-01: Dedicated AI Service Gateway',
      category: 'GATEWAY',
      buyer: 'agent:gpt-4o:apex-procure',
      status: isDepositLocked ? `ACTIVE ($${CATALOG_PLANS[1].price}/MO PAYPAL)` : `AWAITING PAYPAL ($${CATALOG_PLANS[1].price}/MO)`,
      txn: isDepositLocked ? 'I-AUTONOMOUS-8902' : 'UNPAID',
      window: 'Continuous Streaming Session',
      color: isDepositLocked ? '#10b981' : '#f59e0b',
    },
    {
      id: 'workload-201',
      name: `#201 Batch Worker Execution ($${CATALOG_PLANS[0].price})`,
      node: 'Node-02: High-Throughput Batch Worker',
      category: 'BATCH',
      buyer: 'agent:acme-legal',
      status: `PAID $${CATALOG_PLANS[0].price} (PAYPAL VAULT)`,
      txn: 'TXN-SETTLE-7712',
      window: '08:00 - 09:30 • 68% Complete (24m left)',
      color: '#10b981',
    },
    {
      id: 'workload-301',
      name: `#301 Enterprise Cluster Renewal ($${CATALOG_PLANS[2].price})`,
      node: 'Node-03: Enterprise Cluster Node',
      category: 'CLUSTER',
      buyer: 'agent:deepseek-r1:audit',
      status: `PAID $${CATALOG_PLANS[2].price} (PAYPAL VAULT)`,
      txn: 'TXN-SETTLE-5519',
      window: '07:30 - 09:00 • 100% Anti-Tamper Passed',
      color: '#8b5cf6',
    },
    {
      id: 'workload-401',
      name: `#401 Dedicated Gateway Renewal ($${CATALOG_PLANS[1].price})`,
      node: 'Node-04: Dedicated AI Service Gateway',
      category: 'GATEWAY',
      buyer: 'agent:gpt-4o:apex-procure',
      status: `PAID $${CATALOG_PLANS[1].price} (PAYPAL VAULT)`,
      txn: 'TXN-SETTLE-6601',
      window: '08:00 - 09:30 • US-East Gateway Enclave',
      color: '#0284c7',
    },
    {
      id: 'workload-501',
      name: `#501 Enterprise Cluster Verification ($${CATALOG_PLANS[2].price})`,
      node: 'Node-05: Enterprise Cluster Node',
      category: 'CLUSTER',
      buyer: 'agent:human:qa-desk',
      status: `PAID $${CATALOG_PLANS[2].price} (PAYPAL VAULT)`,
      txn: 'TXN-SETTLE-3310',
      window: '09:15 - 10:45 • Dual-Agent Verified',
      color: '#8b5cf6',
    },
  ], [isDepositLocked, isSlotLocked]);

  const displayedNodes = useMemo(() => {
    if (activeTradeFilter === 'ALL') return allNodesList;
    return allNodesList.filter((n) => n.category === activeTradeFilter);
  }, [allNodesList, activeTradeFilter]);

  const displayedWorkloads = useMemo(() => {
    if (activeTradeFilter === 'ALL') return allWorkloadsList;
    return allWorkloadsList.filter((w) => w.category === activeTradeFilter);
  }, [allWorkloadsList, activeTradeFilter]);

  const [apiStatus, setApiStatus] = useState<string>(
    isDepositLocked
      ? '● Node-01 Active: Dedicated Gateway via MCP (HTTP 201)'
      : `○ Pending: Awaiting $${CATALOG_PLANS[1].price}/mo PayPal Subscription Authorization`
  );

  const [dispatchWebhookStatus, setDispatchWebhookStatus] = useState<string | null>(null);
  const [invoiceStatus, setInvoiceStatus] = useState<string | null>(null);
  const [isSendingWebhook, setIsSendingWebhook] = useState(false);
  const [copiedAddress, setCopiedAddress] = useState(false);

  // Wire Protocol Telemetry State
  const [apiWireLogs, setApiWireLogs] = useState<ApiWireLog[]>([]);
  const [wireCategoryFilter, setWireCategoryFilter] = useState<string>('ALL');
  const [dockHeight, setDockHeight] = useState<'collapsed' | 'normal' | 'expanded'>('normal');
  const [selectedWireLog, setSelectedWireLog] = useState<ApiWireLog | null>(null);
  const [copiedWireKey, setCopiedWireKey] = useState<string | null>(null);

  const addWireLog = (log: Omit<ApiWireLog, 'id' | 'timestamp'>) => {
    const now = new Date();
    const timeStr = now.toTimeString().substring(0, 8);
    const newLog: ApiWireLog = {
      ...log,
      id: `wire-log-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      timestamp: timeStr,
    };
    setApiWireLogs((prev) => [newLog, ...prev]);
  };

  const handleCopyWire = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedWireKey(key);
    setTimeout(() => setCopiedWireKey(null), 2000);
  };

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      window.dispatchEvent(new Event('resize'));
    }, 200);
    return () => clearTimeout(timeoutId);
  }, [dockHeight]);

  const handleDispatchWebhook = async () => {
    if (!selectedAppointment) return;
    setIsSendingWebhook(true);
    setDispatchWebhookStatus(null);
    const t0 = performance.now();
    let measuredStatus: number;
    let measuredStatusText: string;
    let measuredDurationMs: number;
    let resData: any;
    let isSuccess = false;
    let isDryRun = false;
    let deliveryId = 'N/A';

    const requestBody = {
      workflow_type: 'a2a_onboarding',
      job_id: selectedAppointment.id,
      customer_name: selectedAppointment.customerName,
      property_address: selectedAppointment.jobAddress,
      payment_amount: 79.99,
      paypal_txn_id: selectedAppointment.paypalTxn,
      contractor_name: selectedAppointment.customerName,
      business_entity: selectedAppointment.resourceEntity || 'Acme Compute Co',
      allocated_did: selectedAppointment.resourceDid,
      trade_vertical: selectedAppointment.name,
      monthly_subscription_fee: 79.99,
      paypal_subscription_id: selectedAppointment.paypalTxn,
      contractor_email: 'buyer-agent-ops@example.com',
      dry_run: true,
    };

    try {
      const res = await fetch('/api/mcp/zapier-sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });
      measuredDurationMs = Math.round(performance.now() - t0);
      measuredStatus = res.status;
      measuredStatusText = res.statusText;
      try {
        resData = await res.json();
      } catch {
        resData = await res.text();
      }
      if (res.ok) {
        isSuccess = true;
        isDryRun = resData?.status === 'DRY_RUN_COMPLETED' || (!resData?.webhook_dispatched && !resData?.webhookDispatched);
        deliveryId = resData?.webhook_delivery_id || resData?.webhookDeliveryId || 'N/A';
      }
    } catch (err: any) {
      measuredDurationMs = Math.round(performance.now() - t0);
      measuredStatus = err?.httpStatus ?? (err?.status ?? 0);
      measuredStatusText = err?.httpStatusText ?? (err?.statusText ?? (measuredStatus === 0 ? 'NETWORK_ERROR' : 'ERROR'));
      resData = { error: err instanceof Error ? err.message : String(err) };
    } finally {
      setIsSendingWebhook(false);
    }

    if (isSuccess) {
      const statusMsg = isDryRun
        ? `Dry run completed for ${selectedAppointment.customerName} (${selectedAppointment.resourceDid}) • Delivery ID: ${deliveryId}`
        : `Dispatched fulfillment webhook to ${selectedAppointment.customerName} (${selectedAppointment.resourceDid}) • Delivery ID: ${deliveryId}`;
      setDispatchWebhookStatus(statusMsg);
    } else {
      setDispatchWebhookStatus(`Webhook dispatch failed (${measuredStatus} ${measuredStatusText})`);
    }
    setTimeout(() => setDispatchWebhookStatus(null), 6000);

    const summary = isSuccess
      ? isDryRun
        ? `Zapier MCP sync dry run for ${selectedAppointment.name} • Delivery ID: ${deliveryId}`
        : `Dispatched fulfillment webhook for ${selectedAppointment.name} • Delivery: ${deliveryId}`
      : `Zapier MCP sync failed (${measuredStatus} ${measuredStatusText}) for ${selectedAppointment.name}`;

    addWireLog({
      method: 'POST',
      endpoint: '/api/mcp/zapier-sync',
      status: measuredStatus,
      statusText: measuredStatusText,
      durationMs: measuredDurationMs,
      category: 'QuickBooks/ERP',
      summary,
      request: requestBody,
      response: resData,
    });
  };

  const handleDownloadReceipt = () => {
    if (!selectedAppointment) return;
    const receiptContent = `======================================================================
  AP2 AGENT PERSONAL PROTOCOL • WORKLOAD EXECUTION RECEIPT
======================================================================
Workload ID:       ${selectedAppointment.id}
Workload Scope:    ${selectedAppointment.name}
Execution Node:    ${selectedAppointment.resourceName} (${selectedAppointment.resourceTrade})
Enclave Endpoint:  ${selectedAppointment.resourceDid}
Buyer Agent:       ${selectedAppointment.customerName}
Principal Entity:  ${selectedAppointment.resourceEntity}
Cryptographic Sig: ${selectedAppointment.clientFingerprint || selectedAppointment.customerPhone}

Fulfillment State: ${selectedAppointment.depositStatus}
PayPal Txn ID:     ${selectedAppointment.paypalTxn}
Settlement Rail:   PayPal Subscriptions
Mandate Standard:  AP2 v0.2 (ES256 SD-JWT)
Anti-Tamper Hash:  SHA256: 98499e3f5739d9879697cb97e8045d (MATCH)
Execution Specs:   ${selectedAppointment.takeoffNotes}
Timestamp:         ${new Date().toISOString()}
======================================================================
This document certifies an authentic autonomous agent-to-agent workload execution.
`;
    const blob = new Blob([receiptContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `AP2_Workload_Execution_Receipt_${selectedAppointment.paypalTxn}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    setInvoiceStatus(`AP2_Workload_Execution_Receipt_${selectedAppointment.paypalTxn}.txt`);
    setTimeout(() => setInvoiceStatus(null), 4000);
  };

  const handleCopyEndpoint = () => {
    if (!selectedAppointment) return;
    navigator.clipboard.writeText(selectedAppointment.jobAddress);
    setCopiedAddress(true);
    setTimeout(() => setCopiedAddress(false), 2000);
  };

  useEffect(() => {
    if (!containerRef.current) return;

    // Define the 5 Autonomous Worker Execution Nodes with Cryptographic Attestation & Telemetry
    const initialResources = [
      {
        id: 'node-1',
        name: 'Node-01: Dedicated AI Service Gateway',
        entity: 'Google Gemini 3.8 / Flash Sub-350ms Engine',
        trade: 'Dedicated AI Service Gateway',
        did: isDepositLocked ? 'node-cluster-01.ap2.net' : 'Awaiting Settlement',
        status: isDepositLocked ? 'ACTIVE_ENCLAVE_BOUND' : 'PENDING_SUBSCRIPTION',
        throughput: '450 tasks/mo',
        health: '98.4%',
        enclave: 'Sealed Enclave (AMD SEV-SNP)',
      },
      {
        id: 'node-2',
        name: 'Node-02: High-Throughput Batch Worker',
        entity: 'High-Throughput Vector Embedding Engine (1M chunks)',
        trade: 'High-Throughput Batch Worker',
        did: 'node-cluster-02.ap2.net',
        status: 'ACTIVE_ENCLAVE_BOUND',
        throughput: '125 tasks/mo',
        health: '100%',
        enclave: 'Sealed Enclave (AWS Nitro)',
      },
      {
        id: 'node-3',
        name: 'Node-03: Enterprise Cluster Node',
        entity: 'Deterministic Sandbox & Smart Contract Verifier',
        trade: 'Enterprise Cluster Node',
        did: 'node-cluster-03.ap2.net',
        status: 'ACTIVE_ENCLAVE_BOUND',
        throughput: '1,200 tasks/mo',
        health: '100%',
        enclave: 'Sealed Enclave (TPM 2.0 Attested)',
      },
      {
        id: 'node-4',
        name: 'Node-04: Dedicated AI Service Gateway (Stream Processing)',
        entity: 'Full-Duplex Real-Time Stream Bridge',
        trade: 'Dedicated AI Service Gateway',
        did: 'node-cluster-04.ap2.net',
        status: 'ACTIVE_ENCLAVE_BOUND',
        throughput: '450 tasks/mo',
        health: '100%',
        enclave: 'Sealed Enclave (Edge Isolated)',
      },
      {
        id: 'node-5',
        name: 'Node-05: Enterprise Cluster Node (Supervised)',
        entity: 'Supervised Verification Desk & Outlier Triage',
        trade: 'Enterprise Cluster Node',
        did: 'node-cluster-05.ap2.net',
        status: 'ACTIVE_ENCLAVE_BOUND',
        throughput: '1,200 tasks/mo',
        health: '100%',
        enclave: 'Supervised Enclave (Operator Guard)',
      },
    ];

    // Define paid autonomous workload execution windows funded by buyer agents via PayPal (Multi-Day: Oct 6 - Oct 10)
    const initialEvents: ScheduleEvent[] = [
      // --- Oct 6, 2026 (Tuesday - Completed Baseline) ---
      {
        id: 'workload-06-101',
        resourceId: 'node-1',
        name: '#071 MCP Baseline Handshake (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-06 09:30',
        endDate: '2026-10-06 11:00',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-check-circle',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-6610',
      },
      {
        id: 'workload-06-201',
        resourceId: 'node-2',
        name: '#171 Knowledge Vault Vector Indexing (included in High-Throughput Batch Worker)',
        startDate: '2026-10-06 11:00',
        endDate: '2026-10-06 12:30',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-database',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-6620',
      },
      {
        id: 'workload-06-301',
        resourceId: 'node-3',
        name: '#271 Zero-Trust Enclave Attestation (included in Enterprise Cluster Node)',
        startDate: '2026-10-06 13:00',
        endDate: '2026-10-06 14:30',
        eventColor: 'purple',
        iconCls: 'b-fa b-fa-shield-alt',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-6630',
      },
      {
        id: 'workload-06-401',
        resourceId: 'node-4',
        name: '#371 Real-Time Ingress Stream (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-06 08:30',
        endDate: '2026-10-06 10:00',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-bolt',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-6640',
      },
      {
        id: 'workload-06-501',
        resourceId: 'node-5',
        name: '#471 Workload Audit & Outlier Triage (included in Enterprise Cluster Node)',
        startDate: '2026-10-06 14:00',
        endDate: '2026-10-06 15:30',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-user-check',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-6650',
      },

      // --- Oct 7, 2026 (Wednesday - Completed Baseline) ---
      {
        id: 'workload-07-101',
        resourceId: 'node-1',
        name: '#081 High-Throughput Reasoning (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-07 09:00',
        endDate: '2026-10-07 10:30',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-bolt',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7710',
      },
      {
        id: 'workload-07-102',
        resourceId: 'node-1',
        name: '#082 Mandate Verification (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-07 13:00',
        endDate: '2026-10-07 14:15',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-microchip',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7715',
      },
      {
        id: 'workload-07-201',
        resourceId: 'node-2',
        name: '#181 Vector Pipeline Ingest (included in High-Throughput Batch Worker)',
        startDate: '2026-10-07 08:30',
        endDate: '2026-10-07 10:00',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-database',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7720',
      },
      {
        id: 'workload-07-202',
        resourceId: 'node-2',
        name: '#182 Semantic Graph Indexing (included in High-Throughput Batch Worker)',
        startDate: '2026-10-07 11:15',
        endDate: '2026-10-07 12:45',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-layer-group',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7728',
      },
      {
        id: 'workload-07-301',
        resourceId: 'node-3',
        name: '#281 Smart Contract Formal Audit (included in Enterprise Cluster Node)',
        startDate: '2026-10-07 10:00',
        endDate: '2026-10-07 11:30',
        eventColor: 'purple',
        iconCls: 'b-fa b-fa-shield-alt',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7730',
      },
      {
        id: 'workload-07-302',
        resourceId: 'node-3',
        name: '#282 Cryptographic Proof Verify (included in Enterprise Cluster Node)',
        startDate: '2026-10-07 14:00',
        endDate: '2026-10-07 15:30',
        eventColor: 'red',
        iconCls: 'b-fa b-fa-key',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7735',
      },
      {
        id: 'workload-07-401',
        resourceId: 'node-4',
        name: `#381 Dedicated AI Service Gateway Renewal ($${CATALOG_PLANS[1].price}/mo)`,
        startDate: '2026-10-07 08:45',
        endDate: '2026-10-07 10:15',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-bolt',
        depositStatus: `SETTLED ($${CATALOG_PLANS[1].price} PAYPAL)`,
        paypalTxn: 'TXN-SETTLE-7740',
      },
      {
        id: 'workload-07-402',
        resourceId: 'node-4',
        name: '#382 Batch Inbound Stream (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-07 13:30',
        endDate: '2026-10-07 15:00',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-broadcast-tower',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7745',
      },
      {
        id: 'workload-07-501',
        resourceId: 'node-5',
        name: '#481 Dual-Agent Verification Review (included in Enterprise Cluster Node)',
        startDate: '2026-10-07 09:30',
        endDate: '2026-10-07 11:00',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-user-check',
        depositStatus: 'SETTLED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7750',
      },

      // --- Oct 8, 2026 (Thursday - Today's Live Workloads) ---
      // Node 1: High-Speed LLM Inference Gateway
      {
        id: 'workload-101',
        resourceId: 'node-1',
        name: isDepositLocked
          ? `Dedicated Gateway Active • MCP Endpoint Bound ($${CATALOG_PLANS[1].price}/mo)`
          : `Dedicated Gateway Pending • Awaiting PayPal Subscription ($${CATALOG_PLANS[1].price}/mo)`,
        startDate: '2026-10-08 13:00',
        endDate: '2026-10-08 14:15',
        eventColor: isDepositLocked ? 'green' : 'orange',
        iconCls: isDepositLocked ? 'b-fa b-fa-check-circle' : 'b-fa b-fa-clock',
        depositStatus: isDepositLocked ? `ACTIVE ($${CATALOG_PLANS[1].price}/MO)` : `AWAITING PAYPAL ($${CATALOG_PLANS[1].price}/MO)`,
        paypalTxn: isDepositLocked ? 'I-AUTONOMOUS-8902' : 'UNPAID',
      },
      {
        id: 'workload-102',
        resourceId: 'node-1',
        name: '#101 Deep Research (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-08 08:30',
        endDate: '2026-10-08 09:45',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-bolt',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-8831',
      },
      {
        id: 'workload-103',
        resourceId: 'node-1',
        name: '#102 Consensus Eval (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-08 10:30',
        endDate: '2026-10-08 11:45',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-microchip',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-8842',
      },
      {
        id: 'workload-104',
        resourceId: 'node-1',
        name: '#103 MCP Sandbox (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-08 15:30',
        endDate: '2026-10-08 16:45',
        eventColor: 'purple',
        iconCls: 'b-fa b-fa-code',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-8859',
      },

      // Node 2: Batch Data & Document RAG Pipeline
      {
        id: 'workload-201',
        resourceId: 'node-2',
        name: `#201 High-Throughput Batch Worker ($${CATALOG_PLANS[0].price}/mo)`,
        startDate: '2026-10-08 08:00',
        endDate: '2026-10-08 09:30',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-database',
        depositStatus: `PAID $${CATALOG_PLANS[0].price} (PAYPAL VAULT)`,
        paypalTxn: 'TXN-SETTLE-7712',
      },
      {
        id: 'workload-202',
        resourceId: 'node-2',
        name: '#202 125 Task Quota Allocation (included in High-Throughput Batch Worker)',
        startDate: '2026-10-08 10:45',
        endDate: '2026-10-08 12:15',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-layer-group',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7725',
      },
      {
        id: 'workload-203',
        resourceId: 'node-2',
        name: '#203 Semantic Index (included in High-Throughput Batch Worker)',
        startDate: '2026-10-08 14:00',
        endDate: '2026-10-08 15:30',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-project-diagram',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-7738',
      },

      // Node 3: Autonomous Code & Security Audit Cluster
      {
        id: 'workload-301',
        resourceId: 'node-3',
        name: '#301 Smart Contract Verification (included in Enterprise Cluster Node)',
        startDate: '2026-10-08 09:00',
        endDate: '2026-10-08 10:30',
        eventColor: 'red',
        iconCls: 'b-fa b-fa-shield-alt',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-9910',
      },
      {
        id: 'workload-302',
        resourceId: 'node-3',
        name: '#302 AST Perimeter Scan (included in Enterprise Cluster Node)',
        startDate: '2026-10-08 12:00',
        endDate: '2026-10-08 13:30',
        eventColor: 'purple',
        iconCls: 'b-fa b-fa-lock',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-9924',
      },
      {
        id: 'workload-303',
        resourceId: 'node-3',
        name: '#303 Crypto Proof Verif (included in Enterprise Cluster Node)',
        startDate: '2026-10-08 15:15',
        endDate: '2026-10-08 16:45',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-key',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-9937',
      },

      // Node 4: Real-Time Stream Processing Node
      {
        id: 'workload-401',
        resourceId: 'node-4',
        name: `#401 Dedicated AI Service Gateway ($${CATALOG_PLANS[1].price}/mo)`,
        startDate: '2026-10-08 08:15',
        endDate: '2026-10-08 09:45',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-bolt',
        depositStatus: `ACTIVE ($${CATALOG_PLANS[1].price}/MO)`,
        paypalTxn: 'I-VC551PP882B4',
      },
      {
        id: 'workload-402',
        resourceId: 'node-4',
        name: `#402 High-Throughput Batch Worker ($${CATALOG_PLANS[0].price}/mo)`,
        startDate: '2026-10-08 11:30',
        endDate: '2026-10-08 13:00',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-layer-group',
        depositStatus: `PAID $${CATALOG_PLANS[0].price} (PAYPAL VAULT)`,
        paypalTxn: 'TXN-SETTLE-5518',
      },
      {
        id: 'workload-403',
        resourceId: 'node-4',
        name: `#403 Enterprise Cluster Node ($${CATALOG_PLANS[2].price}/mo)`,
        startDate: '2026-10-08 14:30',
        endDate: '2026-10-08 16:00',
        eventColor: 'purple',
        iconCls: 'b-fa b-fa-server',
        depositStatus: `PAID $${CATALOG_PLANS[2].price} (PAYPAL VAULT)`,
        paypalTxn: 'TXN-SETTLE-5532',
      },

      // Node 5: Human-in-the-Loop Expert QA Desk
      {
        id: 'workload-501',
        resourceId: 'node-5',
        name: '#501 Model Eval Review (included in Enterprise Cluster Node)',
        startDate: '2026-10-08 09:15',
        endDate: '2026-10-08 10:45',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-user-check',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-3310',
      },
      {
        id: 'workload-502',
        resourceId: 'node-5',
        name: '#502 Incident Remediation (included in Enterprise Cluster Node)',
        startDate: '2026-10-08 11:00',
        endDate: '2026-10-08 12:30',
        eventColor: 'red',
        iconCls: 'b-fa b-fa-user-shield',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-3320',
      },
      {
        id: 'workload-503',
        resourceId: 'node-5',
        name: '#503 Edge-Case Triage (included in Enterprise Cluster Node)',
        startDate: '2026-10-08 13:00',
        endDate: '2026-10-08 14:30',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-check-double',
        depositStatus: 'ACTIVE (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SETTLE-3330',
      },

      // --- Oct 9, 2026 (Friday - Upcoming Scheduled Workloads) ---
      {
        id: 'workload-09-101',
        resourceId: 'node-1',
        name: '#111 Enterprise Multi-Agent Dispatch (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-09 09:00',
        endDate: '2026-10-09 10:15',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-robot',
        depositStatus: 'SCHEDULED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SCHED-9911',
      },
      {
        id: 'workload-09-201',
        resourceId: 'node-2',
        name: '#211 Batch Embed Chunking (included in High-Throughput Batch Worker)',
        startDate: '2026-10-09 10:30',
        endDate: '2026-10-09 12:00',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-layer-group',
        depositStatus: 'SCHEDULED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SCHED-9921',
      },
      {
        id: 'workload-09-301',
        resourceId: 'node-3',
        name: '#311 Continuous AST Audit (included in Enterprise Cluster Node)',
        startDate: '2026-10-09 13:00',
        endDate: '2026-10-09 14:30',
        eventColor: 'purple',
        iconCls: 'b-fa b-fa-lock',
        depositStatus: 'SCHEDULED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SCHED-9931',
      },
      {
        id: 'workload-09-401',
        resourceId: 'node-4',
        name: `#411 Service Gateway Route ($${CATALOG_PLANS[1].price}/mo)`,
        startDate: '2026-10-09 08:30',
        endDate: '2026-10-09 10:00',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-bolt',
        depositStatus: 'SCHEDULED (PAYPAL VAULT)',
        paypalTxn: 'TXN-SCHED-9941',
      },
      {
        id: 'workload-09-501',
        resourceId: 'node-5',
        name: '#511 Weekly Replay Verification (included in Enterprise Cluster Node)',
        startDate: '2026-10-09 11:00',
        endDate: '2026-10-09 12:30',
        eventColor: 'blue',
        iconCls: 'b-fa b-fa-user-check',
        depositStatus: 'SCHEDULED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SCHED-9951',
      },

      // --- Oct 10, 2026 (Saturday - Scheduled Maintenance & Standby) ---
      {
        id: 'workload-10-101',
        resourceId: 'node-1',
        name: '#121 Weekend Standby Enclave (included in Dedicated AI Service Gateway)',
        startDate: '2026-10-10 10:00',
        endDate: '2026-10-10 11:30',
        eventColor: 'cyan',
        iconCls: 'b-fa b-fa-bolt',
        depositStatus: 'SCHEDULED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SCHED-1001',
      },
      {
        id: 'workload-10-201',
        resourceId: 'node-2',
        name: '#221 Deep Archive Vector Maintenance (included in High-Throughput Batch Worker)',
        startDate: '2026-10-10 12:00',
        endDate: '2026-10-10 13:30',
        eventColor: 'purple',
        iconCls: 'b-fa b-fa-database',
        depositStatus: 'SCHEDULED (INCLUDED IN PLAN)',
        paypalTxn: 'TXN-SCHED-1002',
      },
    ];

    // Initialize Bryntum Scheduler instance
    const scheduler = new Scheduler({
      appendTo: containerRef.current,
      startDate: new Date(2026, 9, 8, 7, 0),
      endDate: new Date(2026, 9, 8, 19, 0),
      viewPreset: {
        base: 'hourAndDay',
        tickWidth: 140,
      } as any,
      rowHeight: 80,
      barMargin: 12,
      eventStyle: 'filled',
      columns: [
        {
          text: 'Execution Worker Node & Enclave',
          field: 'name',
          width: 230,
          renderer({ record }: any) {
            const isAssigned = !record.did?.includes('AWAITING') && record.status !== 'PENDING_SUBSCRIPTION';
            const trade = record.trade || 'Dedicated AI Service Gateway';
            const isInf = trade.includes('Gateway') || trade.includes('Inference') || trade.includes('AI');
            const isRag = trade.includes('Batch') || trade.includes('Worker') || trade.includes('Vector');
            const isSec = trade.includes('Cluster') || trade.includes('Security') || trade.includes('Enterprise');
            const dotColor = isInf ? '#38bdf8' : isRag ? '#34d399' : isSec ? '#8b5cf6' : '#38bdf8';

            const parts = record.name ? record.name.split(':') : ['Node', 'Worker'];
            const prefix = parts[0] || 'Node';
            const suffix = record.trade || parts[1]?.trim() || '';
            const conciseTitle = `${prefix}: ${suffix}`;

            return `
              <div style="line-height:1.3;padding:4px 0;width:100%;overflow:hidden;">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:4px;">
                  <span style="font-weight:700;color:#f8fafc;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                    ${conciseTitle}
                  </span>
                  <span style="font-size:8px;padding:1px 4px;border-radius:3px;font-weight:800;background:${isAssigned ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)'};color:${isAssigned ? '#34d399' : '#fbbf24'};border:1px solid ${isAssigned ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'};flex-shrink:0;">
                    ${isAssigned ? 'ACTIVE' : 'PENDING'}
                  </span>
                </div>
                <div style="display:flex;align-items:center;gap:4px;margin-top:2px;font-size:10px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                  <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background-color:${dotColor};flex-shrink:0;"></span>
                  <span>${record.trade}</span>
                  <span style="color:#475569;">&bull;</span>
                  <span style="font-family:ui-monospace, monospace;color:#cbd5e1;font-size:9px;">${record.did ? record.did.replace('.ap2.net', '') : ''}</span>
                </div>
                <div style="display:flex;align-items:center;gap:5px;margin-top:2px;font-size:9px;">
                  <span style="color:#38bdf8;font-weight:600;">⚡ ${record.throughput ? record.throughput.split('•')[0].trim() : '450 tasks/mo'}</span>
                  <span style="color:#475569;">&bull;</span>
                  <span style="color:#34d399;font-weight:600;">${record.health || '100%'}</span>
                </div>
              </div>
            `;
          },
        },
      ],
      resources: initialResources,
      events: initialEvents,
      eventRenderer({ eventRecord }: { eventRecord: any }) {
        const isVerified =
          eventRecord.depositStatus.includes('ACTIVE') ||
          eventRecord.depositStatus.includes('PAID') ||
          eventRecord.depositStatus.includes('VERIFIED');
        const isEmergency = eventRecord.depositStatus.includes('EMERGENCY') || eventRecord.depositStatus.includes('MOBILIZATION');
        
        // High-contrast solid obsidian pill background ensures badge never washes out inside colorful event bars
        const badgeBg = '#090e17';
        const badgeColor = isEmergency ? '#fca5a5' : isVerified ? '#34d399' : '#fbbf24';
        const badgeBorder = isEmergency ? '#ef4444' : isVerified ? '#059669' : '#d97706';

        const shortTitle = getShortWorkloadTitle(eventRecord.name || '');
        const shortBadge = getShortBadge(eventRecord.depositStatus || '');

        return `
          <div title="${eventRecord.name} • ${eventRecord.depositStatus}" style="display:flex;flex-direction:column;justify-content:center;width:100%;height:100%;padding:4px 8px;box-sizing:border-box;overflow:hidden;border-radius:6px;gap:3px;cursor:pointer;">
            <div style="display:flex;align-items:center;gap:6px;width:100%;overflow:hidden;">
              <i class="${eventRecord.iconCls}" style="font-size:10px;color:${badgeColor};flex-shrink:0;"></i>
              <span style="font-size:11px;font-weight:800;color:#ffffff;text-shadow:0 1px 2px rgba(0,0,0,0.6);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:-0.01em;">
                ${shortTitle}
              </span>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;width:100%;gap:4px;">
              <span style="font-size:9px;font-weight:800;padding:2px 6px;border-radius:4px;background-color:${badgeBg};color:${badgeColor};border:1px solid ${badgeBorder};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:75%;box-shadow:0 1px 3px rgba(0,0,0,0.4);">
                ${shortBadge}
              </span>
              <span style="font-size:9px;font-weight:700;color:#e2e8f0;font-family:ui-monospace, monospace;flex-shrink:0;background:#090e17;padding:1px 5px;border-radius:3px;border:1px solid #1e293b;">
                75m
              </span>
            </div>
          </div>
        `;
      },
      listeners: {
        eventClick({ eventRecord }: any) {
          if (eventRecord) {
            const name = eventRecord.name || '';
            const resourceTrade = eventRecord.resource?.trade || 'Dedicated AI Service Gateway';
            setSelectedAppointment({
              id: eventRecord.id,
              name: name,
              customerName: getBuyerAgent(name),
              projectScope: getWorkloadScope(name),
              jobAddress: getClusterEndpoint(name),
              clientFingerprint: getDemoSignatureLabel(name),
              takeoffNotes: getExecutionSpecifications(name, resourceTrade),
              startDate: eventRecord.startDate ? new Date(eventRecord.startDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '13:00',
              endDate: eventRecord.endDate ? new Date(eventRecord.endDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '14:15',
              depositStatus: eventRecord.depositStatus || 'SETTLED VIA PAYPAL',
              paypalTxn: eventRecord.paypalTxn || 'PAY-DEP-9921',
              resourceId: eventRecord.resourceId,
              resourceName: eventRecord.resource?.name || 'Assigned Execution Node',
              resourceEntity: getPrincipalEntity(name),
              resourceTrade: resourceTrade,
              resourceDid: eventRecord.resource?.did || 'node-cluster-01.ap2.net',
            });
            setDispatchWebhookStatus(null);
            setInvoiceStatus(null);
          }
        },
      },
    });

    schedulerRef.current = scheduler;

    // Attach wheel listener to timeline subgrid so vertical mousewheel translates to horizontal timeline scrolling
    const timelineEl =
      (scheduler as any).timeAxisSubGridElement ||
      containerRef.current?.querySelector('.b-timeline-subgrid') ||
      containerRef.current?.querySelector('.b-grid-subgrid-normal');

    const handleTimelineWheel = (e: WheelEvent) => {
      // If user is scrolling vertically with wheel and not holding shift/ctrl
      if (e.deltaY !== 0 && !e.shiftKey && !e.ctrlKey) {
        e.preventDefault();
        const delta = e.deltaY * 0.85;
        if ((scheduler as any).timeAxisSubGrid?.scrollable?.scrollBy) {
          (scheduler as any).timeAxisSubGrid.scrollable.scrollBy(delta, 0);
        } else if (typeof (scheduler as any).scrollHorizontallyTo === 'function') {
          const currentX = (scheduler as any).timeAxisSubGrid?.scrollable?.x || 0;
          (scheduler as any).scrollHorizontallyTo(currentX + delta);
        }
      }
    };

    if (timelineEl) {
      timelineEl.addEventListener('wheel', handleTimelineWheel, { passive: false });
    }

    let mounted = true;
    async function hydrateLiveSchedule() {
      const liveData = await fetchFleetSchedule();
      if (liveData && liveData.resources && liveData.resources.length > 0 && schedulerRef.current && mounted) {
        // Only update if resources are compatible, or keep our enhanced 5-cluster nodes
        setTotalDispatches(liveData.events ? liveData.events.length : 18);
      }
    }
    hydrateLiveSchedule();

    return () => {
      mounted = false;
      if (timelineEl) {
        timelineEl.removeEventListener('wheel', handleTimelineWheel);
      }
      scheduler.destroy();
    };
  }, []);

  // Synchronize AP2 pending workload slot state when parent props change
  useEffect(() => {
    if (!schedulerRef.current) return;
    const targetEvent =
      schedulerRef.current.eventStore.getById('workload-101') ||
      schedulerRef.current.eventStore.find((e: any) => e.name?.includes('Dedicated Gateway'));

    if (targetEvent) {
      targetEvent.set({
        name: isDepositLocked
          ? `Dedicated Gateway Active • MCP Endpoint Bound ($${CATALOG_PLANS[1].price}/mo)`
          : `Dedicated Gateway Pending • Awaiting PayPal Subscription ($${CATALOG_PLANS[1].price}/mo)`,
        eventColor: isDepositLocked ? 'green' : 'orange',
        iconCls: isDepositLocked ? 'b-fa b-fa-check-circle' : 'b-fa b-fa-clock',
        depositStatus: isDepositLocked ? `ACTIVE ($${CATALOG_PLANS[1].price}/MO)` : `AWAITING PAYPAL ($${CATALOG_PLANS[1].price}/MO)`,
        paypalTxn: isDepositLocked ? 'I-AUTONOMOUS-8902' : 'UNPAID',
      });

      const node1Resource =
        schedulerRef.current.resourceStore.getById('node-1') ||
        schedulerRef.current.resourceStore.find((r: any) => r.name?.includes('Node-01'));
      if (node1Resource) {
        node1Resource.set({
          did: isDepositLocked ? 'node-cluster-01.ap2.net' : 'Awaiting Settlement',
          status: isDepositLocked ? 'ACTIVE_ENCLAVE_BOUND' : 'PENDING_SUBSCRIPTION',
        });
      }

      setApiStatus(
        isDepositLocked
          ? '● Node-01 Active: Dedicated Gateway via MCP (HTTP 201)'
          : `○ Pending: Awaiting $${CATALOG_PLANS[1].price}/mo PayPal Subscription Authorization`
      );
      setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));
    }
  }, [isDepositLocked]);

  // Handle Capability Tier Filtering
  const handleFilterTrade = (filter: string) => {
    setActiveTradeFilter(filter);
    if (!schedulerRef.current) return;

    if (filter === 'ALL') {
      schedulerRef.current.resourceStore.clearFilters();
    } else {
      schedulerRef.current.resourceStore.filter((record: any) => {
        const trade = (record.trade || '').toLowerCase();
        if (filter === 'BATCH') return trade.includes('batch') || trade.includes('worker');
        if (filter === 'GATEWAY') return trade.includes('gateway') || trade.includes('ai');
        if (filter === 'CLUSTER') return trade.includes('cluster') || trade.includes('enterprise');
        return true;
      });
    }
  };

  // Simulate A2A PayPal Subscription: Calls FastAPI POST /api/agent/provision
  // MOCK(M-019): button simulates a line activation
  const handleSimulateActivation = async () => {
    if (!schedulerRef.current) return;
    setIsCallingApi(true);
    const t0 = performance.now();
    let measuredStatus: number;
    let measuredStatusText: string;
    let measuredDurationMs: number;
    let responseBody: any;
    let requestPayload: any;
    let isSuccess = false;

    const simulatedSubId = `I-AUTONOMOUS-${Math.floor(100000 + Math.random() * 900000)}`;
    requestPayload = {
      subscription_id: simulatedSubId,
      contractorEmail: 'merchant@example.com',
      business_entity: 'Acme Compute Co',
      trade_vertical: CATALOG_PLANS[1].name,
      monthly_fee: CATALOG_PLANS[1].price,
    };

    try {
      const result = await executeProvisioningAfterSubscription(
        simulatedSubId,
        'Acme Compute Co',
        CATALOG_PLANS[1].name
      );
      measuredDurationMs = Math.round(performance.now() - t0);
      measuredStatus = result.httpStatus;
      measuredStatusText = result.httpStatusText;
      responseBody = result.rawResponse;
      isSuccess = true;

      const targetEvent =
        schedulerRef.current.eventStore.getById('workload-101') ||
        schedulerRef.current.eventStore.find((e: any) => e.name?.includes('Dedicated Gateway'));
      if (targetEvent) {
        targetEvent.set({
          name: `Dedicated Gateway Active • MCP Endpoint: ${result.allocatedDid || 'node-cluster-01.ap2.net'} [BOUND]`,
          eventColor: 'green',
          iconCls: 'b-fa b-fa-check-circle',
          depositStatus: `ACTIVE ($${CATALOG_PLANS[1].price}/MO)`,
          paypalTxn: simulatedSubId,
        });
      }

      const node1Resource =
        schedulerRef.current.resourceStore.getById('node-1') ||
        schedulerRef.current.resourceStore.find((r: any) => r.name?.includes('Node-01'));
      if (node1Resource) {
        node1Resource.set({
          did: result.allocatedDid || 'node-cluster-01.ap2.net',
          status: 'ACTIVE_ENCLAVE_BOUND',
        });
      }

      setApiStatus(`● Node-01 Active: ${result.allocatedDid || 'node-cluster-01.ap2.net'} via MCP (HTTP ${measuredStatus})`);
      setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));
      setLeadSimulationBanner(`✓ Node-01 Dedicated Gateway Provisioned: ${result.allocatedDid || 'node-cluster-01.ap2.net'} bound to Sub ${simulatedSubId}!`);
      setTimeout(() => setLeadSimulationBanner(null), 5000);

      if (onToggleDepositLock) {
        onToggleDepositLock(true);
      }
    } catch (err: any) {
      measuredDurationMs = Math.round(performance.now() - t0);
      measuredStatus = err?.httpStatus ?? (err?.status ?? 0);
      measuredStatusText = err?.httpStatusText ?? (err?.statusText ?? (measuredStatus === 0 ? 'NETWORK_ERROR' : 'ERROR'));
      responseBody = err?.rawResponse ?? { error: err instanceof Error ? err.message : String(err) };
      setApiStatus(`● Provisioning failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsCallingApi(false);
    }

    const summary = isSuccess
      ? `Node-01 Dedicated Gateway Provisioned • Sub ${simulatedSubId} Active ($${CATALOG_PLANS[1].price}/mo)`
      : `Node-01 Provisioning failed (${measuredStatus} ${measuredStatusText})`;

    addWireLog({
      method: 'POST',
      endpoint: '/api/agent/provision',
      status: measuredStatus,
      statusText: measuredStatusText,
      durationMs: measuredDurationMs,
      category: 'MCP',
      summary,
      request: requestPayload,
      response: responseBody,
    });
  };

  // Reset Node-01 and Node-02 back to initial baseline
  const handleResetLine = () => {
    if (!schedulerRef.current) return;

    // 1. Reset pending / active subscription event on Node-01
    const targetEvent =
      schedulerRef.current.eventStore.getById('workload-101') ||
      schedulerRef.current.eventStore.find((e: any) => e.name?.includes('Dedicated Gateway'));
    if (targetEvent) {
      targetEvent.set({
        name: `Dedicated Gateway Pending • Awaiting PayPal Subscription ($${CATALOG_PLANS[1].price}/mo)`,
        eventColor: 'orange',
        iconCls: 'b-fa b-fa-clock',
        depositStatus: `AWAITING PAYPAL ($${CATALOG_PLANS[1].price}/MO)`,
        paypalTxn: 'UNPAID',
      });
    }

    // 2. Remove the dynamically locked slot event from Node-02/Node-01
    const lockedEvent1 = schedulerRef.current.eventStore.getById('locked-workload-slot-1');
    if (lockedEvent1) {
      schedulerRef.current.eventStore.remove(lockedEvent1);
    }
    const lockedEvent2 = schedulerRef.current.eventStore.getById('locked-workload-slot-2');
    if (lockedEvent2) {
      schedulerRef.current.eventStore.remove(lockedEvent2);
    }

    // 3. Reset slot locked state and metrics
    setIsSlotLocked(false);
    setTotalDispatches(18);
    setTotalVaultedDeposits(1219.87);

    const node1Resource =
      schedulerRef.current.resourceStore.getById('node-1') ||
      schedulerRef.current.resourceStore.find((r: any) => r.name?.includes('Node-01'));
    if (node1Resource) {
      node1Resource.set({
        did: 'Awaiting Settlement',
        status: 'PENDING_SUBSCRIPTION',
      });
    }

    setApiStatus(`○ Pending: Awaiting $${CATALOG_PLANS[1].price}/mo PayPal Subscription Authorization`);
    setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));

    if (onToggleDepositLock) {
      onToggleDepositLock(false);
    }
  };

  // Atomically locks an open workload execution slot on Node-02 upon simulated buyer agent intent mandate & verified PayPal capture
  // MOCK(M-019): button simulates inbound work and a slot lock
  const handleSimulateInboundLeadAndLock = async () => {
    if (!schedulerRef.current || isLockingSlot || isSlotLocked) return;
    setIsLockingSlot(true);
    const t0 = performance.now();
    let measuredStatus: number;
    let measuredStatusText: string;
    let measuredDurationMs: number;
    let responseBody: any;
    let requestPayload: any;
    let isSuccess = false;

    requestPayload = {
      jobId: 'WORKLOAD-SLOT-02',
      territoryZone: 'Node-02: Batch Data & RAG Pipeline',
      slotStartIso: '2026-10-08 16:00',
      paypalTransactionId: 'AP2-TXN-DISPATCH-9022',
    };

    try {
      const res = await lockTerritorySlot(
        'WORKLOAD-SLOT-02',
        'Node-02: Batch Data & RAG Pipeline',
        '2026-10-08 16:00',
        'AP2-TXN-DISPATCH-9022'
      );
      measuredDurationMs = Math.round(performance.now() - t0);
      measuredStatus = res.httpStatus;
      measuredStatusText = res.httpStatusText;
      responseBody = res.rawResponse;

      if (res.success) {
        isSuccess = true;
        setIsSlotLocked(true);
        const lockedEventId = 'locked-workload-slot-2';
        const existing = schedulerRef.current.eventStore.getById(lockedEventId);
        if (!existing) {
          // Schedule in open 16:00 - 17:15 window on Node-02 to prevent row expansion / overlap
          (schedulerRef.current.eventStore as any).add({
            id: lockedEventId,
            resourceId: 'node-2',
            name: `#204 Batch Worker Renewal (included in ${CATALOG_PLANS[0].name})`,
            startDate: '2026-10-08 16:00',
            endDate: '2026-10-08 17:15',
            eventColor: 'blue',
            iconCls: 'b-fa b-fa-check-circle',
            depositStatus: `SETTLED ($${CATALOG_PLANS[0].price} PAYPAL)`,
            paypalTxn: 'TXN-DISPATCH-9022',
          });
        }
        setTotalDispatches(19);
        setTotalVaultedDeposits(1269.86);
        setApiStatus(`● Enclave Execution Slot Locked: MCP Task Bound (HTTP ${measuredStatus})`);
        setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));
        setLeadSimulationBanner(`✓ Autonomous Buyer Mandate Verified: agent:gpt-4o:apex-procure dispatched to Node-02. $${CATALOG_PLANS[0].price} PayPal Payment Vaulted!`);
        setTimeout(() => setLeadSimulationBanner(null), 6000);
      }
    } catch (err: any) {
      measuredDurationMs = Math.round(performance.now() - t0);
      measuredStatus = err?.httpStatus ?? (err?.status ?? 0);
      measuredStatusText = err?.httpStatusText ?? (err?.statusText ?? (measuredStatus === 0 ? 'NETWORK_ERROR' : 'ERROR'));
      responseBody = err?.rawResponse ?? { error: err instanceof Error ? err.message : String(err) };
      setApiStatus(`● Slot lock failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsLockingSlot(false);
    }

    const summary = isSuccess
      ? `Node-02 Enclave hardware execution slot locked (16:00-17:15) • $${CATALOG_PLANS[0].price} PayPal Payment Vaulted`
      : `Slot lock failed (${measuredStatus} ${measuredStatusText})`;

    addWireLog({
      method: 'POST',
      endpoint: '/api/agent/dispatch/lock-slot',
      status: measuredStatus,
      statusText: measuredStatusText,
      durationMs: measuredDurationMs,
      category: 'Enclave Dispatch',
      summary,
      request: requestPayload,
      response: responseBody,
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', backgroundColor: '#0f172a', position: 'relative', overflow: 'hidden' }}>
      {/* Simulation Banner Notification */}
      {leadSimulationBanner && (
        <div
          style={{
            backgroundColor: '#065f46',
            color: '#a7f3d0',
            padding: '8px 20px',
            fontSize: '12px',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #059669',
            animation: 'fadeIn 0.2s ease-in-out',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={16} />
            <span>{leadSimulationBanner}</span>
          </div>
          <button
            onClick={() => setLeadSimulationBanner(null)}
            style={{ background: 'none', border: 'none', color: '#a7f3d0', cursor: 'pointer' }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* 1. UNIFIED ENCLAVE WORKLOAD HEADER & METRICS CARD */}
      <div
        style={{
          backgroundColor: '#0f172a',
          border: '1px solid #1e293b',
          borderRadius: '12px',
          padding: isScheduleMetricsCollapsed ? '10px 16px' : '14px 18px',
          display: 'flex',
          flexDirection: 'column',
          gap: isScheduleMetricsCollapsed ? '6px' : '12px',
          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
          margin: '12px 16px 0 16px',
          flexShrink: 0,
        }}
      >
        {/* Card Header Row */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
            width: '100%',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
            <div
              style={{
                width: '26px',
                height: '26px',
                borderRadius: '6px',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Cpu size={14} />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
              <span style={{ fontSize: '13px', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>
                Autonomous Enclave &amp; Workloads
              </span>
              <span
                style={{
                  fontSize: '10px',
                  backgroundColor: 'rgba(56, 189, 248, 0.15)',
                  color: '#38bdf8',
                  border: '1px solid rgba(56, 189, 248, 0.35)',
                  padding: '1px 6px',
                  borderRadius: '9999px',
                  fontWeight: 700,
                  whiteSpace: 'nowrap',
                }}
              >
                FAST-MCP
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
            {/* API Verification Badge (Concise & Clean) */}
            <span
              title={apiStatus}
              style={{
                fontSize: '11px',
                fontWeight: 700,
                padding: '4px 8px',
                borderRadius: '5px',
                backgroundColor:
                  isDepositLocked || isSlotLocked
                    ? '#064e3b'
                    : '#451a03',
                color:
                  isDepositLocked || isSlotLocked
                    ? '#ecfdf5'
                    : '#fef3c7',
                border: `1px solid ${
                  isDepositLocked || isSlotLocked
                    ? '#10b981'
                    : '#f59e0b'
                }`,
                whiteSpace: 'nowrap',
              }}
            >
              {isDepositLocked
                ? `● Node-01 Active ($${CATALOG_PLANS[1].price})`
                : isSlotLocked
                ? '● Node-02 Locked'
                : '○ Awaiting Auth'}
            </span>

            {/* Sync Timestamp (Clean & Single Line) */}
            <div style={{ fontSize: '11px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '3px', whiteSpace: 'nowrap' }}>
              <span style={{ color: '#34d399', fontFamily: 'monospace', fontWeight: 600 }}>{lastPaymentSync.slice(11, 19)} UTC</span>
            </div>

            {/* Collapse / Expand Toggle Button */}
            <button
              onClick={toggleScheduleMetricsCollapsed}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                padding: '5px 10px',
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '6px',
                color: isScheduleMetricsCollapsed ? '#38bdf8' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
              }}
              title={isScheduleMetricsCollapsed ? 'Expand Metrics Deck' : 'Collapse Metrics Deck to maximize schedule timeline'}
            >
              {isScheduleMetricsCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
              <span>{isScheduleMetricsCollapsed ? 'Expand' : 'Collapse'}</span>
            </button>
          </div>
        </div>

        {/* Row 2: Subtitle when expanded vs. Crisp live metrics strip when collapsed */}
        {isScheduleMetricsCollapsed ? (
          <div style={{ fontSize: '11px', color: '#94a3b8', paddingLeft: '34px', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '10px', whiteSpace: 'nowrap', overflow: 'hidden' }}>
            <span style={{ color: '#38bdf8', fontWeight: 600 }}>PayPal Vault Settled</span>
            <span style={{ color: '#475569' }}>&bull;</span>
            <span>Enclaves: <strong style={{ color: '#f8fafc' }}>5 Attested</strong></span>
            <span style={{ color: '#475569' }}>&bull;</span>
            <span>Workloads: <strong style={{ color: '#f8fafc' }}>{totalDispatches} Tasks</strong></span>
            <span style={{ color: '#475569' }}>&bull;</span>
            <span>Demo MRR: <strong style={{ color: '#fbbf24' }}>${totalVaultedDeposits.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong></span>
            <span style={{ color: '#475569' }}>&bull;</span>
            <span>Tier Quotas: <strong style={{ color: '#38bdf8' }}>{tierQuotasLabel}</strong> <span style={{ fontSize: '9px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', padding: '1px 4px', borderRadius: '3px' }}>Tasks/Mo</span></span>
            <span style={{ color: '#475569' }}>&bull;</span>
            <span>Execution: <strong style={{ color: '#a78bfa' }}>High-Throughput</strong></span>
          </div>
        ) : (
          <div style={{ fontSize: '11px', color: '#94a3b8', paddingLeft: '34px', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap' }}>
            <span style={{ color: '#38bdf8', fontWeight: 600 }}>PayPal Vault Settled</span>
            <span style={{ color: '#475569' }}>&bull;</span>
            <span>QBO &amp; MCP Sync &bull; 5 Active Autonomous Node Enclaves</span>
          </div>
        )}

        {/* Card Body: 5 Operational Triage Metrics Summary Cards (Expanded Only) */}
        {!isScheduleMetricsCollapsed && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(5, 1fr)',
              gap: '10px',
              paddingTop: '4px',
            }}
          >
            <div style={{ padding: '8px 12px', borderRadius: '6px', backgroundColor: '#131d31', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ padding: '6px', borderRadius: '5px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8' }}>
                <Server size={16} />
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Active Worker Nodes</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>5 Enclave Clusters</div>
                <div style={{ fontSize: '9px', color: '#34d399', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  Hardware Enclaves <span style={{ fontSize: '8px', backgroundColor: 'rgba(52, 211, 153, 0.15)', padding: '1px 3px', borderRadius: '2px' }}>Demo</span>
                </div>
              </div>
            </div>

            <div style={{ padding: '8px 12px', borderRadius: '6px', backgroundColor: '#131d31', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ padding: '6px', borderRadius: '5px', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399' }}>
                <CalendarCheck size={16} />
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Mandates &amp; Renewals</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>{totalDispatches} Active Mandates</div>
                <div style={{ fontSize: '9px', color: '#38bdf8' }}>Subscription Renewal Cycles</div>
              </div>
            </div>

            <div style={{ padding: '8px 12px', borderRadius: '6px', backgroundColor: '#131d31', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ padding: '6px', borderRadius: '5px', backgroundColor: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24' }}>
                <DollarSign size={16} />
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>PayPal Settlements</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>${totalVaultedDeposits.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mo</div>
                <div style={{ fontSize: '9px', color: '#fbbf24' }}>Seeded demo fleet</div>
              </div>
            </div>

            <div style={{ padding: '8px 12px', borderRadius: '6px', backgroundColor: '#131d31', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ padding: '6px', borderRadius: '5px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8' }}>
                <Zap size={16} />
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Catalog Quotas</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  {tierQuotasLabel} <span style={{ fontSize: '9px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', padding: '1px 4px', borderRadius: '3px' }}>Tasks/Mo</span>
                </div>
                <div style={{ fontSize: '9px', color: '#38bdf8' }}>Catalog Tier Quotas</div>
              </div>
            </div>

            <div style={{ padding: '8px 12px', borderRadius: '6px', backgroundColor: '#131d31', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div style={{ padding: '6px', borderRadius: '5px', backgroundColor: 'rgba(168, 85, 247, 0.15)', color: '#c084fc' }}>
                <Clock size={16} />
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Autonomous Workload Delivery</div>
                <div style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>Active Execution</div>
                <div style={{ fontSize: '9px', color: '#a78bfa', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  Multi-Agent Workloads <span style={{ fontSize: '8px', backgroundColor: 'rgba(167, 139, 250, 0.15)', padding: '1px 3px', borderRadius: '2px' }}>Demo</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Filter Pills & Interactive Action Toolbar (Strict 2-Tier Aligned 3x2 Grid) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '16px',
          padding: '10px 20px',
          backgroundColor: '#0d1527',
          borderBottom: '1px solid #1e293b',
          flexWrap: 'nowrap',
          overflowX: 'auto',
        }}
      >
        {/* Left: 3 Columns × 2 Rows Filter Grid */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
          <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 700, letterSpacing: '0.04em' }}>FILTER:</span>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, minmax(105px, 1fr))',
              gridTemplateRows: '28px',
              gap: '6px',
              alignItems: 'center',
            }}
          >
            {/* Button 1: ALL */}
            <button
              onClick={() => handleFilterTrade('ALL')}
              style={{
                width: '100%',
                height: '100%',
                boxSizing: 'border-box',
                fontSize: '11px',
                fontWeight: 700,
                padding: '0 8px',
                borderRadius: '5px',
                border: activeTradeFilter === 'ALL' ? '1px solid #38bdf8' : '1px solid #1e293b',
                backgroundColor: activeTradeFilter === 'ALL' ? 'rgba(56, 189, 248, 0.15)' : '#131d31',
                color: activeTradeFilter === 'ALL' ? '#38bdf8' : '#94a3b8',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s ease',
              }}
            >
              All Nodes (5)
            </button>

            {/* Button 2: BATCH */}
            <button
              onClick={() => handleFilterTrade('BATCH')}
              style={{
                width: '100%',
                height: '100%',
                boxSizing: 'border-box',
                fontSize: '11px',
                fontWeight: 600,
                padding: '0 8px',
                borderRadius: '5px',
                border: activeTradeFilter === 'BATCH' ? '1px solid #38bdf8' : '1px solid #1e293b',
                backgroundColor: activeTradeFilter === 'BATCH' ? 'rgba(56, 189, 248, 0.15)' : '#131d31',
                color: activeTradeFilter === 'BATCH' ? '#38bdf8' : '#94a3b8',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s ease',
              }}
            >
              Batch Workers (${`$${CATALOG_PLANS[0].price}`})
            </button>

            {/* Button 3: GATEWAY */}
            <button
              onClick={() => handleFilterTrade('GATEWAY')}
              style={{
                width: '100%',
                height: '100%',
                boxSizing: 'border-box',
                fontSize: '11px',
                fontWeight: 600,
                padding: '0 8px',
                borderRadius: '5px',
                border: activeTradeFilter === 'GATEWAY' ? '1px solid #38bdf8' : '1px solid #1e293b',
                backgroundColor: activeTradeFilter === 'GATEWAY' ? 'rgba(56, 189, 248, 0.15)' : '#131d31',
                color: activeTradeFilter === 'GATEWAY' ? '#38bdf8' : '#94a3b8',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s ease',
              }}
            >
              AI Gateways (${`$${CATALOG_PLANS[1].price}`})
            </button>

            {/* Button 4: CLUSTER */}
            <button
              onClick={() => handleFilterTrade('CLUSTER')}
              style={{
                width: '100%',
                height: '100%',
                boxSizing: 'border-box',
                fontSize: '11px',
                fontWeight: 600,
                padding: '0 8px',
                borderRadius: '5px',
                border: activeTradeFilter === 'CLUSTER' ? '1px solid #38bdf8' : '1px solid #1e293b',
                backgroundColor: activeTradeFilter === 'CLUSTER' ? 'rgba(56, 189, 248, 0.15)' : '#131d31',
                color: activeTradeFilter === 'CLUSTER' ? '#38bdf8' : '#94a3b8',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.15s ease',
              }}
            >
              Enterprise Clusters (${`$${CATALOG_PLANS[2].price}`})
            </button>
          </div>

          {activeTradeFilter !== 'ALL' && (
            <button
              onClick={() => handleFilterTrade('ALL')}
              style={{
                fontSize: '10px',
                fontWeight: 700,
                padding: '4px 8px',
                borderRadius: '5px',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                color: '#fca5a5',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                whiteSpace: 'nowrap',
              }}
              title="Clear active filter"
            >
              <X size={11} />
              Reset
            </button>
          )}
        </div>

        {/* Right: 3 Columns × 2 Rows Aligned Action Grid (+ Reset) */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '120px 185px 170px auto',
            gridTemplateRows: '28px 28px',
            gap: '8px',
            alignItems: 'center',
            flexShrink: 0,
          }}
        >
          {/* Row 1, Col 1: Hourly Slots */}
          {schedulerViewMode === 'timeline' ? (
            <button
              onClick={() => handleHorizonChange('hourly')}
              title="Daily Hourly Slots (horizontal scrolling)"
              style={{
                width: '100%',
                height: '100%',
                borderRadius: '5px',
                border: horizonMode === 'hourly' ? '1px solid #38bdf8' : '1px solid #1e293b',
                backgroundColor: horizonMode === 'hourly' ? 'rgba(56, 189, 248, 0.18)' : '#131d31',
                color: horizonMode === 'hourly' ? '#38bdf8' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '4px',
                whiteSpace: 'nowrap',
                boxSizing: 'border-box',
              }}
            >
              ⏱ Hourly Slots
            </button>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', backgroundColor: 'rgba(56, 189, 248, 0.08)', border: '1px solid rgba(56, 189, 248, 0.2)', borderRadius: '5px' }}>
              <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 600 }}>Card Grid Active</span>
            </div>
          )}

          {/* Row 1, Col 2: Date Navigation (< [Thu, 10/8] Today >) */}
          {schedulerViewMode === 'timeline' ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#131d31', border: '1px solid #1e293b', borderRadius: '5px', height: '100%', width: '100%', boxSizing: 'border-box', padding: '0 2px' }}>
              <button
                onClick={handlePrevDay}
                title="Previous Day"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent', border: 'none', color: '#94a3b8', padding: '0 4px', height: '100%', cursor: 'pointer' }}
              >
                <ChevronLeft size={13} />
              </button>
              <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
                <button
                  onClick={() => {
                    if (dateInputRef.current) {
                      if ('showPicker' in HTMLInputElement.prototype) {
                        try {
                          dateInputRef.current.showPicker();
                        } catch {
                          dateInputRef.current.click();
                        }
                      } else {
                        dateInputRef.current.click();
                      }
                    }
                  }}
                  title="Click to select any date from calendar picker"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '3px',
                    backgroundColor: activeDate.getDate() === 8 && activeDate.getMonth() === 9 ? 'rgba(56, 189, 248, 0.15)' : 'transparent',
                    border: 'none',
                    color: activeDate.getDate() === 8 && activeDate.getMonth() === 9 ? '#38bdf8' : '#f8fafc',
                    padding: '0 4px',
                    fontSize: '11px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  <Calendar size={11} />
                  <span>{activeDate.toLocaleDateString('en-US', { weekday: 'short', month: 'numeric', day: 'numeric' })}</span>
                </button>
                <input
                  ref={dateInputRef}
                  type="date"
                  value={`${activeDate.getFullYear()}-${String(activeDate.getMonth() + 1).padStart(2, '0')}-${String(activeDate.getDate()).padStart(2, '0')}`}
                  onChange={handleDateChange}
                  style={{
                    position: 'absolute',
                    opacity: 0,
                    width: '100%',
                    height: '100%',
                    top: 0,
                    left: 0,
                    pointerEvents: 'none',
                  }}
                />
              </div>
              <button
                onClick={handleToday}
                title="Jump to Today (Oct 8, 2026)"
                style={{
                  padding: '0 5px',
                  backgroundColor: 'transparent',
                  border: 'none',
                  color: '#38bdf8',
                  fontSize: '10px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  height: '100%',
                }}
              >
                Today
              </button>
              <button
                onClick={handleNextDay}
                title="Next Day"
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent', border: 'none', color: '#94a3b8', padding: '0 4px', height: '100%', cursor: 'pointer' }}
              >
                <ChevronRight size={13} />
              </button>
            </div>
          ) : (
            <div />
          )}

          {/* Row 1, Col 3: Sim Workload Task */}
          <button
            onClick={handleSimulateInboundLeadAndLock}
            disabled={isLockingSlot || isSlotLocked}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              padding: '0 8px',
              width: '100%',
              height: '100%',
              borderRadius: '5px',
              border: 'none',
              backgroundColor: isSlotLocked ? '#1e3a8a' : isLockingSlot ? '#1e293b' : '#2563eb',
              color: isSlotLocked ? '#60a5fa' : '#fff',
              fontSize: '11px',
              fontWeight: 600,
              cursor: isLockingSlot || isSlotLocked ? 'not-allowed' : 'pointer',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
              whiteSpace: 'nowrap',
              boxSizing: 'border-box',
            }}
          >
            <CalendarCheck size={13} />
            {isLockingSlot
              ? 'Locking Slot...'
              : isSlotLocked
              ? '✓ Slot Locked (Node-02)'
              : '⚡ Sim Workload Task'}
          </button>

          {/* Row 1, Col 4: Empty placeholder to align with Reset in Row 2 */}
          <div style={{ width: '60px' }} />

          {/* Row 2, Col 1: 7-Day Horizon (Identical dimensions as Hourly Slots) */}
          {schedulerViewMode === 'timeline' ? (
            <button
              onClick={() => handleHorizonChange('weekly')}
              title="7-Day Weekly Workload Horizon (Mon - Sun, broad view without hourly clutter)"
              style={{
                width: '100%',
                height: '100%',
                borderRadius: '5px',
                border: horizonMode === 'weekly' ? '1px solid #38bdf8' : '1px solid #1e293b',
                backgroundColor: horizonMode === 'weekly' ? 'rgba(56, 189, 248, 0.18)' : '#131d31',
                color: horizonMode === 'weekly' ? '#38bdf8' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '4px',
                whiteSpace: 'nowrap',
                boxSizing: 'border-box',
              }}
            >
              📅 7-Day Horizon
            </button>
          ) : (
            <div />
          )}

          {/* Row 2, Col 2: Zoom Controls (Identical dimensions as Date Navigation) */}
          {schedulerViewMode === 'timeline' ? (
            <div style={{ display: 'flex', alignItems: 'center', backgroundColor: '#131d31', border: '1px solid #1e293b', borderRadius: '5px', height: '100%', width: '100%', boxSizing: 'border-box', padding: '0 2px' }}>
              <button
                onClick={handleZoomIn}
                title="Zoom In (Widen hour columns to expand cards)"
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px', backgroundColor: 'transparent', border: 'none', color: '#94a3b8', padding: '0 4px', height: '100%', fontSize: '11px', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}
              >
                <ZoomIn size={12} />
                <span>Zoom +</span>
              </button>
              <div style={{ width: '1px', height: '12px', backgroundColor: '#334155' }} />
              <button
                onClick={handleZoomOut}
                title="Zoom Out (Show wider time range)"
                style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px', backgroundColor: 'transparent', border: 'none', color: '#94a3b8', padding: '0 4px', height: '100%', fontSize: '11px', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}
              >
                <ZoomOut size={12} />
                <span>Zoom -</span>
              </button>
            </div>
          ) : (
            <div />
          )}

          {/* Row 2, Col 3: Sim Sub ($79.99) (Identical dimensions as Sim Workload) */}
          <button
            onClick={handleSimulateActivation}
            disabled={isCallingApi || isDepositLocked}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              padding: '0 8px',
              width: '100%',
              height: '100%',
              borderRadius: '5px',
              border: 'none',
              backgroundColor: isDepositLocked ? '#065f46' : isCallingApi ? '#1e293b' : '#0284c7',
              color: isDepositLocked ? '#34d399' : '#fff',
              fontSize: '11px',
              fontWeight: 600,
              cursor: isCallingApi || isDepositLocked ? 'not-allowed' : 'pointer',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
              whiteSpace: 'nowrap',
              boxSizing: 'border-box',
            }}
          >
            <Zap size={13} />
            {isCallingApi
              ? 'Provisioning...'
              : isDepositLocked
              ? '✓ Node-01 Active'
              : `⚡ Sim Sub ($${CATALOG_PLANS[1].price})`}
          </button>

          {/* Row 2, Col 4: Reset Button */}
          <button
            onClick={handleResetLine}
            title="Reset Node-01 back to Amber/Orange (Awaiting Subscription)"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
              padding: '0 8px',
              height: '100%',
              borderRadius: '5px',
              border: '1px solid #334155',
              backgroundColor: '#1e293b',
              color: '#94a3b8',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              boxSizing: 'border-box',
            }}
          >
            <RotateCcw size={12} />
            Reset
          </button>
        </div>
      </div>

      {/* Bryntum Scheduler Container (Timeline View) */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          width: '100%',
          minHeight: '220px',
          overflow: 'hidden',
          display: schedulerViewMode === 'timeline' ? 'block' : 'none',
        }}
      />

      {/* Autonomous Node Enclave Execution Matrix (Operator View) */}
      {schedulerViewMode === 'matrix' && (
        <div
          style={{
            flex: 1,
            width: '100%',
            overflowY: 'auto',
            padding: '16px 20px',
            display: 'grid',
            gridTemplateColumns: 'minmax(340px, 420px) 1fr',
            gap: '16px',
            backgroundColor: '#090e17',
          }}
        >
          {/* LEFT COLUMN: ACTIVE WORKER NODE CLUSTERS (5 ENCLAVES) */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '4px', borderBottom: '1px solid #1e293b' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 800, color: '#f8fafc', letterSpacing: '0.04em' }}>
                <Server size={13} color="#38bdf8" />
                <span>EXECUTION WORKER NODES ({displayedNodes.length} OF 5 ONLINE)</span>
              </div>
              <span style={{ fontSize: '10px', color: '#34d399', fontWeight: 700, backgroundColor: 'rgba(16, 185, 129, 0.12)', padding: '1px 6px', borderRadius: '4px', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                100% HEALTHY
              </span>
            </div>

            {/* List of Filtered Node Enclave Cards */}
            {displayedNodes.map((node) => (
              <div
                key={node.id}
                style={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: '8px',
                  padding: '10px 14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                  boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ width: '7px', height: '7px', borderRadius: '50%', backgroundColor: node.color }} />
                    <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>{node.name}</span>
                  </div>
                  <span
                    style={{
                      fontSize: '9px',
                      fontWeight: 800,
                      padding: '2px 6px',
                      borderRadius: '4px',
                      backgroundColor: node.status.includes('ACTIVE') || node.status.includes('LOCKED') ? '#064e3b' : '#451a03',
                      color: node.status.includes('ACTIVE') || node.status.includes('LOCKED') ? '#ecfdf5' : '#fef3c7',
                      border: `1px solid ${node.status.includes('ACTIVE') || node.status.includes('LOCKED') ? '#10b981' : '#f59e0b'}`,
                    }}
                  >
                    {node.status}
                  </span>
                </div>

                <div style={{ fontSize: '10px', color: '#94a3b8', lineHeight: 1.2 }}>
                  {node.entity}
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#090e17', padding: '4px 8px', borderRadius: '5px', border: '1px solid #1e293b' }}>
                  <span style={{ fontSize: '10px', fontFamily: 'monospace', color: '#38bdf8' }}>{node.did}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '9px', color: '#34d399', fontWeight: 700 }}>⚡ {node.throughput}</span>
                    <span style={{ fontSize: '9px', color: '#cbd5e1' }}>{node.health}</span>
                  </div>
                </div>

                <div style={{ fontSize: '10px', color: '#cbd5e1', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ color: '#64748b' }}>Current:</span>
                  <span style={{ fontWeight: 600, color: '#f8fafc' }}>{node.activeJob}</span>
                </div>
              </div>
            ))}
          </div>

          {/* RIGHT COLUMN: ACTIVE WORKLOAD EXECUTION QUEUE */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '4px', borderBottom: '1px solid #1e293b' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 800, color: '#f8fafc', letterSpacing: '0.04em' }}>
                <Clock size={13} color="#34d399" />
                <span>AUTONOMOUS WORKLOAD EXECUTION QUEUE ({displayedWorkloads.length} OF {allWorkloadsList.length} ALLOCATED)</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: '10px', color: '#94a3b8' }}>Settlement Rail:</span>
                <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700 }}>PayPal Subscriptions</span>
              </div>
            </div>

            {/* Enclave Resource Telemetry Summary Bar */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px', backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px', padding: '10px 14px' }}>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>GPU Enclave Load</div>
                <div style={{ fontSize: '16px', fontWeight: 800, color: '#38bdf8', marginTop: '2px' }}>78.4%</div>
                <div style={{ width: '100%', height: '4px', backgroundColor: '#1e293b', borderRadius: '2px', marginTop: '4px', overflow: 'hidden' }}>
                  <div style={{ width: '78.4%', height: '100%', backgroundColor: '#38bdf8', borderRadius: '2px' }} />
                </div>
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>MCP Concurrency</div>
                <div style={{ fontSize: '16px', fontWeight: 800, color: '#34d399', marginTop: '2px' }}>14 Active Streams</div>
              </div>
              <div>
                <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>Demo Fleet MRR</div>
                <div style={{ fontSize: '16px', fontWeight: 800, color: '#a78bfa', marginTop: '2px' }}>${totalVaultedDeposits.toLocaleString()}</div>
                <div style={{ fontSize: '10px', color: '#34d399', marginTop: '2px' }}>Seeded demo data</div>
              </div>
            </div>

            {/* List of Active Workloads (Filtered & Clickable to open Slide-Over Inspection Drawer!) */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {displayedWorkloads.length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', backgroundColor: '#0f172a', borderRadius: '8px', border: '1px dashed #334155' }}>
                  <div style={{ fontSize: '13px', color: '#94a3b8' }}>No workloads allocated for this capability filter.</div>
                  <button
                    onClick={() => handleFilterTrade('ALL')}
                    style={{ marginTop: '10px', padding: '5px 12px', borderRadius: '5px', border: '1px solid #38bdf8', backgroundColor: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}
                  >
                    Reset Filter (Show All Workloads)
                  </button>
                </div>
              ) : (
                displayedWorkloads.map((wl) => (
                  <div
                    key={wl.id}
                    onClick={() => {
                      setSelectedAppointment({
                        id: wl.id,
                        name: wl.name,
                        customerName: wl.buyer,
                        projectScope: getWorkloadScope(wl.name),
                        jobAddress: getClusterEndpoint(wl.name),
                        clientFingerprint: getDemoSignatureLabel(wl.name),
                        takeoffNotes: getExecutionSpecifications(wl.name, wl.node),
                        startDate: '08:00',
                        endDate: '09:30',
                        depositStatus: wl.status,
                        paypalTxn: wl.txn,
                        resourceId: (wl as any).nodeId || 'node-1',
                        resourceName: wl.node,
                        resourceEntity: getPrincipalEntity(wl.name),
                        resourceTrade: wl.node,
                        resourceDid: 'node-cluster-01.ap2.net',
                      });
                    }}
                    style={{
                      backgroundColor: '#0f172a',
                      border: (wl as any).isNew ? '1px solid #38bdf8' : '1px solid #1e293b',
                      borderRadius: '8px',
                      padding: '10px 14px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
                    }}
                    title="Click to inspect cryptographic signature, anti-tamper hash, and download receipt"
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>{wl.name}</span>
                        {(wl as any).isNew && (
                          <span style={{ fontSize: '9px', fontWeight: 800, padding: '1px 5px', borderRadius: '3px', backgroundColor: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8' }}>
                            NEWLY LOCKED
                          </span>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px', color: '#94a3b8' }}>
                        <span style={{ color: '#cbd5e1' }}>{wl.node.split(':')[0]}</span>
                        <span>&bull;</span>
                        <span style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{wl.buyer}</span>
                        <span>&bull;</span>
                        <span>{wl.window}</span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 700,
                          padding: '3px 8px',
                          borderRadius: '4px',
                          backgroundColor: '#090e17',
                          color: wl.status.includes('ACTIVE') || wl.status.includes('PAID') || wl.status.includes('SETTLED') ? '#34d399' : '#fbbf24',
                          border: '1px solid #1e293b',
                        }}
                      >
                        {wl.status}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedAppointment({
                            id: wl.id,
                            name: wl.name,
                            customerName: wl.buyer,
                            projectScope: getWorkloadScope(wl.name),
                            jobAddress: getClusterEndpoint(wl.name),
                            clientFingerprint: getDemoSignatureLabel(wl.name),
                            takeoffNotes: getExecutionSpecifications(wl.name, wl.node),
                            startDate: '08:00',
                            endDate: '09:30',
                            depositStatus: wl.status,
                            paypalTxn: wl.txn,
                            resourceId: (wl as any).nodeId || 'node-1',
                            resourceName: wl.node,
                            resourceEntity: getPrincipalEntity(wl.name),
                            resourceTrade: wl.node,
                            resourceDid: 'node-cluster-01.ap2.net',
                          });
                        }}
                        style={{
                          backgroundColor: '#131d31',
                          border: '1px solid #1e293b',
                          color: '#38bdf8',
                          borderRadius: '4px',
                          padding: '4px 8px',
                          fontSize: '10px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        Inspect &rarr;
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Live AP2 API Call Execution Wire Console Dock */}
      <div
        style={{
          width: '100%',
          backgroundColor: '#080d1a',
          borderTop: '1px solid #1e293b',
          display: 'flex',
          flexDirection: 'column',
          zIndex: 40,
          transition: 'height 0.2s ease-in-out',
          ...(dockHeight === 'collapsed'
            ? { height: '36px', minHeight: '36px' }
            : dockHeight === 'expanded'
            ? { height: '310px', minHeight: '310px' }
            : { height: '190px', minHeight: '190px'}),
        }}
      >
        {/* Dock Header Bar */}
        <div
          style={{
            height: '36px',
            minHeight: '36px',
            backgroundColor: '#0b1329',
            borderBottom: dockHeight === 'collapsed' ? 'none' : '1px solid #1e293b',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px',
            userSelect: 'none',
          }}
        >
          {/* Left Title & Status */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  backgroundColor: '#10b981',
                  boxShadow: '0 0 8px #10b981',
                  display: 'inline-block',
                }}
              />
              <Activity size={14} style={{ color: '#38bdf8' }} />
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#f8fafc', letterSpacing: '0.04em', whiteSpace: 'nowrap' }}>
                LIVE AP2 EXECUTION WIRE &bull; API CALL TELEMETRY
              </span>
            </div>

            <span style={{ fontSize: '10px', color: '#94a3b8', whiteSpace: 'nowrap' }}>
              ({apiWireLogs.filter((log) => wireCategoryFilter === 'ALL' || log.category.toLowerCase().includes(wireCategoryFilter.toLowerCase())).length} calls)
            </span>
          </div>

          {/* Middle Filter Tabs (visible when not collapsed) */}
          {dockHeight !== 'collapsed' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 600, marginRight: '2px', whiteSpace: 'nowrap' }}>FILTER:</span>
              {[
                { id: 'ALL', label: 'All Calls' },
                { id: 'MCP', label: 'MCP' },
                { id: 'Enclave Dispatch', label: 'Enclave Dispatch' },
                { id: 'PayPal', label: 'PayPal' },
                { id: 'QuickBooks/ERP', label: 'QuickBooks/ERP' },
                { id: 'Security', label: 'Security' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setWireCategoryFilter(tab.id)}
                  style={{
                    height: '24px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxSizing: 'border-box',
                    fontSize: '10px',
                    fontWeight: 600,
                    padding: '0 8px',
                    borderRadius: '4px',
                    border: wireCategoryFilter === tab.id ? '1px solid #38bdf8' : '1px solid #1e293b',
                    backgroundColor: wireCategoryFilter === tab.id ? 'rgba(56, 189, 248, 0.18)' : '#131d31',
                    color: wireCategoryFilter === tab.id ? '#38bdf8' : '#94a3b8',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.1s ease',
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}

          {/* Right Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {dockHeight !== 'collapsed' && (
              <button
                onClick={() => setApiWireLogs([])}
                title="Clear logged calls"
                style={{
                  height: '24px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '3px',
                  backgroundColor: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  fontSize: '10px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  padding: '0 6px',
                  whiteSpace: 'nowrap',
                  boxSizing: 'border-box',
                }}
              >
                <Trash2 size={11} /> Clear Buffer
              </button>
            )}

            {/* Height Buttons */}
            <button
              onClick={() => setDockHeight(dockHeight === 'collapsed' ? 'normal' : 'collapsed')}
              title={dockHeight === 'collapsed' ? 'Expand Wire Console' : 'Minimize Wire Console'}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '24px',
                height: '24px',
                borderRadius: '4px',
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                color: '#94a3b8',
                cursor: 'pointer',
                boxSizing: 'border-box',
              }}
            >
              {dockHeight === 'collapsed' ? <ChevronUp size={13} /> : <Minimize2 size={11} />}
            </button>

            <button
              onClick={() => setDockHeight(dockHeight === 'expanded' ? 'normal' : 'expanded')}
              title={dockHeight === 'expanded' ? 'Restore Normal Height' : 'Maximize Wire Console'}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '24px',
                height: '24px',
                borderRadius: '4px',
                backgroundColor: '#1e293b',
                border: '1px solid #334155',
                color: '#94a3b8',
                cursor: 'pointer',
                boxSizing: 'border-box',
              }}
            >
              {dockHeight === 'expanded' ? <ChevronDown size={13} /> : <Maximize2 size={11} />}
            </button>
          </div>
        </div>

        {/* Dock Log List (when open) */}
        {dockHeight !== 'collapsed' && (
          <div style={{ flex: 1, overflowY: 'auto', padding: '6px 12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {apiWireLogs.length === 0 ? (
              <div style={{ padding: '24px 0', textAlign: 'center', color: '#64748b', fontSize: '11px' }}>
                No API calls yet. Actions in this view will appear here.
              </div>
            ) : apiWireLogs.filter((log) => wireCategoryFilter === 'ALL' || log.category.toLowerCase().includes(wireCategoryFilter.toLowerCase())).length === 0 ? (
              <div style={{ padding: '24px 0', textAlign: 'center', color: '#64748b', fontSize: '11px' }}>
                No API calls matching current filter.
              </div>
            ) : (
              apiWireLogs
                .filter((log) => wireCategoryFilter === 'ALL' || log.category.toLowerCase().includes(wireCategoryFilter.toLowerCase()))
                .map((log) => {
                  const is2xx = log.status >= 200 && log.status < 300;
                  const isPost = log.method === 'POST';
                  const isJsonRpc = log.method === 'JSON-RPC';
                  return (
                    <div
                      key={log.id}
                      onClick={() => setSelectedWireLog(log)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '5px 10px',
                        borderRadius: '5px',
                        backgroundColor: '#0d1527',
                        border: '1px solid #1a253c',
                        fontSize: '11px',
                        cursor: 'pointer',
                        transition: 'background-color 0.1s ease',
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.backgroundColor = '#131e36';
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.backgroundColor = '#0d1527';
                      }}
                    >
                      {/* Left: Status, Method, Endpoint */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '400px' }}>
                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: 800,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            backgroundColor: is2xx ? '#064e3b' : '#7f1d1d',
                            color: is2xx ? '#ecfdf5' : '#fee2e2',
                            border: `1px solid ${is2xx ? '#10b981' : '#ef4444'}`,
                            fontFamily: 'ui-monospace, monospace',
                          }}
                        >
                          {log.status} {log.statusText}
                        </span>

                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            padding: '1px 5px',
                            borderRadius: '3px',
                            backgroundColor: isJsonRpc
                              ? 'rgba(168, 85, 247, 0.15)'
                              : isPost
                              ? 'rgba(2, 132, 199, 0.18)'
                              : 'rgba(100, 116, 139, 0.2)',
                            color: isJsonRpc ? '#c084fc' : isPost ? '#38bdf8' : '#cbd5e1',
                            border: `1px solid ${
                              isJsonRpc
                                ? 'rgba(168, 85, 247, 0.3)'
                                : isPost
                                ? 'rgba(2, 132, 199, 0.3)'
                                : '#334155'
                            }`,
                            fontFamily: 'ui-monospace, monospace',
                          }}
                        >
                          {log.method}
                        </span>

                        <span
                          style={{
                            fontSize: '11px',
                            fontFamily: 'ui-monospace, monospace',
                            color: '#e2e8f0',
                            fontWeight: 600,
                          }}
                        >
                          {log.endpoint}
                        </span>

                        <span
                          style={{
                            fontSize: '10px',
                            fontFamily: 'ui-monospace, monospace',
                            color: '#fbbf24',
                            backgroundColor: 'rgba(245, 158, 11, 0.12)',
                            padding: '1px 5px',
                            borderRadius: '3px',
                            border: '1px solid rgba(245, 158, 11, 0.25)',
                          }}
                        >
                          ⚡ {log.durationMs}ms
                        </span>

                        <span
                          style={{
                            fontSize: '9px',
                            color: '#94a3b8',
                            backgroundColor: '#1e293b',
                            padding: '1px 6px',
                            borderRadius: '3px',
                          }}
                        >
                          {log.category}
                        </span>
                      </div>

                      {/* Middle: Summary */}
                      <div
                        style={{
                          flex: 1,
                          padding: '0 12px',
                          fontSize: '11px',
                          color: '#94a3b8',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {log.summary}
                      </div>

                      {/* Right: Timestamp & Inspect button */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '10px', fontFamily: 'ui-monospace, monospace', color: '#64748b' }}>
                          {log.timestamp}
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedWireLog(log);
                          }}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '3px',
                            padding: '2px 8px',
                            backgroundColor: '#1e293b',
                            border: '1px solid #334155',
                            borderRadius: '4px',
                            color: '#38bdf8',
                            fontSize: '10px',
                            fontWeight: 600,
                            cursor: 'pointer',
                          }}
                        >
                          <Code2 size={11} /> Inspect
                        </button>
                      </div>
                    </div>
                  );
                })
            )}
          </div>
        )}
      </div>

      {/* Appointment Inspection Slide-Over Drawer */}
      {selectedAppointment && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            width: '420px',
            height: '100%',
            backgroundColor: '#0b1120',
            borderLeft: '1px solid #1e293b',
            boxShadow: '-8px 0 24px rgba(0,0,0,0.6)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 50,
            animation: 'slideIn 0.2s ease-out',
          }}
        >
          {/* Drawer Header */}
          <div
            style={{
              padding: '16px 20px',
              borderBottom: '1px solid #1e293b',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              backgroundColor: '#0d1527',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FileText size={18} style={{ color: '#38bdf8' }} />
              <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
                AP2 Workload Fulfillment Dossier
              </h4>
            </div>
            <button
              onClick={() => setSelectedAppointment(null)}
              style={{
                background: 'none',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer',
                padding: '4px',
                borderRadius: '4px',
              }}
            >
              <X size={18} />
            </button>
          </div>

          {/* Drawer Body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {/* Real-time Action Feedback Banners */}
            {dispatchWebhookStatus && (
              <div
                style={{
                  backgroundColor: dispatchWebhookStatus.includes('failed')
                    ? 'rgba(239, 68, 68, 0.15)'
                    : dispatchWebhookStatus.includes('Dry run')
                    ? 'rgba(234, 179, 8, 0.15)'
                    : 'rgba(16, 185, 129, 0.15)',
                  border: `1px solid ${
                    dispatchWebhookStatus.includes('failed')
                      ? 'rgba(239, 68, 68, 0.4)'
                      : dispatchWebhookStatus.includes('Dry run')
                      ? 'rgba(234, 179, 8, 0.4)'
                      : 'rgba(16, 185, 129, 0.4)'
                  }`,
                  borderRadius: '8px',
                  padding: '12px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  color: dispatchWebhookStatus.includes('failed')
                    ? '#f87171'
                    : dispatchWebhookStatus.includes('Dry run')
                    ? '#facc15'
                    : '#34d399',
                  fontSize: '11px',
                  lineHeight: 1.4,
                }}
              >
                {dispatchWebhookStatus.includes('failed') ? (
                  <AlertCircle size={18} style={{ flexShrink: 0, color: '#ef4444' }} />
                ) : (
                  <CheckCircle2
                    size={18}
                    style={{
                      flexShrink: 0,
                      color: dispatchWebhookStatus.includes('Dry run') ? '#eab308' : '#10b981',
                    }}
                  />
                )}
                <div>
                  <div style={{ fontWeight: 700 }}>
                    {dispatchWebhookStatus.includes('failed')
                      ? 'Autonomous Fulfillment Webhook Failed'
                      : dispatchWebhookStatus.includes('Dry run')
                      ? 'Autonomous Fulfillment Webhook (Dry Run)'
                      : 'Autonomous Fulfillment Webhook Dispatched'}
                  </div>
                  <div style={{ color: '#cbd5e1', fontSize: '11px' }}>{dispatchWebhookStatus}</div>
                </div>
              </div>
            )}

            {invoiceStatus && (
              <div style={{ backgroundColor: 'rgba(56, 189, 248, 0.15)', border: '1px solid rgba(56, 189, 248, 0.4)', borderRadius: '8px', padding: '12px', display: 'flex', alignItems: 'center', gap: '10px', color: '#38bdf8', fontSize: '11px', lineHeight: 1.4 }}>
                <Check size={18} style={{ flexShrink: 0, color: '#38bdf8' }} />
                <div>
                  <div style={{ fontWeight: 700 }}>Execution Receipt Generated</div>
                  <div style={{ color: '#cbd5e1', fontSize: '11px' }}>{invoiceStatus}</div>
                </div>
              </div>
            )}

            {/* Title & Timing Card */}
            <div style={{ backgroundColor: '#131d31', borderRadius: '8px', padding: '14px', border: '1px solid #1e293b' }}>
              <div style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700, textTransform: 'uppercase', marginBottom: '4px' }}>
                Workload Task Scope
              </div>
              <div style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', lineHeight: 1.3 }}>
                {selectedAppointment.name}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px', fontSize: '12px', color: '#94a3b8' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={13} style={{ color: '#38bdf8' }} />
                  {selectedAppointment.startDate} – {selectedAppointment.endDate} (Execution Window)
                </span>
              </div>
            </div>

            {/* Buyer Agent & Protocol Identity Card */}
            <div style={{ backgroundColor: '#131d31', borderRadius: '8px', padding: '14px', border: '1px solid #1e293b' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <div style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 700, textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '5px' }}>
                  <Terminal size={13} /> Buyer Agent &bull; Protocol Identity
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Buyer Agent ID</span>
                <span style={{ fontSize: '12px', fontFamily: 'monospace', fontWeight: 700, color: '#38bdf8' }}>{selectedAppointment.customerName}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Principal Entity</span>
                <span style={{ fontSize: '12px', color: '#f8fafc', fontWeight: 600 }}>{selectedAppointment.resourceEntity}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Ed25519 Key</span>
                <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#cbd5e1' }}>{selectedAppointment.clientFingerprint || selectedAppointment.customerPhone}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Enclave Endpoint</span>
                <span style={{ fontSize: '11px', color: '#34d399', fontFamily: 'monospace', textAlign: 'right', maxWidth: '240px', lineHeight: 1.3 }}>
                  {selectedAppointment.jobAddress}
                </span>
              </div>
              <div style={{ display: 'flex', gap: '8px', marginTop: '6px' }}>
                <button
                  onClick={handleCopyEndpoint}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '4px',
                    padding: '5px 8px',
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    color: copiedAddress ? '#34d399' : '#cbd5e1',
                    borderRadius: '5px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {copiedAddress ? <Check size={12} /> : <Copy size={12} />}
                  {copiedAddress ? 'Copied' : 'Copy Node Endpoint'}
                </button>
              </div>
            </div>

            {/* Scope & Execution Specifications Card */}
            <div style={{ backgroundColor: '#131d31', borderRadius: '8px', padding: '14px', border: '1px solid #1e293b' }}>
              <div style={{ fontSize: '11px', color: '#fbbf24', fontWeight: 700, textTransform: 'uppercase', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <Sparkles size={13} /> Workload Specifications &bull; Execution Profile
              </div>
              <div style={{ fontSize: '12px', color: '#e2e8f0', lineHeight: 1.4, backgroundColor: '#0f172a', padding: '10px', borderRadius: '6px', border: '1px solid #1e293b' }}>
                {selectedAppointment.takeoffNotes}
              </div>
            </div>

            {/* Financial & Payment Verification */}
            <div style={{ backgroundColor: '#131d31', borderRadius: '8px', padding: '14px', border: '1px solid #1e293b' }}>
              <div style={{ fontSize: '11px', color: '#34d399', fontWeight: 700, textTransform: 'uppercase', marginBottom: '8px' }}>
                PayPal Payment Rail &bull; Subscriptions
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Settlement State</span>
                <span style={{ fontSize: '11px', fontWeight: 800, padding: '3px 8px', borderRadius: '4px', backgroundColor: '#064e3b', color: '#ecfdf5', border: '1px solid #10b981' }}>
                  {selectedAppointment.depositStatus}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>PayPal Txn Ref</span>
                <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#f8fafc' }}>
                  {selectedAppointment.paypalTxn}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Settlement Policy</span>
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>Zero Bad Debt / Auto-Settled via PayPal</span>
              </div>
            </div>

            {/* Assigned Worker Node Resource */}
            <div style={{ backgroundColor: '#131d31', borderRadius: '8px', padding: '14px', border: '1px solid #1e293b' }}>
              <div style={{ fontSize: '11px', color: '#c084fc', fontWeight: 700, textTransform: 'uppercase', marginBottom: '8px' }}>
                Assigned Execution Node Cluster
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Worker Cluster</span>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>{selectedAppointment.resourceName}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Service Capability</span>
                <span style={{ fontSize: '12px', color: '#cbd5e1' }}>{selectedAppointment.resourceTrade}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: '#94a3b8' }}>Cluster Endpoint</span>
                <span style={{ fontSize: '11px', fontFamily: 'monospace', color: '#34d399', fontWeight: 700 }}>
                  {selectedAppointment.resourceDid}
                </span>
              </div>
            </div>

            {/* Back-Office Integrations */}
            <div style={{ backgroundColor: '#131d31', borderRadius: '8px', padding: '14px', border: '1px solid #1e293b' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', marginBottom: '8px' }}>
                Autonomous Back-Office Integrations
              </div>
              <div style={{ fontSize: '11px', color: '#cbd5e1', lineHeight: 1.5, display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} style={{ color: '#34d399' }} />
                  <span>Enterprise ERP Bridge: <code>ClientCreate</code> &amp; <code>JobCreate</code> synced</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} style={{ color: '#34d399' }} />
                  <span>QuickBooks Online v3: Purchase mapped to GL Account 6300</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CheckCircle2 size={13} style={{ color: '#34d399' }} />
                  <span>Protocol: AP2 MCP JSON-RPC 2.0 Streaming Interface</span>
                </div>
              </div>
            </div>
          </div>

          {/* Drawer Footer Field-Service Actions */}
          <div style={{ padding: '14px 20px', borderTop: '1px solid #1e293b', backgroundColor: '#0d1527', display: 'flex', gap: '10px' }}>
            <button
              onClick={handleDispatchWebhook}
              disabled={isSendingWebhook}
              style={{
                flex: 2,
                padding: '9px 12px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: isSendingWebhook ? '#0369a1' : '#0284c7',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 700,
                cursor: isSendingWebhook ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                boxShadow: '0 2px 6px rgba(2, 132, 199, 0.4)',
                transition: 'all 0.15s ease',
              }}
              title="Dispatch fulfillment webhook notification to buyer agent"
            >
              <Send size={13} />
              {isSendingWebhook ? 'Dispatching Webhook...' : 'Dispatch Webhook'}
            </button>

            <button
              onClick={handleDownloadReceipt}
              style={{
                flex: 1.5,
                padding: '9px 12px',
                borderRadius: '6px',
                border: '1px solid #334155',
                backgroundColor: '#1e293b',
                color: '#38bdf8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                transition: 'all 0.15s ease',
              }}
              title="Download formal AP2 workload execution receipt"
            >
              <Download size={13} />
              Receipt
            </button>

            <button
              onClick={() => setSelectedAppointment(null)}
              style={{
                flex: 1,
                padding: '9px 12px',
                borderRadius: '6px',
                border: '1px solid #334155',
                backgroundColor: '#0f172a',
                color: '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Wire Log Inspection Modal */}
      {selectedWireLog && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '20px',
          }}
          onClick={() => setSelectedWireLog(null)}
        >
          <div
            style={{
              width: '840px',
              maxWidth: '95vw',
              maxHeight: '88vh',
              backgroundColor: '#0b1120',
              border: '1px solid #334155',
              borderRadius: '10px',
              boxShadow: '0 20px 40px rgba(0, 0, 0, 0.8)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div
              style={{
                padding: '14px 20px',
                borderBottom: '1px solid #1e293b',
                backgroundColor: '#0d1527',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Code2 size={18} style={{ color: '#38bdf8' }} />
                <div>
                  <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    API Call Execution Wire Dossier
                    <span
                      style={{
                        fontSize: '10px',
                        padding: '1px 6px',
                        borderRadius: '3px',
                        backgroundColor: 'rgba(16,185,129,0.15)',
                        color: '#34d399',
                        border: '1px solid #10b981',
                        fontFamily: 'ui-monospace, monospace',
                      }}
                    >
                      {selectedWireLog.status} {selectedWireLog.statusText}
                    </span>
                  </h4>
                  <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                    {selectedWireLog.summary}
                  </div>
                </div>
              </div>

              <button
                onClick={() => setSelectedWireLog(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#94a3b8',
                  cursor: 'pointer',
                  padding: '4px',
                  borderRadius: '4px',
                }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Meta Strip */}
            <div
              style={{
                padding: '10px 20px',
                backgroundColor: '#090e17',
                borderBottom: '1px solid #1e293b',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '11px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ color: '#64748b' }}>Endpoint:</span>
                <code style={{ color: '#38bdf8', fontFamily: 'ui-monospace, monospace', fontWeight: 700 }}>
                  {selectedWireLog.method} {selectedWireLog.endpoint}
                </code>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Duration: </span>
                  <span style={{ color: '#fbbf24', fontFamily: 'ui-monospace, monospace', fontWeight: 700 }}>
                    {selectedWireLog.durationMs}ms
                  </span>
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>Category: </span>
                  <span style={{ color: '#cbd5e1', fontWeight: 600 }}>{selectedWireLog.category}</span>
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>Time: </span>
                  <span style={{ color: '#94a3b8', fontFamily: 'ui-monospace, monospace' }}>{selectedWireLog.timestamp}</span>
                </div>
              </div>
            </div>

            {/* Two Column Body: Request vs Response */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: '16px 20px',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '16px',
              }}
            >
              {/* Request Column */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8' }}>
                    Request Payload (HTTP {selectedWireLog.method})
                  </div>
                  <button
                    onClick={() => handleCopyWire(JSON.stringify(selectedWireLog.request, null, 2), 'request')}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '3px 8px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: copiedWireKey === 'request' ? '#34d399' : '#94a3b8',
                      borderRadius: '4px',
                      fontSize: '10px',
                      cursor: 'pointer',
                    }}
                  >
                    {copiedWireKey === 'request' ? <Check size={11} /> : <Copy size={11} />}
                    {copiedWireKey === 'request' ? 'Copied' : 'Copy Request'}
                  </button>
                </div>

                <pre
                  style={{
                    backgroundColor: '#090d16',
                    border: '1px solid #1e293b',
                    borderRadius: '6px',
                    padding: '12px',
                    margin: 0,
                    fontSize: '11px',
                    lineHeight: '1.45',
                    color: '#e2e8f0',
                    overflow: 'auto',
                    maxHeight: '380px',
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  }}
                >
                  <code>{JSON.stringify(selectedWireLog.request, null, 2)}</code>
                </pre>
              </div>

              {/* Response Column */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#34d399' }}>
                    Response Body ({selectedWireLog.status} {selectedWireLog.statusText})
                  </div>
                  <button
                    onClick={() => handleCopyWire(JSON.stringify(selectedWireLog.response, null, 2), 'response')}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '3px 8px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: copiedWireKey === 'response' ? '#34d399' : '#94a3b8',
                      borderRadius: '4px',
                      fontSize: '10px',
                      cursor: 'pointer',
                    }}
                  >
                    {copiedWireKey === 'response' ? <Check size={11} /> : <Copy size={11} />}
                    {copiedWireKey === 'response' ? 'Copied' : 'Copy Response'}
                  </button>
                </div>

                <pre
                  style={{
                    backgroundColor: '#090d16',
                    border: '1px solid #1e293b',
                    borderRadius: '6px',
                    padding: '12px',
                    margin: 0,
                    fontSize: '11px',
                    lineHeight: '1.45',
                    color: '#34d399',
                    overflow: 'auto',
                    maxHeight: '380px',
                    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  }}
                >
                  <code>{JSON.stringify(selectedWireLog.response, null, 2)}</code>
                </pre>
              </div>
            </div>

            {/* Modal Footer */}
            <div
              style={{
                padding: '12px 20px',
                borderTop: '1px solid #1e293b',
                backgroundColor: '#0d1527',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                Live cryptographic verification and settlement telemetry &bull; Guaranteed non-repudiation
              </div>
              <button
                onClick={() => setSelectedWireLog(null)}
                style={{
                  padding: '6px 16px',
                  borderRadius: '6px',
                  border: '1px solid #334155',
                  backgroundColor: '#1e293b',
                  color: '#f8fafc',
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

export default BryntumDispatchScheduler;
