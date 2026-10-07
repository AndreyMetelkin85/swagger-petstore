import { strict as assert } from 'node:assert';

// A testid names a UI role/action. Entity keys and changing state belong in data attributes.
export async function assertTestIdContract(page) {
  const issues = await page.evaluate(() => {
    const controls = [...document.querySelectorAll('button,input,select,textarea,a[href],summary')];
    const elements = [...document.querySelectorAll('[data-testid]')];
    const uuid = /[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}/i;
    const identities = {
      'catalog-item-card': 'data-item-id', 'cart-item': 'data-item-id',
      'admin-item-row': 'data-item-id', 'order-item': 'data-item-id',
      'order-card': 'data-order-id', 'admin-order-card': 'data-order-id',
      'admin-category-row': 'data-category-id', 'admin-user-row': 'data-user-id',
      'media-asset': 'data-media-id',
      'media-upload': 'data-upload-id', 'payment-attempt': 'data-payment-id',
      status: 'data-status',
    };
    return {
      missing: controls.filter((node) => !node.hasAttribute('data-testid')).map((node) => node.outerHTML.slice(0, 200)),
      malformed: elements.map((node) => node.getAttribute('data-testid')).filter((id) => !/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(id) || uuid.test(id)),
      missingIdentity: elements.filter((node) => identities[node.getAttribute('data-testid')] && !node.getAttribute(identities[node.getAttribute('data-testid')])).map((node) => node.outerHTML.slice(0, 200)),
    };
  });
  assert.deepEqual(issues, { missing: [], malformed: [], missingIdentity: [] });
}
