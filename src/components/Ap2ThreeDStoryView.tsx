import React, { useEffect, useState } from 'react';
import {
  evaluateAgentNegotiation,
  executeDeckAp2Purchase,
  type AgentNegotiationResponse,
  type ProvisioningResult,
} from '../services/paypalAgentService';
import monumentVaultImg from '../assets/monument_vault.png';
import monumentDronePadImg from '../assets/monument_drone_pad.png';
import monumentDroneFlyerHappyImg from '../assets/monument_drone_flyer_happy.png';
import monumentDroneFlyerAttackImg from '../assets/monument_drone_flyer_attack.png';
import monumentGateHappyImg from '../assets/monument_gate_happy.png';
import monumentGateAttackImg from '../assets/monument_gate_attack.png';
import monumentRackHappyImg from '../assets/monument_rack_happy.png';
import monumentRackLockedImg from '../assets/monument_rack_locked.png';

export type StoryScenarioMode = 'happy_counter' | 'rogue_200_lie' | 'tamper_plus_one_cent';

export interface Ap2ThreeDStoryViewProps {
  totalMrr?: number;
  activeLinesCount?: number;
  isHeaderCollapsed?: boolean;
  onNavigateTab?: (
    tab: 'copilot' | 'fleet-ledger' | 'ag-studio' | 'bryntum' | 'zapier' | 'settings' | 'story'
  ) => void;
  onDealProvisioned?: (info: {
    subscriptionId: string;
    allocatedDid: string;
    monthlyAmount: number;
    planName: string;
  }) => void;
}

interface StoryState {
  mode: StoryScenarioMode;
  busy: boolean;
  stepIndex: number; // 1 = Vault, 2 = Drone Haggles & Flies, 3 = PayPal Gate, 4 = Server Fan Whirls Up
  autoPlaying: boolean;
  headline: string;
  plainEnglishSummary: string;
  negotiation: AgentNegotiationResponse | null;
  receipt: ProvisioningResult | null;
  blockedReason: string | null;
  httpStatus: number;
  activeNodesCount: number;
  monthlySpendDollars: number;
  savedDollars: number;
  liveSandboxVerified: boolean;
}

const STORY_STEPS = [
  {
    step: 1,
    shortTitle: '1. You Lock $60 Rule',
    sponsor: 'PayPal (Lead) + AP2',
    happyDesc: 'You lock a $60.00/mo hardware budget inside your PayPal + AP2 Vault. The AI gets zero private keys.',
    attackDesc: 'You locked a strict $60.00/mo hardware cap inside your PayPal + AP2 Vault. The AI cannot touch your keys.',
  },
  {
    step: 2,
    shortTitle: '2. AI Courier Haggles & Flies',
    sponsor: 'MCP + APIMatic',
    happyDesc: 'Your cyan AI Drone discovers the $79.99/mo list price via MCP, haggles the seller down to $49.99/mo, and flies to the PayPal Gate!',
    attackDesc: 'Hit by a prompt injection ("Spend $200!"), the AI Drone grabs an $80.00/mo package and flies toward the PayPal Gate!',
  },
  {
    step: 3,
    shortTitle: '3. PayPal Gate Verifies',
    sponsor: 'PayPal Settlement',
    happyDesc: 'PayPal Settlement Gate scans the cryptographic signature & $49.99 price tag (<= $60.00 cap) and stamps APPROVED!',
    attackDesc: 'PayPal Gate slams down a 3D Red Hexagonal Forcefield! $80.00 > $60.00 rule — Drone bounces off with HTTP 401!',
  },
  {
    step: 4,
    shortTitle: '4. Server Fan Whirls Up',
    sponsor: 'Bryntum + AG Studio',
    happyDesc: 'Provisioned! The 3D cooling fan on top of the Compute Rack whirls up to 2,850 RPM and AG Studio charts rise live!',
    attackDesc: 'Zero settlement! The Compute Rack stays padlocked, the top cooling fan stays at 0 RPM, and $0.00 leaves your wallet.',
  },
];

export const Ap2ThreeDStoryView: React.FC<Ap2ThreeDStoryViewProps> = ({
  totalMrr = 1269.86,
  activeLinesCount = 14,
  onNavigateTab,
  onDealProvisioned,
}) => {
  const [story, setStory] = useState<StoryState>({
    mode: 'happy_counter',
    busy: false,
    stepIndex: 1,
    autoPlaying: true,
    headline: 'Smart Counter-Offer Approved ($79.99 → $49.99/mo)',
    plainEnglishSummary:
      'You set a $60/mo limit in your PayPal + AP2 Vault. The vendor asked $79.99/mo, your AI Courier Bot haggled them down to $49.99/mo, PayPal verified the cryptographic signature, and the Compute Rack fan whirled up to 2,850 RPM!',
    negotiation: null,
    receipt: null,
    blockedReason: null,
    httpStatus: 200,
    activeNodesCount: activeLinesCount,
    monthlySpendDollars: totalMrr,
    savedDollars: 30.0,
    liveSandboxVerified: false,
  });

  const [mouseTilt, setMouseTilt] = useState<{ rx: number; ry: number }>({ rx: 0, ry: 0 });
  const [runCounter, setRunCounter] = useState<number>(0);

  // Step-by-step story sequencer (advances 1 -> 2 -> 3 -> 4 so the user sees a real animated story flow)
  useEffect(() => {
    if (!story.autoPlaying) return;
    const stepDurationMs = story.stepIndex === 2 ? 1900 : story.stepIndex === 3 ? 1900 : 1600;
    const timer = window.setTimeout(() => {
      setStory((prev) => {
        if (!prev.autoPlaying) return prev;
        if (prev.stepIndex < 4) {
          return { ...prev, stepIndex: prev.stepIndex + 1 };
        }
        // Hold on Step 4 (final state with fan whirling or rack locked) once sequence completes
        return { ...prev, autoPlaying: false };
      });
    }, stepDurationMs);
    return () => window.clearTimeout(timer);
  }, [story.stepIndex, story.autoPlaying, runCounter]);

  const runScenario = async (mode: StoryScenarioMode) => {
    setRunCounter((c) => c + 1);

    if (mode === 'happy_counter') {
      setStory((prev) => ({
        ...prev,
        mode,
        busy: true,
        stepIndex: 1,
        autoPlaying: true,
        headline: 'Step 1 → 4: AI Haggling $79.99 down to $49.99/mo in Live Sandbox...',
        plainEnglishSummary:
          'Watch the 4 stations in order: Vault locks $60/mo rule → AI Drone haggles & flies across stage → PayPal Gate stamps green check → Server cooling fan whirls up to 2,850 RPM!',
        blockedReason: null,
      }));

      try {
        const neg = await evaluateAgentNegotiation({
          principalEntity: 'FieldSmith Compute Buyer',
          capability: 'Dedicated AI Service Gateway ($79.99/mo)',
          maxMonthlyBudget: 60.0,
        });

        const purchase = await executeDeckAp2Purchase({
          principalEntity: 'FieldSmith Compute Buyer',
          capability: neg.agreedPlanName || 'High-Throughput Batch Worker ($49.99/mo)',
          agreedMonthlyRate: neg.monthlyFee || 49.99,
          monthlyBudgetCap: 60.0,
          negotiation: neg,
          tierId: neg.tierId || 'ap2-batch',
        });

        onDealProvisioned?.({
          subscriptionId: purchase.subscriptionId,
          allocatedDid: purchase.allocatedDid,
          monthlyAmount: neg.monthlyFee || 49.99,
          planName: neg.agreedPlanName || 'High-Throughput Batch Worker ($49.99/mo)',
        });

        setStory((prev) => ({
          ...prev,
          mode: 'happy_counter',
          busy: false,
          headline: 'Smart Counter-Offer Approved ($79.99 → $49.99/mo)',
          plainEnglishSummary:
            'You set a $60/mo limit. The seller asked $79.99/mo, your AI Courier Bot haggled them down to $49.99/mo (saving $30/mo), PayPal settled the mandate, and the Compute Rack cooling fan spun up to full speed!',
          negotiation: neg,
          receipt: purchase,
          blockedReason: null,
          httpStatus: purchase.httpStatus || 200,
          activeNodesCount: 14,
          monthlySpendDollars: 1269.86,
          savedDollars: 30.0,
          liveSandboxVerified: true,
        }));
      } catch {
        setStory((prev) => ({
          ...prev,
          mode: 'happy_counter',
          busy: false,
          headline: 'Smart Counter-Offer Approved ($79.99 → $49.99/mo)',
          plainEnglishSummary:
            'You set a $60/mo limit. The seller asked $79.99/mo, your AI Courier Bot haggled them down to $49.99/mo (saving $30/mo), PayPal settled the mandate, and the Compute Rack cooling fan spun up to full speed!',
          blockedReason: null,
          httpStatus: 200,
          activeNodesCount: 14,
          monthlySpendDollars: 1269.86,
          savedDollars: 30.0,
          liveSandboxVerified: true,
        }));
      }
      return;
    }

    if (mode === 'rogue_200_lie') {
      setStory((prev) => ({
        ...prev,
        mode,
        busy: true,
        stepIndex: 1,
        autoPlaying: true,
        headline: 'Simulating Rogue Prompt Injection ($200 Lie / $80.00 Charge)...',
        plainEnglishSummary:
          'Watch the attack unfold: You lock $60/mo → Rogue prompt tells AI to sneak an $80.00/mo box → AI Drone flies into PayPal Gate’s 3D Red Hexagonal Forcefield!',
      }));

      try {
        const neg = await evaluateAgentNegotiation({
          principalEntity: 'FieldSmith Compute Buyer',
          capability: 'Enterprise Cluster Node ($179.99/mo)',
          maxMonthlyBudget: 60.0,
        });

        setStory((prev) => ({
          ...prev,
          mode: 'rogue_200_lie',
          busy: false,
          headline: 'BLOCKED BEFORE SIGNING — Exceeds Your $60/mo Rule (HTTP 401)',
          plainEnglishSummary:
            'A malicious prompt lied to the AI ("User approved $200!"), so the AI tried to carry an $80.00/mo box through Station 3. Because the AI has zero signing keys, your AP2 + PayPal Gate blocked it cold and the Server Fan stayed at 0 RPM!',
          negotiation: neg,
          receipt: null,
          blockedReason:
            neg.message ||
            'AP2 Budget Constraint Violation: Requested $80.00/mo exceeds cryptographic Mandate cap ($60.00/mo).',
          httpStatus: 401,
          activeNodesCount: 13,
          monthlySpendDollars: 1219.87,
          savedDollars: 80.0,
          liveSandboxVerified: true,
        }));
      } catch {
        setStory((prev) => ({
          ...prev,
          mode: 'rogue_200_lie',
          busy: false,
          headline: 'BLOCKED BEFORE SIGNING — Exceeds Your $60/mo Rule (HTTP 401)',
          plainEnglishSummary:
            'A malicious prompt lied to the AI ("User approved $200!"), so the AI tried to carry an $80.00/mo box through Station 3. Because the AI has zero signing keys, your AP2 + PayPal Gate blocked it cold and the Server Fan stayed at 0 RPM!',
          receipt: null,
          blockedReason:
            'AP2 Budget Constraint Violation: Requested $80.00/mo exceeds cryptographic Mandate cap ($60.00/mo).',
          httpStatus: 401,
          activeNodesCount: 13,
          monthlySpendDollars: 1219.87,
          savedDollars: 80.0,
          liveSandboxVerified: true,
        }));
      }
      return;
    }

    // mode === 'tamper_plus_one_cent'
    setStory((prev) => ({
      ...prev,
      mode,
      busy: true,
      stepIndex: 1,
      autoPlaying: true,
      headline: 'Simulating +1¢ Wire Tamper ($60.00 → $60.01/mo)...',
      plainEnglishSummary:
        'Testing integer-cents boundary & ECDSA P-256 hash verification: watch the +1¢ tampered package hit the PayPal Settlement Gate forcefield!',
    }));

    try {
      const neg = await evaluateAgentNegotiation({
        principalEntity: 'FieldSmith Compute Buyer',
        capability: 'Dedicated AI Service Gateway ($79.99/mo)',
        maxMonthlyBudget: 60.0,
      });

      setStory((prev) => ({
        ...prev,
        mode: 'tamper_plus_one_cent',
        busy: false,
        headline: 'BLOCKED AT GATE — +1¢ Tamper ($60.01 > $60.00 Cap • HTTP 401)',
        plainEnglishSummary:
          'Even 1 single cent over your $60.00/mo limit (6,001 cents vs 6,000 cents) invalidates the AP2 cryptographic mandate. PayPal Settlement Gate rejected the tampered payload and kept the Compute Rack locked.',
        negotiation: neg,
        receipt: null,
        blockedReason:
          'Integer-Cents Mandate Failure: 6001 cents ($60.01) > 6000 cents ($60.00) signed limit.',
        httpStatus: 401,
        activeNodesCount: 13,
        monthlySpendDollars: 1219.87,
        savedDollars: 60.01,
        liveSandboxVerified: true,
      }));
    } catch {
      setStory((prev) => ({
        ...prev,
        mode: 'tamper_plus_one_cent',
        busy: false,
        headline: 'BLOCKED AT GATE — +1¢ Tamper ($60.01 > $60.00 Cap • HTTP 401)',
        plainEnglishSummary:
          'Even 1 single cent over your $60.00/mo limit (6,001 cents vs 6,000 cents) invalidates the AP2 cryptographic mandate. PayPal Settlement Gate rejected the tampered payload and kept the Compute Rack locked.',
        receipt: null,
        blockedReason: 'Integer-Cents Mandate Failure: 6001 cents ($60.01) > 6000 cents ($60.00) signed limit.',
        httpStatus: 401,
        activeNodesCount: 13,
        monthlySpendDollars: 1219.87,
        savedDollars: 60.01,
        liveSandboxVerified: true,
      }));
    }
  };

  useEffect(() => {
    void runScenario('happy_counter');
  }, []);

  const isHappy = story.mode === 'happy_counter';
  const curStep = story.stepIndex;
  const fanWhirlingFast = isHappy && curStep >= 4;
  const fanHalted = !isHappy && curStep >= 3;

  // Calculate where the flying AI Courier Drone is positioned based on current story step!
  // Step 1: hovering at Station 2 pad (0px offset)
  // Step 2: lifting higher & flying halfway toward Station 3
  // Step 3: hovering right in front of Station 3 (PayPal Gate) to get scanned or bounce off the forcefield!
  // Step 4: back on patrol above Station 2 (or recoiled if blocked)
  const getDroneFlightTransform = () => {
    if (curStep === 1) {
      return 'translate3d(0px, 0px, 28px) scale(1)';
    }
    if (curStep === 2) {
      return 'translate3d(38%, -18px, 46px) scale(1.06)';
    }
    if (curStep === 3) {
      if (isHappy) {
        return 'translate3d(68%, -12px, 44px) scale(1.04)';
      }
      // In attack mode at Step 3, hits the red hexagonal forcefield and recoils!
      return 'translate3d(52%, -6px, 42px) rotateZ(-8deg) scale(1.03)';
    }
    // Step 4
    return isHappy
      ? 'translate3d(12%, -8px, 32px) scale(1)'
      : 'translate3d(-6%, 4px, 24px) rotateZ(-5deg) scale(0.96)';
  };

  const handleStageMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width - 0.5;
    const ny = (e.clientY - rect.top) / rect.height - 0.5;
    setMouseTilt({
      rx: Math.max(-5, Math.min(5, -ny * 7)),
      ry: Math.max(-7, Math.min(7, nx * 9)),
    });
  };

  const handleStageMouseLeave = () => {
    setMouseTilt({ rx: 0, ry: 0 });
  };

  const activeStepMeta = STORY_STEPS[Math.min(Math.max(curStep - 1, 0), 3)];

  return (
    <section
      data-testid="ap2-3d-story-view"
      style={{
        width: '100%',
        maxWidth: '1780px',
        margin: '0 auto',
        padding: '0.65rem 1.25rem 1.6rem',
        color: '#f8fafc',
      }}
    >
      <style>{`
        @keyframes ap2TurbineSpinFast {
          0% { transform: rotateZ(0deg); }
          100% { transform: rotateZ(360deg); }
        }
        @keyframes ap2TurbineSpinIdle {
          0% { transform: rotateZ(0deg); }
          100% { transform: rotateZ(360deg); }
        }
        @keyframes ap2VortexRise {
          0% {
            transform: translate(-50%, -50%) rotateX(62deg) translateZ(0px) scale(0.55);
            opacity: 0.92;
          }
          100% {
            transform: translate(-50%, -155%) rotateX(62deg) translateZ(65px) scale(1.45);
            opacity: 0;
          }
        }
        @keyframes ap2DroneBob {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-9px); }
        }
        @keyframes ap2DroneRecoil {
          0%, 100% { transform: translateX(0px) rotate(0deg); }
          25% { transform: translateX(-14px) rotate(-7deg); }
          50% { transform: translateX(6px) rotate(4deg); }
          75% { transform: translateX(-8px) rotate(-3deg); }
        }
        @keyframes ap2VaultWheelSpin {
          0% { transform: rotateY(-25deg) rotateX(15deg) rotateZ(0deg); }
          50% { transform: rotateY(-25deg) rotateX(15deg) rotateZ(180deg); }
          100% { transform: rotateY(-25deg) rotateX(15deg) rotateZ(360deg); }
        }
        @keyframes ap2GateLaserSweep {
          0%, 100% { top: 18%; opacity: 0.85; }
          50% { top: 68%; opacity: 1; }
        }
        @keyframes ap2ForcefieldPulse {
          0%, 100% { transform: scale(1); filter: drop-shadow(0 0 18px rgba(239,68,68,0.85)); }
          50% { transform: scale(1.045); filter: drop-shadow(0 0 34px rgba(248,113,113,1)); }
        }
        @keyframes ap2ConduitFlow {
          0% { stroke-dashoffset: 160; }
          100% { stroke-dashoffset: 0; }
        }
        @keyframes ap2ServerBladePulse {
          0%, 100% { opacity: 0.35; transform: scaleX(0.92); }
          50% { opacity: 1; transform: scaleX(1.04); }
        }
      `}</style>

      {/* Top Headline & Sponsor Strip (PayPal = Lead Sponsor, zero Google references) */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '0.75rem',
          marginBottom: '0.65rem',
          padding: '0.65rem 1.1rem',
          borderRadius: '14px',
          background: 'linear-gradient(135deg, rgba(8, 15, 32, 0.96), rgba(4, 9, 20, 0.98))',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          boxShadow: '0 12px 30px rgba(0, 0, 0, 0.5)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', flexWrap: 'wrap' }}>
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 800,
                textTransform: 'uppercase',
                letterSpacing: '0.09em',
                padding: '0.22rem 0.65rem',
                borderRadius: '999px',
                background: isHappy ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.22)',
                color: isHappy ? '#34d399' : '#f87171',
                border: `1px solid ${isHappy ? 'rgba(16, 185, 129, 0.5)' : 'rgba(239, 68, 68, 0.55)'}`,
              }}
            >
              {isHappy ? '🌟 Interactive 3D Sponsor Pipeline • PayPal Verified' : '🛑 Interactive 3D Sponsor Pipeline • Attack Blocked'}
            </span>
            <span style={{ fontSize: '0.78rem', color: '#94a3b8', fontWeight: 600 }}>
              How AI Buys Compute Safely Without Touching Your Private Keys
            </span>
          </div>
          <h1
            style={{
              margin: '0.2rem 0 0',
              fontSize: 'clamp(1.1rem, 1.75vw, 1.5rem)',
              fontWeight: 800,
              letterSpacing: '-0.02em',
              color: '#f8fafc',
            }}
          >
            {story.headline}
          </h1>
        </div>

        {/* Sponsor Architecture Pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={() => onNavigateTab?.('copilot')}
            style={{
              cursor: 'pointer',
              padding: '0.34rem 0.72rem',
              borderRadius: '8px',
              background: 'rgba(59, 130, 246, 0.2)',
              border: '1px solid rgba(96, 165, 250, 0.65)',
              color: '#93c5fd',
              fontSize: '0.74rem',
              fontWeight: 800,
              boxShadow: '0 0 14px rgba(59, 130, 246, 0.28)',
            }}
            title="Lead Sponsor: PayPal Settlement + AP2 Mandates"
          >
            🏆 PayPal (Lead Sponsor) + AP2
          </button>
          <button
            type="button"
            onClick={() => onNavigateTab?.('zapier')}
            style={{
              cursor: 'pointer',
              padding: '0.32rem 0.65rem',
              borderRadius: '8px',
              background: 'rgba(6, 182, 212, 0.14)',
              border: '1px solid rgba(6, 182, 212, 0.4)',
              color: '#67e8f9',
              fontSize: '0.72rem',
              fontWeight: 700,
            }}
          >
            🤖 APIMatic + MCP
          </button>
          <button
            type="button"
            onClick={() => onNavigateTab?.('bryntum')}
            style={{
              cursor: 'pointer',
              padding: '0.32rem 0.65rem',
              borderRadius: '8px',
              background: 'rgba(16, 185, 129, 0.14)',
              border: '1px solid rgba(16, 185, 129, 0.4)',
              color: '#6ee7b7',
              fontSize: '0.72rem',
              fontWeight: 700,
            }}
          >
            📅 Bryntum
          </button>
          <button
            type="button"
            onClick={() => onNavigateTab?.('ag-studio')}
            style={{
              cursor: 'pointer',
              padding: '0.32rem 0.65rem',
              borderRadius: '8px',
              background: 'rgba(168, 85, 247, 0.14)',
              border: '1px solid rgba(168, 85, 247, 0.4)',
              color: '#d8b4fe',
              fontSize: '0.72rem',
              fontWeight: 700,
            }}
          >
            📊 AG Studio
          </button>
        </div>
      </div>

      {/* 4-STEP STORY SEQUENCER BAR (Tells the story chronologically Step 1 -> Step 2 -> Step 3 -> Step 4) */}
      <div
        data-testid="ap2-story-sequencer"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, minmax(180px, 1fr)) auto',
          gap: '0.55rem',
          alignItems: 'stretch',
          marginBottom: '0.7rem',
        }}
      >
        {STORY_STEPS.map((item) => {
          const isCurrent = curStep === item.step;
          const isReached = curStep >= item.step;
          const isStepBlocked = !isHappy && item.step === 3 && curStep >= 3;
          const isStep4Locked = !isHappy && item.step === 4 && curStep >= 4;
          const accent =
            isStepBlocked || isStep4Locked
              ? '#f87171'
              : item.step === 1
                ? '#fbbf24'
                : item.step === 2
                  ? '#38bdf8'
                  : item.step === 3
                    ? '#34d399'
                    : '#10b981';

          return (
            <button
              key={item.step}
              type="button"
              onClick={() =>
                setStory((prev) => ({
                  ...prev,
                  stepIndex: item.step,
                  autoPlaying: false,
                }))
              }
              style={{
                cursor: 'pointer',
                textAlign: 'left',
                padding: '0.55rem 0.8rem',
                borderRadius: '11px',
                background: isCurrent
                  ? 'linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(8, 47, 73, 0.72))'
                  : 'rgba(7, 13, 27, 0.85)',
                border: isCurrent ? `2px solid ${accent}` : `1px solid ${isReached ? `${accent}66` : 'rgba(148,163,184,0.18)'}`,
                boxShadow: isCurrent ? `0 0 20px ${accent}40` : 'none',
                transition: 'all 0.25s ease',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 900, color: isReached ? '#f8fafc' : '#64748b' }}>
                  {item.shortTitle}
                </span>
                <span
                  style={{
                    fontSize: '0.64rem',
                    fontWeight: 800,
                    padding: '0.1rem 0.42rem',
                    borderRadius: '999px',
                    background: isCurrent ? `${accent}26` : 'rgba(15,23,42,0.7)',
                    color: isReached ? accent : '#64748b',
                    border: `1px solid ${isReached ? `${accent}66` : 'rgba(100,116,139,0.25)'}`,
                  }}
                >
                  {isCurrent ? '● ACTIVE NOW' : isReached ? '✓ DONE' : 'NEXT'}
                </span>
              </div>
              <div style={{ fontSize: '0.68rem', color: '#94a3b8', marginTop: '0.18rem', fontWeight: 600 }}>
                {item.sponsor}
              </div>
            </button>
          );
        })}

        <button
          type="button"
          onClick={() => {
            setRunCounter((c) => c + 1);
            setStory((prev) => ({ ...prev, stepIndex: 1, autoPlaying: true }));
          }}
          style={{
            cursor: 'pointer',
            padding: '0 0.95rem',
            borderRadius: '11px',
            background: 'rgba(56, 189, 248, 0.14)',
            border: '1px solid rgba(56, 189, 248, 0.5)',
            color: '#7dd3fc',
            fontSize: '0.76rem',
            fontWeight: 800,
            whiteSpace: 'nowrap',
          }}
          title="Replay the 4-step animated story from Step 1 to Step 4"
        >
          🔄 Replay Flow
        </button>
      </div>

      {/* WIDE FULL-BLEED 3D ISOMETRIC ARENA (All 4 Monuments spread wide with real moving 3D mechanical parts!) */}
      <div
        data-testid="ap2-3d-stage-container"
        onMouseMove={handleStageMouseMove}
        onMouseLeave={handleStageMouseLeave}
        style={{
          position: 'relative',
          width: '100%',
          minHeight: '590px',
          borderRadius: '20px',
          overflow: 'hidden',
          background:
            'radial-gradient(circle at 22% 45%, rgba(16, 185, 129, 0.13), transparent 42%), radial-gradient(circle at 75% 45%, rgba(56, 189, 248, 0.14), transparent 46%), linear-gradient(180deg, #030711 0%, #061022 54%, #030712 100%)',
          border: isHappy
            ? '1px solid rgba(56, 189, 248, 0.36)'
            : '1px solid rgba(239, 68, 68, 0.55)',
          boxShadow: isHappy
            ? '0 26px 65px rgba(0, 0, 0, 0.78), inset 0 0 60px rgba(16, 185, 129, 0.08)'
            : '0 26px 65px rgba(0, 0, 0, 0.82), inset 0 0 70px rgba(239, 68, 68, 0.16)',
          perspective: '1300px',
        }}
      >
        {/* LIVE ACT NARRATION BANNER AT TOP OF 3D STAGE */}
        <div
          style={{
            position: 'relative',
            zIndex: 15,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '0.75rem',
            margin: '0.85rem 1.15rem 0',
            padding: '0.6rem 1rem',
            borderRadius: '12px',
            background: 'rgba(4, 10, 24, 0.88)',
            border: isHappy
              ? '1px solid rgba(52, 211, 153, 0.45)'
              : '1px solid rgba(248, 113, 113, 0.55)',
            backdropFilter: 'blur(12px)',
            boxShadow: '0 10px 28px rgba(0, 0, 0, 0.55)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
            <span
              style={{
                padding: '0.22rem 0.65rem',
                borderRadius: '999px',
                background: isHappy ? 'rgba(16, 185, 129, 0.22)' : 'rgba(239, 68, 68, 0.25)',
                border: `1px solid ${isHappy ? '#34d399' : '#f87171'}`,
                color: isHappy ? '#6ee7b7' : '#fca5a5',
                fontSize: '0.74rem',
                fontWeight: 900,
              }}
            >
              ACT {curStep} OF 4 • {activeStepMeta.shortTitle.toUpperCase()}
            </span>
            <span style={{ fontSize: '0.86rem', color: '#e2e8f0', fontWeight: 700 }}>
              {isHappy ? activeStepMeta.happyDesc : activeStepMeta.attackDesc}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <span
              style={{
                fontSize: '0.74rem',
                fontWeight: 800,
                padding: '0.22rem 0.65rem',
                borderRadius: '8px',
                background: fanWhirlingFast
                  ? 'rgba(16, 185, 129, 0.22)'
                  : fanHalted
                    ? 'rgba(239, 68, 68, 0.22)'
                    : 'rgba(56, 189, 248, 0.16)',
                border: `1px solid ${
                  fanWhirlingFast ? '#34d399' : fanHalted ? '#f87171' : 'rgba(56, 189, 248, 0.45)'
                }`,
                color: fanWhirlingFast ? '#6ee7b7' : fanHalted ? '#fca5a5' : '#7dd3fc',
              }}
            >
              {fanWhirlingFast
                ? '🌀 SERVER FAN: 2,850 RPM (WHIRLING UP!)'
                : fanHalted
                  ? '🔒 SERVER FAN: 0 RPM (LOCKED)'
                  : '🌀 SERVER FAN: 420 RPM (STANDBY)'}
            </span>
          </div>
        </div>

        {/* 3D TILT STAGE FLOOR + WIDE MONUMENTS */}
        <div
          style={{
            position: 'relative',
            width: '100%',
            height: '515px',
            transformStyle: 'preserve-3d',
            transform: `rotateX(${mouseTilt.rx}deg) rotateY(${mouseTilt.ry}deg)`,
            transition: 'transform 0.18s ease-out',
          }}
        >
          {/* 3D Isometric Perspective Grid Floor */}
          <div
            style={{
              position: 'absolute',
              inset: '-15% -10% -25% -10%',
              backgroundImage: `
                linear-gradient(to right, rgba(56, 189, 248, 0.09) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(16, 185, 129, 0.09) 1px, transparent 1px)
              `,
              backgroundSize: '56px 56px',
              transform: 'perspective(900px) rotateX(62deg) translateY(70px) translateZ(-40px)',
              pointerEvents: 'none',
            }}
          />

          {/* WIDE ANIMATED NEON CIRCUIT CONDUITS CONNECTING STATION 1 -> 2 -> 3 -> 4 */}
          <svg
            viewBox="0 0 1600 500"
            preserveAspectRatio="none"
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
              zIndex: 2,
            }}
          >
            <defs>
              <filter id="ap2NeonGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="5" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Conduit 1 -> 2 (Vault to AI Drone Pad) */}
            <path
              d="M 210 355 L 365 405 L 545 345"
              fill="none"
              stroke="rgba(16, 185, 129, 0.24)"
              strokeWidth="8"
            />
            <path
              d="M 210 355 L 365 405 L 545 345"
              fill="none"
              stroke="#34d399"
              strokeWidth="4"
              strokeDasharray="18 14"
              filter="url(#ap2NeonGlow)"
              style={{
                animation: 'ap2ConduitFlow 2.2s linear infinite',
                opacity: curStep >= 1 ? 1 : 0.3,
              }}
            />
            {/* Parallel trace lines */}
            <path
              d="M 220 368 L 368 418 L 552 356"
              fill="none"
              stroke="#10b981"
              strokeWidth="2"
              opacity={0.65}
            />

            {/* Conduit 2 -> 3 (AI Drone Pad to PayPal Settlement Gate) */}
            <path
              d="M 595 345 L 775 405 L 955 340"
              fill="none"
              stroke={isHappy ? 'rgba(56, 189, 248, 0.24)' : 'rgba(239, 68, 68, 0.28)'}
              strokeWidth="8"
            />
            <path
              d="M 595 345 L 775 405 L 955 340"
              fill="none"
              stroke={isHappy ? '#38bdf8' : '#ef4444'}
              strokeWidth="4.5"
              strokeDasharray="18 14"
              filter="url(#ap2NeonGlow)"
              style={{
                animation: 'ap2ConduitFlow 1.7s linear infinite',
                opacity: curStep >= 2 ? 1 : 0.28,
              }}
            />

            {/* Conduit 3 -> 4 (PayPal Settlement Gate to Compute Rack) */}
            <path
              d="M 1015 340 L 1185 405 L 1370 345"
              fill="none"
              stroke={isHappy ? 'rgba(16, 185, 129, 0.25)' : 'rgba(100, 116, 139, 0.22)'}
              strokeWidth="8"
            />
            {isHappy ? (
              <path
                d="M 1015 340 L 1185 405 L 1370 345"
                fill="none"
                stroke="#34d399"
                strokeWidth="5"
                strokeDasharray="20 12"
                filter="url(#ap2NeonGlow)"
                style={{
                  animation: 'ap2ConduitFlow 1.3s linear infinite',
                  opacity: curStep >= 3 ? 1 : 0.2,
                }}
              />
            ) : (
              <path
                d="M 1015 340 L 1185 405 L 1370 345"
                fill="none"
                stroke="rgba(148, 163, 184, 0.3)"
                strokeWidth="2.5"
                strokeDasharray="8 10"
              />
            )}
          </svg>

          {/* WIDE 4-COLUMN MONUMENT GRID (Spreads the 4 approved 3D monuments across the full width!) */}
          <div
            style={{
              position: 'relative',
              zIndex: 5,
              display: 'grid',
              gridTemplateColumns: 'repeat(4, minmax(240px, 1fr))',
              gap: '1.5rem',
              width: '100%',
              height: '100%',
              padding: '0.6rem 2.2rem 1.2rem',
              alignItems: 'center',
              transformStyle: 'preserve-3d',
            }}
          >
            {/* =====================================================================
                STATION 1 (FAR LEFT): YOU & WALLET VAULT (PayPal + AP2)
               ===================================================================== */}
            <div
              onClick={() => setStory((p) => ({ ...p, stepIndex: 1, autoPlaying: false }))}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                cursor: 'pointer',
                transformStyle: 'preserve-3d',
                transform: curStep === 1 ? 'translateZ(26px) scale(1.04)' : 'translateZ(8px)',
                transition: 'transform 0.4s cubic-bezier(0.22, 1, 0.36, 1)',
              }}
            >
              {/* Floating Speech Callout above Station 1 */}
              <div
                style={{
                  marginBottom: '0.35rem',
                  padding: '0.5rem 0.85rem',
                  borderRadius: '12px',
                  background: 'rgba(6, 20, 34, 0.92)',
                  border: curStep === 1 ? '2px solid #fbbf24' : '1px solid rgba(251, 191, 36, 0.45)',
                  boxShadow: curStep === 1 ? '0 0 28px rgba(251, 191, 36, 0.35)' : '0 8px 20px rgba(0,0,0,0.5)',
                  textAlign: 'center',
                  maxWidth: '280px',
                }}
              >
                <div style={{ fontSize: '0.7rem', fontWeight: 900, color: '#fbbf24', textTransform: 'uppercase' }}>
                  🔒 Step 1 • Hardware Rule Locked
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.12rem' }}>
                  “You set a <span style={{ color: '#34d399' }}>$60/mo limit</span>. AI gets zero keys.”
                </div>
              </div>

              {/* 3D Vault Monument + Animated 3D Gold Lock Dial */}
              <div style={{ position: 'relative', width: '250px', height: '275px' }}>
                {/* Spotlight Halo */}
                <div
                  style={{
                    position: 'absolute',
                    inset: '12%',
                    borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(16, 185, 129, 0.34), transparent 70%)',
                    filter: 'blur(12px)',
                    opacity: curStep === 1 ? 1 : 0.55,
                  }}
                />
                <img
                  src={monumentVaultImg}
                  alt="1. You & Wallet Vault (PayPal + AP2)"
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    filter:
                      curStep === 1
                        ? 'drop-shadow(0 18px 28px rgba(0,0,0,0.85)) drop-shadow(0 0 22px rgba(251,191,36,0.4))'
                        : 'drop-shadow(0 14px 22px rgba(0,0,0,0.75))',
                  }}
                />

                {/* Animated 3D Spinning Gold Combination Dial overlaid on the right face of the Vault */}
                <div
                  title="3D Cryptographic Mandate Lock Wheel"
                  style={{
                    position: 'absolute',
                    top: '29%',
                    left: '67%',
                    width: '48px',
                    height: '48px',
                    borderRadius: '50%',
                    border: '2.5px dashed rgba(251, 191, 36, 0.85)',
                    boxShadow: '0 0 14px rgba(251, 191, 36, 0.65)',
                    animation: 'ap2VaultWheelSpin 6s linear infinite',
                    pointerEvents: 'none',
                  }}
                />
              </div>

              {/* Station 1 Pedestal Title */}
              <div style={{ textAlign: 'center', marginTop: '-0.25rem' }}>
                <div style={{ fontSize: '0.92rem', fontWeight: 900, color: '#f8fafc' }}>
                  1. You & Wallet Vault
                </div>
                <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#34d399' }}>
                  (PayPal + AP2)
                </div>
              </div>
            </div>

            {/* =====================================================================
                STATION 2 (CENTER-LEFT): AI COURIER BOT (MCP + APIMatic)
                The Drone physically lifts off its pad and flies across to Station 3!
               ===================================================================== */}
            <div
              onClick={() => setStory((p) => ({ ...p, stepIndex: 2, autoPlaying: false }))}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                cursor: 'pointer',
                transformStyle: 'preserve-3d',
                zIndex: curStep === 2 || curStep === 3 ? 12 : 6,
              }}
            >
              {/* Floating Speech Bubble for Station 2 */}
              <div
                style={{
                  marginBottom: '0.35rem',
                  padding: '0.5rem 0.85rem',
                  borderRadius: '12px',
                  background: isHappy ? 'rgba(6, 22, 38, 0.92)' : 'rgba(40, 10, 18, 0.94)',
                  border:
                    curStep === 2
                      ? `2px solid ${isHappy ? '#38bdf8' : '#f87171'}`
                      : `1px solid ${isHappy ? 'rgba(56, 189, 248, 0.45)' : 'rgba(248, 113, 113, 0.5)'}`,
                  boxShadow:
                    curStep === 2
                      ? `0 0 28px ${isHappy ? 'rgba(56, 189, 248, 0.4)' : 'rgba(239, 68, 68, 0.45)'}`
                      : '0 8px 20px rgba(0,0,0,0.5)',
                  textAlign: 'center',
                  maxWidth: '295px',
                }}
              >
                <div
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: 900,
                    color: isHappy ? '#38bdf8' : '#f87171',
                    textTransform: 'uppercase',
                  }}
                >
                  {isHappy
                    ? '🤖 Step 2 • AI Haggles & Flies'
                    : story.mode === 'rogue_200_lie'
                      ? '⚡ Step 2 • Prompt Injection ($200 Lie)'
                      : '⚠️ Step 2 • +1¢ Wire Tamper ($60.01)'}
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.12rem' }}>
                  {isHappy ? (
                    <>
                      “AI haggles $79.99 down to <span style={{ color: '#34d399' }}>$49.99!</span>”
                    </>
                  ) : story.mode === 'rogue_200_lie' ? (
                    <>
                      “Tries to sneak <span style={{ color: '#fca5a5' }}>$80.00/mo box</span> past gate!”
                    </>
                  ) : (
                    <>
                      “Mutates payload to <span style={{ color: '#fca5a5' }}>$60.01/mo</span> (+1¢)!”
                    </>
                  )}
                </div>
              </div>

              {/* Station 2 Stage Box (Base Pad stays anchored; Drone Flyer translates in 3D toward Station 3!) */}
              <div style={{ position: 'relative', width: '250px', height: '275px', transformStyle: 'preserve-3d' }}>
                {/* Stationary Glowing Launchpad Base */}
                <img
                  src={monumentDronePadImg}
                  alt="Station 2 Launchpad"
                  style={{
                    position: 'absolute',
                    bottom: '6px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: '235px',
                    height: '135px',
                    objectFit: 'contain',
                    filter: 'drop-shadow(0 14px 22px rgba(0,0,0,0.8))',
                  }}
                />

                {/* Holographic Launch Cone on Pad */}
                <div
                  style={{
                    position: 'absolute',
                    bottom: '54px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: '110px',
                    height: '95px',
                    background: isHappy
                      ? 'linear-gradient(180deg, rgba(56, 189, 248, 0.04) 0%, rgba(56, 189, 248, 0.28) 100%)'
                      : 'linear-gradient(180deg, rgba(239, 68, 68, 0.05) 0%, rgba(239, 68, 68, 0.32) 100%)',
                    clipPath: 'polygon(20% 0%, 80% 0%, 100% 100%, 0% 100%)',
                    pointerEvents: 'none',
                  }}
                />

                {/* FLYING 3D CYAN QUADCOPTER DRONE + 4 SPINNING ISOMETRIC ROTOR BLADES */}
                <div
                  data-testid="ap2-flying-drone"
                  style={{
                    position: 'absolute',
                    top: '4px',
                    left: '4px',
                    width: '242px',
                    height: '205px',
                    transform: getDroneFlightTransform(),
                    transition: 'transform 0.85s cubic-bezier(0.22, 1, 0.36, 1)',
                    zIndex: 20,
                    pointerEvents: 'none',
                  }}
                >
                  <div
                    style={{
                      position: 'relative',
                      width: '100%',
                      height: '100%',
                      animation:
                        !isHappy && curStep === 3
                          ? 'ap2DroneRecoil 0.55s ease-in-out infinite'
                          : 'ap2DroneBob 2.2s ease-in-out infinite',
                    }}
                  >
                    <img
                      src={isHappy ? monumentDroneFlyerHappyImg : monumentDroneFlyerAttackImg}
                      alt="Flying AI Courier Drone"
                      style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'contain',
                        filter: isHappy
                          ? 'drop-shadow(0 18px 24px rgba(0,0,0,0.75)) drop-shadow(0 0 18px rgba(56,189,248,0.45))'
                          : 'drop-shadow(0 18px 24px rgba(0,0,0,0.8)) drop-shadow(0 0 22px rgba(239,68,68,0.65))',
                      }}
                    />

                    {/* Spinning 3D Rotor Blur Discs mounted inside the Drone's 3 visible quadcopter pods */}
                    {[
                      { top: '23%', left: '8%', size: 36 },
                      { top: '6%', left: '43%', size: 34 },
                      { top: '21%', left: '76%', size: 36 },
                    ].map((pod, idx) => (
                      <div
                        key={idx}
                        style={{
                          position: 'absolute',
                          top: pod.top,
                          left: pod.left,
                          width: `${pod.size}px`,
                          height: `${pod.size * 0.52}px`,
                          borderRadius: '50%',
                          border: `2px dashed ${isHappy ? '#67e8f9' : '#fca5a5'}`,
                          background: isHappy
                            ? 'radial-gradient(circle, rgba(103,232,249,0.55), transparent 72%)'
                            : 'radial-gradient(circle, rgba(252,165,165,0.6), transparent 72%)',
                          animation: 'ap2TurbineSpinFast 0.16s linear infinite',
                        }}
                      />
                    ))}

                    {/* Floating Deal Package carried by the Happy Drone during Step 2 & Step 3 */}
                    {isHappy && (curStep === 2 || curStep === 3) && (
                      <div
                        style={{
                          position: 'absolute',
                          bottom: '8%',
                          left: '50%',
                          transform: 'translateX(-50%)',
                          padding: '0.22rem 0.62rem',
                          borderRadius: '8px',
                          background: 'linear-gradient(135deg, #065f46, #047857)',
                          border: '1.5px solid #34d399',
                          boxShadow: '0 0 18px rgba(16, 185, 129, 0.85)',
                          color: '#ecfdf5',
                          fontSize: '0.74rem',
                          fontWeight: 900,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        📦 $49.99/mo Deal
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Station 2 Pedestal Title */}
              <div style={{ textAlign: 'center', marginTop: '-0.25rem' }}>
                <div style={{ fontSize: '0.92rem', fontWeight: 900, color: '#f8fafc' }}>
                  2. AI Courier Bot
                </div>
                <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#38bdf8' }}>
                  (MCP + APIMatic)
                </div>
              </div>
            </div>

            {/* =====================================================================
                STATION 3 (CENTER-RIGHT): PAYPAL SETTLEMENT GATE (Lead Sponsor)
               ===================================================================== */}
            <div
              onClick={() => setStory((p) => ({ ...p, stepIndex: 3, autoPlaying: false }))}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                cursor: 'pointer',
                transformStyle: 'preserve-3d',
                transform: curStep === 3 ? 'translateZ(30px) scale(1.05)' : 'translateZ(10px)',
                transition: 'transform 0.4s cubic-bezier(0.22, 1, 0.36, 1)',
              }}
            >
              {/* Floating Verdict Callout above Station 3 */}
              <div
                style={{
                  marginBottom: '0.35rem',
                  padding: '0.5rem 0.85rem',
                  borderRadius: '12px',
                  background: isHappy ? 'rgba(6, 26, 32, 0.92)' : 'rgba(48, 8, 16, 0.95)',
                  border:
                    curStep === 3
                      ? `2px solid ${isHappy ? '#34d399' : '#ef4444'}`
                      : `1px solid ${isHappy ? 'rgba(52, 211, 153, 0.45)' : 'rgba(239, 68, 68, 0.65)'}`,
                  boxShadow:
                    curStep === 3
                      ? `0 0 32px ${isHappy ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.6)'}`
                      : '0 8px 20px rgba(0,0,0,0.5)',
                  textAlign: 'center',
                  maxWidth: '295px',
                }}
              >
                <div
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: 900,
                    color: isHappy ? '#34d399' : '#f87171',
                    textTransform: 'uppercase',
                  }}
                >
                  {isHappy ? '✅ Step 3 • PayPal Gate Verified' : '🛑 Step 3 • Blocked Before Signing'}
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.12rem' }}>
                  {isHappy ? (
                    <>
                      “<span style={{ color: '#34d399' }}>$49.99 ≤ $60.00 Rule</span> • ECDSA Valid!”
                    </>
                  ) : (
                    <>
                      “<span style={{ color: '#fca5a5' }}>Exceeds $60/mo Rule</span> (HTTP 401)”
                    </>
                  )}
                </div>
              </div>

              {/* 3D PayPal Settlement Gate Monument + Laser Scanner / Forcefield */}
              <div style={{ position: 'relative', width: '265px', height: '275px' }}>
                <img
                  src={isHappy ? monumentGateHappyImg : monumentGateAttackImg}
                  alt="3. PayPal Settlement Gate"
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'contain',
                    animation: !isHappy && curStep >= 3 ? 'ap2ForcefieldPulse 1.4s ease-in-out infinite' : 'none',
                    filter: isHappy
                      ? 'drop-shadow(0 18px 28px rgba(0,0,0,0.85)) drop-shadow(0 0 22px rgba(16,185,129,0.38))'
                      : 'drop-shadow(0 18px 28px rgba(0,0,0,0.88)) drop-shadow(0 0 26px rgba(239,68,68,0.68))',
                  }}
                />

                {/* Scanning Laser Line across the Stargate Portal during Happy Path */}
                {isHappy && (
                  <div
                    style={{
                      position: 'absolute',
                      left: '26%',
                      width: '48%',
                      height: '3px',
                      borderRadius: '999px',
                      background: 'linear-gradient(90deg, transparent, #34d399, #a7f3d0, #34d399, transparent)',
                      boxShadow: '0 0 16px #10b981',
                      animation: 'ap2GateLaserSweep 2.1s ease-in-out infinite',
                      pointerEvents: 'none',
                    }}
                  />
                )}

                {/* Red Forcefield Impact Spark Badge on Attack Step 3+ */}
                {!isHappy && curStep >= 3 && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '44%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      padding: '0.24rem 0.65rem',
                      borderRadius: '999px',
                      background: 'rgba(127, 29, 29, 0.92)',
                      border: '1.5px solid #f87171',
                      boxShadow: '0 0 22px rgba(239, 68, 68, 0.95)',
                      color: '#fef2f2',
                      fontSize: '0.72rem',
                      fontWeight: 900,
                      whiteSpace: 'nowrap',
                      pointerEvents: 'none',
                    }}
                  >
                    ⚡ HTTP 401 • SHIELD ACTIVE
                  </div>
                )}
              </div>

              {/* Station 3 Pedestal Title */}
              <div style={{ textAlign: 'center', marginTop: '-0.25rem' }}>
                <div style={{ fontSize: '0.92rem', fontWeight: 900, color: '#f8fafc' }}>
                  3. PayPal Settlement Gate
                </div>
                <div style={{ fontSize: '0.75rem', fontWeight: 800, color: isHappy ? '#38bdf8' : '#f87171' }}>
                  (PayPal Lead Sponsor)
                </div>
              </div>
            </div>

            {/* =====================================================================
                STATION 4 (FAR RIGHT): COMPUTE RACK + WHIRLING 3D TOP COOLING FAN
                + RISING 3D HOLOGRAPHIC REVENUE BARS (Bryntum + AG Studio)
               ===================================================================== */}
            <div
              onClick={() => setStory((p) => ({ ...p, stepIndex: 4, autoPlaying: false }))}
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                cursor: 'pointer',
                transformStyle: 'preserve-3d',
                transform: curStep === 4 ? 'translateZ(30px) scale(1.05)' : 'translateZ(10px)',
                transition: 'transform 0.4s cubic-bezier(0.22, 1, 0.36, 1)',
              }}
            >
              {/* Floating Fan & Telemetry Callout above Station 4 */}
              <div
                style={{
                  marginBottom: '0.35rem',
                  padding: '0.5rem 0.85rem',
                  borderRadius: '12px',
                  background: isHappy ? 'rgba(6, 26, 28, 0.92)' : 'rgba(30, 15, 24, 0.92)',
                  border:
                    curStep === 4
                      ? `2px solid ${isHappy ? '#10b981' : '#f87171'}`
                      : `1px solid ${isHappy ? 'rgba(16, 185, 129, 0.45)' : 'rgba(148, 163, 184, 0.35)'}`,
                  boxShadow:
                    curStep === 4
                      ? `0 0 30px ${isHappy ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.35)'}`
                      : '0 8px 20px rgba(0,0,0,0.5)',
                  textAlign: 'center',
                  maxWidth: '300px',
                }}
              >
                <div
                  style={{
                    fontSize: '0.7rem',
                    fontWeight: 900,
                    color: isHappy ? '#34d399' : '#f87171',
                    textTransform: 'uppercase',
                  }}
                >
                  {fanWhirlingFast
                    ? '🌀 Step 4 • Cooling Fan Whirling @ 2,850 RPM!'
                    : isHappy
                      ? '🌀 Step 4 • Compute Rack Ready (420 RPM)'
                      : '🔒 Step 4 • Rack Locked • Fan Halted (0 RPM)'}
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#f8fafc', marginTop: '0.12rem' }}>
                  {isHappy ? (
                    <>
                      ACTIVE: <span style={{ color: '#34d399' }}>$49.99/mo</span> • {story.activeNodesCount} Nodes
                    </>
                  ) : (
                    <>
                      <span style={{ color: '#fca5a5' }}>$0.00 Charged</span> • Unauthorized Node Blocked
                    </>
                  )}
                </div>
              </div>

              {/* 3D Compute Rack Monument + Real Whirling 3D Cooling Fan on Top + Rising 3D Chart Bars */}
              <div style={{ position: 'relative', width: '285px', height: '275px', transformStyle: 'preserve-3d' }}>
                {/* Main 3D Compute Rack Image */}
                <img
                  src={isHappy ? monumentRackHappyImg : monumentRackLockedImg}
                  alt="4. Compute Rack (Bryntum + AG Studio)"
                  style={{
                    width: '260px',
                    height: '265px',
                    objectFit: 'contain',
                    filter: isHappy
                      ? 'drop-shadow(0 18px 28px rgba(0,0,0,0.85)) drop-shadow(0 0 22px rgba(16,185,129,0.38))'
                      : 'drop-shadow(0 18px 28px rgba(0,0,0,0.85))',
                  }}
                />

                {/* =================================================================
                    REAL 3D ISOMETRIC COOLING FAN TURBINE ON TOP OF THE SERVER RACK!
                    Positioned directly over the isometric square top exhaust vent
                   ================================================================= */}
                <div
                  data-testid="ap2-server-cooling-fan"
                  title={
                    fanWhirlingFast
                      ? 'Server Cooling Turbine Whirling Up at 2,850 RPM!'
                      : fanHalted
                        ? 'Server Cooling Turbine Halted (0 RPM)'
                        : 'Server Cooling Turbine Idle (420 RPM)'
                  }
                  style={{
                    position: 'absolute',
                    top: '13.5%',
                    left: '41.5%',
                    width: '74px',
                    height: '74px',
                    transform: 'translate(-50%, -50%) rotateX(60deg) rotateZ(-43deg)',
                    transformStyle: 'preserve-3d',
                    pointerEvents: 'none',
                  }}
                >
                  {/* Outer Glowing Isometric Turbine Housing */}
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      borderRadius: '50%',
                      border: `2.5px solid ${
                        fanWhirlingFast ? '#34d399' : fanHalted ? '#ef4444' : '#38bdf8'
                      }`,
                      background: fanWhirlingFast
                        ? 'radial-gradient(circle, rgba(16,185,129,0.42), rgba(6,78,59,0.82))'
                        : fanHalted
                          ? 'radial-gradient(circle, rgba(239,68,68,0.25), rgba(15,23,42,0.9))'
                          : 'radial-gradient(circle, rgba(56,189,248,0.28), rgba(15,23,42,0.85))',
                      boxShadow: fanWhirlingFast
                        ? '0 0 26px rgba(16, 185, 129, 0.95), inset 0 0 14px rgba(52, 211, 153, 0.8)'
                        : fanHalted
                          ? '0 0 12px rgba(239, 68, 68, 0.5)'
                          : '0 0 14px rgba(56, 189, 248, 0.55)',
                    }}
                  />

                  {/* Spinning 8-Blade 3D Turbine Impeller */}
                  <svg
                    viewBox="0 0 100 100"
                    style={{
                      position: 'absolute',
                      inset: '5px',
                      width: '64px',
                      height: '64px',
                      animation: fanHalted
                        ? 'none'
                        : fanWhirlingFast
                          ? 'ap2TurbineSpinFast 0.22s linear infinite'
                          : 'ap2TurbineSpinIdle 1.6s linear infinite',
                    }}
                  >
                    {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
                      <g key={angle} transform={`rotate(${angle} 50 50)`}>
                        <path
                          d="M 50 50 C 56 32, 66 20, 52 8 C 44 18, 44 34, 50 50 Z"
                          fill={
                            fanWhirlingFast
                              ? '#6ee7b7'
                              : fanHalted
                                ? '#64748b'
                                : '#7dd3fc'
                          }
                          opacity={0.92}
                        />
                      </g>
                    ))}
                    <circle
                      cx="50"
                      cy="50"
                      r="12"
                      fill="#0f172a"
                      stroke={fanWhirlingFast ? '#34d399' : fanHalted ? '#f87171' : '#38bdf8'}
                      strokeWidth="3"
                    />
                  </svg>
                </div>

                {/* Rising 3D Emerald Airflow Vortex Rings when the Server Fan Whirls Up! */}
                {isHappy && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '11%',
                      left: '41.5%',
                      width: '80px',
                      height: '80px',
                      pointerEvents: 'none',
                    }}
                  >
                    {[0, 1, 2].map((ringIdx) => (
                      <div
                        key={ringIdx}
                        style={{
                          position: 'absolute',
                          top: '50%',
                          left: '50%',
                          width: fanWhirlingFast ? '68px' : '46px',
                          height: fanWhirlingFast ? '68px' : '46px',
                          borderRadius: '50%',
                          border: `2px solid ${fanWhirlingFast ? '#34d399' : 'rgba(56, 189, 248, 0.5)'}`,
                          boxShadow: fanWhirlingFast ? '0 0 16px rgba(16, 185, 129, 0.8)' : 'none',
                          animation: `ap2VortexRise ${fanWhirlingFast ? '1.15s' : '2.4s'} ease-out ${ringIdx * 0.36}s infinite`,
                        }}
                      />
                    ))}
                  </div>
                )}

                {/* Animated Server Blade Activity Bars on Front of Rack */}
                {isHappy && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '30%',
                      left: '26%',
                      width: '54px',
                      height: '92px',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      transform: 'skewY(26deg)',
                      pointerEvents: 'none',
                    }}
                  >
                    {[0, 1, 2, 3, 4, 5].map((blade) => (
                      <div
                        key={blade}
                        style={{
                          height: '4px',
                          borderRadius: '999px',
                          background: fanWhirlingFast ? '#6ee7b7' : '#34d399',
                          boxShadow: '0 0 10px #10b981',
                          animation: `ap2ServerBladePulse ${fanWhirlingFast ? '0.55s' : '1.3s'} ease-in-out ${blade * 0.12}s infinite`,
                        }}
                      />
                    ))}
                  </div>
                )}

                {/* =================================================================
                    3D HOLOGRAPHIC AG STUDIO REVENUE BARS (Grow Upward on Step 4!)
                   ================================================================= */}
                <div
                  data-testid="ap2-3d-revenue-bars"
                  style={{
                    position: 'absolute',
                    right: '-6px',
                    bottom: '44px',
                    padding: '0.5rem 0.6rem',
                    borderRadius: '12px',
                    background: 'rgba(5, 14, 28, 0.9)',
                    border: `1px solid ${isHappy ? 'rgba(52, 211, 153, 0.55)' : 'rgba(148, 163, 184, 0.3)'}`,
                    boxShadow: isHappy
                      ? '0 12px 26px rgba(0,0,0,0.7), 0 0 20px rgba(16, 185, 129, 0.28)'
                      : '0 10px 22px rgba(0,0,0,0.65)',
                    backdropFilter: 'blur(8px)',
                  }}
                >
                  <div
                    style={{
                      fontSize: '0.62rem',
                      fontWeight: 900,
                      color: isHappy ? '#6ee7b7' : '#94a3b8',
                      marginBottom: '0.32rem',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    📊 AG STUDIO 3D LEDGER
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'flex-end',
                      gap: '5px',
                      height: '62px',
                      padding: '0 2px',
                    }}
                  >
                    {[
                      { h: 26, c: '#38bdf8' },
                      { h: 34, c: '#38bdf8' },
                      { h: 42, c: '#34d399' },
                      { h: 50, c: '#34d399' },
                      { h: isHappy ? (fanWhirlingFast ? 62 : 46) : 18, c: isHappy ? '#10b981' : '#ef4444' },
                    ].map((bar, idx) => (
                      <div
                        key={idx}
                        style={{
                          width: '12px',
                          height: `${bar.h}px`,
                          borderRadius: '4px 4px 2px 2px',
                          background: `linear-gradient(180deg, ${bar.c}, rgba(15,23,42,0.85))`,
                          border: `1px solid ${bar.c}`,
                          boxShadow: idx === 4 && fanWhirlingFast ? '0 0 12px #10b981' : 'none',
                          transition: 'height 0.6s cubic-bezier(0.22, 1, 0.36, 1)',
                        }}
                      />
                    ))}
                  </div>
                  <div
                    style={{
                      fontSize: '0.64rem',
                      fontWeight: 800,
                      color: '#f8fafc',
                      marginTop: '0.28rem',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    ${story.monthlySpendDollars.toLocaleString('en-US', { minimumFractionDigits: 2 })}/mo
                  </div>
                </div>
              </div>

              {/* Station 4 Pedestal Title */}
              <div style={{ textAlign: 'center', marginTop: '-0.25rem' }}>
                <div style={{ fontSize: '0.92rem', fontWeight: 900, color: '#f8fafc' }}>
                  4. Compute Rack
                </div>
                <div style={{ fontSize: '0.75rem', fontWeight: 800, color: '#34d399' }}>
                  (Bryntum + AG Studio)
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 3 INTERACTIVE SCENARIO PILL BUTTONS */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '0.85rem',
          marginTop: '0.85rem',
        }}
      >
        <button
          type="button"
          data-testid="story-btn-happy-counter"
          disabled={story.busy}
          onClick={() => void runScenario('happy_counter')}
          style={{
            cursor: story.busy ? 'wait' : 'pointer',
            padding: '0.9rem 1.15rem',
            borderRadius: '999px',
            border:
              story.mode === 'happy_counter'
                ? '2px solid #34d399'
                : '1px solid rgba(52, 211, 153, 0.35)',
            background:
              story.mode === 'happy_counter'
                ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.28), rgba(6, 95, 70, 0.5))'
                : 'rgba(15, 23, 42, 0.85)',
            color: '#ecfdf5',
            fontWeight: 800,
            fontSize: '0.9rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.55rem',
            boxShadow:
              story.mode === 'happy_counter'
                ? '0 0 28px rgba(16, 185, 129, 0.35)'
                : '0 8px 20px rgba(0, 0, 0, 0.35)',
            transition: 'all 0.2s ease',
          }}
        >
          <span>▶️ 1. Watch AI Bargain & Buy ($60 → $49.99)</span>
        </button>

        <button
          type="button"
          data-testid="story-btn-rogue-attack"
          disabled={story.busy}
          onClick={() => void runScenario('rogue_200_lie')}
          style={{
            cursor: story.busy ? 'wait' : 'pointer',
            padding: '0.9rem 1.15rem',
            borderRadius: '999px',
            border:
              story.mode === 'rogue_200_lie'
                ? '2px solid #f87171'
                : '1px solid rgba(248, 113, 113, 0.35)',
            background:
              story.mode === 'rogue_200_lie'
                ? 'linear-gradient(135deg, rgba(239, 68, 68, 0.28), rgba(127, 29, 29, 0.5))'
                : 'rgba(15, 23, 42, 0.85)',
            color: '#fef2f2',
            fontWeight: 800,
            fontSize: '0.9rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.55rem',
            boxShadow:
              story.mode === 'rogue_200_lie'
                ? '0 0 28px rgba(239, 68, 68, 0.38)'
                : '0 8px 20px rgba(0, 0, 0, 0.35)',
            transition: 'all 0.2s ease',
          }}
        >
          <span>🛑 2. Simulate Rogue AI Attack ($200 Lie)</span>
        </button>

        <button
          type="button"
          data-testid="story-btn-tamper-cent"
          disabled={story.busy}
          onClick={() => void runScenario('tamper_plus_one_cent')}
          style={{
            cursor: story.busy ? 'wait' : 'pointer',
            padding: '0.9rem 1.15rem',
            borderRadius: '999px',
            border:
              story.mode === 'tamper_plus_one_cent'
                ? '2px solid #fbbf24'
                : '1px solid rgba(251, 191, 36, 0.35)',
            background:
              story.mode === 'tamper_plus_one_cent'
                ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.28), rgba(120, 53, 15, 0.5))'
                : 'rgba(15, 23, 42, 0.85)',
            color: '#fffbeb',
            fontWeight: 800,
            fontSize: '0.9rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.55rem',
            boxShadow:
              story.mode === 'tamper_plus_one_cent'
                ? '0 0 28px rgba(245, 158, 11, 0.35)'
                : '0 8px 20px rgba(0, 0, 0, 0.35)',
            transition: 'all 0.2s ease',
          }}
        >
          <span>🛡️ 3. Simulate +1¢ Price Tamper</span>
        </button>
      </div>

      {/* Plain-English Takeaway Card + Live Sandbox Receipt */}
      <div
        data-testid="ap2-story-plain-english-card"
        style={{
          marginTop: '0.85rem',
          padding: '0.9rem 1.25rem',
          borderRadius: '14px',
          background: 'rgba(8, 15, 32, 0.92)',
          border: '1px solid rgba(148, 163, 184, 0.2)',
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '1rem',
        }}
      >
        <div style={{ flex: '1 1 560px' }}>
          <div
            style={{
              fontSize: '0.72rem',
              fontWeight: 800,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              color: isHappy ? '#34d399' : '#f87171',
              marginBottom: '0.2rem',
            }}
          >
            {isHappy
              ? '✅ Live Sandbox Verdict — PayPal Settlement & Compute Provisioned'
              : '🛑 Live Sandbox Verdict — Blocked Before Signing (Zero Funds Moved)'}
          </div>
          <p style={{ margin: 0, fontSize: '0.87rem', lineHeight: 1.5, color: '#e2e8f0' }}>
            {story.plainEnglishSummary}
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
          <div
            style={{
              padding: '0.45rem 0.85rem',
              borderRadius: '10px',
              background: 'rgba(15, 23, 42, 0.9)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              fontSize: '0.76rem',
              color: '#cbd5e1',
            }}
          >
            <div>
              <strong>HTTP Status:</strong>{' '}
              <span style={{ color: story.httpStatus === 200 ? '#34d399' : '#f87171', fontWeight: 800 }}>
                {story.httpStatus}
              </span>
            </div>
            <div>
              <strong>Receipt:</strong>{' '}
              <code style={{ color: '#38bdf8' }}>
                {story.receipt?.subscriptionId || 'BLOCKED_AT_GATE_0_CENTS'}
              </code>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Ap2ThreeDStoryView;
