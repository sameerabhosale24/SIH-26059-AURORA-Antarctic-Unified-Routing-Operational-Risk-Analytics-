/**
 * Graticule portrayal.
 *
 * The grid is a reading aid, not chart content: lines are drawn well below the
 * luminance of anything operational, and labels sit in a halo so they stay
 * legible over land, water and the SIC raster alike.
 *
 * Line and label are deliberately separate features rather than one style, so
 * their weight can move independently without rebuilding either.
 */
import { Fill, Stroke, Style, Text } from 'ol/style';
import type { FeatureLike } from 'ol/Feature';
import type { StyleFunction } from 'ol/style/Style';

import { REFERENCE_WIDTH } from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { withAlpha } from '../shared';
import { GRID_PROPS, type GridFeatureKind } from './gridSource';

/** Line weight, as a fraction of the text colour — faint, but readable over
 *  both white pack ice and the ocean background. */
const LINE_ALPHA = 0.35;
/** Label weight — the labels must read at a glance. */
const LABEL_ALPHA = 0.8;

function readKind(feature: FeatureLike): GridFeatureKind | null {
  const value = feature.get(GRID_PROPS.KIND);
  return value === 'line' || value === 'label' ? value : null;
}

export function getGridStyle(palette: Palette): StyleFunction {
  const line = new Style({
    stroke: new Stroke({
      color: withAlpha(palette.text, LINE_ALPHA),
      width: REFERENCE_WIDTH.graticule,
    }),
  });

  const label = new Style({
    text: new Text({
      font: '10px ui-monospace, SFMono-Regular, Menlo, monospace',
      fill: new Fill({ color: withAlpha(palette.text, LABEL_ALPHA) }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      overflow: true,
    }),
  });

  return (feature) => {
    const kind = readKind(feature);
    if (kind === 'label') {
      const text = feature.get(GRID_PROPS.TEXT);
      if (typeof text !== 'string' || text === '') return undefined;
      label.getText()?.setText(text);
      return label;
    }
    if (kind === 'line') return line;
    return undefined;
  };
}
