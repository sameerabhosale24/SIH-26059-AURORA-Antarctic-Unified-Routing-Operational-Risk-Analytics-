/**
 * Coastline portrayal.
 *
 * A single unfilled stroke in S-52 `CSTLN`. The coastline is drawn from the
 * backend's geometry rather than from a chart's land polygons, so it carries
 * no depth information and must never be drawn with the land fill.
 */
import { Stroke, Style } from 'ol/style';

import { REFERENCE_WIDTH } from '@/config/constants';
import type { Palette } from '@/config/palettes';

export function getCoastlineStyle(palette: Palette): Style {
  return new Style({
    stroke: new Stroke({
      color: palette.coastline,
      width: REFERENCE_WIDTH.coastline,
      lineJoin: 'round',
      lineCap: 'round',
    }),
  });
}
