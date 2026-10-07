import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { api, dataMode } from './api';
import { authSchema, registrationSchema } from './validation';
import { friendlyError, ServiceError } from './errors';
import { useStore } from './store';
import { ActionLink, Button, Field, Loading } from './ui';
import { MailInboxLink } from './features';

const registrationKey = dataMode === 'api' ? 'lapki.registration.api.v1' : 'lapki.registration.v1';
type Registration = { email: string; name: string; username?: string; userId?: string; next: string; demoLink: string | null; confirmed: boolean; confirmedCode?: string };
let credentials: { email: string; password: string } | null = null;
export function clearRegistrationCredentials() { credentials = null; }
function heldPassword(email: string) { return credentials?.email.toLowerCase() === email.toLowerCase() ? credentials.password : ''; }
function localConfirmationUrl(value: string, userId?: string) {
  const url = new URL(value, location.origin), id = url.pathname.split('/').at(-1);
  const resolvedId = id && /^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id) ? id : userId;
  const code = url.searchParams.get('code');
  return resolvedId && code ? `/confirm/${resolvedId}?code=${encodeURIComponent(code)}` : null;
}
export function safeNext(value: string | null | undefined) { return value?.startsWith('/') && !value.startsWith('//') ? value : '/account'; }
export function authPath(path: string, next: string | null | undefined) { const destination = safeNext(next); return `${path}?next=${encodeURIComponent(destination)}`; }
export function readRegistration(): Registration | null {
  try { const saved = JSON.parse(sessionStorage.getItem(registrationKey) ?? 'null'); return saved && typeof saved.email === 'string' ? saved : null; } catch { return null; }
}
function saveRegistration(value: Registration) { sessionStorage.setItem(registrationKey, JSON.stringify(value)); }
export function resumeRegistration(email: string, next?: string | null, password?: string) {
  const current = readRegistration();
  const value: Registration = current?.email.toLowerCase() === email.toLowerCase() && !current.confirmed ? { ...current, next: safeNext(next ?? current.next) } : { email, name: '', next: safeNext(next), demoLink: null, confirmed: false };
  if (password) credentials = { email, password };
  saveRegistration(value); return value;
}
export function RegistrationFrame({ step, title, children }: { step: number; title: string; children: ReactNode }) {
  return <section className="auth-page registration-page"><ActionLink testId="registration-back-store" className="back-link" to="/">‹ В магазин</ActionLink><ol className="registration-steps" aria-label="Этапы регистрации" data-testid="registration-steps">{['Данные', 'Почта', 'Готово'].map((label, index) => <li key={label} className={index + 1 === step ? 'current' : index + 1 < step ? 'completed' : ''} aria-current={index + 1 === step ? 'step' : undefined}><span>{index + 1}</span>{label}</li>)}</ol><h1>{title}</h1>{children}</section>;
}
export function RegistrationPage() {
  const [params] = useSearchParams(), navigate = useNavigate(), store = useStore(), existing = readRegistration();
  const form = useForm<{ username: string; name?: string; email: string; password: string }>({ defaultValues: { username: existing?.confirmed ? '' : existing?.username ?? '', name: existing?.confirmed ? '' : existing?.name ?? '', email: existing?.confirmed ? '' : existing?.email ?? '', password: '' }, resolver: zodResolver(registrationSchema), mode: 'onBlur' });
  const next = safeNext(params.get('next') ?? existing?.next);
  return <RegistrationFrame step={1} title="Создать аккаунт"><p className="registration-intro">Заполните данные. На следующем шаге подтвердим вашу почту.</p><form noValidate data-testid="registration-form" onSubmit={form.handleSubmit(async (values) => {
    try {
      const result = await api.register(values);
      credentials = { email: values.email, password: values.password };
      saveRegistration({ email: values.email, name: values.name ?? '', username: values.username, userId: result.user.id, next, demoLink: dataMode === 'mock' ? localConfirmationUrl(result.confirmationUrl, result.user.id) : null, confirmed: false });
      form.reset({ username: values.username, name: values.name, email: values.email, password: '' });
      navigate('/register/verify');
    } catch (failure) { if (failure instanceof ServiceError) failure.details.forEach((detail) => { if (detail.field === 'email' || detail.field === 'username') form.setError(detail.field, { message: ['USER_ALREADY_EXISTS', 'USERNAME_ALREADY_EXISTS', 'EMAIL_ALREADY_EXISTS'].includes(failure.code) ? 'Уже используется другим аккаунтом' : 'Проверьте значение поля' }); }); store.report(failure); }
  })}><Field label="Логин" testId="registration-username" required hint="3–30 символов: латинские буквы, цифры, точка, дефис или подчёркивание." error={form.formState.errors.username?.message}><input data-testid="registration-username" autoComplete="username" placeholder="pet_lover" minLength={3} maxLength={30} {...form.register('username')} /></Field><Field label="Имя (необязательно)" testId="auth-name" error={form.formState.errors.name?.message}><input data-testid="auth-name" autoComplete="name" placeholder="Анна" maxLength={50} {...form.register('name')} /></Field><Field label="Электронная почта" testId="login-email" required error={form.formState.errors.email?.message}><input data-testid="login-email" type="email" autoComplete="email" placeholder="name@example.com" maxLength={254} {...form.register('email')} /></Field><Field label="Пароль" testId="login-password" required hint="От 6 до 100 символов. Пароль не может состоять только из пробелов." error={form.formState.errors.password?.message}><input data-testid="login-password" type="password" autoComplete="new-password" placeholder="Придумайте пароль" minLength={6} maxLength={100} {...form.register('password')} /></Field><Button testId="login-submit" type="submit" className="primary-button full-width" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Создаём аккаунт…' : 'Продолжить регистрацию'}</Button></form><div className="auth-links"><ActionLink testId="auth-login" to={authPath('/login', next)}>Уже есть аккаунт? Войти</ActionLink></div></RegistrationFrame>;
}
export function RegistrationVerification() {
  const initial = readRegistration(), [registration, setRegistration] = useState(initial), [email, setEmail] = useState(initial?.email ?? ''), [password, setPassword] = useState(heldPassword(initial?.email ?? '')), [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({}), [busy, setBusy] = useState(false), [sentAgain, setSentAgain] = useState(false), navigate = useNavigate(), store = useStore(), emailInput = useRef<HTMLInputElement>(null), passwordInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if (initial?.confirmed) navigate('/register/complete', { replace: true }); }, [initial?.confirmed, navigate]);
  async function resend() {
    const parsed = authSchema.safeParse({ email, password });
    if (!parsed.success) { const errors = parsed.error.flatten().fieldErrors; setFieldErrors({ email: errors.email?.[0], password: errors.password?.[0] }); if (errors.email) emailInput.current?.focus(); else passwordInput.current?.focus(); return; }
    setFieldErrors({});
    setBusy(true);
    try {
      const result = await api.resendConfirmation(parsed.data.email, parsed.data.password);
      credentials = { email: parsed.data.email, password: parsed.data.password };
      const link = localConfirmationUrl(result.confirmationUrl, registration?.userId);
      const value = { ...registration, email: parsed.data.email, name: registration?.name ?? '', userId: link?.split('/')[2]?.split('?')[0] ?? registration?.userId, next: safeNext(registration?.next), demoLink: dataMode === 'mock' ? link : null, confirmed: false };
      saveRegistration(value); setRegistration(value); setSentAgain(true); store.notify('Письмо подтверждения запрошено');
    } catch (failure) { if (failure instanceof ServiceError && failure.code === 'ACCOUNT_ALREADY_CONFIRMED') { saveRegistration({ email, name: registration?.name ?? '', next: safeNext(registration?.next), demoLink: null, confirmed: true }); clearRegistrationCredentials(); navigate('/register/complete'); } else store.report(failure); } finally { setBusy(false); }
  }
  return <RegistrationFrame step={2} title="Подтвердите вашу почту"><div className="registration-pending" data-testid="registration-pending"><p>Чтобы завершить регистрацию, перейдите по ссылке в письме.</p>{registration?.email && <p className="registration-email" data-testid="registration-email">{registration.email}</p>}<p className="form-hint">Если письма нет, проверьте папку «Спам» или отправьте его ещё раз.</p><MailInboxLink />{sentAgain && <p className="registration-sent" role="status" data-testid="registration-sent-again">Если адрес ожидает подтверждения, новое письмо отправлено. Предыдущая ссылка больше не действует.</p>}{dataMode === 'mock' && registration?.demoLink && <div className="registration-demo-mail"><p>В деморежиме письмо доступно прямо здесь.</p><ActionLink testId="auth-demo-link" className="primary-button full-width" to={registration.demoLink}>Открыть письмо</ActionLink></div>}<form noValidate data-testid="registration-resend-form" onSubmit={(event) => { event.preventDefault(); void resend(); }}>{!registration?.email && <Field label="Электронная почта аккаунта" testId="registration-email-input" required error={fieldErrors.email}><input data-testid="registration-email-input" ref={emailInput} placeholder="name@example.com" type="email" autoComplete="email" value={email} required maxLength={254} onChange={(event) => { setEmail(event.target.value); setFieldErrors((errors) => ({ ...errors, email: undefined })); }} /></Field>}{!heldPassword(email) && <Field label="Пароль аккаунта для повторной отправки" testId="registration-resend-password" required hint="Введите пароль, который указали при регистрации." error={fieldErrors.password}><input data-testid="registration-resend-password" ref={passwordInput} placeholder="Пароль аккаунта" type="password" autoComplete="current-password" required minLength={6} maxLength={100} value={password} onChange={(event) => { setPassword(event.target.value); setFieldErrors((errors) => ({ ...errors, password: undefined })); }} /></Field>}<Button testId="registration-resend" type="submit" className="outline-button full-width" disabled={busy}>{busy ? 'Отправляем…' : 'Отправить письмо повторно'}</Button></form><div className="auth-links"><ActionLink testId="registration-edit-email" to={authPath('/register', registration?.next)}>Изменить адрес почты</ActionLink><ActionLink testId="registration-login" to={authPath('/login', registration?.next)} state={{ registrationEmail: registration?.email }}>Вернуться ко входу</ActionLink></div></div></RegistrationFrame>;
}
export function RegistrationConfirmation() {
  const [params] = useSearchParams(), route = useParams(), code = params.get('code') ?? '', userId = route.userId ?? readRegistration()?.userId ?? '', navigate = useNavigate(), [failure, setFailure] = useState<unknown>(null), [attempt, setAttempt] = useState(0);
  const operation = useRef<{ userId: string; code: string; attempt: number; promise: Promise<void> } | null>(null);
  useEffect(() => {
    let active = true;
    if (!code || !userId) { setFailure(new ServiceError('INVALID_CONFIRMATION_LINK', 400)); return; }
    const existing = readRegistration();
    if (existing?.confirmed && existing.userId === userId && existing.confirmedCode === code) { navigate('/register/complete', { replace: true }); return; }
    setFailure(null);
    if (!operation.current || operation.current.userId !== userId || operation.current.code !== code || operation.current.attempt !== attempt) {
      const complete = () => {
        const current = readRegistration();
        const matching = current?.userId === userId && (current?.demoLink ? new URL(current.demoLink, location.origin).searchParams.get('code') === code : true);
        saveRegistration({ email: matching ? current?.email ?? '' : '', name: matching ? current?.name ?? '' : '', userId, next: safeNext(current?.next), demoLink: null, confirmed: true, confirmedCode: code }); clearRegistrationCredentials();
      };
      const promise = api.confirmRegistration(userId, code).then(complete).catch((error) => { if (error instanceof ServiceError && error.code === 'ACCOUNT_ALREADY_CONFIRMED') complete(); else throw error; });
      operation.current = { userId, code, attempt, promise };
    }
    operation.current.promise.then(() => { if (active) navigate('/register/complete', { replace: true }); }).catch((error) => { if (active) setFailure(error); });
    return () => { active = false; };
  }, [code, userId, attempt, navigate]);
  const message = friendlyError(failure);
  return <RegistrationFrame step={2} title={failure ? 'Не удалось подтвердить почту' : 'Подтверждаем вашу почту'}>{failure ? <div className="registration-confirm-error" role="alert" data-testid="registration-confirm-error"><h2>{message.title}</h2><p>{message.text}</p>{message.requestId && <p className="request-id">Номер обращения: {message.requestId}</p>}<div className="button-row">{failure instanceof ServiceError && !['LINK_EXPIRED', 'INVALID_CONFIRMATION_LINK', 'CONFIRMATION_LINK_EXPIRED', 'USER_NOT_FOUND'].includes(failure.code) && <Button testId="registration-confirm-retry" className="primary-button" onClick={() => setAttempt(attempt + 1)}>Повторить</Button>}<ActionLink testId="confirm-resend" className="outline-button" to="/register/verify">Получить новое письмо</ActionLink></div></div> : <Loading label="Завершаем регистрацию…" />}</RegistrationFrame>;
}
export function RegistrationComplete() {
  const registration = readRegistration(), navigate = useNavigate();
  useEffect(() => { if (!registration?.confirmed) navigate(registration?.email ? '/register/verify' : '/register', { replace: true }); }, [registration?.confirmed, registration?.email, navigate]);
  if (!registration?.confirmed) return <Loading />;
  return <RegistrationFrame step={3} title="Регистрация завершена"><div className="registration-success" data-testid="registration-complete"><p>Почта подтверждена. Теперь можно войти в магазин и оформлять заказы.</p><ActionLink testId="confirm-login" className="primary-button full-width" to={authPath('/login', registration.next)} state={{ registrationEmail: registration.email }}>Войти в магазин</ActionLink></div></RegistrationFrame>;
}
