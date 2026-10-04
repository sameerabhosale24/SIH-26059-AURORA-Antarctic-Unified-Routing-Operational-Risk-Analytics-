/**
 * S-52 portrayal for ENC features.
 *
 * The S-52 Presentation Library is **not** reimplemented here. Symbology comes
 * from `@s57-parser/s52-render`:
 *   - `lookupInstruction(OBJL, attributes)` gives the standard rendering
 *     instruction for an object class, including S-52's conditional symbology
 *     for DEPARE depth areas and LIGHTS.
 *   - `resolveColor(token, mode)` resolves the standard colour tokens for
 *     whichever S-52 presentation is selected — AURORA selects exactly one.
 *
 * This module is a mechanical adapter from those instructions to
 * `ol.style.Style`. It contains no chart knowledge of its own.
 *
 * ---------------------------------------------------------------------------
 * APPROXIMATION NOTICE — read before relying on this for navigation
 * ---------------------------------------------------------------------------
 * What is EXACT, because it comes from the presentation library:
 *   - depth-area and depth-contour colouring, including depth-band selection
 *     for DEPARE (DRVAL1/DRVAL2);
 *   - line vs area vs point vs text symbol class for each object class;
 *   - the S-52 colour tokens for that presentation;
 *   - the fallback instruction for unrecognised object classes.
 *
 * What is APPROXIMATED here, and why it is acceptable for this operating area:
 *   - **Pattern fills** (`hatch` / `cross-hatch` / `stipple`) are drawn as a
 *     plain translucent fill. Approximated because OL `Fill` has no pattern,
 *     and because the pattern-encoded classes in this corridor are sparse
 *     compared with depth areas and coastline.
 *   - **Sector arcs and light characteristics** are not drawn. Lights are
 *     rendered as a simple position symbol plus a text label. Approximated
 *     because the `@s57-parser` renderer exposes no arc geometry, and because
 *     sector light detail is not used for route planning in the
 *     Cape Town → Maitri/Bharati corridor.
 *   - **Scale-dependent visibility** is resolution-based, not per-object
 *     SCAMIN/SCAMAX. See {@link isVisibleAtResolution}.
 *
 * Anything safety-critical for navigation — coastline, depth areas, the safety
 * contour, wrecks, rocks, obstructions, restricted areas — is rendered from the
 * standard's own instruction and is not approximated. See
 * `src/config/palettes.ts` for the token-to-`Palette` mapping.
 */
import type { FeatureLike } from 'ol/Feature';
import type { StyleFunction } from 'ol/style/Style';
import CircleStyle from 'ol/style/Circle';
import Fill from 'ol/style/Fill';
import RegularShape from 'ol/style/RegularShape';
import Stroke from 'ol/style/Stroke';
import Style from 'ol/style/Style';
import Text from 'ol/style/Text';

import { lookupInstruction, resolveColor, rgbToCSS } from '@s57-parser/s52-render';
import type { RenderInstruction } from '@s57-parser/s52-render';

import { REFERENCE_WIDTH, ZOOM_THRESHOLDS } from '@/config/constants';
import { S52_PRESENTATION, type Palette } from '@/config/palettes';
import { ENC_PROPS } from './encSource';

/**
 * The presentation argument the S-52 library's colour resolver takes.
 *
 * Derived from the library rather than re-declared, so AURORA carries no
 * vocabulary for presentations it does not use.
 */
type S52Presentation = Parameters<typeof resolveColor>[1];

/** S-57 attribute codes this portrayal reads directly. */
const ATTL = {
  /** Value of maximum depth (DEPARE, DEPCNT). */
  DRVAL1: 31,
  /** Value of minimum depth (DEPARE, DEPCNT). */
  DRVAL2: 32,
  /** Sounding value (SOUNDG). */
  VALSOU: 140,
  /** Minimum scale denominator (SCAMIN). */
  SCAMIN: 178,
  /** Maximum scale denominator (SCAMAX). */
  SCAMAX: 179,
} as const;

/** Chart label text, in pixels. */
const LABEL_SIZE = 10;

/**
 * Attribute codes whose value is rendered as a label next to the symbol.
 * Only attributes that exist on the corresponding object class are used, so a
 * feature simply has nothing to label.
 */
const SOUNDING_TEXT_ATTL = ATTL.VALSOU;

/**
 * Plotting-standard pixel size, in metres, used to convert between an OL
 * resolution (ground metres per pixel) and a cartographic scale denominator.
 */
const PIXEL_SIZE_M = 0.00025;

/**
 * Scale-dependent visibility.
 *
 * Primary rule, when the chart supplies it: S-57 SCAMIN (ATTL 178) and
 * SCAMAX (ATTL 179) give the range of scale denominators at which an object is
 * displayed. Those attributes are read from the file — nothing is invented —
 * and applied exactly as the standard defines when present.
 *
 * Fallback, when a chart omits them: per-object visibility is unrestricted, and
 * only the resolution thresholds in `ZOOM_THRESHOLDS` gate labels and soundings.
 * That mirrors the resolution-based behaviour of the package's own renderer.
 */
function isVisibleAtResolution(
  attributes: Map<number, string>,
  resolution: number,
  maxResolution: number,
): boolean {
  const scamin = readNumber(attributes, ATTL.SCAMIN);
  const scamax = readNumber(attributes, ATTL.SCAMAX);

  if (scamin !== null || scamax !== null) {
    // SCAMIN/SCAMAX are scale denominators: ground metres per pixel divided by
    // the plotting-standard pixel size of 0.25 mm. OL's resolution is already
    // ground metres per pixel in the view projection, so no unit or projection
    // conversion is needed and the test is identical in LCC, polar and local.
    const scaleDenominator = resolution / PIXEL_SIZE_M;

    // Hidden once zoomed out beyond SCAMIN, or zoomed in beyond SCAMAX.
    // A bound absent from the chart is treated as unbounded rather than
    // defaulted — inventing a chart-wide scale limit would hide objects the
    // chart author intended to show.
    if (scamin !== null && scaleDenominator > scamin) return false;
    if (scamax !== null && scaleDenominator < scamax) return false;

    return true;
  }

  return resolution <= maxResolution;
}

/**
 * Portray one feature.
 *
 * Returns `undefined` to leave a feature undrawn, which is OpenLayers' way of
 * saying "hidden at this resolution".
 */
export function getEncStyle(palette: Palette): StyleFunction {
  const s52Mode: S52Presentation = S52_PRESENTATION;

  return function encStyleFunction(feature: FeatureLike, resolution: number): Style | Style[] | undefined {
    const objl = readNumberAttribute(feature, ENC_PROPS.OBJL, -1);
    const attributes = readAttributes(feature);

    if (objl < 0) return undefined;

    if (!isVisibleAtResolution(attributes, resolution, maxResolutionFor(objl))) return undefined;

    const instruction = lookupInstruction(objl, attributes);

    // ENC colours come from the S-52 presentation library verbatim; the
    // palette supplies only AURORA's own label colours. A single style carries
    // fill/stroke/image and OL applies whichever part matches the geometry, so
    // a polygon, a line and a point each render from the same instruction.
    const styles: Style[] = [];

    const style = new Style();

    const fill = resolveFill(instruction, s52Mode);
    if (fill) style.setFill(fill);

    const stroke = strokePart(instruction, s52Mode);
    if (stroke) style.setStroke(stroke);

    const image = pointPart(instruction, s52Mode);
    if (image) style.setImage(image);

    if (fill !== null || stroke !== null || image !== null) styles.push(style);

    const label = labelPart(instruction, attributes, palette, resolution, objl);
    if (label) styles.push(label);

    if (styles.length === 0) return undefined;
    return styles;
  };
}

function maxResolutionFor(objl: number): number {
  // Only classes whose whole purpose is to disappear when zoomed out are gated.
  // Land and depth areas must never vanish: an operator seeing "no land" is
  // worse than a busy chart.
  if (objl === 129 || objl === 75 || objl === 76) return ZOOM_THRESHOLDS.SOUNDING_LABEL;
  return Number.POSITIVE_INFINITY;
}

function resolveFill(instruction: RenderInstruction, s52Mode: S52Presentation): Fill | null {
  // S-52 pattern fills are approximated by a translucent fill (see header).
  if (instruction.fillAlpha !== undefined && instruction.fillAlpha <= 0) return null;
  if (!instruction.fill && !instruction.pattern) return null;

  const token = instruction.fill ?? instruction.patternColor;
  if (!token) return null;

  return new Fill({
    color: rgbToCSS(resolveColor(token, s52Mode), instruction.fillAlpha ?? 1),
  });
}

function strokePart(instruction: RenderInstruction, s52Mode: S52Presentation): Stroke | null {
  const token = instruction.stroke;
  if (!token) return null;

  const width =
    instruction.strokeWidth ??
    (instruction.type === 'line' ? REFERENCE_WIDTH.coastline : REFERENCE_WIDTH.depthContour);

  return new Stroke({
    color: rgbToCSS(resolveColor(token, s52Mode)),
    width,
    lineDash: instruction.dashPattern ?? undefined,
  });
}

/**
 * Point symbols.
 *
 * Circles and diamonds map to `CircleStyle`; triangles map to `RegularShape`
 * (OpenLayers' triangle rotation is 45° from square). Sector arcs and light
 * characteristics are intentionally not drawn — see the header notice.
 */
function pointPart(instruction: RenderInstruction, s52Mode: S52Presentation): CircleStyle | RegularShape | null {
  if (instruction.type !== 'point') return null;

  const radius = instruction.radius ?? 3;
  const color = rgbToCSS(resolveColor(instruction.fill ?? instruction.stroke ?? 'CHBLK', s52Mode));

  switch (instruction.shape) {
    case 'circle':
      return new CircleStyle({
        radius,
        fill: new Fill({ color }),
        stroke: new Stroke({ color, width: 0.5 }),
      });
    case 'triangle':
      return new RegularShape({
        points: 3,
        radius,
        rotation: Math.PI / 2,
        fill: new Fill({ color }),
      });
    case 'square':
      return new RegularShape({
        points: 4,
        radius,
        fill: new Fill({ color }),
        stroke: new Stroke({ color, width: 0.5 }),
      });
    case 'diamond':
      return new CircleStyle({
        radius,
        fill: new Fill({ color }),
        stroke: new Stroke({ color, width: 1 }),
      });
    default:
      return new CircleStyle({
        radius,
        fill: new Fill({ color }),
      });
  }
}

function labelPart(
  instruction: RenderInstruction,
  attributes: Map<number, string>,
  palette: Palette,
  resolution: number,
  objl: number,
): Style | null {
  const raw = attributes.get(SOUNDING_TEXT_ATTL);
  if (raw === undefined || raw === '') return null;

  // Only sounding and light classes are labelled in this portrayal. An object
  // from any other class simply has nothing to say here.
  const isLabelledClass = objl === 129 || objl === 75 || objl === 76;
  if (!isLabelledClass) return null;

  const limit = objl === 129 ? ZOOM_THRESHOLDS.SOUNDING_LABEL : ZOOM_THRESHOLDS.LIGHT_LABEL;
  if (resolution > limit) return null;

  // Light characteristics (Fl(3) 10s etc.) are not formatted here — see header.
  return new Style({
    text: new Text({
      text: raw,
      font: `${LABEL_SIZE}px system-ui, sans-serif`,
      fill: new Fill({ color: palette.text }),
      stroke: new Stroke({ color: palette.textHalo, width: 3 }),
      textAlign: instruction.textAlign ?? 'center',
      offsetY: instruction.textOffsetY ?? -10,
      overflow: true,
    }),
  });
}

function readNumber(attributes: Map<number, string>, code: number): number | null {
  const raw = attributes.get(code);
  if (raw === undefined) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

function readNumberAttribute(feature: FeatureLike, key: string, fallback: number): number {
  const value = feature.get(key);
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function readAttributes(feature: FeatureLike): Map<number, string> {
  const value = feature.get(ENC_PROPS.ATTRS);
  return value instanceof Map ? (value as Map<number, string>) : new Map();
}

