import { useState } from 'react';
import { Button } from './ui';
import { readLogs } from './logger';
export function LiveLogs() {
  const [records, setRecords] = useState(readLogs);
  return <section className="page-section"><h1>Журнал событий</h1><p className="page-intro">Действия, коды ошибок и номера обращений. Пароли, карточные реквизиты и личные данные исключены.</p><Button testId="logs-refresh" className="outline-button" onClick={() => setRecords(readLogs())}>Обновить журнал</Button><pre className="safe-logs" data-testid="client-logs">{JSON.stringify(records.slice(-30), null, 2)}</pre></section>;
}
