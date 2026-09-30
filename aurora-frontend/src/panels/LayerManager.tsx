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
import { useUiStore } from '@/stores/uiStore';

function LayerRow({ id }: { id: string }): JSX.Element | null {
  const layer = layerById(id);
  const visible = useUiStore((state) => isLayerVisible(id, state));
  const opacity = useUiStore((state) => layerOpacity(id, state));
  const toggleLayer = useUiStore((state) => state.toggleLayer);
  const setOpacity = useUiStore((state) => state.setOpacity);

  if (!layer) return null;

  return (
    <div className="border-b border-aurora-border/40 py-2 last:border-b-0">
      <div className="flex items-center gap-2">
        <input
          id={`layer-${layer.id}`}
          type="checkbox"
          checked={visible}
          onChange={() => toggleLayer(layer.id)}
          className="h-3.5 w-3.5 shrink-0 accent-aurora-accent"
        />

        <label
          htmlFor={`layer-${layer.id}`}
          className={`min-w-0 flex-1 cursor-pointer truncate text-xs ${
            visible ? 'text-aurora-text' : 'text-aurora-muted'
          }`}
        >
          {layer.title}
        </label>

        <span className="shrink-0 font-mono text-[10px] text-aurora-muted">
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
          disabled={!visible}
          onChange={(event) => setOpacity(layer.id, Number(event.target.value) / 100)}
          className="h-1 flex-1 cursor-pointer accent-aurora-accent"
        />
      </div>
    </div>
  );
}

export function LayerManager({ className = '' }: { className?: string }): JSX.Element {
  const groups = layersByCategory();
  const total = groups.reduce((count, group) => count + group.layers.length, 0);

  return (
    <Panel className={className} title="Layers" action={<span className="text-[10px] text-aurora-muted">{total}</span>}>
      {groups.map(({ category, layers }) => (
        <section key={category} className="mb-3 last:mb-0">
          <h3 className="mb-1 text-[10px] uppercase tracking-[0.2em] text-aurora-accent">
            {CATEGORY_LABELS[category]}
          </h3>

          <div>
            {layers.map((layer) => (
              <LayerRow key={layer.id} id={layer.id} />
            ))}
          </div>
        </section>
      ))}

      <p className="mt-1 text-[10px] leading-snug text-aurora-muted">
        Order matches the paint order on the map. Opacity resets to each layer's
        default when the console reloads.
      </p>
    </Panel>
  );
}
