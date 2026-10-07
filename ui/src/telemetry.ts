import { setLogSink } from './logger';
import { capabilities, isLive, token } from './api';
import { messages } from './errors';
export function configureTelemetry() {
  if (!capabilities.telemetry) return;
  setLogSink(async (records) => {
    const current = token(), headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (current) headers.Authorization = `Bearer ${current}`;
    const allowed = new Set(['api_result', 'api_failure', 'client_error', 'cart_merge', 'checkout', 'media_upload', 'navigation']);
    const aliases: Record<string, string> = { page_opened: 'navigation', order_placed: 'checkout', media_uploaded: 'media_upload', cart_changed: 'cart_merge' };
    const events = isLive ? records.filter((record) => allowed.has(aliases[record.event] ?? record.event)).map(({ event, method, httpStatus, durationMs, requestId, code, resourceId, routeId, endpointTemplate, timestamp }) => ({ event: aliases[event] ?? event, timestamp, ...(method ? { method } : {}), ...(httpStatus ? { httpStatus } : {}), ...(durationMs !== undefined ? { durationMs } : {}), ...(requestId ? { requestId } : {}), ...(code ? { errorCode: String(code) in messages ? code : 'UNEXPECTED' } : {}), ...(resourceId ? { resourceId } : {}), ...(routeId ? { routeId } : {}), ...(endpointTemplate ? { endpointTemplate } : {}) })) : records.map(({ actorId: _actor, scope: _scope, ...event }) => event);
    if (!events.length) return;
    if (isLive) headers.Accept = 'application/json, msw/passthrough';
    await fetch('/api/v3/telemetry/client-events', { method: 'POST', headers, body: JSON.stringify({ events }), signal: AbortSignal.timeout(3000) });
  });
}
