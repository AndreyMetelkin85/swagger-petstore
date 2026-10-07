export type PendingPayment = { key: string; previousPaymentIds: string[] };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function decodePendingPayment(raw: string | null): PendingPayment | null {
  try { const value = JSON.parse(raw ?? 'null'); return value && typeof value.key === 'string' && uuid.test(value.key) && Array.isArray(value.previousPaymentIds) && value.previousPaymentIds.every((id: unknown) => typeof id === 'string' && uuid.test(id)) ? { key: value.key, previousPaymentIds: value.previousPaymentIds } : null; } catch { return null; }
}
export function encodePendingPayment(value: PendingPayment): string {
  return JSON.stringify({ key: value.key, previousPaymentIds: value.previousPaymentIds });
}
