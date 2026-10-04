/**
 * Follow-ship toggle.
 *
 * Off by default: an operator who is reading a panel does not want the
 * viewport sliding underneath them because the GPS ticked. Turning it on
 * eases the view onto the vessel and then tracks it, with the debounce
 * living in `mapSetup.setFollowShip` rather than here.
 */
import { useUiStore } from '@/stores/uiStore';

export function FollowShipToggle(): JSX.Element {
  const followShip = useUiStore((state) => state.followShip);
  const setFollowShip = useUiStore((state) => state.setFollowShip);

  return (
    <button
      type="button"
      onClick={() => setFollowShip(!followShip)}
      aria-pressed={followShip}
      title="Keep the view centred on own ship"
      className={`rounded-sm border px-2 py-1 text-[10px] uppercase tracking-[0.12em] transition-colors ${
        followShip
          ? 'border-ocean-400/50 bg-ocean-400/15 text-ocean-400'
          : 'border-ocean-800 text-ocean-300 hover:text-ocean-100'
      }`}
    >
      Follow ship
    </button>
  );
}
