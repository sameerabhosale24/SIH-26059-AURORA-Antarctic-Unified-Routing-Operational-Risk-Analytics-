/**
 * Account creation.
 *
 * Shares the sign-in page's chrome for the same reason it shares its guard:
 * an operator who has not chosen a password yet is still nobody, so this is
 * the second and last page that exists outside the console.
 *
 * Validation runs locally and instantly (zod, 8 characters minimum, exact
 * match on the confirmation); the server's answer is shown separately, because
 * "these passwords differ" and "that address is already registered" are
 * different facts and must never be conflated into one line.
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { z } from 'zod';

import { takeIntendedPath } from '@/services/session';
import { useUserStore } from '@/stores/userStore';

const registerSchema = z
  .object({
    email: z.email('Enter a valid email address'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
    confirm: z.string().min(1, 'Confirm your password'),
  })
  .refine((values) => values.password === values.confirm, {
    message: 'Passwords do not match',
    path: ['confirm'],
  });

type RegisterForm = z.infer<typeof registerSchema>;

export function RegisterPage(): JSX.Element {
  const navigate = useNavigate();

  const user = useUserStore((state) => state.user);
  const status = useUserStore((state) => state.status);
  const serverError = useUserStore((state) => state.error);
  const signUp = useUserStore((state) => state.register);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { email: '', password: '', confirm: '' },
  });

  // Already signed in — a second account is not what they came here for.
  if (user !== null) {
    return <Navigate to={takeIntendedPath()} replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    const ok = await signUp(values.email.trim(), values.password);
    if (ok) navigate('/ships', { replace: true });
  });

  const busy = isSubmitting || status === 'pending';

  return (
    <div className="flex min-h-full items-center justify-center bg-aurora-bg px-4 py-10">
      <form
        onSubmit={(event) => {
          void onSubmit(event);
        }}
        className="w-full max-w-sm rounded border border-aurora-border bg-aurora-panel p-6"
        noValidate
      >
        <div className="mb-6 text-center">
          <div className="text-lg font-semibold tracking-[0.3em] text-aurora-accent">AURORA</div>
          <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-aurora-muted">
            Create operator account
          </p>
        </div>

        <label className="mb-3 block" title="The address this operator account will sign in with">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-aurora-muted">
            Email
          </span>
          <input
            type="email"
            autoComplete="username"
            autoFocus
            placeholder="operator@aurora.demo"
            className="w-full rounded-sm border border-aurora-border bg-aurora-bg px-2.5 py-2 text-sm text-aurora-text outline-none transition-colors focus:border-aurora-accent"
            aria-invalid={errors.email ? true : undefined}
            {...register('email')}
          />
          {errors.email ? (
            <span className="mt-1 block text-[11px] text-aurora-crit">{errors.email.message}</span>
          ) : null}
        </label>

        <label className="mb-3 block" title="At least 8 characters. It is never shown back to you.">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-aurora-muted">
            Password
          </span>
          <input
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            className="w-full rounded-sm border border-aurora-border bg-aurora-bg px-2.5 py-2 text-sm text-aurora-text outline-none transition-colors focus:border-aurora-accent"
            aria-invalid={errors.password ? true : undefined}
            {...register('password')}
          />
          {errors.password ? (
            <span className="mt-1 block text-[11px] text-aurora-crit">
              {errors.password.message}
            </span>
          ) : null}
        </label>

        <label className="mb-4 block" title="Type the same password again.">
          <span className="mb-1 block text-[10px] uppercase tracking-[0.14em] text-aurora-muted">
            Confirm password
          </span>
          <input
            type="password"
            autoComplete="new-password"
            placeholder="••••••••"
            className="w-full rounded-sm border border-aurora-border bg-aurora-bg px-2.5 py-2 text-sm text-aurora-text outline-none transition-colors focus:border-aurora-accent"
            aria-invalid={errors.confirm ? true : undefined}
            {...register('confirm')}
          />
          {errors.confirm ? (
            <span className="mt-1 block text-[11px] text-aurora-crit">{errors.confirm.message}</span>
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
          className="w-full rounded-sm bg-aurora-accent px-3 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-aurora-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Creating account…' : 'Create account'}
        </button>

        <p className="mt-4 text-center text-[10px] leading-relaxed text-aurora-muted">
          Already have an account?{' '}
          <Link to="/login" className="text-aurora-accent underline-offset-2 hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </div>
  );
}
