import { z } from 'zod';
import type { Category, Item, Order, Payment, Profile, User } from './models';
import { ServiceError } from './errors.ts';

const uuid = z.string().uuid();
const money = z.union([z.number(), z.string().regex(/^\d+(?:\.\d+)?$/)]).transform(Number).refine(Number.isFinite);
const address = z.object({ city: z.string(), street: z.string(), house: z.string(), apartment: z.string().nullish(), postalCode: z.string() });
export const userDto = z.object({ id: uuid, username: z.string(), firstName: z.string().nullish(), lastName: z.string().nullish(), email: z.string(), phone: z.string().nullish(), address: address.nullish(), userStatus: z.enum(['PENDING', 'ACTIVE', 'BLOCKED']), role: z.enum(['USER', 'ADMIN']) });
const categoryDto = z.object({ id: uuid, name: z.string() });
export const petDto = z.object({ id: uuid, name: z.string(), category: categoryDto.nullish(), tags: z.array(categoryDto).nullish(), photoUrls: z.array(z.string()).nullish(), status: z.enum(['available', 'pending', 'reserved', 'sold']), version: z.number().int().nonnegative(), price: money, currency: z.literal('RUB') });
export type PetDto = z.infer<typeof petDto>;
export const orderDto = z.object({ id: uuid, userId: uuid, petId: uuid, quantity: z.number().int().positive(), createdAt: z.string(), status: z.enum(['draft', 'placed', 'approved', 'shipped', 'delivered', 'cancelled', 'expired']), unitPrice: money.nullish(), totalAmount: money.nullish(), currency: z.literal('RUB'), deliveryDetails: z.object({ firstName: z.string(), lastName: z.string(), phone: z.string(), address }).nullish(), paymentStatus: z.enum(['NOT_STARTED', 'NOT_REQUIRED', 'UNPAID', 'PAID', 'REFUNDED', 'EXPIRED']), paymentExpiresAt: z.string().nullish() });
export const paymentDto = z.object({ id: uuid, orderId: uuid, amount: money, currency: z.literal('RUB'), status: z.enum(['SUCCEEDED', 'DECLINED', 'REFUNDED']), cardBrand: z.string(), cardLast4: z.string().regex(/^\d{4}$/), failureCode: z.string().nullish(), createdAt: z.string(), updatedAt: z.string() });
export type OrderDto = z.infer<typeof orderDto>;
export type PaymentInput = { cardNumber: string; expiryMonth: number; expiryYear: number; cvv: string; cardholderName: string };

export function decode<S extends z.ZodTypeAny>(schema: S, value: unknown): z.output<S> {
  const result = schema.safeParse(value);
  if (!result.success) throw new ServiceError('API_CONTRACT_MISMATCH', 502);
  return result.data;
}
export function mapProfile(value: { firstName?: string | null; lastName?: string | null; phone?: string | null; address?: z.infer<typeof address> | null }): Profile {
  const firstName = value.firstName ?? '', lastName = value.lastName ?? '';
  return { name: [firstName, lastName].filter(Boolean).join(' '), firstName, lastName, phone: value.phone ?? '', city: value.address?.city ?? '', street: value.address?.street ?? '', building: value.address?.house ?? '', apartment: value.address?.apartment ?? '', postalCode: value.address?.postalCode ?? '' };
}
export function mapUser(value: unknown): User {
  const user = decode(userDto, value);
  return { id: user.id, username: user.username, email: user.email, role: user.role, status: user.userStatus, profile: mapProfile(user) };
}
export function profilePayload(profile: Profile) {
  return { firstName: profile.firstName ?? '', lastName: profile.lastName ?? '', phone: profile.phone, address: { city: profile.city, street: profile.street, house: profile.building, apartment: profile.apartment || null, postalCode: profile.postalCode } };
}
export function mapPet(value: unknown): Item {
  const pet = decode(petDto, value), name = pet.category?.name.trim().toLowerCase();
  const animal = name && ['dog', 'dogs', 'собака', 'собаки'].includes(name) ? 'dog' : name && ['cat', 'cats', 'кошка', 'кошки'].includes(name) ? 'cat' : 'other';
  return { id: pet.id, kind: 'pet', category: 'pet', animalTypes: [animal], name: pet.name, description: '', subtitle: pet.category?.name ?? 'Питомец', price: pet.price, stock: 1, reserved: pet.status === 'reserved' ? 1 : 0, visual: animal === 'cat' ? 'cat' : 'dog', color: '', version: pet.version, sku: '', categoryId: pet.category?.id ?? '', brand: '', productType: 'OTHER', feedForm: '', lifeStages: [], netWeightGrams: 0, ingredients: '', publicationStatus: 'PUBLISHED', images: (pet.photoUrls ?? []).map((url) => ({ url, alt: pet.name })), status: pet.status, breed: '', sex: '', birthDate: '' };
}
export function mapCategories(values: PetDto[]): Category[] {
  return [...new Map(values.filter((pet) => pet.category).map((pet) => [pet.category!.id, { id: pet.category!.id, name: pet.category!.name, kind: 'pet' as const, version: 0, archived: false }])).values()];
}
export function mapPayment(value: unknown): Payment {
  const payment = decode(paymentDto, value);
  return { id: payment.id, status: payment.status, last4: payment.cardLast4, createdAt: payment.createdAt };
}
export function mapOrder(value: unknown, pet?: Item, payments: Payment[] = []): Order {
  const order = decode(orderDto, value), price = order.unitPrice ?? pet?.price ?? 0;
  return { id: order.id, userId: order.userId, version: 0, cartVersion: 0, status: order.status.toUpperCase() as Order['status'], paymentStatus: order.paymentStatus, createdAt: order.createdAt, reserveUntil: order.paymentExpiresAt ?? null, lines: [{ itemId: order.petId, kind: 'pet', name: pet?.name ?? 'Питомец', sku: '', quantity: order.quantity, price, images: pet?.images ?? [] }], total: order.totalAmount ?? price * order.quantity, delivery: order.deliveryDetails ? mapProfile(order.deliveryDetails) : null, payments, estimated: order.totalAmount == null };
}
