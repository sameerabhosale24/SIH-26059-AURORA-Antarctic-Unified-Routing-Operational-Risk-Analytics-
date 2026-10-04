/**
 * Station portrayal.
 *
 * An amber disc with the station name set beside it, so a label never covers
 * the marker it names. Coordinates are deliberately *not* labelled — the cursor
 * already reads them out, and a duplicate would crowd the label the operator
 * actually wants.
 *
 * ## Label gate
 *
 * Labels are shown from `ZOOM_THRESHOLDS.STATION_LABEL` upwards, where that
 * value is a **view zoom level** (4), not a resolution. OpenLayers converts
 * between the two with `View#getResolutionForZoom`, and that mapping depends on
 * the view's own projection, so the threshold is resolved against the live view
 * once when the layer is built (`stationLayer.build`) rather than hardcoded
 * here.
 */
import CircleStyle from 'ol/style/Circle';
import { Fill, Style, Stroke, Text } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import { MARKER_SIZES } from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { STATION_PROPS } from './stationSource';

/**
 * Station fill.
 *
 * `palette.station` is still the violet of the original palette set; the
 * console's station colour is amber, so the marker carries the literal until
 * the palette catches up. Palette definitions are not changed here.
 */
export const STATION_COLOR = '#FFB300';

/** Station outline — the palette's text colour, which is white. */
const STATION_STROKE = '#FFFFFF';

export function getStationStyle(palette: Palette, labelResolution: number): StyleFunction {
  const marker = new Style({
    image: new CircleStyle({
      radius: MARKER_SIZES.station, // 6 px
      fill: new Fill({ color: STATION_COLOR }),
      stroke: new Stroke({ color: STATION_STROKE, width: 1 }),
    }),
    // Above the SIC raster so a station is never lost under the ice field.
    zIndex: 1,
  });

  const label = new Style({
    text: new Text({
      font: '12px sans-serif',
      text: '',
      fill: new Fill({ color: palette.text }),
      // One pixel of the palette's dark halo: enough to keep white type
      // legible over land, ocean and the SIC raster alike.
      stroke: new Stroke({ color: palette.textHalo, width: 1 }),
      // Beside the dot, vertically centred on it.
      offsetX: MARKER_SIZES.station + 4,
      textBaseline: 'middle',
      overflow: true,
    }),
    zIndex: 2,
  });

  return (feature, resolution) => {
    if (resolution > labelResolution) return marker;

    const name = feature.get(STATION_PROPS.NAME);

    // No name means no label — an unnamed station still shows its marker.
    if (typeof name !== 'string' || name.trim() === '') return marker;

    label.getText()?.setText(name);
    return [marker, label];
  };
}
