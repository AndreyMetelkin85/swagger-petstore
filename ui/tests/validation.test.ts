import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { authSchema, categorySchema, demoCardSchema, forgotPasswordSchema, itemSchema, normalizePhone, numberInput, passwordResetSchema, profileSchema, registrationSchema, stockAdjustmentSchema, validBirthDate } from '../src/validation.ts';

const profile = { name: 'Анна Иванова', phone: '+7 (900) 123-45-67', city: 'Москва', street: 'Лесная', building: '12, корпус 2', apartment: '', postalCode: '123456' };

test('email is trimmed; invalid addresses never pass login or recovery validation', () => {
  assert.equal(authSchema.parse({ email: '  buyer@example.com  ', password: 'Secret6' }).email, 'buyer@example.com');
  for (const email of ['', ' ', 'no-at', 'a@', 'a b@example.com']) {
    assert.equal(forgotPasswordSchema.safeParse({ email }).success, false, email);
  }
});
test('registration follows the username contract and trims optional name', () => {
  const values = { username: 'pet_lover', name: ' Анна ', email: 'buyer@example.com', password: 'Secret6' };
  assert.equal(registrationSchema.parse(values).name, 'Анна');
  for (const username of ['ab', 'я_люблю_котиков', 'bad user', 'a'.repeat(31), '   ']) assert.equal(registrationSchema.safeParse({ ...values, username }).success, false);
  assert.equal(registrationSchema.safeParse({ ...values, username: 'qa.user-1' }).success, true);
});
test('password boundaries are enforced without changing intentional spaces', () => {
  for (const password of ['', 'short', '      ', 'a'.repeat(101)]) assert.equal(passwordResetSchema.safeParse({ password }).success, false);
  assert.equal(passwordResetSchema.parse({ password: ' Secret6 ' }).password, ' Secret6 ');
  assert.equal(passwordResetSchema.safeParse({ password: '123456' }).success, true);
});
test('phone validation counts digits rather than accepting separators as digits', () => {
  assert.equal(profileSchema.safeParse(profile).success, true);
  assert.equal(normalizePhone(profile.phone), '+79001234567');
  for (const phone of ['+7          ', '+7----------', '+7900123456', '+790012345678', '+7(abc)1234567', '89001234567']) assert.equal(profileSchema.safeParse({ ...profile, phone }).success, false, phone);
});
test('address constraints reject whitespace and oversize fields; apartment remains optional', () => {
  for (const field of ['name', 'city', 'street', 'building', 'postalCode']) assert.equal(profileSchema.safeParse({ ...profile, [field]: '  ' }).success, false, field);
  for (const postalCode of ['12345', '1234567', '12а456']) assert.equal(profileSchema.safeParse({ ...profile, postalCode }).success, false);
  for (const [field, limit] of [['city', 100], ['street', 150], ['building', 30], ['apartment', 30]] as const) assert.equal(profileSchema.safeParse({ ...profile, [field]: 'x'.repeat(limit + 1) }).success, false);
  assert.equal(profileSchema.parse({ ...profile, city: ' Москва ', apartment: ' ' }).apartment, '');
});
test('blank numbers are distinct from zero; decimal commas represent rubles correctly', () => {
  for (const value of ['', ' ', '12 рублей', '1e3', '0x10', null]) assert.equal(Number.isNaN(numberInput(value)), true);
  assert.equal(numberInput('0'), 0);
  assert.equal(numberInput(' 12,50 '), 12.5);
  const price = itemSchema.pick({ price: true });
  assert.equal(price.parse({ price: '12,50' }).price, 12.5);
  for (const value of ['', '-1', '12.345', 'Infinity']) assert.equal(price.safeParse({ price: value }).success, false);
});
test('stock and feed weight reject fractional, empty and negative quantities', () => {
  const quantity = itemSchema.pick({ stock: true, netWeightGrams: true });
  assert.equal(quantity.safeParse({ stock: 0, netWeightGrams: 2000 }).success, true);
  for (const value of ['', -1, 1.5]) {
    assert.equal(quantity.safeParse({ stock: value, netWeightGrams: 2000 }).success, false);
    assert.equal(quantity.safeParse({ stock: 1, netWeightGrams: value }).success, false);
  }
});
test('birth dates must exist on the calendar and cannot be in the future', () => {
  assert.equal(validBirthDate('', '2026-10-06'), true);
  assert.equal(validBirthDate('2024-02-29', '2026-10-06'), true);
  for (const value of ['2025-02-29', '2026-04-31', '2099-01-01', '06.10.2026']) assert.equal(validBirthDate(value, '2026-10-06'), false);
});
test('stock adjustments require a meaningful reason and preserve existing reservations', () => {
  const schema = stockAdjustmentSchema(3);
  assert.equal(schema.parse({ quantity: '4', reason: ' Поставка ' }).reason, 'Поставка');
  for (const quantity of ['', 2, -1, 3.5]) assert.equal(schema.safeParse({ quantity, reason: 'Поставка' }).success, false);
  for (const reason of ['', '  ', 'x'.repeat(301)]) assert.equal(schema.safeParse({ quantity: 4, reason }).success, false);
});
test('category names cannot be empty after trimming', () => {
  assert.equal(categorySchema.parse({ name: ' Корма ', kind: 'product' }).name, 'Корма');
  for (const name of ['', '   ', 'x'.repeat(81)]) assert.equal(categorySchema.safeParse({ name, kind: 'product' }).success, false);
});
test('demo cards accept the supported scenarios and reject other input', () => {
  assert.equal(demoCardSchema.parse('4242 4242 4242 4242'), '4242424242424242');
  for (const card of ['4000 0000 0000 0002', '4000 0000 0000 9995']) assert.equal(demoCardSchema.safeParse(card).success, true);
  for (const card of ['', '123', '4242abcd42424242', '1111111111111111']) assert.equal(demoCardSchema.safeParse(card).success, false);
});
