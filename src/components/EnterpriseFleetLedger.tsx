import { useState, useMemo, useRef } from 'react';
import {
  ShieldCheck,
  PhoneCall,
  CreditCard,
  TrendingUp,
  Search,
  Download,
  RefreshCw,
  Copy,
  Check,
  ExternalLink,
  Layers,
  Radio,
  Sliders,
  CheckCircle2,
  Eye,
  Zap,
  X,
  FileText,
  LayoutGrid,
} from 'lucide-react';
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
}

export function EnterpriseFleetLedger({
  transactions,
  tradeImpactData,
  kycAuditData,
  studioData,
  studioMode,
  onSetStudioMode,
  onSimulateClick,
  onInspectTrace,
  onNavigateTab,
  onRefreshData,
  viewMode,
  onViewModeChange,
}: EnterpriseFleetLedgerProps) {
  const [internalViewMode, setInternalViewMode] = useState<'grid' | 'studio'>('grid');
  const currentViewMode = viewMode ?? internalViewMode;
  const handleViewModeToggle = (m: 'grid' | 'studio') => {
    if (onViewModeChange) {
      onViewModeChange(m);
    } else {
      setInternalViewMode(m);
    }
  };
  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedTrade, setSelectedTrade] = useState<string>('ALL');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Selected transaction for the Slide-Over Inspection Drawer
  const [selectedTxn, setSelectedTxn] = useState<A2aTransaction | null>(null);
  const [drawerTab, setDrawerTab] = useState<'audit' | 'raw'>('audit');

  // Copy helper
  const handleCopy = (text: string, key: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  // Live refresh: synchronizes with SQLite backend via onRefreshData
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
        fileName: `fieldsmith_enterprise_fleet_ledger_${new Date().toISOString().slice(0, 10)}.csv`,
      });
      return;
    }

    const headers = [
      'Transaction ID',
      'Timestamp',
      'Contractor Name',
      'Business Entity',
      'Trade Vertical',
      'Service Plan',
      'Monthly Amount ($)',
      'PayPal Subscription ID',
      'Allocated DID',
      'TCPA Shield Status',
      'KYC Verification',
      'State',
    ];

    const rows = transactions.map((t) => [
      t.id,
      t.timestamp,
      t.contractor_name,
      t.kyc_legal_entity,
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
    link.setAttribute('download', `fieldsmith_enterprise_fleet_ledger_${new Date().toISOString().slice(0, 10)}.csv`);
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
        headerName: 'Tenant / Txn ID',
        width: 160,
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
              <div style={{ fontSize: '10px', color: '#64748b', lineHeight: 1 }}>{t.timestamp.slice(11, 19)}</div>
            </div>
          );
        },
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 175,
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
                {isActive ? 'ACTIVE_STREAMING' : 'PENDING_DEPOSIT'}
              </span>
            </div>
          );
        },
      },
      {
        field: 'contractor_name',
        headerName: 'Contractor & Legal Entity',
        flex: 1.4,
        minWidth: 220,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          const isMarcus = t.contractor_name === 'Marcus Miller';
          return (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span>{t.contractor_name}</span>
                {isMarcus && (
                  <span style={{ fontSize: '9px', backgroundColor: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', padding: '1px 5px', borderRadius: '4px' }}>
                    CURRENT COPILOT
                  </span>
                )}
              </div>
              <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: 1.2 }}>{t.kyc_legal_entity}</div>
            </div>
          );
        },
      },
      {
        field: 'trade_vertical',
        headerName: 'Trade Vertical',
        width: 160,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          return (
            <div style={{ display: 'flex', alignItems: 'center', height: '100%' }}>
              <span style={{ fontSize: '11px', backgroundColor: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', padding: '3px 8px', borderRadius: '6px' }}>
                {t.trade_vertical}
              </span>
            </div>
          );
        },
      },
      {
        field: 'allocated_did',
        headerName: 'Allocated 10DLC DID',
        width: 180,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          const isActive = t.status === 'ACTIVE_STREAMING';
          return (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              {isActive ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <strong style={{ color: '#38bdf8', fontFamily: 'monospace' }}>{t.allocated_did}</strong>
                  <button
                    onClick={() => handleCopy(t.allocated_did, t.allocated_did)}
                    style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0 }}
                    title="Copy 10DLC DID"
                  >
                    {copiedKey === t.allocated_did ? <Check size={12} color="#34d399" /> : <Copy size={12} />}
                  </button>
                </div>
              ) : (
                <span style={{ color: '#f59e0b', fontStyle: 'italic', fontSize: '11px' }}>Awaiting Approval</span>
              )}
              <div style={{ fontSize: '10px', color: '#64748b', lineHeight: 1 }}>Telnyx Carrier Bound</div>
            </div>
          );
        },
      },
      {
        field: 'monthly_amount',
        headerName: 'Monthly Rate & Rail',
        width: 160,
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
        field: 'kyc_status',
        headerName: 'KYC Identity & TCPA',
        width: 170,
        cellRenderer: (params: ICellRendererParams<A2aTransaction>) => {
          const t = params.data;
          if (!t) return null;
          return (
            <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#34d399', fontSize: '11px', fontWeight: 600 }}>
                <CheckCircle2 size={12} /> {t.kyc_status.includes('VERIFIED') ? 'KYC Verified' : 'Pending KYC'}
              </div>
              <div style={{ fontSize: '10px', color: '#94a3b8', lineHeight: 1 }}>
                100% Inbound Locked
              </div>
            </div>
          );
        },
      },
      {
        headerName: 'Back-Office',
        width: 150,
        sortable: false,
        filter: false,
        cellRenderer: () => {
          return (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', height: '100%' }}>
              <span style={{ fontSize: '10px', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '2px 6px', borderRadius: '4px' }}>
                Jobber
              </span>
              <span style={{ fontSize: '10px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '2px 6px', borderRadius: '4px' }}>
                QBO #6300
              </span>
            </div>
          );
        },
      },
      {
        headerName: 'Action',
        width: 145,
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
                title="Inspect contractor mandate and cryptographic proof"
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

  // Dynamic Trade GMV computed from live active transactions
  const dynamicTradeData = useMemo(() => {
    const tradeGmvMap: Record<string, number> = {};
    transactions.forEach((t) => {
      if (t.status === 'ACTIVE_STREAMING') {
        tradeGmvMap[t.trade_vertical] = (tradeGmvMap[t.trade_vertical] || 0) + t.monthly_amount * 12;
      }
    });

    return tradeImpactData.map((d) => {
      const liveGmv = tradeGmvMap[d.trade];
      const gmv = liveGmv !== undefined ? liveGmv : (d.annualized_gmv ?? d.recovered_revenue ?? 0);
      return {
        trade: d.trade,
        gmv: Math.round(gmv * 100) / 100,
      };
    });
  }, [transactions, tradeImpactData]);

  // AG Charts: Autonomous A2A Commerce Volume by Trade
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
          stroke: '#38bdf8',
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

  const activeTrunksHistory = useMemo(() => {
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

  const topVertical = useMemo(() => {
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

  // Subscription Tier Distribution computed from live transactions (Adam Finer's <= 5 slice rule)
  const tierDistribution = useMemo(() => {
    const map: Record<string, { tier: string; count: number; mrr: number }> = {};

    transactions.forEach((t) => {
      let tierName = 'Pro Screener ($79.99)';
      const plan = t.service_plan.toLowerCase();
      if (plan.includes('commercial') || plan.includes('scope') || plan.includes('metal') || plan.includes('restoration')) {
        tierName = 'Commercial Fleet ($79.99)';
      } else if (plan.includes('dispatch') || plan.includes('roadside') || plan.includes('gps')) {
        tierName = 'Emergency Dispatch ($79.99)';
      } else if (plan.includes('receptionist') || plan.includes('sole')) {
        tierName = 'Solo Receptionist ($79.99)';
      } else if (t.monthly_amount < 60) {
        tierName = 'Solo Dispatch ($49.99)';
      } else if (t.monthly_amount > 100) {
        tierName = 'Enterprise Fleet ($179.99)';
      }

      if (!map[tierName]) {
        map[tierName] = { tier: tierName, count: 0, mrr: 0 };
      }
      map[tierName].count += 1;
      map[tierName].mrr = Math.round((map[tierName].mrr + t.monthly_amount) * 100) / 100;
    });

    return Object.values(map);
  }, [transactions]);

  // AG Charts: Subscription Tier Distribution Donut Chart (Adam Finer Polar Mix)
  const tierChartOptions: AgChartOptions = useMemo(
    () => ({
      theme: 'ag-default-dark',
      data: tierDistribution,
      series: [
        {
          type: 'donut',
          angleKey: 'count',
          legendItemKey: 'tier',
          sectorLabelKey: 'count',
          innerRadiusRatio: 0.65,
          fills: ['#0284c7', '#10b981', '#8b5cf6', '#f59e0b'],
          strokes: ['#070d1a', '#070d1a', '#070d1a', '#070d1a'],
          strokeWidth: 2,
          cornerRadius: 4,
          sectorSpacing: 3,
          innerLabels: [
            {
              text: `$${totalMrr.toFixed(0)}`,
              fontSize: 20,
              fontWeight: 'bold',
              color: '#f8fafc',
            },
            {
              text: 'Active MRR',
              fontSize: 11,
              color: '#94a3b8',
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
      },
    }),
    [tierDistribution, totalMrr]
  );

  // Filtered transactions for the ledger grid
  const filteredTransactions = useMemo(() => {
    return transactions.filter((t) => {
      const matchesSearch =
        searchTerm === '' ||
        t.contractor_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        t.kyc_legal_entity.toLowerCase().includes(searchTerm.toLowerCase()) ||
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
  // Real Hourly Settlement Velocity is superseded by Adam Finer Tier Distribution Donut Chart

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: '#080d1a', color: '#f8fafc', overflowY: 'auto' }}>
      {/* COMMAND CENTER SUB-HEADER & MODE TOGGLE */}
      <div
        style={{
          padding: '12px 24px',
          backgroundColor: '#0d1527',
          borderBottom: '1px solid #1e293b',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '32px',
              height: '32px',
              borderRadius: '8px',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              color: '#38bdf8',
              border: '1px solid rgba(56, 189, 248, 0.3)',
            }}
          >
            <Radio size={16} className="animate-pulse" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '14px', fontWeight: 800, letterSpacing: '0.04em', color: '#f8fafc' }}>
                ENTERPRISE FLEET COMMAND CENTER
              </span>
              <span
                style={{
                  fontSize: '10px',
                  backgroundColor: 'rgba(56, 189, 248, 0.15)',
                  color: '#38bdf8',
                  border: '1px solid rgba(56, 189, 248, 0.35)',
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                SIMULATED SANDBOX DATA
              </span>
              <span
                style={{
                  fontSize: '10px',
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  color: '#34d399',
                  border: '1px solid rgba(16, 185, 129, 0.4)',
                  padding: '2px 8px',
                  borderRadius: '9999px',
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }} />
                ALL SYSTEMS OPERATIONAL
              </span>
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>
              Simulated Fleet Demonstration &bull; 14 Pre-Seeded Florida Contractor Verticals &bull; Telnyx 10DLC Wholesale &bull; Florida LATA 952/953
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Segmented Operational Grid / AG Studio Custom BI Switcher */}
          <div style={{ display: 'flex', alignItems: 'center', backgroundColor: '#1e293b', borderRadius: '6px', padding: '2px', border: '1px solid #334155' }}>
            <button
              onClick={() => handleViewModeToggle('grid')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                borderRadius: '4px',
                border: 'none',
                backgroundColor: currentViewMode === 'grid' ? '#0284c7' : 'transparent',
                color: currentViewMode === 'grid' ? '#ffffff' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title="Live high-density operational ledger with column filtering and sorting"
            >
              <LayoutGrid size={13} /> Live Operational Grid
            </button>
            <button
              onClick={() => handleViewModeToggle('studio')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                borderRadius: '4px',
                border: 'none',
                backgroundColor: currentViewMode === 'studio' ? '#0284c7' : 'transparent',
                color: currentViewMode === 'studio' ? '#ffffff' : '#94a3b8',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title="Interactive AG Studio drag-and-drop report designer with 4 multi-table datasets"
            >
              <Layers size={13} /> AG Studio Custom BI
            </button>
          </div>

          <button
            onClick={onSimulateClick}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              background: 'linear-gradient(135deg, #10b981, #059669)',
              color: '#fff',
              fontSize: '12px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 2px 6px rgba(16, 185, 129, 0.3)',
            }}
          >
            <Sliders size={14} /> Simulate AP2 Purchase
          </button>
        </div>
      </div>

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
          {/* ENTERPRISE COMMAND CENTER DASHBOARD (HIGH-DENSITY MISSION CONTROL) */}
          <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* 1. TOP STAT CARDS (KPI METRIC DECK - TUFTE DATA-TO-INK RATIO) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '16px' }}>
            {/* Card 1: Active Fleet MRR */}
            <div
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '16px 20px',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', color: '#94a3b8', textTransform: 'uppercase' }}>
                  Fleet Run-Rate MRR
                </span>
                <div style={{ width: '28px', height: '28px', borderRadius: '7px', backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#38bdf8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CreditCard size={15} />
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '12px' }}>
                <div>
                  <div style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc', lineHeight: 1.1 }}>
                    ${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    <span style={{ fontSize: '12px', fontWeight: 500, color: '#64748b' }}>/mo</span>
                  </div>
                  <div style={{ fontSize: '11px', color: '#34d399', fontWeight: 600, marginTop: '5px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <TrendingUp size={13} /> {activeLinesCount} Seeded Trunks
                  </div>
                </div>
                <div style={{ paddingBottom: '2px' }}>
                  <Sparkline data={mrrHistory} color="#38bdf8" />
                </div>
              </div>
            </div>

            {/* Card 2: Active Carrier Lines */}
            <div
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '16px 20px',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', color: '#94a3b8', textTransform: 'uppercase' }}>
                  Active 10DLC Trunks
                </span>
                <div style={{ width: '28px', height: '28px', borderRadius: '7px', backgroundColor: 'rgba(16, 185, 129, 0.12)', color: '#34d399', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <PhoneCall size={15} />
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '12px' }}>
                <div>
                  <div style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc', lineHeight: 1.1 }}>
                    {activeLinesCount} Trunks
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '5px' }}>
                    TCR <strong>CITNRYD</strong> &bull; LATA 952/953
                  </div>
                </div>
                <div style={{ paddingBottom: '2px' }}>
                  <Sparkline data={activeTrunksHistory} color="#34d399" />
                </div>
              </div>
            </div>

            {/* Card 3: Spending Policy & Anti-Tamper Guard */}
            <div
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '16px 20px',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', color: '#94a3b8', textTransform: 'uppercase' }}>
                  Autonomous Policy Guard
                </span>
                <div style={{ width: '28px', height: '28px', borderRadius: '7px', backgroundColor: 'rgba(16, 185, 129, 0.12)', color: '#34d399', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <ShieldCheck size={15} />
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '12px' }}>
                <div>
                  <div style={{ fontSize: '26px', fontWeight: 800, color: '#34d399', lineHeight: 1.1 }}>
                    100% Enforced
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '5px' }}>
                    {activeLinesCount} Trunks Bound &bull; 0 Budget Leaks
                  </div>
                </div>
              </div>
            </div>

            {/* Card 4: Autonomous Settlement Volume (GMV) */}
            <div
              style={{
                backgroundColor: '#0f172a',
                border: '1px solid #1e293b',
                borderRadius: '12px',
                padding: '16px 20px',
                boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', color: '#94a3b8', textTransform: 'uppercase' }}>
                  Annualized Fleet GMV
                </span>
                <div style={{ width: '28px', height: '28px', borderRadius: '7px', backgroundColor: 'rgba(56, 189, 248, 0.12)', color: '#38bdf8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Zap size={15} />
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '12px' }}>
                <div>
                  <div style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc', lineHeight: 1.1 }}>
                    ${totalAutonomousGmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    <span style={{ fontSize: '12px', fontWeight: 500, color: '#64748b' }}> ARR</span>
                  </div>
                  <div style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 600, marginTop: '5px' }}>
                    {activeLinesCount} Carrier Subscriptions &bull; PayPal Vault MIT
                  </div>
                </div>
                <div style={{ paddingBottom: '2px' }}>
                  <Sparkline data={gmvHistory} color="#a78bfa" />
                </div>
              </div>
            </div>
          </div>

          {/* 2. DUAL VISUAL COMMAND DECK: COMMERCE BY TRADE & RECURRING TIER MIX (POWERED BY AG CHARTS) */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '16px' }}>
            {/* Chart 1: Autonomous A2A Commerce Volume by Trade ($ ARR) */}
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
                    Autonomous Agentic Commerce Volume by Trade ($ ARR)
                  </h4>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                    Recurring contract run-rate negotiated and settled autonomously under policy spending caps
                  </div>
                </div>
                <span style={{ fontSize: '11px', backgroundColor: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', padding: '3px 8px', borderRadius: '6px', fontWeight: 600 }}>
                  AG Charts v14
                </span>
              </div>

              {/* AG Charts Component */}
              <div style={{ height: '220px', width: '100%' }}>
                <AgCharts options={tradeChartOptions} style={{ height: '100%', width: '100%' }} />
              </div>

              <div style={{ borderTop: '1px solid #1e293b', paddingTop: '12px', marginTop: '14px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                <span>
                  Top Vertical:{' '}
                  <strong>
                    {topVertical
                      ? `${topVertical.name} ($${topVertical.gmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ARR • ${topVertical.agentCount} ${topVertical.agentCount === 1 ? 'Agent' : 'Agents'})`
                      : 'None Active ($0.00 ARR • 0 Agents)'}
                  </strong>
                </span>
                <span>Software Tiers: <strong>$49.99 Solo / $79.99 Pro / $179.99 Fleet &bull; PayPal Recurring</strong></span>
              </div>
            </div>

            {/* Chart 2: Subscription Tier Distribution (Adam Finer Donut Chart) */}
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
                    Subscription Tier &amp; Recurring Revenue Mix
                  </h4>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                    Categorical breakdown across {transactions.length} active and provisioned carrier accounts
                  </div>
                </div>
                <span style={{ fontSize: '11px', backgroundColor: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', padding: '3px 8px', borderRadius: '6px', fontWeight: 600 }}>
                  Adam Finer Polar Mix
                </span>
              </div>

              {/* AG Charts Donut Component */}
              <div style={{ height: '220px', width: '100%' }}>
                <AgCharts options={tierChartOptions} style={{ height: '100%', width: '100%' }} />
              </div>

              <div style={{ borderTop: '1px solid #1e293b', paddingTop: '12px', marginTop: '14px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                <span>Primary Plan: <strong>Emergency Dispatch (6 Accounts &bull; $479.94/mo)</strong></span>
                <span>Billing Rail: <strong>PayPal Subscriptions API &bull; 100% Autopilot</strong></span>
              </div>
            </div>
          </div>

          {/* 3. ENTERPRISE FLEET LEDGER DATA GRID */}
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
                padding: '14px 20px',
                backgroundColor: '#1e293b',
                borderBottom: '1px solid #334155',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '12px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Layers size={16} /> Autonomous Agentic Fleet Ledger
                </span>

                {/* Search Bar */}
                <div style={{ position: 'relative', width: '260px' }}>
                  <Search size={14} style={{ position: 'absolute', left: '10px', top: '9px', color: '#94a3b8' }} />
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search contractor, entity, DID, or ID..."
                    style={{
                      width: '100%',
                      padding: '6px 10px 6px 30px',
                      backgroundColor: '#0f172a',
                      border: '1px solid #334155',
                      borderRadius: '6px',
                      color: '#f8fafc',
                      fontSize: '11px',
                      outline: 'none',
                    }}
                  />
                </div>

                {/* Status Filter Tabs */}
                <div style={{ display: 'flex', backgroundColor: '#0f172a', padding: '2px', borderRadius: '6px', border: '1px solid #334155' }}>
                  {['ALL', 'ACTIVE', 'PENDING'].map((status) => (
                    <button
                      key={status}
                      onClick={() => setSelectedStatus(status)}
                      style={{
                        padding: '4px 10px',
                        border: 'none',
                        borderRadius: '4px',
                        backgroundColor: selectedStatus === status ? '#0284c7' : 'transparent',
                        color: selectedStatus === status ? '#fff' : '#94a3b8',
                        fontSize: '11px',
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {status === 'ALL' ? 'All Rows' : status === 'ACTIVE' ? 'Active' : 'Pending'}
                    </button>
                  ))}
                </div>

                {/* Trade Filter Dropdown */}
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
                  }}
                  title="Filter ledger by trade vertical"
                >
                  <option value="ALL">All Trade Verticals</option>
                  <option value="Tile">Tile & Flooring</option>
                  <option value="Plumbing">Emergency Plumbing</option>
                  <option value="Roofing">Roofing & Storm</option>
                  <option value="Towing">Towing & Roadside</option>
                  <option value="HVAC">HVAC & Mechanical</option>
                  <option value="Accounting">Accounting & Bookkeeping</option>
                </select>

                {/* KYC Compliance Status Badge */}
                <div
                  style={{
                    fontSize: '10px',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    color: '#34d399',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    padding: '3px 8px',
                    borderRadius: '6px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                  title="All provisioned lines authenticated via TCR 10DLC campaign 4b3001a0-c5af-db76-3128-a88a3d668ff6"
                >
                  <CheckCircle2 size={11} /> {kycAuditData.length} TCR Campaigns Active
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                  onClick={handleRefresh}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    backgroundColor: '#334155',
                    color: '#f8fafc',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title="Simulate carrier heartbeat ping"
                >
                  <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} /> Refresh
                </button>
                <button
                  onClick={handleExportCsv}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 12px',
                    backgroundColor: '#0284c7',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                  title="Export official CSV audit docket"
                >
                  <Download size={13} /> Export Audit CSV
                </button>
              </div>
            </div>

            {/* AG Grid High-Density Data Table Container */}
            <div style={{ height: '520px', width: '100%', position: 'relative' }}>
              <AgGridReact<A2aTransaction>
                ref={gridRef}
                theme={agGridDarkTheme}
                rowData={filteredTransactions}
                columnDefs={colDefs}
                pagination={true}
                paginationPageSize={10}
                paginationPageSizeSelector={[10, 20, 50]}
                rowHeight={48}
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
              <span>Powered by <strong>AG Grid Community v36</strong> &bull; Showing <strong>{filteredTransactions.length}</strong> of <strong>{transactions.length}</strong> Fleet Tenant Accounts</span>
              <span>QuickFilter Active &bull; Column Sorting &amp; Filtering Enabled &bull; Central FL Telephony Trunks &bull; Carrier SLA: 99.999%</span>
            </div>
          </div>
        </div>

      {/* SLIDE-OVER INSPECTION DRAWER (PROGRESSIVE DISCLOSURE - ADAM FINER PRINCIPLE) */}
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
                    Tenant Identity &amp; Mandate Audit
                  </h3>
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '3px' }}>
                  Tenant ID: <strong style={{ color: '#38bdf8', fontFamily: 'monospace' }}>{selectedTxn.id}</strong> &bull; {selectedTxn.contractor_name}
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
                        {selectedTxn.status}
                      </span>
                    </div>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                      {selectedTxn.timestamp}
                    </span>
                  </div>

                  {/* Contractor Profile Card */}
                  <div
                    style={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #1e293b',
                      borderRadius: '10px',
                      padding: '14px 16px',
                    }}
                  >
                    <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '10px' }}>
                      Contractor Entity
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                      <div>
                        <div style={{ fontSize: '10px', color: '#64748b' }}>Primary Name</div>
                        <div style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc', marginTop: '2px' }}>
                          {selectedTxn.contractor_name}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: '10px', color: '#64748b' }}>Trade Vertical</div>
                        <div style={{ fontSize: '13px', fontWeight: 600, color: '#38bdf8', marginTop: '2px' }}>
                          {selectedTxn.trade_vertical}
                        </div>
                      </div>
                      <div style={{ gridColumn: 'span 2' }}>
                        <div style={{ fontSize: '10px', color: '#64748b' }}>KYC Legal Entity</div>
                        <div style={{ fontSize: '12px', color: '#cbd5e1', marginTop: '2px', fontWeight: 500 }}>
                          {selectedTxn.kyc_legal_entity}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Assigned 10DLC Telecom DID */}
                  <div
                    style={{
                      backgroundColor: '#0f172a',
                      border: '1px solid #1e293b',
                      borderRadius: '10px',
                      padding: '14px 16px',
                    }}
                  >
                    <div style={{ fontSize: '11px', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '10px' }}>
                      Provisioned Telecom Carrier Trunk
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div>
                        <div style={{ fontSize: '16px', fontWeight: 800, color: '#38bdf8', fontFamily: 'monospace' }}>
                          {selectedTxn.allocated_did}
                        </div>
                        <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                          Telnyx Wholesale Carrier &bull; LATA 952/953 Central Florida
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
                      Ed25519 Deterministic Signature (Contractor Mandate + TCPA Attestation):
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
                      Verified by FieldSmith Anti-Tamper Runtime &bull; SHA-256 Digest Anchored
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
    </div>
  );
}
