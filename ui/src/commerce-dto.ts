import { z } from 'zod';
import type { Cart, Category, Item, Order } from './models';
import { decode, mapProfile } from './backend-dto.ts';
import { ServiceError } from './errors.ts';

const uuid = z.string().uuid();
const money = z.union([z.number(), z.string().regex(/^\d+(?:\.\d+)?$/)]).transform(Number).refine(Number.isFinite);
const animal = z.enum(['dog', 'cat', 'bird', 'rodent', 'fish', 'reptile', 'other']);
const image = z.object({ mediaId: uuid, alt: z.string(), isCover: z.boolean(), position: z.number().int(), imageUrl: z.string(), thumbUrl: z.string() });
const common = z.object({ id: uuid, name: z.string(), description: z.string(), categoryId: uuid.nullable(), price: money.nullable(), currency: z.literal('RUB'), publicationStatus: z.enum(['DRAFT', 'PUBLISHED', 'ARCHIVED']), version: z.number().int().nonnegative(), images: z.array(image) });
export const productCardDto = common.extend({ kind: z.literal('product'), sku: z.string().nullable(), brand: z.string(), productType: z.enum(['FEED', 'TREAT', 'TOY', 'ACCESSORY', 'HYGIENE', 'OTHER']).nullable(), animalTypes: z.array(animal), feedForm: z.enum(['', 'DRY', 'WET']), lifeStages: z.array(z.string()), netWeightGrams: z.number().int().nullable(), ingredients: z.string(), stock: z.number().int(), reserved: z.number().int(), availableQuantity: z.number().int() });
export const petCardDto = common.extend({ kind: z.literal('pet'), animalType: animal.nullable(), breed: z.string(), sex: z.enum(['MALE', 'FEMALE', 'UNKNOWN']), birthDate: z.string().nullable(), status: z.enum(['available', 'pending', 'reserved', 'sold']), photoUrls: z.array(z.string()) });
export const cardDto = z.discriminatedUnion('kind', [productCardDto, petCardDto]);
export const pageDto = z.object({ items: z.array(cardDto), page: z.number().int().positive(), pageSize: z.number().int().positive(), total: z.number().int().nonnegative() });
export const commerceCategoryDto = z.object({ id: uuid, name: z.string(), kind: z.enum(['product', 'pet']), active: z.boolean(), archived: z.boolean(), version: z.number().int() });
export const commerceCartDto = z.object({ version: z.number().int().positive(), lines: z.array(z.object({ id: uuid, kind: z.enum(['product', 'pet']), quantity: z.number().int().positive(), name: z.string(), price: money.nullable(), quotedPrice: money.nullable(), priceChanged: z.boolean(), available: z.boolean(), reason: z.string().nullable(), images: z.array(image), currency: z.literal('RUB') })) });
const deliveryDto = z.object({ firstName: z.string(), lastName: z.string(), phone: z.string(), address: z.object({ city: z.string(), street: z.string(), house: z.string(), apartment: z.string().nullish(), postalCode: z.string() }) });
export const commerceOrderDto = z.object({ id: uuid, userId: uuid, version: z.number().int(), cartVersion: z.number().int().nullish(), status: z.enum(['draft', 'placed', 'approved', 'shipped', 'delivered', 'cancelled', 'expired']), paymentStatus: z.enum(['NOT_STARTED', 'NOT_REQUIRED', 'UNPAID', 'PAID', 'REFUNDED', 'EXPIRED']), createdAt: z.string(), paymentExpiresAt: z.string().nullish(), currency: z.literal('RUB'), total: money.nullable(), delivery: deliveryDto.nullable(), lines: z.array(z.object({ itemId: uuid, kind: z.enum(['product', 'pet']), name: z.string(), sku: z.string(), quantity: z.number().int().positive(), price: money.nullable(), images: z.array(image) })) });

function mapImages(images: z.infer<typeof image>[]) {
  return [...images].sort((a, b) => Number(b.isCover) - Number(a.isCover) || a.position - b.position).map(({ mediaId, alt }) => ({ mediaId, alt }));
}
export function mapCard(value: unknown): Item {
  const card = decode(cardDto, value);
  const base = { ...card, price: card.price ?? 0, categoryId: card.categoryId ?? '', images: mapImages(card.images), color: '', sku: '', brand: '', productType: 'OTHER' as const, feedForm: '' as const, lifeStages: [] as string[], netWeightGrams: 0, ingredients: '', stock: 1, reserved: 0, status: 'available' as const, breed: '', sex: '', birthDate: '' };
  if (card.kind === 'product') return { ...base, ...card, price: card.price ?? 0, sku: card.sku ?? '', productType: card.productType ?? 'OTHER', categoryId: card.categoryId ?? '', images: mapImages(card.images), netWeightGrams: card.netWeightGrams ?? 0, animalTypes: card.animalTypes, category: card.productType === 'FEED' || card.productType === 'TREAT' ? 'food' : 'accessory', visual: card.productType === 'FEED' ? 'food' : 'bowl', subtitle: [card.brand, card.netWeightGrams ? `${card.netWeightGrams} г` : ''].filter(Boolean).join(' · ') };
  return { ...base, breed: card.breed, sex: card.sex === 'UNKNOWN' ? '' : card.sex, birthDate: card.birthDate ?? '', status: card.status, reserved: card.status === 'reserved' ? 1 : 0, category: 'pet', visual: card.animalType === 'cat' ? 'cat' : 'dog', animalTypes: card.animalType ? [card.animalType] : [], subtitle: card.breed || 'Питомец', images: card.images.length ? mapImages(card.images) : card.photoUrls.map((url) => ({ url, alt: card.name })) };
}
export const mapCommerceCategory = (value: unknown): Category => decode(commerceCategoryDto, value);
export function mapCommerceCart(value: unknown): Cart {
  const cart = decode(commerceCartDto, value);
  return { version: cart.version, lines: cart.lines.map((line) => ({ ...line, images: mapImages(line.images) })) };
}
export function cartPayload(cart: Cart) {
  return { version: cart.version, lines: cart.lines.map(({ id, quantity, kind }) => {
    if (!kind) throw new ServiceError('API_CONTRACT_MISMATCH', 502);
    return { id, kind, quantity };
  }) };
}
export function mapCommerceOrder(value: unknown): Order {
  const order = decode(commerceOrderDto, value);
  const lines = order.lines.map((line) => ({ ...line, price: line.price ?? 0, images: mapImages(line.images) }));
  return { id: order.id, userId: order.userId, version: order.version, cartVersion: order.cartVersion ?? 0, status: order.status.toUpperCase() as Order['status'], paymentStatus: order.paymentStatus, createdAt: order.createdAt, reserveUntil: order.paymentExpiresAt ?? null, delivery: order.delivery ? mapProfile(order.delivery) : null, lines, total: order.total ?? lines.reduce((sum, line) => sum + Math.round(line.price * 100) * line.quantity, 0) / 100, payments: [], estimated: order.total == null };
}
export function cardPayload(item: Item, creating: boolean) {
  const common = { name: item.name.trim(), description: item.description, categoryId: item.categoryId || null, price: item.price || null, images: item.images.filter((image) => image.mediaId).map(({ mediaId, alt }, index) => {
    if (!mediaId) throw new ServiceError('IMAGE_REQUIRED', 422);
    return { mediaId, alt, isCover: index === 0 };
  }), ...(!creating ? { version: item.version } : {}) };
  return item.kind === 'pet' ? { ...common, animalType: item.animalTypes[0] ?? null, breed: item.breed, sex: item.sex.toUpperCase() || 'UNKNOWN', birthDate: item.birthDate || null } : { ...common, sku: item.sku.trim() || null, brand: item.brand, productType: item.productType, animalTypes: item.animalTypes, feedForm: item.feedForm, lifeStages: item.lifeStages, netWeightGrams: item.netWeightGrams || null, ingredients: item.ingredients, ...(creating ? { stock: item.stock } : {}) };
}
