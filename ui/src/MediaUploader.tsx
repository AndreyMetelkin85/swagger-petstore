import { useEffect, useId, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Upload, X } from 'lucide-react';
import { api, isLive, request } from './api';
import { ServiceError } from './errors';
import { useStore } from './store';
import { MediaImage } from './MediaImage';
import { Button, Field } from './ui';
import type { ImageRef, Media } from './models';
import { log } from './logger';
type Job = { id: string; file: File; url: string; sourceType: string; sourceNote: string; status: 'ready' | 'uploading' | 'error'; progress: number; controller?: AbortController };
function MediaSource({ id }: { id?: string }) {
  const { user } = useStore();
  const query = useQuery({ queryKey: ['media-source', user?.id, id], enabled: !!id, queryFn: () => request<Media>(`/media/${id}`), retry: false, staleTime: Infinity });
  if (!id) return null;
  if (query.isPending) return <p className="form-hint" data-testid="media-source-loading">Загружаем источник фотографии…</p>;
  if (query.error) return <div><p className="form-hint" data-testid="media-source-error">Не удалось загрузить сведения об источнике.</p><Button testId="media-source-retry" className="text-link" onClick={() => { void query.refetch(); }}>Повторить</Button></div>;
  return <div className="form-hint"><span data-testid="media-asset-source">Источник: {({ OWN: 'Наши фотографии', SUPPLIER: 'От поставщика', DEMO: 'Демонстрационные' })[query.data.sourceType]}</span>{query.data.sourceNote && <p data-testid="media-asset-source-note">{query.data.sourceNote}</p>}</div>;
}
export function MediaUploader({ images, change, busy }: { images: ImageRef[]; change: (update: ImageRef[] | ((current: ImageRef[]) => ImageRef[])) => void; busy: (value: boolean) => void }) {
  const uploadHintId = useId(), galleryHintId = useId();
  const { report } = useStore(), [jobs, setJobs] = useState<Job[]>([]), [source, setSource] = useState('OWN'), [note, setNote] = useState('');
  const jobRef = useRef(jobs); jobRef.current = jobs;
  const uploadQueue = useRef(Promise.resolve()), alive = useRef(true);
  useEffect(() => { busy(jobs.length > 0); }, [jobs.length, busy]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; jobRef.current.forEach((job) => { job.controller?.abort(); URL.revokeObjectURL(job.url); }); jobRef.current = []; }; }, []);
  function patch(id: string, update: Partial<Job>) { setJobs((current) => current.map((job) => job.id === id ? { ...job, ...update } : job)); }
  function removeJob(id: string) { const job = jobRef.current.find((entry) => entry.id === id); job?.controller?.abort(); if (job) URL.revokeObjectURL(job.url); jobRef.current = jobRef.current.filter((entry) => entry.id !== id); setJobs(jobRef.current); }
  async function upload(job: Job) {
    const controller = new AbortController(); patch(job.id, { status: 'uploading', progress: 10, controller });
    const timer = setInterval(() => setJobs((current) => current.map((entry) => entry.id === job.id ? { ...entry, progress: Math.min(90, entry.progress + 15) } : entry)), 120);
    try {
      const media = await api.upload(job.file, job.sourceType, job.sourceNote, controller.signal);
      if (controller.signal.aborted) return;
      change((current) => [...current, { mediaId: media.id, alt: '' }]); log('media_uploaded', { resourceId: media.id, result: 'success' }); removeJob(job.id);
    } catch (failure) { if (!controller.signal.aborted) { patch(job.id, { status: 'error', progress: 0 }); report(failure); } } finally { clearInterval(timer); }
  }
  function enqueue(job: Job) { uploadQueue.current = uploadQueue.current.then(async () => { if (alive.current && jobRef.current.some((entry) => entry.id === job.id)) await upload(job); }); }
  function choose(files: FileList | File[]) {
    if (images.length + jobRef.current.length + files.length > 20) { report(new ServiceError('MEDIA_LIMIT_EXCEEDED', 422)); return; }
    const next: Job[] = [];
    for (const file of Array.from(files)) {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { report(new ServiceError('MEDIA_UNSUPPORTED_TYPE', 415)); continue; }
      if (file.size > 10 * 1024 * 1024) { report(new ServiceError('MEDIA_FILE_TOO_LARGE', 413)); continue; }
      next.push({ id: crypto.randomUUID(), file, url: URL.createObjectURL(file), sourceType: source, sourceNote: note, status: 'ready', progress: 0 });
    }
    jobRef.current = [...jobRef.current, ...next]; setJobs(jobRef.current); next.forEach(enqueue);
  }
  function move(index: number, offset: number) { change((current) => { const result = [...current]; [result[index], result[index + offset]] = [result[index + offset], result[index]]; return result; }); }
  return <section className="media-uploader" data-testid="media-gallery"><div className="form-row"><Field label="Источник фотографий" testId="media-source"><select data-testid="media-source" value={source} onChange={(event) => setSource(event.target.value)}><option value="OWN">Наши фотографии</option><option value="SUPPLIER">От поставщика</option><option value="DEMO">Демонстрационные</option></select></Field><Field label="Примечание к источнику (необязательно)" testId="media-note" hint="Например, откуда получены фотографии. До 500 символов."><input data-testid="media-note" value={note} maxLength={500} onChange={(event) => setNote(event.target.value)} placeholder="Например, каталог поставщика" /></Field></div><label className="upload-zone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files); }}><Upload size={25} /><strong>Выберите или перетащите фотографии</strong><span id={uploadHintId} data-testid="media-upload-hint">JPEG, PNG, статичный WebP · до 10 МБ · до 20 фото</span><input data-testid="media-upload-input" aria-describedby={uploadHintId} type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={(event) => { if (event.target.files) choose(event.target.files); event.target.value = ''; }} /></label><p id={galleryHintId} className="form-hint" data-testid="media-gallery-hint">Описание фото — до 200 символов, например «Упаковка спереди». Пустое описание заполнится названием карточки при сохранении.</p>{isLive && images.some((image) => !image.mediaId) && <p className="form-hint" data-testid="media-linked-photos-hint">Фотографии по ссылкам доступны для просмотра. Загрузите файлы, чтобы создать новую галерею.</p>}<div className="media-list" data-testid="media-assets">{images.map((image, index) => <div className="media-row" key={image.mediaId ?? image.url ?? index} data-testid="media-asset" data-media-id={image.mediaId}><div className="media-thumbnail" data-testid="media-asset-preview"><MediaImage id={image.mediaId} url={image.url} alt={image.alt || 'Фотография карточки'} thumb /></div><div className="media-row-fields"><span className="media-state" data-testid="media-asset-status">{index === 0 ? 'Обложка · загружено' : 'Загружено'}</span><input data-testid="media-asset-alt" aria-label="Описание фотографии" placeholder="Например, упаковка спереди" aria-describedby={galleryHintId} value={image.alt} readOnly={isLive && !image.mediaId} maxLength={200} onChange={(event) => change((current) => current.map((entry, entryIndex) => entryIndex === index ? { ...entry, alt: event.target.value } : entry))} /><MediaSource id={image.mediaId} /><div className="media-actions"><Button testId="media-asset-make-cover" disabled={index === 0 || isLive && !image.mediaId} onClick={() => change((current) => [current[index], ...current.filter((_, i) => i !== index)])}>Обложка</Button><Button testId="media-asset-move-earlier" aria-label="Переместить раньше" disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={15} /></Button><Button testId="media-asset-move-later" aria-label="Переместить позже" disabled={index === images.length - 1 || isLive && !image.mediaId} onClick={() => move(index, 1)}><ArrowDown size={15} /></Button><Button testId="media-asset-remove" disabled={isLive && !image.mediaId} aria-label="Удалить фотографию из галереи" onClick={() => change((current) => current.filter((_, entryIndex) => entryIndex !== index))}><X size={15} /></Button></div></div></div>)}{jobs.map((job) => <div className="media-row" key={job.id} data-testid="media-upload" data-upload-id={job.id}><div className="media-thumbnail" data-testid="media-upload-preview"><img src={job.url} alt="Предпросмотр выбранного файла" /></div><div className="media-row-fields"><span data-testid="media-upload-status">{job.status === 'error' ? 'Не удалось загрузить' : job.status === 'ready' ? 'Готово к загрузке' : 'Загружаем…'}</span><progress data-testid="media-upload-progress" value={job.progress} max={100} /><div className="media-actions">{job.status === 'error' && <Button testId="media-upload-retry" onClick={() => enqueue(job)}>Повторить</Button>}<Button testId="media-upload-remove" aria-label="Удалить выбранный файл" onClick={() => removeJob(job.id)}><X size={15} /></Button></div></div></div>)}</div>{jobs.length > 0 && <p className="form-hint">Завершите загрузки или удалите выбранные файлы перед сохранением.</p>}</section>;
}
