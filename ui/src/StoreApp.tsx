import { Component, useEffect, useState, type ErrorInfo, type ReactNode } from 'react';
import { createBrowserRouter, Navigate, Outlet, RouterProvider, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Cat, Dog, Menu, PawPrint, Search, ShoppingBag, UserRound } from 'lucide-react';
import { dataMode, isLive } from './api';
import { FeaturePending } from './features';
import { StoreProvider, useStore } from './store';
import { ActionLink, Button, Empty } from './ui';
import { About, Catalog, Home, ItemDetail } from './catalog';
import { Account, CartPage, Checkout, OrderDetail, Orders, RequireUser } from './customer';
import { AuthPage, PasswordReset } from './auth';
import { clearRegistrationCredentials, RegistrationComplete, RegistrationConfirmation, RegistrationPage, RegistrationVerification } from './registration';
import { AdminCategories, AdminItems, AdminLayout, AdminOrders, AdminOverview, AdminUsers, DemoPage, ItemEditor, LiveLogs } from './admin';
import { log } from './logger';
function Root() { return <StoreProvider><Chrome /></StoreProvider>; }
function RouteFailure() { return <div className="startup-error"><h1>Не удалось открыть страницу</h1><p>Попробуйте обновить приложение. Сохранённые данные останутся в браузере.</p><Button testId="route-retry" className="primary-button" onClick={() => location.reload()}>Обновить</Button></div>; }
function Chrome() {
  const store = useStore(), location = useLocation(), navigate = useNavigate(), [search, setSearch] = useState('');
  const count = store.lines.reduce((sum, line) => sum + line.quantity, 0);
  useEffect(() => { if (!location.pathname.startsWith('/register') && !location.pathname.startsWith('/confirm') && location.pathname !== '/login') clearRegistrationCredentials(); }, [location.pathname]);
  useEffect(() => { window.scrollTo(0, 0); document.title = location.pathname.startsWith('/admin') ? 'Лапки · Управление магазином' : 'Лапки · Зоомагазин'; log('page_opened', { routeId: location.pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, ':id') }); }, [location.pathname]);
  return <div className="app theme-bethowen"><header className="store-header"><div className="store-header-main shell"><ActionLink testId="nav-home" className="logo" to="/" aria-label="Лапки — на главную"><PawPrint size={33} strokeWidth={2.5} /><span>лапки</span></ActionLink><form className="header-search-form" onSubmit={(event) => { event.preventDefault(); navigate(`/catalog${search.trim() ? `?q=${encodeURIComponent(search.trim())}` : ''}`); }}><input data-testid="header-search" type="search" aria-label="Поиск по каталогу товаров" placeholder="Найти что-нибудь для питомца" value={search} onChange={(event) => setSearch(event.target.value)} /><Button testId="header-search-submit" type="submit" aria-label="Найти" className="icon-button"><Search size={23} /></Button></form><div className="header-actions"><ActionLink testId="open-account" className="account-button" to={store.user ? '/account' : '/login'}><UserRound size={24} /><span>{store.user ? 'Кабинет' : 'Войти'}</span></ActionLink><ActionLink testId="open-cart" className="cart-button" to="/cart" aria-label={`Корзина, товаров: ${count}`}><ShoppingBag size={24} /><span className="cart-label">Корзина</span>{count > 0 && <span className="cart-count" data-testid="cart-count">{count}</span>}</ActionLink></div></div><nav className="store-nav shell" aria-label="Основная навигация"><ActionLink testId="nav-catalog" className="catalog-button" to="/catalog"><Menu size={19} />Каталог</ActionLink><ActionLink testId="nav-dogs" to="/catalog?animal=dog"><Dog size={19} />Для собак</ActionLink><ActionLink testId="nav-cats" to="/catalog?animal=cat"><Cat size={19} />Для кошек</ActionLink><ActionLink testId="nav-home-goods" to="/catalog?type=accessory">Для дома</ActionLink><ActionLink testId="nav-pets" to="/pets"><PawPrint size={18} />Питомцы</ActionLink><ActionLink testId="nav-about" className="nav-about" to="/about">О магазине</ActionLink></nav></header><main className="shell" id="main-content"><Outlet /></main><footer className="site-footer shell"><ActionLink testId="footer-home" className="footer-logo" to="/">лапки</ActionLink><span>Забота в простых вещах</span><ActionLink testId="footer-orders" to="/account/orders">Мои заказы</ActionLink>{dataMode === 'mock' && <ActionLink testId="footer-demo" className="footer-demo" to="/demo">Демонстрационный магазин <ArrowRight size={13} /></ActionLink>}</footer></div>;
}
const router = createBrowserRouter([{ element: <Root />, errorElement: <RouteFailure />, children: [
  { index: true, element: <Home /> }, { path: 'catalog', element: <Catalog /> }, { path: 'catalog/:id', element: <ItemDetail /> }, { path: 'pets', element: <Catalog pets /> }, { path: 'about', element: <About /> }, { path: 'cart', element: <CartPage /> },
  ...['login', 'forgot-password'].map((path) => ({ path, element: <AuthPage /> })),
  { path: 'register', element: <RegistrationPage /> }, { path: 'register/verify', element: <RegistrationVerification /> }, { path: 'register/complete', element: <RegistrationComplete /> },
  { path: 'resend-confirmation', element: <Navigate to="/register/verify" replace /> },
  { path: 'confirm', element: <RegistrationConfirmation /> }, { path: 'confirm/:userId', element: <RegistrationConfirmation /> }, { path: 'reset-password', element: <PasswordReset /> }, { path: 'demo', element: isLive ? <FeaturePending title="Демоверсия доступна отдельно" /> : <DemoPage /> },
  { path: 'checkout', element: <RequireUser><Checkout /></RequireUser> },
  { path: 'account', element: <RequireUser><Account /></RequireUser> }, { path: 'account/orders', element: <RequireUser><Orders /></RequireUser> }, { path: 'account/orders/:id', element: <RequireUser><OrderDetail /></RequireUser> },
  { path: 'admin', element: <RequireUser admin><AdminLayout /></RequireUser>, children: [
    { index: true, element: <AdminOverview /> }, { path: 'products', element: <AdminItems /> }, { path: 'products/:id', element: <ItemEditor /> }, { path: 'pets', element: <AdminItems pets /> }, { path: 'pets/:id', element: <ItemEditor pets /> },
    { path: 'categories', element: <AdminCategories /> }, { path: 'orders', element: <AdminOrders /> }, { path: 'orders/:id', element: <OrderDetail admin /> }, { path: 'users', element: <AdminUsers /> }, { path: 'demo', element: isLive ? <LiveLogs /> : <DemoPage controls /> }, { path: 'logs', element: <LiveLogs /> },
  ] },
  { path: '*', element: <Empty title="Страница не найдена" text="Вернитесь в магазин."><ActionLink testId="not-found-home" className="primary-button" to="/">На главную</ActionLink></Empty> },
] }]);
class AppBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { log('client_error', { code: 'UNEXPECTED' }); }
  render() { return this.state.failed ? <div className="startup-error"><h1>Не удалось открыть страницу</h1><p>Обновите приложение. Сохранённые данные останутся в браузере.</p><Button testId="app-retry" className="primary-button" onClick={() => location.reload()}>Обновить</Button></div> : this.props.children; }
}
export function App() { return <AppBoundary><RouterProvider router={router} /></AppBoundary>; }
