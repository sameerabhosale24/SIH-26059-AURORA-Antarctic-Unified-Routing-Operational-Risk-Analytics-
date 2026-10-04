/**
 * Coastline portrayal.
 *
 * The backend publishes land *polygons* (Natural Earth `ne_10m_land`, clipped
 * to the ROI), so the layer is drawn the way a chart draws land: a grey fill
 * under an S-52 `CSTLN` stroke. The stroke alone would leave the ocean
 * showing through the continent, which reads as an outline rather than as
 * land.
 *
 * If the backend ever publishes a line-only coastline the fill is harmless —
 * a `LineString` has no interior for `Fill` to paint — so no geometry check is
 * needed here.
 */
import { Fill, Stroke, Style } from 'ol/style';

import { REFERENCE_WIDTH } from '@/config/constants';
import type { Palette } from '@/config/palettes';

export function getCoastlineStyle(palette: Palette): Style {
  return new Style({
    fill: new Fill({ color: palette.land }),
    stroke: new Stroke({
      color: palette.coastline,
      width: REFERENCE_WIDTH.coastline,
      lineJoin: 'round',
      lineCap: 'round',
    }),
  });
}
