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
  Cpu,
  Terminal,
} from 'lucide-react';
import {
  evaluateAgentNegotiation,
  executeDeckAp2Purchase,
} from '../services/paypalAgentService';

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

interface StationBillboard {
  id: number;
  stepLabel: string;
  title: string;
  sponsor: string;
  sponsorColor: string;
  plainEnglish: string;
  statusTag: string;
  tone: 'emerald' | 'cyan' | 'amber' | 'red' | 'violet';
  worldX: number;
  worldY: number;
  worldZ: number;
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
  const [isRunningApi, setIsRunningApi] = useState<boolean>(false);
  const [cinemaOrbit, setCinemaOrbit] = useState<boolean>(true);
  const [showConceptArtModal, setShowConceptArtModal] = useState<boolean>(false);
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

  // Canvas & 3D projection refs
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const billboardRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const cameraRef = useRef({
    yaw: 0.0,
    pitch: 0.42,
    zoom: 1.0,
    dragging: false,
    lastX: 0,
    lastY: 0,
  });
  const animStateRef = useRef({
    scenario: 'happy' as StoryScenarioId,
    stepProgress: 1.0, // 0..1 across pipeline
    time: 0,
  });

  useEffect(() => {
    animStateRef.current.scenario = scenario;
  }, [scenario]);

  // Run a real sandbox scenario against the FastAPI backend
  const runScenario = useCallback(
    async (targetScenario: StoryScenarioId) => {
      setScenario(targetScenario);
      setIsRunningApi(true);
      setActiveStageStep(1);
      animStateRef.current.scenario = targetScenario;
      animStateRef.current.stepProgress = 0.08;

      const stepTimer1 = setTimeout(() => {
        setActiveStageStep(2);
        animStateRef.current.stepProgress = 0.38;
      }, 450);

      const stepTimer2 = setTimeout(() => {
        setActiveStageStep(3);
        animStateRef.current.stepProgress = 0.68;
      }, 950);

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
          animStateRef.current.stepProgress = 1.0;

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
              monthlyBudgetCap: 200.0, // AI's prompt-injected lie
              tierId: 'ap2-gateway',
              negotiation: {
                ...ownerMandates,
                // Omit counter-offer checkoutJwt so the AI attempts to close $79.99 against the $60 Open Mandate
                checkoutJwt: undefined,
                checkoutHash: undefined,
                nonce: undefined,
                offerId: undefined,
              },
            });
            // If it somehow didn't throw, report unexpected state
            setLiveProof({
              scenario: 'rogue_ai',
              timestamp: new Date().toISOString().slice(11, 19) + ' UTC',
              httpStatus: 500,
              verdictBadge: 'UNEXPECTED RESPONSE',
              plainEnglishSummary: 'Expected sandbox backend to reject overspend.',
              technicalReason: 'Unexpected response.',
              mandateCapUsd: 60.0,
              attemptedPriceUsd: 79.99,
              settledPriceUsd: null,
            });
          } catch (err: any) {
            clearTimeout(stepTimer1);
            clearTimeout(stepTimer2);
            setActiveStageStep(3);
            animStateRef.current.stepProgress = 0.62;

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
              verdictBadge: `BLOCKED BY WALLET GUARD (HTTP ${err?.httpStatus || 400} • ${errCode})`,
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
            animStateRef.current.stepProgress = 0.62;

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

  // 5 Station Billboards positioned in 3D space
  const stations: StationBillboard[] = [
    {
      id: 1,
      stepLabel: 'STATION 1 • YOU & WALLET',
      title: '1. You Set a $60 Limit',
      sponsor: 'Google AP2 + PayPal',
      sponsorColor: '#34d399',
      plainEnglish:
        scenario === 'price_tamper'
          ? 'You sign a $100/mo rule once. Your AI agent gets zero private keys.'
          : 'You sign a $60/mo rule once. Your AI agent gets zero private keys.',
      statusTag:
        scenario === 'price_tamper'
          ? '✓ $100/mo Rule Locked (ES256)'
          : '✓ $60/mo Rule Locked (ES256)',
      tone: 'emerald',
      worldX: -340,
      worldY: 98,
      worldZ: 0,
    },
    {
      id: 2,
      stepLabel: 'STATION 2 • UNTRUSTED COURIER',
      title:
        scenario === 'happy'
          ? '2. AI Haggles $79 → $49.99'
          : scenario === 'rogue_ai'
          ? '2. Rogue AI Lies: "$200 Cap!"'
          : '2. +1¢ Price Tamper ($80.00)',
      sponsor: 'APIMatic SDK + MCP',
      sponsorColor: '#38bdf8',
      plainEnglish:
        scenario === 'happy'
          ? 'Seller asks $79.99. AI haggles down to $49.99 Batch Worker!'
          : scenario === 'rogue_ai'
          ? 'Prompt injection tricks AI into asking for the $79.99 server.'
          : 'Attacker alters the signed $79.99 quote to $80.00 (+1¢).',
      statusTag:
        scenario === 'happy'
          ? '✓ Counter-Offer: $49.99/mo'
          : scenario === 'rogue_ai'
          ? '⚡ Prompt Injection ($79.99 > $60)'
          : '⚡ Tampered Payload (+1¢ Drift)',
      tone: scenario === 'happy' ? 'cyan' : 'red',
      worldX: -170,
      worldY: 105,
      worldZ: -35,
    },
    {
      id: 3,
      stepLabel: 'STATION 3 • CRYPTO & PAYPAL GATE',
      title:
        scenario === 'happy'
          ? '3. PayPal Gate Stamps Deal'
          : '3. Red Forcefield Blocks It!',
      sponsor: 'PayPal Agent Toolkit',
      sponsorColor: scenario === 'happy' ? '#38bdf8' : '#f87171',
      plainEnglish:
        scenario === 'happy'
          ? '$49.99 fits inside your $60 rule. PayPal locks in subscription!'
          : scenario === 'rogue_ai'
          ? 'STOPPED! $79.99 beats your $60 rule. AI cannot forge your key.'
          : 'STOPPED! $80.00 breaks the ES256 signature on the $79.99 quote.',
      statusTag:
        scenario === 'happy'
          ? '✓ PayPal Vault Bound ($49.99)'
          : `🛑 REFUSED (HTTP ${liveProof.httpStatus || 400})`,
      tone: scenario === 'happy' ? 'emerald' : 'red',
      worldX: 0,
      worldY: 112,
      worldZ: 15,
    },
    {
      id: 4,
      stepLabel: 'STATION 4 • WORKLOAD DISPATCH',
      title:
        scenario === 'happy'
          ? '4. Server Rack Spins Up'
          : '4. Server Stays Locked',
      sponsor: 'Bryntum Scheduler',
      sponsorColor: '#c084fc',
      plainEnglish:
        scenario === 'happy'
          ? 'Dedicated worker node turns on & auto-cancels before Month 13.'
          : 'Zero servers provisioned because the payment gate failed closed.',
      statusTag:
        scenario === 'happy'
          ? '✓ Node Online • 12-Mo Guard'
          : '🔒 Locked (Fail-Closed)',
      tone: scenario === 'happy' ? 'violet' : 'amber',
      worldX: 170,
      worldY: 102,
      worldZ: -25,
    },
    {
      id: 5,
      stepLabel: 'STATION 5 • LIVE BI TELEMETRY',
      title: '5. Live Revenue & Audit',
      sponsor: 'AG Studio + AG Grid',
      sponsorColor: '#fbbf24',
      plainEnglish:
        scenario === 'happy'
          ? `Fleet MRR ($${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 2 })}/mo) & QBO GL 6300 update live.`
          : 'Tamper attempt logged in audit trail; $0.00 charged to your account.',
      statusTag: `${activeLinesCount} Active Nodes • $${totalMrr.toLocaleString('en-US', { minimumFractionDigits: 0 })}/mo`,
      tone: 'amber',
      worldX: 340,
      worldY: 98,
      worldZ: 0,
    },
  ];

  // 60fps 3D Isometric WebGL-style Canvas Renderer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;

    const project3D = (
      x: number,
      y: number,
      z: number,
      w: number,
      h: number,
      yaw: number,
      pitch: number,
      zoom: number
    ) => {
      const cosY = Math.cos(yaw);
      const sinY = Math.sin(yaw);
      const rx = x * cosY - z * sinY;
      const rz = x * sinY + z * cosY;

      const cosP = Math.cos(pitch);
      const sinP = Math.sin(pitch);
      const ry = y * cosP - rz * sinP;
      const rz2 = y * sinP + rz * cosP;

      const fov = 950;
      const dist = 820;
      const scale = (fov / (fov + rz2 + dist)) * zoom * (Math.min(w, 1280) / 1020);
      return {
        x: w * 0.5 + rx * scale,
        y: h * 0.57 - ry * scale,
        scale,
        depth: rz2,
      };
    };

    const drawBox3D = (
      cx: number,
      cy: number,
      cz: number,
      bw: number,
      bh: number,
      bd: number,
      topColor: string,
      leftColor: string,
      rightColor: string,
      strokeColor: string,
      w: number,
      h: number,
      yaw: number,
      pitch: number,
      zoom: number
    ) => {
      const hw = bw / 2;
      const hd = bd / 2;
      const v = [
        project3D(cx - hw, cy, cz - hd, w, h, yaw, pitch, zoom),
        project3D(cx + hw, cy, cz - hd, w, h, yaw, pitch, zoom),
        project3D(cx + hw, cy, cz + hd, w, h, yaw, pitch, zoom),
        project3D(cx - hw, cy, cz + hd, w, h, yaw, pitch, zoom),
        project3D(cx - hw, cy + bh, cz - hd, w, h, yaw, pitch, zoom),
        project3D(cx + hw, cy + bh, cz - hd, w, h, yaw, pitch, zoom),
        project3D(cx + hw, cy + bh, cz + hd, w, h, yaw, pitch, zoom),
        project3D(cx - hw, cy + bh, cz + hd, w, h, yaw, pitch, zoom),
      ];

      ctx.lineWidth = 1.15;
      ctx.strokeStyle = strokeColor;

      // Left/Front face
      ctx.fillStyle = leftColor;
      ctx.beginPath();
      ctx.moveTo(v[3].x, v[3].y);
      ctx.lineTo(v[2].x, v[2].y);
      ctx.lineTo(v[6].x, v[6].y);
      ctx.lineTo(v[7].x, v[7].y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Right face
      ctx.fillStyle = rightColor;
      ctx.beginPath();
      ctx.moveTo(v[1].x, v[1].y);
      ctx.lineTo(v[2].x, v[2].y);
      ctx.lineTo(v[6].x, v[6].y);
      ctx.lineTo(v[5].x, v[5].y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      // Top face
      ctx.fillStyle = topColor;
      ctx.beginPath();
      ctx.moveTo(v[4].x, v[4].y);
      ctx.lineTo(v[5].x, v[5].y);
      ctx.lineTo(v[6].x, v[6].y);
      ctx.lineTo(v[7].x, v[7].y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    };

    const drawRing3D = (
      cx: number,
      cy: number,
      cz: number,
      radius: number,
      color: string,
      lineWidth: number,
      w: number,
      h: number,
      yaw: number,
      pitch: number,
      zoom: number,
      dashed = false
    ) => {
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;
      if (dashed) ctx.setLineDash([6, 5]);
      ctx.beginPath();
      const segs = 36;
      for (let i = 0; i <= segs; i++) {
        const a = (i / segs) * Math.PI * 2;
        const p = project3D(
          cx + Math.cos(a) * radius,
          cy,
          cz + Math.sin(a) * radius,
          w,
          h,
          yaw,
          pitch,
          zoom
        );
        if (i === 0) ctx.moveTo(p.x, p.y);
        else ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
      ctx.restore();
    };

    const render = () => {
      const parent = canvas.parentElement;
      if (parent) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const targetW = parent.clientWidth;
        const targetH = parent.clientHeight;
        if (canvas.width !== Math.floor(targetW * dpr) || canvas.height !== Math.floor(targetH * dpr)) {
          canvas.width = Math.floor(targetW * dpr);
          canvas.height = Math.floor(targetH * dpr);
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      }

      const w = canvas.parentElement?.clientWidth || 960;
      const h = canvas.parentElement?.clientHeight || 420;

      animStateRef.current.time += 0.025;
      const t = animStateRef.current.time;
      const curScenario = animStateRef.current.scenario;
      const isAttack = curScenario !== 'happy';

      if (cinemaOrbit && !cameraRef.current.dragging) {
        cameraRef.current.yaw = Math.sin(t * 0.35) * 0.24;
      }

      const { yaw, pitch, zoom } = cameraRef.current;

      // 1. Deep Obsidian & Volumetric Stage Background
      ctx.clearRect(0, 0, w, h);
      const bgGrad = ctx.createRadialGradient(w * 0.5, h * 0.52, 30, w * 0.5, h * 0.52, w * 0.65);
      bgGrad.addColorStop(
        0,
        isAttack ? 'rgba(45, 12, 24, 0.92)' : 'rgba(12, 32, 54, 0.92)'
      );
      bgGrad.addColorStop(0.55, 'rgba(7, 13, 25, 0.98)');
      bgGrad.addColorStop(1, '#030712');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, w, h);

      // 2. 3D Isometric Perspective Floor Grid
      ctx.lineWidth = 1;
      for (let gx = -480; gx <= 480; gx += 60) {
        const p1 = project3D(gx, -22, -240, w, h, yaw, pitch, zoom);
        const p2 = project3D(gx, -22, 240, w, h, yaw, pitch, zoom);
        ctx.strokeStyle = gx === 0 ? 'rgba(56, 189, 248, 0.22)' : 'rgba(51, 65, 85, 0.26)';
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }
      for (let gz = -240; gz <= 240; gz += 60) {
        const p1 = project3D(-480, -22, gz, w, h, yaw, pitch, zoom);
        const p2 = project3D(480, -22, gz, w, h, yaw, pitch, zoom);
        ctx.strokeStyle = gz === 0 ? 'rgba(56, 189, 248, 0.22)' : 'rgba(51, 65, 85, 0.26)';
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }

      // 3. Glowing Energy Conduit Path Linking the 5 Stations
      const stationCoords = [
        { x: -340, z: 0 },
        { x: -170, z: -35 },
        { x: 0, z: 15 },
        { x: 170, z: -25 },
        { x: 340, z: 0 },
      ];

      for (let i = 0; i < stationCoords.length - 1; i++) {
        const a = project3D(stationCoords[i].x, -12, stationCoords[i].z, w, h, yaw, pitch, zoom);
        const b = project3D(
          stationCoords[i + 1].x,
          -12,
          stationCoords[i + 1].z,
          w,
          h,
          yaw,
          pitch,
          zoom
        );
        const blockedSegment = isAttack && i >= 2;
        ctx.save();
        ctx.strokeStyle = blockedSegment
          ? 'rgba(239, 68, 68, 0.22)'
          : isAttack && i === 1
          ? 'rgba(239, 68, 68, 0.85)'
          : 'rgba(16, 185, 129, 0.72)';
        ctx.lineWidth = blockedSegment ? 2 : 4;
        if (blockedSegment) ctx.setLineDash([6, 6]);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.restore();

        // Flowing energy pulses along active segments
        if (!blockedSegment) {
          const pulseFrac = (t * 0.55 + i * 0.3) % 1;
          const px = stationCoords[i].x + (stationCoords[i + 1].x - stationCoords[i].x) * pulseFrac;
          const pz = stationCoords[i].z + (stationCoords[i + 1].z - stationCoords[i].z) * pulseFrac;
          const pp = project3D(px, -10, pz, w, h, yaw, pitch, zoom);
          ctx.fillStyle = isAttack && i === 1 ? '#f87171' : '#34d399';
          ctx.beginPath();
          ctx.arc(pp.x, pp.y, 4.5 * pp.scale, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // =========================================================================
      // STATION 1: You & Wallet Vault (Google AP2 + PayPal) at (-340, 0)
      // =========================================================================
      drawRing3D(-340, -18, 0, 56, 'rgba(16, 185, 129, 0.55)', 2, w, h, yaw, pitch, zoom);
      drawRing3D(
        -340,
        24 + Math.sin(t * 2) * 3,
        0,
        46,
        'rgba(250, 204, 21, 0.65)',
        1.8,
        w,
        h,
        yaw,
        pitch,
        zoom,
        true
      );
      // Base pedestal
      drawBox3D(
        -340,
        -20,
        0,
        74,
        14,
        74,
        '#064e3b',
        '#022c22',
        '#065f46',
        '#10b981',
        w,
        h,
        yaw,
        pitch,
        zoom
      );
      // Gold/Emerald Vault Cube
      drawBox3D(
        -340,
        -6,
        0,
        52,
        54,
        52,
        '#047857',
        '#065f46',
        '#064e3b',
        '#34d399',
        w,
        h,
        yaw,
        pitch,
        zoom
      );
      // Vault Gold Crown
      drawBox3D(
        -340,
        48,
        0,
        34,
        12,
        34,
        '#f59e0b',
        '#d97706',
        '#b45309',
        '#fde047',
        w,
        h,
        yaw,
        pitch,
        zoom
      );

      // =========================================================================
      // STATION 2: AI Courier Bot Pad + Flying 3D Drone (APIMatic + MCP)
      // =========================================================================
      drawRing3D(-170, -18, -35, 50, 'rgba(56, 189, 248, 0.5)', 2, w, h, yaw, pitch, zoom);
      drawBox3D(
        -170,
        -20,
        -35,
        66,
        12,
        66,
        '#0c4a6e',
        '#082f49',
        '#075985',
        '#38bdf8',
        w,
        h,
        yaw,
        pitch,
        zoom
      );

      // Animated 3D AI Courier Drone flying between Station 2 (-170) and Station 3 (0)
      const droneOsc = (Math.sin(t * 1.6) + 1) * 0.5; // 0..1
      const maxReach = isAttack ? 0.68 : 0.85;
      const droneX = -170 + droneOsc * 145 * maxReach;
      const droneZ = -35 + droneOsc * 42 * maxReach;
      const droneY = 26 + Math.sin(t * 3.8) * 6;

      drawBox3D(
        droneX,
        droneY,
        droneZ,
        36,
        24,
        36,
        isAttack ? '#ef4444' : '#0284c7',
        isAttack ? '#991b1b' : '#0369a1',
        isAttack ? '#7f1d1d' : '#075985',
        isAttack ? '#fca5a5' : '#7dd3fc',
        w,
        h,
        yaw,
        pitch,
        zoom
      );
      // Drone Halo Ring
      drawRing3D(
        droneX,
        droneY + 28,
        droneZ,
        24,
        isAttack ? '#f87171' : '#38bdf8',
        2,
        w,
        h,
        yaw,
        pitch,
        zoom
      );

      // Floating Price Tag on the Drone
      const droneScreen = project3D(droneX, droneY - 12, droneZ, w, h, yaw, pitch, zoom);
      ctx.save();
      ctx.font = 'bold 11px Inter, system-ui, sans-serif';
      const droneTag =
        curScenario === 'happy'
          ? '$49.99 Deal'
          : curScenario === 'rogue_ai'
          ? '$200 Lie ($79.99)'
          : '$80.00 (+1¢)';
      const tagW = ctx.measureText(droneTag).width + 14;
      ctx.fillStyle = isAttack ? 'rgba(153, 27, 27, 0.92)' : 'rgba(6, 95, 70, 0.92)';
      ctx.strokeStyle = isAttack ? '#f87171' : '#34d399';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.roundRect(droneScreen.x - tagW / 2, droneScreen.y - 9, tagW, 18, 5);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(droneTag, droneScreen.x, droneScreen.y);
      ctx.restore();

      // =========================================================================
      // STATION 3: PayPal Settlement Gate (Center, 0, 15)
      // =========================================================================
      const gateStroke = isAttack ? '#f87171' : '#34d399';
      const gateTop = isAttack ? '#991b1b' : '#065f46';
      const gateSide = isAttack ? '#7f1d1d' : '#064e3b';

      drawRing3D(
        0,
        -18,
        15,
        64,
        isAttack ? 'rgba(239, 68, 68, 0.7)' : 'rgba(16, 185, 129, 0.65)',
        2.4,
        w,
        h,
        yaw,
        pitch,
        zoom
      );
      // Left & Right Pillars + Top Arch
      drawBox3D(-26, -20, 15, 16, 78, 22, gateTop, gateSide, gateSide, gateStroke, w, h, yaw, pitch, zoom);
      drawBox3D(26, -20, 15, 16, 78, 22, gateTop, gateSide, gateSide, gateStroke, w, h, yaw, pitch, zoom);
      drawBox3D(0, 58, 15, 72, 14, 26, gateTop, gateSide, gateSide, gateStroke, w, h, yaw, pitch, zoom);

      // If Attack or Tamper: Draw Dramatic 3D Red Hexagonal Forcefield Shield!
      if (isAttack) {
        const shieldCenter = project3D(-22, 24, 15, w, h, yaw, pitch, zoom);
        const pulseR = (48 + Math.sin(t * 6) * 5) * shieldCenter.scale;
        ctx.save();
        const shieldGrad = ctx.createRadialGradient(
          shieldCenter.x,
          shieldCenter.y,
          4,
          shieldCenter.x,
          shieldCenter.y,
          pulseR
        );
        shieldGrad.addColorStop(0, 'rgba(248, 113, 113, 0.55)');
        shieldGrad.addColorStop(0.7, 'rgba(239, 68, 68, 0.28)');
        shieldGrad.addColorStop(1, 'rgba(239, 68, 68, 0.0)');
        ctx.fillStyle = shieldGrad;
        ctx.strokeStyle = '#f87171';
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
          const ang = (i / 6) * Math.PI * 2 + t * 0.8;
          const hx = shieldCenter.x + Math.cos(ang) * pulseR;
          const hy = shieldCenter.y + Math.sin(ang) * pulseR * 0.88;
          if (i === 0) ctx.moveTo(hx, hy);
          else ctx.lineTo(hx, hy);
        }
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.restore();
      } else {
        // Happy Path Emerald Verification Portal Glow
        const portalCenter = project3D(0, 22, 15, w, h, yaw, pitch, zoom);
        const portalGrad = ctx.createRadialGradient(
          portalCenter.x,
          portalCenter.y,
          2,
          portalCenter.x,
          portalCenter.y,
          34 * portalCenter.scale
        );
        portalGrad.addColorStop(0, 'rgba(52, 211, 153, 0.55)');
        portalGrad.addColorStop(1, 'rgba(16, 185, 129, 0.0)');
        ctx.fillStyle = portalGrad;
        ctx.beginPath();
        ctx.arc(portalCenter.x, portalCenter.y, 34 * portalCenter.scale, 0, Math.PI * 2);
        ctx.fill();
      }

      // =========================================================================
      // STATION 4: Compute Node Server Rack (Bryntum Scheduler) at (170, -25)
      // =========================================================================
      drawRing3D(
        170,
        -18,
        -25,
        54,
        isAttack ? 'rgba(148, 163, 184, 0.3)' : 'rgba(192, 132, 252, 0.55)',
        2,
        w,
        h,
        yaw,
        pitch,
        zoom
      );
      drawBox3D(
        170,
        -20,
        -25,
        58,
        74,
        48,
        '#1e1b4b',
        '#0f172a',
        '#1e293b',
        isAttack ? '#475569' : '#a855f7',
        w,
        h,
        yaw,
        pitch,
        zoom
      );
      // Server Blade LED Bars
      for (let b = 0; b < 4; b++) {
        const bladeY = -6 + b * 16;
        const pL = project3D(152, bladeY, -1, w, h, yaw, pitch, zoom);
        const pR = project3D(188, bladeY, -1, w, h, yaw, pitch, zoom);
        ctx.strokeStyle = isAttack ? '#475569' : b === 0 ? '#34d399' : '#38bdf8';
        ctx.lineWidth = 3.2 * pL.scale;
        ctx.beginPath();
        ctx.moveTo(pL.x, pL.y);
        ctx.lineTo(pR.x, pR.y);
        ctx.stroke();
      }

      // =========================================================================
      // STATION 5: Live Revenue Hologram (AG Studio + AG Grid) at (340, 0)
      // =========================================================================
      drawRing3D(340, -18, 0, 56, 'rgba(251, 191, 36, 0.55)', 2, w, h, yaw, pitch, zoom);
      drawBox3D(
        340,
        -20,
        0,
        74,
        12,
        64,
        '#451a03',
        '#27272a',
        '#3f3f46',
        '#f59e0b',
        w,
        h,
        yaw,
        pitch,
        zoom
      );
      // 4 Rising 3D Holographic Revenue Bars
      const barHeights = [26, 40, 52, isAttack ? 34 : 68 + Math.sin(t * 3) * 4];
      const barOffsets = [-22, -7, 8, 23];
      for (let bi = 0; bi < 4; bi++) {
        const isLast = bi === 3;
        drawBox3D(
          340 + barOffsets[bi],
          -8,
          0,
          10,
          barHeights[bi],
          12,
          isLast && !isAttack ? '#34d399' : '#f59e0b',
          isLast && !isAttack ? '#059669' : '#d97706',
          isLast && !isAttack ? '#047857' : '#b45309',
          isLast && !isAttack ? '#6ee7b7' : '#fde047',
          w,
          h,
          yaw,
          pitch,
          zoom
        );
      }

      // Update floating HTML Billboard positions to track 3D monuments
      stations.forEach((st) => {
        const el = billboardRefs.current[st.id];
        if (!el) return;
        const proj = project3D(st.worldX, st.worldY, st.worldZ, w, h, yaw, pitch, zoom);
        el.style.left = `${proj.x}px`;
        el.style.top = `${proj.y}px`;
      });

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animationFrameId);
  }, [cinemaOrbit, scenario, activeLinesCount, totalMrr, liveProof.httpStatus]);

  // Pointer drag / wheel handlers for interactive 3D camera
  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    cameraRef.current.dragging = true;
    cameraRef.current.lastX = e.clientX;
    cameraRef.current.lastY = e.clientY;
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!cameraRef.current.dragging) return;
    const dx = e.clientX - cameraRef.current.lastX;
    const dy = e.clientY - cameraRef.current.lastY;
    cameraRef.current.lastX = e.clientX;
    cameraRef.current.lastY = e.clientY;
    cameraRef.current.yaw = Math.max(-0.85, Math.min(0.85, cameraRef.current.yaw + dx * 0.0055));
    cameraRef.current.pitch = Math.max(0.18, Math.min(0.75, cameraRef.current.pitch + dy * 0.004));
  };

  const handlePointerUp = () => {
    cameraRef.current.dragging = false;
  };

  const isAttack = scenario !== 'happy';

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
      {/* Top Plain-English Hero & Sponsor Ribbon (Collapsible via Header Expand/Collapse) */}
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
                  backgroundColor: 'rgba(16, 185, 129, 0.2)',
                  color: '#34d399',
                  border: '1px solid rgba(16, 185, 129, 0.45)',
                }}
              >
                PLAIN-ENGLISH 3D EXPLAINER
              </span>
              <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: '#f8fafc', letterSpacing: '-0.02em' }}>
                How Your AI Agent Shops &amp; Pays Safely — Without Holding Your Credit Card or Keys
              </h2>
            </div>
            <p style={{ margin: 0, fontSize: '12px', color: '#cbd5e1', lineHeight: 1.4 }}>
              Your AI agent is an <strong>untrusted courier</strong>: it can haggle prices with sellers, but your{' '}
              <strong>Isolated Wallet (AP2 ES256)</strong> and <strong>PayPal</strong> block any deal that breaks your{' '}
              <strong style={{ color: '#34d399' }}>$60/mo</strong> rule.
            </p>
          </div>

          {/* Interactive Sponsor Architecture Jump Pills */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <button
              onClick={() => onNavigateTab('copilot')}
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
              title="Inspect AP2 v0.2 ES256 + PayPal Setup"
            >
              <Cpu size={12} /> AP2 + PayPal Vault
            </button>
            <button
              onClick={() => onNavigateTab('zapier')}
              style={{
                padding: '5px 10px',
                borderRadius: '8px',
                border: '1px solid rgba(56, 189, 248, 0.4)',
                backgroundColor: 'rgba(12, 74, 110, 0.35)',
                color: '#7dd3fc',
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
              <Calendar size={12} /> Bryntum Scheduler
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
              <Layers size={12} /> AG Studio BI
            </button>
          </div>
        </div>
      )}

      {/* Centerpiece: Interactive 3D WebGL-Style Isometric Stage */}
      <div
        style={{
          position: 'relative',
          flex: '1 1 390px',
          minHeight: '370px',
          borderRadius: '14px',
          border: isAttack
            ? '1px solid rgba(248, 113, 113, 0.45)'
            : '1px solid rgba(52, 211, 153, 0.35)',
          overflow: 'hidden',
          backgroundColor: '#030712',
          boxShadow: isAttack
            ? '0 0 40px rgba(239, 68, 68, 0.16)'
            : '0 0 40px rgba(16, 185, 129, 0.12)',
        }}
      >
        <canvas
          ref={canvasRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
          style={{
            width: '100%',
            height: '100%',
            display: 'block',
            cursor: 'grab',
            touchAction: 'none',
          }}
        />

        {/* Top-Left Live Status Banner on the 3D Stage */}
        <div
          style={{
            position: 'absolute',
            top: '12px',
            left: '14px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 12px',
            borderRadius: '999px',
            backgroundColor: isAttack ? 'rgba(127, 29, 29, 0.88)' : 'rgba(6, 78, 59, 0.88)',
            border: isAttack ? '1px solid #f87171' : '1px solid #34d399',
            backdropFilter: 'blur(8px)',
            fontSize: '11px',
            fontWeight: 800,
            color: '#ffffff',
            zIndex: 15,
            boxShadow: '0 4px 14px rgba(0,0,0,0.45)',
          }}
        >
          {isAttack ? <ShieldAlert size={14} color="#fca5a5" /> : <ShieldCheck size={14} color="#6ee7b7" />}
          <span>{isRunningApi ? 'RUNNING LIVE SANDBOX CHECK...' : liveProof.verdictBadge}</span>
        </div>

        {/* Top-Right 3D Camera Controls */}
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
            onClick={() => setCinemaOrbit((prev) => !prev)}
            style={{
              padding: '5px 10px',
              borderRadius: '8px',
              border: cinemaOrbit ? '1px solid #38bdf8' : '1px solid #334155',
              backgroundColor: cinemaOrbit ? 'rgba(2, 132, 199, 0.28)' : 'rgba(15, 23, 42, 0.85)',
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
            <Video size={12} /> {cinemaOrbit ? 'Cinema Orbit: ON' : 'Cinema Orbit: OFF'}
          </button>
          <button
            onClick={() => {
              cameraRef.current.yaw = 0;
              cameraRef.current.pitch = 0.42;
              cameraRef.current.zoom = 1.0;
            }}
            style={{
              padding: '5px 10px',
              borderRadius: '8px',
              border: '1px solid #334155',
              backgroundColor: 'rgba(15, 23, 42, 0.85)',
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
            <RotateCcw size={12} /> Reset View
          </button>
        </div>

        {/* 5 Floating 3D Station Billboards anchored to the 3D Monuments */}
        {stations.map((st) => {
          const borderMap = {
            emerald: 'rgba(52, 211, 153, 0.65)',
            cyan: 'rgba(56, 189, 248, 0.65)',
            amber: 'rgba(251, 191, 36, 0.65)',
            red: 'rgba(248, 113, 113, 0.85)',
            violet: 'rgba(192, 132, 252, 0.65)',
          };
          const badgeBgMap = {
            emerald: 'rgba(6, 95, 70, 0.7)',
            cyan: 'rgba(12, 74, 110, 0.7)',
            amber: 'rgba(120, 53, 15, 0.7)',
            red: 'rgba(153, 27, 27, 0.8)',
            violet: 'rgba(88, 28, 135, 0.7)',
          };
          return (
            <div
              key={st.id}
              ref={(el) => {
                billboardRefs.current[st.id] = el;
              }}
              style={{
                position: 'absolute',
                transform: 'translate(-50%, -100%)',
                width: '182px',
                padding: '8px 10px',
                borderRadius: '10px',
                backgroundColor: 'rgba(15, 23, 42, 0.88)',
                border: `1.5px solid ${borderMap[st.tone]}`,
                boxShadow: '0 8px 20px rgba(0, 0, 0, 0.55)',
                backdropFilter: 'blur(8px)',
                pointerEvents: 'none',
                zIndex: st.id === 3 ? 12 : 10,
                transition: 'border-color 0.25s ease',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '4px',
                  marginBottom: '3px',
                }}
              >
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 800,
                    color: '#94a3b8',
                    letterSpacing: '0.04em',
                  }}
                >
                  {st.stepLabel}
                </span>
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 800,
                    padding: '1px 5px',
                    borderRadius: '4px',
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    color: st.sponsorColor,
                    border: `1px solid ${st.sponsorColor}55`,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {st.sponsor}
                </span>
              </div>
              <div
                style={{
                  fontSize: '12px',
                  fontWeight: 800,
                  color: '#f8fafc',
                  marginBottom: '3px',
                  lineHeight: 1.2,
                }}
              >
                {st.title}
              </div>
              <div
                style={{
                  fontSize: '10.5px',
                  color: '#cbd5e1',
                  lineHeight: 1.32,
                  marginBottom: '5px',
                }}
              >
                {st.plainEnglish}
              </div>
              <div
                style={{
                  fontSize: '10px',
                  fontWeight: 700,
                  padding: '2px 6px',
                  borderRadius: '5px',
                  backgroundColor: badgeBgMap[st.tone],
                  color: '#ffffff',
                  display: 'inline-block',
                }}
              >
                {st.statusTag}
              </div>
            </div>
          );
        })}

        {/* Bottom-Left Helper Hint */}
        <div
          style={{
            position: 'absolute',
            bottom: '10px',
            left: '14px',
            fontSize: '11px',
            color: '#94a3b8',
            backgroundColor: 'rgba(15, 23, 42, 0.78)',
            padding: '4px 10px',
            borderRadius: '6px',
            border: '1px solid rgba(51, 65, 85, 0.6)',
            pointerEvents: 'none',
          }}
        >
          💡 Drag anywhere to rotate 3D stage &bull; Click any scenario below to run a real sandbox verification
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
            <span style={{ fontSize: '11px', fontWeight: 800, color: '#38bdf8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              <Sparkles size={12} style={{ verticalAlign: '-2px', marginRight: '4px' }} />
              Try a Live 3D Story (Calls Real FastAPI Sandbox)
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
                border:
                  scenario === 'happy'
                    ? '1.5px solid #10b981'
                    : '1px solid #334155',
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
                border:
                  scenario === 'rogue_ai'
                    ? '1.5px solid #ef4444'
                    : '1px solid #334155',
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
                border:
                  scenario === 'price_tamper'
                    ? '1.5px solid #f59e0b'
                    : '1px solid #334155',
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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: 800, color: isAttack ? '#fca5a5' : '#6ee7b7' }}>
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

      {showConceptArtModal && (
        <div className="modal-overlay" onClick={() => setShowConceptArtModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close" onClick={() => setShowConceptArtModal(false)}>
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
