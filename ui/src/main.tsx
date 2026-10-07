import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { dataMode } from './api';
import { log } from './logger';
import { configureTelemetry } from './telemetry';
import './styles.css';

async function start() {
  if (dataMode === 'mock') {
    const [{ worker }, { initialize }] = await Promise.all([import('./mocks/browser'), import('./mocks/storage')]);
    await initialize(); await worker.start({ quiet: true, onUnhandledRequest: 'bypass' });
  } else if (dataMode === 'api') {
    if ('serviceWorker' in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      for (const registration of registrations) {
        const worker = registration.active ?? registration.waiting ?? registration.installing;
        if (worker?.scriptURL === new URL('/mockServiceWorker.js', location.origin).href) await registration.unregister();
      }
    }
  } else throw new Error('Invalid data mode');
  configureTelemetry();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: true }, mutations: { retry: false } } });
  ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={client}><App /></QueryClientProvider></React.StrictMode>);
}
void start().catch(() => { log('client_error', { code: 'STARTUP_FAILED' }); ReactDOM.createRoot(document.getElementById('root')!).render(<div className="startup-error"><h1>Не удалось запустить магазин</h1><p>Проверьте, разрешены ли локальное хранилище и service worker, и обновите страницу.</p><button data-testid="startup-retry" onClick={() => location.reload()}>Обновить</button></div>); });
