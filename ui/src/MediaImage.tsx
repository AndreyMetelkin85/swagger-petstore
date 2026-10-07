import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PawPrint } from 'lucide-react';
import { request } from './api';
import { useStore } from './store';
import type { Media } from './models';
export function MediaImage({ id, url, alt, thumb = false, className = '' }: { id?: string; url?: string; alt: string; thumb?: boolean; className?: string }) {
  const { user } = useStore(), [src, setSrc] = useState(''), [broken, setBroken] = useState(false);
  const query = useQuery({ queryKey: ['media', id, thumb, user?.id], enabled: !!id && !url, queryFn: async () => { const meta = await request<Pick<Media, 'id' | 'mime' | 'seedUrl' | 'createdAt'>>(`/media/${id}`); return meta.seedUrl ? { url: meta.seedUrl } : { blob: await request<Blob>(`/media/${id}/${thumb ? 'thumb' : 'image'}`, { blob: true }) }; }, retry: false, staleTime: Infinity });
  useEffect(() => { setBroken(false); if (!query.data) { setSrc(''); return; } const url = 'blob' in query.data ? URL.createObjectURL(query.data.blob!) : query.data.url!; setSrc(url); return () => { if ('blob' in query.data!) URL.revokeObjectURL(url); }; }, [query.data]);
  const direct = url && /^https?:\/\//i.test(url) ? url : undefined;
  useEffect(() => { setBroken(false); }, [direct]);
  if (!(direct || src) || broken || query.error) return <div className={`image-fallback ${className}`} role="img" aria-label={alt} data-testid="image-fallback"><PawPrint size={35} aria-hidden="true" /><span>{query.error || broken ? 'Фото недоступно' : 'Фото'}</span></div>;
  return <img src={direct || src} alt={alt} referrerPolicy="no-referrer" className={className || 'media-photo'} onError={() => setBroken(true)} />;
}
