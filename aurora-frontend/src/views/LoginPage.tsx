/**
 * Sign-in.
 *
 * The only page that exists outside the console chrome: an operator who is
 * not authenticated has no business seeing a map, a health dot, or a vessel
 * name, so nothing else mounts until they are through.
 *
 * Validation is local and instant (zod); the server's answer is shown
 * separately underneath, because "your password is wrong" and "the backend is
 * not running" need different reactions and must never be conflated.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { takeIntendedPath } from '@/services/session';
import { useUserStore } from '@/stores/userStore';

const loginSchema = z.object({
  email: z.email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

type LoginForm = z.infer<typeof loginSchema>;

export function LoginPage(): JSX.Element {
  const navigate = useNavigate();

  const user = useUserStore((state) => state.user);
  const status = useUserStore((state) => state.status);
  const serverError = useUserStore((state) => state.error);
  const signIn = useUserStore((state) => state.signIn);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  // Already signed in — continue to wherever the operator was heading.
  if (user !== null) {
    return <Navigate to={takeIntendedPath()} replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    const ok = await signIn(values.email.trim(), values.password);
    if (ok) navigate(takeIntendedPath(), { replace: true });
  });

  const busy = isSubmitting || status === 'pending';

  return (
    <div className="flex min-h-full items-center justify-center bg-ocean-950/80 px-4 py-10">
      <form
        onSubmit={(event) => {
          void onSubmit(event);
        }}
        className="w-full max-w-sm rounded border border-ocean-700 bg-ocean-900 p-6"
        noValidate
      >
        <div className="mb-6 text-center">
          <div className="text-lg font-semibold tracking-[0.3em] text-ocean-400">AURORA</div>
          <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-ocean-300">
            Vessel decision support
          </p>
        </div>

        <label className="mb-3 block" title="The address your operator account was created with">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-ocean-300">
            Email
          </span>
          <input
            type="email"
            autoComplete="username"
            autoFocus
            placeholder="operator@aurora.demo"
            className="w-full rounded-sm border border-ocean-800 bg-ocean-950 px-2.5 py-2 text-sm text-ocean-100 outline-none transition-colors focus:border-ocean-400"
            aria-invalid={errors.email ? true : undefined}
            {...register('email')}
          />
          {errors.email ? (
            <span className="mt-1 block text-[11px] text-aurora-crit">{errors.email.message}</span>
          ) : null}
        </label>

        <label className="mb-4 block" title="Your account password. It is never shown back to you.">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-ocean-300">
            Password
          </span>
          <input
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            className="w-full rounded-sm border border-ocean-800 bg-ocean-950 px-2.5 py-2 text-sm text-ocean-100 outline-none transition-colors focus:border-ocean-400"
            aria-invalid={errors.password ? true : undefined}
            {...register('password')}
          />
          {errors.password ? (
            <span className="mt-1 block text-[11px] text-aurora-crit">
              {errors.password.message}
            </span>
          ) : null}
        </label>

        {serverError ? (
          <p
            role="alert"
            className="mb-3 rounded-sm border border-aurora-crit/50 bg-aurora-crit/10 px-2.5 py-2 text-[11px] leading-snug text-aurora-crit"
          >
            {serverError}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-sm bg-ocean-600 hover:bg-ocean-500 px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="mt-4 text-center text-[10px] leading-relaxed text-ocean-300">
          Don&apos;t have an account?{' '}
          <Link to="/register" className="text-ocean-400 underline-offset-2 hover:underline">
            Create one
          </Link>
        </p>

        <p className="mt-3 text-center text-[10px] leading-relaxed text-ocean-300">
          Sessions persist across reloads. Signing out only happens when you choose it or the
          token is rejected.
        </p>
      </form>
    </div>
  );
}
