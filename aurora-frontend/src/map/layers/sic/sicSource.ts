/**
 * SIC frame selection and raster source construction.
 *
 * `frame_extent` arrives from the backend already expressed in AURORA's LCC
 * metres and, under the default projection, is handed to OpenLayers verbatim —
 * the frontend does not recompute a raster's footprint.
 *
 * The one case where it cannot be used verbatim is the polar preset, where
 * LCC metres mean nothing to the view. There the footprint is round-tripped
 * LCC → WGS84 → the view projection with {@link reprojectExtent}, which
 * samples the boundary so the box still contains the whole image.
 *
 * Nearest-neighbour interpolation is forced: SIC is a categorical field and
 * bilinear smoothing would invent concentrations between class boundaries.
 */
import ImageStatic from 'ol/source/ImageStatic';

import { API_BASE } from '@/config/env';
import { LCC_CODE, WGS84_CODE, reprojectExtent, type BoxExtent } from '@/config/projection';
import { getMap } from '@/map/mapSetup';
import { useSicStore, type SicStore } from '@/stores/sicStore';
import type { SicFrameMeta } from '@/types/sic';

/** Layer properties that let `update` detect a frame or projection change. */
export const SIC_FRAME_PROP = 'aurora-frame';
export const SIC_PROJ_PROP = 'aurora-proj';

/**
 * A frame URL from the manifest, made absolute.
 *
 * The manifest publishes API-relative paths (`/api/sic/frame/…`), which is
 * right for a deployment where the console and the API share an origin but
 * wrong in development, where the page lives on Vite's origin and `/api`
 * there falls through to the SPA shell — the browser then hands OpenLayers
 * HTML to decode and the raster dies with `EncodingError`. Every frame URL
 * therefore goes through `API_BASE`, exactly like the REST client.
 */
export function frameHref(url: string): string {
  return /^[a-z][a-z0-9+.-]*:/i.test(url) ? url : `${API_BASE}${url}`;
}

/**
 * The frame matching the operator's horizon, or `null`.
 *
 * Among frames for that horizon the newest `date` wins — the operator asked
 * "day N", not "day N as of some particular issue", and the manifest is the
 * authority on which issues exist.
 *
 * Takes the two fields it reads rather than the whole store so a caller that
 * has only the manifest and the horizon (the time slider) can reuse it without
 * fabricating the rest of the slice.
 */
export function selectedFrame(
  state: Pick<SicStore, 'data' | 'selectedHorizon'>,
): SicFrameMeta | null {
  const manifest = state.data;
  if (!manifest || manifest.frames.length === 0) return null;

  const matching = manifest.frames.filter((frame) => frame.horizon === state.selectedHorizon);
  if (matching.length === 0) return null;

  return matching.reduce((newest, frame) => (frame.date > newest.date ? frame : newest));
}

/** The projection the map is currently drawing in. */
export function viewProjectionCode(): string {
  return getMap()?.getView().getProjection().getCode() ?? LCC_CODE;
}

/** `frame_extent` expressed in the given projection. */
export function imageExtentFor(frame: SicFrameMeta, projectionCode: string): BoxExtent {
  const extent: BoxExtent = [...frame.frame_extent] as BoxExtent;

  // The manifest's units are LCC metres, so under the LCC view the value is
  // already correct and must not be recomputed.
  if (projectionCode === LCC_CODE) return extent;

  return reprojectExtent(reprojectExtent(extent, LCC_CODE, WGS84_CODE), WGS84_CODE, projectionCode);
}

function buildSource(url: string, frame: SicFrameMeta, projectionCode: string): ImageStatic {
  return new ImageStatic({
    url: frameHref(url),
    projection: projectionCode,
    imageExtent: imageExtentFor(frame, projectionCode),
    interpolate: false,
  });
}

/** The primary SIC raster for the current frame. */
export function createSicSource(frame: SicFrameMeta, projectionCode: string): ImageStatic {
  return buildSource(frame.frame_url, frame, projectionCode);
}

/**
 * The matching 90 % interval raster, or `null`.
 *
 * `interval_url` is nullable in the manifest: a run without an uncertainty
 * product leaves the uncertainty layer absent rather than blank.
 */
export function createUncertaintySource(
  frame: SicFrameMeta,
  projectionCode: string,
): ImageStatic | null {
  if (!frame.interval_url) return null;
  return buildSource(frame.interval_url, frame, projectionCode);
}

export { useSicStore };
