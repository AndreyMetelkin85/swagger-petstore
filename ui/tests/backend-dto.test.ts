import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { mapCategories, mapOrder, mapPayment, mapPet, mapUser, petDto, profilePayload } from '../src/backend-dto.ts';
import { decodePendingPayment, encodePendingPayment } from '../src/payment-state.ts';
import { legacyPetSchema, livePaymentSchema, liveProfileSchema } from '../src/validation.ts';
const id = '10000000-0000-4000-8000-000000000001', userId = '20000000-0000-4000-8000-000000000001';
const user = { id: userId, username: 'buyer', email: 'buyer@petstore.test', firstName: 'Анна', lastName: 'Иванова', phone: '+79001234567', address: { city: 'Москва', street: 'Лесная', house: '12', apartment: null, postalCode: '123456' }, userStatus: 'ACTIVE', role: 'USER' };
const pet = { id, name: 'Тедди', category: { id: '30000000-0000-4000-8000-000000000001', name: 'Dogs' }, photoUrls: ['https://example.com/pet.jpg'], tags: [], status: 'available', version: 3, price: '12000.50', currency: 'RUB' };
test('actual User DTO maps userStatus and nested house without leaking unexpected fields', () => {
  const mapped = mapUser({ ...user, password: 'never-copy' });
  assert.equal(mapped.status, 'ACTIVE'); assert.equal(mapped.profile.name, 'Анна Иванова'); assert.equal(mapped.profile.building, '12'); assert.equal(mapped.profile.apartment, '');
  assert.equal(JSON.stringify(mapped).includes('never-copy'), false);
  const body = profilePayload(mapped.profile); assert.equal(body.address.house, '12'); assert.equal('name' in body, false); assert.equal('building' in body.address, false);
});
test('pending accounts with missing optional profiles remain valid; invalid roles fail closed', () => {
  const mapped = mapUser({ ...user, firstName: null, lastName: null, phone: null, address: null, userStatus: 'PENDING' });
  assert.equal(mapped.profile.firstName, ''); assert.equal(mapped.profile.postalCode, ''); assert.equal(mapped.status, 'PENDING');
  assert.throws(() => mapUser({ ...user, role: 'OWNER' }), /API_CONTRACT_MISMATCH/);
});
test('legacy photos remain URLs, never invented media IDs; category extraction deduplicates', () => {
  const mapped = mapPet(pet); assert.equal(mapped.price, 12000.5); assert.equal(mapped.images[0].url, pet.photoUrls[0]); assert.equal(mapped.images[0].mediaId, undefined); assert.deepEqual(mapped.animalTypes, ['dog']);
  assert.equal(mapCategories([petDto.parse(pet), petDto.parse(pet)]).length, 1);
});
test('server totals, lowercase lifecycle and delivery snapshots map to UI independently of current price', () => {
  const mapped = mapOrder({ id, userId, petId: id, quantity: 1, status: 'placed', createdAt: '2026-10-07T00:00:00Z', unitPrice: '1000.25', totalAmount: '1000.25', currency: 'RUB', paymentStatus: 'UNPAID', paymentExpiresAt: '2026-10-07T00:15:00Z', deliveryDetails: { firstName: 'Анна', lastName: 'Иванова', phone: user.phone, address: user.address } }, mapPet(pet));
  assert.equal(mapped.status, 'PLACED'); assert.equal(mapped.total, 1000.25); assert.equal(mapped.lines[0].price, 1000.25); assert.equal(mapped.delivery?.building, '12'); assert.equal(mapped.estimated, false);
});
test('drafts without a server price are marked as estimates; safe payment summaries contain last4 only', () => {
  const draft = mapOrder({ id, userId, petId: id, quantity: 1, status: 'draft', createdAt: '2026-10-07T00:00:00Z', unitPrice: null, totalAmount: null, currency: 'RUB', paymentStatus: 'NOT_STARTED', paymentExpiresAt: null, deliveryDetails: null }, mapPet(pet));
  assert.equal(draft.estimated, true); assert.equal(draft.paymentStatus, 'NOT_STARTED');
  const payment = mapPayment({ id, orderId: id, amount: '1000.25', currency: 'RUB', status: 'SUCCEEDED', cardBrand: 'VISA', cardLast4: '4242', createdAt: '2026-10-07T00:00:00Z', updatedAt: '2026-10-07T00:00:00Z', cvv: '123', cardNumber: '4242424242424242' });
  assert.equal(payment.last4, '4242'); assert.equal(JSON.stringify(payment).includes('4242424242424242'), false); assert.equal('cvv' in payment, false);
});
test('payment validation covers every required legacy field and expiry boundaries', () => {
  const schema = livePaymentSchema(new Date('2026-10-07T00:00:00Z'));
  const body = { cardNumber: '4242 4242 4242 4242', expiryMonth: '10', expiryYear: '2026', cvv: '001', cardholderName: ' IVAN IVANOV ' };
  const parsed = schema.parse(body); assert.equal(parsed.cardNumber, '4242424242424242'); assert.equal(parsed.expiryMonth, 10); assert.equal(parsed.cvv, '001');
  for (const invalid of [{ expiryMonth: 9 }, { expiryMonth: 13 }, { expiryYear: 2025 }, { expiryYear: 2201 }, { cvv: '12' }, { cvv: 'abc' }, { cardholderName: ' ' }]) assert.equal(schema.safeParse({ ...body, ...invalid }).success, false);
});
test('live profile requires independent first and last names; legacy pet URLs remain constrained', () => {
  const profile = mapUser(user).profile; assert.equal(liveProfileSchema.safeParse(profile).success, true); assert.equal(liveProfileSchema.safeParse({ ...profile, lastName: '' }).success, false);
  const values = { name: 'Мика', price: '1200,50', status: 'available', photoUrls: 'https://example.com/pet.png' };
  assert.equal(legacyPetSchema.parse(values).price, 1200.5);
  for (const photoUrls of ['javascript:alert(1)', 'https://user:password@example.com/photo.png', 'not-a-url']) assert.equal(legacyPetSchema.safeParse({ ...values, photoUrls }).success, false);
});
test('uncertain payment metadata survives reload without storing card, CVV or cardholder', () => {
  const encoded = encodePendingPayment({ key: id, previousPaymentIds: [userId], cardNumber: '4242424242424242', cvv: '123', cardholderName: 'PRIVATE' } as never);
  assert.deepEqual(decodePendingPayment(encoded), { key: id, previousPaymentIds: [userId] });
  for (const value of ['4242424242424242', 'PRIVATE', 'cvv']) assert.equal(encoded.includes(value), false);
  for (const raw of ['invalid', '{}', 'null', '{"key":"bad","previousPaymentIds":[]}', `{"key":"${id}","previousPaymentIds":null}`]) assert.equal(decodePendingPayment(raw), null);
});
