import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { isLive } from './api';
import { liveProfileSchema, normalizePhone, profileSchema } from './validation';
import type { Profile } from './models';
import { ServiceError } from './errors';
import { useStore } from './store';
import { Button, Field } from './ui';

export function ProfileForm({ initial, submit, testPrefix, buttonLabel = 'Сохранить', disabled = false }: { initial: Profile; submit: (profile: Profile) => Promise<void>; testPrefix: string; buttonLabel?: string; disabled?: boolean }) {
  const { report } = useStore(), form = useForm<Profile>({ defaultValues: initial, resolver: zodResolver(isLive ? liveProfileSchema : profileSchema), mode: 'onBlur' });
  const fields: { name: keyof Profile; label: string; autocomplete: string; placeholder: string; maxLength: number; hint?: string }[] = [
    ...(isLive ? [{ name: 'firstName' as const, label: 'Имя', autocomplete: 'given-name', placeholder: 'Анна', maxLength: 50 }, { name: 'lastName' as const, label: 'Фамилия', autocomplete: 'family-name', placeholder: 'Иванова', maxLength: 50 }] : [{ name: 'name' as const, label: 'Имя и фамилия', autocomplete: 'name', placeholder: 'Анна Иванова', maxLength: 100 }]),
    { name: 'phone', label: 'Телефон', autocomplete: 'tel', placeholder: '+7 (900) 123-45-67', maxLength: 30, hint: '+7 и 10 цифр номера. Пробелы, скобки и дефисы допустимы.' },
    { name: 'city', label: 'Город', autocomplete: 'address-level2', placeholder: 'Москва', maxLength: 100 },
    { name: 'street', label: 'Улица', autocomplete: 'address-line1', placeholder: 'Лесная', maxLength: 150 },
    { name: 'building', label: 'Дом', autocomplete: 'address-line2', placeholder: '12, корпус 2', maxLength: 30 },
    { name: 'apartment', label: 'Квартира (необязательно)', autocomplete: 'off', placeholder: '24', maxLength: 30 },
    { name: 'postalCode', label: 'Почтовый индекс', autocomplete: 'postal-code', placeholder: '123456', maxLength: 6, hint: 'Ровно 6 цифр.' },
  ];
  return <form noValidate data-layout={isLive ? 'api' : undefined} data-testid={`${testPrefix}-form`} onSubmit={form.handleSubmit(async (values) => {
    try { await submit({ ...values, phone: normalizePhone(values.phone) }); form.reset(values); }
    catch (failure) { if (failure instanceof ServiceError) failure.details.forEach((detail) => { const field = detail.field?.replace(/^address\./, '').replace(/^house$/, 'building'); if (field && field in values) form.setError(field as keyof Profile, { message: 'Проверьте значение поля' }); }); report(failure); }
  })}>
    <div className="profile-fields">{fields.map(({ name, label, autocomplete, placeholder, maxLength, hint }) => {
      const testId = `${testPrefix}-${name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
      return <Field key={name} label={label} testId={testId} required={name !== 'apartment'} hint={hint} error={form.formState.errors[name]?.message}>
        <input data-testid={testId} autoComplete={autocomplete} type={name === 'phone' ? 'tel' : 'text'} inputMode={name === 'postalCode' ? 'numeric' : undefined} placeholder={placeholder} maxLength={maxLength} disabled={form.formState.isSubmitting} {...form.register(name)} />
      </Field>;
    })}</div>
    <Button testId={`${testPrefix}-submit`} type="submit" className="primary-button" disabled={disabled || form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Сохраняем…' : buttonLabel}</Button>
  </form>;
}
