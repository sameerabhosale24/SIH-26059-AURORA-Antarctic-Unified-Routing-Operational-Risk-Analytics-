/**
 * Layer manager — visibility and opacity for every layer, grouped by category.
 *
 * Ordering comes from `layersByCategory()`, which is the same array the map
 * paints from, so the list cannot drift out of sync with the stack. "Never
 * touched" resolves to each layer's own default rather than to `false`, so the
 * panel accurately reports what is on the map before anyone moves a control.
 */
import { Panel } from '@/components/ui/Panel';
import { CATEGORY_LABELS } from '@/map/layers/types';
import { isLayerVisible, layerById, layerOpacity, layersByCategory } from '@/map/layers';
import { useSicStore } from '@/stores/sicStore';
import { useUiStore } from '@/stores/uiStore';

/** Shown when the SIC toggle has nothing behind it. */
const SIC_NO_DATA_HINT =
  'Waiting for the daily SIC run. Configure credentials and run the scheduler, or load a simulation bundle.';

function LayerRow({ id }: { id: string }): JSX.Element | null {
  const layer = layerById(id);
  const visible = useUiStore((state) => isLayerVisible(id, state));
  const opacity = useUiStore((state) => layerOpacity(id, state));
  const toggleLayer = useUiStore((state) => state.toggleLayer);
  const setOpacity = useUiStore((state) => state.setOpacity);

  // The SIC layer is registered before the backend has produced a single
  // frame — expected, but not something a toggle should pretend about.
  const sicFrames = useSicStore((state) => state.data?.frames);
  const hasSicData = Array.isArray(sicFrames) && sicFrames.length > 0;
  const awaitingData = layer?.id === 'sic' && !hasSicData;

  if (!layer) return null;

  return (
    <div
      className="border-b border-ocean-800/40 py-2 last:border-b-0"
      title={awaitingData ? SIC_NO_DATA_HINT : undefined}
    >
      <div className="flex items-center gap-2">
        <input
          id={`layer-${layer.id}`}
          type="checkbox"
          checked={visible}
          disabled={awaitingData}
          onChange={() => toggleLayer(layer.id)}
          className={`h-3.5 w-3.5 shrink-0 accent-ocean-400 ${
            awaitingData ? 'cursor-not-allowed opacity-40' : ''
          }`}
        />

        <label
          htmlFor={`layer-${layer.id}`}
          className={`min-w-0 flex-1 truncate text-xs ${
            awaitingData
              ? 'cursor-not-allowed text-ocean-400'
              : visible
                ? 'cursor-pointer text-ocean-100'
                : 'cursor-pointer text-ocean-300'
          }`}
        >
          {layer.title}
          {awaitingData ? (
            <span className="ml-1.5 rounded-sm border border-ocean-700 bg-ocean-800 px-1 py-px align-middle text-[9px] uppercase tracking-[0.12em] text-ocean-300">
              No data
            </span>
          ) : null}
        </label>

        <span className="shrink-0 font-mono text-[10px] text-ocean-300">
          {Math.round(opacity * 100)}%
        </span>
      </div>

      <div className={`mt-1 flex items-center gap-2 pl-6 ${visible ? '' : 'opacity-40'}`}>
        <label htmlFor={`opacity-${layer.id}`} className="sr-only">
          {layer.title} opacity
        </label>

        <input
          id={`opacity-${layer.id}`}
          type="range"
          min={0}
          max={100}
          step={5}
          value={Math.round(opacity * 100)}
          disabled={!visible || awaitingData}
          onChange={(event) => setOpacity(layer.id, Number(event.target.value) / 100)}
          className="h-1 flex-1 accent-ocean-400 disabled:cursor-not-allowed"
        />
      </div>
    </div>
  );
}

export function LayerManager({ className = '' }: { className?: string }): JSX.Element {
  const groups = layersByCategory();
  const total = groups.reduce((count, group) => count + group.layers.length, 0);

  return (
    <Panel className={className} title="Layers" action={<span className="text-[10px] text-ocean-300">{total}</span>}>
      {groups.map(({ category, layers }) => (
        <section key={category} className="mb-3 last:mb-0">
          <h3 className="mb-1 text-[10px] uppercase tracking-[0.2em] text-ocean-400">
            {CATEGORY_LABELS[category]}
          </h3>

          <div>
            {layers.map((layer) => (
              <LayerRow key={layer.id} id={layer.id} />
            ))}
          </div>
        </section>
      ))}

      <p className="mt-1 text-[10px] leading-snug text-ocean-300">
        Order matches the paint order on the map. Opacity resets to each layer's
        default when the console reloads.
      </p>
    </Panel>
  );
}
