/**
 * SIC uncertainty "style".
 *
 * Same mechanism as `sicStyle` — a canvas filter installed around the draw —
 * but reading `UNCERTAINTY_IMAGE_FILTER`, because the interval product is a
 * different visual weight from the concentration product and dimming them
 * together would make the band look like a confidence region on the ice
 * field rather than a separate product.
 */
import type { DisplayMode } from '@/config/palettes';
import { SIC_FILTER_PROP, attachImageFilter, uncertaintyFilterFor } from '../sic/sicStyle';

export { SIC_FILTER_PROP, attachImageFilter, uncertaintyFilterFor };

/** The filter string for the current display mode. */
export function uncertaintyStyle(mode: DisplayMode): string {
  return uncertaintyFilterFor(mode);
}
