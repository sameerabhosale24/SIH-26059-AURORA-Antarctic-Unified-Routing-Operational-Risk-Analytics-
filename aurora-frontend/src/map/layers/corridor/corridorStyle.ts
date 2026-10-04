/**
 * Corridor and coverage portrayal.
 *
 * The corridor is deliberately quiet — a 40 % dashed hairline that says "this
 * is the general shape of the voyage" without competing with the computed
 * route — and the coverage rectangle is quieter still, appearing only when the
 * operator is looking at the whole corridor rather than down at a segment of
 * it.
 */
import { Fill, Stroke, Style, Text } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import type { Palette } from '@/config/palettes';
import { withAlpha } from '../shared';
import { CORRIDOR_PROPS, type CorridorKind } from './corridorSource';

/** ocean-400 — the corridor's colour, by design. */
export const CORRIDOR_COLOR = '#5FB0DD';

/** ocean-400 at 40 % — the reference corridor is deliberately quiet. */
const CORRIDOR_STROKE = 'rgba(95, 176, 221, 0.4)';

/** Dash pattern for the corridor lines, in pixels. */
const CORRIDOR_DASH: number[] = [12, 8];

/** Dash pattern for the coverage rectangle, in pixels. */
const ROI_DASH: number[] = [6, 6];

/**
 * @param palette portrayal for the caption and the coverage outline.
 * @param roiVisibleFrom view resolution at which the coverage rectangle turns
 *        on — the resolution the full corridor framing fits the viewport at.
 *        Anything coarser (zoomed out) shows it; anything finer hides it.
 */
export function getCorridorStyle(palette: Palette, roiVisibleFrom: number): StyleFunction {
  const line = new Style({
    stroke: new Stroke({
      color: CORRIDOR_STROKE,
      width: 2,
      lineDash: CORRIDOR_DASH,
    }),
    zIndex: 1,
  });

  const roi = new Style({
    stroke: new Stroke({
      color: withAlpha(palette.text, 0.5),
      width: 1,
      lineDash: ROI_DASH,
    }),
    zIndex: 2,
  });

  const label = new Style({
    text: new Text({
      font: '11px sans-serif',
      text: '',
      fill: new Fill({ color: palette.text }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      // Sitting just above the rectangle's top edge.
      offsetY: -8,
      overflow: true,
    }),
    zIndex: 3,
  });

  return (feature, resolution) => {
    const kind = feature.get(CORRIDOR_PROPS.KIND) as CorridorKind | undefined;

    if (kind === 'line') return line;
    if (kind !== 'roi' && kind !== 'label') return undefined;

    // Coverage only matters when the operator can see the whole corridor; up
    // close it would just sit under the route and the stations.
    if (resolution < roiVisibleFrom) return undefined;
    if (kind === 'roi') return roi;

    const text = feature.get(CORRIDOR_PROPS.TEXT);
    if (typeof text !== 'string' || text === '') return undefined;

    label.getText()?.setText(text);
    return label;
  };
}
