/**
 * Public landing page.
 *
 * The one route an unauthenticated visitor is allowed to reach. It exists to
 * answer "what is this?" and hand over to the sign-in form — it deliberately
 * contains no numbers pulled from a store, because every one of them would be
 * either a guess or a piece of console state a stranger must not see.
 *
 * Console chrome (status bar, view nav, connection overlay) is suppressed on
 * this route: advertising a health dot and a vessel selector to someone who
 * cannot use either is noise.
 */
import { Link } from 'react-router-dom';

/**
 * Verified facts about the product, not marketing copy: each one is a
 * constant in `config/constants.ts` or `app/utils/constants.py`.
 */
const STATS: ReadonlyArray<{ value: string; label: string }> = [
  { value: '3', label: 'Forecast horizons published daily — D+1 through D+3' },
  { value: '0.25°', label: 'Sea-ice grid resolution, 101 × 361 cells over 75°S–50°S' },
  { value: 'S-52', label: 'IHO electronic navigational chart as the base chart' },
  { value: 'Real-time', label: 'AIS and own-ship positions on the operational view' },
];

const STEPS: ReadonlyArray<{ step: string; title: string; body: string }> = [
  {
    step: '01',
    title: 'Open a session',
    body:
      'Sign in with a demo operator account. The session persists across reloads ' +
      'and is only dropped when you choose to sign out or the token is rejected.',
  },
  {
    step: '02',
    title: 'Choose a vessel',
    body:
      'Pick a ship from the fleet or register a new one. Every console view is ' +
      'scoped to a vessel, so the URL always says which one you are reading.',
  },
  {
    step: '03',
    title: 'Read the chart',
    body:
      'Sea-ice forecast, AIS targets, icebergs and route candidates on a single ' +
      'chart, with the three horizons selectable on the time slider.',
  },
];

export function LandingPage(): JSX.Element {
  return (
    <div className="min-h-full overflow-y-auto bg-ocean-950 text-ocean-100">
      <header className="border-b border-ocean-800">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <span className="text-sm font-semibold tracking-[0.34em] text-ocean-400">AURORA</span>
          <nav className="flex items-center gap-5 text-[11px] uppercase tracking-[0.16em]">
            <Link to="/login" className="text-ocean-300 transition-colors hover:text-ocean-100">
              Sign in
            </Link>
            <Link
              to="/register"
              className="rounded-sm border border-ocean-600 px-3 py-1.5 text-ocean-300 transition-colors hover:bg-ocean-800 hover:text-ocean-100"
            >
              Create account
            </Link>
          </nav>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="border-b border-ocean-800 bg-ocean-900/40">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <p className="text-[11px] uppercase tracking-[0.24em] text-ocean-300">
              Antarctic Unified Routing, Operational &amp; Risk Analytics
            </p>
            <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-ocean-100 sm:text-5xl">
              Ice-aware routing decisions, on one chart.
            </h1>
            <p className="mt-6 max-w-2xl text-sm leading-relaxed text-ocean-300">
              AURORA puts a three-day sea-ice forecast, live AIS traffic, iceberg drift and
              route candidates on a single S-52 electronic chart, so an operator can compare
              a plan against the ice instead of against a table.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                to="/login"
                className="rounded-sm bg-ocean-500 px-5 py-2.5 text-xs font-semibold uppercase tracking-[0.16em] text-ocean-950 transition-colors hover:bg-ocean-400"
              >
                Explore Demo Console →
              </Link>
              <Link
                to="/register"
                className="rounded-sm border border-ocean-600 px-5 py-2.5 text-xs font-semibold uppercase tracking-[0.16em] text-ocean-300 transition-colors hover:bg-ocean-800 hover:text-ocean-100"
              >
                Register an operator
              </Link>
            </div>
          </div>
        </section>

        {/* Stat cards */}
        <section className="border-b border-ocean-800">
          <div className="mx-auto grid max-w-6xl grid-cols-1 gap-px bg-ocean-800 sm:grid-cols-2 lg:grid-cols-4">
            {STATS.map((stat) => (
              <div key={stat.value} className="bg-ocean-950 px-6 py-8">
                <div className="text-3xl font-semibold tracking-tight text-ocean-100">
                  {stat.value}
                </div>
                <p className="mt-3 text-[11px] leading-relaxed uppercase tracking-[0.12em] text-ocean-300">
                  {stat.label}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* How it works */}
        <section className="border-b border-ocean-800">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="text-[11px] uppercase tracking-[0.24em] text-ocean-300">
              How it works
            </h2>
            <div className="mt-8 grid grid-cols-1 gap-6 md:grid-cols-3">
              {STEPS.map((step) => (
                <article key={step.step} className="rounded border border-ocean-800 bg-ocean-900 p-6">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-ocean-400">
                    {step.step}
                  </div>
                  <h3 className="mt-3 text-base font-semibold text-ocean-100">{step.title}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-ocean-300">{step.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-8 text-[11px] leading-relaxed text-ocean-300 sm:flex-row sm:items-center sm:justify-between">
        <span>AURORA — Antarctic Unified Routing, Operational &amp; Risk Analytics.</span>
        <span>Demo console. Sign-in data stays in this browser.</span>
      </footer>
    </div>
  );
}
