/**
 * SIC uncertainty "style".
 *
 * Same mechanism as `sicStyle` — a canvas filter installed around the draw —
 * but reading `UNCERTAINTY_IMAGE_FILTER`, because the interval product is a
 * different visual weight from the concentration product and dimming them
 * together would make the band look like a confidence region on the ice
 * field rather than a separate product.
 */
import {
  SIC_FILTER_PROP,
  attachImageFilter,
  uncertaintyFilterFor,
} from '../sic/sicStyle';

export { SIC_FILTER_PROP, attachImageFilter, uncertaintyFilterFor };

/** The canvas filter applied around the uncertainty raster. */
export function uncertaintyStyle(): string {
  return uncertaintyFilterFor();
}
