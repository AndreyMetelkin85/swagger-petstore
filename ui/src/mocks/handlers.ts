import { delay, http, HttpResponse } from 'msw';
import { advanceOrder, cancelOrder, createDraft, expireOrders, idempotent, payOrder, placeOrder, validateItem } from '../commerce';
import { ServiceError } from '../errors';
import { emptyProfile, type Category, type Item, type Media, type Order, type Profile, type Scenario, type State, type StoredUser, type User } from '../models';
import { itemSchema } from '../validation';
import { getBlob, passwordHash, resetData, saveMedia, updateState } from './storage';

const publicUser = (user: StoredUser): User => ({ id: user.id, username: user.username ?? user.email.split('@')[0], email: user.email, role: user.role, status: user.status, profile: user.profile });
function authorize(state: State, request: Request, admin = false) {
  const token = request.headers.get('Authorization')?.replace(/^Bearer /, '');
  const session = state.sessions.find((entry) => entry.token === token && entry.expiresAt > Date.now());
  const user = state.users.find((entry) => entry.id === session?.userId);
  if (!user) throw new ServiceError('UNAUTHORIZED', 401);
  if (user.status === 'BLOCKED') throw new ServiceError('ACCOUNT_BLOCKED', 403);
  if (user.status !== 'ACTIVE') throw new ServiceError('ACCOUNT_NOT_VERIFIED', 403);
  if (admin && user.role !== 'ADMIN') throw new ServiceError('FORBIDDEN', 403);
  return user;
}
function userOrder(state: State, user: User, id: string): Order {
  const order = state.orders.find((entry) => entry.id === id && (entry.userId === user.id || user.role === 'ADMIN'));
  if (!order) throw new ServiceError('PRODUCT_NOT_FOUND', 404); return order;
}
const validEmail = (value: unknown) => typeof value === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) && value.length <= 254;
function issueLink(state: State, userId: string, kind: 'confirm' | 'reset') {
  state.confirmations = state.confirmations.filter((entry) => entry.userId !== userId || entry.kind !== kind);
  const code = crypto.randomUUID(), expiresAt = Date.now() + (kind === 'confirm' ? 24 * 3600_000 : 30 * 60_000); state.confirmations.push({ code, userId, kind, expiresAt });
  return kind === 'confirm' ? { confirmationUrl: `${location.origin}/api/v3/auth/confirm/${userId}?code=${code}`, expiresAt: new Date(expiresAt).toISOString() } : { demoLink: `/reset-password?code=${code}`, expiresAt: new Date(expiresAt).toISOString() };
}
async function authenticatedCredentials(body: Record<string, unknown>): Promise<StoredUser> {
  const details = [];
  if (!validEmail(body.email)) details.push({ field: 'email', code: 'INVALID_EMAIL' });
  if (typeof body.password !== 'string' || body.password.length < 6 || body.password.length > 100) details.push({ field: 'password', code: 'INVALID_PASSWORD' });
  if (details.length) throw new ServiceError('VALIDATION_ERROR', 422, details);
  const email = String(body.email).trim().toLowerCase();
  const candidate = await updateState((state) => { if ((state.authAttempts?.[email]?.blockedUntil ?? 0) > Date.now()) throw new ServiceError('LOGIN_RATE_LIMITED', 429); return state.users.find((user) => user.email === email); });
  const hash = candidate ? await passwordHash(String(body.password), candidate.salt) : '';
  const result = await updateState((state) => {
    const attempts = state.authAttempts ??= {}, previous = attempts[email], current = state.users.find((user) => user.email === email);
    if (previous?.blockedUntil > Date.now()) return { error: 'LOGIN_RATE_LIMITED' };
    if (!current || current.passwordHash !== hash) {
      const activeWindow = previous && previous.windowStart > Date.now() - 5 * 60_000;
      const count = activeWindow ? previous.count + 1 : 1;
      attempts[email] = { count, windowStart: activeWindow ? previous.windowStart : Date.now(), blockedUntil: count >= 5 ? Date.now() + 5 * 60_000 : 0 };
      return { error: count >= 5 ? 'LOGIN_RATE_LIMITED' : 'INVALID_CREDENTIALS' };
    }
    delete attempts[email]; return { user: current };
  });
  if (result.error) throw new ServiceError(result.error, result.error === 'LOGIN_RATE_LIMITED' ? 429 : 401);
  return result.user!;
}
function validateProfile(value: Profile) {
  const fields = ['name', 'phone', 'city', 'street', 'building', 'postalCode'] as const;
  const details = fields.filter((field) => !value[field]?.trim()).map((field) => ({ field, code: 'REQUIRED' }));
  if (!/^\+7\d{10}$/.test(String(value.phone ?? '').replace(/[\s()-]/g, ''))) details.push({ field: 'phone', code: 'INVALID_PHONE' });
  if (!/^\d{6}$/.test(value.postalCode)) details.push({ field: 'postalCode', code: 'INVALID_POSTAL' });
  if (details.length) throw new ServiceError('VALIDATION_FAILED', 422, details);
}
async function takeScenario(request: Request, path: string) {
  return updateState((state) => {
    const scenario = state.scenario;
    const matches = (scenario === 'MEDIA_STORAGE_UNAVAILABLE' && request.method === 'POST' && path === '/media') || (scenario === 'PRODUCT_VERSION_CONFLICT' && request.method === 'PUT' && /^\/admin\/(products|pets)\//.test(path)) || (['PRICE_CHANGED', 'INSUFFICIENT_STOCK'].includes(scenario) && path.endsWith('/place')) || (scenario === 'RESERVATION_EXPIRED' && path.endsWith('/payments')) || (scenario === 'SERVICE_UNAVAILABLE' && !path.startsWith('/demo'));
    if (!matches) return 'NORMAL' as Scenario;
    state.scenario = 'NORMAL';
    if (['PRICE_CHANGED', 'INSUFFICIENT_STOCK'].includes(scenario)) {
      const id = path.split('/')[3], order = state.orders.find((entry) => entry.id === id), line = order?.lines.find((entry) => entry.kind === 'product') ?? order?.lines[0];
      const item = state.items.find((entry) => entry.id === line?.itemId);
      if (item) { if (scenario === 'PRICE_CHANGED') item.price += 100; else { item.stock = 0; if (item.kind === 'pet') item.status = 'pending'; } item.version++; }
    }
    if (scenario === 'RESERVATION_EXPIRED') { const order = state.orders.find((entry) => entry.id === path.split('/')[3]); if (order) order.reserveUntil = new Date(Date.now() - 1000).toISOString(); expireOrders(state); }
    if (scenario === 'PRODUCT_VERSION_CONFLICT') { const item = state.items.find((entry) => entry.id === path.split('/')[3]); if (item) item.version++; }
    return scenario;
  });
}
function mediaVisible(state: State, request: Request, id: string) {
  if (state.items.some((item) => item.publicationStatus === 'PUBLISHED' && item.images.some((image) => image.mediaId === id))) return;
  const user = authorize(state, request);
  if (user.role === 'ADMIN' || state.orders.some((order) => order.userId === user.id && order.lines.some((line) => line.images.some((image) => image.mediaId === id)))) return;
  throw new ServiceError('FORBIDDEN', 403);
}
async function upload(request: Request) {
  await updateState((state) => authorize(state, request, true));
  const form = await request.formData(), file = form.get('file');
  if (!(file instanceof File) || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new ServiceError('MEDIA_UNSUPPORTED_TYPE', 415);
  if (file.size > 10 * 1024 * 1024) throw new ServiceError('MEDIA_FILE_TOO_LARGE', 413);
  const bytes = new Uint8Array(await file.arrayBuffer());
  const jpeg = bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
  const png = [137, 80, 78, 71, 13, 10, 26, 10].every((value, index) => bytes[index] === value);
  const webp = String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' && String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP';
  if (!jpeg && !png && !webp) throw new ServiceError('MEDIA_INVALID_IMAGE', 422);
  if (webp) {
    for (let pos = 12; pos + 8 <= bytes.length;) { const type = String.fromCharCode(...bytes.slice(pos, pos + 4)); if (type === 'ANIM' || type === 'ANMF') throw new ServiceError('MEDIA_UNSUPPORTED_TYPE', 415); const size = new DataView(bytes.buffer).getUint32(pos + 4, true); pos += 8 + size + (size % 2); }
  }
  let bitmap: ImageBitmap;
  try { bitmap = await createImageBitmap(file); } catch { throw new ServiceError('MEDIA_INVALID_IMAGE', 422); }
  if (bitmap.width * bitmap.height > 40_000_000 || !bitmap.width || !bitmap.height) { bitmap.close(); throw new ServiceError('MEDIA_INVALID_IMAGE', 422); }
  async function normalize(max: number) {
    const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas'); canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext('2d')!; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return new Promise<Blob>((resolve, reject) => canvas.toBlob((blob) => blob ? resolve(blob) : reject(new ServiceError('MEDIA_INVALID_IMAGE', 422)), 'image/jpeg', .9));
  }
  const [image, thumb] = await Promise.all([normalize(1600), normalize(400)]).finally(() => bitmap.close());
  const id = crypto.randomUUID();
  const sourceType = form.get('sourceType');
  const media: Media = { id, name: file.name.slice(0, 150), mime: 'image/jpeg', sourceType: ['OWN', 'SUPPLIER', 'DEMO'].includes(String(sourceType)) ? sourceType as Media['sourceType'] : 'OWN', sourceNote: String(form.get('sourceNote') ?? '').slice(0, 500), createdAt: new Date().toISOString() };
  return saveMedia(media, image, thumb, (state) => { authorize(state, request, true); });
}
async function dispatch(request: Request, path: string, body: Record<string, unknown>): Promise<unknown> {
  const method = request.method, url = new URL(request.url), parts = path.split('/').filter(Boolean);
  if (path === '/auth/register' && method === 'POST') {
    const details = [];
    if (!validEmail(body.email)) details.push({ field: 'email' });
    if (typeof body.password !== 'string' || body.password.length < 6 || body.password.length > 100) details.push({ field: 'password' });
    if (typeof body.username !== 'string' || !/^[A-Za-z0-9_.-]{3,30}$/.test(body.username)) details.push({ field: 'username' });
    if (details.length) throw new ServiceError('VALIDATION_ERROR', 422, details);
    const salt = crypto.randomUUID(), hash = await passwordHash(String(body.password), salt);
    return updateState((state) => {
      const email = String(body.email).trim().toLowerCase(), username = String(body.username), conflicts = [];
      if (state.users.some((user) => user.email === email)) conflicts.push({ field: 'email' });
      if (state.users.some((user) => (user.username ?? user.email.split('@')[0]).toLowerCase() === username.toLowerCase())) conflicts.push({ field: 'username' });
      if (conflicts.length) throw new ServiceError('USER_ALREADY_EXISTS', 409, conflicts);
      const user: StoredUser = { id: crypto.randomUUID(), username, email, salt, passwordHash: hash, role: 'USER', status: 'PENDING', profile: { ...emptyProfile, name: String(body.firstName ?? '').slice(0, 50) } };
      state.users.push(user); return { user: publicUser(user), ...issueLink(state, user.id, 'confirm') };
    });
  }
  if (path === '/auth/login' && method === 'POST') {
    const candidate = await authenticatedCredentials(body);
    return updateState((state) => { const user = state.users.find((entry) => entry.id === candidate.id)!; if (user.status !== 'ACTIVE') throw new ServiceError(user.status === 'PENDING' ? 'ACCOUNT_NOT_VERIFIED' : 'ACCOUNT_BLOCKED', 403); const token = crypto.randomUUID(); state.sessions.push({ token, userId: user.id, expiresAt: Date.now() + 3600_000 }); return { access_token: token, token_type: 'Bearer', expires_in: 3600, user: publicUser(user) }; });
  }
  if (['/auth/confirmation/resend', '/auth/resend'].includes(path) && method === 'POST') {
    const candidate = await authenticatedCredentials(body);
    return updateState((state) => { const user = state.users.find((entry) => entry.id === candidate.id)!; if (user.status !== 'PENDING') throw new ServiceError('ACCOUNT_ALREADY_CONFIRMED', 409); return issueLink(state, user.id, 'confirm'); });
  }
  if (path === '/auth/forgot' && method === 'POST') {
    return updateState((state) => { const user = state.users.find((entry) => entry.email === String(body.email).toLowerCase()); return user ? issueLink(state, user.id, 'reset') : { demoLink: null }; });
  }
  if (parts[0] === 'auth' && parts[1] === 'confirm' && method === 'GET') {
    if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(parts[2] ?? '')) throw new ServiceError('BAD_REQUEST', 400);
    return updateState((state) => {
      const user = state.users.find((entry) => entry.id === parts[2]); if (!user) throw new ServiceError('USER_NOT_FOUND', 404);
      if (user.status !== 'PENDING') throw new ServiceError('ACCOUNT_ALREADY_CONFIRMED', 409);
      const link = state.confirmations.find((entry) => entry.userId === user.id && entry.kind === 'confirm');
      if (!link || link.code !== url.searchParams.get('code')) throw new ServiceError('INVALID_CONFIRMATION_LINK', 400);
      if (link.expiresAt <= Date.now()) throw new ServiceError('CONFIRMATION_LINK_EXPIRED', 410);
      user.status = 'ACTIVE'; state.confirmations = state.confirmations.filter((entry) => entry !== link); return publicUser(user);
    });
  }
  if (['/auth/confirm', '/auth/reset'].includes(path) && method === 'POST') {
    const found = await updateState((state) => state.confirmations.find((entry) => entry.code === body.code && entry.kind === (path === '/auth/confirm' ? 'confirm' : 'reset') && entry.expiresAt > Date.now()));
    if (!found) throw new ServiceError('LINK_EXPIRED', 422);
    const user = await updateState((state) => state.users.find((entry) => entry.id === found.userId)!);
    if (path === '/auth/reset' && (typeof body.password !== 'string' || body.password.length < 6)) throw new ServiceError('VALIDATION_FAILED', 422);
    const hash = path === '/auth/reset' ? await passwordHash(String(body.password), user.salt) : null;
    return updateState((state) => { if (!state.confirmations.some((entry) => entry.code === body.code && entry.expiresAt > Date.now())) throw new ServiceError('LINK_EXPIRED', 422); const current = state.users.find((entry) => entry.id === user.id)!; if (current.status === 'BLOCKED') throw new ServiceError('ACCOUNT_BLOCKED', 403); if (hash) { current.passwordHash = hash; state.sessions = state.sessions.filter((entry) => entry.userId !== current.id); } else current.status = 'ACTIVE'; state.confirmations = state.confirmations.filter((entry) => entry.code !== body.code); return { ok: true }; });
  }
  if (path === '/media' && method === 'POST') return upload(request);
  if (path === '/demo/reset' && method === 'POST') { await updateState((state) => authorize(state, request, true)); await resetData(); return { ok: true }; }
  return updateState((state) => {
    expireOrders(state);
    if (path === '/me') {
      const user = authorize(state, request);
      if (method === 'PUT') { const profile = body as unknown as Profile; validateProfile(profile); user.profile = Object.fromEntries(Object.keys(emptyProfile).map((key) => [key, String(profile[key as keyof Profile] ?? '').trim().slice(0, 200)])) as Profile; }
      return publicUser(user);
    }
    if (path === '/auth/logout' && method === 'POST') { const token = request.headers.get('Authorization')?.replace(/^Bearer /, ''); state.sessions = state.sessions.filter((entry) => entry.token !== token); return { ok: true }; }
    if (parts[0] === 'media' && method === 'GET') { mediaVisible(state, request, parts[1]); const media = state.media.find((entry) => entry.id === parts[1]); if (!media) throw new ServiceError('MEDIA_NOT_FOUND', 404); return { id: media.id, mime: media.mime, seedUrl: media.seedUrl, createdAt: media.createdAt }; }
    if (path === '/catalog/categories' && method === 'GET') return state.categories.filter((category) => !category.archived);
    if ((parts[0] === 'products' || (parts[0] === 'catalog' && parts[1] === 'pets')) && method === 'GET') {
      const kind = parts[0] === 'products' ? 'product' : 'pet', id = parts[0] === 'products' ? parts[1] : parts[2];
      const items = state.items.filter((item) => item.kind === kind && item.publicationStatus === 'PUBLISHED');
      if (id) { const item = items.find((entry) => entry.id === id); if (!item) throw new ServiceError('PRODUCT_NOT_FOUND', 404); return item; }
      const q = (url.searchParams.get('q') ?? '').toLowerCase(); return items.filter((item) => `${item.name} ${item.brand} ${item.sku}`.toLowerCase().includes(q));
    }
    if (path === '/store/cart') {
      const user = authorize(state, request), cart = state.carts[user.id] ?? { lines: [], version: 1 };
      if (method === 'PUT') {
        const save = () => {
        if (body.version !== cart.version) throw new ServiceError('CART_VERSION_CONFLICT');
        if (!Array.isArray(body.lines) || body.lines.some((line) => !line || typeof line.id !== 'string' || !Number.isInteger(line.quantity) || line.quantity < 1 || line.quantity > 1000000)) throw new ServiceError('VALIDATION_FAILED', 422);
        cart.lines = body.lines.map((line) => { const item = state.items.find((entry) => entry.id === line.id); return { id: line.id, quantity: item?.kind === 'pet' ? 1 : line.quantity, name: item?.publicationStatus === 'PUBLISHED' ? item.name : cart.lines.find((entry) => entry.id === line.id)?.name ?? String(line.name ?? 'Недоступная позиция').slice(0, 150) }; }); cart.version++;
        state.carts[user.id] = cart; return cart;
        };
        const key = request.headers.get('Idempotency-Key');
        return key ? idempotent(state, `${user.id}:cart-merge`, key, body, save) : save();
      }
      state.carts[user.id] = cart; return cart;
    }
    if (parts[0] === 'store' && parts[1] === 'orders') {
      const user = authorize(state, request);
      if (!parts[2]) {
        if (method === 'GET') return state.orders.filter((order) => order.userId === user.id);
        if (method === 'POST') return idempotent(state, `${user.id}:draft`, request.headers.get('Idempotency-Key'), body, () => { const cart = state.carts[user.id] ?? { lines: [], version: 1 }; if (body.cartVersion !== undefined && body.cartVersion !== cart.version) throw new ServiceError('CART_VERSION_CONFLICT'); return createDraft(state, user, cart); });
      }
      const order = userOrder(state, user, parts[2]);
      if (method === 'GET') return order;
      const key = request.headers.get('Idempotency-Key');
      if (parts[3] === 'place') return idempotent(state, `${user.id}:${order.id}:place`, key, body, () => placeOrder(state, user, order, Number(body.expectedTotal)));
      if (parts[3] === 'cancel') return cancelOrder(state, order);
      if (parts[3] === 'payments') {
        const mode = body.mode as 'success' | 'declined' | 'ambiguous';
        if (!['success', 'declined', 'ambiguous'].includes(mode) || !/^\d{4}$/.test(String(body.last4))) throw new ServiceError('INVALID_CARD', 422);
        return idempotent(state, `${user.id}:${order.id}:pay`, key, body, () => payOrder(state, order, mode, String(body.last4)));
      }
    }
    if (parts[0] === 'admin') {
      const user = authorize(state, request, true);
      if (['products', 'pets'].includes(parts[1])) {
        const kind = parts[1] === 'pets' ? 'pet' : 'product', existing = state.items.find((entry) => entry.id === parts[2] && entry.kind === kind);
        if (method === 'GET') { if (parts[2] && !existing) throw new ServiceError('PRODUCT_NOT_FOUND', 404); return existing ?? state.items.filter((item) => item.kind === kind); }
        if (parts[3] === 'stock' && method === 'POST') {
          if (!existing || existing.kind !== 'product') throw new ServiceError('PRODUCT_NOT_FOUND', 404);
          const quantity = Number(body.quantity); if (!Number.isInteger(quantity) || quantity < existing.reserved || !String(body.reason ?? '').trim()) throw new ServiceError('VALIDATION_FAILED', 422);
          state.stockHistory.unshift({ id: crypto.randomUUID(), actorId: user.id, itemId: existing.id, before: existing.stock, after: quantity, reason: String(body.reason).slice(0, 300), createdAt: new Date().toISOString() }); existing.stock = quantity; existing.version++; return existing;
        }
        if (parts[3] === 'archive' && method === 'POST') { if (!existing) throw new ServiceError('PRODUCT_NOT_FOUND', 404); existing.publicationStatus = 'ARCHIVED'; existing.version++; return existing; }
        if (method === 'POST' || method === 'PUT') {
          const parsed = itemSchema.safeParse(body);
          if (!parsed.success) throw new ServiceError('VALIDATION_FAILED', 422, parsed.error.issues.map((issue) => ({ field: String(issue.path[0]), code: 'INVALID_FIELD' })));
          if (method === 'PUT' && (!existing || body.version !== existing.version)) throw new ServiceError('PRODUCT_VERSION_CONFLICT');
          const item = { ...parsed.data, id: existing?.id ?? crypto.randomUUID(), kind, version: (existing?.version ?? 0) + 1, reserved: existing?.reserved ?? 0, stock: kind === 'pet' ? 1 : existing?.stock ?? parsed.data.stock, status: existing && ['reserved', 'sold'].includes(existing.status) ? existing.status : parsed.data.status } as Item;
          if (!existing && ['reserved', 'sold'].includes(item.status)) throw new ServiceError('VALIDATION_FAILED', 422, [{ field: 'status' }]);
          if (!['DRAFT', 'PUBLISHED', 'ARCHIVED'].includes(item.publicationStatus)) throw new ServiceError('VALIDATION_FAILED', 422);
          const errors = validateItem(item, item.publicationStatus === 'PUBLISHED'); if (errors.length) throw new ServiceError('VALIDATION_FAILED', 422, errors);
          if (item.images.some((image) => !state.media.some((media) => media.id === image.mediaId))) throw new ServiceError('MEDIA_NOT_FOUND', 422, [{ field: 'images' }]);
          if (item.sku && state.items.some((entry) => entry.id !== item.id && entry.sku.toLowerCase() === item.sku.toLowerCase())) throw new ServiceError('SKU_ALREADY_EXISTS', 409, [{ field: 'sku' }]);
          if (item.categoryId && !state.categories.some((category) => category.id === item.categoryId && category.kind === kind && !category.archived)) throw new ServiceError('VALIDATION_FAILED', 422, [{ field: 'categoryId' }]);
          item.category = kind === 'pet' ? 'pet' : item.productType === 'FEED' ? 'food' : 'accessory';
          item.subtitle = kind === 'pet' ? `${item.breed || 'Питомец'} · ${item.sex === 'MALE' ? 'мальчик' : item.sex === 'FEMALE' ? 'девочка' : 'пол не указан'}` : `${item.brand || 'Лапки'}${item.productType === 'FEED' ? ` · ${item.netWeightGrams / 1000} кг` : ''}`;
          if (existing) state.items[state.items.indexOf(existing)] = item; else state.items.push(item); return item;
        }
      }
      if (parts[1] === 'categories') {
        if (method === 'GET') return state.categories;
        const existing = state.categories.find((category) => category.id === parts[2]);
        if (method === 'DELETE') { if (!existing) throw new ServiceError('PRODUCT_NOT_FOUND', 404); if (state.items.some((item) => item.categoryId === existing.id)) throw new ServiceError('CATEGORY_IN_USE'); existing.archived = true; existing.version++; return existing; }
        if (!String(body.name ?? '').trim() || !['product', 'pet'].includes(String(body.kind))) throw new ServiceError('VALIDATION_FAILED', 422);
        if (existing && body.version !== existing.version) throw new ServiceError('PRODUCT_VERSION_CONFLICT');
        if (existing && existing.kind !== body.kind && state.items.some((item) => item.categoryId === existing.id)) throw new ServiceError('CATEGORY_IN_USE');
        const category: Category = { id: existing?.id ?? crypto.randomUUID(), name: String(body.name).trim().slice(0, 80), kind: body.kind as Category['kind'], version: (existing?.version ?? 0) + 1, archived: false };
        if (existing) state.categories[state.categories.indexOf(existing)] = category; else state.categories.push(category); return category;
      }
      if (parts[1] === 'orders') {
        if (method === 'GET') return parts[2] ? userOrder(state, user, parts[2]) : state.orders;
        const order = userOrder(state, user, parts[2]); return body.status === 'CANCELLED' ? cancelOrder(state, order) : advanceOrder(state, order, String(body.status));
      }
      if (parts[1] === 'users') {
        if (method === 'GET') return state.users.map(publicUser);
        const target = state.users.find((entry) => entry.id === parts[2]); if (!target) throw new ServiceError('PRODUCT_NOT_FOUND', 404);
        if (!['ACTIVE', 'BLOCKED'].includes(String(body.status))) throw new ServiceError('VALIDATION_FAILED', 422);
        if (target.id === user.id || (target.role === 'ADMIN' && state.users.filter((entry) => entry.role === 'ADMIN' && entry.status === 'ACTIVE').length <= 1)) throw new ServiceError('LAST_ADMIN');
        target.status = body.status as User['status']; if (target.status === 'BLOCKED') state.sessions = state.sessions.filter((session) => session.userId !== target.id); return publicUser(target);
      }
      if (parts[1] === 'stock-history') return state.stockHistory;
    }
    if (path === '/demo/scenario') { authorize(state, request, true); if (method === 'POST') state.scenario = body.scenario as Scenario; return { scenario: state.scenario }; }
    throw new ServiceError('PRODUCT_NOT_FOUND', 404);
  });
}

export const handlers = [http.all('/api/v3/*', async ({ request }) => {
  const requestId = request.headers.get('X-Request-ID') ?? crypto.randomUUID(), path = new URL(request.url).pathname.slice('/api/v3'.length);
  const headers = { 'Content-Type': 'application/json', 'X-Request-ID': requestId };
  try {
    await delay(path.startsWith('/media') ? 250 : 90);
    if (path === '/telemetry/client-events' && request.method === 'POST') return new HttpResponse(null, { status: 202, headers: { 'X-Request-ID': requestId } });
    // Commit expiry independently so failed actions cannot roll it back.
    await updateState((state) => expireOrders(state));
    const scenario = await takeScenario(request, path);
    if (scenario === 'MEDIA_STORAGE_UNAVAILABLE' || scenario === 'SERVICE_UNAVAILABLE') throw new ServiceError(scenario, 503);
    const rawBody = !['GET', 'HEAD'].includes(request.method) && request.headers.get('Content-Type')?.includes('application/json') ? await request.text() : '';
    let body: Record<string, unknown> = {};
    if (rawBody.trim()) { try { const parsed = JSON.parse(rawBody); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(); body = parsed; } catch { throw new ServiceError('VALIDATION_FAILED', 422); } }
    const wasPaid = path.endsWith('/payments') ? await updateState((state) => state.orders.find((order) => order.id === path.split('/')[3])?.paymentStatus === 'PAID') : false;
    const result = await dispatch(request, path, body);
    if (/^\/media\/[^/]+\/(image|thumb)$/.test(path)) {
      const media = result as Media;
      const blob = media.seedUrl ? await fetch(media.seedUrl).then((response) => response.blob()) : await getBlob(path.endsWith('/thumb') ? `${media.id}:thumb` : media.id);
      if (!blob) throw new ServiceError('MEDIA_NOT_FOUND', 404);
      return new HttpResponse(blob, { headers: { 'Content-Type': blob.type, 'X-Request-ID': requestId } });
    }
    if (path.endsWith('/payments')) {
      const order = result as Order;
      if (body.mode === 'ambiguous' && !wasPaid) throw new ServiceError('PAYMENT_STATUS_UNKNOWN', 504);
      if (body.mode === 'declined' && order.paymentStatus !== 'PAID') throw new ServiceError('PAYMENT_DECLINED', 402);
    }
    return new HttpResponse(JSON.stringify(result), { headers, status: path === '/auth/register' && request.method === 'POST' ? 201 : 200 });
  } catch (error) {
    const known = error instanceof ServiceError ? error : new ServiceError('UNEXPECTED', 500);
    return new HttpResponse(JSON.stringify({ status: known.status, error: known.code, message: 'Mock service internal diagnostic', details: known.details, requestId }), { status: known.status, headers });
  }
})];
