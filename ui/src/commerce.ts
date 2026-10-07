import type { CartLine } from './domain.ts';
import type { Cart, Item, Order, State, User } from './models.ts';
import { ServiceError } from './errors.ts';
export function mergeCartLines(account: CartLine[], guest: CartLine[], items: Item[]): CartLine[] {
  const merged = new Map<string, number>();
  const names = new Map<string, string>();
  const kinds = new Map<string, 'product' | 'pet'>();
  for (const line of [...account, ...guest]) {
    if (!line || typeof line.id !== 'string' || !Number.isInteger(line.quantity) || line.quantity <= 0) continue;
    const item = items.find((entry) => entry.id === line.id);
    const kind = line.kind ?? item?.kind;
    if (kind) kinds.set(line.id, kind);
    if (line.name) names.set(line.id, line.name);
    merged.set(line.id, kind === 'pet' ? 1 : (merged.get(line.id) ?? 0) + line.quantity);
  }
  return [...merged].map(([id, quantity]) => ({ id, quantity, ...(kinds.has(id) ? { kind: kinds.get(id) } : {}), ...(names.has(id) ? { name: names.get(id) } : {}) }));
}
export function lineIssue(item: Item | undefined, quantity: number): string | null {
  if (!item || item.publicationStatus !== 'PUBLISHED' || (item.kind === 'pet' && item.status !== 'available')) return 'PRODUCT_UNAVAILABLE';
  if (!Number.isInteger(quantity) || quantity < 1 || (item.kind === 'pet' && quantity !== 1)) return 'VALIDATION_FAILED';
  return quantity > item.stock - item.reserved ? 'INSUFFICIENT_STOCK' : null;
}
export function remainingGuest(current: CartLine[], merged: CartLine[]): CartLine[] {
  return current.map((line) => ({ ...line, quantity: Math.max(0, line.quantity - (merged.find((entry) => entry.id === line.id)?.quantity ?? 0)) })).filter((line) => line.quantity > 0);
}
const totalOf = (lines: Order['lines']) => lines.reduce((sum, line) => sum + Math.round(line.price * 100) * line.quantity, 0) / 100;
export const cartAmount = (lines: CartLine[], items: Item[]) => lines.reduce((sum, line) => sum + Math.round((line.price ?? items.find((item) => item.id === line.id)?.price ?? 0) * 100) * line.quantity, 0) / 100;
export function createDraft(state: State, user: User, cart: Cart): Order {
  if (!cart.lines.length) throw new ServiceError('CART_EMPTY', 422);
  const lines = cart.lines.map((line) => {
    const item = state.items.find((entry) => entry.id === line.id), issue = lineIssue(item, line.quantity);
    if (!item || issue) throw new ServiceError(issue ?? 'PRODUCT_UNAVAILABLE', 409, [{ itemId: line.id }]);
    return { itemId: item.id, kind: item.kind, name: item.name, sku: item.sku, quantity: line.quantity, price: item.price, images: structuredClone(item.images) };
  });
  const order: Order = { id: crypto.randomUUID(), userId: user.id, version: 1, cartVersion: cart.version, status: 'DRAFT', paymentStatus: 'NOT_STARTED', createdAt: new Date().toISOString(), reserveUntil: null, lines, total: totalOf(lines), delivery: null, payments: [], estimated: true };
  state.orders.unshift(order); return order;
}
export function placeOrder(state: State, user: User, order: Order, expectedTotal: number) {
  if (order.status !== 'DRAFT') throw new ServiceError('ORDER_TRANSITION_INVALID');
  const cart = state.carts[user.id] ?? { lines: [], version: 1 };
  if (cart.version !== order.cartVersion) throw new ServiceError('CART_VERSION_CONFLICT');
  const required = ['name', 'phone', 'city', 'street', 'building', 'postalCode'] as const;
  if (required.some((field) => !user.profile[field].trim())) throw new ServiceError('PROFILE_INCOMPLETE', 422);
  const current = order.lines.map((line) => {
    const item = state.items.find((entry) => entry.id === line.itemId), issue = lineIssue(item, line.quantity);
    if (!item || issue) throw new ServiceError(issue ?? 'PRODUCT_UNAVAILABLE', 409, [{ itemId: line.itemId }]);
    return { ...line, price: item.price, name: item.name, images: structuredClone(item.images) };
  });
  const total = totalOf(current);
  if (total !== expectedTotal) throw new ServiceError('PRICE_CHANGED');
  for (const line of current) { const item = state.items.find((entry) => entry.id === line.itemId)!; item.reserved += line.quantity; item.version++; if (item.kind === 'pet') item.status = 'reserved'; }
  order.lines = current; order.total = total; order.delivery = structuredClone(user.profile); order.status = 'PLACED'; order.paymentStatus = 'UNPAID'; order.estimated = false; order.reserveUntil = new Date(Date.now() + 15 * 60_000).toISOString(); order.version++;
  state.carts[user.id] = { lines: [], version: cart.version + 1 }; return order;
}
export function payOrder(state: State, order: Order, mode: 'success' | 'declined' | 'ambiguous', last4: string) {
  if (order.paymentStatus === 'PAID') return order;
  if (order.status !== 'PLACED') throw new ServiceError(order.status === 'EXPIRED' ? 'RESERVATION_EXPIRED' : 'ORDER_TRANSITION_INVALID');
  if (!order.reserveUntil || Date.parse(order.reserveUntil) <= Date.now()) throw new ServiceError('RESERVATION_EXPIRED');
  order.payments.push({ id: crypto.randomUUID(), status: mode === 'declined' ? 'DECLINED' : 'SUCCEEDED', last4, createdAt: new Date().toISOString() }); order.version++;
  if (mode === 'declined') return order;
  for (const line of order.lines) { const item = state.items.find((entry) => entry.id === line.itemId)!; if (item.kind === 'product') { item.stock -= line.quantity; item.reserved -= line.quantity; item.version++; } }
  order.paymentStatus = 'PAID'; order.reserveUntil = null; return order;
}
export function cancelOrder(state: State, order: Order) {
  if (order.status === 'CANCELLED') return order;
  if (!['DRAFT', 'PLACED', 'APPROVED'].includes(order.status)) throw new ServiceError('ORDER_TRANSITION_INVALID');
  if (order.status !== 'DRAFT') for (const line of order.lines) { const item = state.items.find((entry) => entry.id === line.itemId)!; if (item.kind === 'product' && order.paymentStatus === 'PAID') item.stock += line.quantity; else item.reserved = Math.max(0, item.reserved - line.quantity); if (item.kind === 'pet') item.status = 'available'; item.version++; }
  if (order.paymentStatus === 'PAID') { order.paymentStatus = 'REFUNDED'; order.payments.push({ id: crypto.randomUUID(), status: 'REFUNDED', last4: order.payments.at(-1)?.last4 ?? '', createdAt: new Date().toISOString() }); }
  order.status = 'CANCELLED'; order.reserveUntil = null; order.version++; return order;
}
export function expireOrders(state: State) {
  for (const order of state.orders) if (['PLACED', 'APPROVED'].includes(order.status) && order.paymentStatus === 'UNPAID' && order.reserveUntil && Date.parse(order.reserveUntil) <= Date.now()) { cancelOrder(state, order); order.status = 'EXPIRED'; }
}
export function advanceOrder(state: State, order: Order, next: string) {
  const allowed: Record<string, string> = { PLACED: 'APPROVED', APPROVED: 'SHIPPED', SHIPPED: 'DELIVERED' };
  if (allowed[order.status] !== next || order.paymentStatus !== 'PAID') throw new ServiceError('ORDER_TRANSITION_INVALID');
  order.status = next as Order['status']; order.version++;
  if (next === 'DELIVERED') for (const line of order.lines) { const item = state.items.find((entry) => entry.id === line.itemId)!; if (item.kind === 'pet') { item.status = 'sold'; item.reserved = 0; item.version++; } }
  return order;
}
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, child]) => `${JSON.stringify(key)}:${stable(child)}`).join(',')}}`;
  return JSON.stringify(value) ?? 'null';
}
export function idempotent<T>(state: State, scope: string, key: string | null, payload: unknown, operation: () => T): T {
  if (!key || !/^[a-zA-Z0-9-]{8,100}$/.test(key)) throw new ServiceError('VALIDATION_FAILED', 422, [{ field: 'idempotencyKey' }]);
  const id = `${scope}:${key}`, fingerprint = stable(payload), existing = state.idempotency[id];
  if (existing && existing.expiresAt > Date.now()) { if (existing.fingerprint !== fingerprint) throw new ServiceError('IDEMPOTENCY_KEY_REUSED'); return structuredClone(existing.result) as T; }
  const result = operation(); state.idempotency[id] = { fingerprint, result: structuredClone(result), expiresAt: Date.now() + 86_400_000 }; return result;
}
export function validateItem(item: Item, publishing: boolean): { field: string; code: string }[] {
  const errors: { field: string; code: string }[] = [];
  const required = (field: keyof Item, valid: boolean) => { if (!valid) errors.push({ field, code: 'REQUIRED' }); };
  required('name', !!item.name.trim());
  if (publishing) {
    required('categoryId', !!item.categoryId); required('price', Number.isFinite(item.price) && item.price > 0); required('animalTypes', item.animalTypes.length > 0); required('images', item.images.length > 0);
    if (item.kind === 'product') { required('sku', !!item.sku.trim()); if (item.productType === 'FEED') { required('brand', !!item.brand.trim()); required('feedForm', !!item.feedForm); required('lifeStages', item.lifeStages.length > 0); required('netWeightGrams', item.netWeightGrams > 0); } }
  }
  if (!Number.isInteger(item.stock) || item.stock < 0) errors.push({ field: 'stock', code: 'NON_NEGATIVE_INTEGER' });
  if (item.images.length > 20) errors.push({ field: 'images', code: 'MEDIA_LIMIT_EXCEEDED' }); return errors;
}
