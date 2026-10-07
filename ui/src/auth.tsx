import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { api, dataMode } from './api';
import { authSchema, forgotPasswordSchema, passwordResetSchema } from './validation';
import { ServiceError } from './errors';
import { useStore } from './store';
import { ActionLink, Button, Field } from './ui';
import { authPath, resumeRegistration, safeNext } from './registration';
import { MailInboxLink } from './features';

export function AuthPage() {
  const location = useLocation(), [params] = useSearchParams(), navigate = useNavigate(), store = useStore();
  const forgot = location.pathname === '/forgot-password', next = safeNext(params.get('next'));
  const emailFromRegistration = typeof location.state?.registrationEmail === 'string' ? location.state.registrationEmail : '';
  const [link, setLink] = useState<string | null | undefined>(undefined), [busy, setBusy] = useState(false);
  const form = useForm<{ email: string; password: string }>({ defaultValues: { email: emailFromRegistration, password: '' }, resolver: zodResolver(forgot ? forgotPasswordSchema : authSchema), mode: 'onBlur' });
  useEffect(() => { setLink(undefined); form.reset({ email: emailFromRegistration, password: '' }); }, [forgot, emailFromRegistration, form]);
  return <section className="auth-page">
    <ActionLink testId="auth-back" className="back-link" to="/">‹ В магазин</ActionLink>
    <h1>{forgot ? 'Восстановить пароль' : 'Вход в магазин'}</h1>
    {link !== undefined ? <div className="auth-result" data-testid="auth-result"><h2>Проверьте почту</h2><p>{dataMode === 'mock' ? 'В деморежиме письмо можно открыть прямо здесь.' : 'Если аккаунт с этой почтой существует, отправили письмо со ссылкой восстановления.'}</p>{link ? <ActionLink testId="auth-demo-link" className="primary-button" to={link}>Открыть письмо</ActionLink> : <p className="muted">Проверьте входящие письма и папку «Спам».</p>}<MailInboxLink /><ActionLink testId="auth-result-login" className="text-link" to={authPath('/login', next)}>Перейти ко входу</ActionLink></div> :
      <form noValidate data-testid={forgot ? 'forgot-password-form' : 'login-form'} onSubmit={form.handleSubmit(async (values) => {
        setBusy(true);
        try {
          if (forgot) { const response = await api.forgotPassword(values.email); setLink(response.demoLink); }
          else { await store.login(values.email, values.password); navigate(next); }
        } catch (failure) {
          if (!forgot && failure instanceof ServiceError && ['ACCOUNT_PENDING', 'ACCOUNT_NOT_VERIFIED'].includes(failure.code)) { resumeRegistration(values.email, next, values.password); navigate('/register/verify'); }
          else { if (failure instanceof ServiceError) failure.details.forEach((detail) => { if (detail.field === 'email' || detail.field === 'password') form.setError(detail.field, { message: 'Проверьте значение поля' }); }); store.report(failure); }
        } finally { setBusy(false); }
      })}>
        <Field label="Электронная почта" testId="login-email" required hint={forgot ? 'Отправим ссылку для восстановления на почту аккаунта.' : undefined} error={form.formState.errors.email?.message}><input data-testid="login-email" type="email" autoComplete="email" placeholder="name@example.com" maxLength={254} {...form.register('email')} /></Field>
        {!forgot && <Field label="Пароль" testId="login-password" required error={form.formState.errors.password?.message}><input data-testid="login-password" type="password" autoComplete="current-password" placeholder="Введите пароль" minLength={6} maxLength={100} {...form.register('password')} /></Field>}
        <Button testId="login-submit" type="submit" className="primary-button full-width" disabled={busy}>{busy ? 'Подождите…' : forgot ? 'Получить ссылку' : 'Войти'}</Button>
      </form>}
    <div className="auth-links">{forgot && <ActionLink testId="auth-login" to={authPath('/login', next)}>Вернуться ко входу</ActionLink>}<ActionLink testId="auth-register" to={authPath('/register', next)}>Создать аккаунт</ActionLink>{!forgot && <ActionLink testId="auth-forgot" to={authPath('/forgot-password', next)}>Не помню пароль</ActionLink>}{dataMode === 'mock' && <ActionLink testId="auth-demo" to="/demo">Демо-аккаунты для просмотра</ActionLink>}</div>
  </section>;
}
export function PasswordReset() {
  const [params] = useSearchParams(), [done, setDone] = useState(false), { report, logout } = useStore(), navigate = useNavigate();
  const form = useForm<{ password: string }>({ defaultValues: { password: '' }, resolver: zodResolver(passwordResetSchema), mode: 'onBlur' });
  return <section className="auth-page"><h1>{done ? 'Пароль обновлён' : 'Новый пароль'}</h1>{done ? <ActionLink testId="confirm-login" className="primary-button" to="/login">Войти в магазин</ActionLink> :
    <form noValidate data-testid="reset-password-form" onSubmit={form.handleSubmit(async ({ password }) => {
      try { await api.resetPassword(params.get('code'), password); if (dataMode === 'api') await logout(); setDone(true); navigate('/reset-password', { replace: true }); }
      catch (failure) { if (failure instanceof ServiceError && failure.details.some((detail) => detail.field === 'password' || detail.field === 'newPassword')) form.setError('password', { message: 'Проверьте новый пароль' }); report(failure); }
    })}>
      <Field label="Новый пароль" testId="reset-password" required hint="От 6 до 100 символов. Пароль не может состоять только из пробелов." error={form.formState.errors.password?.message}><input data-testid="reset-password" type="password" autoComplete="new-password" placeholder="Придумайте новый пароль" minLength={6} maxLength={100} {...form.register('password')} /></Field>
      <Button testId="confirm-submit" className="primary-button" type="submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Подождите…' : 'Сохранить пароль'}</Button>
    </form>}<div className="auth-links"><ActionLink testId="confirm-resend" to="/forgot-password">Получить новую ссылку</ActionLink></div></section>;
}
