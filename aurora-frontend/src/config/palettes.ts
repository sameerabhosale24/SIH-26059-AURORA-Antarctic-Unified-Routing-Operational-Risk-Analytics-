/**
 * Display palettes.
 *
 * Two independent colour systems meet here:
 *
 *  1. **S-52 chart colours** come from `@s57-parser/s52-render` verbatim, via
 *     `resolveColor(token, mode)`. Nothing here re-implements or overrides an
 *     S-52 token — ENC symbology must match the standard exactly.
 *  2. **AURORA overlay colours** (SIC, AIS, icebergs, routes, alarms) sit on
 *     top of the chart and are tuned per mode so overlays stay readable
 *     against the chart beneath them. Night values are deliberately
 *     red-shifted and low-luminance to protect night vision on the bridge.
 *
 * The package's display modes are `DAY_BRIGHT | DUSK | NIGHT`; AURORA's UI
 * uses `day | dusk | night`. `toS52Mode` is the single mapping point.
 */
import { resolveColor, rgbToCSS } from '@s57-parser/s52-render';
import type { DisplayMode as S52DisplayMode } from '@s57-parser/s52-render';

/** AURORA display modes, as used by `uiStore.displayMode`. */
export type DisplayMode = 'day' | 'dusk' | 'night';

export const DISPLAY_MODES: readonly DisplayMode[] = ['day', 'dusk', 'night'];

/** AURORA mode → the mode name understood by `@s57-parser/s52-render`. */
export function toS52Mode(mode: DisplayMode): S52DisplayMode {
  switch (mode) {
    case 'day':
      return 'DAY_BRIGHT';
    case 'dusk':
      return 'DUSK';
    case 'night':
      return 'NIGHT';
  }
}

export interface Palette {
  mode: DisplayMode;

  /* --- S-52 chart colours (verbatim from the standard) --- */
  /** Map canvas background — S-52 NODTA. */
  background: string;
  /** Land fill — S-52 LANDA. */
  land: string;
  /** Water shallower than the safety contour — S-52 DEPVS. */
  shallowWater: string;
  /** Water deeper than the safety contour — S-52 DEPDW. */
  deepWater: string;
  /** Coastline — S-52 CSTLN. */
  coastline: string;
  /** Depth contour line — S-52 DEPSC. */
  depthContour: string;
  /** Rocks, wrecks, obstructions — S-52 CHBLK. */
  hazard: string;
  /** Chart text — S-52 SNDG1. */
  text: string;
  /** Text halo, drawn in the background colour so labels stay legible. */
  textHalo: string;
  /** Restricted / danger area fill — S-52 RESBL. */
  restricted: string;
  /** Light symbols — S-52 LITRD. */
  light: string;

  /* --- AURORA overlay colours (tuned per mode) --- */
  route: string;
  routeAlt: string;
  sicIce: string;
  sicOpen: string;
  uncertainty: string;
  ais: { none: string; low: string; medium: string; high: string };
  alarm: { critical: string; warning: string; caution: string };
  station: string;
  vessel: string;
  iceberg: string;
}

type AurataTokens = Pick<
  Palette,
  | 'route'
  | 'routeAlt'
  | 'sicIce'
  | 'sicOpen'
  | 'uncertainty'
  | 'ais'
  | 'alarm'
  | 'station'
  | 'vessel'
  | 'iceberg'
>;

/**
 * AURORA overlay colours. Deliberately not S-52 tokens: these are operational
 * overlays, not chart symbology, and must not be confused with it.
 *
 * Day  — full-saturation, dark background contrast.
 * Dusk — dimmed, cooler.
 * Night — low-luminance red-shifted. Per bridge practice night lighting is
 *        red because the eye is far more sensitive to red at low luminance, so
 *        white overlays destroy dark adaptation.
 */
const auroraTokens: Record<DisplayMode, AurataTokens> = {
  day: {
    route: '#f8fafc',
    routeAlt: '#38bdf8',
    sicIce: '#f1f5f9',
    sicOpen: '#0e7490',
    uncertainty: '#a78bfa',
    ais: { none: '#16a34a', low: '#ca8a04', medium: '#ea580c', high: '#dc2626' },
    alarm: { critical: '#dc2626', warning: '#ea580c', caution: '#ca8a04' },
    station: '#7c3aed',
    vessel: '#22d3ee',
    iceberg: '#e2e8f0',
  },
  dusk: {
    route: '#e2e8f0',
    routeAlt: '#0ea5e9',
    sicIce: '#cbd5e1',
    sicOpen: '#155e75',
    uncertainty: '#8b5cf6',
    ais: { none: '#15803d', low: '#a16207', medium: '#c2410c', high: '#b91c1c' },
    alarm: { critical: '#b91c1c', warning: '#c2410c', caution: '#a16207' },
    station: '#6d28d9',
    vessel: '#06b6d4',
    iceberg: '#cbd5e1',
  },
  night: {
    route: '#c08080',
    routeAlt: '#7a3a3a',
    sicIce: '#8a6a6a',
    sicOpen: '#4a2a2a',
    uncertainty: '#6b3a6b',
    ais: { none: '#7a2020', low: '#8a5a10', medium: '#8a3010', high: '#a01010' },
    alarm: { critical: '#a01010', warning: '#8a3010', caution: '#8a5a10' },
    station: '#5a2a6a',
    vessel: '#8a3a3a',
    iceberg: '#8a6a6a',
  },
};

function build(mode: DisplayMode): Palette {
  const s52 = toS52Mode(mode);
  const token = (name: string): string => rgbToCSS(resolveColor(name, s52));

  return {
    mode,
    background: token('NODTA'),
    land: token('LANDA'),
    shallowWater: token('DEPVS'),
    deepWater: token('DEPDW'),
    coastline: token('CSTLN'),
    depthContour: token('DEPSC'),
    hazard: token('CHBLK'),
    text: token('SNDG1'),
    textHalo: token('NODTA'),
    restricted: token('RESBL'),
    light: token('LITRD'),
    ...auroraTokens[mode],
  };
}

export const PALETTES: Record<DisplayMode, Palette> = {
  day: build('day'),
  dusk: build('dusk'),
  night: build('night'),
};

export function getPalette(mode: DisplayMode): Palette {
  return PALETTES[mode];
}
