import { test } from 'node:test';
import { strict as assert } from 'node:assert';
import { friendlyError, messages, ServiceError } from '../src/errors.ts';

// Snapshot of the existing backend's OpenAPI error examples, not invented UI codes.
const backendCodes = `ACCOUNT_ALREADY_CONFIRMED ACCOUNT_BLOCKED ACCOUNT_NOT_VERIFIED ADMIN_ACCOUNT_PROTECTED BAD_REQUEST CONFIRMATION_LINK_EXPIRED DEMO_ACCOUNT_PROTECTED EMAIL_ALREADY_EXISTS FORBIDDEN IDEMPOTENCY_KEY_REQUIRED IDEMPOTENCY_KEY_REUSED INSUFFICIENT_FUNDS INTERNAL_SERVER_ERROR INVALID_CONFIRMATION_LINK INVALID_CREDENTIALS INVALID_IDEMPOTENCY_KEY INVALID_RESET_LINK INVALID_ROLE_TRANSITION INVALID_STATUS_TRANSITION INVALID_TOKEN LAST_ADMIN_PROTECTED LOGIN_RATE_LIMITED ORDER_ACCESS_DENIED ORDER_ALREADY_PAID ORDER_NOT_DELETABLE ORDER_NOT_FOUND ORDER_NOT_PAID ORDER_NOT_PAYABLE ORDER_PAYMENT_EXPIRED PAYMENT_DECLINED PAYMENT_NOT_DELETABLE PAYMENT_NOT_FOUND PAYMENT_STATE_CONFLICT PET_HAS_ACTIVE_ORDER PET_HAS_ORDERS PET_NOT_AVAILABLE PET_NOT_FOUND PET_VERSION_CONFLICT PROFILE_INCOMPLETE RESET_LINK_ALREADY_USED RESET_LINK_EXPIRED RESET_STATE_CHANGED TOKEN_EXPIRED UNAUTHORIZED USER_ALREADY_EXISTS USER_HAS_ORDERS USER_NOT_FOUND USERNAME_ALREADY_EXISTS VALIDATION_ERROR`.split(' ');
test('every documented existing backend error has a Russian user-facing message', () => {
  for (const code of backendCodes) { assert.ok(messages[code], code); const message = friendlyError(new ServiceError(code)); assert.match(message.title, /[А-Яа-яЁё]/); assert.match(message.text, /[А-Яа-яЁё]/); }
});
test('confirmation problems suggest the corresponding recovery action', () => {
  assert.match(friendlyError(new ServiceError('CONFIRMATION_LINK_EXPIRED')).text, /новое письмо/);
  assert.match(friendlyError(new ServiceError('ACCOUNT_ALREADY_CONFIRMED')).text, /Войдите/);
  assert.match(friendlyError(new ServiceError('LOGIN_RATE_LIMITED')).text, /Подождите/);
  assert.equal(friendlyError(new ServiceError('UNKNOWN_SERVER_CODE')).title, messages.UNEXPECTED.title);
});
test('published commerce errors offer a Russian explanation without raw backend diagnostics', () => {
  const codes = 'IMAGE_REQUIRED IMAGE_TOO_LARGE INVALID_IMAGE_FORMAT INVALID_IMAGE ANIMATED_IMAGE_NOT_ALLOWED MEDIA_IN_USE MEDIA_NOT_FOUND MEDIA_STORAGE_UNAVAILABLE CATEGORY_VERSION_CONFLICT CATEGORY_KIND_CONFLICT CATEGORY_UNAVAILABLE CATEGORY_NOT_FOUND CATEGORY_ALREADY_EXISTS STOCK_ADJUSTMENT_REQUIRED INVALID_PUBLICATION_TRANSITION ORDER_VERSION_CONFLICT INVENTORY_STATE_CONFLICT PRODUCT_VERSION_CONFLICT PET_VERSION_CONFLICT PRICE_CHANGED INSUFFICIENT_STOCK CART_VERSION_CONFLICT PRODUCT_UNAVAILABLE TELEMETRY_RATE_LIMITED'.split(' ');
  for (const code of codes) { assert.ok(messages[code], code); assert.match(friendlyError(new ServiceError(code)).text, /[А-Яа-яЁё]/); }
});
