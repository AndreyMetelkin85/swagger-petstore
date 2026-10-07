import type { Cart, Category, Item, Media, Order, Profile, User } from './models';
import { ServiceError } from './errors';
import { log } from './logger';
import { decode, mapPayment, mapUser, profilePayload, type PaymentInput } from './backend-dto';
import { cardPayload, cartPayload, mapCard, mapCommerceCart, mapCommerceCategory, mapCommerceOrder, pageDto } from './commerce-dto';

export const dataMode = import.meta.env.VITE_DATA_MODE ?? 'api';
export const isLive = dataMode === 'api';
export const capabilities = { products: true, media: true, serverCart: true, mixedOrders: true, petPublication: true, telemetry: true } as const;
export const sessionKey = isLive ? 'lapki.session.api.v1' : 'lapki.session.v3';
export const mailViewerUrl = import.meta.env.VITE_MAIL_UI_URL as string | undefined;
export function token() { try { return sessionStorage.getItem(sessionKey); } catch { return null; } }
export async function request<T>(path: string, options: { method?: string; body?: unknown; key?: string; signal?: AbortSignal; blob?: boolean } = {}): Promise<T> {
  const requestId = crypto.randomUUID(), start = performance.now(), method = options.method ?? 'GET';
  const headers: Record<string, string> = { 'X-Request-ID': requestId };
  // Explicitly bypass a previously installed MSW worker when this origin switches to API mode.
  if (isLive) headers.Accept = 'application/json, msw/passthrough';
  const currentToken = token(); if (currentToken) headers.Authorization = `Bearer ${currentToken}`;
  if (options.key) headers['Idempotency-Key'] = options.key;
  const isForm = options.body instanceof FormData; if (options.body && !isForm) headers['Content-Type'] = 'application/json';
  const endpointTemplate = path.split('?')[0].replace(/[0-9a-f]{8}-[0-9a-f-]{27}/gi, ':id');
  try {
    const response = await fetch(`/api/v3${path}`, { method, headers, body: options.body ? isForm ? options.body as FormData : JSON.stringify(options.body) : undefined, signal: options.signal ?? AbortSignal.timeout(15_000) });
    const responseId = response.headers.get('X-Request-ID') ?? requestId;
    const result = { method, endpointTemplate, resourceId: path.split('?')[0].match(/[0-9a-f]{8}-[0-9a-f-]{27}/i)?.[0], httpStatus: response.status, durationMs: Math.round(performance.now() - start), requestId: responseId };
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as { error?: string; details?: { field?: string; code?: string; itemId?: string }[] };
      log('api_result', { ...result, code: typeof body.error === 'string' ? body.error : 'SERVICE_UNAVAILABLE' });
      throw new ServiceError(typeof body.error === 'string' ? body.error : 'SERVICE_UNAVAILABLE', response.status, Array.isArray(body.details) ? body.details : [], responseId);
    }
    log('api_result', result);
    if (response.status === 204) return undefined as T;
    if (options.blob) return await response.blob() as T;
    const text = await response.text();
    if (!text.trim()) return undefined as T;
    try { return JSON.parse(text) as T; } catch { throw new ServiceError('API_CONTRACT_MISMATCH', 502, [], responseId); }
  } catch (error) {
    if (error instanceof ServiceError) throw error;
    log('api_failure', { method, endpointTemplate, requestId, durationMs: Math.round(performance.now() - start) });
    throw new ServiceError('SERVICE_UNAVAILABLE', 503, [], requestId);
  }
}
async function cards(path: string): Promise<Item[]> {
  const result: Item[] = [];
  for (let page = 1; ; page++) {
    const data = decode(pageDto, await request<unknown>(`${path}?page=${page}&pageSize=100`));
    result.push(...data.items.map(mapCard));
    if (page * data.pageSize >= data.total || !data.items.length) return result;
  }
}
async function getOrder(id: string, admin = false): Promise<Order> {
  if (!isLive) return request<Order>(`${admin ? '/admin' : '/store'}/orders/${id}`);
  const [raw, payments] = await Promise.all([request<unknown>(`/store/orders/${id}`), request<unknown[]>(`/store/orders/${id}/payments`).then((values) => values.map(mapPayment))]);
  return { ...mapCommerceOrder(raw), payments };
}
const uncertain = (failure: unknown) => failure instanceof ServiceError && (failure.code === 'SERVICE_UNAVAILABLE' || failure.status >= 500);
export const api = {
  catalog: async (): Promise<Item[]> => (await Promise.all(isLive ? [cards('/products'), cards('/catalog/pets')] : [request<Item[]>('/products'), request<Item[]>('/catalog/pets')])).flat(),
  categories: async (): Promise<Category[]> => { const values = await request<unknown[]>('/catalog/categories'); return isLive ? values.map(mapCommerceCategory) : values as Category[]; },
  adminCategories: async (): Promise<Category[]> => { const values = await request<unknown[]>(isLive ? '/admin/catalog/categories' : '/admin/categories'); return isLive ? values.map(mapCommerceCategory) : values as Category[]; },
  saveCategory: async (category: Partial<Category> & Pick<Category, 'name' | 'kind'>) => { const path = isLive ? '/admin/catalog/categories' : '/admin/categories'; const result = await request<unknown>(`${path}${category.id ? `/${category.id}` : ''}`, { method: category.id ? 'PUT' : 'POST', body: isLive ? { name: category.name, kind: category.kind, active: !category.archived, ...(category.id ? { version: category.version } : {}) } : category }); return isLive ? mapCommerceCategory(result) : result as Category; },
  archiveCategory: (category: Category) => isLive ? api.saveCategory({ ...category, archived: true }) : request(`/admin/categories/${category.id}`, { method: 'DELETE' }),
  adminItems: async (): Promise<Item[]> => (await Promise.all(isLive ? [cards('/admin/products'), cards('/admin/pets')] : [request<Item[]>('/admin/products'), request<Item[]>('/admin/pets')])).flat(),
  adminItem: async (id: string, pets: boolean): Promise<Item> => { const result = await request<unknown>(`/admin/${pets ? 'pets' : 'products'}/${id}`); return isLive ? mapCard(result) : result as Item; },
  saveItem: async (item: Item, creating: boolean): Promise<Item> => { const path = isLive && item.kind === 'product' ? '/products' : `/admin/${item.kind === 'pet' ? 'pets' : 'products'}`; const result = await request<unknown>(`${path}${creating ? '' : `/${item.id}`}`, { method: creating ? 'POST' : 'PUT', body: isLive ? cardPayload(item, creating) : item }); return isLive ? mapCard(result) : result as Item; },
  publishItem: async (item: Item, action: 'publish' | 'unpublish' | 'archive'): Promise<Item> => { const path = isLive && item.kind === 'product' ? '/products' : `/admin/${item.kind === 'pet' ? 'pets' : 'products'}`; const result = await request<unknown>(`${path}/${item.id}/${action}`, { method: 'POST', ...(isLive ? { body: { version: item.version } } : {}) }); return isLive ? mapCard(result) : result as Item; },
  adjustStock: async (item: Item, quantity: number, reason: string): Promise<Item> => { const result = await request<unknown>(`${isLive ? '/products' : '/admin/products'}/${item.id}/${isLive ? 'stock-adjustments' : 'stock'}`, { method: 'POST', body: isLive ? { version: item.version, delta: quantity - item.stock, reason } : { version: item.version, quantity, reason } }); return isLive ? mapCard(result) : result as Item; },
  me: async (): Promise<User> => { const result = await request<unknown>(isLive ? '/user/me' : '/me'); return isLive ? mapUser(result) : result as User; },
  profile: async (profile: Profile): Promise<User> => { const result = await request<unknown>(isLive ? '/user/me' : '/me', { method: 'PUT', body: isLive ? profilePayload(profile) : profile }); return isLive ? mapUser(result) : result as User; },
  login: async (email: string, password: string) => { const result = await request<{ token?: string; access_token?: string; user: unknown }>('/auth/login', { method: 'POST', body: { email, password } }); const value = result.access_token ?? result.token; if (!value || typeof value !== 'string') throw new ServiceError('API_CONTRACT_MISMATCH', 502); return { token: value, user: isLive ? mapUser(result.user) : result.user as User }; },
  register: async (values: { username: string; email: string; password: string; name?: string }) => { const result = await request<{ user: unknown; confirmationUrl: string; expiresAt: string }>('/auth/register', { method: 'POST', body: { username: values.username, email: values.email, password: values.password, ...(values.name?.trim() ? { firstName: values.name.trim() } : {}) } }); return { ...result, user: isLive ? mapUser(result.user) : result.user as User }; },
  resendConfirmation: (email: string, password: string) => request<{ confirmationUrl: string; expiresAt: string }>('/auth/confirmation/resend', { method: 'POST', body: { email, password } }),
  confirmRegistration: (userId: string, code: string) => request(`/auth/confirm/${encodeURIComponent(userId)}?code=${encodeURIComponent(code)}`),
  forgotPassword: async (email: string): Promise<{ demoLink: string | null }> => {
    if (!isLive) return request('/auth/forgot', { method: 'POST', body: { email } });
    await request('/auth/password/forgot', { method: 'POST', body: { email } });
    return { demoLink: null };
  },
  resetPassword: (code: string | null, password: string) => isLive ? request(`/auth/password/reset?code=${encodeURIComponent(code ?? '')}`, { method: 'POST', body: { newPassword: password } }) : request('/auth/reset', { method: 'POST', body: { code, password } }),
  logout: async () => { if (!isLive) await request('/auth/logout', { method: 'POST' }); },
  cart: async (): Promise<Cart> => { const result = await request<unknown>('/store/cart'); return isLive ? mapCommerceCart(result) : result as Cart; },
  cartSave: async (cart: Cart, key?: string): Promise<Cart> => { const result = await request<unknown>('/store/cart', { method: 'PUT', body: isLive ? cartPayload(cart) : cart, key }); return isLive ? mapCommerceCart(result) : result as Cart; },
  orders: async (): Promise<Order[]> => isLive ? (await request<unknown[]>('/store/orders')).map(mapCommerceOrder) : request('/store/orders'),
  adminOrders: async (): Promise<Order[]> => isLive ? (await request<unknown[]>('/store/orders')).map(mapCommerceOrder) : request('/admin/orders'),
  order: getOrder,
  createDraft: async (_lines: { id: string; quantity: number }[], key: string, cartVersion?: number): Promise<Order> => {
    if (!isLive) { const cart = await api.cart(); return request('/store/orders', { method: 'POST', key, body: { cartVersion: cart.version } }); }
    try { return mapCommerceOrder(await request<unknown>('/store/orders', { method: 'POST', key, body: { cartVersion: cartVersion ?? (await api.cart()).version } })); }
    catch (failure) { if (uncertain(failure)) throw new ServiceError('DRAFT_STATUS_UNKNOWN', 503, [], (failure as ServiceError).requestId); throw failure; }
  },
  placeOrder: async (id: string, expectedTotal: number, key: string, version?: number): Promise<Order> => {
    if (!isLive) return request(`/store/orders/${id}/place`, { method: 'POST', key, body: { expectedTotal } });
    try { await request(`/store/orders/${id}/place`, { method: 'POST', key, body: { version: version ?? (await getOrder(id)).version } }); }
    catch (failure) {
      if (uncertain(failure) || failure instanceof ServiceError && failure.code === 'INVALID_STATUS_TRANSITION') {
        const current = await getOrder(id).catch(() => null);
        if (current && ['PLACED', 'APPROVED', 'SHIPPED', 'DELIVERED'].includes(current.status)) return current;
      }
      if (uncertain(failure)) throw new ServiceError('PLACE_STATUS_UNKNOWN', 503, [], (failure as ServiceError).requestId);
      throw failure;
    }
    return getOrder(id);
  },
  payOrder: async (order: Order, input: PaymentInput, key: string): Promise<Order> => {
    if (!isLive) throw new ServiceError('FEATURE_NOT_READY', 503);
    try { await request(`/store/orders/${order.id}/payments`, { method: 'POST', key, body: input }); return await getOrder(order.id); }
    catch (failure) { if (uncertain(failure)) throw new ServiceError('PAYMENT_STATUS_UNKNOWN', 503, [], (failure as ServiceError).requestId); throw failure; }
  },
  cancelOrder: async (id: string, version?: number) => request(`/store/orders/${id}/cancel`, { method: 'POST', ...(isLive ? { body: { version: version ?? (await getOrder(id)).version } } : {}) }),
  advanceOrder: async (id: string, next: 'APPROVED' | 'SHIPPED' | 'DELIVERED', version?: number) => isLive ? request(`/store/orders/${id}/${({ APPROVED: 'approve', SHIPPED: 'ship', DELIVERED: 'deliver' })[next]}`, { method: 'POST', body: { version: version ?? (await getOrder(id)).version } }) : request(`/admin/orders/${id}`, { method: 'PUT', body: { status: next } }),
  adminUsers: async (): Promise<User[]> => { const values = await request<unknown[]>(isLive ? '/users' : '/admin/users'); return isLive ? values.map(mapUser) : values as User[]; },
  blockUser: (id: string, blocked: boolean) => isLive ? request(`/admin/users/${id}/${blocked ? 'block' : 'unblock'}`, { method: 'POST' }) : request(`/admin/users/${id}`, { method: 'PUT', body: { status: blocked ? 'BLOCKED' : 'ACTIVE' } }),
  upload: (file: File, sourceType: string, sourceNote: string, signal?: AbortSignal) => { const body = new FormData(); body.append('file', file); body.append('sourceType', sourceType); body.append('sourceNote', sourceNote); return request<Media>('/media', { method: 'POST', body, signal }); },
};
