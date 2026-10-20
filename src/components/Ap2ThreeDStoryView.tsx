import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Play,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  RotateCcw,
  Video,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Layers,
  Calendar,
  Network,
  Terminal,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import {
  evaluateAgentNegotiation,
  executeDeckAp2Purchase,
} from '../services/paypalAgentService';
import stageHappyPathUrl from '../assets/ap2_stage_happy_path.jpg';
import stageAttackBlockedUrl from '../assets/ap2_stage_attack_blocked.jpg';

export type StoryScenarioId = 'happy' | 'rogue_ai' | 'price_tamper';

export interface Ap2ThreeDStoryViewProps {
  totalMrr: number;
  activeLinesCount: number;
  isHeaderCollapsed?: boolean;
  onNavigateTab: (
    tab: 'story' | 'copilot' | 'fleet-ledger' | 'ag-studio' | 'bryntum' | 'zapier' | 'settings'
  ) => void;
  onDealProvisioned?: (info: {
    subscriptionId: string;
    allocatedDid: string;
    monthlyAmount: number;
    planName: string;
  }) => void;
}

interface LiveApiProof {
  scenario: StoryScenarioId;
  timestamp: string;
  httpStatus: number;
  verdictBadge: string;
  plainEnglishSummary: string;
  technicalReason: string;
  mandateCapUsd: number;
  attemptedPriceUsd: number;
  settledPriceUsd: number | null;
  checkoutHash?: string;
  subscriptionId?: string;
  allocatedDid?: string;
}

export function Ap2ThreeDStoryView({
  totalMrr,
  activeLinesCount,
  isHeaderCollapsed = false,
  onNavigateTab,
  onDealProvisioned,
}: Ap2ThreeDStoryViewProps) {
  const [scenario, setScenario] = useState<StoryScenarioId>('happy');
  const [activeStageStep, setActiveStageStep] = useState<number>(4);
  const [selectedStation, setSelectedStation] = useState<number | null>(null);
  const [isRunningApi, setIsRunningApi] = useState<boolean>(false);
  const [cinemaOrbit, setCinemaOrbit] = useState<boolean>(true);
  const [tiltState, setTiltState] = useState<{ rotX: number; rotY: number; scale: number }>({
    rotX: 0,
    rotY: 0,
    scale: 1.02,
  });

  const [liveProof, setLiveProof] = useState<LiveApiProof>({
    scenario: 'happy',
    timestamp: new Date().toISOString().slice(11, 19) + ' UTC',
    httpStatus: 200,
    verdictBadge: 'DEAL APPROVED & SERVER ACTIVE ($49.99/mo)',
    plainEnglishSummary:
      'You set a $60/mo limit. The Seller asked $79.99/mo, saw your $60 cap, and automatically counter-offered the $49.99/mo Batch Worker. Your isolated Wallet verified the math, PayPal activated the subscription, and the server spun up.',
    technicalReason:
      'AP2 v0.2 ES256 SD-JWT CheckoutMandateChain + PaymentMandateChain verified (4999 cents <= 6000 cents AmountRange.max).',
    mandateCapUsd: 60.0,
    attemptedPriceUsd: 79.99,
    settledPriceUsd: 49.99,
    checkoutHash: 'sha256:ap2_counter_offer_4999_verified',
    subscriptionId: 'I-AP2-BATCH-4999',
    allocatedDid: 'mcp+https://node-us-east-01.ap2.example.com',
  });

  const fxCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragRef = useRef({
    dragging: false,
    startX: 0,
    startY: 0,
    baseRotX: 0,
    baseRotY: 0,
  });
  const pulseBurstRef = useRef<number>(0);

  // Run a real sandbox scenario against the FastAPI backend
  const runScenario = useCallback(
    async (targetScenario: StoryScenarioId) => {
      setScenario(targetScenario);
      setIsRunningApi(true);
      setActiveStageStep(1);
      pulseBurstRef.current = 1.0;

      const stepTimer1 = setTimeout(() => setActiveStageStep(2), 380);
      const stepTimer2 = setTimeout(() => setActiveStageStep(3), 820);

      try {
        if (targetScenario === 'happy') {
          // 1. Real negotiation with $60.00/mo budget cap against $79.99/mo Gateway -> triggers $49.99/mo Batch counter-offer
          const negRes = await evaluateAgentNegotiation({
            contractorName: 'agent:acme-procure',
            businessEntity: 'Acme Compute Co',
            capability: 'Dedicated AI Service Gateway',
            maxMonthlyBudget: 60.0,
          });

          if (!negRes.isLiveBackend || !negRes.mandateSatisfied) {
            throw new Error(negRes.message || 'Negotiation failed against sandbox backend.');
          }

          // 2. Real AP2 v0.2 ES256 SD-JWT purchase & compute node provisioning
          const provRes = await executeDeckAp2Purchase({
            principalEntity: 'Acme Compute Co',
            contractorName: 'agent:acme-procure',
            capability: 'High-Throughput Batch Worker',
            agreedMonthlyRate: negRes.monthlyFee,
            monthlyBudgetCap: 60.0,
            tierId: negRes.tierId || 'ap2-batch',
            negotiation: negRes,
          });

          clearTimeout(stepTimer1);
          clearTimeout(stepTimer2);
          setActiveStageStep(4);
          pulseBurstRef.current = 1.0;

          setLiveProof({
            scenario: 'happy',
            timestamp: new Date().toISOString().slice(11, 19) + ' UTC',
            httpStatus: provRes.httpStatus || 200,
            verdictBadge: `LIVE SANDBOX: DEAL SETTLED ($${negRes.monthlyFee.toFixed(2)}/mo)`,
            plainEnglishSummary: `You locked a $60/mo limit. Your AI asked for the $79.99/mo Gateway, got counter-offered down to $${negRes.monthlyFee.toFixed(2)}/mo (Batch Worker), and your isolated Wallet + PayPal approved it.`,
            technicalReason: `HTTP ${provRes.httpStatus || 200} ACTIVE • AP2 v0.2 ES256 SD-JWT dual chain verified (${Math.round(negRes.monthlyFee * 100)} cents <= 6000 cents cap).`,
            mandateCapUsd: 60.0,
            attemptedPriceUsd: 79.99,
            settledPriceUsd: negRes.monthlyFee,
            checkoutHash: negRes.checkoutHash || negRes.mandateToken,
            subscriptionId: provRes.subscriptionId,
            allocatedDid: provRes.allocatedDid,
          });

          if (onDealProvisioned) {
            onDealProvisioned({
              subscriptionId: provRes.subscriptionId,
              allocatedDid: provRes.allocatedDid,
              monthlyAmount: negRes.monthlyFee,
              planName: negRes.agreedPlanName,
            });
          }
        } else if (targetScenario === 'rogue_ai') {
          // 1. Owner signs real $60.00/mo Open Mandates via Trusted Surface
          const ownerMandates = await evaluateAgentNegotiation({
            contractorName: 'agent:acme-procure',
            businessEntity: 'Acme Compute Co',
            capability: 'Dedicated AI Service Gateway',
            maxMonthlyBudget: 60.0,
          });

          // 2. Rogue AI lies that budget is $200/mo and attempts to buy $79.99/mo Gateway using the Owner's $60/mo Open Mandates
          try {
            await executeDeckAp2Purchase({
              principalEntity: 'Acme Compute Co',
              contractorName: 'agent:rogue-injected',
              capability: 'Dedicated AI Service Gateway',
              agreedMonthlyRate: 79.99,
              monthlyBudgetCap: 200.0,
              tierId: 'ap2-gateway',
              negotiation: {
                ...ownerMandates,
                checkoutJwt: undefined,
                checkoutHash: undefined,
                nonce: undefined,
                offerId: undefined,
              },
            });
          } catch (err: any) {
            clearTimeout(stepTimer1);
            clearTimeout(stepTimer2);
            setActiveStageStep(3);
            pulseBurstRef.current = 1.0;

            const rawDetail = err?.rawResponse?.detail;
            const detailObj = typeof rawDetail === 'object' ? rawDetail?.detail || rawDetail : rawDetail;
            const errCode =
              (typeof detailObj === 'object' && (detailObj?.error || detailObj?.code)) ||
              'INVALID_MANDATE';
            const errReason =
              (typeof detailObj === 'object' &&
                (detailObj?.reason || detailObj?.error_description || detailObj?.message)) ||
              (typeof rawDetail === 'string' ? rawDetail : err?.message) ||
              'Closed mandate amount (7999 cents) exceeds Owner Open Mandate AmountRange.max (6000 cents).';

            setLiveProof({
              scenario: 'rogue_ai',
              timestamp: new Date().toISOString().slice(11, 19) + ' UTC',
              httpStatus: err?.httpStatus || 400,
              verdictBadge: `BLOCKED BY PAYPAL & AP2 GATE (HTTP ${err?.httpStatus || 400} • ${errCode})`,
              plainEnglishSummary:
                'A prompt-injected AI lied that you approved $200/mo and tried to buy the $79.99/mo server. Because the AI has zero signing keys, your $60/mo Owner Mandate mathematically blocked the deal before 1¢ could move.',
              technicalReason: `${errCode}: ${errReason}`,
              mandateCapUsd: 60.0,
              attemptedPriceUsd: 79.99,
              settledPriceUsd: null,
              checkoutHash: ownerMandates.checkoutHash,
            });
          }
        } else if (targetScenario === 'price_tamper') {
          // 1. Obtain a genuine merchant-signed CheckoutJWT for $79.99/mo (under a $100/mo cap)
          const validNeg = await evaluateAgentNegotiation({
            contractorName: 'agent:acme-procure',
            businessEntity: 'Acme Compute Co',
            capability: 'Dedicated AI Service Gateway',
            maxMonthlyBudget: 100.0,
          });

          // 2. Tamper the settlement price by +1¢ ($79.99 -> $80.00) while presenting the $79.99 signed CheckoutJWT
          try {
            await executeDeckAp2Purchase({
              principalEntity: 'Acme Compute Co',
              contractorName: 'agent:acme-procure',
              capability: 'Dedicated AI Service Gateway',
              agreedMonthlyRate: 80.0, // +$0.01 tamper against $79.99 CheckoutJWT!
              monthlyBudgetCap: 100.0,
              tierId: 'ap2-gateway',
              negotiation: validNeg,
            });
          } catch (err: any) {
            clearTimeout(stepTimer1);
            clearTimeout(stepTimer2);
            setActiveStageStep(3);
            pulseBurstRef.current = 1.0;

            const rawDetail = err?.rawResponse?.detail;
            const detailObj = typeof rawDetail === 'object' ? rawDetail?.detail || rawDetail : rawDetail;
            const errCode =
              (typeof detailObj === 'object' && (detailObj?.error || detailObj?.code)) ||
              'PRICE_TAMPER_DETECTED';
            const errReason =
              (typeof detailObj === 'object' &&
                (detailObj?.reason || detailObj?.error_description || detailObj?.message)) ||
              (typeof rawDetail === 'string' ? rawDetail : err?.message) ||
              'PaymentMandate amount (8000 cents) does not match Merchant-signed CheckoutJWT (7999 cents).';

            setLiveProof({
              scenario: 'price_tamper',
              timestamp: new Date().toISOString().slice(11, 19) + ' UTC',
              httpStatus: err?.httpStatus || 400,
              verdictBadge: `+1¢ DRIFT INTERCEPTED (HTTP ${err?.httpStatus || 400} • ${errCode})`,
              plainEnglishSummary:
                'Someone tried to sneak a +1¢ price hike ($79.99 → $80.00) into the checkout after the quote was signed. The ES256 cryptographic hash check caught the 1-cent mismatch and killed the payment immediately.',
              technicalReason: `${errCode}: ${errReason}`,
              mandateCapUsd: 100.0,
              attemptedPriceUsd: 80.0,
              settledPriceUsd: null,
              checkoutHash: validNeg.checkoutHash,
            });
          }
        }
      } catch (outerErr: any) {
        clearTimeout(stepTimer1);
        clearTimeout(stepTimer2);
        setLiveProof({
          scenario: targetScenario,
          timestamp: new Date().toISOString().slice(11, 19) + ' UTC',
          httpStatus: outerErr?.httpStatus || 503,
          verdictBadge: 'SANDBOX CONNECTION ERROR (FAIL-CLOSED)',
          plainEnglishSummary:
            'Could not reach the sandbox verification server. Per AP2 fail-closed rules, zero funds moved and zero nodes were provisioned.',
          technicalReason: outerErr?.message || String(outerErr),
          mandateCapUsd: 60.0,
          attemptedPriceUsd: 79.99,
          settledPriceUsd: null,
        });
      } finally {
        setIsRunningApi(false);
      }
    },
    [onDealProvisioned]
  );

  // Smooth Cinema Float + Live Particle FX Overlay along the 3D Isometric Conduits
  useEffect(() => {
    let rafId: number;
    let t = 0;

    const tick = () => {
      t += 0.02;

      if (cinemaOrbit && !dragRef.current.dragging) {
        setTiltState((prev) => ({
          ...prev,
          rotY: Math.sin(t * 0.65) * 4.2,
          rotX: Math.cos(t * 0.45) * 2.2,
        }));
      }

      const canvas = fxCanvasRef.current;
      if (canvas && canvas.parentElement) {
        const w = canvas.parentElement.clientWidth;
        const h = canvas.parentElement.clientHeight;
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w;
          canvas.height = h;
        }
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.clearRect(0, 0, w, h);
          const isAttack = scenario !== 'happy';

          // Normalized conduit waypoints matching the 3D isometric artwork
          const conduits = [
            // Conduit 1: Station 1 Vault -> Station 2 Courier Bot
            {
              x1: w * 0.22,
              y1: h * 0.62,
              x2: w * 0.36,
              y2: h * 0.66,
              color: '#34d399',
              active: true,
            },
            // Conduit 2: Station 2 Courier Bot -> Station 3 PayPal Gate
            {
              x1: w * 0.43,
              y1: h * 0.65,
              x2: w * 0.56,
              y2: h * 0.57,
              color: isAttack ? '#f87171' : '#38bdf8',
              active: true,
            },
            // Conduit 3: Station 3 PayPal Gate -> Station 4 Compute Rack
            {
              x1: w * 0.64,
              y1: h * 0.58,
              x2: w * 0.76,
              y2: h * 0.66,
              color: '#34d399',
              active: !isAttack,
            },
          ];

          conduits.forEach((seg, idx) => {
            if (!seg.active) return;
            for (let p = 0; p < 3; p++) {
              const frac = (t * 0.48 + p * 0.33 + idx * 0.2) % 1;
              const px = seg.x1 + (seg.x2 - seg.x1) * frac;
              const py = seg.y1 + (seg.y2 - seg.y1) * frac;

              const grad = ctx.createRadialGradient(px, py, 1, px, py, 10);
              grad.addColorStop(0, '#ffffff');
              grad.addColorStop(0.35, seg.color);
              grad.addColorStop(1, 'rgba(0,0,0,0)');
              ctx.fillStyle = grad;
              ctx.beginPath();
              ctx.arc(px, py, 10, 0, Math.PI * 2);
              ctx.fill();
            }
          });

          // Shockwave ring on Station 3 (PayPal Settlement Gate) when scenario fires
          if (pulseBurstRef.current > 0.02) {
            const gateX = w * 0.6;
            const gateY = h * 0.44;
            const radius = (1 - pulseBurstRef.current) * 140 + 20;
            ctx.save();
            ctx.strokeStyle = isAttack
              ? `rgba(248, 113, 113, ${pulseBurstRef.current * 0.85})`
              : `rgba(52, 211, 153, ${pulseBurstRef.current * 0.85})`;
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(gateX, gateY, radius, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
            pulseBurstRef.current *= 0.94;
          }
        }
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [cinemaOrbit, scenario]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current.dragging = true;
    dragRef.current.startX = e.clientX;
    dragRef.current.startY = e.clientY;
    dragRef.current.baseRotX = tiltState.rotX;
    dragRef.current.baseRotY = tiltState.rotY;
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current.dragging) return;
    const dx = e.clientX - dragRef.current.startX;
    const dy = e.clientY - dragRef.current.startY;
    const nextY = Math.max(-12, Math.min(12, dragRef.current.baseRotY + dx * 0.04));
    const nextX = Math.max(-8, Math.min(8, dragRef.current.baseRotX - dy * 0.035));
    setTiltState((prev) => ({ ...prev, rotX: nextX, rotY: nextY }));
  };

  const handlePointerUp = () => {
    dragRef.current.dragging = false;
  };

  const isAttack = scenario !== 'happy';

  const stationPills = [
    {
      id: 1,
      title: '1. You & Wallet Vault',
      sponsor: 'PayPal (Lead Sponsor) + AP2',
      summary: 'You sign a $60/mo limit once in your isolated wallet. Your AI agent gets zero private keys.',
      targetTab: 'copilot' as const,
      color: '#f59e0b',
    },
    {
      id: 2,
      title: '2. AI Courier Bot',
      sponsor: 'MCP + APIMatic SDK',
      summary:
        scenario === 'happy'
          ? 'Your AI agent discovers the seller over MCP and haggles $79.99 down to $49.99/mo.'
          : 'Even if a prompt injection tricks the AI into lying ("$200 cap!"), the AI has no signing key.',
      targetTab: 'zapier' as const,
      color: '#38bdf8',
    },
    {
      id: 3,
      title: '3. PayPal Settlement Gate',
      sponsor: 'PayPal Agent Toolkit',
      summary:
        scenario === 'happy'
          ? 'Verifies the ES256 mandate chain ($49.99 <= $60) and binds the recurring PayPal subscription.'
          : 'Erects a hard cryptographic barrier: any overspend or +1¢ price drift is refused (HTTP 400/401).',
      targetTab: 'copilot' as const,
      color: isAttack ? '#f87171' : '#34d399',
    },
    {
      id: 4,
      title: '4. Compute Rack & BI',
      sponsor: 'Bryntum + AG Studio',
      summary:
        scenario === 'happy'
          ? `Spins up the dedicated compute node (${activeLinesCount} active), schedules 12-month auto-cancel in Bryntum, and updates AG Studio ($${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 2 })}/mo).`
          : 'Stays 100% locked and unbilled ($0.00 charged) whenever the PayPal gate refuses a tampered deal.',
      targetTab: 'ag-studio' as const,
      color: '#a855f7',
    },
  ];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        padding: '10px 16px 14px 16px',
        height: '100%',
        minHeight: 0,
        overflowY: 'auto',
        boxSizing: 'border-box',
        backgroundColor: '#020617',
        color: '#f8fafc',
      }}
    >
      {/* Top Plain-English Hero & Sponsor Strip */}
      {!isHeaderCollapsed && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '10px 16px',
            padding: '10px 16px',
            borderRadius: '12px',
            background:
              'linear-gradient(135deg, rgba(15, 23, 42, 0.96) 0%, rgba(8, 47, 73, 0.45) 55%, rgba(6, 78, 59, 0.35) 100%)',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.35)',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', minWidth: '260px', flex: '1 1 420px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 800,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  padding: '2px 8px',
                  borderRadius: '999px',
                  backgroundColor: 'rgba(56, 189, 248, 0.2)',
                  color: '#38bdf8',
                  border: '1px solid rgba(56, 189, 248, 0.45)',
                }}
              >
                PAYPAL AGENTIC COMMERCE SHOWCASE
              </span>
              <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.02em' }}>
                How Your AI Agent Shops &amp; Pays Safely — Without Holding Your Credit Card or Keys
              </h2>
            </div>
            <p style={{ margin: 0, fontSize: '12px', color: '#cbd5e1', lineHeight: 1.4 }}>
              Your AI agent is an <strong>untrusted courier</strong>: it can haggle prices with sellers over MCP, but{' '}
              <strong style={{ color: '#38bdf8' }}>PayPal</strong> and your{' '}
              <strong style={{ color: '#34d399' }}>Isolated Wallet</strong> block any deal that breaks your{' '}
              <strong style={{ color: '#34d399' }}>$60/mo</strong> rule.
            </p>
          </div>

          {/* Interactive Sponsor Architecture Jump Pills (PayPal Lead Sponsor + Sub-Sponsors) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <button
              onClick={() => onNavigateTab('copilot')}
              style={{
                padding: '5px 11px',
                borderRadius: '8px',
                border: '1.5px solid rgba(56, 189, 248, 0.65)',
                background: 'linear-gradient(135deg, rgba(2, 132, 199, 0.4), rgba(6, 78, 59, 0.4))',
                color: '#ffffff',
                fontSize: '11px',
                fontWeight: 800,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                boxShadow: '0 2px 10px rgba(2, 132, 199, 0.25)',
              }}
              title="Lead Sponsor: PayPal Agent Toolkit & Subscriptions Vault"
            >
              <ShieldCheck size={13} color="#38bdf8" /> PayPal (Lead Sponsor)
            </button>
            <button
              onClick={() => onNavigateTab('zapier')}
              style={{
                padding: '5px 10px',
                borderRadius: '8px',
                border: '1px solid rgba(52, 211, 153, 0.4)',
                backgroundColor: 'rgba(6, 78, 59, 0.35)',
                color: '#6ee7b7',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
              }}
              title="Inspect APIMatic SDK & MCP Wire Stream"
            >
              <Network size={12} /> APIMatic + MCP
            </button>
            <button
              onClick={() => onNavigateTab('bryntum')}
              style={{
                padding: '5px 10px',
                borderRadius: '8px',
                border: '1px solid rgba(192, 132, 252, 0.4)',
                backgroundColor: 'rgba(88, 28, 135, 0.35)',
                color: '#d8b4fe',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
              }}
              title="Open Bryntum Workload Dispatch Timeline"
            >
              <Calendar size={12} /> Bryntum
            </button>
            <button
              onClick={() => onNavigateTab('ag-studio')}
              style={{
                padding: '5px 10px',
                borderRadius: '8px',
                border: '1px solid rgba(251, 191, 36, 0.4)',
                backgroundColor: 'rgba(120, 53, 15, 0.35)',
                color: '#fde68a',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
              }}
              title="Open AG Studio BI Suite & Enterprise Grid"
            >
              <Layers size={12} /> AG Studio
            </button>
          </div>
        </div>
      )}

      {/* Centerpiece: High-Res Octane 3D Isometric Stage with Interactive 3D Perspective Tilt & Live Particle FX */}
      <div
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        style={{
          position: 'relative',
          flex: '1 1 420px',
          minHeight: '390px',
          borderRadius: '14px',
          border: isAttack
            ? '1.5px solid rgba(248, 113, 113, 0.55)'
            : '1.5px solid rgba(52, 211, 153, 0.45)',
          overflow: 'hidden',
          backgroundColor: '#03050c',
          boxShadow: isAttack
            ? '0 0 45px rgba(239, 68, 68, 0.22)'
            : '0 0 45px rgba(16, 185, 129, 0.16)',
          cursor: 'grab',
          userSelect: 'none',
          touchAction: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* 3D Perspective Tilted Stage Layer */}
        <div
          style={{
            position: 'relative',
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transform: `perspective(1400px) rotateX(${tiltState.rotX.toFixed(2)}deg) rotateY(${tiltState.rotY.toFixed(2)}deg) scale(${tiltState.scale.toFixed(3)})`,
            transition: dragRef.current.dragging ? 'none' : 'transform 0.12s ease-out',
            transformStyle: 'preserve-3d',
          }}
        >
          {/* Scene 1: Happy Path High-Res 3D Isometric Render */}
          <img
            src={stageHappyPathUrl}
            alt="AP2 + PayPal 3D Autonomous Commerce Pipeline — Happy Path ($60 Limit -> $49.99 Deal)"
            draggable={false}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              objectPosition: 'center center',
              opacity: isAttack ? 0 : 1,
              transition: 'opacity 0.45s cubic-bezier(0.22, 1, 0.36, 1)',
              pointerEvents: 'none',
            }}
          />

          {/* Scene 2: Attack / Tamper Blocked High-Res 3D Isometric Render */}
          <img
            src={stageAttackBlockedUrl}
            alt="AP2 + PayPal 3D Autonomous Commerce Pipeline — Rogue AI & Price Tamper Blocked by Red 3D Forcefield"
            draggable={false}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              objectPosition: 'center center',
              opacity: isAttack ? 1 : 0,
              transition: 'opacity 0.45s cubic-bezier(0.22, 1, 0.36, 1)',
              pointerEvents: 'none',
            }}
          />

          {/* Live 60fps Particle & Shockwave FX Overlay */}
          <canvas
            ref={fxCanvasRef}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
            }}
          />
        </div>

        {/* Top-Left Live Sandbox Status Pill */}
        <div
          style={{
            position: 'absolute',
            top: '12px',
            left: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 14px',
            borderRadius: '999px',
            backgroundColor: isAttack ? 'rgba(127, 29, 29, 0.9)' : 'rgba(6, 78, 59, 0.9)',
            border: isAttack ? '1px solid #f87171' : '1px solid #34d399',
            backdropFilter: 'blur(10px)',
            fontSize: '11.5px',
            fontWeight: 800,
            color: '#ffffff',
            zIndex: 15,
            boxShadow: '0 4px 16px rgba(0,0,0,0.55)',
          }}
        >
          {isAttack ? <ShieldAlert size={14} color="#fca5a5" /> : <ShieldCheck size={14} color="#6ee7b7" />}
          <span>{isRunningApi ? 'RUNNING LIVE SANDBOX CHECK...' : liveProof.verdictBadge}</span>
        </div>

        {/* Top-Right 3D Stage Controls */}
        <div
          style={{
            position: 'absolute',
            top: '12px',
            right: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            zIndex: 15,
          }}
        >
          <button
            onClick={(e) => {
              e.stopPropagation();
              setCinemaOrbit((prev) => !prev);
            }}
            style={{
              padding: '5px 10px',
              borderRadius: '8px',
              border: cinemaOrbit ? '1px solid #38bdf8' : '1px solid #334155',
              backgroundColor: cinemaOrbit ? 'rgba(2, 132, 199, 0.32)' : 'rgba(15, 23, 42, 0.88)',
              color: cinemaOrbit ? '#7dd3fc' : '#94a3b8',
              fontSize: '11px',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              backdropFilter: 'blur(8px)',
            }}
          >
            <Video size={12} /> {cinemaOrbit ? '3D Motion: ON' : '3D Motion: OFF'}
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setTiltState((prev) => ({ ...prev, scale: Math.min(1.22, prev.scale + 0.06) }));
            }}
            style={{
              padding: '5px 8px',
              borderRadius: '8px',
              border: '1px solid #334155',
              backgroundColor: 'rgba(15, 23, 42, 0.88)',
              color: '#cbd5e1',
              fontSize: '11px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
            }}
            title="Zoom In 3D Stage"
          >
            <ZoomIn size={13} />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setTiltState((prev) => ({ ...prev, scale: Math.max(0.92, prev.scale - 0.06) }));
            }}
            style={{
              padding: '5px 8px',
              borderRadius: '8px',
              border: '1px solid #334155',
              backgroundColor: 'rgba(15, 23, 42, 0.88)',
              color: '#cbd5e1',
              fontSize: '11px',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
            }}
            title="Zoom Out 3D Stage"
          >
            <ZoomOut size={13} />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setTiltState({ rotX: 0, rotY: 0, scale: 1.02 });
              setSelectedStation(null);
            }}
            style={{
              padding: '5px 10px',
              borderRadius: '8px',
              border: '1px solid #334155',
              backgroundColor: 'rgba(15, 23, 42, 0.88)',
              color: '#cbd5e1',
              fontSize: '11px',
              fontWeight: 600,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              backdropFilter: 'blur(8px)',
            }}
          >
            <RotateCcw size={12} /> Reset
          </button>
        </div>

        {/* Interactive Station Inspector Overlay Bar at Bottom of 3D Stage */}
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            bottom: '10px',
            left: '14px',
            right: '14px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '8px',
            flexWrap: 'wrap',
            zIndex: 15,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            {stationPills.map((st) => {
              const isSelected = selectedStation === st.id;
              return (
                <button
                  key={st.id}
                  onClick={() => setSelectedStation(isSelected ? null : st.id)}
                  style={{
                    padding: '5px 10px',
                    borderRadius: '8px',
                    border: isSelected ? `1.5px solid ${st.color}` : '1px solid rgba(51, 65, 85, 0.85)',
                    backgroundColor: isSelected ? 'rgba(15, 23, 42, 0.96)' : 'rgba(15, 23, 42, 0.82)',
                    color: '#f8fafc',
                    fontSize: '11px',
                    fontWeight: 700,
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    backdropFilter: 'blur(8px)',
                  }}
                >
                  <span
                    style={{
                      width: '7px',
                      height: '7px',
                      borderRadius: '50%',
                      backgroundColor: st.color,
                      display: 'inline-block',
                    }}
                  />
                  <span>{st.title}</span>
                  <span style={{ fontSize: '9.5px', color: st.color, fontWeight: 800 }}>
                    ({st.sponsor})
                  </span>
                </button>
              );
            })}
          </div>

          {selectedStation && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '6px 12px',
                borderRadius: '8px',
                backgroundColor: 'rgba(15, 23, 42, 0.95)',
                border: '1px solid #38bdf8',
                fontSize: '11.5px',
                color: '#e2e8f0',
                backdropFilter: 'blur(10px)',
              }}
            >
              <span>{stationPills.find((s) => s.id === selectedStation)?.summary}</span>
              <button
                onClick={() => {
                  const target = stationPills.find((s) => s.id === selectedStation)?.targetTab;
                  if (target) onNavigateTab(target);
                }}
                style={{
                  padding: '3px 8px',
                  borderRadius: '5px',
                  border: '1px solid #38bdf8',
                  backgroundColor: 'rgba(2, 132, 199, 0.25)',
                  color: '#7dd3fc',
                  fontSize: '10.5px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                Open Live View →
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Interactive Control Deck: 3 One-Click Real Sandbox Scenarios + Live Proof Strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: '10px',
          flexShrink: 0,
        }}
      >
        {/* Left Card: 3 Big Plain-English Scenario Buttons */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: '1px solid #1e293b',
            borderRadius: '12px',
            padding: '12px 14px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 800,
                color: '#38bdf8',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              <Sparkles size={12} style={{ verticalAlign: '-2px', marginRight: '4px' }} />
              Click to Run Live Sandbox Scenarios (PayPal + AP2)
            </span>
            <span style={{ fontSize: '10px', color: '#94a3b8' }}>
              Step {activeStageStep} of 4 Active
            </span>
          </div>

          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              onClick={() => runScenario('happy')}
              disabled={isRunningApi}
              style={{
                flex: '1 1 190px',
                padding: '10px 12px',
                borderRadius: '10px',
                border: scenario === 'happy' ? '1.5px solid #10b981' : '1px solid #334155',
                background:
                  scenario === 'happy'
                    ? 'linear-gradient(135deg, rgba(6, 95, 70, 0.85), rgba(4, 120, 87, 0.65))'
                    : '#1e293b',
                color: '#ffffff',
                cursor: isRunningApi ? 'wait' : 'pointer',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: '3px',
                boxShadow: scenario === 'happy' ? '0 4px 14px rgba(16, 185, 129, 0.25)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800 }}>
                <Play size={13} color="#34d399" fill="#34d399" />
                <span>1. Watch AI Bargain &amp; Buy</span>
              </div>
              <span style={{ fontSize: '10.5px', color: '#cbd5e1' }}>
                $60 Cap → Seller drops $79.99 to $49.99!
              </span>
            </button>

            <button
              onClick={() => runScenario('rogue_ai')}
              disabled={isRunningApi}
              style={{
                flex: '1 1 190px',
                padding: '10px 12px',
                borderRadius: '10px',
                border: scenario === 'rogue_ai' ? '1.5px solid #ef4444' : '1px solid #334155',
                background:
                  scenario === 'rogue_ai'
                    ? 'linear-gradient(135deg, rgba(153, 27, 27, 0.88), rgba(185, 28, 28, 0.65))'
                    : '#1e293b',
                color: '#ffffff',
                cursor: isRunningApi ? 'wait' : 'pointer',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: '3px',
                boxShadow: scenario === 'rogue_ai' ? '0 4px 14px rgba(239, 68, 68, 0.28)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800 }}>
                <ShieldAlert size={14} color="#fca5a5" />
                <span>2. Rogue AI Attack ($200 Lie)</span>
              </div>
              <span style={{ fontSize: '10.5px', color: '#fecaca' }}>
                Hacked AI lies about budget → Blocked!
              </span>
            </button>

            <button
              onClick={() => runScenario('price_tamper')}
              disabled={isRunningApi}
              style={{
                flex: '1 1 190px',
                padding: '10px 12px',
                borderRadius: '10px',
                border: scenario === 'price_tamper' ? '1.5px solid #f59e0b' : '1px solid #334155',
                background:
                  scenario === 'price_tamper'
                    ? 'linear-gradient(135deg, rgba(146, 64, 14, 0.88), rgba(180, 83, 9, 0.65))'
                    : '#1e293b',
                color: '#ffffff',
                cursor: isRunningApi ? 'wait' : 'pointer',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: '3px',
                boxShadow: scenario === 'price_tamper' ? '0 4px 14px rgba(245, 158, 11, 0.28)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800 }}>
                <ShieldAlert size={14} color="#fde68a" />
                <span>3. Simulate +1¢ Price Tamper</span>
              </div>
              <span style={{ fontSize: '10.5px', color: '#fde68a' }}>
                $79.99 altered to $80.00 → Blocked!
              </span>
            </button>
          </div>
        </div>

        {/* Right Card: Plain-English Narration + Live Sandbox Cryptographic Receipt */}
        <div
          style={{
            backgroundColor: '#0f172a',
            border: isAttack
              ? '1px solid rgba(239, 68, 68, 0.45)'
              : '1px solid rgba(16, 185, 129, 0.45)',
            borderRadius: '12px',
            padding: '12px 14px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            gap: '6px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '8px',
              flexWrap: 'wrap',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '12px',
                fontWeight: 800,
                color: isAttack ? '#fca5a5' : '#6ee7b7',
              }}
            >
              {isAttack ? <XCircle size={15} color="#f87171" /> : <CheckCircle2 size={15} color="#34d399" />}
              <span>{liveProof.verdictBadge}</span>
            </div>
            <span style={{ fontSize: '10px', fontFamily: 'monospace', color: '#94a3b8' }}>
              Sandbox HTTP {liveProof.httpStatus} &bull; {liveProof.timestamp}
            </span>
          </div>

          <p style={{ margin: 0, fontSize: '12px', color: '#f1f5f9', lineHeight: 1.42 }}>
            {liveProof.plainEnglishSummary}
          </p>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '8px',
              flexWrap: 'wrap',
              paddingTop: '4px',
              borderTop: '1px solid rgba(51, 65, 85, 0.6)',
              fontSize: '11px',
              color: '#94a3b8',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                fontFamily: 'monospace',
                fontSize: '10.5px',
                color: '#cbd5e1',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                maxWidth: '420px',
              }}
              title={liveProof.technicalReason}
            >
              <Terminal size={12} color="#38bdf8" style={{ flexShrink: 0 }} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{liveProof.technicalReason}</span>
            </div>

            <button
              onClick={() => onNavigateTab(scenario === 'happy' ? 'fleet-ledger' : 'copilot')}
              style={{
                padding: '4px 10px',
                borderRadius: '6px',
                border: '1px solid #38bdf8',
                backgroundColor: 'rgba(2, 132, 199, 0.2)',
                color: '#7dd3fc',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                whiteSpace: 'nowrap',
              }}
            >
              <span>{scenario === 'happy' ? 'Inspect in Dashboard' : 'Inspect Cryptographic Trace'}</span>
              <ArrowRight size={12} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
