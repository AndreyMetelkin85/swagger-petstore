import { createRequire } from 'node:module';
import { strict as assert } from 'node:assert';
import { mkdir, writeFile } from 'node:fs/promises';
import { assertTestIdContract } from './assert-testid-contract.mjs';
const { chromium } = createRequire(import.meta.url)(process.env.LAPKI_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.LAPKI_PREVIEW_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({ channel: process.env.LAPKI_BROWSER_CHANNEL === 'bundled' ? undefined : process.env.LAPKI_BROWSER_CHANNEL || 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce', locale: 'ru-RU', timezoneId: 'Europe/Moscow' });
const page = await context.newPage(); page.setDefaultTimeout(15000);
const errors = [], logs = [], results = [];
page.on('pageerror', (error) => errors.push(error.message));
page.on('console', (message) => { if (message.type() === 'info') logs.push(message.text()); });
const product = '10000000-0000-4000-8000-000000000001', pet = '10000000-0000-4000-8000-000000000005';
const photo = 'public/images/pets-hero.png';
// Scope repeated actions by the entity, never by row position or a UUID in testid.
const entity = (testId, kind, id) => page.getByTestId(testId).and(page.locator(`[data-${kind}-id=${JSON.stringify(id)}]`));
const itemCard = (id) => entity('catalog-item-card', 'item', id);
const cartItem = (id) => entity('cart-item', 'item', id);
const mediaAsset = (id) => entity('media-asset', 'media', id);
const adminUser = (id) => entity('admin-user-row', 'user', id);
await mkdir('qa/screenshots', { recursive: true });
async function goto(path) { await page.goto(base + path); await page.getByTestId('nav-home').waitFor(); }
async function api(path, method = 'GET', body, explicitToken, key) {
  return page.evaluate(async ({ path, method, body, explicitToken, key }) => {
    const headers = { 'Content-Type': 'application/json' }; const token = explicitToken || sessionStorage.getItem('lapki.session.v3');
    if (token) headers.Authorization = `Bearer ${token}`; if (key) headers['Idempotency-Key'] = key;
    const response = await fetch('/api/v3' + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
    return { status: response.status, data: await response.json() };
  }, { path, method, body, explicitToken, key });
}
async function role(role) { await goto('/demo'); await page.getByTestId(`demo-${role}`).click(); await page.waitForURL(new RegExp(role === 'admin' ? '/admin$' : '/account$')); }
async function caseDone(name) { results.push({ name, passed: true }); console.log(`PASS ${name}`); }
async function assertControls() {
  await assertTestIdContract(page);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
}
async function checkout() {
  await goto('/checkout'); await page.getByTestId('checkout-name').waitFor();
  await page.getByTestId('checkout-submit').click(); await page.waitForURL(/\/account\/orders\/[0-9a-f-]+$/);
  await page.getByTestId('order-total').waitFor(); return page.url().split('/').at(-1);
}
async function closeError(text) { await page.getByTestId('error-dialog').waitFor(); if (text) assert.match(await page.getByTestId('error-dialog').textContent(), text); await assertControls(); await page.getByTestId('error-dismiss').click(); }
try {
  await goto('/'); await itemCard(product).getByTestId('catalog-item-add').click();
  await page.getByTestId('cart-count').waitFor(); await goto('/pets'); await itemCard(pet).getByTestId('catalog-item-add').click();
  const auth = await api('/auth/login', 'POST', { email: 'buyer@lapki.demo', password: 'Buyer123!' });
  assert.equal(auth.status, 200);
  await api('/store/cart', 'PUT', { version: 1, lines: [{ id: product, quantity: 2 }, { id: pet, quantity: 1 }] }, auth.data.access_token);
  await goto('/login?next=%2Fcart'); await page.getByTestId('login-email').fill('buyer@lapki.demo'); await page.getByTestId('login-password').fill('Buyer123!'); await page.getByTestId('login-submit').click();
  await page.waitForURL(/\/cart$/); await cartItem(product).getByTestId('cart-item-quantity').waitFor();
  assert.equal(await cartItem(product).getByTestId('cart-item-quantity').textContent(), '3'); assert.equal(await cartItem(pet).getByTestId('cart-item-quantity').textContent(), '1');
  await page.reload(); await cartItem(product).getByTestId('cart-item-quantity').waitFor(); assert.equal(await cartItem(product).getByTestId('cart-item-quantity').textContent(), '3');
  await cartItem(product).getByTestId('cart-item-decrement').click(); await page.waitForFunction((id) => document.querySelector(`[data-testid="cart-item"][data-item-id="${id}"] [data-testid="cart-item-quantity"]`)?.textContent === '2', product);
  await cartItem(product).getByTestId('cart-item-decrement').click(); await page.waitForFunction((id) => document.querySelector(`[data-testid="cart-item"][data-item-id="${id}"] [data-testid="cart-item-quantity"]`)?.textContent === '1', product);
  await caseDone('guest/account merge, pet deduplication, persistence, quantity');
  await assertControls();
  await cartItem(product).getByTestId('cart-item-remove').click();
  await cartItem(product).waitFor({ state: 'hidden' });
  assert.equal(await cartItem(pet).getByTestId('cart-item-quantity').textContent(), '1');
  await goto('/catalog'); await page.getByTestId('catalog-sort').selectOption('price-down');
  await itemCard(product).getByTestId('catalog-item-add').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="cart-count"]')?.textContent === '2');
  await goto('/cart'); await cartItem(product).getByTestId('cart-item-quantity').waitFor();
  assert.equal(await cartItem(product).getByTestId('cart-item-quantity').textContent(), '1');
  assert.equal(await cartItem(pet).getByTestId('cart-item-quantity').textContent(), '1');
  await caseDone('stable testids: scoped actions affect one item, sorting preserves entity selection');
  const orderId = await checkout();
  await page.getByTestId('payment-card').fill('4000 0000 0000 0002'); await page.getByTestId('payment-submit').click(); await closeError(/Оплата не прошла/);
  assert.equal(await page.getByTestId('payment-card').inputValue(), '4000 0000 0000 0002');
  await page.getByTestId('payment-card').fill('4000 0000 0000 9995'); await page.getByTestId('payment-submit').click(); await closeError(/Проверяем результат оплаты/);
  await page.getByTestId('payment-recheck').click(); await page.locator('[data-testid="status"][data-status="PAID"]').waitFor();
  const paid = await api(`/store/orders/${orderId}`); assert.equal(paid.data.payments.filter((payment) => payment.status === 'SUCCEEDED').length, 1);
  assert.equal((await api('/products')).data.find((item) => item.id === product).stock, 7);
  await page.getByTestId('order-cancel').click(); await page.getByTestId('order-cancel-confirm').click(); await page.locator('.page-title-row').locator('[data-testid="status"][data-status="REFUNDED"]').waitFor();
  await api(`/store/orders/${orderId}/cancel`, 'POST'); assert.equal((await api('/products')).data.find((item) => item.id === product).stock, 8);
  await caseDone('mixed order, decline preserves form, ambiguous success, one payment, refund once');
  await goto('/admin'); await page.getByRole('heading', { name: 'Недостаточно прав' }).waitFor(); assert.equal((await api('/admin/products')).status, 403);
  await caseDone('USER cannot enter admin UI or mock API');

  await role('admin'); await goto('/admin/categories'); await page.getByTestId('admin-category-create').click(); await page.getByTestId('admin-category-name').fill('Демо корм');
  const categoryResponse = page.waitForResponse((response) => response.url().endsWith('/admin/categories') && response.request().method() === 'POST'); await page.getByTestId('admin-category-submit').click(); const categoryId = (await (await categoryResponse).json()).id;
  await goto('/admin/products/new'); await page.getByTestId('admin-item-name').fill('Корм для кошек — проверка'); await page.getByTestId('admin-item-publish').click(); await closeError(/Проверьте заполненные поля/);
  assert.equal(await page.getByTestId('admin-item-name').inputValue(), 'Корм для кошек — проверка');
  await page.getByTestId('admin-item-description').fill('Учебный корм с демонстрационной упаковкой.'); await page.getByTestId('admin-item-sku').fill('QA-CAT-1000'); await page.getByTestId('admin-item-brand').fill('Лапки'); await page.getByTestId('admin-item-category-id').selectOption(categoryId); await page.getByTestId('admin-item-net-weight-grams').fill('1000'); await page.getByTestId('admin-item-price').fill('850.50'); await page.getByTestId('admin-item-stock').fill('5');
  await page.getByTestId('media-upload-input').setInputFiles({ name: 'wrong.txt', mimeType: 'text/plain', buffer: Buffer.from('invalid photo') }); await closeError(/Формат фотографии не подходит/);
  await api('/demo/scenario', 'POST', { scenario: 'MEDIA_STORAGE_UNAVAILABLE' }); await page.getByTestId('media-upload-input').setInputFiles(photo); await closeError(/Не удалось загрузить фотографию/);
  await page.locator('[data-testid="media-upload-retry"]').click(); await page.locator('[data-testid="media-asset-make-cover"]').first().waitFor();
  await page.getByTestId('media-upload-input').setInputFiles(photo); await page.waitForFunction(() => document.querySelectorAll('[data-testid="media-asset-make-cover"]').length === 2);
  const draftResponse = page.waitForResponse((response) => response.url().endsWith('/admin/products') && response.request().method() === 'POST'); await page.getByTestId('admin-item-save-draft').click(); const newProduct = (await (await draftResponse).json()).id;
  await page.waitForURL(new RegExp(`/admin/products/${newProduct}$`)); await page.reload(); await page.getByTestId('admin-item-name').waitFor();
  await page.waitForFunction(() => document.querySelectorAll('[data-testid="media-asset-make-cover"]').length === 2);
  const refs = (await api(`/admin/products/${newProduct}`)).data.images;
  await mediaAsset(refs[1].mediaId).getByTestId('media-asset-make-cover').click(); await mediaAsset(refs[1].mediaId).getByTestId('media-asset-alt').fill('Обложка корма'); await page.getByTestId('admin-item-publish').click(); await page.locator('[data-testid="status"][data-status="PUBLISHED"]').waitFor();
  const published = (await api(`/products/${newProduct}`)).data; assert.equal(published.images[0].mediaId, refs[1].mediaId); assert.equal(published.netWeightGrams, 1000); assert.equal(published.price, 850.5);
  await goto(`/catalog/${newProduct}`); await page.getByRole('heading', { name: 'Корм для кошек — проверка' }).waitFor(); await page.waitForFunction(() => document.querySelector('.full-detail-image img')?.naturalWidth > 0);
  await caseDone('category, form validation, wrong upload, failed upload retry, draft/photo reload, cover and publication');
  await goto(`/admin/products/${newProduct}`); await page.getByTestId('admin-item-name').waitFor(); await page.getByTestId('admin-item-name').fill('Правка без сохранения'); await page.getByTestId('admin-editor-back').click(); await page.getByTestId('unsaved-dialog').waitFor(); await page.getByTestId('unsaved-stay').click(); assert.equal(await page.getByTestId('admin-item-name').inputValue(), 'Правка без сохранения');
  await api('/demo/scenario', 'POST', { scenario: 'PRODUCT_VERSION_CONFLICT' }); await page.getByTestId('admin-item-save-draft').click(); await closeError(/Карточка уже изменилась/); assert.equal(await page.getByTestId('admin-item-name').inputValue(), 'Правка без сохранения'); await page.getByTestId('admin-item-reload-version').click(); await page.getByTestId('admin-item-reload-version').waitFor({ state: 'hidden' }); await page.getByTestId('admin-item-name').fill('Корм для кошек — проверка'); await page.getByTestId('admin-item-save-draft').click(); await page.waitForFunction(() => document.querySelector('[data-testid=toast]')?.textContent === 'Карточка опубликована');
  await page.getByTestId('admin-item-stock-edit').click(); await page.getByTestId('stock-quantity').fill('7'); await page.getByTestId('stock-reason').fill('Учебная поставка'); await page.getByTestId('stock-submit').click(); await page.waitForFunction(() => !document.querySelector('[data-testid="stock-dialog"]'));
  assert.equal((await api(`/admin/products/${newProduct}`)).data.stock, 7);
  await page.getByTestId('media-upload-input').setInputFiles(photo); await page.waitForFunction(() => document.querySelectorAll('[data-testid="media-asset-make-cover"]').length === 3); await page.getByTestId('admin-editor-back').click(); await page.getByTestId('unsaved-leave').click(); await page.waitForURL(/\/admin\/products$/); assert.equal((await api(`/admin/products/${newProduct}`)).data.images.length, 2);
  await caseDone('unsaved navigation, conflict keeps fields and recovers, separate stock adjustment, cancelled gallery edit');
  await goto('/admin/pets/new'); await page.getByTestId('admin-item-name').fill('Демо Мурка'); await page.getByTestId('admin-item-description').fill('Спокойная учебная кошка.'); await page.getByTestId('admin-item-category-id').selectOption('30000000-0000-4000-8000-000000000003'); await page.getByTestId('admin-item-animal-cat').check(); await page.getByTestId('admin-item-price').fill('5000'); await page.getByTestId('media-upload-input').setInputFiles([photo, photo]); await page.waitForFunction(() => document.querySelectorAll('[data-testid="media-asset-make-cover"]').length === 2);
  const uploadedPetRefs = await page.locator('[data-testid="media-asset-move-earlier"]').evaluateAll((nodes) => nodes.map((node) => node.closest('[data-testid="media-asset"]').getAttribute('data-media-id'))); await mediaAsset(uploadedPetRefs[1]).getByTestId('media-asset-move-earlier').focus(); await page.keyboard.press('Enter');
  const petResponse = page.waitForResponse((response) => response.url().endsWith('/admin/pets') && response.request().method() === 'POST'); await page.getByTestId('admin-item-publish').click(); const newPet = (await (await petResponse).json()).id; await page.waitForURL(new RegExp(`/admin/pets/${newPet}$`)); assert.equal((await api(`/catalog/pets/${newPet}`)).data.images.length, 2);
  await caseDone('pet editor, keyboard gallery reorder, publication');

  for (const width of [1440, 768, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/', '/catalog', `/catalog/${newProduct}`, '/cart', '/account', '/account/orders', '/admin', '/admin/products', `/admin/products/${newProduct}`, '/admin/pets', '/admin/categories', '/admin/users', '/admin/demo']) {
      await goto(route); await page.waitForTimeout(350); await assertControls();
      if (['/', `/admin/products/${newProduct}`, '/account'].includes(route)) await page.screenshot({ path: `qa/screenshots/full-${route === '/' ? 'home' : route === '/account' ? 'account' : 'editor'}-${width}.png`, fullPage: width === 1440 });
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 }); await caseDone('39 responsive page checks: 360/768/1440, testids, no horizontal overflow');

  await role('buyer'); await goto('/catalog'); await itemCard(newProduct).getByTestId('catalog-item-add').click(); await page.waitForFunction(() => document.querySelector('[data-testid="cart-count"]')?.textContent === '1'); await goto('/pets'); await itemCard(newPet).getByTestId('catalog-item-add').click(); await page.waitForFunction(() => document.querySelector('[data-testid="cart-count"]')?.textContent === '2'); const deliveredOrder = await checkout(); await page.getByTestId('payment-submit').click(); await page.locator('[data-testid="status"][data-status="PAID"]').waitFor();
  await role('admin'); await goto(`/admin/orders/${deliveredOrder}`); for (const status of ['APPROVED', 'SHIPPED', 'DELIVERED']) { await page.getByTestId('admin-order-advance').click(); await page.locator(`[data-testid="status"][data-status="${status}"]`).waitFor(); } assert.equal((await api(`/admin/pets/${newPet}`)).data.status, 'sold');
  await caseDone('admin confirms, ships, delivers; pet sold only on delivery');
  const buyerId = '20000000-0000-4000-8000-000000000002'; await goto('/admin/users'); await adminUser(buyerId).getByTestId('admin-user-toggle-status').click(); await page.locator('[data-testid="status"][data-status="BLOCKED"]').waitFor(); const blocked = await api('/auth/login', 'POST', { email: 'buyer@lapki.demo', password: 'Buyer123!' }); assert.equal(blocked.status, 403); await adminUser(buyerId).getByTestId('admin-user-toggle-status').click(); await adminUser(buyerId).locator('[data-testid="status"][data-status="ACTIVE"]').waitFor();
  await caseDone('admin user blocking and unblocking');

  const email = 'scenario@lapki.demo'; await goto('/register'); await page.getByTestId('registration-username').fill('scenario_user'); await page.getByTestId('auth-name').fill('Учебный Пользователь'); await page.getByTestId('login-email').fill(email); await page.getByTestId('login-password').fill('DemoRegister123!'); await page.getByTestId('login-submit').click(); await page.getByTestId('auth-demo-link').waitFor(); const confirmLink = await page.getByTestId('auth-demo-link').getAttribute('href');
  assert.equal((await api('/auth/login', 'POST', { email, password: 'DemoRegister123!' })).data.error, 'ACCOUNT_NOT_VERIFIED'); await goto(confirmLink); await page.waitForURL('**/register/complete'); await page.getByTestId('confirm-login').waitFor();
  await goto('/forgot-password'); await page.getByTestId('login-email').fill(email); await page.getByTestId('login-submit').click(); await page.getByTestId('auth-demo-link').waitFor(); const resetLink = await page.getByTestId('auth-demo-link').getAttribute('href'); await goto(resetLink); await page.getByTestId('reset-password').fill('DemoNewPassword123!'); await page.getByTestId('confirm-submit').click(); await page.getByTestId('confirm-login').waitFor(); assert.equal((await api('/auth/login', 'POST', { email, password: 'DemoNewPassword123!' })).status, 200);
  await caseDone('registration, email confirmation, recovery, password reset');

  await role('admin'); await api('/demo/scenario', 'POST', { scenario: 'PRICE_CHANGED' }); await role('buyer'); await goto('/catalog'); await itemCard(product).getByTestId('catalog-item-add').click(); await page.waitForFunction(() => document.querySelector('[data-testid="cart-count"]')?.textContent === '1'); await goto('/checkout'); await page.getByTestId('checkout-submit').click(); await closeError(/Цена изменилась/); await page.getByTestId('checkout-submit').click(); await page.waitForURL(/\/account\/orders\/[0-9a-f-]+$/); const expiredOrder = page.url().split('/').at(-1);
  await role('admin'); await api('/demo/scenario', 'POST', { scenario: 'RESERVATION_EXPIRED' }); await role('buyer'); await goto(`/account/orders/${expiredOrder}`); await page.getByTestId('payment-submit').click(); await closeError(/Время резерва истекло/); await page.locator('[data-testid="status"][data-status="EXPIRED"]').waitFor();
  await caseDone('changed price requires review, retry, expired reservation safely releases stock');
  await role('admin'); await api('/demo/scenario', 'POST', { scenario: 'INSUFFICIENT_STOCK' }); await role('buyer'); await goto('/catalog'); await itemCard(product).getByTestId('catalog-item-add').click(); await page.waitForFunction(() => document.querySelector('[data-testid="cart-count"]')?.textContent === '1'); await goto('/checkout'); await page.getByTestId('checkout-submit').click(); await closeError(/Недостаточно товара/); await goto('/cart'); await cartItem(product).getByTestId('cart-item-error').waitFor(); assert.equal(await page.getByTestId('cart-checkout').count(), 0); await cartItem(product).getByTestId('cart-item-remove').click(); await page.getByRole('heading', { name: 'Здесь пока пусто' }).waitFor();
  await role('admin'); const longItem = (await api(`/admin/products/${newProduct}`)).data; const longName = 'Очень длинное название учебного товара '.repeat(3).slice(0, 145); await api(`/admin/products/${newProduct}`, 'PUT', { ...longItem, name: longName }); await goto(`/catalog/${newProduct}`); await page.setViewportSize({ width: 360, height: 1000 }); await page.getByRole('heading', { name: longName }).waitFor(); await assertControls(); await page.setViewportSize({ width: 1440, height: 1000 });
  await role('buyer'); await goto('/catalog'); await itemCard(newProduct).getByTestId('catalog-item-add').click(); await page.waitForFunction(() => document.querySelector('[data-testid="cart-count"]')?.textContent === '1'); await role('admin'); await api(`/admin/products/${newProduct}/archive`, 'POST'); await role('buyer'); await goto('/cart'); await cartItem(newProduct).getByTestId('cart-item-error').waitFor(); assert.equal(await page.getByTestId('cart-checkout').count(), 0); await cartItem(newProduct).getByTestId('cart-item-remove').click();
  await caseDone('stock shortage and archived cart items block checkout without data loss; long mobile titles');
  assert.deepEqual(errors, []); const allLogs = logs.join('\n'); for (const forbidden of ['Buyer123!', 'Admin123!', 'DemoRegister123!', 'DemoNewPassword123!', 'scenario@lapki.demo', 'Учебный Пользователь', '4242424242424242', '4000000000009995', 'Mock service internal diagnostic']) assert.equal(allLogs.includes(forbidden), false, `sensitive log: ${forbidden}`);
  await role('admin'); await goto('/admin/demo'); await page.getByTestId('demo-reset').click(); await page.getByTestId('demo-reset-confirm').click(); await page.waitForURL(/\/demo$/); const resetCatalog = await api('/products'); assert.equal(resetCatalog.data.length, 4); await caseDone('safe logs, no runtime errors, confirmed demo reset');
  await writeFile('qa/full-result.json', JSON.stringify({ passed: true, baseUrl: base, results, runtimeErrors: errors, checkedAt: new Date().toISOString() }, null, 2));
  console.log(JSON.stringify({ passed: true, cases: results.length, runtimeErrors: errors }));
} catch (error) {
  await page.screenshot({ path: 'qa/screenshots/full-failure.png', fullPage: true });
  await writeFile('qa/full-result.json', JSON.stringify({ passed: false, results, failure: String(error), runtimeErrors: errors, url: page.url() }, null, 2));
  throw error;
} finally { await browser.close(); }
