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
          ? 'border-aurora-accent/50 bg-aurora-accent/15 text-aurora-accent'
          : 'border-aurora-border text-aurora-muted hover:text-aurora-text'
      }`}
    >
      Follow ship
    </button>
  );
}
