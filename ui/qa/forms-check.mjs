import { createRequire } from 'node:module';
import { strict as assert } from 'node:assert';
import { mkdir, writeFile } from 'node:fs/promises';
import { assertTestIdContract } from './assert-testid-contract.mjs';
const { chromium } = createRequire(import.meta.url)(process.env.LAPKI_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.LAPKI_PREVIEW_URL || 'http://127.0.0.1:8088';
const browser = await chromium.launch({ channel: process.env.LAPKI_BROWSER_CHANNEL === 'bundled' ? undefined : process.env.LAPKI_BROWSER_CHANNEL || 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'ru-RU', timezoneId: 'Europe/Moscow', reducedMotion: 'reduce' });
const page = await context.newPage(); page.setDefaultTimeout(15000);
const requests = [], errors = [], results = [];
page.on('request', (request) => { if (['POST', 'PUT', 'DELETE'].includes(request.method())) requests.push(new URL(request.url()).pathname); });
page.on('pageerror', (error) => errors.push(error.message));
page.on('dialog', (dialog) => dialog.accept());
await mkdir('qa/screenshots', { recursive: true });
const done = (name) => { results.push(name); console.log('PASS ' + name); };
const count = (suffix) => requests.filter((path) => path.endsWith(suffix)).length;
async function goto(path) { await page.goto(base + path); await page.getByTestId('nav-home').waitFor(); }
async function role(name) { await goto('/demo'); await page.getByTestId(`demo-${name}`).click(); await page.waitForURL(name === 'admin' ? '**/admin' : '**/account'); }
async function invalid(testId, text) {
  await page.getByTestId(testId + '-error').waitFor();
  if (text) assert.match(await page.getByTestId(testId + '-error').textContent(), text);
  assert.equal(await page.getByTestId(testId).getAttribute('aria-invalid'), 'true');
}
async function audit() {
  await assertTestIdContract(page);
  const issues = await page.evaluate(() => {
    const fields = [...document.querySelectorAll('input:not([type=hidden]),select,textarea')];
    const name = (node) => node.getAttribute('data-testid');
    const ids = [...document.querySelectorAll('[id]')].map((node) => node.id);
    return {
      unlabeled: fields.filter((node) => !node.labels?.length && !node.getAttribute('aria-label') && !node.getAttribute('aria-labelledby')).map(name),
      noPlaceholder: fields.filter((node) => (node.tagName === 'TEXTAREA' || node.tagName === 'INPUT' && !['file', 'date', 'checkbox', 'radio'].includes(node.type)) && !node.placeholder?.trim()).map(name),
      brokenDescription: [...document.querySelectorAll('[aria-describedby]')].filter((node) => node.getAttribute('aria-describedby').split(/\s+/).some((id) => !document.getElementById(id))).map(name),
      duplicateIds: [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))],
      overflow: document.documentElement.scrollWidth > innerWidth,
    };
  });
  assert.deepEqual(issues, { unlabeled: [], noPlaceholder: [], brokenDescription: [], duplicateIds: [], overflow: false });
}
const named = (list, row, title, text) => page.getByTestId(list).getByTestId(row).filter({ has: page.getByTestId(title).filter({ hasText: new RegExp('^' + text + '$') }) });
try {
  await goto('/register'); await page.getByTestId('login-submit').click();
  await invalid('registration-username'); await invalid('login-email'); await invalid('login-password'); await audit();
  const beforeRegistration = count('/auth/register');
  await page.getByTestId('registration-username').fill('котики'); await page.getByTestId('login-email').fill('bad'); await page.getByTestId('login-password').fill('123'); await page.getByTestId('login-submit').click();
  await invalid('registration-username', /латинские/); await invalid('login-email', /формате/); await invalid('login-password', /6 символов/);
  assert.equal(count('/auth/register'), beforeRegistration);
  assert.equal(await page.getByTestId('registration-username').inputValue(), 'котики');
  await page.screenshot({ path: 'qa/screenshots/forms-registration-invalid.png', fullPage: true });
  await page.getByTestId('registration-username').fill('validation_user'); await page.getByTestId('auth-name').fill(' Анна '); await page.getByTestId('login-email').fill('forms@lapki.demo'); await page.getByTestId('login-password').fill('Forms123!');
  const registration = page.waitForResponse((response) => response.url().endsWith('/auth/register') && response.request().method() === 'POST'); await page.getByTestId('login-submit').click();
  const sent = (await registration).request().postDataJSON(); assert.equal(sent.firstName, 'Анна'); await page.waitForURL('**/register/verify');
  done('registration: inline errors, contract rules, retained input, accessible labels and hints');

  await page.reload(); await page.getByTestId('registration-resend-password').fill('123'); const beforeResend = count('/auth/confirmation/resend'); await page.getByTestId('registration-resend').click();
  await invalid('registration-resend-password'); assert.equal(count('/auth/confirmation/resend'), beforeResend); await audit();
  done('confirmation resend: short password never reaches API');

  await goto('/login'); await page.getByTestId('login-submit').click(); await invalid('login-email'); await invalid('login-password'); await audit();
  await goto('/forgot-password'); const beforeForgot = count('/auth/forgot'); await page.getByTestId('login-email').fill('bad'); await page.getByTestId('login-submit').click(); await invalid('login-email'); assert.equal(count('/auth/forgot'), beforeForgot); await audit();
  await goto('/reset-password?code=invalid'); const beforeReset = count('/auth/reset'); await page.getByTestId('reset-password').fill('123'); await page.getByTestId('confirm-submit').click(); await invalid('reset-password'); assert.equal(count('/auth/reset'), beforeReset); await audit();
  done('login, recovery and password reset validate locally with Russian errors');

  await role('buyer'); const beforeProfile = count('/me');
  await page.getByTestId('profile-phone').fill('+7          '); await page.getByTestId('profile-city').fill('   '); await page.getByTestId('profile-postal-code').fill('12345'); await page.getByTestId('profile-submit').click();
  await invalid('profile-phone', /10 цифр/); await invalid('profile-city'); await invalid('profile-postal-code', /6 цифр/); assert.equal(count('/me'), beforeProfile); await audit();
  assert.equal(await page.getByTestId('profile-phone').inputValue(), '+7          ');
  await page.getByTestId('profile-phone').fill('+7 (900) 123-45-67'); await page.getByTestId('profile-city').fill(' Москва '); await page.getByTestId('profile-postal-code').fill('123456');
  const profile = page.waitForResponse((response) => response.url().endsWith('/me') && response.request().method() === 'PUT'); await page.getByTestId('profile-submit').click();
  const profileRequest = (await profile).request().postDataJSON(); assert.equal(profileRequest.phone, '+79001234567'); assert.equal(profileRequest.city, 'Москва');
  done('profile: phone digit count, required address, postal code, normalized request, preserved input');

  await goto('/catalog'); await named('catalog-items', 'catalog-item-card', 'catalog-item-name', 'Корм для собак').getByTestId('catalog-item-add').click(); await page.getByTestId('cart-count').waitFor();
  await goto('/checkout'); await page.getByTestId('checkout-phone').fill('123'); await page.getByTestId('checkout-submit').click(); await invalid('checkout-phone'); await audit();
  await page.getByTestId('checkout-phone').fill('+7 (900) 123-45-67'); await page.getByTestId('checkout-submit').click(); await page.waitForURL(/\/account\/orders\/[0-9a-f-]+$/);
  const beforePayment = requests.filter((path) => path.endsWith('/payments')).length;
  await page.getByTestId('payment-card').fill('123'); await page.getByTestId('payment-submit').click(); await invalid('payment-card', /16 цифр/); await audit();
  await page.getByTestId('payment-card').fill('1111 1111 1111 1111'); await page.getByTestId('payment-submit').click(); await invalid('payment-card', /Тестовые карты/); assert.equal(requests.filter((path) => path.endsWith('/payments')).length, beforePayment);
  done('checkout and demo payment reject invalid input without creating a payment');

  await role('admin'); await goto('/admin/products/new'); await page.getByTestId('admin-item-save-draft').click(); await invalid('admin-item-name');
  await page.getByTestId('admin-item-name').fill(' Проверка валидации '); await page.getByTestId('admin-item-price').fill('не цена'); await page.getByTestId('admin-item-stock').fill('-1'); await page.getByTestId('admin-item-save-draft').click(); await invalid('admin-item-price', /Введите цену/); await invalid('admin-item-stock', /отрицательным/);
  await page.getByTestId('admin-item-price').fill('12,345'); await page.getByTestId('admin-item-stock').fill('-1'); await page.getByTestId('admin-item-save-draft').click(); await invalid('admin-item-price', /копейки/); await invalid('admin-item-stock', /отрицательным/); await audit();
  await page.getByTestId('admin-item-price').fill('12,50'); await page.getByTestId('admin-item-stock').fill('2');
  const draft = page.waitForResponse((response) => response.url().endsWith('/admin/products') && response.request().method() === 'POST'); await page.getByTestId('admin-item-save-draft').click();
  const draftRequest = (await draft).request().postDataJSON(); assert.equal(draftRequest.price, 12.5); assert.equal(draftRequest.name, 'Проверка валидации'); await page.waitForURL(/\/admin\/products\/[0-9a-f-]+$/);
  await page.getByTestId('admin-item-publish').click(); await page.getByTestId('error-dismiss').click(); await invalid('admin-item-category-id'); await audit();
  done('item editor: empty numbers, negative stock, cents, decimal comma, draft versus publication');

  await goto('/admin/pets/new'); await page.getByTestId('admin-item-name').fill('Мика'); await page.getByTestId('admin-item-birth-date').fill('2099-01-01'); await page.getByTestId('admin-item-save-draft').click(); await invalid('admin-item-birth-date', /сегодняшней/); await audit();
  done('pet birth date rejects the future with an inline explanation');

  await goto('/admin/categories'); await page.getByTestId('admin-category-create').click(); const beforeCategory = count('/admin/categories'); await page.getByTestId('admin-category-name').fill('   '); await page.getByTestId('admin-category-submit').click(); await invalid('admin-category-name'); assert.equal(count('/admin/categories'), beforeCategory); await audit(); await page.getByTestId('category-dialog-close').click();
  done('category rejects a whitespace-only name without an API request');

  await goto('/admin/products'); await named('admin-items', 'admin-item-row', 'admin-item-title', 'Корм для собак').getByTestId('admin-item-edit').click(); await page.getByTestId('admin-item-stock-edit').click(); const beforeStock = requests.filter((path) => path.endsWith('/stock')).length;
  await page.getByTestId('stock-quantity').fill(''); await page.getByTestId('stock-reason').fill('   '); await page.getByTestId('stock-submit').click(); await invalid('stock-quantity'); await invalid('stock-reason');
  await page.getByTestId('stock-quantity').fill('1.5'); await page.getByTestId('stock-submit').click(); await invalid('stock-quantity', /целым/);
  await page.getByTestId('stock-quantity').fill('0'); await page.getByTestId('stock-reason').fill('Инвентаризация'); await page.getByTestId('stock-submit').click(); await invalid('stock-quantity', /резерва/); assert.equal(requests.filter((path) => path.endsWith('/stock')).length, beforeStock); await audit(); await page.getByTestId('stock-dialog-close').click();
  done('stock adjustment: blank values, integer quantity, meaningful reason and reservation floor');

  for (const width of [360, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/register', '/login', '/forgot-password', '/account', '/admin/products/new', '/admin/pets/new']) {
      await goto(route); await page.waitForTimeout(250); await audit();
      if (route === '/register' || route === '/account') await page.screenshot({ path: `qa/screenshots/forms-${route.slice(1)}-${width}.png`, fullPage: true });
    }
  }
  assert.deepEqual(errors, []); done('18 responsive form audits: placeholders, labels, hints, error associations and testids');
  await writeFile('qa/forms-result.json', JSON.stringify({ passed: true, baseUrl: base, results, runtimeErrors: errors, checkedAt: new Date().toISOString() }, null, 2));
  console.log(JSON.stringify({ passed: true, cases: results.length, runtimeErrors: errors }));
} catch (error) {
  await page.screenshot({ path: 'qa/screenshots/forms-failure.png', fullPage: true });
  await writeFile('qa/forms-result.json', JSON.stringify({ passed: false, results, failure: String(error), runtimeErrors: errors, url: page.url() }, null, 2));
  throw error;
} finally { await browser.close(); }
