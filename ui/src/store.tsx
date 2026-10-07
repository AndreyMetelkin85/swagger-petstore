import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, capabilities, isLive, sessionKey, token } from './api';
import type { CartLine } from './domain';
import type { Cart, Item, User } from './models';
import { lineIssue, mergeCartLines, remainingGuest } from './commerce';
import { ServiceError, friendlyError } from './errors';
import { log, setLogActor } from './logger';
import { Button, Modal } from './ui';

const guestKey = isLive ? 'lapki.selection.api.v1' : 'lapki.guest.cart.v3';
function readGuest(): CartLine[] { try { const raw = JSON.parse(localStorage.getItem(guestKey) ?? '[]'); return Array.isArray(raw) ? raw.filter((line) => line && typeof line.id === 'string' && Number.isInteger(line.quantity) && line.quantity > 0) : []; } catch { return []; } }
type Store = {
  user: User | null; authLoading: boolean; items: Item[]; itemsLoading: boolean; catalogError: unknown; cartError: unknown; guest: CartLine[]; lines: CartLine[]; cartBusy: boolean; mergePending: boolean;
  login: (email: string, password: string) => Promise<void>; logout: () => Promise<void>; finishMerge: () => Promise<void>;
  setLine: (id: string, quantity: number) => Promise<void>; add: (item: Item) => Promise<void>; refresh: () => Promise<void>; report: (error: unknown) => void; notify: (text: string) => void;
};
const StoreContext = createContext<Store | null>(null);
export function useStore() { const context = useContext(StoreContext); if (!context) throw new Error('Store provider missing'); return context; }
export function StoreProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [session, setSession] = useState(token), [guest, setGuest] = useState<CartLine[]>(readGuest), [error, setError] = useState<unknown>(null), [toast, setToast] = useState(''), [cartBusy, setCartBusy] = useState(false), [mergePending, setMergePending] = useState(false);
  const guestRef = useRef(guest); guestRef.current = guest;
  const me = useQuery({ queryKey: ['me', session], queryFn: api.me, enabled: !!session, retry: false });
  const catalog = useQuery({ queryKey: ['catalog'], queryFn: api.catalog, retry: false });
  const user = me.data ?? null;
  useEffect(() => { setLogActor(user?.id); }, [user?.id]);
  const cartQuery = useQuery({ queryKey: ['cart', user?.id], queryFn: api.cart, enabled: !!user && capabilities.serverCart, retry: false });
  useEffect(() => { if (user && guest.length) setMergePending(true); }, [user?.id, guest.length]);
  function report(failure: unknown) { setError(failure); log('client_error', { code: failure instanceof ServiceError ? failure.code : 'UNEXPECTED', requestId: failure instanceof ServiceError ? failure.requestId : undefined }); }
  function saveGuest(lines: CartLine[]) { try { localStorage.setItem(guestKey, JSON.stringify(lines)); } catch { throw new ServiceError('STORAGE_UNAVAILABLE', 503); } guestRef.current = lines; setGuest(lines); }
  useEffect(() => { if (session && me.error) { if (me.error instanceof ServiceError && [401, 403].includes(me.error.status)) { sessionStorage.removeItem(sessionKey); setSession(null); client.removeQueries({ queryKey: ['me', session] }); } report(me.error); } }, [me.error, session]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 4500); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    const update = (event: StorageEvent) => { if (event.key === guestKey) { const next = readGuest(); guestRef.current = next; setGuest(next); } };
    window.addEventListener('storage', update); return () => window.removeEventListener('storage', update);
  }, []);
  async function refresh() { await client.invalidateQueries(); }
  async function mergeFor(currentUser: User) {
    if (!capabilities.serverCart) { setMergePending(false); return; }
    if (!guestRef.current.length) { setMergePending(false); return; }
    setMergePending(true);
    const operationKey = `lapki.merge.${currentUser.id}`;
    const stored = sessionStorage.getItem(operationKey);
    const pending = stored ? JSON.parse(stored) as { cart: Cart; key: string; guest?: CartLine[] } : null;
    const current = pending?.cart ?? await api.cart();
    const knownItems = isLive && guestRef.current.some((line) => !line.kind) ? catalog.data ?? await api.catalog() : catalog.data ?? [];
    const next = pending ?? { cart: { ...current, lines: mergeCartLines(current.lines, guestRef.current, knownItems) }, key: crypto.randomUUID(), guest: structuredClone(guestRef.current) };
    sessionStorage.setItem(operationKey, JSON.stringify(next));
    try {
      const merged = await api.cartSave(next.cart, next.key);
      const rest = remainingGuest(guestRef.current, next.guest ?? guestRef.current); saveGuest(rest); sessionStorage.removeItem(operationKey); client.setQueryData(['cart', currentUser.id], merged); setMergePending(false);
      if (rest.length) await mergeFor(currentUser);
    } catch (failure) { if (failure instanceof ServiceError && failure.code === 'CART_VERSION_CONFLICT') sessionStorage.removeItem(operationKey); throw failure; }
  }
  async function login(email: string, password: string) {
    const result = await api.login(email, password); client.removeQueries({ predicate: (query) => ['me', 'cart', 'order', 'orders', 'media', 'admin-items', 'admin-users', 'admin-orders'].includes(String(query.queryKey[0])) }); sessionStorage.setItem(sessionKey, result.token); setSession(result.token); client.setQueryData(['me', result.token], result.user);
    try { await mergeFor(result.user); } catch (failure) { report(failure); }
    log('signed_in', { result: 'success' });
  }
  async function finishMerge() { if (!user) return; setCartBusy(true); try { await mergeFor(user); } catch (failure) { report(failure); } finally { setCartBusy(false); } }
  async function logout() {
    try { await api.logout(); } catch { /* local sign-out must remain available */ }
    sessionStorage.removeItem(sessionKey); setSession(null); setMergePending(false); client.clear(); log('signed_out');
  }
  async function setLine(id: string, quantity: number) {
    if (cartBusy || mergePending) return;
    setCartBusy(true);
    try {
      const base = user && capabilities.serverCart ? client.getQueryData<Cart>(['cart', user.id]) ?? await api.cart() : { lines: guestRef.current, version: 1 };
      const item = catalog.data?.find((entry) => entry.id === id);
      if (quantity > 0 && item?.kind === 'pet') quantity = 1;
      if (!Number.isInteger(quantity) || quantity < 0 || quantity > 1000000) throw new ServiceError('VALIDATION_FAILED', 422);
      if (quantity > (base.lines.find((line) => line.id === id)?.quantity ?? 0)) { const issue = lineIssue(item, quantity); if (issue) throw new ServiceError(issue); }
      const lines = quantity ? base.lines.some((line) => line.id === id) ? base.lines.map((line) => line.id === id ? { ...line, quantity, kind: line.kind ?? item?.kind } : line) : [...base.lines, { id, quantity, name: item?.name, kind: item?.kind }] : base.lines.filter((line) => line.id !== id);
      if (user && capabilities.serverCart) { const saved = await api.cartSave({ ...base, lines }); client.setQueryData(['cart', user.id], saved); } else saveGuest(lines);
      log('cart_changed', { resourceId: id, quantity });
    } catch (failure) { report(failure); if (user) await client.invalidateQueries({ queryKey: ['cart', user.id] }); } finally { setCartBusy(false); }
  }
  const lines = user && capabilities.serverCart ? cartQuery.data?.lines ?? [] : guest;
  const value: Store = { user, authLoading: !!session && me.isPending, items: catalog.data ?? [], itemsLoading: catalog.isPending, catalogError: catalog.error, cartError: cartQuery.error, guest, lines, cartBusy: cartBusy || (!!user && capabilities.serverCart && cartQuery.isPending), mergePending, login, logout, finishMerge, setLine, add: (item) => setLine(item.id, (lines.find((line) => line.id === item.id)?.quantity ?? 0) + 1), refresh, report, notify: setToast };
  const translated = friendlyError(error);
  return <StoreContext.Provider value={value}>{children}<div className="toast-slot" role="status" aria-live="polite">{toast && <div className="toast" data-testid="toast">{toast}</div>}</div><Modal open={!!error} close={() => setError(null)} title={translated.title} description={translated.text} testId="error-dialog">{translated.requestId && <p className="request-id" data-testid="error-request-id">Номер обращения: {translated.requestId}</p>}<Button testId="error-dismiss" className="primary-button full-width" onClick={() => setError(null)}>Понятно</Button></Modal></StoreContext.Provider>;
}
