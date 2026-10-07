import { items as originalItems } from '../domain';
import { emptyProfile, type Media, type State } from '../models';
import { ServiceError } from '../errors';
export const demoIds = { admin: '20000000-0000-4000-8000-000000000001', buyer: '20000000-0000-4000-8000-000000000002' };
export async function passwordHash(password: string, salt: string) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${salt}:${password}`));
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('');
}
async function seed(): Promise<State> {
  const categories = ['Корм', 'Для дома', 'Питомцы'].map((name, i) => ({ id: `30000000-0000-4000-8000-00000000000${i + 1}`, name, kind: i === 2 ? 'pet' as const : 'product' as const, version: 1, archived: false }));
  const media = originalItems.map((item, i) => ({ id: `40000000-0000-4000-8000-00000000000${i + 1}`, name: item.name, mime: item.kind === 'pet' ? 'image/png' : 'image/svg+xml', sourceType: 'DEMO' as const, sourceNote: 'Собственный демонстрационный ассет', seedUrl: item.kind === 'pet' ? '/images/pets-hero.png' : `/images/${item.id}.svg`, createdAt: new Date().toISOString() }));
  const items = originalItems.map((item, i) => ({ ...item, id: `10000000-0000-4000-8000-00000000000${i + 1}`, version: 1, sku: item.kind === 'product' ? `LAPKI-${i + 1}` : '', categoryId: categories[item.kind === 'pet' ? 2 : item.category === 'food' ? 0 : 1].id, brand: 'Лапки', productType: item.category === 'food' ? 'FEED' as const : 'ACCESSORY' as const, feedForm: item.category === 'food' ? 'DRY' as const : '' as const, lifeStages: ['ADULT'], netWeightGrams: i === 0 ? 2000 : i === 1 ? 1500 : 0, ingredients: 'Учебные данные. Состав уточняется по данным производителя.', publicationStatus: 'PUBLISHED' as const, images: [{ mediaId: media[i].id, alt: item.name }], reserved: 0, status: 'available' as const, breed: '', sex: i === 4 ? 'MALE' : 'FEMALE', birthDate: '' }));
  const users = await Promise.all([{ id: demoIds.admin, email: 'admin@lapki.demo', role: 'ADMIN' as const, password: 'Admin123!' }, { id: demoIds.buyer, email: 'buyer@lapki.demo', role: 'USER' as const, password: 'Buyer123!' }].map(async ({ password, ...user }) => ({ ...user, status: 'ACTIVE' as const, salt: user.id, passwordHash: await passwordHash(password, user.id), profile: { ...emptyProfile, name: user.role === 'ADMIN' ? 'Администратор' : 'Демо Покупатель', phone: '+79000000000', city: 'Москва', street: 'Учебная', building: '1', postalCode: '101000' } })));
  return { schema: 3, items, categories, users, carts: {}, orders: [], media, sessions: [], confirmations: [], idempotency: {}, stockHistory: [], scenario: 'NORMAL' };
}
let dbPromise: Promise<IDBDatabase> | undefined;
function database() {
  if (!dbPromise) dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open('lapki.mock.v3', 1);
    request.onupgradeneeded = () => { request.result.createObjectStore('state'); request.result.createObjectStore('media'); };
    request.onsuccess = () => resolve(request.result); request.onerror = () => reject(new ServiceError('STORAGE_UNAVAILABLE', 503));
  }); return dbPromise;
}
let initial: State;
export async function initialize() {
  initial = await seed();
  const orphanIds = await updateState((state) => {
    const referenced = new Set([...state.items.flatMap((item) => item.images.map((image) => image.mediaId)), ...state.orders.flatMap((order) => order.lines.flatMap((line) => line.images.map((image) => image.mediaId)))]);
    const old = state.media.filter((media) => !media.seedUrl && !referenced.has(media.id) && Date.parse(media.createdAt) < Date.now() - 86_400_000).map((media) => media.id);
    state.media = state.media.filter((media) => !old.includes(media.id));
    state.sessions = state.sessions.filter((session) => session.expiresAt > Date.now());
    for (const [id, value] of Object.entries(state.idempotency)) if (value.expiresAt <= Date.now()) delete state.idempotency[id];
    return old;
  });
  if (orphanIds.length) { const db = await database(); await new Promise<void>((resolve, reject) => { const tx = db.transaction('media', 'readwrite'); for (const id of orphanIds) { tx.objectStore('media').delete(id); tx.objectStore('media').delete(`${id}:thumb`); } tx.oncomplete = () => resolve(); tx.onerror = () => reject(new ServiceError('STORAGE_UNAVAILABLE', 503)); }); }
}
export async function updateState<T>(operation: (state: State) => T): Promise<T> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('state', 'readwrite'); let result: T; let failure: unknown;
    const request = tx.objectStore('state').get('current');
    request.onsuccess = () => { const state = (request.result as State | undefined) ?? structuredClone(initial); try { result = operation(state); tx.objectStore('state').put(state, 'current'); } catch (error) { failure = error; tx.abort(); } };
    tx.oncomplete = () => resolve(result); tx.onabort = tx.onerror = () => reject(failure ?? new ServiceError('STORAGE_UNAVAILABLE', 503));
  });
}
export async function putBlob(id: string, blob: Blob) {
  const db = await database();
  await new Promise<void>((resolve, reject) => { const tx = db.transaction('media', 'readwrite'); tx.objectStore('media').put(blob, id); tx.oncomplete = () => resolve(); tx.onerror = () => reject(new ServiceError('MEDIA_STORAGE_UNAVAILABLE', 503)); });
}
export async function getBlob(id: string): Promise<Blob | undefined> {
  const db = await database();
  return new Promise((resolve, reject) => { const request = db.transaction('media').objectStore('media').get(id); request.onsuccess = () => resolve(request.result); request.onerror = () => reject(new ServiceError('MEDIA_STORAGE_UNAVAILABLE', 503)); });
}
export async function saveMedia(meta: Media, image: Blob, thumb: Blob, verify: (state: State) => void) {
  const db = await database();
  return new Promise<Media>((resolve, reject) => {
    const tx = db.transaction(['state', 'media'], 'readwrite'); let failure: unknown;
    const request = tx.objectStore('state').get('current');
    request.onsuccess = () => {
      const state = request.result as State;
      try { verify(state); state.media.push(meta); tx.objectStore('state').put(state, 'current'); tx.objectStore('media').put(image, meta.id); tx.objectStore('media').put(thumb, `${meta.id}:thumb`); }
      catch (error) { failure = error; tx.abort(); }
    };
    tx.oncomplete = () => resolve(meta); tx.onabort = tx.onerror = () => reject(failure ?? new ServiceError('MEDIA_STORAGE_UNAVAILABLE', 503));
  });
}
export async function resetData() {
  const fresh = await seed(), db = await database();
  await new Promise<void>((resolve, reject) => { const tx = db.transaction(['state', 'media'], 'readwrite'); tx.objectStore('state').put(fresh, 'current'); tx.objectStore('media').clear(); tx.oncomplete = () => resolve(); tx.onerror = () => reject(new ServiceError('STORAGE_UNAVAILABLE', 503)); });
}
