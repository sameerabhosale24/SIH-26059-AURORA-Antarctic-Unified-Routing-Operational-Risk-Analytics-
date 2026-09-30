/**
 * Graticule portrayal.
 *
 * The grid is a reading aid, not chart content: lines are drawn well below the
 * luminance of anything operational, and labels sit in a halo so they stay
 * legible over land, water and the SIC raster alike.
 *
 * Line and label are deliberately separate features rather than one style, so
 * a colour change in a display mode can move them independently — night mode
 * needs the labels dimmed further than the lines.
 */
import { Fill, Stroke, Style, Text } from 'ol/style';
import type { FeatureLike } from 'ol/Feature';
import type { StyleFunction } from 'ol/style/Style';

import { REFERENCE_WIDTH } from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { withAlpha } from '../shared';
import { GRID_PROPS, type GridFeatureKind } from './gridSource';

function readKind(feature: FeatureLike): GridFeatureKind | null {
  const value = feature.get(GRID_PROPS.KIND);
  return value === 'line' || value === 'label' ? value : null;
}

export function getGridStyle(palette: Palette): StyleFunction {
  const line = new Style({
    stroke: new Stroke({
      color: withAlpha(palette.text, palette.mode === 'night' ? 0.18 : 0.28),
      width: REFERENCE_WIDTH.graticule,
    }),
  });

  const label = new Style({
    text: new Text({
      font: '10px ui-monospace, SFMono-Regular, Menlo, monospace',
      fill: new Fill({ color: withAlpha(palette.text, palette.mode === 'night' ? 0.55 : 0.8) }),
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
