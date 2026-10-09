import { useState, useMemo, useRef } from 'react';
import {
  ShieldCheck,
  CreditCard,
  TrendingUp,
  Search,
  Download,
  RefreshCw,
  Copy,
  Check,
  ExternalLink,
  Layers,
  CheckCircle2,
  Eye,
  Zap,
  X,
  FileText,
  Cpu,
  ShieldAlert,
  Sparkles,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { AdversarialTamperModal } from './AdversarialTamperModal';
import { AgStudioReportStudio } from './AgStudioReportStudio';
import { AgGridReact } from 'ag-grid-react';
import {
  ModuleRegistry as GridModuleRegistry,
  AllCommunityModule as AllGridCommunityModule,
  themeQuartz,
  type ColDef,
  type ICellRendererParams,
} from 'ag-grid-community';
import { AgCharts } from 'ag-charts-react';
import {
  ModuleRegistry as ChartModuleRegistry,
  AllCommunityModule as AllChartCommunityModule,
  type AgChartOptions,
} from 'ag-charts-community';

// Register AG Grid & AG Charts Community Modules
GridModuleRegistry.registerModules([AllGridCommunityModule]);
ChartModuleRegistry.registerModules([AllChartCommunityModule]);

import {
  type A2aTransaction,
  type TradeImpact,
  type KycAuditRecord,
} from '../data/telemetryData';

// Edward Tufte Data-to-Ink Ratio Sparkline
function Sparkline({
  data,
  color = '#38bdf8',
  height = 24,
  width = 76,
}: {
  data: number[];
  color?: string;
  height?: number;
  width?: number;
}) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data
    .map((val, idx) => {
      const x = (idx / (data.length - 1)) * (width - 8) + 4;
      const y = height - 4 - ((val - min) / range) * (height - 8) + 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const lastPoint = points.split(' ').pop()?.split(',');
  const [lastX, lastY] = lastPoint ? [parseFloat(lastPoint[0]), parseFloat(lastPoint[1])] : [0, 0];

  return (
    <svg width={width} height={height} style={{ overflow: 'visible', display: 'inline-block' }}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
      <circle cx={lastX} cy={lastY} r="2.5" fill={color} />
    </svg>
  );
}

export interface EnterpriseFleetLedgerProps {
  transactions: A2aTransaction[];
  tradeImpactData: TradeImpact[];
  kycAuditData: KycAuditRecord[];
  studioData?: any;
  studioMode?: any;
  onSetStudioMode?: (mode: any) => void;
  onSimulateClick: () => void;
  onInspectTrace?: (transactionId: string) => void;
  onNavigateTab?: (tab: 'copilot' | 'fleet-ledger' | 'ag-studio' | 'bryntum' | 'zapier') => void;
  onRefreshData?: () => Promise<void>;
  viewMode?: 'grid' | 'studio';
  onViewModeChange?: (mode: 'grid' | 'studio') => void;
  isTopMetricsCollapsed?: boolean;
  onToggleTopMetrics?: () => void;
}

export function EnterpriseFleetLedger({
  transactions,
  tradeImpactData,
  kycAuditData: _kycAuditData,
  studioData,
  studioMode,
  onSetStudioMode,
  onSimulateClick,
  onInspectTrace,
  onNavigateTab,
  onRefreshData,
  viewMode,
  onViewModeChange: _onViewModeChange,
  isTopMetricsCollapsed: propIsTopMetricsCollapsed,
  onToggleTopMetrics: _onToggleTopMetrics,
}: EnterpriseFleetLedgerProps) {
  const [internalIsTopMetricsCollapsed] = useState(true);
  const isTopMetricsCollapsed = propIsTopMetricsCollapsed ?? internalIsTopMetricsCollapsed;
  const [internalViewMode] = useState<'grid' | 'studio'>('grid');
  const currentViewMode = viewMode ?? internalViewMode;
  const [isFunnelCollapsed, setIsFunnelCollapsed] = useState(false);

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedTrade, setSelectedTrade] = useState<string>('ALL');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Selected transaction for the Slide-Over Inspection Drawer
  const [selectedTxn, setSelectedTxn] = useState<A2aTransaction | null>(null);
  const [drawerTab, setDrawerTab] = useState<'audit' | 'raw'>('audit');
  const [showTamperModal, setShowTamperModal] = useState(false);

  // Copy helper
  const handleCopy = (text: string, key: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  // Live refresh: synchronizes with backend via onRefreshData
  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      if (onRefreshData) {
        await onRefreshData();
      }
    } finally {
      setTimeout(() => setIsRefreshing(false), 500);
    }
  };

  // Grid Ref for AG Grid API calls
  const gridRef = useRef<AgGridReact<A2aTransaction>>(null);

  // Export CSV using AG Grid's native CSV export with fallback
  const handleExportCsv = () => {
    if (gridRef.current?.api) {
      gridRef.current.api.exportDataAsCsv({
        fileName: `ap2_seller_operations_ledger_${new Date().toISOString().slice(0, 10)}.csv`,
      });
      return;
    }

    const headers = [
      'Protocol Txn ID',
      'Timestamp',
      'Buyer Agent ID',
      'Principal Entity',
      'Service Capability',
      'Service Plan Tier',
      'Monthly Amount ($)',
      'PayPal Subscription ID',
      'Execution Node Endpoint',
      'Anti-Tamper & Spending Guard',
      'Cryptographic Attestation',
      'Fulfillment State',
    ];

    const rows = transactions.map((t) => [
      t.id,
      t.timestamp,
      t.buyer_agent || t.contractor_name,
      t.principal_entity || t.kyc_legal_entity,
      t.trade_vertical,
      t.service_plan,
      t.monthly_amount.toFixed(2),
      t.paypal_sub_id,
      t.allocated_did,
      t.tcpa_guard,
      t.kyc_status,
      t.status,
    ]);

    const csvContent =
      'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map((e) => e.map((val) => `"${val}"`).join(','))].join('\n');

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `ap2_seller_operations_ledger_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // AG Grid Quartz Dark Theme Configuration
  const agGridDarkTheme = useMemo(() => {
    return themeQuartz.withParams({
      backgroundColor: '#0f172a',
      foregroundColor: '#f8fafc',
      headerBackgroundColor: '#131e32',
      headerTextColor: '#94a3b8',
      headerFontSize: 11,
      headerFontWeight: 700,
      borderColor: '#1e293b',
      rowHoverColor: 'rgba(30, 41, 59, 0.6)',
      accentColor: '#38bdf8',
      fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      fontSize: 12,
    });
  }, []);

  // AG Grid Column Definitions
  const colDefs = useMemo<ColDef<A2aTransaction>[]>(
    () => [
      {
        field: 'id',
        headerName: 'Protocol Txn ID',
        width: 165,
        pinned: 'left',
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          return (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontFamily: 'monospace', fontWeight: 600, color: '#38bdf8' }}>
                <span>{t.id}</span>
                <button
                  onClick={() => handleCopy(t.id, t.id)}
                  style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0 }}
                  title="Copy Transaction ID"
                >
                  {copiedKey === t.id ? <Check size={12} color="#34d399" /> : <Copy size={12} />}
                </button>
              </div>
              <div style={{ fontSize: '10px', color: '#64748b', lineHeight: 1 }}>
                {t.timestamp ? `${t.timestamp.slice(5, 10)} ${t.timestamp.slice(11, 16)} UTC` : ''}
              </div>
            </div>
          );
        },
      },
      {
        field: 'status',
        headerName: 'Fulfillment State',
        width: 165,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          const isActive = t.status === 'ACTIVE_STREAMING';
          return (
            <div style={{ display: 'flex', alignItems: 'center', height: '100%' }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '3px 8px',
                  borderRadius: '9999px',
                  fontSize: '10px',
                  fontWeight: 700,
                  backgroundColor: isActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                  color: isActive ? '#34d399' : '#fbbf24',
                  border: `1px solid ${isActive ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
                }}
              >
                <span
                  style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    backgroundColor: isActive ? '#10b981' : '#f59e0b',
                  }}
                />
                {isActive ? 'Active' : 'Awaiting approval'}
              </span>
            </div>
          );
        },
      },
      {
        field: 'buyer_agent',
        headerName: 'Buyer Agent & Principal Entity',
        flex: 1.5,
        minWidth: 260,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          const buyer = t.buyer_agent || t.contractor_name;
          const principal = t.principal_entity || t.kyc_legal_entity;
          return (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontWeight: 700, color: '#38bdf8', fontFamily: 'monospace', fontSize: '11px' }}>
                {buyer}
              </div>
              <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: 1.2 }}>{principal}</div>
            </div>
          );
        },
      },
      {
        field: 'trade_vertical',
        headerName: 'Service Capability',
        width: 210,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          return (
            <div style={{ display: 'flex', alignItems: 'center', height: '100%' }}>
              <span style={{ fontSize: '11px', fontWeight: 600, backgroundColor: 'rgba(56, 189, 248, 0.1)', border: '1px solid rgba(56, 189, 248, 0.25)', color: '#38bdf8', padding: '3px 8px', borderRadius: '6px' }}>
                {t.trade_vertical}
              </span>
            </div>
          );
        },
      },
      {
        field: 'allocated_did',
        headerName: 'Execution Node Endpoint',
        flex: 1.2,
        minWidth: 230,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          const isActive = t.status === 'ACTIVE_STREAMING';
          return (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              {isActive ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <strong style={{ color: '#34d399', fontFamily: 'monospace', fontSize: '11px' }}>{t.allocated_did}</strong>
                  <button
                    onClick={() => handleCopy(t.allocated_did, t.allocated_did)}
                    style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0 }}
                    title="Copy Node Endpoint"
                  >
                    {copiedKey === t.allocated_did ? <Check size={12} color="#34d399" /> : <Copy size={12} />}
                  </button>
                </div>
              ) : (
                <span style={{ color: '#64748b', fontSize: '13px', fontWeight: 600 }}>—</span>
              )}
            </div>
          );
        },
      },
      {
        field: 'monthly_amount',
        headerName: 'Monthly Rate & Settlement Rail',
        width: 175,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          return (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontWeight: 700, color: '#f8fafc' }}>
                ${t.monthly_amount.toFixed(2)}
                <span style={{ fontSize: '10px', color: '#94a3b8' }}>/mo</span>
              </div>
              <div style={{ fontSize: '10px', color: '#38bdf8', fontFamily: 'monospace', lineHeight: 1 }}>
                {t.paypal_sub_id.startsWith('I-') ? t.paypal_sub_id : 'Pre-Debit Token'}
              </div>
            </div>
          );
        },
      },
      {
        headerName: 'Action',
        width: 105,
        sortable: false,
        filter: false,
        pinned: 'right',
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', height: '100%' }}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedTxn(t);
                }}
                style={{
                  backgroundColor: '#0284c7',
                  border: '1px solid #0369a1',
                  color: '#ffffff',
                  padding: '4px 8px',
                  borderRadius: '5px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
                title="Inspect buyer mandate and cryptographic proof"
              >
                <Eye size={11} /> Inspect
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (onNavigateTab) {
                    onNavigateTab('copilot');
                  }
                  if (onInspectTrace) {
                    onInspectTrace(t.id);
                  }
                }}
                style={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  color: '#38bdf8',
                  padding: '4px 8px',
                  borderRadius: '5px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
                title="Inspect machine-to-machine execution trace in Copilot"
              >
                Trace <ExternalLink size={11} />
              </button>
            </div>
          );
        },
      },
    ],
    [copiedKey, onInspectTrace, onNavigateTab]
  );

  // Dynamic Trade GMV computed from live active transactions sorted Batch -> Gateway -> Cluster
  const dynamicTradeData = useMemo(() => {
    const tradeGmvMap: Record<string, number> = {};
    transactions.forEach((t) => {
      if (t.status === 'ACTIVE_STREAMING') {
        const key = t.trade_vertical;
        tradeGmvMap[key] = (tradeGmvMap[key] || 0) + (t.monthly_amount || 0) * 12;
      }
    });

    const tierOrderWeights: Record<string, number> = {
      'High-Throughput Batch Worker': 1,
      'Dedicated AI Service Gateway': 2,
      'Enterprise Cluster Node': 3,
      'Autonomous Security Audit Cluster': 3,
    };

    return tradeImpactData
      .map((d) => {
        const liveGmv = tradeGmvMap[d.trade];
        const gmv = liveGmv !== undefined ? liveGmv : (d.annualized_gmv ?? d.recovered_revenue ?? 0);
        return {
          trade: d.trade,
          gmv: Math.round(gmv * 100) / 100,
        };
      })
      .sort((a, b) => (tierOrderWeights[a.trade] || 99) - (tierOrderWeights[b.trade] || 99));
  }, [transactions, tradeImpactData]);

  // AG Charts: Autonomous AP2 Commerce Volume by Capability
  const tradeChartOptions: AgChartOptions = useMemo(
    () => ({
      theme: 'ag-default-dark',
      data: dynamicTradeData,
      series: [
        {
          type: 'bar',
          direction: 'horizontal',
          xKey: 'trade',
          yKey: 'gmv',
          yName: 'ARR ($)',
          cornerRadius: 4,
          fill: '#0284c7',
          strokeWidth: 0,
          label: {
            enabled: true,
            placement: 'outside',
            formatter: (params: any) => `$${Math.round(params.value).toLocaleString()}`,
            color: '#cbd5e1',
            fontSize: 11,
          },
        } as any,
      ],
      background: {
        fill: 'transparent',
      },
      axes: {
        x: {
          type: 'category',
          position: 'left',
        },
        y: {
          type: 'number',
          position: 'bottom',
          label: {
            formatter: (params: any) => {
              const v = params.value;
              if (v === 0) return '$0';
              return `$${Math.round(v / 1000)}k`;
            },
          },
        },
      } as any,
    }),
    [dynamicTradeData]
  );

  // Dynamic metrics computed from real state
  const totalMrr = useMemo(() => {
    return transactions.reduce((acc, t) => acc + (t.status === 'ACTIVE_STREAMING' ? t.monthly_amount : 0), 0);
  }, [transactions]);

  const activeLinesCount = useMemo(() => {
    return transactions.filter((t) => t.status === 'ACTIVE_STREAMING').length;
  }, [transactions]);

  const totalAutonomousGmv = useMemo(() => {
    return dynamicTradeData.reduce((acc, d) => acc + d.gmv, 0);
  }, [dynamicTradeData]);

  // Dynamic histories computed from real transactions (ADR-079)
  const mrrHistory = useMemo(() => {
    if (!transactions.length) return [];
    const sorted = [...transactions].sort((a, b) => (a.timestamp > b.timestamp ? 1 : -1));
    let running = 0;
    return sorted.map((t) => {
      if (t.status === 'ACTIVE_STREAMING') running += t.monthly_amount;
      return running;
    });
  }, [transactions]);

  const activeNodesHistory = useMemo(() => {
    if (!transactions.length) return [];
    const sorted = [...transactions].sort((a, b) => (a.timestamp > b.timestamp ? 1 : -1));
    let count = 0;
    return sorted.map((t) => {
      if (t.status === 'ACTIVE_STREAMING') count += 1;
      return count;
    });
  }, [transactions]);

  const gmvHistory = useMemo(() => {
    if (!transactions.length) return [];
    const sorted = [...transactions].sort((a, b) => (a.timestamp > b.timestamp ? 1 : -1));
    let running = 0;
    return sorted.map((t) => {
      if (t.status === 'ACTIVE_STREAMING') running += (t.monthly_amount * 12);
      return running;
    });
  }, [transactions]);

  const quarantinedCount = useMemo(() => {
    return transactions.filter(
      (t) => t.status === 'QUARANTINED' || t.status === 'TAMPER_DETECTED' || t.status === 'REJECTED'
    ).length;
  }, [transactions]);

  const starterTierTransactions = useMemo(() => {
    return transactions.filter(
      (t) => (t.monthly_amount === 49.99 || t.service_plan?.includes('49.99')) && t.status === 'ACTIVE_STREAMING'
    );
  }, [transactions]);

  const mrrPreserved = useMemo(() => {
    return starterTierTransactions.reduce((acc, t) => acc + t.monthly_amount, 0);
  }, [starterTierTransactions]);

  // Dynamic 5-Step Funnel Metrics derived directly from AP2 transactions (Claude verification)
  const funnelMetrics = useMemo(() => {
    // Instant approvals: full-price tiers ($79.99 Gateway, $179.99 Cluster) that auto-approved
    const instantApprovals = transactions.filter(
      (t) => t.monthly_amount > 49.99 && t.status === 'ACTIVE_STREAMING'
    ).length;

    // Counter-offers won: $49.99 Batch inquiries converted to active streaming
    const counterOffersWon = starterTierTransactions.length;

    // Pending inquiries: subscriptions awaiting authorization/token (TXN-AP2-9021)
    const pendingInquiries = transactions.filter((t) => t.status !== 'ACTIVE_STREAMING').length;

    // Hard floor block: inquiries with spending cap below $49.99 starter floor (Demo data benchmark)
    const hardFloorBlocks = 2;

    const totalInquiries = instantApprovals + counterOffersWon + pendingInquiries + hardFloorBlocks;
    const instantApprovalPct = totalInquiries > 0 ? ((instantApprovals / totalInquiries) * 100).toFixed(0) : '0';
    const counterOffersWonPct = totalInquiries > 0 ? ((counterOffersWon / totalInquiries) * 100).toFixed(0) : '0';
    const pendingPct = totalInquiries > 0 ? ((pendingInquiries / totalInquiries) * 100).toFixed(0) : '0';
    const hardFloorPct = totalInquiries > 0 ? ((hardFloorBlocks / totalInquiries) * 100).toFixed(0) : '0';

    const instantWidth = totalInquiries > 0 ? `${((instantApprovals / totalInquiries) * 100).toFixed(2)}%` : '0%';
    const counterWidth = totalInquiries > 0 ? `${((counterOffersWon / totalInquiries) * 100).toFixed(2)}%` : '0%';
    const pendingWidth = totalInquiries > 0 ? `${((pendingInquiries / totalInquiries) * 100).toFixed(2)}%` : '0%';
    const floorWidth = totalInquiries > 0 ? `${((hardFloorBlocks / totalInquiries) * 100).toFixed(2)}%` : '0%';

    return {
      totalInquiries,
      instantApprovals,
      instantApprovalPct,
      instantWidth,
      counterOffersWon,
      counterOffersWonPct,
      counterWidth,
      pendingInquiries,
      pendingPct,
      pendingWidth,
      hardFloorBlocks,
      hardFloorPct,
      floorWidth,
    };
  }, [transactions, starterTierTransactions]);

  const topCapability = useMemo(() => {
    if (!dynamicTradeData || dynamicTradeData.length === 0) return null;
    const sorted = [...dynamicTradeData].sort((a, b) => b.gmv - a.gmv);
    const top = sorted[0];
    if (!top || top.gmv === 0) return null;
    const agentCount = transactions.filter(
      (t) => (t.trade_vertical || '').toLowerCase() === top.trade.toLowerCase() && t.status === 'ACTIVE_STREAMING'
    ).length;
    return {
      name: top.trade,
      gmv: top.gmv,
      agentCount,
    };
  }, [dynamicTradeData, transactions]);

  // Subscription Tier Distribution computed on active transactions (Batch 4 [31%], Gateway 6 [46%], Cluster 3 [23%])
  const tierDistribution = useMemo(() => {
    const activeTxns = transactions.filter((t) => t.status === 'ACTIVE_STREAMING');
    const totalCount = activeTxns.length || 1;

    const tierMap: Record<string, { tier: string; shortName: string; count: number; mrr: number; sortOrder: number }> = {
      'High-Throughput Batch Worker': { tier: 'High-Throughput Batch Worker', shortName: 'Batch', count: 0, mrr: 0, sortOrder: 1 },
      'Dedicated AI Service Gateway': { tier: 'Dedicated AI Service Gateway', shortName: 'Gateway', count: 0, mrr: 0, sortOrder: 2 },
      'Enterprise Cluster Node': { tier: 'Enterprise Cluster Node', shortName: 'Cluster', count: 0, mrr: 0, sortOrder: 3 },
    };

    activeTxns.forEach((t) => {
      let cap = t.trade_vertical || '';
      if (!tierMap[cap]) {
        if (t.monthly_amount === 49.99 || cap.toLowerCase().includes('batch')) cap = 'High-Throughput Batch Worker';
        else if (t.monthly_amount === 179.99 || cap.toLowerCase().includes('cluster')) cap = 'Enterprise Cluster Node';
        else cap = 'Dedicated AI Service Gateway';
      }
      tierMap[cap].count += 1;
      tierMap[cap].mrr = Math.round((tierMap[cap].mrr + t.monthly_amount) * 100) / 100;
    });

    return Object.values(tierMap)
      .sort((a, b) => a.sortOrder - b.sortOrder)
      .map((item) => {
        const pct = Math.round((item.count / totalCount) * 100);
        return {
          tier: item.tier,
          count: item.count,
          mrr: item.mrr,
          percentage: `${pct}%`,
          label: `${item.shortName} · ${item.count} (${pct}%)`,
        };
      });
  }, [transactions]);

  // AG Charts: Subscription Tier & Capability Fleet Distribution Donut Chart
  const tierChartOptions: AgChartOptions = useMemo(
    () => ({
      theme: 'ag-default-dark',
      data: tierDistribution,
      series: [
        {
          type: 'donut',
          angleKey: 'count',
          legendItemKey: 'label',
          innerRadiusRatio: 0.65,
          fills: ['#0284c7', '#199e70', '#8b5cf6'],
          strokes: ['#070d1a', '#070d1a', '#070d1a'],
          strokeWidth: 2,
          cornerRadius: 4,
          sectorSpacing: 3,
          sectorLabel: { enabled: false },
          calloutLabel: { enabled: false },
          innerLabels: [
            {
              text: `${activeLinesCount} Active Subscriptions`,
              fontSize: 14,
              fontWeight: 'bold',
              color: '#f8fafc',
            },
            {
              text: `$${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mo MRR`,
              fontSize: 11,
              color: '#38bdf8',
            },
          ],
        } as any,
      ],
      background: {
        fill: 'transparent',
      },
      legend: {
        position: 'right',
        item: {
          label: {
            color: '#cbd5e1',
            fontSize: 11,
          },
        },
      } as any,
    }),
    [tierDistribution, totalMrr, activeLinesCount]
  );

  // Filtered transactions for the ledger grid
  const filteredTransactions = useMemo(() => {
    return transactions.filter((t) => {
      const buyer = t.buyer_agent || t.contractor_name || '';
      const principal = t.principal_entity || t.kyc_legal_entity || '';
      const matchesSearch =
        searchTerm === '' ||
        buyer.toLowerCase().includes(searchTerm.toLowerCase()) ||
        principal.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.allocated_did.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.paypal_sub_id.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesStatus =
        selectedStatus === 'ALL' ||
        (selectedStatus === 'ACTIVE' && t.status === 'ACTIVE_STREAMING') ||
        (selectedStatus === 'PENDING' && t.status === 'PENDING_DEPOSIT');

      const matchesTrade =
        selectedTrade === 'ALL' || t.trade_vertical.toLowerCase().includes(selectedTrade.toLowerCase());

      return matchesSearch && matchesStatus && matchesTrade;
    });
  }, [transactions, searchTerm, selectedStatus, selectedTrade]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: '#080d1a', color: '#f8fafc', overflowY: 'auto', padding: '12px 16px', gap: '12px' }}>
      {/* 1. EXPANDED 4 KPI METRIC CARDS (Hidden when collapsed) */}
      {!isTopMetricsCollapsed && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', flexShrink: 0 }}>
          {/* Card 1: Active Protocol MRR */}
          <div
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '10px',
                padding: '12px 16px',
                boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em', color: '#94a3b8', textTransform: 'uppercase' }}>
                    Active Protocol MRR
                  </span>
                  <div style={{ width: '24px', height: '24px', borderRadius: '6px', backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#38bdf8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <CreditCard size={13} />
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '6px' }}>
                  <div>
                    <div style={{ fontSize: '22px', fontWeight: 800, color: '#f8fafc', lineHeight: 1.1 }}>
                      ${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      <span style={{ fontSize: '11px', fontWeight: 500, color: '#64748b' }}>/mo</span>
                    </div>
                    <div style={{ fontSize: '10px', color: '#34d399', fontWeight: 600, marginTop: '3px', display: 'flex', alignItems: 'center', gap: '4px', whiteSpace: 'nowrap' }}>
                      <TrendingUp size={12} /> {activeLinesCount} Active Subscribed Nodes
                    </div>
                  </div>
                  <div style={{ paddingBottom: '2px' }}>
                    <Sparkline data={mrrHistory} color="#38bdf8" />
                  </div>
                </div>
              </div>

              {/* Card 2: Connected Buyer Agents */}
              <div
                style={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: '10px',
                  padding: '12px 16px',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em', color: '#94a3b8', textTransform: 'uppercase' }}>
                    Connected Buyer Agents
                  </span>
                  <div style={{ width: '24px', height: '24px', borderRadius: '6px', backgroundColor: 'rgba(16, 185, 129, 0.12)', color: '#34d399', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Cpu size={13} />
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '6px' }}>
                  <div>
                    <div style={{ fontSize: '22px', fontWeight: 800, color: '#f8fafc', lineHeight: 1.1 }}>
                      {activeLinesCount} Agents
                    </div>
                    <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '3px', whiteSpace: 'nowrap' }}>
                      Ed25519 Verified &bull; RFC 8032 Bound
                    </div>
                  </div>
                  <div style={{ paddingBottom: '2px' }}>
                    <Sparkline data={activeNodesHistory} color="#34d399" />
                  </div>
                </div>
              </div>

              {/* Card 3: Anti-Tamper & Cryptographic Trust */}
              <div
                style={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: '10px',
                  padding: '12px 16px',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em', color: '#94a3b8', textTransform: 'uppercase' }}>
                    Anti-Tamper &amp; Crypto Trust
                  </span>
                  <button
                    onClick={() => setShowTamperModal(true)}
                    style={{
                      backgroundColor: 'rgba(239, 68, 68, 0.15)',
                      border: '1px solid rgba(239, 68, 68, 0.35)',
                      color: '#f87171',
                      borderRadius: '5px',
                      padding: '2px 6px',
                      fontSize: '10px',
                      fontWeight: 700,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '3px',
                    }}
                    title="Launch Adversarial Tamper Sandbox"
                  >
                    <ShieldAlert size={11} /> Sandbox
                  </button>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '6px' }}>
                  <div>
                    <div style={{ fontSize: '22px', fontWeight: 800, color: '#34d399', lineHeight: 1.1 }}>
                      100% Ed25519
                    </div>
                    <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '3px', whiteSpace: 'nowrap' }}>
                      {activeLinesCount} Enclaves Bound &bull;{' '}
                      {quarantinedCount > 0 ? (
                        <span style={{ color: '#f87171', fontWeight: 600 }}>{quarantinedCount} Quarantined</span>
                      ) : (
                        <span style={{ color: '#34d399', fontWeight: 600 }}>0 Quarantined (Secure)</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Card 4: Annualized AP2 GMV (ARR) */}
              <div
                style={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: '10px',
                  padding: '12px 16px',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em', color: '#94a3b8', textTransform: 'uppercase' }}>
                    Annualized AP2 GMV (ARR)
                  </span>
                  <div style={{ width: '24px', height: '24px', borderRadius: '6px', backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#38bdf8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Zap size={13} />
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '6px', gap: '8px' }}>
                  <div style={{ overflow: 'hidden' }}>
                    <div style={{ fontSize: '22px', fontWeight: 800, color: '#f8fafc', lineHeight: 1.1 }}>
                      ${totalAutonomousGmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <div style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 600, marginTop: '3px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {activeLinesCount} Nodes &bull; PayPal Vault
                    </div>
                  </div>
                  <div style={{ paddingBottom: '2px', flexShrink: 0 }}>
                    <Sparkline data={gmvHistory} color="#a78bfa" width={64} />
                  </div>
                </div>
              </div>
            </div>
          )}

      {currentViewMode === 'studio' ? (
        <div style={{ flex: 1, minHeight: 'calc(100vh - 140px)', width: '100%' }}>
          <AgStudioReportStudio
            studioData={studioData}
            studioMode={studioMode ?? 'view'}
            onSetStudioMode={onSetStudioMode ?? (() => {})}
            transactions={transactions}
            onSimulateClick={onSimulateClick}
            onNavigateTab={onNavigateTab}
          />
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* 1.5 AUTONOMOUS BARGAINING & CONVERSION INTELLIGENCE FUNNEL */}
            <div
              style={{
                backgroundColor: '#0d1527',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: isFunnelCollapsed ? '10px 16px' : '14px 18px',
                display: 'flex',
                flexDirection: 'column',
                gap: isFunnelCollapsed ? '6px' : '12px',
                boxShadow: '0 4px 14px rgba(0, 0, 0, 0.2)',
              }}
            >
              {/* Row 1: Left (Icon + Title + Badge) & Right (Metrics + Collapse Button) */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', width: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                  <div
                    style={{
                      width: '26px',
                      height: '26px',
                      borderRadius: '6px',
                      backgroundColor: 'rgba(56, 189, 248, 0.15)',
                      color: '#38bdf8',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Sparkles size={14} />
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <span style={{ fontSize: '13px', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>
                      Inbound Inquiries &amp; Autonomous Conversion
                    </span>
                    <span
                      style={{
                        fontSize: '9px',
                        backgroundColor: 'rgba(148, 163, 184, 0.15)',
                        color: '#94a3b8',
                        border: '1px solid rgba(148, 163, 184, 0.3)',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      Demo data
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '11px', flexShrink: 0 }}>
                  <span style={{ color: '#94a3b8', whiteSpace: 'nowrap' }}>
                    {funnelMetrics.totalInquiries} Total Inquiries &bull; Active rate: <strong style={{ color: '#34d399' }}>{transactions.length > 0 ? `${Math.round((activeLinesCount / Math.max(transactions.length, 1)) * 100)}% (${activeLinesCount}/${transactions.length})` : '100%'}</strong>
                  </span>
                  <span style={{ color: '#94a3b8', whiteSpace: 'nowrap' }}>
                    MRR Preserved: <strong style={{ color: '#38bdf8' }}>+${mrrPreserved.toFixed(2)}/mo</strong>
                  </span>
                  <button
                    onClick={() => setIsFunnelCollapsed((prev) => !prev)}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px',
                      padding: '4px 10px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: isFunnelCollapsed ? '#38bdf8' : '#94a3b8',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      transition: 'all 0.15s ease',
                    }}
                    title={isFunnelCollapsed ? 'Expand Conversion Distribution' : 'Collapse Conversion Distribution'}
                  >
                    {isFunnelCollapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
                    <span>{isFunnelCollapsed ? 'Expand' : 'Collapse'}</span>
                  </button>
                </div>
              </div>

              {/* Row 2: Subtitle text */}
              <div style={{ fontSize: '11px', color: '#94a3b8', paddingLeft: '34px', marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                Distribution of {funnelMetrics.totalInquiries} inbound buyer agent inquiries across instant catalog approvals, negotiated counter-offers, and floor limits
              </div>

              {/* 100% Horizontal Stacked Bar */}
              {!isFunnelCollapsed && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '8px' }}>
                  {/* The Bar */}
                  <div
                    style={{
                      display: 'flex',
                      height: '36px',
                      borderRadius: '8px',
                      overflow: 'hidden',
                      border: '1px solid #1e293b',
                      backgroundColor: '#090e1a',
                      boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.4)',
                    }}
                  >
                    {/* Segment 1: Instant Approvals */}
                    <div
                      style={{
                        width: funnelMetrics.instantWidth,
                        backgroundColor: '#0284c7',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#ffffff',
                        fontSize: '11px',
                        fontWeight: 700,
                        padding: '0 8px',
                        cursor: 'default',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={`Instant Catalog Approvals: ${funnelMetrics.instantApprovals} inquiries (${funnelMetrics.instantApprovalPct}%) • Cap >= $79.99/mo accepted automatically`}
                    >
                      Instant {funnelMetrics.instantApprovals} ({funnelMetrics.instantApprovalPct}%)
                    </div>

                    {/* Segment 2: Won by Counter-Offer - Emphasized */}
                    <div
                      style={{
                        width: funnelMetrics.counterWidth,
                        backgroundColor: '#199e70',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#ffffff',
                        fontSize: '11px',
                        fontWeight: 800,
                        padding: '0 8px',
                        cursor: 'default',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        boxShadow: '0 0 12px rgba(25, 158, 112, 0.45)',
                        borderLeft: '1px solid rgba(255, 255, 255, 0.25)',
                        borderRight: '1px solid rgba(255, 255, 255, 0.25)',
                        zIndex: 2,
                      }}
                      title={`Won by Counter-Offer: ${funnelMetrics.counterOffersWon} inquiries (${funnelMetrics.counterOffersWonPct}%) • Sub-budget counter-offer accepted (+$${mrrPreserved.toFixed(2)}/mo MRR saved)`}
                    >
                      Won Counter {funnelMetrics.counterOffersWon} ({funnelMetrics.counterOffersWonPct}%)
                    </div>

                    {/* Segment 3: Pending Authorization */}
                    <div
                      style={{
                        width: funnelMetrics.pendingWidth,
                        backgroundColor: '#f59e0b',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#1e293b',
                        fontSize: '10px',
                        fontWeight: 800,
                        padding: '0 4px',
                        cursor: 'default',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={`Pending Authorization: ${funnelMetrics.pendingInquiries} inquiry (${funnelMetrics.pendingPct}%) • Awaiting PayPal agreement token`}
                    >
                      {funnelMetrics.pendingInquiries} ({funnelMetrics.pendingPct}%)
                    </div>

                    {/* Segment 4: Below Hard Floor */}
                    <div
                      style={{
                        width: funnelMetrics.floorWidth,
                        backgroundColor: '#475569',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#cbd5e1',
                        fontSize: '11px',
                        fontWeight: 600,
                        padding: '0 6px',
                        cursor: 'default',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                      title={`Below Hard Floor: ${funnelMetrics.hardFloorBlocks} inquiries (${funnelMetrics.hardFloorPct}%) • Spending mandate < $49.99/mo rejected`}
                    >
                      Below Floor {funnelMetrics.hardFloorBlocks} ({funnelMetrics.hardFloorPct}%)
                    </div>
                  </div>

                  {/* Legend / Breakdown Row */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(4, 1fr)',
                      gap: '8px',
                      fontSize: '11px',
                    }}
                  >
                    <div style={{ backgroundColor: '#090e1a', border: '1px solid #1e293b', borderRadius: '6px', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#0284c7', flexShrink: 0 }} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ color: '#f8fafc', fontWeight: 600 }}>Instant Approvals: {funnelMetrics.instantApprovals} ({funnelMetrics.instantApprovalPct}%)</div>
                        <div style={{ color: '#64748b', fontSize: '10px' }}>Cap &ge; $79.99/mo (Standard)</div>
                      </div>
                    </div>

                    <div style={{ backgroundColor: '#090e1a', border: '1px solid #199e70', borderRadius: '6px', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#199e70', flexShrink: 0 }} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ color: '#34d399', fontWeight: 700 }}>Won Counter: {funnelMetrics.counterOffersWon} ({funnelMetrics.counterOffersWonPct}%)</div>
                        <div style={{ color: '#38bdf8', fontSize: '10px', fontWeight: 600 }}>+${mrrPreserved.toFixed(2)}/mo MRR Saved</div>
                      </div>
                    </div>

                    <div style={{ backgroundColor: '#090e1a', border: '1px solid #1e293b', borderRadius: '6px', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#f59e0b', flexShrink: 0 }} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ color: '#fbbf24', fontWeight: 600 }}>Pending: {funnelMetrics.pendingInquiries} ({funnelMetrics.pendingPct}%)</div>
                        <div style={{ color: '#64748b', fontSize: '10px' }}>Awaiting Token (TXN-9021)</div>
                      </div>
                    </div>

                    <div style={{ backgroundColor: '#090e1a', border: '1px solid #1e293b', borderRadius: '6px', padding: '6px 10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: '#475569', flexShrink: 0 }} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ color: '#94a3b8', fontWeight: 600 }}>Below Floor: {funnelMetrics.hardFloorBlocks} ({funnelMetrics.hardFloorPct}%)</div>
                        <div style={{ color: '#64748b', fontSize: '10px' }}>Spending Cap &lt; $49.99/mo</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 2. DUAL VISUAL COMMAND DECK: COMMERCE BY CAPABILITY & TIER MIX */}
            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '16px' }}>
              {/* Chart 1: Autonomous AP2 Commerce Volume by Capability ($ ARR) */}
              <div
                style={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: '12px',
                  padding: '18px 20px',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
                      Autonomous AP2 Commerce Volume by Capability ($ ARR)
                    </h4>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                      Recurring contract run-rate negotiated and settled autonomously under policy spending caps
                    </div>
                  </div>
                </div>

                {/* AG Charts Component */}
                <div style={{ height: '220px', width: '100%' }}>
                  <AgCharts options={tradeChartOptions} style={{ height: '100%', width: '100%' }} />
                </div>

                <div style={{ borderTop: '1px solid #1e293b', paddingTop: '12px', marginTop: '14px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                  <span>
                    Top Capability:{' '}
                    <strong>
                      {topCapability
                        ? `${topCapability.name} ($${topCapability.gmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ARR • ${topCapability.agentCount} ${topCapability.agentCount === 1 ? 'Agent' : 'Agents'})`
                        : 'None Active ($0.00 ARR • 0 Agents)'}
                    </strong>
                  </span>
                  <span>Software Tiers: <strong>$49.99 Batch / $79.99 Gateway / $179.99 Cluster &bull; PayPal Recurring</strong></span>
                </div>
              </div>

              {/* Chart 2: Subscription Tier Distribution */}
              <div
                style={{
                  backgroundColor: '#0f172a',
                  border: '1px solid #1e293b',
                  borderRadius: '12px',
                  padding: '18px 20px',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
                      Service Capability &amp; Fleet Distribution
                    </h4>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                      Workload allocation breakdown across {activeLinesCount} active autonomous agent nodes
                    </div>
                  </div>
                </div>

                {/* AG Charts Donut Component */}
                <div style={{ height: '220px', width: '100%' }}>
                  <AgCharts options={tierChartOptions} style={{ height: '100%', width: '100%' }} />
                </div>

                <div style={{ borderTop: '1px solid #1e293b', paddingTop: '12px', marginTop: '14px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                  <span>Top Capability: <strong>{topCapability ? `${topCapability.name} (${topCapability.agentCount} Nodes)` : 'None Active'}</strong></span>
                  <span>Billing Rail: <strong>PayPal Subscriptions API &bull; 100% Autopilot</strong></span>
                </div>
              </div>
            </div>

            {/* 3. ENTERPRISE AP2 SETTLEMENT LEDGER DATA GRID */}
            <div
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                overflow: 'hidden',
                boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)',
              }}
            >
              {/* Table Control Strip */}
              <div
                style={{
                  padding: '10px 16px',
                  backgroundColor: '#1e293b',
                  borderBottom: '1px solid #334155',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'nowrap',
                  gap: '10px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'nowrap', flexShrink: 1, minWidth: 0 }}>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px', whiteSpace: 'nowrap', flexShrink: 0 }}>
                    <Layers size={16} color="#38bdf8" /> Autonomous AP2 Settlement Ledger
                  </span>

                  {/* Search Bar */}
                  <div style={{ position: 'relative', width: '220px', flexShrink: 1 }}>
                    <Search size={14} style={{ position: 'absolute', left: '9px', top: '8px', color: '#94a3b8' }} />
                    <input
                      type="text"
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      placeholder="Search agent, entity, ID..."
                      style={{
                        width: '100%',
                        padding: '5px 8px 5px 28px',
                        backgroundColor: '#0f172a',
                        border: '1px solid #334155',
                        borderRadius: '6px',
                        color: '#f8fafc',
                        fontSize: '11px',
                        outline: 'none',
                        boxSizing: 'border-box',
                      }}
                    />
                  </div>

                  {/* Status Filter Tabs */}
                  <div style={{ display: 'flex', backgroundColor: '#0f172a', padding: '2px', borderRadius: '6px', border: '1px solid #334155', flexShrink: 0 }}>
                    {['ALL', 'ACTIVE', 'PENDING'].map((status) => (
                      <button
                        key={status}
                        onClick={() => setSelectedStatus(status)}
                        style={{
                          padding: '3px 8px',
                          border: 'none',
                          borderRadius: '4px',
                          backgroundColor: selectedStatus === status ? '#0284c7' : 'transparent',
                          color: selectedStatus === status ? '#fff' : '#94a3b8',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {status === 'ALL' ? 'All Rows' : status === 'ACTIVE' ? 'Active' : 'Pending'}
                      </button>
                    ))}
                  </div>

                  {/* Capability Filter Dropdown */}
                  <select
                    value={selectedTrade}
                    onChange={(e) => setSelectedTrade(e.target.value)}
                    style={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: '#f8fafc',
                      fontSize: '11px',
                      padding: '5px 8px',
                      outline: 'none',
                      cursor: 'pointer',
                      flexShrink: 0,
                    }}
                    title="Filter ledger by service capability"
                  >
                    <option value="ALL">All Capabilities</option>
                    <option value="High-Throughput Batch Worker">High-Throughput Batch Worker</option>
                    <option value="Dedicated AI Service Gateway">Dedicated AI Service Gateway</option>
                    <option value="Enterprise Cluster Node">Enterprise Cluster Node</option>
                  </select>
                </div>

                {/* Action Buttons */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
                  <button
                    onClick={handleRefresh}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '5px 10px',
                      height: '28px',
                      backgroundColor: '#334155',
                      color: '#f8fafc',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      boxSizing: 'border-box',
                    }}
                    title="Refresh data from backend"
                  >
                    <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} /> Refresh
                  </button>
                  <button
                    onClick={handleExportCsv}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      padding: '5px 10px',
                      height: '28px',
                      backgroundColor: '#0284c7',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      whiteSpace: 'nowrap',
                      boxSizing: 'border-box',
                    }}
                    title="Export official CSV audit docket"
                  >
                    <Download size={13} /> CSV
                  </button>
                </div>
              </div>

              {/* Single Demo data banner */}
              <div
                style={{
                  padding: '6px 16px',
                  backgroundColor: 'rgba(30, 41, 59, 0.5)',
                  borderBottom: '1px solid #1e293b',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '11px',
                  color: '#94a3b8',
                }}
              >
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 700,
                    backgroundColor: 'rgba(148, 163, 184, 0.15)',
                    color: '#94a3b8',
                    border: '1px solid rgba(148, 163, 184, 0.3)',
                    padding: '1px 6px',
                    borderRadius: '4px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                  }}
                >
                  Demo data
                </span>
                <span>
                  Sample autonomous agent subscriptions for AP2 protocol demonstration &bull; All cryptographic proofs &amp; ERP syncs viewable in Inspect drawer
                </span>
              </div>

              {/* AG Grid High-Density Data Table Container */}
              <div style={{ width: '100%', position: 'relative' }}>
                <AgGridReact<A2aTransaction>
                  ref={gridRef}
                  theme={agGridDarkTheme}
                  rowData={filteredTransactions}
                  columnDefs={colDefs}
                  domLayout="autoHeight"
                  pagination={true}
                  paginationPageSize={10}
                  paginationPageSizeSelector={[10, 20, 50]}
                  rowHeight={56}
                  headerHeight={38}
                  floatingFiltersHeight={34}
                  onRowClicked={(event) => {
                    if (event.data) {
                      setSelectedTxn(event.data);
                    }
                  }}
                  defaultColDef={{
                    sortable: true,
                    filter: true,
                    floatingFilter: true,
                    resizable: true,
                  }}
                />
              </div>

              {/* Table Footer */}
              <div
                style={{
                  padding: '10px 20px',
                  backgroundColor: '#131e32',
                  borderTop: '1px solid #1e293b',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '11px',
                  color: '#94a3b8',
                }}
              >
                <span>Powered by <strong>AG Grid Community v36</strong> &bull; Showing <strong>{filteredTransactions.length}</strong> of <strong>{transactions.length}</strong> AP2 Protocol Contracts</span>
                <span>QuickFilter Active &bull; Column Sorting &amp; Filtering Enabled &bull; Autonomous Agent Nodes</span>
              </div>
            </div>
          </div>

          {/* SLIDE-OVER INSPECTION DRAWER */}
          {selectedTxn && (
            <>
              {/* Backdrop */}
              <div
                onClick={() => setSelectedTxn(null)}
                style={{
                  position: 'fixed',
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                  backgroundColor: 'rgba(0, 0, 0, 0.65)',
                  backdropFilter: 'blur(3px)',
                  zIndex: 998,
                  transition: 'opacity 0.2s ease',
                }}
              />

              {/* Drawer Panel */}
              <div
                style={{
                  position: 'fixed',
                  top: 0,
                  right: 0,
                  bottom: 0,
                  width: '500px',
                  maxWidth: '92vw',
                  backgroundColor: '#0b1222',
                  borderLeft: '1px solid #1e293b',
                  boxShadow: '-10px 0 30px rgba(0, 0, 0, 0.7)',
                  zIndex: 999,
                  display: 'flex',
                  flexDirection: 'column',
                  overflow: 'hidden',
                }}
              >
                {/* Drawer Header */}
                <div
                  style={{
                    padding: '16px 20px',
                    backgroundColor: '#0f172a',
                    borderBottom: '1px solid #1e293b',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <div
                        style={{
                          width: '24px',
                          height: '24px',
                          borderRadius: '6px',
                          backgroundColor: 'rgba(56, 189, 248, 0.15)',
                          color: '#38bdf8',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <ShieldCheck size={14} />
                      </div>
                      <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 800, color: '#f8fafc' }}>
                        Buyer Agent Identity &amp; Mandate Audit
                      </h3>
                    </div>
                    <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>
                      Protocol Txn: <strong style={{ color: '#38bdf8', fontFamily: 'monospace' }}>{selectedTxn.id}</strong> &bull; {selectedTxn.buyer_agent || selectedTxn.contractor_name}
                    </div>
                  </div>

                  <button
                    onClick={() => setSelectedTxn(null)}
                    style={{
                      background: 'none',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: '#94a3b8',
                      cursor: 'pointer',
                      padding: '6px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'all 0.15s ease',
                    }}
                    title="Close drawer"
                  >
                    <X size={16} />
                  </button>
                </div>

                {/* Drawer Tab Switcher */}
                <div
                  style={{
                    padding: '8px 20px',
                    backgroundColor: '#0d1527',
                    borderBottom: '1px solid #1e293b',
                    display: 'flex',
                    gap: '8px',
                  }}
                >
                  <button
                    onClick={() => setDrawerTab('audit')}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '6px 14px',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: drawerTab === 'audit' ? '#0284c7' : 'transparent',
                      color: drawerTab === 'audit' ? '#fff' : '#94a3b8',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <ShieldCheck size={13} /> Mandate &amp; Vault Docket
                  </button>
                  <button
                    onClick={() => setDrawerTab('raw')}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      padding: '6px 14px',
                      borderRadius: '6px',
                      border: 'none',
                      backgroundColor: drawerTab === 'raw' ? '#0284c7' : 'transparent',
                      color: drawerTab === 'raw' ? '#fff' : '#94a3b8',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <FileText size={13} /> Machine JSON
                  </button>
                </div>

                {/* Drawer Body (Scrollable) */}
                <div style={{ flex: 1, padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  {drawerTab === 'audit' && (
                    <>
                      {/* Status Banner */}
                      <div
                        style={{
                          padding: '12px 14px',
                          borderRadius: '8px',
                          backgroundColor:
                            selectedTxn.status === 'ACTIVE_STREAMING' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                          border: `1px solid ${
                            selectedTxn.status === 'ACTIVE_STREAMING' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'
                          }`,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <span
                            style={{
                              width: '8px',
                              height: '8px',
                              borderRadius: '50%',
                              backgroundColor: selectedTxn.status === 'ACTIVE_STREAMING' ? '#10b981' : '#f59e0b',
                            }}
                          />
                          <span
                            style={{
                              fontSize: '12px',
                              fontWeight: 700,
                              color: selectedTxn.status === 'ACTIVE_STREAMING' ? '#34d399' : '#fbbf24',
                            }}
                          >
                            {selectedTxn.status === 'ACTIVE_STREAMING' ? 'Active' : selectedTxn.status === 'PENDING_DEPOSIT' ? 'Awaiting approval' : selectedTxn.status}
                          </span>
                        </div>
                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                          {selectedTxn.timestamp} UTC
                        </span>
                      </div>

                      {/* Buyer Agent Profile Card */}
                      <div
                        style={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #1e293b',
                          borderRadius: '10px',
                          padding: '14px 16px',
                        }}
                      >
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '10px' }}>
                          Buyer Agent &amp; Principal Entity
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                          <div>
                            <div style={{ fontSize: '10px', color: '#64748b' }}>Buyer Agent ID</div>
                            <div style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8', fontFamily: 'monospace', marginTop: '2px' }}>
                              {selectedTxn.buyer_agent || selectedTxn.contractor_name}
                            </div>
                          </div>
                          <div>
                            <div style={{ fontSize: '10px', color: '#64748b' }}>Service Capability</div>
                            <div style={{ fontSize: '12px', fontWeight: 600, color: '#cbd5e1', marginTop: '2px' }}>
                              {selectedTxn.trade_vertical}
                            </div>
                          </div>
                          <div style={{ gridColumn: 'span 2' }}>
                            <div style={{ fontSize: '10px', color: '#64748b' }}>Principal Entity</div>
                            <div style={{ fontSize: '13px', color: '#f8fafc', marginTop: '2px', fontWeight: 600 }}>
                              {selectedTxn.principal_entity || selectedTxn.kyc_legal_entity}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Assigned Worker Node Endpoint */}
                      <div
                        style={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #1e293b',
                          borderRadius: '10px',
                          padding: '14px 16px',
                        }}
                      >
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '10px' }}>
                          Provisioned Worker Node Endpoint
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <div>
                            <div style={{ fontSize: '15px', fontWeight: 800, color: '#34d399', fontFamily: 'monospace' }}>
                              {selectedTxn.allocated_did}
                            </div>
                            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                              FastMCP JSON-RPC 2.0 &bull; Cryptographic Attestation Tier A
                            </div>
                          </div>
                          <button
                            onClick={() => handleCopy(selectedTxn.allocated_did, `drawer-${selectedTxn.allocated_did}`)}
                            style={{
                              backgroundColor: '#1e293b',
                              border: '1px solid #334155',
                              borderRadius: '6px',
                              color: '#f8fafc',
                              padding: '6px 10px',
                              fontSize: '11px',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                          >
                            {copiedKey === `drawer-${selectedTxn.allocated_did}` ? <Check size={13} color="#34d399" /> : <Copy size={13} />} Copy
                          </button>
                        </div>
                        <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px solid #1e293b', fontSize: '11px', color: '#34d399', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <CheckCircle2 size={13} /> {selectedTxn.tcpa_guard}
                        </div>
                      </div>

                      {/* PayPal Vault Agreement */}
                      <div
                        style={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #1e293b',
                          borderRadius: '10px',
                          padding: '14px 16px',
                        }}
                      >
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '10px' }}>
                          PayPal Autonomous Payment Rail
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#94a3b8' }}>Service Plan</span>
                            <strong style={{ color: '#f8fafc' }}>{selectedTxn.service_plan}</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#94a3b8' }}>Recurring Rate</span>
                            <strong style={{ color: '#38bdf8' }}>${selectedTxn.monthly_amount.toFixed(2)}/mo</strong>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#94a3b8' }}>PayPal Subscription ID</span>
                            <span style={{ fontFamily: 'monospace', color: '#f8fafc', fontSize: '11px' }}>
                              {selectedTxn.paypal_sub_id}
                            </span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                            <span style={{ color: '#94a3b8' }}>Vault Token</span>
                            <span style={{ fontFamily: 'monospace', color: '#34d399', fontSize: '11px' }}>
                              ba_vault_auto_mit_active
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Cryptographic Ed25519 Mandate Signature */}
                      <div
                        style={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #1e293b',
                          borderRadius: '10px',
                          padding: '14px 16px',
                        }}
                      >
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                          Cryptographic Mandate Proof
                        </div>
                        <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '6px' }}>
                          Ed25519 Deterministic Signature (Buyer Spending Mandate + Nonce Attestation):
                        </div>
                        <div
                          style={{
                            padding: '8px 10px',
                            backgroundColor: '#080d1a',
                            borderRadius: '6px',
                            fontFamily: 'monospace',
                            fontSize: '10px',
                            color: '#a78bfa',
                            wordBreak: 'break-all',
                            border: '1px solid #1e293b',
                          }}
                        >
                          ed25519:sig:9a7f4b82c1e4d0f6a2b8e5c3d7a9b1f4e6c8a0d2b4f6e8a0c2e4f6a8b0d2e4f6
                        </div>
                        <div style={{ marginTop: '8px', fontSize: '10px', color: '#64748b' }}>
                          Verified by AP2 Anti-Tamper Runtime &bull; SHA-256 Digest Anchored
                        </div>
                      </div>

                      {/* Back-Office ERP Integration */}
                      <div
                        style={{
                          backgroundColor: '#0f172a',
                          border: '1px solid #1e293b',
                          borderRadius: '10px',
                          padding: '14px 16px',
                        }}
                      >
                        <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                          Back-Office ERP Integration
                        </div>
                        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                          <span style={{ fontSize: '11px', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '3px 8px', borderRadius: '4px', fontWeight: 600 }}>
                            FastMCP Bridge
                          </span>
                          <span style={{ fontSize: '11px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '3px 8px', borderRadius: '4px', fontWeight: 600 }}>
                            QBO GL 6300 Exported
                          </span>
                        </div>
                        <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                          Real-time ledger sync via FastMCP tool calling to Enterprise ERP and QuickBooks Online GL Account #6300.
                        </div>
                      </div>
                    </>
                  )}

                  {drawerTab === 'raw' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', height: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: '11px', color: '#94a3b8' }}>Structured Transaction Entity JSON:</span>
                        <button
                          onClick={() => handleCopy(JSON.stringify(selectedTxn, null, 2), 'raw-json')}
                          style={{
                            backgroundColor: '#1e293b',
                            border: '1px solid #334155',
                            borderRadius: '5px',
                            color: '#f8fafc',
                            padding: '4px 8px',
                            fontSize: '11px',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                        >
                          {copiedKey === 'raw-json' ? <Check size={12} color="#34d399" /> : <Copy size={12} />} Copy JSON
                        </button>
                      </div>
                      <pre
                        style={{
                          flex: 1,
                          backgroundColor: '#080d1a',
                          border: '1px solid #1e293b',
                          borderRadius: '8px',
                          padding: '12px',
                          fontFamily: 'monospace',
                          fontSize: '11px',
                          color: '#38bdf8',
                          overflowX: 'auto',
                          whiteSpace: 'pre-wrap',
                          margin: 0,
                        }}
                      >
                        {JSON.stringify(selectedTxn, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>

                {/* Drawer Footer */}
                <div
                  style={{
                    padding: '14px 20px',
                    backgroundColor: '#0f172a',
                    borderTop: '1px solid #1e293b',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '10px',
                  }}
                >
                  <button
                    onClick={() => setSelectedTxn(null)}
                    style={{
                      padding: '8px 16px',
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      color: '#cbd5e1',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Close
                  </button>

                  <button
                    onClick={() => {
                      const txnId = selectedTxn.id;
                      setSelectedTxn(null);
                      if (onNavigateTab) {
                        onNavigateTab('copilot');
                      }
                      if (onInspectTrace) {
                        onInspectTrace(txnId);
                      }
                    }}
                    style={{
                      padding: '8px 16px',
                      backgroundColor: '#0284c7',
                      border: 'none',
                      color: '#fff',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    Trace in Copilot <ExternalLink size={13} />
                  </button>
                </div>
              </div>
            </>
          )}
        </>
      )}

      {/* Adversarial Attack & Anti-Tamper Interactive Sandbox */}
      <AdversarialTamperModal
        isOpen={showTamperModal}
        onClose={() => setShowTamperModal(false)}
      />
    </div>
  );
}

export default EnterpriseFleetLedger;
