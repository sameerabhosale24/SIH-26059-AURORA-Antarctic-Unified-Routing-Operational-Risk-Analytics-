/**
 * Legend — what each colour on the map means.
 *
 * Swatches are read from the live {@link Palette}, so switching Day/Dusk/Night
 * changes the legend at the same moment as the layers; a legend that kept the
 * day colours while the map went to night lighting would be a trap.
 *
 * Layers that are currently hidden are dimmed rather than removed: the
 * operator needs to be able to see what a layer *would* mean before turning it
 * on, which is half the reason to open a legend.
 */
import { Panel } from '@/components/ui/Panel';
import { getPalette, type Palette } from '@/config/palettes';
import { CATEGORY_LABELS } from '@/map/layers/types';
import { isLayerVisible, layersByCategory } from '@/map/layers';
import { useUiStore } from '@/stores/uiStore';

interface Swatch {
  label: string;
  color: string;
  /** Draw as a dashed line rather than a solid block. */
  dashed?: boolean;
}

/**
 * Symbols each layer contributes to the map.
 *
 * Kept here rather than on `AuroraLayer` because the layer contract is about
 * *drawing*, and this is about *explaining* — a layer can be portrayed
 * differently for a valid reason without needing a second set of styles.
 */
const LEGEND: Record<string, (palette: Palette) => Swatch[]> = {
  enc: (p) => [
    { label: 'Charted land', color: p.land },
    { label: 'Shallow water', color: p.shallowWater },
    { label: 'Deep water', color: p.deepWater },
    { label: 'Depth contour', color: p.depthContour },
  ],
  coastline: (p) => [{ label: 'Coastline', color: p.coastline }],
  grid: (p) => [{ label: 'Lat/lon graticule', color: p.depthContour }],
  station: (p) => [{ label: 'Station', color: p.station }],
  sic: (p) => [{ label: 'Sea ice', color: p.sicIce }],
  sicUncertainty: (p) => [{ label: '90% interval', color: p.uncertainty }],
  icebergDrift: (p) => [{ label: 'Drift cone', color: p.iceberg, dashed: true }],
  iceberg: (p) => [{ label: 'Iceberg', color: p.iceberg }],
  route: (p) => [{ label: 'Recommended', color: p.route }],
  routeAlt: (p) => [{ label: 'Alternative', color: p.routeAlt, dashed: true }],
  alarmZone: (p) => [
    { label: 'Critical', color: p.alarm.critical },
    { label: 'Warning', color: p.alarm.warning },
    { label: 'Caution', color: p.alarm.caution },
  ],
  ais: (p) => [
    { label: 'No risk', color: p.ais.none },
    { label: 'Low', color: p.ais.low },
    { label: 'Medium', color: p.ais.medium },
    { label: 'High', color: p.ais.high },
  ],
  ownShip: (p) => [{ label: 'Own ship', color: p.vessel }],
};

function SwatchChip({ swatch }: { swatch: Swatch }): JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className={`h-2.5 w-6 shrink-0 rounded-[1px] ${swatch.dashed ? 'border-t-2 border-dashed' : ''}`}
        style={swatch.dashed ? { backgroundColor: 'transparent', borderColor: swatch.color } : { backgroundColor: swatch.color }}
      />
      <span className="truncate text-[11px] text-aurora-muted">{swatch.label}</span>
    </div>
  );
}

function LayerLegend({ id, title }: { id: string; title: string }): JSX.Element | null {
  const visible = useUiStore((state) => isLayerVisible(id, state));
  const displayMode = useUiStore((state) => state.displayMode);

  const build = LEGEND[id];
  if (!build) return null;

  const swatches = build(getPalette(displayMode));

  return (
    <div className={`py-1.5 ${visible ? '' : 'opacity-40'}`}>
      <p className="mb-1 text-[11px] text-aurora-text">{title}</p>

      <div className="flex flex-col gap-1 pl-1">
        {swatches.map((swatch) => (
          <SwatchChip key={swatch.label} swatch={swatch} />
        ))}
      </div>
    </div>
  );
}

export function LegendPanel({ className = '' }: { className?: string }): JSX.Element {
  const groups = layersByCategory();

  return (
    <Panel className={className} title="Legend">
      {groups.map(({ category, layers }) => {
        // Only categories that actually have a legend entry — an empty heading
        // tells the operator nothing about the map.
        const withEntries = layers.filter((layer) => LEGEND[layer.id]);
        if (withEntries.length === 0) return null;

        return (
          <section key={category} className="mb-2 border-b border-aurora-border/40 pb-2 last:mb-0 last:border-b-0 last:pb-0">
            <h3 className="mb-0.5 text-[10px] uppercase tracking-[0.2em] text-aurora-accent">
              {CATEGORY_LABELS[category]}
            </h3>

            {withEntries.map((layer) => (
              <LayerLegend key={layer.id} id={layer.id} title={layer.title} />
            ))}
          </section>
        );
      })}
    </Panel>
  );
}
