/**
 * Alternative-route portrayal.
 *
 * Thinner and dashed in the alternate colour, and drawn *below* the primary
 * route: an alternative is a comparison, not a recommendation, and the two
 * must never be confused at a glance. The dash is the differentiator that
 * survives a colour-blind operator and a monochrome night display.
 */
import { Style, Stroke } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import { ROUTE_WIDTH } from '@/config/constants';
import type { Palette } from '@/config/palettes';

export function getAlternativeRouteStyle(palette: Palette): StyleFunction {
  const line = new Style({
    stroke: new Stroke({
      color: palette.routeAlt,
      width: ROUTE_WIDTH.alternative,
      lineJoin: 'round',
      lineCap: 'round',
      lineDash: [12, 8],
    }),
    zIndex: 3,
  });

  return () => line;
}
