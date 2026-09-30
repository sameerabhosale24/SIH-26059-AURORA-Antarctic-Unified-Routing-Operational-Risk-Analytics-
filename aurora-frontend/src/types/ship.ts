/**
 * Fleet vessel blueprint — the persisted ship record.
 *
 * Deliberately separate from `types/vessel.ts`: that file describes the
 * *live* own-ship telemetry stream (position, SOG, fuel remaining), while this
 * describes the static ship the operator entered once and that routing then
 * treats as a set of hard constraints. Mixing them would make a telemetry
 * field look like something a form could edit.
 *
 * Field names mirror the database columns exactly so the API layer is a
 * pass-through and a rename has one place to land.
 */

/** IACS polar class as published: `PC1`…`PC7`, or `N/A`. */
export type PolarClass = 'PC1' | 'PC2' | 'PC3' | 'PC4' | 'PC5' | 'PC6' | 'PC7' | 'N/A';

/** IMO Polar Code category. */
export type PolarCategory = 'A' | 'B' | 'C';

export type VesselType = 'research' | 'icebreaker' | 'supply' | 'patrol';

export type BowShape = 'icebreaking' | 'ice-strengthened' | 'conventional';

/**
 * One vessel, as returned by the API.
 *
 * Required fields are the ones the form mandates; everything else is
 * nullable rather than optional, because the backend answers `null` for an
 * empty column and `undefined` would silently render as "missing key" in a
 * read-only view.
 */
export interface Vessel {
  id: number;
  user_id: number | null;

  /* --- identity --- */
  name: string;
  imo: string;
  mmsi: string | null;
  call_sign: string | null;
  flag: string;
  vessel_type: string;
  operator: string | null;

  /* --- ice regime --- */
  max_ice_thickness_m: number;
  max_sic: number;
  iacs_polar_class: string;
  polar_code_category: string;

  /* --- under-keel clearance --- */
  draft_loaded_m: number;
  draft_ballast_m: number | null;

  /* --- weather tolerance --- */
  max_wind_speed_kt: number | null;
  max_wave_height_m: number | null;

  /* --- speed --- */
  economical_speed_kt: number;
  max_speed_kt: number | null;
  speed_in_ice_kt: number;

  /* --- fuel & range --- */
  fuel_capacity_t: number;
  fuel_burn_economical_tpd: number;
  endurance_days: number | null;

  /* --- station reachability --- */
  crane_outreach_m: number | null;
  has_helideck: boolean;
  has_hangar: boolean;
  has_rov: boolean;

  /* --- ice maneuverability --- */
  shaft_power_kw: number | null;
  bow_shape: string;

  created_at: string | null;
  updated_at: string | null;
}

/** What the form submits: the record minus server-assigned fields. */
export type VesselBlueprint = Omit<Vessel, 'id' | 'user_id' | 'created_at' | 'updated_at'>;

/** Partial patch for `PATCH /api/vessels/:id`. */
export type VesselPatch = Partial<VesselBlueprint>;

/** ISO 3166-1 alpha-2 list for the flag dropdown. */
export const FLAGS: ReadonlyArray<{ code: string; name: string }> = [
  { code: 'AQ', name: 'Antarctica' },
  { code: 'AU', name: 'Australia' },
  { code: 'BE', name: 'Belgium' },
  { code: 'CA', name: 'Canada' },
  { code: 'CL', name: 'Chile' },
  { code: 'CN', name: 'China' },
  { code: 'DE', name: 'Germany' },
  { code: 'DK', name: 'Denmark' },
  { code: 'ES', name: 'Spain' },
  { code: 'FI', name: 'Finland' },
  { code: 'FR', name: 'France' },
  { code: 'GB', name: 'United Kingdom' },
  { code: 'IN', name: 'India' },
  { code: 'IT', name: 'Italy' },
  { code: 'JP', name: 'Japan' },
  { code: 'KR', name: 'South Korea' },
  { code: 'NL', name: 'Netherlands' },
  { code: 'NO', name: 'Norway' },
  { code: 'NZ', name: 'New Zealand' },
  { code: 'PL', name: 'Poland' },
  { code: 'RU', name: 'Russia' },
  { code: 'SE', name: 'Sweden' },
  { code: 'US', name: 'United States' },
  { code: 'ZA', name: 'South Africa' },
];

export const VESSEL_TYPES: ReadonlyArray<VesselType> = [
  'research',
  'icebreaker',
  'supply',
  'patrol',
];

export const POLAR_CLASSES: ReadonlyArray<PolarClass> = [
  'PC1',
  'PC2',
  'PC3',
  'PC4',
  'PC5',
  'PC6',
  'PC7',
  'N/A',
];

export const POLAR_CATEGORIES: ReadonlyArray<PolarCategory> = ['A', 'B', 'C'];

export const BOW_SHAPES: ReadonlyArray<BowShape> = [
  'icebreaking',
  'ice-strengthened',
  'conventional',
];
