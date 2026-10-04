/**
 * Selected-station readout.
 *
 * Rendered in the bottom-left of the map, beside the scale bar, and driven
 * entirely by `uiStore.selectedStation` — the map interaction sets it, this
 * panel only presents it, so it works in every view that mounts a map.
 *
 * It is a compact card rather than a `Panel`: the operator needs three facts
 * and a way out, not a scrolling column.
 */
import { useUiStore } from '@/stores/uiStore';

export function StationInfoPanel({ className = '' }: { className?: string }): JSX.Element | null {
  const station = useUiStore((state) => state.selectedStation);
  const setSelectedStation = useUiStore((state) => state.setSelectedStation);

  if (!station) return null;

  return (
    <section
      className={`w-56 rounded border border-ocean-800 bg-ocean-900/95 shadow-lg shadow-black/40 ${className}`}
      aria-label={`Station ${station.name}`}
    >
      <header className="flex items-start justify-between gap-2 border-b border-ocean-800 px-3 py-1.5">
        <h2 className="text-base font-semibold leading-tight text-ocean-100">{station.name}</h2>

        <button
          type="button"
          onClick={() => setSelectedStation(null)}
          className="-mr-1 shrink-0 text-xs text-ocean-300 transition-colors hover:text-ocean-100"
          aria-label="Close station details"
        >
          ×
        </button>
      </header>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 px-3 py-2 text-[11px]">
        <dt className="text-ocean-300">Country</dt>
        <dd className="text-right text-ocean-100">{station.country}</dd>

        <dt className="text-ocean-300">Latitude</dt>
        <dd className="text-right font-mono text-ocean-100">{station.lat.toFixed(3)}</dd>

        <dt className="text-ocean-300">Longitude</dt>
        <dd className="text-right font-mono text-ocean-100">{station.lon.toFixed(3)}</dd>
      </dl>
    </section>
  );
}
