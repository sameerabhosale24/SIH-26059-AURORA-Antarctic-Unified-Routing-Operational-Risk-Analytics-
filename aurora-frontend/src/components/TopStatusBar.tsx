/**
 * Compatibility alias for the Part 1 top bar.
 *
 * The real implementation lives in `@/panels/StatusBar` alongside the other
 * panels; this re-export keeps the Part 1 import path working so no call site
 * has to know which phase of the build produced it.
 */
export { StatusBar as TopStatusBar } from '@/panels/StatusBar';
