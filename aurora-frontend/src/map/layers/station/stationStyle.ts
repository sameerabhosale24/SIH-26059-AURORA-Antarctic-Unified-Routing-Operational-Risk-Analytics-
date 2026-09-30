/**
 * Station portrayal.
 *
 * A filled disc in the overlay's station colour, with the station name revealed
 * only once the view is detailed enough for it to be readable. Coordinates are
 * deliberately *not* labelled — the cursor already reads them out, and a
 * duplicate would crowd the label the operator actually wants.
 */
import CircleStyle from 'ol/style/Circle';
import { Fill, Style, Stroke, Text } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import { MARKER_SIZES, ZOOM_THRESHOLDS } from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { STATION_PROPS } from './stationSource';

export function getStationStyle(palette: Palette): StyleFunction {
  const marker = new Style({
    image: new CircleStyle({
      radius: MARKER_SIZES.station,
      fill: new Fill({ color: palette.station }),
      stroke: new Stroke({ color: palette.textHalo, width: 1.5 }),
    }),
    // Enough to keep a station distinguishable when the SIC raster sits above
    // it in luminance, without turning a 4 px disc into a blob.
    zIndex: 1,
  });

  const label = new Style({
    text: new Text({
      font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
      text: '',
      fill: new Fill({ color: palette.station }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      offsetY: -MARKER_SIZES.station - 5,
      overflow: true,
    }),
    zIndex: 2,
  });

  return (feature, resolution) => {
    if (resolution > ZOOM_THRESHOLDS.STATION_LABEL) return marker;

    const name = feature.get(STATION_PROPS.NAME);
    const text = label.getText();
    if (!text) return marker;

    // No name means no label — an unnamed station still shows its marker.
    if (typeof name !== 'string' || name.trim() === '') return marker;

    text.setText(name);
    return [marker, label];
  };
}
