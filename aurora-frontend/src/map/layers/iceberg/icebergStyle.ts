/**
 * Iceberg position portrayal.
 *
 * Iceberg identifiers are the only handle the operator has when relaying a
 * sighting, so the label is drawn at every zoom level rather than gated behind
 * a threshold — the population is small enough that it cannot crowd the map,
 * and an unlabelled hazard is close to useless.
 *
 * The marker radius is fixed rather than scaled by `length_km`: a size-coded
 * disc would read as a positional accuracy circle, and AURORA does not know
 * the positional accuracy of the observation.
 */
import CircleStyle from 'ol/style/Circle';
import { Fill, Style, Stroke, Text } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import { MARKER_SIZES } from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { ICEBERG_PROPS } from './icebergSource';

export function getIcebergStyle(palette: Palette): StyleFunction {
  const marker = new Style({
    image: new CircleStyle({
      radius: MARKER_SIZES.iceberg,
      fill: new Fill({ color: palette.iceberg }),
      stroke: new Stroke({ color: palette.textHalo, width: 1.5 }),
    }),
    zIndex: 2,
  });

  const label = new Style({
    text: new Text({
      font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
      text: '',
      fill: new Fill({ color: palette.iceberg }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      offsetY: -MARKER_SIZES.iceberg - 5,
      overflow: true,
    }),
    zIndex: 3,
  });

  return (feature) => {
    const id = feature.get(ICEBERG_PROPS.ID);
    const text = label.getText();
    if (typeof id !== 'string' || id === '' || !text) return marker;

    const size = feature.get(ICEBERG_PROPS.SIZE_KM);
    // A missing size is not "0 km" — the identifier alone is shown.
    text.setText(
      typeof size === 'number' && Number.isFinite(size) ? `${id} · ${size.toFixed(1)} km` : id,
    );

    return [marker, label];
  };
}
