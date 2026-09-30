/**
 * Lambert Conformal Conic projection for the AURORA operating area.
 *
 * The map is NOT Web Mercator. The view uses `EPSG:9802`, and feature
 * geometries stay in WGS84 lon/lat — OpenLayers converts them at render time
 * because `EPSG:4326` is declared as its *user projection*
 * (see {@link declareUserProjection}).
 *
 * Conic projection is used because the operating area spans ~90° of longitude
 * at high southern latitudes, where Mercator badly distorts both scale and
 * shape. A Lambert Conformal Conic with standard parallels at 45°S and 65°S
 * is near-conformal across the Cape Town → Maitri/Bharati corridor.
 *
 * Verify registration from the browser console (dev server only):
 *
 *   __aurora.lccProjection()  // the registered OpenLayers Projection
 *   __aurora.lccTest()        // [lon, lat, x, y] round trip for the origin
 */
import proj4 from 'proj4';
import type { Coordinate } from 'ol/coordinate';
import { get as getProjection, getUserProjection, setUserProjection, transform } from 'ol/proj';
import type { Projection } from 'ol/proj';
import { isRegistered as isProj4Registered, register as registerProj4 } from 'ol/proj/proj4';
import type { Roi } from '@/types/common';

/** Raw proj4 definition string for the AURORA operating projection. */
export const LCC_PROJECTION =
  '+proj=lcc +lat_1=-45 +lat_2=-65 +lat_0=-55 +lon_0=35 +x_0=0 +y_0=0 ' +
  '+datum=WGS84 +units=m +no_defs';

/** Code under which the LCC projection is registered in proj4 and OpenLayers. */
export const LCC_CODE = 'EPSG:9802';

/**
 * WGS 84 / Antarctic Polar Stereographic — the standard EPSG code for the
 * polar view. Used by the `polar` projection preset.
 */
export const POLAR_CODE = 'EPSG:3031';

export const POLAR_PROJECTION =
  '+proj=stere +lat_0=-90 +lat_ts=-71 +lon_0=0 +k=1 +x_0=0 +y_0=0 ' +
  '+datum=WGS84 +units=m +no_defs';

/** Geographic CRS used for all I/O with the backend. */
export const WGS84_CODE = 'EPSG:4326';

/** `[minX, minY, maxX, maxY]`. */
export type BoxExtent = [number, number, number, number];

let isRegistered = false;

/**
 * Define `EPSG:9802` with proj4 and hand the proj4 registry to OpenLayers.
 *
 * Idempotent: safe to call from every entry point. Both definitions must be
 * added *before* OpenLayers registers, because it does not rewrite existing
 * transforms afterwards — that is why POLAR is defined here too rather than in
 * its own call.
 */
export function registerLccProjection(): void {
  if (isRegistered) return;

  proj4.defs(LCC_CODE, LCC_PROJECTION);
  proj4.defs(POLAR_CODE, POLAR_PROJECTION);

  if (!isProj4Registered()) {
    registerProj4(proj4);
  }

  declareUserProjection();

  isRegistered = true;
}

/**
 * Declare WGS84 as OpenLayers' *user projection*.
 *
 * This is the mechanism behind the "OpenLayers reprojects automatically"
 * behaviour AURORA relies on. OpenLayers does **not** transform vector
 * feature geometries by default — it expects coordinates already expressed in
 * the view projection. With a user projection set, OL instead:
 *
 *   - transforms user coordinates to the view projection while rendering
 *     (`renderer/VectorLayer.js` reads `getUserProjection()`);
 *   - returns `MousePosition`, `forEachFeatureAtPixel` and map event
 *     coordinates in WGS84 instead;
 *   - leaves `ol.View` methods (`setCenter`, `fit`) alone, so those still take
 *     view-projection metres — see `toLCC`.
 *
 * Consequences that matter:
 *   - every vector layer stores plain lon/lat and is authored once;
 *   - switching the projection preset rebuilds no layer;
 *   - `ol/View`'s public methods (`setCenter`, `animate`, `fit`,
 *     `calculateExtent`) also take and return lon/lat, because they run their
 *     argument through `fromUserCoordinate`/`fromUserExtent`. Nothing must call
 *     `toLCC()` before handing a position to the view, or it is transformed
 *     twice — only *resolution* stays in view-projection units.
 *
 * Must run before any map or layer is created.
 */
function declareUserProjection(): void {
  if (getUserProjection()?.getCode() === WGS84_CODE) return;
  setUserProjection(WGS84_CODE);
}

/**
 * The OpenLayers `Projection` object for the AURORA LCC, registered and ready.
 *
 * @throws if the projection is unavailable (registration failed).
 */
export function lccProjection(): Projection {
  registerLccProjection();

  const projection = getProjection(LCC_CODE);

  if (!projection) {
    throw new Error(
      `Projection ${LCC_CODE} is not registered. registerLccProjection() must run before the map is created.`,
    );
  }

  return projection;
}

/** The Antarctic polar-stereographic projection, registered and ready. */
export function polarProjection(): Projection {
  registerLccProjection();

  const projection = getProjection(POLAR_CODE);

  if (!projection) {
    throw new Error(`Projection ${POLAR_CODE} is not registered.`);
  }

  return projection;
}

/**
 * OpenLayers returns coordinates as `number[]`, so a malformed result is
 * possible in principle. Fail loudly here rather than letting a `NaN` reach
 * the map, where it would silently break rendering.
 */
function toPair(coordinate: Coordinate, label: string): [number, number] {
  const x = coordinate[0];
  const y = coordinate[1];

  if (typeof x !== 'number' || typeof y !== 'number' || !Number.isFinite(x) || !Number.isFinite(y)) {
    throw new Error(`Projection error: could not compute ${label} ([${coordinate.join(', ')}])`);
  }

  return [x, y];
}

/** WGS84 lon/lat (degrees) → LCC easting/northing (metres). */
export function toLCC(lonLat: [number, number]): [number, number] {
  const result = transform(lonLat, WGS84_CODE, lccProjection());
  return toPair(result, `LCC coordinates for [${lonLat.join(', ')}]`);
}

/** LCC easting/northing (metres) → WGS84 lon/lat (degrees). */
export function fromLCC(xy: [number, number]): [number, number] {
  const result = transform(xy, lccProjection(), WGS84_CODE);
  return toPair(result, `WGS84 coordinates for [${xy.join(', ')}]`);
}

/**
 * Bounding box of a WGS84 ROI expressed in LCC metres.
 *
 * Computed by transforming the four corners of the ROI and taking the
 * axis-aligned min/max. For a conic projection the true bounding box of the
 * curved region can be marginally larger than the corners' box; the backend
 * is the authority for exact raster `imageExtent` values (see `SicFrameMeta`).
 */
export function lccExtent(roi: Roi): BoxExtent {
  const corners: Array<[number, number]> = [
    toLCC([roi.lon_min, roi.lat_min]),
    toLCC([roi.lon_max, roi.lat_min]),
    toLCC([roi.lon_min, roi.lat_max]),
    toLCC([roi.lon_max, roi.lat_max]),
  ];

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  for (const [x, y] of corners) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }

  return [minX, minY, maxX, maxY];
}

/**
 * Project a rectangle between two registered CRSs, returning its bounding box.
 *
 * The boundary is sampled rather than corner-transformed. Both steps that need
 * this — LCC → WGS84 → polar — bend a straight edge into a curve, so the four
 * corners alone can under-report the box and clip the raster at the edges.
 *
 * @param extent `[minX, minY, maxX, maxY]` in `from` coordinates.
 * @param samplesPerEdge points sampled along each of the four edges.
 */
export function reprojectExtent(
  extent: BoxExtent,
  from: string,
  to: string,
  samplesPerEdge = 48,
): BoxExtent {
  if (from === to) return [...extent] as BoxExtent;

  const [minX, minY, maxX, maxY] = extent;

  let outMinX = Number.POSITIVE_INFINITY;
  let outMinY = Number.POSITIVE_INFINITY;
  let outMaxX = Number.NEGATIVE_INFINITY;
  let outMaxY = Number.NEGATIVE_INFINITY;

  const consume = (x: number, y: number): void => {
    const [tx, ty] = toPair(transform([x, y], from, to), `projection of [${x}, ${y}]`);
    if (tx < outMinX) outMinX = tx;
    if (ty < outMinY) outMinY = ty;
    if (tx > outMaxX) outMaxX = tx;
    if (ty > outMaxY) outMaxY = ty;
  };

  for (let i = 0; i <= samplesPerEdge; i += 1) {
    const t = i / samplesPerEdge;
    const alongX = minX + (maxX - minX) * t;
    const alongY = minY + (maxY - minY) * t;

    consume(alongX, minY); // bottom edge
    consume(maxX, alongY); // right edge
    consume(alongX, maxY); // top edge
    consume(minX, alongY); // left edge
  }

  return [outMinX, outMinY, outMaxX, outMaxY];
}

/**
 * Register the projection and expose a self-check for the browser console.
 * Returns `[lon, lat, x, y]` for the projection origin so a round trip can be
 * eyeballed after a redeploy.
 */
export function lccTest(): [number, number, number, number] {
  const lon = 35;
  const lat = -55;
  const [x, y] = toLCC([lon, lat]);
  const [lonBack, latBack] = fromLCC([x, y]);
  return [lonBack, latBack, x, y];
}
