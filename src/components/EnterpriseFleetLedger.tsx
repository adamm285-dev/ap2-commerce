import { useState, useMemo } from 'react';
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
  Edit3,
  BarChart3,
  Zap,
} from 'lucide-react';
import { AgStudio } from 'ag-studio-react';
import { studioTheme, type AgDataSourcesDefinition, type AgStudioMode } from 'ag-studio';
import {
  type A2aTransaction,
  type TradeImpact,
  type KycAuditRecord,
  initialDashboardState,
} from '../data/telemetryData';

export interface EnterpriseFleetLedgerProps {
  transactions: A2aTransaction[];
  tradeImpactData: TradeImpact[];
  kycAuditData: KycAuditRecord[];
  studioData: AgDataSourcesDefinition;
  studioMode: AgStudioMode;
  onSetStudioMode: (mode: AgStudioMode) => void;
  onSimulateClick: () => void;
  onInspectTrace?: (transactionId: string) => void;
  onNavigateTab?: (tab: 'copilot' | 'ag-studio' | 'bryntum' | 'zapier') => void;
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
}: EnterpriseFleetLedgerProps) {
  // View toggle: 'command-center' (Default high-density mission control) vs 'ag-studio' (Raw drag-and-drop report builder)
  const [subView, setSubView] = useState<'command-center' | 'ag-studio'>('command-center');

  // Search & Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedTrade, setSelectedTrade] = useState<string>('ALL');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [activeChartTrade, setActiveChartTrade] = useState<string | null>(null);

  // AG Studio theme accent & reset state
  const [accentColor, setAccentColor] = useState<string>('#0284c7');
  const [resetKey, setResetKey] = useState<number>(0);

  // Custom Dark Enterprise Studio Theme
  const customStudioTheme = useMemo(() => {
    return studioTheme.withParams({
      browserColorScheme: 'dark',
      fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      fontSize: 13,
      lineHeight: 16,
      backgroundColor: '#0b1222',
      foregroundColor: '#f8fafc',
      textColor: '#f8fafc',
      subtleTextColor: '#94a3b8',
      borderColor: '#1e293b',
      borderWidth: 1,
      borderRadius: 8,
      accentColor: accentColor,

      // Studio canvas & wrapper
      studioCanvasBackgroundColor: '#070d1a',
      studioCanvasFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      studioCanvasPadding: 16,
      studioWrapperBackgroundColor: '#0b1222',
      studioWrapperBorder: 'solid 1px #1e293b',
      studioWrapperBorderRadius: 10,

      // Panels (Sidebar, Toolbars, Drawers)
      studioPanelContainerBackgroundColor: '#0b1222',
      studioPanelContainerBorder: 'solid 1px #1e293b',
      studioPanelWidth: 260,
      studioPanelMinWidth: 200,
      studioPanelMaxWidth: 420,
      studioPanelDividerColor: '#1e293b',
      studioPanelDividerActiveColor: accentColor,
      studioPanelHeaderFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      studioPanelHeaderFontSize: 13,
      studioPanelHeaderFontWeight: 'bold',
      studioPanelGroupBackgroundColor: '#0f172a',
      studioPanelGroupTitleBarTextColor: '#e2e8f0',
      studioPanelSectionBorderColor: '#1e293b',

      // Buttons & toggles
      studioToggleButtonActiveBackgroundColor: accentColor,
      studioToggleButtonActiveBorderColor: accentColor,
      studioToggleButtonActiveColor: '#ffffff',

      // Widgets
      studioWidgetBackgroundColor: '#0f172a',
      studioWidgetBorder: 'solid 1px #1e293b',
      studioWidgetBorderRadius: 10,
      studioWidgetPadding: 12,
      studioWidgetTitleFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      studioWidgetTitleFontSize: 14,
      studioWidgetTitleFontWeight: 'bold',
      studioWidgetTitleTextColor: '#f8fafc',
      studioWidgetSubtitleFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      studioWidgetSubtitleFontSize: 11,
      studioWidgetSubtitleTextColor: '#94a3b8',
      studioWidgetCaptionFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      studioWidgetCaptionFontSize: 11,
      studioWidgetCaptionTextColor: '#64748b',
      studioValueWidgetFontSize: 28,

      // Charts
      chartFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      chartFontSize: 11,
      chartTextColor: '#cbd5e1',
      chartSubtleTextColor: '#64748b',
      chartAxisLineColor: '#334155',
      chartGridLineColor: '#1e293b',
      chartTooltipBackgroundColor: '#0f172a',
      chartTooltipTextColor: '#f8fafc',
      chartTooltipBorder: 'solid 1px #334155',
      chartPaletteFills1Color: accentColor,
      chartPaletteFills2Color: '#10b981',
      chartPaletteFills3Color: '#8b5cf6',
      chartPaletteFills4Color: '#f59e0b',
      chartPaletteFills5Color: '#06b6d4',
      chartPaletteFills6Color: '#ec4899',
      chartPaletteStrokes1Color: '#38bdf8',
      chartPaletteStrokes2Color: '#34d399',
      chartPaletteStrokes3Color: '#a78bfa',
      chartPaletteStrokes4Color: '#fbbf24',
      chartPaletteStrokes5Color: '#22d3ee',
      chartPaletteStrokes6Color: '#f472b6',

      // Grid
      gridRowHeight: 40,
      gridHeaderHeight: 38,
      gridHeaderBackgroundColor: '#131e32',
      gridHeaderTextColor: '#94a3b8',
      gridHeaderFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      gridHeaderFontSize: 11,
      gridHeaderFontWeight: 'bold',
      gridDataFontSize: 12,
      gridFontFamily: 'Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif',
      gridRowBorder: 'solid 1px #1e293b',
      gridHeaderRowBorder: 'solid 1px #1e293b',
      gridAccentColor: accentColor,
    });
  }, [accentColor]);

  // Copy helper
  const handleCopy = (text: string, key: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  // Simulate refresh
  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 600);
  };

  // Export CSV
  const handleExportCsv = () => {
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

  // Dynamic metrics computed from real state
  const totalMrr = useMemo(() => {
    return transactions.reduce((acc, t) => acc + (t.status === 'ACTIVE_STREAMING' ? t.monthly_amount : 0), 0);
  }, [transactions]);

  const activeLinesCount = useMemo(() => {
    return transactions.filter((t) => t.status === 'ACTIVE_STREAMING').length;
  }, [transactions]);

  const totalAutonomousGmv = useMemo(() => {
    return tradeImpactData.reduce((acc, d) => acc + (d.annualized_gmv ?? d.recovered_revenue ?? 0), 0);
  }, [tradeImpactData]);

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

  // 24-Hour Autonomous A2A Settlement & Mandate Stream
  const hourlyA2aStream = [
    { hour: '00:00', settled: 2, mandates: 2, volume: 159.98 },
    { hour: '02:00', settled: 1, mandates: 1, volume: 79.99 },
    { hour: '04:00', settled: 3, mandates: 3, volume: 239.97 },
    { hour: '06:00', settled: 7, mandates: 8, volume: 559.93 },
    { hour: '08:00', settled: 17, mandates: 18, volume: 1359.83 },
    { hour: '10:00', settled: 26, mandates: 28, volume: 2079.74 },
    { hour: '12:00', settled: 32, mandates: 34, volume: 2559.68 },
    { hour: '14:00', settled: 28, mandates: 29, volume: 2239.72 },
    { hour: '16:00', settled: 21, mandates: 22, volume: 1679.79 },
    { hour: '18:00', settled: 14, mandates: 14, volume: 1119.86 },
    { hour: '20:00', settled: 6, mandates: 6, volume: 479.94 },
    { hour: '22:00', settled: 3, mandates: 3, volume: 239.97 },
  ];

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
              Autonomous M2M Telephony Fleet &bull; Telnyx 10DLC Wholesale &bull; PayPal Subscriptions &bull; Florida LATA 952/953
            </div>
          </div>
        </div>

        {/* View Mode Toggle: Command Center vs AG Studio */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{ display: 'flex', backgroundColor: '#1e293b', padding: '3px', borderRadius: '8px', border: '1px solid #334155' }}>
            <button
              onClick={() => setSubView('command-center')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: subView === 'command-center' ? '#0284c7' : 'transparent',
                color: subView === 'command-center' ? '#fff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <BarChart3 size={14} /> Mission Control
            </button>
            <button
              onClick={() => setSubView('ag-studio')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                backgroundColor: subView === 'ag-studio' ? '#0284c7' : 'transparent',
                color: subView === 'ag-studio' ? '#fff' : '#94a3b8',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <Layers size={14} /> AG Studio Report Studio
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
            <Sliders size={14} /> Simulate A2A Purchase
          </button>
        </div>
      </div>

      {/* VIEW BRANCH: AG STUDIO VIEW (ENTERPRISE REPORT STUDIO) */}
      {subView === 'ag-studio' && (
        <div className="ag-studio-frame" style={{ margin: '16px 20px', display: 'flex', flexDirection: 'column' }}>
          {/* Studio Control Header */}
          <div className="ag-studio-control-bar">
            {/* Left: Studio Identity & Live Badge */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#10b981', boxShadow: '0 0 10px #10b981' }} />
                <span style={{ fontSize: '12px', fontWeight: 800, letterSpacing: '0.04em', color: '#f8fafc' }}>
                  AG STUDIO ENTERPRISE v3.0
                </span>
              </div>
              <div style={{ width: '1px', height: '18px', backgroundColor: '#334155' }} />
              <div>
                <div style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  Autonomous Telephony &amp; A2A Commerce Report
                  <span style={{ fontSize: '10px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', padding: '1px 6px', borderRadius: '4px', border: '1px solid rgba(56, 189, 248, 0.3)' }}>
                    LIVE IN-MEMORY
                  </span>
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                  3 Live Datasets &bull; 14 Active Carrier Subscriptions &bull; 10DLC KYC Attestation
                </div>
              </div>
            </div>

            {/* Center: Accent Palette Selector */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#0f172a', padding: '4px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>Palette:</span>
              {[
                { label: 'Cyber Blue', color: '#0284c7' },
                { label: 'Emerald', color: '#10b981' },
                { label: 'Neon Violet', color: '#8b5cf6' },
              ].map((p) => (
                <button
                  key={p.color}
                  onClick={() => setAccentColor(p.color)}
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    backgroundColor: p.color,
                    border: accentColor === p.color ? '2px solid #ffffff' : '1px solid transparent',
                    boxShadow: accentColor === p.color ? `0 0 8px ${p.color}` : 'none',
                    cursor: 'pointer',
                    padding: 0,
                    transition: 'all 0.15s ease',
                  }}
                  title={`Switch theme accent to ${p.label}`}
                />
              ))}
            </div>

            {/* Right: Studio Controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {/* Mode Switcher */}
              <div style={{ display: 'flex', backgroundColor: '#0f172a', padding: '3px', borderRadius: '8px', border: '1px solid #1e293b' }}>
                <button
                  onClick={() => onSetStudioMode('view')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '5px 12px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: studioMode === 'view' ? accentColor : 'transparent',
                    color: studioMode === 'view' ? '#fff' : '#94a3b8',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <Eye size={12} /> Executive View
                </button>
                <button
                  onClick={() => onSetStudioMode('edit')}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '5px 12px',
                    borderRadius: '6px',
                    border: 'none',
                    backgroundColor: studioMode === 'edit' ? accentColor : 'transparent',
                    color: studioMode === 'edit' ? '#fff' : '#94a3b8',
                    fontSize: '11px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <Edit3 size={12} /> Drag &amp; Drop Editor
                </button>
              </div>

              {/* Reset Layout */}
              <button
                onClick={() => setResetKey((k) => k + 1)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  color: '#cbd5e1',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                title="Reset report canvas to default layout"
              >
                <RefreshCw size={12} /> Reset Canvas
              </button>

              {/* Export CSV */}
              <button
                onClick={handleExportCsv}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  color: '#38bdf8',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Download size={12} /> Export CSV
              </button>
            </div>
          </div>

          {/* Studio Canvas Embed */}
          <div style={{ flex: 1, minHeight: '660px', height: 'calc(100vh - 220px)', position: 'relative', overflow: 'hidden' }}>
            <AgStudio
              key={`studio-${accentColor}-${resetKey}`}
              data={studioData}
              mode={studioMode}
              initialState={initialDashboardState}
              theme={customStudioTheme}
              style={{ width: '100%', height: '100%' }}
            />
          </div>

          {/* Studio Footer Status */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 18px',
              backgroundColor: '#0b1222',
              borderTop: '1px solid #1e293b',
              fontSize: '11px',
              color: '#64748b',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <span>Telemetry: <strong style={{ color: '#38bdf8' }}>$1,119.86/mo MRR</strong></span>
              <span>&bull;</span>
              <span>Ingress Shield: <strong style={{ color: '#34d399' }}>99.8% TCPA Protected</strong></span>
              <span>&bull;</span>
              <span>Autonomous GMV: <strong style={{ color: '#38bdf8' }}>${totalAutonomousGmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ARR</strong></span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span>AG Grid &amp; AG Charts Enterprise v3.0</span>
              <span>&bull;</span>
              <span>Model Context Protocol (MCP 2024-11-05)</span>
            </div>
          </div>
        </div>
      )}

      {/* VIEW BRANCH: ENTERPRISE COMMAND CENTER DASHBOARD */}
      {subView === 'command-center' && (
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* 1. TOP STAT CARDS (KPI METRIC DECK) */}
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
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>Total Active Fleet MRR</span>
                <div style={{ width: '32px', height: '32px', borderRadius: '8px', backgroundColor: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CreditCard size={16} />
                </div>
              </div>
              <div style={{ marginTop: '10px' }}>
                <div style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc' }}>
                  ${totalMrr.toFixed(2)}
                  <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}>/mo</span>
                </div>
                <div style={{ fontSize: '11px', color: '#34d399', fontWeight: 600, marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <TrendingUp size={13} /> +32.4% MoM &bull; {activeLinesCount} Active Trunks
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
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>Autonomous Carrier 10DLC Lines</span>
                <div style={{ width: '32px', height: '32px', borderRadius: '8px', backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#34d399', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <PhoneCall size={16} />
                </div>
              </div>
              <div style={{ marginTop: '10px' }}>
                <div style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc' }}>
                  {activeLinesCount} Active Trunks
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                  Telnyx TCR Campaign <strong>CITNRYD</strong> &bull; STIR/SHAKEN A
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
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>Spending Policy &amp; Anti-Tamper Guard</span>
                <div style={{ width: '32px', height: '32px', borderRadius: '8px', backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#34d399', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <ShieldCheck size={16} />
                </div>
              </div>
              <div style={{ marginTop: '10px' }}>
                <div style={{ fontSize: '26px', fontWeight: 800, color: '#34d399' }}>
                  100% Policy Enforced
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>
                  168 HMAC-SHA256 Mandates Verified &bull; 0 Budget Leaks
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
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8' }}>Total Autonomous Settlement (GMV)</span>
                <div style={{ width: '32px', height: '32px', borderRadius: '8px', backgroundColor: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Zap size={16} />
                </div>
              </div>
              <div style={{ marginTop: '10px' }}>
                <div style={{ fontSize: '26px', fontWeight: 800, color: '#f8fafc' }}>
                  ${totalAutonomousGmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  <span style={{ fontSize: '13px', fontWeight: 500, color: '#64748b' }}> ARR</span>
                </div>
                <div style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 600, marginTop: '4px' }}>
                  14 Autonomous Buyer Mandates Cleared &bull; 100% M2M Rails
                </div>
              </div>
            </div>
          </div>

          {/* 2. DUAL VISUAL COMMAND DECK: COMMERCE BY TRADE & 24H INGRESS */}
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
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
                    Autonomous A2A Commerce Volume by Trade ($ ARR)
                  </h4>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                    Recurring contract run-rate negotiated and settled autonomously under policy spending caps
                  </div>
                </div>
                <span style={{ fontSize: '11px', backgroundColor: 'rgba(56, 189, 248, 0.1)', color: '#38bdf8', padding: '3px 8px', borderRadius: '6px', fontWeight: 600 }}>
                  PayPal M2M Rails
                </span>
              </div>

              {/* Bar Chart Visualization */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: 1, justifyContent: 'center' }}>
                {tradeImpactData.map((d) => {
                  const gmv = d.annualized_gmv ?? d.recovered_revenue ?? 0;
                  const maxGmv = 4500;
                  const pct = Math.min(100, Math.round((gmv / maxGmv) * 100));
                  const isHovered = activeChartTrade === d.trade;

                  return (
                    <div
                      key={d.trade}
                      onMouseEnter={() => setActiveChartTrade(d.trade)}
                      onMouseLeave={() => setActiveChartTrade(null)}
                      style={{
                        cursor: 'pointer',
                        padding: '6px 8px',
                        borderRadius: '8px',
                        backgroundColor: isHovered ? 'rgba(30, 41, 59, 0.8)' : 'transparent',
                        transition: 'background-color 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                        <span style={{ fontSize: '12px', fontWeight: 600, color: '#e2e8f0' }}>{d.trade}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                            {d.active_agents ?? 2} agents &bull; <strong style={{ color: '#34d399' }}>{d.mandates_cleared ?? 24} settled</strong>
                          </span>
                          <span style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8' }}>
                            ${gmv.toLocaleString('en-US', { minimumFractionDigits: 2 })} ARR
                          </span>
                        </div>
                      </div>
                      <div style={{ width: '100%', height: '10px', backgroundColor: '#1e293b', borderRadius: '5px', overflow: 'hidden' }}>
                        <div
                          style={{
                            width: `${pct}%`,
                            height: '100%',
                            background:
                              gmv >= 3000
                                ? 'linear-gradient(90deg, #0284c7, #38bdf8)'
                                : 'linear-gradient(90deg, #059669, #10b981)',
                            borderRadius: '5px',
                            transition: 'width 0.6s cubic-bezier(0.4, 0, 0.2, 1)',
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>

              <div style={{ borderTop: '1px solid #1e293b', paddingTop: '12px', marginTop: '14px', display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
                <span>Top Vertical: <strong>Roofing &amp; Storm ($3,839.52 ARR &bull; 4 Agents)</strong></span>
                <span>Fleet Tier: <strong>$79.99/mo &bull; PayPal Subscriptions Rail</strong></span>
              </div>
            </div>

            {/* Chart 2: 24-Hour Telephony Ingress & Call Triage Volume */}
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
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#f8fafc' }}>
                    24h Autonomous A2A Settlement Velocity
                  </h4>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                    Hourly M2M stream: PayPal Subscriptions Settled (Cyan) vs Mandates Evaluated (Violet)
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '10px' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#38bdf8' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: '#0284c7', borderRadius: '2px' }} /> Settled M2M
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#c084fc' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: '#a855f7', borderRadius: '2px' }} /> Mandates Evaluated
                  </span>
                </div>
              </div>

              {/* Time-Series Column Visualization */}
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: '6px', height: '170px', padding: '10px 0', borderBottom: '1px solid #1e293b' }}>
                {hourlyA2aStream.map((h) => {
                  const maxVal = 40;
                  const mandatesHeight = Math.max(6, Math.round((h.mandates / maxVal) * 125));
                  const settledHeight = Math.max(4, Math.round((h.settled / maxVal) * 125));

                  return (
                    <div key={h.hour} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '2px', width: '100%', justifyContent: 'center' }}>
                        {/* Mandates Evaluated Column */}
                        <div
                          style={{
                            width: '45%',
                            height: `${mandatesHeight}px`,
                            backgroundColor: '#a855f7',
                            borderRadius: '2px 2px 0 0',
                            opacity: 0.85,
                          }}
                          title={`${h.hour}: ${h.mandates} spending mandates evaluated`}
                        />
                        {/* Settled Transactions Column */}
                        <div
                          style={{
                            width: '45%',
                            height: `${settledHeight}px`,
                            backgroundColor: '#0284c7',
                            borderRadius: '2px 2px 0 0',
                          }}
                          title={`${h.hour}: ${h.settled} settled M2M ($${h.volume.toFixed(2)})`}
                        />
                      </div>
                      <span style={{ fontSize: '9px', color: '#64748b', marginTop: '6px' }}>{h.hour.slice(0, 2)}</span>
                    </div>
                  );
                })}
              </div>

              <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8' }}>
                <span>Autonomous Rails: <strong>PayPal Subscriptions API + PayPal Vault MIT</strong></span>
                <span style={{ color: '#34d399', fontWeight: 600 }}>100% Cryptographic Match (0 Tamper Events)</span>
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
                  <Layers size={16} /> Autonomous A2A Fleet Ledger
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

            {/* High-Density Data Table */}
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
                <thead>
                  <tr style={{ backgroundColor: '#131e32', borderBottom: '1px solid #1e293b', color: '#94a3b8', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    <th style={{ padding: '10px 14px' }}>Tenant / Txn ID</th>
                    <th style={{ padding: '10px 14px' }}>Status</th>
                    <th style={{ padding: '10px 14px' }}>Contractor &amp; Legal Entity</th>
                    <th style={{ padding: '10px 14px' }}>Trade Vertical</th>
                    <th style={{ padding: '10px 14px' }}>Allocated 10DLC DID</th>
                    <th style={{ padding: '10px 14px' }}>Monthly Rate &amp; Rail</th>
                    <th style={{ padding: '10px 14px' }}>KYC Identity &amp; TCPA</th>
                    <th style={{ padding: '10px 14px' }}>Back-Office</th>
                    <th style={{ padding: '10px 14px', textAlign: 'center' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTransactions.map((t, idx) => {
                    const isActive = t.status === 'ACTIVE_STREAMING';
                    const isMarcus = t.contractor_name === 'Marcus Miller';

                    return (
                      <tr
                        key={t.id}
                        style={{
                          borderBottom: '1px solid #1e293b',
                          backgroundColor: idx % 2 === 0 ? 'rgba(15, 23, 42, 0.4)' : 'transparent',
                          transition: 'background-color 0.15s ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'rgba(30, 41, 59, 0.6)')}
                        onMouseLeave={(e) =>
                          (e.currentTarget.style.backgroundColor = idx % 2 === 0 ? 'rgba(15, 23, 42, 0.4)' : 'transparent')
                        }
                      >
                        {/* Tenant / Txn ID */}
                        <td style={{ padding: '12px 14px', fontFamily: 'monospace', fontWeight: 600, color: '#38bdf8' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span>{t.id}</span>
                            <button
                              onClick={() => handleCopy(t.id, t.id)}
                              style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0 }}
                              title="Copy Transaction ID"
                            >
                              {copiedKey === t.id ? <Check size={12} color="#34d399" /> : <Copy size={12} />}
                            </button>
                          </div>
                          <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>{t.timestamp.slice(11, 19)}</div>
                        </td>

                        {/* Status Badge */}
                        <td style={{ padding: '12px 14px' }}>
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
                        </td>

                        {/* Contractor & Legal Entity */}
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ fontWeight: 700, color: '#f8fafc' }}>
                            {t.contractor_name}
                            {isMarcus && (
                              <span style={{ marginLeft: '6px', fontSize: '9px', backgroundColor: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8', padding: '1px 5px', borderRadius: '4px' }}>
                                CURRENT COPILOT
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>{t.kyc_legal_entity}</div>
                        </td>

                        {/* Trade Vertical */}
                        <td style={{ padding: '12px 14px' }}>
                          <span style={{ fontSize: '11px', backgroundColor: '#1e293b', border: '1px solid #334155', color: '#e2e8f0', padding: '3px 8px', borderRadius: '6px' }}>
                            {t.trade_vertical}
                          </span>
                        </td>

                        {/* Allocated DID Phone */}
                        <td style={{ padding: '12px 14px', fontFamily: 'monospace' }}>
                          {isActive ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <strong style={{ color: '#38bdf8' }}>{t.allocated_did}</strong>
                              <button
                                onClick={() => handleCopy(t.allocated_did, t.allocated_did)}
                                style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 0 }}
                                title="Copy 10DLC DID"
                              >
                                {copiedKey === t.allocated_did ? <Check size={12} color="#34d399" /> : <Copy size={12} />}
                              </button>
                            </div>
                          ) : (
                            <span style={{ color: '#f59e0b', fontStyle: 'italic' }}>Awaiting Approval</span>
                          )}
                          <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>Telnyx Carrier Bound</div>
                        </td>

                        {/* Monthly Rate & Rail */}
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ fontWeight: 700, color: '#f8fafc' }}>
                            ${t.monthly_amount.toFixed(2)}
                            <span style={{ fontSize: '10px', color: '#94a3b8' }}>/mo</span>
                          </div>
                          <div style={{ fontSize: '10px', color: '#38bdf8', marginTop: '2px', fontFamily: 'monospace' }}>
                            {t.paypal_sub_id.startsWith('I-') ? t.paypal_sub_id : 'Pre-Debit Token'}
                          </div>
                        </td>

                        {/* KYC Identity & TCPA */}
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#34d399', fontSize: '11px', fontWeight: 600 }}>
                            <CheckCircle2 size={12} /> {t.kyc_status.includes('VERIFIED') ? 'KYC Verified' : 'Pending KYC'}
                          </div>
                          <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>
                            100% Inbound Locked
                          </div>
                        </td>

                        {/* Back-Office */}
                        <td style={{ padding: '12px 14px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ fontSize: '10px', backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '2px 6px', borderRadius: '4px' }}>
                              Jobber
                            </span>
                            <span style={{ fontSize: '10px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '2px 6px', borderRadius: '4px' }}>
                              QBO #6300
                            </span>
                          </div>
                        </td>

                        {/* Quick Action */}
                        <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                          <button
                            onClick={() => {
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
                              padding: '4px 10px',
                              borderRadius: '6px',
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
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
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
              <span>Showing <strong>{filteredTransactions.length}</strong> of <strong>{transactions.length}</strong> Fleet Tenant Accounts</span>
              <span>Central FL Telephony Trunks &bull; Carrier SLA: 99.999%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
