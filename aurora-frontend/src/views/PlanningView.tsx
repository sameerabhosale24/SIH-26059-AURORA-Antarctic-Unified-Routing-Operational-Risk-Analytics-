/**
 * Planning view — route decisions and the controls that shape the map.
 *
 * The controls live here rather than floating over the operational map because
 * they are *interpretation* choices, not driving choices: an operator changes
 * the projection or hides a layer while working out what to do, not while
 * conning the ship. The map is mounted here too, so every control has its
 * effect visible on the same screen.
 */
import { LayerManager } from '@/panels/LayerManager';
import { RoutePanel } from '@/panels/RoutePanel';
import { TimeSlider } from '@/panels/TimeSlider';
import { ProjectionSwitcher } from '@/controls/ProjectionSwitcher';
import { VesselGate } from '@/components/VesselGate';
import { MapView } from '@/map/MapView';

export function PlanningView(): JSX.Element {
  return (
    <VesselGate>
      <div className="grid h-full min-h-0 grid-cols-1 gap-2 p-2 lg:grid-cols-[20rem_minmax(0,1fr)_18rem]">
        <aside className="order-2 flex min-h-0 flex-col gap-2 lg:order-1">
          <LayerManager className="min-h-0 flex-1" />
        </aside>

        <div className="relative order-1 min-h-0 lg:order-2">
          <MapView />

          <div className="absolute left-2 top-2 z-10 flex items-center gap-2">
            <ProjectionSwitcher />
          </div>
        </div>

        <aside className="order-3 flex min-h-0 flex-col gap-2">
          <RoutePanel className="min-h-0 flex-1" />
          <TimeSlider className="flex-none" />
        </aside>
      </div>
    </VesselGate>
  );
}
