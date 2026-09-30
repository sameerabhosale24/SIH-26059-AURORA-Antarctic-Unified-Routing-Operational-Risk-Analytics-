/**
 * Electronic Navigational Chart (S-57 ENC) types.
 *
 * A "cell" is one S-57 dataset — conventionally one `.000` file. The backend
 * serves the manifest and the raw files; the frontend parses and portrays them.
 * No chart geometry is bundled with the frontend.
 */

/** One S-57 chart cell available to the client. */
export interface EncCell {
  id: string;
  /** Human-readable cell name, e.g. ` Approaches to Bharati`. */
  name: string;
  /** Absolute or API-relative URL of the raw `.000` file. */
  url: string;
  /** `[lonMin, latMin, lonMax, latMax]` in WGS84 degrees. */
  bounds: [number, number, number, number];
  updated_at: string;
}

/** Response of `GET /api/enc/manifest`. */
export interface EncManifest {
  /** Empty when no ENC is configured — the layer then renders nothing. */
  cells: EncCell[];
  version: number;
}

/** A single S-57 feature after parsing, ready for portrayal. */
export interface EncFeatureRecord {
  /** Chart cell this feature came from. */
  cellId: string;
  /** S-57 record id (RCID) — the stable identifier within a cell. */
  rcid: number;
  /** S-57 object class code (OBJL), e.g. 42 = DEPARE. */
  objl: number;
  /** S-57 attribute code (ATTL) → value, as parsed from the file. */
  attributes: Map<number, string>;
  /** Raw GeoJSON geometry from the parser. */
  geometry: EncGeometry | null;
}

export type EncGeometry =
  | { type: 'Point'; coordinates: [number, number] }
  | { type: 'MultiPoint'; coordinates: [number, number][] }
  | { type: 'LineString'; coordinates: [number, number][] }
  | { type: 'Polygon'; coordinates: [number, number][][] }
  | { type: 'GeometryCollection'; geometries: EncGeometry[] };
