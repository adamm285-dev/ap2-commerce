import { useState, useMemo } from 'react';
import {
  Eye,
  Edit3,
  RefreshCw,
  Sliders,
  ArrowLeft,
} from 'lucide-react';
import { AgStudio } from 'ag-studio-react';
import { studioTheme, type AgDataSourcesDefinition, type AgStudioMode } from 'ag-studio';
import {
  type A2aTransaction,
  initialDashboardState,
} from '../data/telemetryData';

export interface AgStudioReportStudioProps {
  studioData: AgDataSourcesDefinition;
  studioMode: AgStudioMode;
  onSetStudioMode: (mode: AgStudioMode) => void;
  transactions: A2aTransaction[];
  onSimulateClick: () => void;
  onNavigateTab?: (tab: 'copilot' | 'fleet-ledger' | 'ag-studio' | 'bryntum' | 'zapier') => void;
}

export function AgStudioReportStudio({
  studioData,
  studioMode,
  onSetStudioMode,
  transactions,
  onSimulateClick,
  onNavigateTab,
}: AgStudioReportStudioProps) {
  // Theme accent & reset key
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
      chartPaletteFills2Color: '#199e70',
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

  // Derived financial metrics
  const activeLinesCount = transactions.filter((t) => t.status === 'ACTIVE_STREAMING').length;
  const totalMrr = useMemo(() => {
    const raw = transactions
      .filter((t) => t.status === 'ACTIVE_STREAMING')
      .reduce((sum, t) => sum + (t.monthly_amount || 0), 0);
    return Math.round(raw * 100) / 100;
  }, [transactions]);
  const totalAutonomousGmv = useMemo(() => Math.round(totalMrr * 12 * 100) / 100, [totalMrr]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', minHeight: 'calc(100vh - 72px)', backgroundColor: '#020617' }}>
      {/* Studio Control Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 24px',
          backgroundColor: '#0b1222',
          borderBottom: '1px solid #1e293b',
        }}
      >
        {/* Left: Studio Identity & Live Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          {onNavigateTab && (
            <button
              onClick={() => onNavigateTab('copilot')}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                padding: '5px 10px',
                borderRadius: '6px',
                border: '1px solid #334155',
                backgroundColor: '#1e293b',
                color: '#94a3b8',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
              title="Return to Mission Control"
            >
              <ArrowLeft size={13} /> Mission Control
            </button>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: '#199e70', boxShadow: '0 0 10px #199e70' }} />
            <span style={{ fontSize: '12px', fontWeight: 800, letterSpacing: '0.04em', color: '#f8fafc' }}>
              AG STUDIO ENTERPRISE v3.0
            </span>
          </div>
          <div style={{ width: '1px', height: '18px', backgroundColor: '#334155' }} />
          <div>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
              Autonomous Agentic Commerce &amp; Worker Node Report Studio
              <span style={{ fontSize: '10px', backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', padding: '1px 6px', borderRadius: '4px', border: '1px solid rgba(56, 189, 248, 0.3)' }}>
                4 MULTI-TABLE DATASETS
              </span>
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8' }}>
              Transactions &bull; Service Capabilities &bull; Mandate Audits &bull; Worker Node Clusters &bull; {activeLinesCount} Active Subscriptions
            </div>
          </div>
        </div>

        {/* Center: Accent Palette Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#0f172a', padding: '4px 10px', borderRadius: '8px', border: '1px solid #1e293b' }}>
          <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>Palette:</span>
          {[
            { label: 'Cyber Blue', color: '#0284c7' },
            { label: 'Emerald', color: '#199e70' },
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
            title="Reset Studio layout to default"
          >
            <RefreshCw size={12} /> Reset Canvas
          </button>

          {/* Simulate AP2 Purchase Button */}
          <button
            onClick={onSimulateClick}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              background: 'linear-gradient(135deg, #199e70, #059669)',
              color: '#fff',
              fontSize: '11px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 2px 6px rgba(25, 158, 112, 0.3)',
            }}
          >
            <Sliders size={13} /> Simulate AP2
          </button>
        </div>
      </div>

      {/* Studio Canvas Embed */}
      <div style={{ flex: 1, minHeight: '660px', height: 'calc(100vh - 180px)', position: 'relative', overflow: 'hidden' }}>
        <AgStudio
          key={`studio-${resetKey}`}
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
          padding: '8px 24px',
          backgroundColor: '#0b1222',
          borderTop: '1px solid #1e293b',
          fontSize: '11px',
          color: '#64748b',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <span>Telemetry: <strong style={{ color: '#38bdf8' }}>${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mo MRR</strong></span>
          <span>&bull;</span>
          <span>Spending Policy Guard: <strong style={{ color: '#34d399' }}>100% Enforced</strong></span>
          <span>&bull;</span>
          <span>Autonomous GMV: <strong style={{ color: '#38bdf8' }}>${totalAutonomousGmv.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ARR</strong></span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span>AG Studio Enterprise v3.0 &bull; AG Grid Community v36</span>
          <span>&bull;</span>
          <span>Model Context Protocol (MCP 2024-11-05)</span>
        </div>
      </div>
    </div>
  );
}

export default AgStudioReportStudio;
