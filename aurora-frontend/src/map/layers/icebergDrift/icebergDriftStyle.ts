/**
 * Drift-cone portrayal.
 *
 * A translucent fill with a dashed outline: the cone covers a large area of
 * otherwise meaningful chart, so it must never be opaque, and the dash keeps
 * it visually distinct from a restricted-area polygon (which is solid and
 * filled from S-52 `RESBL`).
 *
 * The containment probability is the single number an operator needs when
 * deciding whether the cone is worth acting on, so it is labelled directly on
 * the cone rather than hidden in a tooltip.
 */
import { Fill, Stroke, Style, Text } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import type { Palette } from '@/config/palettes';
import { withAlpha } from '../shared';
import { DRIFT_PROPS } from './icebergDriftSource';

export function getIcebergDriftStyle(palette: Palette): StyleFunction {
  const cone = new Style({
    fill: new Fill({ color: withAlpha(palette.iceberg, 0.14) }),
    stroke: new Stroke({
      color: withAlpha(palette.iceberg, 0.9),
      width: 1.5,
      lineDash: [8, 6],
    }),
    zIndex: 1,
  });

  const label = new Style({
    text: new Text({
      font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
      text: '',
      fill: new Fill({ color: palette.iceberg }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      overflow: true,
    }),
    zIndex: 2,
  });

  return (feature) => {
    const id = feature.get(DRIFT_PROPS.ID);
    const text = label.getText();
    if (typeof id !== 'string' || id === '' || !text) return cone;

    const probability = feature.get(DRIFT_PROPS.PROBABILITY);
    // A null probability is shown as an identifier only — never as 0 %.
    text.setText(
      typeof probability === 'number' && Number.isFinite(probability)
        ? `${id} · ${Math.round(probability * 100)}%`
        : id,
    );

    return [cone, label];
  };
}
