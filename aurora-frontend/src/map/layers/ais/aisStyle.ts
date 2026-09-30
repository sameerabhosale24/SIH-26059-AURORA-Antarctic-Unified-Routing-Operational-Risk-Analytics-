/**
 * AIS target portrayal.
 *
 * Colour carries the backend's risk band — CPA and risk are computed server
 * side and are never recomputed here. A target past
 * `AIS_LIFETIME.FADE_AFTER_SECONDS` drops to a dimmed variant of its own
 * colour rather than to a neutral grey: the operator still needs to see *which*
 * band it was, because the risk was assessed against a position that is now
 * that old.
 *
 * Labels are gated on resolution so the corridor overview stays readable; the
 * values shown are whatever the payload carried, and a null CPA or TCPA is
 * omitted entirely instead of being rendered as zero.
 */
import CircleStyle from 'ol/style/Circle';
import { Fill, Style, Stroke, Text } from 'ol/style';
import type { StyleFunction } from 'ol/style/Style';

import { AIS_LIFETIME, ZOOM_THRESHOLDS } from '@/config/constants';
import type { Palette } from '@/config/palettes';
import { withAlpha } from '../shared';
import { AIS_PROPS } from './aisSource';

type RiskBand = 'none' | 'low' | 'medium' | 'high';

const RISK_BANDS: readonly RiskBand[] = ['none', 'low', 'medium', 'high'];

function isRiskBand(value: unknown): value is RiskBand {
  return typeof value === 'string' && (RISK_BANDS as readonly string[]).includes(value);
}

/** Resolve the payload's risk band, defaulting to `none` only when it is null. */
function riskOf(feature: { get(key: string): unknown }): RiskBand {
  const value = feature.get(AIS_PROPS.RISK);
  return isRiskBand(value) ? value : 'none';
}

/**
 * Build a label style at a given opacity.
 *
 * OpenLayers' `Style` has no opacity option, so a faded target's label is
 * dimmed by baking the alpha into the fill and halo colours instead.
 */
function buildLabel(palette: Palette, risk: RiskBand, alpha: number): {
  style: Style;
  text: Text;
} {
  const text = new Text({
    font: '11px ui-monospace, SFMono-Regular, Menlo, monospace',
    text: '',
    fill: new Fill({ color: withAlpha(palette.ais[risk], alpha) }),
    stroke: new Stroke({ color: withAlpha(palette.textHalo, Math.min(1, alpha + 0.2)), width: 3 }),
    offsetY: -9,
    overflow: true,
  });

  return {
    style: new Style({ text, zIndex: 2 }),
    text,
  };
}

export function getAisStyle(palette: Palette): StyleFunction {
  const markers = new Map<RiskBand, Style>();
  const fadedMarkers = new Map<RiskBand, Style>();
  const labels = new Map<RiskBand, ReturnType<typeof buildLabel>>();
  const fadedLabels = new Map<RiskBand, ReturnType<typeof buildLabel>>();

  for (const band of RISK_BANDS) {
    const color = palette.ais[band];

    markers.set(
      band,
      new Style({
        image: new CircleStyle({
          radius: 5,
          fill: new Fill({ color }),
          stroke: new Stroke({
            color: palette.textHalo,
            // A high-risk target gets a heavier outline as well as a hotter
            // fill, so the band survives a colour-blind operator and a
            // low-luminance night display.
            width: band === 'high' ? 2.5 : 1.5,
          }),
        }),
        zIndex: 1,
      }),
    );

    fadedMarkers.set(
      band,
      new Style({
        image: new CircleStyle({
          radius: 5,
          fill: new Fill({ color: withAlpha(color, 0.45) }),
          stroke: new Stroke({ color: withAlpha(palette.textHalo, 0.45), width: 1.5 }),
        }),
        zIndex: 1,
      }),
    );

    labels.set(band, buildLabel(palette, band, 1));
    fadedLabels.set(band, buildLabel(palette, band, 0.5));
  }

  return (feature, resolution) => {
    const band = riskOf(feature);
    const age = feature.get(AIS_PROPS.AGE_S);
    const faded = typeof age === 'number' && age > AIS_LIFETIME.FADE_AFTER_SECONDS;

    const marker = (faded ? fadedMarkers : markers).get(band) ?? markers.get('none');
    if (!marker) return undefined;
    if (resolution > ZOOM_THRESHOLDS.AIS_LABEL) return marker;

    const name = feature.get(AIS_PROPS.NAME);
    const mmsi = feature.get(AIS_PROPS.MMSI);
    const identifier =
      typeof name === 'string' && name.trim() !== ''
        ? name.trim()
        : mmsi !== undefined && mmsi !== null
          ? String(mmsi)
          : null;

    if (identifier === null) return marker;

    const details: string[] = [];
    const cpa = feature.get(AIS_PROPS.CPA_NM);
    const tcpa = feature.get(AIS_PROPS.TCPA_MIN);

    if (typeof cpa === 'number' && Number.isFinite(cpa)) details.push(`CPA ${cpa.toFixed(1)}nm`);
    if (typeof tcpa === 'number' && Number.isFinite(tcpa)) details.push(`TCPA ${Math.round(tcpa)}m`);

    const entry = (faded ? fadedLabels : labels).get(band);
    if (!entry) return marker;

    entry.text.setText(details.length > 0 ? `${identifier}  ${details.join(' ')}` : identifier);
    return [marker, entry.style];
  };
}
