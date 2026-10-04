/**
 * Display palette.
 *
 * AURORA renders a single presentation: **Day**. There is no Dusk or Night
 * variant anywhere in the runtime path — no mode switch, no per-mode chrome,
 * no re-portrayal on a lighting change. One palette is built at module load
 * and every consumer reads it.
 *
 * Two colour systems meet in that palette:
 *
 *  1. **S-52 chart colours** come from `@s57-parser/s52-render` verbatim, via
 *     `resolveColor(token, mode)`. Nothing here re-implements an S-52 token
 *     that ENC symbology depends on.
 *  2. **AURORA overview colours** (the canvas, land, overlays) are chosen for
 *     the console as a whole: a blue ocean the overlays are tuned against,
 *     grey land, and text light enough to read over both.
 */
import { resolveColor, rgbToCSS } from '@s57-parser/s52-render';

/**
 * The single S-52 presentation AURORA renders.
 *
 * Exported because the ENC style resolves its instruction colours against the
 * same presentation library and must not drift from the palette above.
 */
export const S52_PRESENTATION = 'DAY_BRIGHT' as const;

export interface Palette {
  /* --- S-52 chart colours (verbatim from the standard) --- */
  /** Map canvas background — the open ocean behind every layer. */
  background: string;
  /** Land fill. */
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
  /** Text halo, drawn so labels stay legible over the ocean beneath them. */
  textHalo: string;
  /** Restricted / danger area fill — S-52 RESBL. */
  restricted: string;
  /** Light symbols — S-52 LITRD. */
  light: string;

  /* --- AURORA overlay colours --- */
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

/**
 * AURORA's own colours, over the S-52 tokens.
 *
 * The ocean and land values are the console's identity, not chart symbology:
 * they are what the panels, the landing page and the graticule are tuned
 * against, and they are deliberately not the S-52 `NODTA`/`LANDA` tokens —
 * those describe an ENC's own no-data and land areas, which is a different
 * question from "what colour is the water in AURORA".
 */
const auroraTokens = {
  background: '#1E6091',
  land: '#9E9E9E',
  text: '#FFFFFF',
  textHalo: '#0A2A45',
  route: '#f8fafc',
  routeAlt: '#38bdf8',
  sicIce: '#f1f5f9',
  sicOpen: '#0e7490',
  uncertainty: '#a78bfa',
  ais: { none: '#16a34a', low: '#ca8a04', medium: '#ea580c', high: '#dc2626' },
  alarm: { critical: '#dc2626', warning: '#ea580c', caution: '#ca8a04' },
  station: '#7c3aed',
  vessel: '#22d3ee',
  iceberg: '#FFFFFF',
} as const;

function build(): Palette {
  const token = (name: string): string => rgbToCSS(resolveColor(name, S52_PRESENTATION));

  return {
    ...auroraTokens,
    shallowWater: token('DEPVS'),
    deepWater: token('DEPDW'),
    coastline: token('CSTLN'),
    depthContour: token('DEPSC'),
    hazard: token('CHBLK'),
    restricted: token('RESBL'),
    light: token('LITRD'),
  };
}

/** The one palette. Built once — the console has a single presentation. */
export const PALETTE: Palette = build();

/**
 * The palette.
 *
 * Takes no argument: there is nothing to select between.
 */
export function getPalette(): Palette {
  return PALETTE;
}
