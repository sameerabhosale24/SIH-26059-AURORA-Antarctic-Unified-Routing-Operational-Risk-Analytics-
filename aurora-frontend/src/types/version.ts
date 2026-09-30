/**
 * Monotonic revision counters for each backend data product.
 *
 * Returned by `GET /api/version` and polled every 10 minutes. A field that
 * changes means that product has been republished and dependent stores must
 * refetch. Versions are never synthesised — absent fields stay undefined.
 */
export interface DataVersion {
  sic: number;
  currents: number;
  weather: number;
  icebergs: number;
  enc: number;
}

/** Keys of {@link DataVersion}, in the order used by the UI. */
export const DATA_VERSION_KEYS = ['sic', 'currents', 'weather', 'icebergs', 'enc'] as const;

export type DataVersionKey = (typeof DATA_VERSION_KEYS)[number];

/**
 * Returns the subset of `keys` whose value differs between two version
 * snapshots. Missing/null values on either side count as a change.
 */
export function diffVersions(
  previous: Partial<DataVersion> | null,
  next: Partial<DataVersion> | null,
  keys: readonly DataVersionKey[] = DATA_VERSION_KEYS,
): DataVersionKey[] {
  return keys.filter((key) => (previous?.[key] ?? null) !== (next?.[key] ?? null));
}
