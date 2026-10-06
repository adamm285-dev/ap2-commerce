import { useEffect, useRef, useState } from 'react';
import '@bryntum/scheduler/scheduler.css';
import '@bryntum/scheduler/stockholm-dark.css';
import '@bryntum/scheduler/fontawesome/css/fontawesome.css';
import '@bryntum/scheduler/fontawesome/css/solid.css';
import { Scheduler } from '@bryntum/scheduler';
import { Zap, PhoneCall, CalendarCheck } from 'lucide-react';

import {
  executeProvisioningAfterSubscription,
  fetchFleetSchedule,
  lockTerritorySlot,
} from '../services/paypalAgentService';

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
}

export function BryntumDispatchScheduler({
  isDepositLocked = false,
  onToggleDepositLock,
}: BryntumDispatchSchedulerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const schedulerRef = useRef<Scheduler | null>(null);
  const [lastPaymentSync, setLastPaymentSync] = useState<string>('2026-10-02 02:14:22');
  const [isCallingApi, setIsCallingApi] = useState(false);
  const [isLockingSlot, setIsLockingSlot] = useState(false);
  const [isSlotLocked, setIsSlotLocked] = useState(false);
  const [apiStatus, setApiStatus] = useState<string>(
    isDepositLocked
      ? '● Live Line Active: +1 (863) 267-8902 via Telnyx (HTTP 201)'
      : '○ Pending: Awaiting $79.99/mo PayPal Subscription Authorization'
  );

  useEffect(() => {
    if (!containerRef.current) return;

    // Define Contractor Fleet Tenants with statutory KYC identities
    const resources = [
      {
        id: 'crew-1',
        name: 'Marcus Miller',
        entity: 'Miller Custom Flooring LLC',
        trade: 'Tile & Custom Flooring',
        did: isDepositLocked ? '+1 (863) 267-8902' : 'AWAITING PAYMENT',
        status: isDepositLocked ? 'ACTIVE_10DLC_BOUND' : 'PENDING_SUBSCRIPTION',
      },
      {
        id: 'crew-2',
        name: 'Dave Vance',
        entity: 'Vance Rapid Drain & Plumbing Inc',
        trade: 'Emergency 24/7 Plumbing',
        did: '+1 (863) 356-7801',
        status: 'ACTIVE_10DLC_BOUND',
      },
      {
        id: 'crew-3',
        name: 'Elena Rostova',
        entity: 'Apex Storm & Roofing Specialists',
        trade: 'Roofing & Storm Restoration',
        did: '+1 (863) 356-7802',
        status: 'ACTIVE_10DLC_BOUND',
      },
      {
        id: 'crew-4',
        name: 'Hank Schrader',
        entity: 'Schrader Heavy Duty Towing LLC',
        trade: 'Towing & Heavy Roadside',
        did: '+1 (863) 356-7803',
        status: 'ACTIVE_10DLC_BOUND',
      },
    ];

    // Define 24/7 AI Voice Screener Line Shifts across the fleet
    // Marcus Miller starts with an UNPROVISIONED line awaiting PayPal $79.99/mo subscription (Orange)
    const events: ScheduleEvent[] = [
      {
        id: 'line-marcus-screener',
        resourceId: 'crew-1',
        name: isDepositLocked
          ? 'AI Voice Screener Active • DID: +1 (863) 267-8902 [KYC BOUND]'
          : 'AI Screener Line Pending • Awaiting PayPal Subscription ($79.99/mo)',
        startDate: '2026-10-02 08:00',
        endDate: '2026-10-02 18:00',
        eventColor: isDepositLocked ? 'green' : 'orange',
        iconCls: isDepositLocked ? 'b-fa b-fa-check-circle' : 'b-fa b-fa-clock',
        depositStatus: isDepositLocked ? 'ACTIVE ($79.99/MO)' : 'AWAITING PAYPAL ($79.99/MO)',
        paypalTxn: isDepositLocked ? 'I-AUTONOMOUS-8902' : 'UNPAID',
      },
      {
        id: 'line-dave-screener',
        resourceId: 'crew-2',
        name: 'AI Voice Screener Active • DID: +1 (863) 356-7801 [KYC BOUND]',
        startDate: '2026-10-02 08:00',
        endDate: '2026-10-02 18:00',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-check-circle',
        depositStatus: 'ACTIVE ($79.99/MO)',
        paypalTxn: 'I-PL782MK110Q9',
      },
      {
        id: 'line-elena-screener',
        resourceId: 'crew-3',
        name: 'AI Voice Screener Active • DID: +1 (863) 356-7802 [KYC BOUND]',
        startDate: '2026-10-02 08:00',
        endDate: '2026-10-02 18:00',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-check-circle',
        depositStatus: 'ACTIVE ($79.99/MO)',
        paypalTxn: 'I-RF994ZZ331A8',
      },
      {
        id: 'line-hank-screener',
        resourceId: 'crew-4',
        name: 'AI Voice Screener Active • DID: +1 (863) 356-7803 [KYC BOUND]',
        startDate: '2026-10-02 08:00',
        endDate: '2026-10-02 18:00',
        eventColor: 'green',
        iconCls: 'b-fa b-fa-check-circle',
        depositStatus: 'ACTIVE ($79.99/MO)',
        paypalTxn: 'I-TW551PP882B4',
      },
    ];

    // Initialize Bryntum Scheduler instance
    const scheduler = new Scheduler({
      appendTo: containerRef.current,
      startDate: new Date(2026, 9, 2, 7, 0),
      endDate: new Date(2026, 9, 2, 19, 0),
      viewPreset: 'hourAndDay',
      rowHeight: 68,
      barMargin: 10,
      eventStyle: 'filled',
      columns: [
        {
          text: 'Contractor & Legal Entity',
          field: 'name',
          width: 210,
          renderer({ record }: any) {
            return `
              <div style="line-height:1.3;">
                <div style="font-weight:700;color:#f8fafc;font-size:12px;">${record.name}</div>
                <div style="font-size:10px;color:#94a3b8;">${record.entity}</div>
              </div>
            `;
          },
        },
        { text: 'Trade Vertical', field: 'trade', width: 170 },
        {
          text: 'Provisioned DID Phone',
          field: 'did',
          width: 170,
          renderer({ record }: any) {
            const isAssigned = !record.did.includes('AWAITING');
            return `
              <span style="font-size:11px;font-family:ui-monospace, monospace;font-weight:600;color:${
                isAssigned ? '#34d399' : '#fbbf24'
              };">
                ${record.did}
              </span>
            `;
          },
        },
      ],
      resources,
      events,
      eventRenderer({ eventRecord }: { eventRecord: any }) {
        const isActive = eventRecord.depositStatus.includes('ACTIVE');
        return `
          <div style="display:flex;align-items:center;justify-content:space-between;width:100%;height:100%;padding:4px 10px;font-size:11px;font-weight:600;">
            <div style="display:flex;align-items:center;gap:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
              <i class="${eventRecord.iconCls}" style="font-size:12px;color:${isActive ? '#34d399' : '#fbbf24'};"></i>
              <span>${eventRecord.name}</span>
            </div>
            <span style="font-size:10px;padding:3px 8px;border-radius:4px;background-color:${
              isActive ? 'rgba(16,185,129,0.25)' : 'rgba(245,158,11,0.25)'
            };color:${isActive ? '#34d399' : '#fbbf24'};border:1px solid ${
              isActive ? '#10b981' : '#f59e0b'
            };flex-shrink:0;letter-spacing:0.02em;">
              ${eventRecord.depositStatus}
            </span>
          </div>
        `;
      },
    });

    schedulerRef.current = scheduler;

    let mounted = true;
    async function hydrateLiveSchedule() {
      const liveData = await fetchFleetSchedule();
      if (liveData && liveData.resources && liveData.resources.length > 0 && schedulerRef.current && mounted) {
        schedulerRef.current.resourceStore.data = liveData.resources;
        schedulerRef.current.eventStore.data = liveData.events;
        const hasLockedSlot = liveData.events.some((e: any) => e.name && e.name.includes('Takeoff:'));
        if (hasLockedSlot) {
          setIsSlotLocked(true);
        }
      }
    }
    hydrateLiveSchedule();

    return () => {
      mounted = false;
      scheduler.destroy();
    };
  }, []);

  // Synchronize slot state when parent props change
  useEffect(() => {
    if (!schedulerRef.current) return;
    const targetEvent = schedulerRef.current.eventStore.getById('line-marcus-screener');
    if (targetEvent) {
      targetEvent.set({
        name: isDepositLocked
          ? 'AI Voice Screener Active • DID: +1 (863) 267-8902 [KYC BOUND]'
          : 'AI Screener Line Pending • Awaiting PayPal Subscription ($79.99/mo)',
        eventColor: isDepositLocked ? 'green' : 'orange',
        iconCls: isDepositLocked ? 'b-fa b-fa-check-circle' : 'b-fa b-fa-clock',
        depositStatus: isDepositLocked ? 'ACTIVE ($79.99/MO)' : 'AWAITING PAYPAL ($79.99/MO)',
        paypalTxn: isDepositLocked ? 'I-AUTONOMOUS-8902' : 'UNPAID',
      });

      // Also update Marcus Miller's DID in the resource store
      const marcusResource = schedulerRef.current.resourceStore.getById('crew-1');
      if (marcusResource) {
        marcusResource.set({
          did: isDepositLocked ? '+1 (863) 267-8902' : 'AWAITING PAYMENT',
          status: isDepositLocked ? 'ACTIVE_10DLC_BOUND' : 'PENDING_SUBSCRIPTION',
        });
      }

      setApiStatus(
        isDepositLocked
          ? '● Live Line Active: +1 (863) 267-8902 via Telnyx (HTTP 201)'
          : '○ Pending: Awaiting $79.99/mo PayPal Subscription Authorization'
      );
      setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));
    }
  }, [isDepositLocked]);

  // Simulate A2A PayPal Subscription: Calls FastAPI POST /api/agent/provision
  // and dynamically mutates Marcus Miller's line bar from Orange -> Vibrant Green in place!
  const handleSimulateActivation = async () => {
    if (!schedulerRef.current) return;
    setIsCallingApi(true);

    try {
      const simulatedSubId = `I-AUTONOMOUS-${Math.floor(100000 + Math.random() * 900000)}`;

      // 1. Send live POST /api/agent/provision to FastAPI backend
      const result = await executeProvisioningAfterSubscription(
        simulatedSubId,
        'Miller Custom Flooring LLC',
        'Tile & Flooring'
      );

      // 2. Dynamically mutate Marcus Miller's timeline card from Orange -> Green
      const targetEvent = schedulerRef.current.eventStore.getById('line-marcus-screener');
      if (targetEvent) {
        targetEvent.set({
          name: `AI Voice Screener Active • DID: ${result.allocatedDid} [KYC BOUND]`,
          eventColor: 'green',
          iconCls: 'b-fa b-fa-check-circle',
          depositStatus: 'ACTIVE ($79.99/MO)',
          paypalTxn: simulatedSubId,
        });
      }

      // 3. Update the resource row DID column
      const marcusResource = schedulerRef.current.resourceStore.getById('crew-1');
      if (marcusResource) {
        marcusResource.set({
          did: result.allocatedDid,
          status: 'ACTIVE_10DLC_BOUND',
        });
      }

      setApiStatus(`● Live Line Active: ${result.allocatedDid} via Telnyx (HTTP 201)`);
      setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));

      if (onToggleDepositLock) {
        onToggleDepositLock(true);
      }
    } finally {
      setIsCallingApi(false);
    }
  };

  // Reset Marcus Miller's line back to Amber/Orange (Awaiting Subscription) for repeated demonstrations
  const handleResetLine = () => {
    if (!schedulerRef.current) return;

    const targetEvent = schedulerRef.current.eventStore.getById('line-marcus-screener');
    if (targetEvent) {
      targetEvent.set({
        name: 'AI Screener Line Pending • Awaiting PayPal Subscription ($79.99/mo)',
        eventColor: 'orange',
        iconCls: 'b-fa b-fa-clock',
        depositStatus: 'AWAITING PAYPAL ($79.99/MO)',
        paypalTxn: 'UNPAID',
      });
    }

    const marcusResource = schedulerRef.current.resourceStore.getById('crew-1');
    if (marcusResource) {
      marcusResource.set({
        did: 'AWAITING PAYMENT',
        status: 'PENDING_SUBSCRIPTION',
      });
    }

    setApiStatus('○ Pending: Awaiting $79.99/mo PayPal Subscription Authorization');
    setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));

    if (onToggleDepositLock) {
      onToggleDepositLock(false);
    }
  };

  // Atomically locks a 75-minute estimate window upon verified PayPal deposit capture
  const handleLockTerritorySlot = async () => {
    if (!schedulerRef.current || isLockingSlot || isSlotLocked) return;
    setIsLockingSlot(true);
    try {
      const res = await lockTerritorySlot(
        'LEAD-SLAKELAND-863',
        'South Lakeland Zone 2',
        '2026-10-02 13:00',
        'TXN-DISPATCH-9021'
      );
      if (res.success) {
        setIsSlotLocked(true);
        const lockedEventId = 'locked-takeoff-slot-1';
        const existing = schedulerRef.current.eventStore.getById(lockedEventId);
        if (!existing) {
          (schedulerRef.current.eventStore as any).add({
            id: lockedEventId,
            resourceId: 'crew-1',
            name: 'Takeoff: 1,450 sqft Travertine Tile (South Lakeland Zone 2)',
            startDate: '2026-10-02 13:00',
            endDate: '2026-10-02 14:15',
            eventColor: 'blue',
            iconCls: 'b-fa b-fa-calendar-check',
            depositStatus: 'DEPOSIT VERIFIED ($89.00)',
            paypalTxn: 'TXN-DISPATCH-9021',
          });
        }
        setApiStatus('● Territory Slot Locked: 75-Min Takeoff Window (HTTP 200)');
        setLastPaymentSync(new Date().toISOString().replace('T', ' ').substring(0, 19));
      }
    } finally {
      setIsLockingSlot(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', backgroundColor: '#0f172a' }}>
      {/* Header Banner */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 20px',
          borderBottom: '1px solid #1e293b',
          backgroundColor: '#0b1120',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              padding: '6px',
              borderRadius: '6px',
              backgroundColor: 'rgba(56, 189, 248, 0.15)',
              color: '#38bdf8',
            }}
          >
            <PhoneCall size={18} />
          </div>
          <div>
            <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#f8fafc', margin: 0 }}>
              Bryntum Telephony Fleet &amp; Line Activation Timeline
            </h3>
            <p style={{ fontSize: '11px', color: '#94a3b8', margin: '2px 0 0 0' }}>
              Dedicated Inbound 10DLC Lines &bull; Statutory KYC Identity Bound &bull; Unlocked via PayPal A2A Commerce ($79.99/mo)
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* API Verification Badge */}
          <span
            style={{
              fontSize: '11px',
              fontWeight: 700,
              padding: '4px 10px',
              borderRadius: '12px',
              backgroundColor:
                isDepositLocked || apiStatus.includes('HTTP 201')
                  ? 'rgba(16, 185, 129, 0.2)'
                  : 'rgba(245, 158, 11, 0.2)',
              color:
                isDepositLocked || apiStatus.includes('HTTP 201')
                  ? '#34d399'
                  : '#fbbf24',
              border: `1px solid ${
                isDepositLocked || apiStatus.includes('HTTP 201')
                  ? '#10b981'
                  : '#f59e0b'
              }`,
            }}
          >
            {apiStatus}
          </span>

          <div style={{ fontSize: '11px', color: '#94a3b8' }}>
            Last Sync:{' '}
            <span style={{ color: '#34d399', fontFamily: 'monospace' }}>{lastPaymentSync}</span>
          </div>

          {/* Lock 75-Min Estimate Window Button */}
          <button
            onClick={handleLockTerritorySlot}
            disabled={isLockingSlot || isSlotLocked}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: isSlotLocked
                ? '#1e3a8a'
                : isLockingSlot
                ? '#1e293b'
                : '#2563eb',
              color: isSlotLocked ? '#60a5fa' : '#fff',
              fontSize: '12px',
              fontWeight: 600,
              cursor: isLockingSlot || isSlotLocked ? 'not-allowed' : 'pointer',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            <CalendarCheck size={14} />
            {isLockingSlot
              ? 'Locking Window via API...'
              : isSlotLocked
              ? '✓ 75-Min Takeoff Locked (South Lakeland)'
              : '🔒 Lock 75-Min Estimate Window ($89 Deposit)'}
          </button>

          {/* Simulate PayPal A2A Subscription Button */}
          <button
            onClick={handleSimulateActivation}
            disabled={isCallingApi || isDepositLocked}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              backgroundColor: isDepositLocked
                ? '#065f46'
                : isCallingApi
                ? '#1e293b'
                : '#0284c7',
              color: isDepositLocked ? '#34d399' : '#fff',
              fontSize: '12px',
              fontWeight: 600,
              cursor: isCallingApi || isDepositLocked ? 'not-allowed' : 'pointer',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            <Zap size={14} />
            {isCallingApi
              ? 'Calling /api/agent/provision...'
              : isDepositLocked
              ? '✓ Marcus Miller Line Active (+1 863-267-8902)'
              : '⚡ Simulate $79.99/mo A2A Subscription & Provisioning'}
          </button>

          {/* Reset Line Button */}
          <button
            onClick={handleResetLine}
            title="Reset Marcus Miller's line back to Amber/Orange (Awaiting Subscription)"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              padding: '6px 12px',
              borderRadius: '6px',
              border: '1px solid #334155',
              backgroundColor: '#1e293b',
              color: '#94a3b8',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            ↺ Reset to Pending (Orange)
          </button>
        </div>
      </div>

      {/* Bryntum Scheduler Container */}
      <div ref={containerRef} style={{ flex: 1, width: '100%', height: 'calc(100% - 60px)' }} />
    </div>
  );
}
export default BryntumDispatchScheduler;
