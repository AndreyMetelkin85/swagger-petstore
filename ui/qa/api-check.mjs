import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { strict as assert } from 'node:assert';
import { mkdir, writeFile } from 'node:fs/promises';
import { assertTestIdContract } from './assert-testid-contract.mjs';
const { chromium } = createRequire(import.meta.url)(process.env.LAPKI_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.LAPKI_PREVIEW_URL || 'http://127.0.0.1:8089';
const mail = process.env.LAPKI_MAIL_URL || 'http://127.0.0.1:18025';
const browser = await chromium.launch({ channel: process.env.LAPKI_BROWSER_CHANNEL === 'bundled' ? undefined : process.env.LAPKI_BROWSER_CHANNEL || 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'ru-RU', timezoneId: 'Europe/Moscow', reducedMotion: 'reduce' });
const page = await context.newPage(); page.setDefaultTimeout(20000);
const errors = [], logs = [], requested = [], results = [], pets = [], orders = [], messages = [], products = [], categories = [], mediaIds = [];
let userId, adminToken;
page.on('pageerror', (error) => errors.push(error.message));
page.on('console', (message) => { if (message.type() === 'info') logs.push(message.text()); });
page.on('request', (request) => requested.push({ path: new URL(request.url()).pathname, method: request.method() }));
page.on('dialog', (dialog) => dialog.accept());
await mkdir('qa/screenshots', { recursive: true });
const marker = 'api' + Date.now(), email = marker + '@petstore.test', password = 'ApiInitial_' + marker + '!';
const newPassword = 'ApiReset_' + marker + '!';
async function goto(path) { await page.goto(base + path); await page.getByTestId('nav-home').waitFor(); }
async function api(path, method = 'GET', body, bearer, key) {
  const current = bearer ?? await page.evaluate(() => sessionStorage.getItem('lapki.session.api.v1'));
  const response = await context.request.fetch(base + '/api/v3' + path, { method, headers: { ...(current ? { Authorization: `Bearer ${current}` } : {}), ...(key ? { 'Idempotency-Key': key } : {}) }, data: body });
  return { status: response.status(), data: response.status() === 204 ? null : await response.json() };
}
async function signIn(address, secret, next = '/account') { await goto('/login?next=' + encodeURIComponent(next)); await page.getByTestId('login-email').fill(address); await page.getByTestId('login-password').fill(secret); await page.getByTestId('login-submit').click(); await page.waitForURL(base + next); }
async function closeError(text) { await page.getByTestId('error-dialog').waitFor(); if (text) assert.match(await page.getByTestId('error-dialog').textContent(), text); await page.getByTestId('error-dismiss').click(); }
async function audit() { await assertTestIdContract(page); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false); }
const named = (list, row, title, name) => page.getByTestId(list).getByTestId(row).filter({ has: page.getByTestId(title).filter({ hasText: name }) });
const pass = (name) => { results.push(name); console.log('PASS ' + name); };
async function letter(skip = []) {
  const boxes = await (await context.request.get(mail + '/api/Mailboxes')).json();
  const selected = boxes.find((box) => box.name === 'Tests') ?? boxes.find((box) => box.name === 'Default');
  const mailboxQuery = selected ? '&mailboxName=' + encodeURIComponent(selected.name) : '';

  for (let attempt = 0; attempt < 50; attempt++) {
    const response = await context.request.get(mail + '/api/Messages?searchTerms=' + encodeURIComponent(email) + '&pageSize=100' + mailboxQuery);
    if (response.ok()) {
      const body = await response.json(), message = body.results?.find((item) => !skip.includes(item.id));
      if (message) { messages.push(message.id); const content = await (await context.request.get(mail + `/api/Messages/${message.id}/plaintext`)).text(); const link = content.match(/https?:\/\/[^\s<>"\)]+/)?.[0]; assert.ok(link, 'mail has an action link'); assert.equal(new URL(link).origin, base); assert.equal(content.includes(password), false); return { id: message.id, link }; }
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('SMTP message not received');
}
async function card(number) {
  await page.getByTestId('payment-card').fill(number); await page.getByTestId('payment-expiry-month').fill('12'); await page.getByTestId('payment-expiry-year').fill('2099'); await page.getByTestId('payment-cvv').fill('123'); await page.getByTestId('payment-cardholder').fill('API TEST USER');
}
async function selectItem(path, name) { await goto(path); await page.getByTestId('catalog-search').fill(name); await named('catalog-items', 'catalog-item-card', 'catalog-item-name', name).getByTestId('catalog-item-add').click(); await page.getByTestId('cart-count').waitFor(); }
async function selectPet(name) { await selectItem('/pets',name); }
async function checkout() { await goto('/checkout'); await page.getByTestId('checkout-submit').click(); await page.waitForURL(/\/account\/orders\/[0-9a-f-]+$/); const id = page.url().split('/').at(-1); orders.push(id); await page.getByTestId('payment-card').waitFor(); return id; }
try {
  await goto('/'); const contract = await api('/openapi.json'); assert.equal(contract.status, 200); assert.ok(contract.data.paths['/auth/password/reset']); assert.equal(await page.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length), 0); await audit();
  await goto('/catalog'); await page.getByTestId('catalog-search').waitFor();
  pass('API mode uses the published contract, has no MSW and connects the published commerce endpoints');

  await goto('/register'); await page.getByTestId('registration-username').fill(marker); await page.getByTestId('auth-name').fill('Анна'); await page.getByTestId('login-email').fill(email); await page.getByTestId('login-password').fill(password);
  const registered = page.waitForResponse((response) => response.url().endsWith('/auth/register') && response.request().method() === 'POST'); await page.getByTestId('login-submit').click(); const response = await registered; assert.equal(response.status(), 201); userId = (await response.json()).user.id;
  await page.waitForURL('**/register/verify'); await page.getByTestId('mail-inbox').waitFor(); const first = await letter();
  await page.getByTestId('registration-resend').click(); await page.getByTestId('registration-sent-again').waitFor(); const second = await letter([first.id]);
  const old = new URL(first.link); assert.equal((await api(`/auth/confirm/${userId}?code=${old.searchParams.get('code')}`)).status, 400);
  await page.goto(second.link); await page.waitForURL('**/register/complete'); await audit();
  pass('real SMTP registration, resend, invalidated old link and automatic frontend confirmation');

  await page.getByTestId('confirm-login').click(); await page.getByTestId('login-password').fill(password); await page.getByTestId('login-submit').click(); await page.waitForURL('**/account');
  const buyerToken = await page.evaluate(() => sessionStorage.getItem('lapki.session.api.v1')); assert.equal(buyerToken.split('.').length, 3); assert.equal(await page.getByTestId('profile-first-name').inputValue(), 'Анна');
  for (const [field, value] of Object.entries({ 'first-name': 'Анна', 'last-name': 'Иванова', phone: '+7 (900) 123-45-67', city: 'Москва', street: 'Лесная', building: '12', apartment: '24', 'postal-code': '123456' })) await page.getByTestId('profile-' + field).fill(value);
  const profile = page.waitForResponse((item) => item.url().endsWith('/user/me') && item.request().method() === 'PUT'); await page.getByTestId('profile-submit').click(); const payload = (await profile).request().postDataJSON(); assert.equal(payload.address.house, '12'); assert.equal(payload.lastName, 'Иванова'); assert.equal('name' in payload, false); await page.reload(); await page.getByTestId('profile-last-name').waitFor(); assert.equal(await page.getByTestId('profile-last-name').inputValue(), 'Иванова'); await audit();
  await goto('/admin'); await page.getByRole('heading', { name: 'Недостаточно прав' }).waitFor(); assert.equal((await api('/users')).status, 403);
  pass('real JWT, nested delivery profile persistence and USER access restrictions');

  await signIn('admin@example.com', 'admin123', '/admin'); adminToken = await page.evaluate(() => sessionStorage.getItem('lapki.session.api.v1'));
  await goto('/admin/products/new'); await page.getByTestId('admin-item-name').fill(marker + 'partial');
  await page.getByTestId('admin-item-price').fill(''); await page.getByTestId('admin-item-net-weight-grams').fill('');
  await page.getByTestId('admin-item-save-draft').click(); await page.waitForURL(/\/admin\/products\/[0-9a-f-]+$/);
  const partialId = page.url().split('/').at(-1); products.push(partialId);
  const partial = (await api('/admin/products/' + partialId)).data;
  assert.equal(partial.price, null); assert.equal(partial.sku, null); assert.equal(partial.publicationStatus, 'DRAFT');
  await page.reload(); await page.getByTestId('admin-item-sku').waitFor(); assert.equal(await page.getByTestId('admin-item-sku').inputValue(), '');
  await page.getByTestId('admin-item-publish').click(); await closeError();
  assert.equal((await api('/admin/products/' + partialId)).data.publicationStatus, 'DRAFT');
  pass('name-only nullable draft survives reload and cannot be published incomplete');
  for (const kind of ['product', 'pet']) {
    await goto('/admin/categories'); await page.getByTestId('admin-category-create').click(); await page.getByTestId('admin-category-name').fill(marker + kind); await page.getByTestId('admin-category-kind').selectOption(kind);
    const created = page.waitForResponse((response) => response.url().endsWith('/admin/catalog/categories') && response.request().method() === 'POST');
    await page.getByTestId('admin-category-submit').click(); const category = await (await created).json(); categories.push(category); await page.getByTestId('category-dialog').waitFor({ state: 'hidden' });
  }
  const imagePath = fileURLToPath(new URL('../public/images/pets-hero.png', import.meta.url));
  for (let index = 0; index < 2; index++) {
    await goto('/admin/pets/new'); await page.getByTestId('admin-item-name').fill(marker + 'pet' + index); await page.getByTestId('admin-item-description').fill('Описание питомца для интеграционной проверки.'); await page.getByTestId('admin-item-price').fill('1000,25'); await page.getByTestId('admin-item-category-id').selectOption(categories.find((value) => value.kind === 'pet').id);
    await page.getByTestId('media-source').selectOption('DEMO'); await page.getByTestId('media-note').fill('Каталог для учебной проверки');
    await page.getByTestId('media-upload-input').setInputFiles(imagePath); await page.getByTestId('media-asset').waitFor(); mediaIds.push(await page.getByTestId('media-asset').getAttribute('data-media-id'));
    const created = page.waitForResponse((item) => item.url().endsWith('/admin/pets') && item.request().method() === 'POST'); await page.getByTestId('admin-item-publish').click(); const pet = await (await created).json(); pets.push(pet.id); await page.waitForURL(base + '/admin/pets/' + pet.id); await page.getByTestId('admin-item-form').locator('[data-testid="admin-item-save-draft"]').filter({ hasText: 'Сохранить изменения' }).waitFor();
  }
  await goto('/admin/products/new'); await page.getByTestId('admin-item-name').fill(marker + 'toy'); await page.getByTestId('admin-item-description').fill('Прочная игрушка для питомцев.'); await page.getByTestId('admin-item-sku').fill(marker.toUpperCase()); await page.getByTestId('admin-item-category-id').selectOption(categories.find((value) => value.kind === 'product').id); await page.getByTestId('admin-item-product-type').selectOption('TOY'); await page.getByTestId('admin-item-price').fill('790,50'); await page.getByTestId('admin-item-stock').fill('8');
  await page.getByTestId('media-source').selectOption('DEMO'); await page.getByTestId('media-note').fill('Каталог для учебной проверки');
  await page.getByTestId('media-upload-input').setInputFiles(imagePath); await page.getByTestId('media-asset').waitFor(); mediaIds.push(await page.getByTestId('media-asset').getAttribute('data-media-id'));
  const productCreated = page.waitForResponse((item) => item.url().endsWith('/products') && item.request().method() === 'POST'); await page.getByTestId('admin-item-publish').click(); const product = await (await productCreated).json(); products.unshift(product.id); await page.waitForURL(base + '/admin/products/' + product.id); await page.getByTestId('admin-item-save-draft').filter({ hasText: 'Сохранить изменения' }).waitFor();
  await page.getByTestId('admin-item-stock-edit').click(); await page.getByTestId('stock-quantity').fill('12'); await page.getByTestId('stock-reason').fill('Тестовая поставка'); await page.getByTestId('stock-submit').click(); await page.getByTestId('stock-dialog').waitFor({ state: 'hidden' }); assert.equal((await api('/admin/products/' + product.id)).data.stock, 12);
  await page.getByTestId('admin-item-stock-edit').click(); await page.getByTestId('stock-quantity').fill('13'); await page.getByTestId('stock-reason').fill('Повтор после конфликта');
  const parallelStock = (await api('/admin/products/' + product.id)).data;
  assert.equal((await api('/products/' + product.id + '/stock-adjustments', 'POST', { version: parallelStock.version, delta: 0, reason: 'Параллельное изменение' })).status, 200);
  await page.getByTestId('stock-submit').click(); await closeError(/Карточка уже изменилась/); await page.getByTestId('stock-version-conflict').waitFor();
  assert.equal(await page.getByTestId('stock-quantity').inputValue(), '13'); assert.equal(await page.getByTestId('stock-reason').inputValue(), 'Повтор после конфликта'); assert.equal(await page.getByTestId('stock-submit').isDisabled(), true);
  await page.getByTestId('stock-reload-version').click(); await page.getByTestId('stock-version-conflict').waitFor({ state: 'hidden' }); await page.getByTestId('stock-submit').click(); await page.getByTestId('stock-dialog').waitFor({ state: 'hidden' }); assert.equal((await api('/admin/products/' + product.id)).data.stock, 13);
  pass('stock version conflict recovers in the same modal without losing quantity or reason');
  await page.reload(); await page.getByTestId('media-asset-source-note').waitFor(); assert.match(await page.getByTestId('media-asset-source').textContent(), /Демонстрационные/); assert.equal(await page.getByTestId('media-asset-source-note').textContent(), 'Каталог для учебной проверки');
  await audit(); await page.screenshot({ path: 'qa/screenshots/api-product-editor.png', fullPage: true });
  await goto('/admin/pets/' + pets[0]); await page.getByTestId('admin-item-name').fill(marker + 'first'); const current = (await api('/admin/pets/' + pets[0])).data;
  const command = Object.fromEntries(['name', 'description', 'categoryId', 'price', 'animalType', 'breed', 'sex', 'birthDate', 'version'].map((field) => [field, current[field]])); command.images = current.images.map(({ mediaId, alt, isCover }) => ({ mediaId, alt, isCover })); command.name = marker + 'other';
  assert.equal((await api('/admin/pets/' + pets[0], 'PUT', command)).status, 200);
  await page.getByTestId('admin-item-save-draft').click(); await closeError(/Карточка.*измени|Карточка уже/); assert.equal(await page.getByTestId('admin-item-name').inputValue(), marker + 'first'); await page.getByTestId('admin-item-reload-version').click(); await page.getByTestId('admin-item-reload-version').waitFor({ state: 'hidden' }); await page.getByTestId('admin-item-save-draft').click(); await page.waitForFunction(() => document.querySelector('[data-testid="toast"]')?.textContent === 'Карточка опубликована');
  assert.equal((await context.request.get(base + '/api/v3/media/' + mediaIds[0] + '/image')).status(), 200);
  pass('real categories, uploaded images, pet/product publication, stock adjustment, conflict and retained editor values');

  await page.getByTestId('account-signout').count().then(async (count) => { if (count) await page.getByTestId('account-signout').click(); else { await goto('/account'); await page.getByTestId('account-signout').click(); } });
  await selectItem('/catalog', marker + 'toy'); await selectItem('/pets', marker + 'first');
  const guest = await page.evaluate(() => JSON.parse(localStorage.getItem('lapki.selection.api.v1'))); assert.equal(guest.length, 2);
  await signIn(email, password); const merged = (await api('/store/cart')).data; assert.equal(merged.lines.length, 2); assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('lapki.selection.api.v1')).length), 0);
  await goto('/cart'); const productLine = page.getByTestId('cart-item').filter({ has: page.getByTestId('cart-item-name').filter({ hasText: marker + 'toy' }) }); await productLine.getByTestId('cart-item-increment').click(); await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="cart-item-quantity"]')].some((node) => node.textContent === '2')); await audit();
  let draftRetryKey;
  await page.route('**/api/v3/store/orders', async (route) => { if (route.request().method() !== 'POST') return route.continue(); draftRetryKey = route.request().headers()['idempotency-key']; const response = await route.fetch(); assert.equal(response.status(), 201); orders.push((await response.json()).id); await route.abort('failed'); }, { times: 1 });
  await goto('/checkout'); await page.getByTestId('checkout-submit').click(); await closeError(/Проверим созданный заказ/); await page.reload(); await page.getByTestId('checkout-submit').click(); await page.waitForURL(/\/account\/orders\/[0-9a-f-]+$/); const orderId = page.url().split('/').at(-1); assert.equal(orderId, orders.at(-1)); await page.getByTestId('payment-card').waitFor();
  const mixed = (await api('/store/orders/' + orderId)).data; assert.equal(mixed.lines.length, 2); assert.equal(mixed.total, 2581.25); assert.equal((await api('/store/cart')).data.lines.length, 0); assert.equal((await api('/store/orders')).data.filter((order) => order.id === orderId).length, 1); assert.ok(draftRetryKey);
  await page.getByTestId('payment-submit').click(); await page.getByTestId('payment-cvv-error').waitFor();
  await card('4000 0000 0000 0002'); await page.getByTestId('payment-submit').click(); await closeError(/Оплата не прошла/);
  assert.equal(await page.getByTestId('payment-cvv').inputValue(), '123');
  await card('4000 0000 0000 9995'); await page.getByTestId('payment-submit').click(); await closeError(/Недостаточно средств/);
  let lostKey;
  await page.route('**/api/v3/store/orders/*/payments', async (route) => { lostKey = route.request().headers()['idempotency-key']; const accepted = await route.fetch(); assert.equal(accepted.status(), 201); await route.abort('failed'); }, { times: 1 });
  await card('4242 4242 4242 4242'); await page.getByTestId('payment-submit').click(); await closeError(/Проверяем результат оплаты/); await page.getByTestId('payment-recheck').click(); await page.locator('[data-testid="status"][data-status="PAID"]').waitFor();
  assert.equal(await page.getByTestId('order-reserve-countdown').count(), 0); await page.reload(); await page.locator('.page-title-row [data-status="PAID"]').waitFor(); assert.equal(await page.getByTestId('order-reserve-countdown').count(), 0);
  const archivedPet = (await api('/admin/pets/' + pets[0], 'GET', undefined, adminToken)).data; assert.equal((await api('/admin/pets/' + pets[0] + '/archive', 'POST', { version: archivedPet.version }, adminToken)).status, 200); await page.reload(); await page.getByTestId('order-item').first().waitFor(); await page.waitForFunction(() => [...document.querySelectorAll('[data-testid="order-item"] img')].length === 2 && [...document.querySelectorAll('[data-testid="order-item"] img')].every((image) => image.naturalWidth > 0));
  const attempts = (await api('/store/orders/' + orderId + '/payments')).data; assert.equal(attempts.filter((item) => item.status === 'SUCCEEDED').length, 1); assert.equal(attempts.filter((item) => item.status === 'DECLINED').length, 2); assert.equal('cvv' in attempts[0], false);
  const replay = await api('/store/orders/' + orderId + '/payments', 'POST', { cardNumber: '4242424242424242', expiryMonth: 12, expiryYear: 2099, cvv: '123', cardholderName: 'API TEST USER' }, undefined, lostKey); assert.equal(replay.status, 200);
  assert.equal((await api('/store/orders/' + orderId + '/payments')).data.filter((item) => item.status === 'SUCCEEDED').length, 1);
  const stored = await page.evaluate(() => JSON.stringify({ ...sessionStorage, ...localStorage })); for (const secret of [password, '4242424242424242', 'API TEST USER']) assert.equal(stored.includes(secret), false);
  await page.getByTestId('order-cancel').click(); await page.getByTestId('order-cancel-confirm').click(); await page.locator('.page-title-row').locator('[data-testid="status"][data-status="REFUNDED"]').waitFor();
  pass('mixed order, guest/server merge, lost accepted draft, cart clearing, full card validation, decline, funds, lost accepted response, idempotent replay and refund');

  await selectItem('/catalog', marker + 'toy'); await goto('/cart');
  const beforeConflict = (await api('/store/cart')).data;
  assert.equal((await api('/store/cart', 'PUT', { version: beforeConflict.version, lines: beforeConflict.lines.map(({ id, kind, quantity }) => ({ id, kind, quantity })) }, undefined, crypto.randomUUID())).status, 200);
  await page.getByTestId('cart-item-increment').click(); await closeError(/Корзина изменилась/); assert.equal((await api('/store/cart')).data.lines[0].quantity, 1);
  await page.route('**/api/v3/store/orders/*/place', async (route) => {
    const current = (await api('/admin/products/' + products[0], 'GET', undefined, adminToken)).data;
    const fields = ['sku','name','description','categoryId','brand','productType','animalTypes','price','feedForm','lifeStages','netWeightGrams','ingredients','version'];
    const command = Object.fromEntries(fields.map((field) => [field,current[field]])); command.price += 1; command.images = current.images.map(({ mediaId, alt, isCover }) => ({ mediaId, alt, isCover }));
    assert.equal((await api('/products/' + products[0], 'PUT', command, adminToken)).status, 200);
    await route.continue();
  }, { times: 1 });
  await goto('/checkout'); await page.getByTestId('checkout-submit').click(); await closeError(/Цена изменилась/); await page.waitForURL('**/cart'); await page.getByTestId('cart-price-changed').waitFor();
  const changed = (await api('/admin/products/' + products[0], 'GET', undefined, adminToken)).data; assert.equal(changed.reserved, 0);
  assert.equal((await api('/products/' + products[0] + '/stock-adjustments','POST',{version:changed.version,delta:-changed.stock,reason:'Тест отсутствия остатков'},adminToken)).status,200);
  await page.reload(); await page.getByTestId('cart-item-error').waitFor(); assert.match(await page.getByTestId('cart-item-error').textContent(), /Уменьшите количество/); assert.equal(await page.getByTestId('cart-checkout').count(),0);
  await page.getByTestId('cart-item-remove').click(); await page.getByTestId('empty-cart-catalog').waitFor();
  const emptyStock = (await api('/admin/products/' + products[0], 'GET', undefined, adminToken)).data;
  assert.equal((await api('/products/' + products[0] + '/stock-adjustments','POST',{version:emptyStock.version,delta:12,reason:'Возврат тестового остатка'},adminToken)).status,200);
  await signIn('admin@example.com','admin123','/admin'); await goto('/admin/products/' + products[0]); await page.getByTestId('admin-item-unpublish').click(); await page.getByTestId('admin-item-publish').waitFor();
  assert.equal((await context.request.get(base + '/api/v3/media/' + mediaIds.at(-1) + '/image')).status(),404);
  await page.getByTestId('admin-item-publish').click(); await page.getByTestId('admin-item-unpublish').waitFor(); assert.equal((await context.request.get(base + '/api/v3/media/' + mediaIds.at(-1) + '/image')).status(),200);
  await signIn(email,password);
  pass('cart version conflict preserves contents, price race reserves nothing, out-of-stock blocks checkout, publication controls public media access');

  await selectPet(marker + 'pet1'); const delivered = await checkout(); await card('4242 4242 4242 4242'); await page.getByTestId('payment-submit').click(); await page.locator('[data-testid="status"][data-status="PAID"]').waitFor();
  await signIn('admin@example.com', 'admin123', '/admin'); await goto('/admin/orders/' + delivered);
  for (const status of ['APPROVED', 'SHIPPED', 'DELIVERED']) { await page.getByTestId('admin-order-advance').click(); await page.locator(`[data-testid="status"][data-status="${status}"]`).waitFor(); }
  assert.equal((await api('/pet/' + pets[1])).data.status, 'sold');
  await goto('/admin/users'); const row = page.getByTestId('admin-user-row').filter({ has: page.getByText(email, { exact: true }) }); await row.getByTestId('admin-user-toggle-status').click(); await row.locator('[data-status="BLOCKED"]').waitFor(); assert.equal((await api('/auth/login', 'POST', { email, password })).status, 403); await row.getByTestId('admin-user-toggle-status').click(); await row.locator('[data-status="ACTIVE"]').waitFor();
  pass('real administrator order transitions and user block/unblock');

  await signIn(email, password); const oldToken = await page.evaluate(() => sessionStorage.getItem('lapki.session.api.v1')); await goto('/forgot-password'); await page.getByTestId('login-email').fill(email); await page.getByTestId('login-submit').click(); await page.getByTestId('auth-result').waitFor(); const recovery = await letter(messages);
  await page.goto(recovery.link); await page.getByTestId('reset-password').fill(newPassword); const reset = page.waitForResponse((item) => item.url().includes('/auth/password/reset') && item.request().method() === 'POST'); await page.getByTestId('confirm-submit').click(); const resetRequest = (await reset).request(); assert.deepEqual(Object.keys(resetRequest.postDataJSON()), ['newPassword']); assert.ok(new URL(resetRequest.url()).searchParams.get('code')); await page.getByTestId('confirm-login').waitFor(); assert.equal((await api('/user/me', 'GET', undefined, oldToken)).status, 401); await signIn(email, newPassword);
  pass('SMTP password recovery, correct code query and newPassword body, old JWT revocation');

  for (const width of [360, 768, 1440]) { await page.setViewportSize({ width, height: 1000 }); for (const path of ['/', '/pets', '/catalog', '/account', '/account/orders']) { await goto(path); await page.waitForTimeout(200); await audit(); } await page.screenshot({ path: `qa/screenshots/api-account-${width}.png`, fullPage: true }); }
  assert.deepEqual(errors, []); const text = logs.join('\n'); for (const value of [password, newPassword, email, '4242424242424242', 'API TEST USER']) assert.equal(text.includes(value), false);
  assert.equal(requested.some((request) => /^\/api\/v3\/demo/.test(request.path)), false);
  for (const path of ['/api/v3/products', '/api/v3/catalog/pets', '/api/v3/store/cart', '/api/v3/media']) assert.ok(requested.some((request) => request.path.startsWith(path)));
  pass('API responsive pages, stable testids, no unsupported calls, no runtime errors or credential logs');
  await writeFile('qa/api-result.json', JSON.stringify({ passed: true, baseUrl: base, results, runtimeErrors: errors, checkedAt: new Date().toISOString() }, null, 2)); console.log(JSON.stringify({ passed: true, cases: results.length }));
} catch (error) { await page.screenshot({ path: 'qa/screenshots/api-failure.png', fullPage: true }); await writeFile('qa/api-result.json', JSON.stringify({ passed: false, results, failure: String(error), runtimeErrors: errors, url: page.url() }, null, 2)); throw error; }
finally {
  if (adminToken) {
    for (const id of [...new Set(orders)]) { const order = (await api('/store/orders/' + id, 'GET', undefined, adminToken)).data; if (order && ['draft', 'placed', 'approved'].includes(order.status)) await api('/store/orders/' + id + '/cancel', 'POST', { version: order.version }, adminToken).catch(() => {}); await api('/store/orders/' + id, 'DELETE', undefined, adminToken).catch(() => {}); }
    for (const [kind, ids] of [['pets',pets], ['products',products]]) for (const id of ids) { const path = kind === 'pets' ? '/admin/pets/' : '/products/'; const item = (await api('/admin/' + kind + '/' + id,'GET',undefined,adminToken)).data; if (item?.version !== undefined) await api(path + id + '/archive','POST',{version:item.version},adminToken).catch(() => {}); }
    for (const category of categories) await api('/admin/catalog/categories/' + category.id,'PUT',{name:category.name,kind:category.kind,active:false,version:category.version},adminToken).catch(() => {});
    if (userId) await api('/users/' + userId, 'DELETE', undefined, adminToken).catch(() => {});
  }
  for (const id of messages) await context.request.delete(mail + '/api/Messages/' + id).catch(() => {});
  await browser.close();
}
