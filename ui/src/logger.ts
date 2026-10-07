const allowed = new Set(['actorId', 'itemId', 'resourceId', 'quantity', 'design', 'code', 'count', 'method', 'endpointTemplate', 'httpStatus', 'durationMs', 'requestId', 'routeId', 'result']);
export type LogRecord = { timestamp: string; scope: string; event: string } & Record<string, string | number | boolean>;
const records: LogRecord[] = [];
export function sanitizeContext(context: Record<string, unknown>) {
  const filtered: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(context)) {
    if (!allowed.has(key) || !['string', 'number', 'boolean'].includes(typeof value)) continue;
    if (['actorId', 'itemId', 'resourceId', 'requestId'].includes(key) && !/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(String(value))) continue;
    if (key === 'code' && !/^[A-Z0-9_]{1,64}$/.test(String(value))) { filtered.code = 'UNEXPECTED'; continue; }
    if (['routeId', 'endpointTemplate'].includes(key) && (/[?@=]/.test(String(value)) || String(value).length > 160)) continue;
    filtered[key] = value as string | number | boolean;
  }
  return filtered;
}
let actorId: string | undefined;
let sink: ((records: LogRecord[]) => Promise<unknown>) | undefined;
let queued: LogRecord[] = [], timer: ReturnType<typeof setTimeout> | undefined;
export const setLogActor = (value?: string) => { actorId = value; };
export const setLogSink = (value: (records: LogRecord[]) => Promise<unknown>) => { sink = value; };
export function log(event: string, context: Record<string, unknown> = {}) {
  const safeEvent = /^[a-z_]{1,64}$/.test(event) ? event : 'client_event';
  const record = { timestamp: new Date().toISOString(), scope: 'lapki.frontend', event: safeEvent, ...sanitizeContext({ actorId, ...context }) };
  records.push(record); if (records.length > 200) records.shift(); console.info(JSON.stringify(record));
  if (sink) { queued.push(record); if (queued.length > 100) queued.shift(); if (!timer) timer = setTimeout(() => { timer = undefined; const batch = queued.splice(0, 20); queued = []; void sink!(batch).catch(() => { /* log delivery must not create recursive logging */ }); }, 1000); }
}
export const readLogs = () => [...records];
