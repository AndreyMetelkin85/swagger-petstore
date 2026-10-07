export type Design = 'bethowen' | 'calm' | 'editorial' | 'essential';
export type CatalogItem = {
  id: string;
  kind: 'product' | 'pet';
  category: 'food' | 'accessory' | 'pet';
  animalTypes: ('dog' | 'cat')[];
  name: string;
  subtitle: string;
  price: number;
  stock: number;
  visual: 'food' | 'bowl' | 'bed' | 'dog' | 'cat';
  color: string;
  description: string;
};
export type CartLine = { id: string; quantity: number; name?: string; kind?: 'product' | 'pet'; price?: number | null; quotedPrice?: number | null; available?: boolean; reason?: string | null; priceChanged?: boolean; images?: { mediaId?: string; url?: string; alt: string }[] };

export const items: CatalogItem[] = [
  { id: 'food-dog', kind: 'product', category: 'food', animalTypes: ['dog'], name: 'Корм для собак', subtitle: 'Лапки · индейка · 2 кг', price: 1490, stock: 8, visual: 'food', color: '#7b8b64', description: 'Демонстрационный сухой корм для взрослых собак. Фасовка 2 кг. Состав и свойства в рабочем магазине будут заполняться по данным производителя.' },
  { id: 'food-cat', kind: 'product', category: 'food', animalTypes: ['cat'], name: 'Корм для кошек', subtitle: 'Лапки · лосось · 1,5 кг', price: 1290, stock: 6, visual: 'food', color: '#bb7d65', description: 'Демонстрационный сухой корм для взрослых кошек. Фасовка 1,5 кг. Вымышленная упаковка создана только для оценки интерфейса.' },
  { id: 'bowl', kind: 'product', category: 'accessory', animalTypes: ['dog', 'cat'], name: 'Керамическая миска', subtitle: 'Песочный · 500 мл', price: 790, stock: 4, visual: 'bowl', color: '#c4b398', description: 'Простая керамическая миска с устойчивым основанием. Демонстрационный товар; характеристики и фотографии будут заменены перед подключением реального каталога.' },
  { id: 'bed', kind: 'product', category: 'accessory', animalTypes: ['dog', 'cat'], name: 'Мягкое место', subtitle: 'Оливковый · 60 × 45 см', price: 3490, stock: 3, visual: 'bed', color: '#8e957c', description: 'Мягкая лежанка со съёмным чехлом. Демонстрационный товар для проверки карточки, количества и единой корзины.' },
  { id: 'pet-dog', kind: 'pet', category: 'pet', animalTypes: ['dog'], name: 'Солнечный Тедди', subtitle: 'Собака · 1 год · мальчик', price: 25000, stock: 1, visual: 'dog', color: '#e8d9c2', description: 'Любознательный и дружелюбный компаньон. Персонаж и фотография созданы для макета. В рабочем магазине здесь будут настоящие сведения о конкретном питомце и его фотографии.' },
  { id: 'pet-cat', kind: 'pet', category: 'pet', animalTypes: ['cat'], name: 'Кошка Мика', subtitle: 'Кошка · 8 месяцев · девочка', price: 15000, stock: 1, visual: 'cat', color: '#e8d9c2', description: 'Спокойная кошка, которая любит солнечные места. Персонаж и фотография созданы для макета; это не объявление о продаже реального животного.' },
];

export const money = (value: number) => new Intl.NumberFormat('ru-RU', {
  style: 'currency', currency: 'RUB', minimumFractionDigits: 0, maximumFractionDigits: 2,
}).format(value);

export function setQuantity(cart: CartLine[], id: string, quantity: number): CartLine[] {
  const item = items.find((entry) => entry.id === id);
  if (!item || !Number.isInteger(quantity) || quantity < 0) throw new Error('INVALID_QUANTITY');
  if (quantity > item.stock || (item.kind === 'pet' && quantity > 1)) throw new Error('INSUFFICIENT_STOCK');
  const rest = cart.filter((line) => line.id !== id);
  if (quantity === 0) return rest;
  const existing = cart.findIndex((line) => line.id === id);
  if (existing < 0) return [...rest, { id, quantity }];
  return cart.map((line) => line.id === id ? { id, quantity } : line);
}

export function parseCart(raw: unknown): CartLine[] {
  if (!Array.isArray(raw)) return [];
  let cart: CartLine[] = [];
  for (const line of raw) {
    if (line && typeof line.id === 'string' && Number.isInteger(line.quantity) && line.quantity > 0) {
      const item = items.find((entry) => entry.id === line.id);
      if (item) cart = setQuantity(cart, item.id, Math.min(line.quantity, item.stock));
    }
  }
  return cart;
}

export const cartTotal = (cart: CartLine[]) => cart.reduce((sum, line) => {
  const item = items.find((entry) => entry.id === line.id);
  return sum + (item?.price ?? 0) * line.quantity;
}, 0);

export const friendlyErrors: Record<string, { title: string; message: string }> = {
  INSUFFICIENT_STOCK: { title: 'Столько пока нет в наличии', message: 'Уменьшите количество. Остальные товары останутся в корзине.' },
  PAYMENT_DECLINED: { title: 'Оплата не прошла', message: 'Попробуйте ещё раз. Корзина сохранена, деньги не списаны.' },
  UNEXPECTED: { title: 'Не получилось завершить действие', message: 'Попробуйте ещё раз чуть позже. Ваши данные сохранены.' },
};
