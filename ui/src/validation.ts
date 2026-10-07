import { z } from 'zod';

z.setErrorMap(() => ({ message: 'Проверьте значение поля' }));
const text = (label: string, max: number) => z.string().trim().min(1, `Укажите ${label}`).max(max, `Не более ${max} символов`);
export const emailSchema = z.string().trim().min(1, 'Введите электронную почту').email('Укажите почту в формате name@example.com').max(254, 'Не более 254 символов');
export const passwordSchema = z.string().min(6, 'Пароль должен содержать не менее 6 символов').max(100, 'Пароль должен содержать не более 100 символов').refine((value) => !!value.trim(), 'Пароль не может состоять только из пробелов');
export const authSchema = z.object({ email: emailSchema, password: passwordSchema });
export const forgotPasswordSchema = authSchema.pick({ email: true });
export const passwordResetSchema = authSchema.pick({ password: true });
export const registrationSchema = authSchema.extend({ username: z.string().trim().min(3, 'Логин должен содержать не менее 3 символов').max(30, 'Не более 30 символов').regex(/^[A-Za-z0-9_.-]+$/, 'Используйте латинские буквы, цифры, точку, дефис или подчёркивание'), name: z.string().trim().max(50, 'Не более 50 символов').optional() });

export const normalizePhone = (value: string) => value.trim().replace(/[\s()-]/g, '');
export const profileSchema = z.object({
  name: z.string().trim().min(2, 'Введите имя и фамилию: не менее 2 символов').max(100, 'Не более 100 символов'),
  phone: z.string().trim().refine((value) => /^\+7[\d ()-]+$/.test(value) && /^\+7\d{10}$/.test(normalizePhone(value)), 'Введите +7 и 10 цифр номера, например +7 (900) 123-45-67'),
  city: text('город', 100), street: text('улицу', 150), building: text('номер дома', 30), apartment: z.string().trim().max(30, 'Не более 30 символов'),
  postalCode: z.string().trim().regex(/^\d{6}$/, 'Введите индекс из 6 цифр'),
});
export const liveProfileSchema = profileSchema.omit({ name: true }).extend({
  firstName: text('имя', 50), lastName: text('фамилию', 50),
}).transform((value) => ({ ...value, name: `${value.firstName} ${value.lastName}` }));

// Empty numeric fields must not silently become zero. Russian decimal commas are accepted.
export function numberInput(value: unknown): number {
  if (typeof value === 'number') return value;
  if (typeof value !== 'string' || !value.trim() || !/^[+-]?\d+(?:[.,]\d+)?$/.test(value.trim())) return NaN;
  return Number(value.trim().replace(',', '.'));
}
const number = (message: string) => z.number({ invalid_type_error: message }).finite(message);
const numeric = <T extends z.ZodTypeAny>(schema: T) => z.preprocess(numberInput, schema);
export const categorySchema = z.object({ name: text('название категории', 80), kind: z.enum(['product', 'pet']) });
export const stockAdjustmentSchema = (reserved: number) => z.object({
  quantity: numeric(number('Введите количество').int('Количество должно быть целым').min(reserved, `Остаток не может быть меньше резерва: ${reserved}`)),
  reason: text('причину изменения остатка', 300),
});
export const todayDate = () => new Date().toLocaleDateString('sv-SE');
export function validBirthDate(value: string, today = todayDate()) {
  if (!value) return true;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value > today) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}
export const itemSchema = z.object({
  id: z.string(), version: z.number(), kind: z.enum(['product', 'pet']), name: text('название', 150), description: z.string().trim().max(4000, 'Не более 4000 символов'), subtitle: z.string(), sku: z.string().trim().max(80, 'Не более 80 символов'), categoryId: z.string(), brand: z.string().trim().max(80, 'Не более 80 символов'),
  price: numeric(number('Введите цену').min(0, 'Цена не может быть отрицательной').refine((value) => Math.abs(value * 100 - Math.round(value * 100)) < 1e-8, 'Укажите цену с точностью до копейки')), stock: numeric(number('Введите остаток').int('Укажите целое количество').min(0, 'Остаток не может быть отрицательным')), reserved: z.number(), publicationStatus: z.enum(['DRAFT', 'PUBLISHED', 'ARCHIVED']),
  productType: z.enum(['FEED', 'TREAT', 'TOY', 'ACCESSORY', 'HYGIENE', 'OTHER']), feedForm: z.enum(['', 'DRY', 'WET']), netWeightGrams: numeric(number('Введите вес в граммах').int('Укажите вес в целых граммах').min(0, 'Вес не может быть отрицательным')), lifeStages: z.array(z.enum(['YOUNG', 'ADULT', 'SENIOR', 'ALL'])), ingredients: z.string().trim().max(4000, 'Не более 4000 символов'),
  animalTypes: z.array(z.enum(['dog', 'cat', 'bird', 'rodent', 'fish', 'reptile', 'other'])), images: z.array(z.object({ mediaId: z.string().optional(), url: z.string().optional(), alt: z.string().max(200, 'Не более 200 символов') })).max(20, 'Не более 20 фотографий'),
  status: z.enum(['available', 'pending', 'reserved', 'sold']), category: z.enum(['food', 'accessory', 'pet']), visual: z.enum(['food', 'bowl', 'bed', 'dog', 'cat']), color: z.string(), breed: z.string().trim().max(100, 'Не более 100 символов'), sex: z.enum(['', 'male', 'female', 'MALE', 'FEMALE']), birthDate: z.string().refine((value) => validBirthDate(value), 'Укажите существующую дату, не позднее сегодняшней'),
});
const draftNumber = (value: unknown) => typeof value === 'string' && !value.trim() ? 0 : value;
export const commerceItemSchema = itemSchema.extend({
  price: z.preprocess(draftNumber, itemSchema.shape.price),
  stock: z.preprocess(draftNumber, itemSchema.shape.stock),
  netWeightGrams: z.preprocess(draftNumber, itemSchema.shape.netWeightGrams),
}).superRefine((item, context) => {
  const issue = (field: string, message: string) => context.addIssue({ code: 'custom', path: [field], message });
  if (item.price > 9999999999.99) issue('price', 'Цена не более 9 999 999 999,99 ₽');
  if (item.stock > 1000000) issue('stock', 'Не более 1 000 000 единиц');
  if (item.kind === 'pet' && item.name.length > 100) issue('name', 'Не более 100 символов');
  if (item.kind === 'product') {
    if (item.sku && !/^[A-Za-z0-9_.-]{1,64}$/.test(item.sku)) issue('sku', 'От 1 до 64 символов: латинские буквы, цифры, точка, дефис, подчёркивание');
    if (item.productType === 'FEED') {
      if (item.netWeightGrams > 1000000) issue('netWeightGrams', 'Вес не более 1 000 000 граммов');
    }
  }
  if (item.lifeStages.includes('ALL') && item.lifeStages.length !== 1) issue('lifeStages', 'Все возрасты нельзя совмещать с другими группами');
});
export const publicationError: Record<string, string> = { name: 'Введите название', description: 'Добавьте описание перед публикацией', categoryId: 'Выберите категорию', price: 'Для публикации цена должна быть больше нуля', animalTypes: 'Выберите хотя бы одно животное', images: 'Добавьте хотя бы одну фотографию', sku: 'Укажите артикул', brand: 'Укажите производителя корма', feedForm: 'Выберите форму корма', lifeStages: 'Выберите возраст животного', netWeightGrams: 'Для публикации вес упаковки должен быть больше нуля', stock: 'Укажите целое неотрицательное количество' };
export const demoCardSchema = z.string().transform((value) => value.replace(/\s/g, '')).refine((value) => /^\d{16}$/.test(value), 'Введите номер тестовой карты из 16 цифр').refine((value) => ['4242424242424242', '4000000000000002', '4000000000009995'].includes(value), 'Используйте одну из карт в списке «Тестовые карты»');
export function livePaymentSchema(now = new Date()) {
  return z.object({ cardNumber: demoCardSchema, expiryMonth: numeric(number('Введите месяц').int('Введите целый месяц').min(1, 'Месяц от 1 до 12').max(12, 'Месяц от 1 до 12')), expiryYear: numeric(number('Введите год').int('Введите год из 4 цифр').min(now.getUTCFullYear(), 'Срок действия карты истёк').max(2200, 'Укажите год не позднее 2200')), cvv: z.string().regex(/^\d{3,4}$/, 'Введите CVV/CVC из 3 или 4 цифр'), cardholderName: text('имя владельца карты', 100) }).superRefine((value, context) => { if (value.expiryYear === now.getUTCFullYear() && value.expiryMonth < now.getUTCMonth() + 1) context.addIssue({ code: 'custom', path: ['expiryMonth'], message: 'Срок действия карты истёк' }); });
}
export const legacyPetSchema = z.object({ name: text('имя питомца', 100), price: numeric(number('Введите цену').positive('Цена должна быть больше нуля').refine((value) => Math.abs(value * 100 - Math.round(value * 100)) < 1e-8, 'Укажите цену с точностью до копейки')), status: z.enum(['available', 'pending', 'sold', 'reserved']), photoUrls: z.string().refine((value) => value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean).length <= 20, 'Не более 20 фотографий').refine((value) => value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean).every((url) => { try { const parsed = new URL(url); return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password && url.length <= 2048 && !/\s/.test(url); } catch { return false; } }), 'Укажите полные ссылки http:// или https:// — по одной на строке') });
