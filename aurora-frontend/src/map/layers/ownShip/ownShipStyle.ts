/**
 * Own-ship portrayal.
 *
 * A triangle rotated to the reported heading, so the direction of travel is
 * readable at a glance without a separate vector. The rotation is derived from
 * `heading` only; `cog` is deliberately not substituted, because in ice the
 * two routinely differ and a marker pointing along a course it is not making
 * is a hazard.
 *
 * When `heading` is null the marker falls back to an unrotated disc rather
 * than to zero — an unknown heading must not be drawn as due north.
 */
import CircleStyle from 'ol/style/Circle';
import RegularShape from 'ol/style/RegularShape';
import { Fill, Style, Stroke } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import type { Palette } from '@/config/palettes';
import { OWN_SHIP_PROPS } from './ownShipSource';

const RADIUS = 9;

export function getOwnShipStyle(palette: Palette): StyleFunction {
  // Rebuilt per style function rather than per feature: there is exactly one
  // own-ship feature, and a rotation change comes in with each 1 Hz update.
  const disc = new Style({
    image: new CircleStyle({
      radius: 6,
      fill: new Fill({ color: palette.vessel }),
      stroke: new Stroke({ color: palette.textHalo, width: 2 }),
    }),
    zIndex: 3,
  });

  return (feature) => {
    const heading = feature.get(OWN_SHIP_PROPS.HEADING);
    if (typeof heading !== 'number' || !Number.isFinite(heading)) return disc;

    const arrow = new Style({
      image: new RegularShape({
        points: 3,
        radius: RADIUS,
        // `heading` is degrees true (clockwise from north) and OL rotates
        // clockwise from the shape's default north, so the two agree.
        rotation: (heading * Math.PI) / 180,
        fill: new Fill({ color: palette.vessel }),
        stroke: new Stroke({ color: palette.textHalo, width: 2 }),
      }),
      zIndex: 3,
    });

    return arrow;
  };
}
