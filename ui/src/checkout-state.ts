import { z } from 'zod';
const pendingCheckout = z.object({ key: z.string().uuid(), cartVersion: z.number().int().positive(), placeKey: z.string().uuid(), draftId: z.string().uuid().optional(), placeVersion: z.number().int().nonnegative().optional() });
export type PendingCheckout = z.infer<typeof pendingCheckout>;
export function decodePendingCheckout(raw: string | null): PendingCheckout | null {
  try { const result = pendingCheckout.safeParse(JSON.parse(raw ?? 'null')); return result.success ? result.data : null; } catch { return null; }
}
