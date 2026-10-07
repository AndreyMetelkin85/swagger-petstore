import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { cartTotal, parseCart, setQuantity } from '../src/domain.ts';

test('a pet and goods share one cart and total; pets cannot be duplicated', () => {
  let cart = setQuantity([], 'pet-dog', 1);
  cart = setQuantity(cart, 'food-dog', 2);
  assert.equal(cartTotal(cart), 27980);
  assert.throws(() => setQuantity(cart, 'pet-dog', 2), /INSUFFICIENT_STOCK/);
  assert.deepEqual(setQuantity(cart, 'food-dog', 0), [{ id: 'pet-dog', quantity: 1 }]);
});

test('stock errors do not alter an existing cart', () => {
  const cart = [{ id: 'bowl', quantity: 4 }];
  assert.throws(() => setQuantity(cart, 'bowl', 5), /INSUFFICIENT_STOCK/);
  assert.deepEqual(cart, [{ id: 'bowl', quantity: 4 }]);
  assert.throws(() => setQuantity(cart, 'bowl', -1), /INVALID_QUANTITY/);
});

test('untrusted stored cart is sanitized and capped at available stock', () => {
  assert.deepEqual(parseCart([{ id: 'bowl', quantity: 200 }, { id: 'pet-cat', quantity: 5 }, { id: 'unknown', quantity: 1 }, { id: 'food-cat', quantity: -1 }]), [{ id: 'bowl', quantity: 4 }, { id: 'pet-cat', quantity: 1 }]);
  assert.deepEqual(parseCart({ id: 'bowl' }), []);
});
