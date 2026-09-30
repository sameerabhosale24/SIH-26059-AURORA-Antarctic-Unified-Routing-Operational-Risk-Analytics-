/**
 * The eight sections of a vessel blueprint.
 *
 * One table drives both the form and the read-only detail page, so the two
 * can never drift: a label, a unit or a tooltip exists once and appears in
 * both places. It also means "what did I just enter?" and "what did I save?"
 * are answered by literally the same words.
 *
 * Order matters — it is the order an operator fills the sheet in, identity
 * first because every later number is meaningless without knowing which ship
 * it belongs to.
 */
import type { Vessel, VesselBlueprint } from '@/types/ship';
import {
  BOW_SHAPES,
  FLAGS,
  POLAR_CATEGORIES,
  POLAR_CLASSES,
  VESSEL_TYPES,
} from '@/types/ship';

export type FieldKind = 'text' | 'number' | 'select' | 'checkbox';

export interface ShipField {
  key: keyof VesselBlueprint;
  label: string;
  /** Hover text — the answer to "why are you asking me this?". */
  tooltip: string;
  kind: FieldKind;
  required?: boolean;
  unit?: string;
  placeholder?: string;
  options?: ReadonlyArray<{ value: string; label: string }>;
}

export interface ShipSection {
  id: string;
  title: string;
  /** One line saying what this section constrains downstream. */
  hint: string;
  fields: ShipField[];
}

const flagOptions = FLAGS.map((flag) => ({ value: flag.code, label: `${flag.code} — ${flag.name}` }));

export const SHIP_SECTIONS: readonly ShipSection[] = [
  {
    id: 'identity',
    title: '1 · Identity',
    hint: 'Who the ship is. The IMO number is the permanent key; everything else can be corrected later.',
    fields: [
      {
        key: 'name',
        label: 'Vessel name',
        tooltip: 'Shown in the status bar, the fleet cards and every route record. Use the name the crew uses.',
        kind: 'text',
        required: true,
        placeholder: 'Polar Star',
      },
      {
        key: 'imo',
        label: 'IMO number',
        tooltip: 'Seven digits, permanently assigned to the hull. Used to tie routes and alarms to the ship across renames.',
        kind: 'text',
        required: true,
        placeholder: '7431285',
      },
      {
        key: 'mmsi',
        label: 'MMSI',
        tooltip: 'Nine digits. Lets incoming AIS targets be recognised as this vessel rather than as traffic.',
        kind: 'text',
        placeholder: '257389000',
      },
      {
        key: 'call_sign',
        label: 'Call sign',
        tooltip: 'Radio identifier printed on the hull, e.g. LAXY. Shown to operators talking to the ship.',
        kind: 'text',
        placeholder: 'LAXY',
      },
      {
        key: 'flag',
        label: 'Flag state',
        tooltip: 'Country of registry. Determines which polar waters the vessel is certified to enter.',
        kind: 'select',
        required: true,
        options: flagOptions,
      },
      {
        key: 'vessel_type',
        label: 'Vessel type',
        tooltip: 'Changes how routing weighs ice risk: an icebreaker may push where a supply ship must divert.',
        kind: 'select',
        required: true,
        options: VESSEL_TYPES.map((type) => ({ value: type, label: type })),
      },
      {
        key: 'operator',
        label: 'Operator',
        tooltip: 'Organisation responsible for the vessel. Recorded with route decisions for the voyage log.',
        kind: 'text',
        placeholder: 'Antarctic Logistics',
      },
    ],
  },

  {
    id: 'ice',
    title: '2 · Ice capability',
    hint: 'The hard limits routing must never plan past. Route acceptance treats these as constraints, not preferences.',
    fields: [
      {
        key: 'max_ice_thickness_m',
        label: 'Maximum ice thickness',
        tooltip: 'Thickest level ice the ship can break at continuous speed. Any route segment predicted above this is rejected.',
        kind: 'number',
        required: true,
        unit: 'm',
        placeholder: '1.0',
      },
      {
        key: 'max_sic',
        label: 'Maximum sea-ice concentration',
        tooltip: 'Fraction of the surface covered by ice that the ship may enter. 0.9 means 90% — beyond that, open water disappears ahead of the bow.',
        kind: 'number',
        required: true,
        unit: 'fraction (0–1)',
        placeholder: '0.9',
      },
      {
        key: 'iacs_polar_class',
        label: 'IACS polar class',
        tooltip: 'Ice class as assigned by IACS. PC1 is the strongest, PC7 the lightest; N/A means no polar notation.',
        kind: 'select',
        required: true,
        options: POLAR_CLASSES.map((pc) => ({ value: pc, label: pc })),
      },
      {
        key: 'polar_code_category',
        label: 'IMO Polar Code category',
        tooltip: 'Category A is the most severe ice conditions. It sets which cargo and crewing rules apply.',
        kind: 'select',
        required: true,
        options: POLAR_CATEGORIES.map((category) => ({ value: category, label: category })),
      },
    ],
  },

  {
    id: 'ukc',
    title: '3 · Under-keel clearance',
    hint: 'Draft in Antarctic shallows. A wrong draft is how a route that looks safe grounds a ship.',
    fields: [
      {
        key: 'draft_loaded_m',
        label: 'Draft, loaded',
        tooltip: 'Depth of keel below the waterline with cargo aboard — the worst case, and the one clearance is checked against.',
        kind: 'number',
        required: true,
        unit: 'm',
        placeholder: '7.4',
      },
      {
        key: 'draft_ballast_m',
        label: 'Draft, ballast',
        tooltip: 'Draft when in ballast (no cargo). Leave empty if the vessel does not sail in ballast.',
        kind: 'number',
        unit: 'm',
        placeholder: '5.1',
      },
    ],
  },

  {
    id: 'weather',
    title: '4 · Weather tolerance',
    hint: 'Wind and swell limits. Beyond these, the ship is not slowed — it is turned back.',
    fields: [
      {
        key: 'max_wind_speed_kt',
        label: 'Maximum wind speed',
        tooltip: 'Sustained wind above which operations stop. Helicopter decks and crane work are the usual binding limits.',
        kind: 'number',
        unit: 'kt',
        placeholder: '45',
      },
      {
        key: 'max_wave_height_m',
        label: 'Maximum significant wave height',
        tooltip: 'Significant swell the vessel will work in. Routing uses it to avoid areas where the forecast exceeds this.',
        kind: 'number',
        unit: 'm',
        placeholder: '4.0',
      },
    ],
  },

  {
    id: 'speed',
    title: '5 · Speed',
    hint: 'How fast the ship actually goes — fuel and arrival estimates are derived from these, never assumed.',
    fields: [
      {
        key: 'economical_speed_kt',
        label: 'Economical speed',
        tooltip: 'Speed at which the vessel cruises on open water. This is the baseline fuel burn the charts report.',
        kind: 'number',
        required: true,
        unit: 'kt',
        placeholder: '12',
      },
      {
        key: 'max_speed_kt',
        label: 'Maximum speed',
        tooltip: 'Best possible speed in open water. Leave empty if unknown; routing then will not plan above the economical speed.',
        kind: 'number',
        unit: 'kt',
        placeholder: '16',
      },
      {
        key: 'speed_in_ice_kt',
        label: 'Speed in ice',
        tooltip: 'Speed maintained in the ice thickness the vessel is rated for. This is what a transit through the pack is timed at.',
        kind: 'number',
        required: true,
        unit: 'kt',
        placeholder: '3',
      },
    ],
  },

  {
    id: 'fuel',
    title: '6 · Fuel and range',
    hint: 'Endurance is a safety limit: a route must never need more fuel than the tanks hold.',
    fields: [
      {
        key: 'fuel_capacity_t',
        label: 'Fuel capacity',
        tooltip: 'Total bunker capacity. Route range is bounded by this minus a reserve the planner does not spend.',
        kind: 'number',
        required: true,
        unit: 't',
        placeholder: '1200',
      },
      {
        key: 'fuel_burn_economical_tpd',
        label: 'Fuel burn, economical',
        tooltip: 'Tonnes per day at economical speed. The fuel chart is this number multiplied by the leg duration.',
        kind: 'number',
        required: true,
        unit: 't/day',
        placeholder: '28',
      },
      {
        key: 'endurance_days',
        label: 'Endurance',
        tooltip: 'Days the vessel can operate without resupply. Leave empty if not stated; range is then limited by fuel alone.',
        kind: 'number',
        unit: 'days',
        placeholder: '45',
      },
    ],
  },

  {
    id: 'station',
    title: '7 · Station reachability',
    hint: 'Whether the ship can actually do the job at the far end — cargo, aircraft and ROV are not optional at a research station.',
    fields: [
      {
        key: 'crane_outreach_m',
        label: 'Crane outreach',
        tooltip: 'Horizontal reach from the quay or deck. Station berths with a wider gap than this cannot be served.',
        kind: 'number',
        unit: 'm',
        placeholder: '18',
      },
      {
        key: 'has_helideck',
        label: 'Helideck',
        tooltip: 'Allows crew change and medical evacuation by air, which changes which stations are considered supported.',
        kind: 'checkbox',
      },
      {
        key: 'has_hangar',
        label: 'Hangar',
        tooltip: 'Protects aircraft from the weather between flights, extending the operating window at sea.',
        kind: 'checkbox',
      },
      {
        key: 'has_rov',
        label: 'ROV',
        tooltip: 'Remotely operated vehicle for survey and recovery work below the ice.',
        kind: 'checkbox',
      },
    ],
  },

  {
    id: 'manoeuvre',
    title: '8 · Ice manoeuvrability',
    hint: 'How the hull behaves when it stops in ice — the difference between backing out and waiting for a breakout.',
    fields: [
      {
        key: 'shaft_power_kw',
        label: 'Shaft power',
        tooltip: 'Delivered shaft power. Together with the bow shape it decides whether the vessel can ram and back out of a pressure ridge.',
        kind: 'number',
        unit: 'kW',
        placeholder: '16000',
      },
      {
        key: 'bow_shape',
        label: 'Bow shape',
        tooltip: 'An icebreaking bow rides up and crushes down; a conventional bow parts the ice and wedges. Routing assumes the behaviour you pick here.',
        kind: 'select',
        required: true,
        options: BOW_SHAPES.map((shape) => ({ value: shape, label: shape })),
      },
    ],
  },
];

/** Flat field list, for validation and for the "30 tooltips" count. */
export const SHIP_FIELDS: readonly ShipField[] = SHIP_SECTIONS.flatMap((section) => section.fields);

/** Human value for the read-only mirror. */
export function formatFieldValue(vessel: Vessel, field: ShipField): string {
  const raw = vessel[field.key];

  if (field.kind === 'checkbox') return raw ? 'Yes' : 'No';
  if (raw === null || raw === undefined || raw === '') return '—';

  if (typeof raw === 'number') {
    // Concentration is the only ratio in the sheet; everything else is a
    // plain quantity an operator reads better as a percentage.
    const value = field.key === 'max_sic' ? `${Math.round(raw * 100)}%` : String(raw);
    return field.unit && !field.unit.startsWith('fraction') ? `${value} ${field.unit}` : value;
  }

  if (field.key === 'flag') {
    const match = FLAGS.find((flag) => flag.code === raw);
    return match ? `${match.code} — ${match.name}` : String(raw);
  }

  return String(raw);
}
