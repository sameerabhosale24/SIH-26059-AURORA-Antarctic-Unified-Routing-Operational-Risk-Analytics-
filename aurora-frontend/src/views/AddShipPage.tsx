/**
 * Create or edit a vessel blueprint.
 *
 * `/ships/new` and `/ships/:id/edit` are the same component: the only
 * difference is where the defaults come from and what the button says. One
 * form means validation, tooltips and section order cannot diverge between
 * "add" and "edit" — an operator who learns the sheet in one mode finds the
 * identical sheet in the other.
 *
 * Validation is zod-side, so a rejected submit never reaches the backend and
 * the server is never asked to re-check what the browser already knows.
 */
import { useForm, type DefaultValues } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { z } from 'zod';

import { useVesselRecord } from '@/hooks/useVesselRecord';
import { useShipsStore } from '@/stores/shipsStore';
import { notify } from '@/stores/toastStore';
import type { Vessel, VesselBlueprint } from '@/types/ship';
import { SHIP_FIELDS, SHIP_SECTIONS, type ShipField } from './shipSections';

/* ------------------------------------------------------------------ *
 * Validation
 * ------------------------------------------------------------------ */

/**
 * Empty means "not provided", not "zero" — an operator who leaves endurance
 * blank has told us nothing, which is different from saying the ship has none.
 * Anything present must match the pattern; the message is ours rather than
 * zod's union wording, because the operator needs to know *which* number is
 * malformed.
 */
const blankOr = (pattern: RegExp, message: string) =>
  z.string().refine((value) => value === '' || pattern.test(value), { message });

/** Numbers arrive from `type="number"` inputs, where blank is the common case. */
const requiredNumber = z.number({ error: 'Enter a number' }).min(0, 'Must be 0 or more');
const optionalNumber = z.number().min(0, 'Must be 0 or more').optional();

const shipSchema = z.object({
  /* 1 · identity */
  name: z.string().min(1, 'Vessel name is required'),
  imo: blankOr(/^\d{7}$/, 'IMO must be exactly 7 digits'),
  mmsi: blankOr(/^\d{9}$/, 'MMSI must be exactly 9 digits'),
  call_sign: blankOr(/^[A-Za-z0-9]{3,7}$/, 'Call sign is 3–7 letters or digits'),
  flag: z.string().min(1, 'Choose a flag state'),
  vessel_type: z.string().min(1, 'Choose a vessel type'),
  operator: z.string(),

  /* 2 · ice capability */
  max_ice_thickness_m: requiredNumber,
  max_sic: z.number({ error: 'Enter a number' }).min(0, 'Between 0 and 1').max(1, 'Between 0 and 1'),
  iacs_polar_class: z.string().min(1, 'Choose an ice class'),
  polar_code_category: z.string().min(1, 'Choose a Polar Code category'),

  /* 3 · under-keel clearance */
  draft_loaded_m: requiredNumber,
  draft_ballast_m: optionalNumber,

  /* 4 · weather tolerance */
  max_wind_speed_kt: optionalNumber,
  max_wave_height_m: optionalNumber,

  /* 5 · speed */
  economical_speed_kt: requiredNumber,
  max_speed_kt: optionalNumber,
  speed_in_ice_kt: requiredNumber,

  /* 6 · fuel and range */
  fuel_capacity_t: requiredNumber,
  fuel_burn_economical_tpd: requiredNumber,
  endurance_days: optionalNumber,

  /* 7 · station reachability */
  crane_outreach_m: optionalNumber,
  has_helideck: z.boolean(),
  has_hangar: z.boolean(),
  has_rov: z.boolean(),

  /* 8 · ice manoeuvrability */
  shaft_power_kw: optionalNumber,
  bow_shape: z.string().min(1, 'Choose a bow shape'),
});

export type ShipForm = z.infer<typeof shipSchema>;

/* ------------------------------------------------------------------ *
 * Value plumbing
 * ------------------------------------------------------------------ */

/**
 * `type="number"` hands back a string; blank and garbage both become
 * `undefined` so optional fields validate as "not provided" and required
 * fields fall through to their own "Enter a number" message.
 */
function toNumberInput(value: unknown): number | undefined {
  if (value === '' || value === null || value === undefined) return undefined;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? undefined : parsed;
}

function defaultsFor(vessel: Vessel | null): DefaultValues<ShipForm> {
  const values: Record<string, string | number | boolean> = {};

  for (const field of SHIP_FIELDS) {
    const raw = vessel ? vessel[field.key] : undefined;

    // Checkboxes always start from a definite false — "not recorded" and
    // "no" render differently in the UI but the form needs one or the other.
    if (field.kind === 'checkbox') {
      values[field.key] = raw === true;
      continue;
    }

    // Text and selects always start as a string, even when the column is
    // null: zod validates `string`, and an omitted key would arrive as
    // `undefined` and fail with an error the operator cannot act on.
    if (field.kind !== 'number') {
      values[field.key] = raw === null || raw === undefined ? '' : String(raw);
      continue;
    }

    // Numbers are the only fields allowed to be absent. Omitting the key
    // (rather than setting `undefined`) keeps the object assignable under
    // `exactOptionalPropertyTypes`, and `optionalNumber` accepts the gap.
    if (raw !== null && raw !== undefined && typeof raw === 'number') {
      values[field.key] = raw;
    }
  }

  return values as unknown as DefaultValues<ShipForm>;
}

/** Form values → the exact payload the backend stores. Nothing invented. */
function toBlueprint(form: ShipForm): VesselBlueprint {
  const blank = (value: string): string | null => (value.trim() === '' ? null : value.trim());

  return {
    name: form.name.trim(),
    imo: form.imo.trim(),
    mmsi: blank(form.mmsi),
    call_sign: blank(form.call_sign),
    flag: form.flag,
    vessel_type: form.vessel_type,
    operator: blank(form.operator),

    max_ice_thickness_m: form.max_ice_thickness_m,
    max_sic: form.max_sic,
    iacs_polar_class: form.iacs_polar_class,
    polar_code_category: form.polar_code_category,

    draft_loaded_m: form.draft_loaded_m,
    draft_ballast_m: form.draft_ballast_m ?? null,

    max_wind_speed_kt: form.max_wind_speed_kt ?? null,
    max_wave_height_m: form.max_wave_height_m ?? null,

    economical_speed_kt: form.economical_speed_kt,
    max_speed_kt: form.max_speed_kt ?? null,
    speed_in_ice_kt: form.speed_in_ice_kt,

    fuel_capacity_t: form.fuel_capacity_t,
    fuel_burn_economical_tpd: form.fuel_burn_economical_tpd,
    endurance_days: form.endurance_days ?? null,

    crane_outreach_m: form.crane_outreach_m ?? null,
    has_helideck: form.has_helideck,
    has_hangar: form.has_hangar,
    has_rov: form.has_rov,

    shaft_power_kw: form.shaft_power_kw ?? null,
    bow_shape: form.bow_shape,
  };
}

/* ------------------------------------------------------------------ *
 * Controls
 * ------------------------------------------------------------------ */

interface FieldProps {
  field: ShipField;
  register: ReturnType<typeof useForm<ShipForm>>['register'];
  error: string | undefined;
}

function Field({ field, register, error }: FieldProps): JSX.Element {
  const id = `ship-${field.key}`;
  const label = `${field.label}${field.required ? ' *' : ''}`;

  const baseClass =
    'w-full rounded-sm border border-ocean-800 bg-ocean-950 px-2.5 py-1.5 text-xs text-ocean-100 outline-none transition-colors focus:border-ocean-400';

  const describedBy = error ? `${id}-error` : undefined;

  if (field.kind === 'checkbox') {
    return (
      <label
        htmlFor={id}
        title={field.tooltip}
        className="flex h-full cursor-pointer items-center gap-2 rounded-sm border border-ocean-800 bg-ocean-950 px-2.5 py-2 transition-colors hover:border-ocean-400/50"
      >
        <input
          id={id}
          type="checkbox"
          className="h-3.5 w-3.5 accent-ocean-400"
          aria-describedby={describedBy}
          {...register(field.key)}
        />
        <span className="text-xs text-ocean-100">{field.label}</span>
      </label>
    );
  }

  return (
    <div className="min-w-0">
      <label
        htmlFor={id}
        title={field.tooltip}
        className="mb-1 block cursor-help text-[10px] uppercase tracking-[0.12em] text-ocean-300"
      >
        {label}
      </label>

      {field.kind === 'select' ? (
        <select
          id={id}
          className={baseClass}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...register(field.key)}
        >
          <option value="">Choose…</option>
          {field.options?.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          type={field.kind === 'number' ? 'number' : 'text'}
          step={field.key === 'max_sic' ? '0.01' : 'any'}
          min={field.kind === 'number' ? 0 : undefined}
          inputMode={field.kind === 'number' ? 'decimal' : undefined}
          placeholder={field.placeholder}
          className={baseClass}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...register(
            field.key,
            field.kind === 'number' ? { setValueAs: toNumberInput } : undefined,
          )}
        />
      )}

      {error ? (
        <span id={describedBy} className="mt-1 block text-[11px] text-aurora-crit">
          {error}
        </span>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Page
 * ------------------------------------------------------------------ */

function ShipFormFields({
  vessel,
  onSaved,
}: {
  vessel: Vessel | null;
  onSaved: (created: Vessel) => void;
}): JSX.Element {
  const navigate = useNavigate();
  const editId = vessel?.id ?? null;

  const createShip = useShipsStore((state) => state.createShip);
  const patchShip = useShipsStore((state) => state.patchShip);
  const submitError = useShipsStore((state) => state.error);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ShipForm>({
    resolver: zodResolver(shipSchema),
    defaultValues: defaultsFor(vessel),
  });

  const fieldError = (key: string): string | undefined =>
    (errors as Record<string, { message?: string } | undefined>)[key]?.message;

  const onSubmit = handleSubmit(async (values) => {
    const blueprint = toBlueprint(values);

    if (editId === null) {
      const created = await createShip(blueprint);
      if (created) {
        notify(`${created.name} added to the fleet`, 'success');
        reset(defaultsFor(created));
        onSaved(created);
      }
      return;
    }

    const updated = await patchShip(editId, blueprint);
    if (updated) {
      notify(`${updated.name} updated`, 'success');
      reset(defaultsFor(updated));
      onSaved(updated);
    }
  });

  const busy = isSubmitting;

  return (
    <form
      onSubmit={(event) => {
        void onSubmit(event);
      }}
      noValidate
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="mx-auto grid max-w-5xl gap-3 lg:grid-cols-2">
          {SHIP_SECTIONS.map((section) => (
            <section
              key={section.id}
              className="rounded border border-ocean-800 bg-ocean-900"
            >
              <header className="border-b border-ocean-800 px-3 py-2">
                <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ocean-100">
                  {section.title}
                </h2>
                <p className="mt-0.5 text-[11px] leading-snug text-ocean-300">{section.hint}</p>
              </header>

              <div className="grid gap-3 p-3 sm:grid-cols-2">
                {section.fields.map((field) => (
                  <Field key={field.key} field={field} register={register} error={fieldError(field.key)} />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>

      <footer className="sticky bottom-0 z-10 flex shrink-0 items-center gap-3 border-t border-ocean-800 bg-ocean-900 px-3 py-2.5">
        <p className="text-[11px] text-ocean-300">
          Fields marked <span className="text-ocean-100">*</span> are required. Every other
          value may stay blank.
        </p>

        {submitError ? (
          <p role="alert" className="text-[11px] text-aurora-crit">
            {submitError}
          </p>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(editId === null ? '/ships' : `/ships/${editId}`)}
            disabled={busy}
            className="rounded-sm border border-ocean-600 px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-ocean-300 transition-colors hover:bg-ocean-800 hover:text-ocean-100 disabled:opacity-50"
          >
            Cancel
          </button>

          <button
            type="submit"
            disabled={busy}
            className="rounded-sm bg-ocean-600 hover:bg-ocean-500 px-3.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? 'Saving…' : editId === null ? 'Create vessel' : 'Save changes'}
          </button>
        </div>
      </footer>
    </form>
  );
}

function PageHeader({ title, subtitle, backTo }: { title: string; subtitle: string; backTo: string }): JSX.Element {
  return (
    <header className="flex items-center gap-3 border-b border-ocean-800 bg-ocean-900 px-3 py-2">
      <Link
        to={backTo}
        className="rounded-sm border border-ocean-600 px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-ocean-300 transition-colors hover:bg-ocean-800 hover:text-ocean-100"
      >
        ← Fleet
      </Link>

      <div className="min-w-0">
        <h1 className="truncate text-sm font-semibold tracking-[0.12em] text-ocean-100">{title}</h1>
        <p className="truncate text-[11px] text-ocean-300">{subtitle}</p>
      </div>
    </header>
  );
}

function Blocked({ title, message, backTo }: { title: string; message: string; backTo: string }): JSX.Element {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-sm text-ocean-100">{title}</p>
      <p className="max-w-md text-[11px] leading-relaxed text-ocean-300">{message}</p>
      <Link
        to={backTo}
        className="rounded-sm bg-ocean-600 hover:bg-ocean-500 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-white"
      >
        Back to fleet
      </Link>
    </div>
  );
}

export function AddShipPage(): JSX.Element {
  const params = useParams();
  const navigate = useNavigate();

  const editId = params.id ? Number(params.id) : undefined;
  const isEdit = editId !== undefined && !Number.isNaN(editId);

  const { vessel, loading, error, notFound } = useVesselRecord(isEdit ? editId : undefined);

  if (isEdit) {
    if (loading) {
      return (
        <div className="flex h-full flex-col">
          <PageHeader title="Edit vessel" subtitle="Loading…" backTo="/ships" />
          <div className="flex flex-1 items-center justify-center text-xs text-ocean-300">
            Loading vessel…
          </div>
        </div>
      );
    }

    if (notFound) {
      return (
        <Blocked
          title="That vessel does not exist"
          message="It may have been deleted from the fleet by another operator, or the link is out of date."
          backTo="/ships"
        />
      );
    }

    if (error || vessel === null) {
      return (
        <Blocked
          title="Could not load that vessel"
          message={error ?? 'The backend returned no record.'}
          backTo="/ships"
        />
      );
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageHeader
        title={isEdit ? `Edit ${vessel?.name ?? ''}` : 'Add vessel'}
        subtitle={
          isEdit
            ? 'Changes apply to routes computed from now on.'
            : 'Eight sections. Only the constraints routing enforces are required.'
        }
        backTo="/ships"
      />

      <ShipFormFields
        key={vessel?.id ?? 'new'}
        vessel={isEdit ? vessel : null}
        onSaved={(saved) => navigate(`/ships/${saved.id}`)}
      />
    </div>
  );
}
