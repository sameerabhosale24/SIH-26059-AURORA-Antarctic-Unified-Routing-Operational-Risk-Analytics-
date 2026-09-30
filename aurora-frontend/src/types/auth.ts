/**
 * Authentication types.
 *
 * The backend issues a bearer token on login and treats it as stateless —
 * there is no refresh token and no server-side session to end, which is why
 * `logout` is a client-side clear plus an advisory `POST`.
 */
export interface User {
  id: number;
  email: string;
  role: string;
}

/** Response of `POST /api/auth/login`. */
export interface LoginResponse {
  token: string;
  user: User;
}
