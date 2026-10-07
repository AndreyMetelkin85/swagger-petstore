import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { cardPayload, cartPayload, mapCard, mapCommerceCart, mapCommerceOrder } from '../src/commerce-dto.ts';
import { commerceItemSchema } from '../src/validation.ts';
import { decodePendingCheckout } from '../src/checkout-state.ts';
import { mergeCartLines } from '../src/commerce.ts';

const id = '10000000-0000-4000-8000-000000000001', mediaId = '40000000-0000-4000-8000-000000000001';
const image = { mediaId, alt: 'Упаковка', position: 0, isCover: true, imageUrl: `/api/v3/media/${mediaId}/image`, thumbUrl: `/api/v3/media/${mediaId}/thumb` };
const product = { id, kind: 'product', name: 'Корм', description: 'С индейкой', categoryId: id, price: '1490.25', currency: 'RUB', publicationStatus: 'PUBLISHED', version: 5, images: [image], sku: 'DOG-1', brand: 'Поставщик', productType: 'FEED', animalTypes: ['dog'], feedForm: 'DRY', lifeStages: ['ADULT'], netWeightGrams: 2000, ingredients: 'Индейка, рис', stock: 10, reserved: 3, availableQuantity: 7 };
test('commerce cards retain stock/reservations and cover IDs without trusting storage URLs', () => {
  const item = mapCard(product); assert.equal(item.price, 1490.25); assert.equal(item.stock - item.reserved, 7); assert.deepEqual(item.images, [{ mediaId, alt: 'Упаковка' }]);
  assert.throws(() => mapCard({ ...product, currency: 'USD' }), /API_CONTRACT_MISMATCH/);
});
test('card commands exclude client publication, reserved counts and update stock', () => {
  const item = mapCard(product), command = cardPayload(item, false);
  for (const field of ['id', 'publicationStatus', 'reserved', 'stock', 'availableQuantity', 'subtitle', 'visual']) assert.equal(field in command, false);
  assert.equal(command.version, 5); assert.deepEqual(command.images, [{ mediaId, alt: 'Упаковка', isCover: true }]);
  assert.equal((cardPayload(item, true) as { stock: number }).stock, 10);
});
test('cart read retains unavailable identities and changed quotes; writes contain only accepted fields', () => {
  const cart = mapCommerceCart({ version: 3, lines: [{ id, kind: 'product', quantity: 2, name: 'Корм', price: '1500', quotedPrice: '1490.25', currency: 'RUB', available: false, priceChanged: true, reason: 'INSUFFICIENT_STOCK', images: [image] }] });
  assert.equal(cart.lines[0].available, false); assert.equal(cart.lines[0].priceChanged, true);
  assert.deepEqual(cartPayload(cart), { version: 3, lines: [{ id, kind: 'product', quantity: 2 }] });
  assert.throws(() => cartPayload({ version: 1, lines: [{ id, quantity: 1 }] }), /API_CONTRACT_MISMATCH/);
});
test('mixed drafts use immutable line quotes while placed orders use the server total', () => {
  const dto = { id, userId: id, status: 'draft', paymentStatus: 'NOT_STARTED', version: 0, cartVersion: 3, createdAt: '2026-10-07T00:00:00Z', paymentExpiresAt: null, currency: 'RUB', total: null, delivery: null, lines: [{ itemId: id, kind: 'product', name: 'Снимок имени', sku: 'DOG-1', quantity: 2, price: '1490.25', images: [image] }] };
  const draft = mapCommerceOrder(dto); assert.equal(draft.total, 2980.5); assert.equal(draft.estimated, true);
  const placed = mapCommerceOrder({ ...dto, status: 'placed', paymentStatus: 'UNPAID', total: '2980.50', version: 1 }); assert.equal(placed.status, 'PLACED'); assert.equal(placed.estimated, false); assert.equal(placed.version, 1);
});
test('draft validation checks supplied values without requiring publication fields', () => {
  const item = mapCard(product); assert.equal(commerceItemSchema.safeParse(item).success, true);
  for (const patch of [{ price: -1 }, { sku: 'НЕ-КОД' }, { sku: 'A'.repeat(65) }, { lifeStages: ['ALL','ADULT'] }, { netWeightGrams: -1 }, { stock: 1000001 }]) assert.equal(commerceItemSchema.safeParse({ ...item, ...patch }).success, false);
  assert.equal(commerceItemSchema.safeParse({ ...item, name: 'Draft only', price: '', sku: '', categoryId: '', brand: '', feedForm: '', lifeStages: [], netWeightGrams: '', ingredients: '', images: [] }).success, true);
});

test('nullable server drafts map to empty form values and serialize without invented price or SKU', () => {
  const item = mapCard({ ...product, publicationStatus: 'DRAFT', price: null, sku: null, productType: null });
  const body = cardPayload(item, false);
  assert.equal(body.price, null); assert.equal((body as {sku: null}).sku, null);
});
test('pending checkout retains retry identity and version without persisting profile or payment fields', () => {
  const result = decodePendingCheckout(JSON.stringify({ key: id, cartVersion: 4, placeKey: mediaId, email: 'private@example.com', cvv: '123' }));
  assert.deepEqual(result, { key: id, cartVersion: 4, placeKey: mediaId }); assert.equal(decodePendingCheckout('{broken'), null); assert.equal(decodePendingCheckout(JSON.stringify({ key: id, cartVersion: 0, placeKey: mediaId })), null);
});
test('merge keeps the kind of an unpublished pet and never doubles its quantity', () => {
  assert.deepEqual(mergeCartLines([{ id, kind: 'pet', quantity: 1 }], [{ id, kind: 'pet', quantity: 1 }], []), [{ id, kind: 'pet', quantity: 1 }]);
});
