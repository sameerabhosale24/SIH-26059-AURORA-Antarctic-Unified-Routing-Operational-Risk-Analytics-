// DEV ONLY — bypasses the backend for local frontend work.
// Remove when the real backend is running.
const DEV_MODE = import.meta.env.VITE_AUTH_DEV === 'true';
const DEMO_EMAIL = 'operator@aurora.demo';
const DEMO_PASSWORD = 'aurora123';

export async function devLogin(email: string, password: string) {
  if (!DEV_MODE) throw new Error('devLogin called outside dev mode');
  if (email !== DEMO_EMAIL || password !== DEMO_PASSWORD) {
    throw new Error('Invalid email or password');
  }
  return {
    token: 'dev-token-' + Date.now(),
    user: { id: 1, email: DEMO_EMAIL, role: 'operator' },
  };
}

export async function devRegister(email: string, _password: string) {
  if (!DEV_MODE) throw new Error('devRegister called outside dev mode');
  return {
    token: 'dev-token-' + Date.now(),
    user: { id: Date.now(), email, role: 'operator' },
  };
}

export async function devListVessels() {
  if (!DEV_MODE) throw new Error('devListVessels called outside dev mode');
  const raw = localStorage.getItem('aurora.dev.vessels');
  return raw ? JSON.parse(raw) : [];
}

export async function devCreateVessel(blueprint: any) {
  if (!DEV_MODE) throw new Error('devCreateVessel called outside dev mode');
  const list = await devListVessels();
  const vessel = { ...blueprint, id: Date.now(), user_id: 1 };
  list.push(vessel);
  localStorage.setItem('aurora.dev.vessels', JSON.stringify(list));
  return vessel;
}

export async function devGetVessel(id: number) {
  if (!DEV_MODE) throw new Error('devGetVessel called outside dev mode');
  const list = await devListVessels();
  return list.find((v: any) => v.id === id) ?? null;
}

export async function devDeleteVessel(id: number) {
  if (!DEV_MODE) throw new Error('devDeleteVessel called outside dev mode');
  const list = await devListVessels();
  const next = list.filter((v: any) => v.id !== id);
  localStorage.setItem('aurora.dev.vessels', JSON.stringify(next));
}
