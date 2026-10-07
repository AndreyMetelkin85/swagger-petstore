import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { items } from '../src/domain.ts';
import { emptyProfile, type State, type Item } from '../src/models.ts';
import { advanceOrder, cancelOrder, cartAmount, createDraft, expireOrders, idempotent, mergeCartLines, payOrder, placeOrder, remainingGuest } from '../src/commerce.ts';
import { friendlyError, ServiceError } from '../src/errors.ts';
import { log, sanitizeContext, setLogSink } from '../src/logger.ts';

function fixture() {
  const catalog = items.map((item): Item => ({ ...item, version: 1, sku: item.id, categoryId: 'category', brand: 'Лапки', productType: 'FEED', feedForm: 'DRY', lifeStages: ['ADULT'], netWeightGrams: 1000, ingredients: '', publicationStatus: 'PUBLISHED', images: [{ mediaId: 'image', alt: '' }], reserved: 0, status: 'available', breed: '', sex: '', birthDate: '' }));
  const user = { id: 'buyer', email: 'buyer@demo.test', role: 'USER' as const, status: 'ACTIVE' as const, profile: { ...emptyProfile, name: 'Демо', phone: '+79000000000', city: 'Москва', street: 'Учебная', building: '1', postalCode: '101000' }, salt: 'salt', passwordHash: 'hash' };
  const state: State = { schema: 3, items: catalog, users: [user], carts: { buyer: { version: 1, lines: [{ id: 'food-dog', quantity: 2 }, { id: 'pet-dog', quantity: 1 }] } }, categories: [], orders: [], media: [], sessions: [], confirmations: [], idempotency: {}, stockHistory: [], scenario: 'NORMAL' };
  return { state, user };
}
test('merge preserves supply quantities and unavailable positions, deduplicates pets', () => {
  const { state } = fixture();
  assert.deepEqual(mergeCartLines([{ id: 'food-dog', quantity: 7 }, { id: 'pet-dog', quantity: 1 }], [{ id: 'food-dog', quantity: 5 }, { id: 'pet-dog', quantity: 1 }, { id: 'removed', quantity: 3 }], state.items), [{ id: 'food-dog', kind: 'product', quantity: 12 }, { id: 'pet-dog', kind: 'pet', quantity: 1 }, { id: 'removed', quantity: 3 }]);
});
test('acknowledging an old merge cannot discard newer guest additions', () => {
  assert.deepEqual(remainingGuest([{ id: 'food-dog', quantity: 5 }, { id: 'bowl', quantity: 1 }], [{ id: 'food-dog', quantity: 2 }]), [{ id: 'food-dog', quantity: 3 }, { id: 'bowl', quantity: 1 }]);
});
test('failed placement reserves nothing; same key can succeed after availability is fixed', () => {
  const { state, user } = fixture(), draft = createDraft(state, user, state.carts.buyer), originalCart = structuredClone(state.carts.buyer);
  state.items[0].stock = 0;
  assert.throws(() => idempotent(state, 'place', 'key-12345678', { expectedTotal: draft.total }, () => placeOrder(state, user, draft, draft.total)), /INSUFFICIENT_STOCK/);
  assert.equal(state.items.find((item) => item.kind === 'pet')!.reserved, 0); assert.equal(draft.status, 'DRAFT'); assert.deepEqual(state.carts.buyer, originalCart); assert.equal(Object.keys(state.idempotency).length, 0);
  state.items[0].stock = 8;
  idempotent(state, 'place', 'key-12345678', { expectedTotal: draft.total }, () => placeOrder(state, user, draft, draft.total));
  assert.equal(draft.status, 'PLACED'); assert.equal(state.items[0].reserved, 2); assert.equal(state.carts.buyer.lines.length, 0);
});
test('idempotency replays saved results and rejects changed parameters', () => {
  const { state, user } = fixture();
  const first = idempotent(state, 'draft', 'draft-12345678', { version: 1 }, () => createDraft(state, user, state.carts.buyer));
  const replay = idempotent(state, 'draft', 'draft-12345678', { version: 1 }, () => { throw new Error('must not execute'); });
  assert.deepEqual(replay, first); assert.equal(state.orders.length, 1);
  assert.throws(() => idempotent(state, 'draft', 'draft-12345678', { version: 2 }, () => first), /IDEMPOTENCY_KEY_REUSED/);
});
test('declined attempts and successful payment are saved once; cancellation refunds once', () => {
  const { state, user } = fixture(), order = createDraft(state, user, state.carts.buyer); placeOrder(state, user, order, order.total);
  idempotent(state, 'pay', 'decline-12345678', { mode: 'declined' }, () => payOrder(state, order, 'declined', '0002'));
  idempotent(state, 'pay', 'decline-12345678', { mode: 'declined' }, () => payOrder(state, order, 'declined', '0002'));
  assert.equal(order.payments.length, 1); assert.equal(state.items[0].stock, 8); assert.equal(order.paymentStatus, 'UNPAID');
  idempotent(state, 'pay', 'success-12345678', { mode: 'success' }, () => payOrder(state, order, 'success', '4242'));
  idempotent(state, 'pay', 'success-12345678', { mode: 'success' }, () => payOrder(state, order, 'success', '4242'));
  assert.equal(order.payments.length, 2); assert.equal(state.items[0].stock, 6); assert.equal(state.items[0].reserved, 0); assert.equal(state.items.find((item) => item.id === 'pet-dog')!.status, 'reserved');
  cancelOrder(state, order); cancelOrder(state, order); assert.equal(state.items[0].stock, 8); assert.equal(order.payments.filter((attempt) => attempt.status === 'REFUNDED').length, 1);
});
test('unpaid expiry releases the complete order; paid pets remain reserved until delivered', () => {
  const { state, user } = fixture(), order = createDraft(state, user, state.carts.buyer); placeOrder(state, user, order, order.total); order.reserveUntil = new Date(Date.now() - 1).toISOString(); expireOrders(state); expireOrders(state); assert.equal(order.status, 'EXPIRED'); assert.equal(state.items[0].reserved, 0); assert.equal(state.items.find((item) => item.id === 'pet-dog')!.status, 'available');
  state.carts.buyer = { version: 3, lines: [{ id: 'pet-dog', quantity: 1 }] }; const paid = createDraft(state, user, state.carts.buyer); placeOrder(state, user, paid, paid.total); payOrder(state, paid, 'success', '4242'); expireOrders(state); assert.equal(state.items.find((item) => item.id === 'pet-dog')!.status, 'reserved'); advanceOrder(state, paid, 'APPROVED'); advanceOrder(state, paid, 'SHIPPED'); advanceOrder(state, paid, 'DELIVERED'); assert.equal(state.items.find((item) => item.id === 'pet-dog')!.status, 'sold');
});
test('friendly errors and logger do not expose raw diagnostics or private data', () => {
  assert.equal(JSON.stringify(friendlyError(new Error('private email password card'))).includes('private email'), false);
  assert.equal(friendlyError(new ServiceError('PRICE_CHANGED')).title, 'Цена изменилась');
  assert.deepEqual(sanitizeContext({ email: 'private@example.com', password: 'secret', token: 'secret', address: 'private', cardNumber: '4242424242424242', filename: 'private.png', details: { private: true }, code: 'PAYMENT_DECLINED', quantity: 2, requestId: '40000000-0000-4000-8000-000000000001' }), { code: 'PAYMENT_DECLINED', quantity: 2, requestId: '40000000-0000-4000-8000-000000000001' });
  assert.equal(sanitizeContext({ code: 'private@example.com' }).code, 'UNEXPECTED');
});
test('fractional ruble prices do not cause a false PRICE_CHANGED conflict', () => {
  const { state, user } = fixture(); state.items[0].price = .1; state.carts.buyer.lines = [{ id: 'food-dog', quantity: 3 }];
  const total = cartAmount(state.carts.buyer.lines, state.items); assert.equal(total, .3);
  const order = createDraft(state, user, state.carts.buyer); placeOrder(state, user, order, total); assert.equal(order.total, .3);
});
test('an unused placement key accepts the updated total after explicit price confirmation', () => {
  const { state, user } = fixture(), order = createDraft(state, user, state.carts.buyer); state.items[0].price += 100;
  assert.throws(() => idempotent(state, 'place', 'price-12345678', { expectedTotal: order.total }, () => placeOrder(state, user, order, order.total)), /PRICE_CHANGED/);
  const confirmed = cartAmount(state.carts.buyer.lines, state.items);
  idempotent(state, 'place', 'price-12345678', { expectedTotal: confirmed }, () => placeOrder(state, user, order, confirmed));
  assert.equal(order.total, confirmed); assert.equal(order.status, 'PLACED');
});
test('failed telemetry delivery neither rejects an action nor recursively logs its failure', async () => {
  let deliveries = 0;
  setLogSink(async () => { deliveries++; throw new Error('delivery failure'); }); log('telemetry_test', { code: 'TEST_EVENT' });
  await new Promise((resolve) => setTimeout(resolve, 1150)); assert.equal(deliveries, 1); setLogSink(async () => {});
});
