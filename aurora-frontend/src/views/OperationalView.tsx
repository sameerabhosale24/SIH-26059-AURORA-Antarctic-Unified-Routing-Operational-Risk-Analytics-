/**
 * Operational view — the live console.
 *
 * The map takes the centre and the two high-frequency panels sit either side:
 * own-ship instruments on the left where the eye rests, the alarm queue beside
 * them, and the derived forecast on the right. Panels are stacked in CSS only;
 * every one of them reads its own store, so nothing here has to pass data
 * around and a panel can be lifted into another view unchanged.
 *
 * The freshness drawer is an overlay rather than a permanent column because
 * "how old is this?" is an occasional question, and spending a third of the
 * screen on it all day would be the wrong trade.
 */
import { AlarmPanel } from '@/panels/AlarmPanel';
import { ConningPanel } from '@/panels/ConningPanel';
import { DataFreshnessPanel } from '@/panels/DataFreshnessPanel';
import { ForecastTable } from '@/panels/ForecastTable';
import { LegendPanel } from '@/panels/LegendPanel';
import { FollowShipToggle } from '@/controls/FollowShipToggle';
import { VesselGate } from '@/components/VesselGate';
import { MapView } from '@/map/MapView';
import { useUiStore } from '@/stores/uiStore';

export function OperationalView(): JSX.Element {
  const freshnessOpen = useUiStore((state) => state.freshnessOpen);
  const toggleFreshness = useUiStore((state) => state.toggleFreshness);

  return (
    <VesselGate>
      <div className="grid h-full min-h-0 grid-cols-1 gap-2 p-2 lg:grid-cols-[19rem_minmax(0,1fr)_18rem]">
        <aside className="order-2 flex min-h-0 flex-col gap-2 lg:order-1">
          <ConningPanel className="flex-none" />
          <AlarmPanel className="min-h-0 flex-1" />
        </aside>

        <div className="relative order-1 min-h-0 lg:order-2">
          <MapView />

          <div className="absolute right-2 top-2 z-10 flex items-center gap-2">
            <FollowShipToggle />

            <button
              type="button"
              onClick={toggleFreshness}
              aria-pressed={freshnessOpen}
              className={`rounded-sm border px-2 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors ${
                freshnessOpen
                  ? 'border-ocean-400/50 bg-ocean-400/15 text-ocean-400'
                  : 'border-ocean-800 bg-ocean-900/90 text-ocean-300 hover:text-ocean-100'
              }`}
            >
              Freshness
            </button>
          </div>

          {freshnessOpen ? (
            <div className="absolute right-2 top-11 z-10 max-h-[calc(100%-3rem)] w-80 overflow-auto">
              <DataFreshnessPanel onClose={toggleFreshness} />
            </div>
          ) : null}
        </div>

        <aside className="order-3 grid min-h-0 gap-2 lg:grid-rows-[minmax(0,1.2fr)_minmax(0,1fr)]">
          <ForecastTable className="min-h-0" />
          <LegendPanel className="min-h-0" />
        </aside>
      </div>
    </VesselGate>
  );
}
