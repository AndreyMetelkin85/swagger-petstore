import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { api, request } from './api';
import { decodePendingCheckout, type PendingCheckout } from './checkout-state';
import type { Order } from './models';
import type { PaymentInput } from './backend-dto';
import { livePaymentSchema } from './validation';
import { ServiceError } from './errors';
import { useStore } from './store';
import { ProfileForm } from './ProfileForm';
import { ActionLink, Button, Empty, Field, Loading } from './ui';
import { money } from './domain';
import { lineIssue } from './commerce';
import { log } from './logger';
import { decodePendingPayment, encodePendingPayment, type PendingPayment } from './payment-state';

export function LiveCheckout() {
  const store = useStore(), navigate = useNavigate(), [search] = useSearchParams(), draftId = search.get('draft');
  const storageKey = `lapki.checkout.api.${store.user?.id}`;
  const operation = useRef<PendingCheckout | null>(decodePendingCheckout(sessionStorage.getItem(storageKey))), draft = useRef<Order | null>(null);
  const resumeId = draftId ?? operation.current?.draftId;
  const resume = useQuery({ queryKey: ['resume-draft', store.user?.id, resumeId], queryFn: () => api.order(resumeId!), enabled: !!resumeId && !!store.user, retry: false });
  useEffect(() => { if (resume.data) draft.current = resume.data; }, [resume.data]);
  if (!store.user || resumeId && resume.isPending) return <Loading />;
  if (store.cartError && !resumeId) return <Empty title="Не удалось загрузить корзину" text="Повторите запрос перед оформлением заказа."><Button testId="checkout-cart-retry" className="outline-button" onClick={() => { void store.refresh(); }}>Повторить</Button></Empty>;
  if (resume.error) return <Empty title="Не удалось открыть черновик" text="Откройте заказ в личном кабинете и проверьте его статус."><ActionLink testId="checkout-orders" to="/account/orders" className="primary-button">Мои заказы</ActionLink></Empty>;
  if (resume.data && resume.data.status !== 'DRAFT') return <Empty title="Заказ уже оформлен" text="Повторное оформление не требуется."><ActionLink testId="checkout-order" to={`/account/orders/${resume.data.id}`} className="primary-button">Открыть заказ</ActionLink></Empty>;
  const lines = resume.data?.lines ?? store.lines.map((line) => ({ itemId: line.id, quantity: line.quantity, name: line.name ?? store.items.find((item) => item.id === line.id)?.name ?? 'Недоступная позиция', price: line.price ?? store.items.find((item) => item.id === line.id)?.price ?? 0 }));
  if (!lines.length && !store.cartBusy) return <Empty title="Корзина пока пуста" text="Добавьте товары или питомца перед оформлением."><ActionLink testId="checkout-empty" className="primary-button" to="/catalog">В каталог</ActionLink></Empty>;
  const invalid = !resume.data && store.lines.some((line) => line.available === false || lineIssue(store.items.find((item) => item.id === line.id), line.quantity));
  const total = lines.reduce((sum, line) => sum + Math.round(line.price * 100) * line.quantity, 0) / 100;
  function persist(next: PendingCheckout) { sessionStorage.setItem(storageKey, JSON.stringify(next)); operation.current = next; }
  return <section className="page-section"><ActionLink testId="checkout-back" className="back-link" to="/cart">‹ В корзину</ActionLink><h1>Оформление заказа</h1><p className="page-intro">Проверьте контакты, адрес и состав заказа.</p><div className="cart-page-grid"><div className="panel"><h2>Контакты и доставка</h2><ProfileForm initial={store.user.profile} testPrefix="checkout" buttonLabel="Оформить заказ" disabled={!!invalid || store.cartBusy || store.mergePending} submit={async (profile) => {
    await api.profile(profile);
    try {
      if (!operation.current) {
        const cart = await api.cart();
        if (!draft.current && cart.lines.some((line) => {
          const displayed = lines.find((entry) => entry.itemId === line.id);
          return !displayed || displayed.quantity !== line.quantity || displayed.price !== line.price;
        })) throw new ServiceError('PRICE_CHANGED');
        // Saving acknowledges the prices displayed in the current quote. The server rechecks at placement.
        const quoted = draft.current ? cart : await api.cartSave(cart, crypto.randomUUID());
        persist({ key: crypto.randomUUID(), cartVersion: quoted.version, placeKey: crypto.randomUUID(), ...(draft.current ? { draftId: draft.current.id, placeVersion: draft.current.version } : {}) });
      }
      const pending = operation.current!;
      if (!draft.current) draft.current = await api.createDraft(store.lines, pending.key, pending.cartVersion);
      persist({ ...pending, draftId: draft.current.id, placeVersion: pending.placeVersion ?? draft.current.version });
      const order = await api.placeOrder(draft.current.id, total, pending.placeKey, operation.current!.placeVersion);
      sessionStorage.removeItem(storageKey); operation.current = null;
      // The server clears exactly the quoted cart atomically; never clear newer positions here.
      await store.refresh(); log('order_placed', { resourceId: order.id, result: 'success' }); navigate(`/account/orders/${order.id}`);
    } catch (failure) {
      if (failure instanceof ServiceError && ['PRICE_CHANGED', 'CART_VERSION_CONFLICT', 'INSUFFICIENT_STOCK', 'PRODUCT_UNAVAILABLE', 'PET_NOT_AVAILABLE'].includes(failure.code)) {
        if (draft.current?.status === 'DRAFT') await request(`/store/orders/${draft.current.id}`, { method: 'DELETE' }).catch(() => undefined);
        draft.current = null; operation.current = null; sessionStorage.removeItem(storageKey); await store.refresh(); navigate('/cart');
      }
      if (failure instanceof ServiceError && failure.code === 'PLACE_STATUS_UNKNOWN' && draft.current) navigate(`/account/orders/${draft.current.id}`);
      throw failure;
    }
  }} />{operation.current && !operation.current.draftId && <p className="form-hint" data-testid="checkout-retry-hint">Если ответ не получен, повторите оформление. Повтор использует тот же ключ и не создаст второй заказ.</p>}</div><aside className="panel order-summary"><h2>Состав заказа</h2>{lines.map((line) => <div className="summary-row" data-testid="checkout-item" key={line.itemId}><span>{line.name} × {line.quantity}</span><strong>{money(line.price * line.quantity)}</strong></div>)}<div className="cart-total"><span>Итого</span><strong data-testid="checkout-total">{money(total)}</strong></div><p className="form-hint">После оформления резерв действует 15 минут. Оплата тестовая.</p>{invalid && <ActionLink testId="checkout-fix-cart" to="/cart" className="text-link">Исправить корзину</ActionLink>}</aside></div></section>;
}

export function LivePaymentForm({ order }: { order: Order }) {
  const store = useStore(), client = useQueryClient(), storageKey = `lapki.payment.api.${store.user?.id}.${order.id}`;
  const saved = useRef<PendingPayment | null>(decodePendingPayment(sessionStorage.getItem(storageKey)));
  const key = useRef(saved.current?.key ?? crypto.randomUUID()), [unknown, setUnknown] = useState(!!saved.current), [checking, setChecking] = useState(false);
  const form = useForm<PaymentInput>({ defaultValues: { cardNumber: '', cvv: '', cardholderName: '' }, resolver: zodResolver(livePaymentSchema()), mode: 'onBlur' });
  const cacheOrder = (next: Order) => client.setQueryData(['order', store.user?.id, order.id, false], next);
  const clearPending = () => { sessionStorage.removeItem(storageKey); saved.current = null; key.current = crypto.randomUUID(); };
  useEffect(() => { if (order.paymentStatus !== 'UNPAID') sessionStorage.removeItem(storageKey); }, [order.paymentStatus, storageKey]);
  return <div className="panel payment-panel"><h2>Тестовая оплата</h2><p className="form-hint">Реального списания не будет. Используйте только карты из списка ниже.</p>{unknown ? <div data-testid="payment-unknown"><p className="notice">Ответ не получен. Сначала проверим результат оплаты.</p><Button testId="payment-recheck" className="primary-button" disabled={checking} onClick={async () => {
    setChecking(true);
    try {
      const current = await api.order(order.id); cacheOrder(current);
      if (current.paymentStatus === 'PAID') { clearPending(); form.reset(); store.notify('Оплата подтверждена'); }
      else if (current.paymentStatus !== 'UNPAID') clearPending();
      else if (current.payments.some((payment) => payment.status === 'DECLINED' && !saved.current?.previousPaymentIds.includes(payment.id))) clearPending();
      setUnknown(false); await store.refresh();
    } catch (failure) { store.report(failure); } finally { setChecking(false); }
  }}>Проверить оплату</Button></div> : <form noValidate data-testid="payment-form" onSubmit={form.handleSubmit(async (input) => {
    const pending = { key: key.current, previousPaymentIds: order.payments.map((payment) => payment.id) };
    sessionStorage.setItem(storageKey, encodePendingPayment(pending)); saved.current = pending;
    try { const paid = await api.payOrder(order, input, key.current); cacheOrder(paid); clearPending(); form.reset(); store.notify(paid.paymentStatus === 'PAID' ? 'Заказ оплачен' : 'Статус платежа обновлён'); log('order_paid', { resourceId: order.id, result: 'success' }); await store.refresh(); }
    catch (failure) {
      if (failure instanceof ServiceError && (failure.code === 'PAYMENT_STATUS_UNKNOWN' || failure.code === 'IDEMPOTENCY_KEY_REUSED')) setUnknown(true);
      else { clearPending(); if (failure instanceof ServiceError) failure.details.forEach((detail) => { if (detail.field && detail.field in input) form.setError(detail.field as keyof PaymentInput, { message: 'Проверьте значение поля' }); }); await store.refresh(); }
      store.report(failure);
    }
  })}>
    <Field label="Номер тестовой карты" testId="payment-card" required hint="16 цифр; пробелы допустимы." error={form.formState.errors.cardNumber?.message}><input data-testid="payment-card" placeholder="4242 4242 4242 4242" inputMode="numeric" autoComplete="off" maxLength={23} {...form.register('cardNumber')} /></Field>
    <div className="form-row"><Field label="Месяц" testId="payment-expiry-month" required error={form.formState.errors.expiryMonth?.message}><input data-testid="payment-expiry-month" placeholder="12" type="number" min={1} max={12} autoComplete="off" {...form.register('expiryMonth')} /></Field><Field label="Год" testId="payment-expiry-year" required error={form.formState.errors.expiryYear?.message}><input data-testid="payment-expiry-year" placeholder="2099" type="number" min={new Date().getFullYear()} max={2200} autoComplete="off" {...form.register('expiryYear')} /></Field></div>
    <Field label="CVV/CVC" testId="payment-cvv" required hint="3 или 4 цифры. Значение не сохраняется." error={form.formState.errors.cvv?.message}><input data-testid="payment-cvv" placeholder="123" type="password" inputMode="numeric" maxLength={4} autoComplete="off" {...form.register('cvv')} /></Field>
    <Field label="Имя владельца карты" testId="payment-cardholder" required error={form.formState.errors.cardholderName?.message}><input data-testid="payment-cardholder" placeholder="IVAN IVANOV" maxLength={100} autoComplete="off" {...form.register('cardholderName')} /></Field>
    <Button testId="payment-submit" type="submit" className="primary-button full-width" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Проверяем…' : `Оплатить ${money(order.total)}`}</Button>
  </form>}<details className="test-cards"><summary data-testid="payment-cards-help">Тестовые карты</summary><p>4242 4242 4242 4242 — успешно</p><p>4000 0000 0000 0002 — отказ</p><p>4000 0000 0000 9995 — недостаточно средств</p><p>Для теста: месяц 12, год 2099, CVV 123.</p></details></div>;
}
