export const SALON = 'glow-studio';
export const API = '/api/backend';
export type Service = { _id: string; name: string; category: string; price: number; duration_min: number };
export type SalonData = { salon: {name: string; address: string; phone: string; hours: Record<string,string>}; services: Service[]; staff: {name:string; specialties:string[]}[] };
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(API + path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Something went wrong. Please try again.');
  return body;
}
export function openConcierge(message?: string) { window.dispatchEvent(new CustomEvent('open-concierge', { detail: message })); }
