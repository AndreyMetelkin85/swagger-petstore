import type { CatalogItem } from './domain';

export function Visual({ item }: { item: CatalogItem }) {
  if (item.kind === 'pet') return <img className={`pet-photo ${item.visual}`} src="/images/pets-hero.png" alt={item.name} />;
  return <svg className="product-art" viewBox="0 0 300 260" role="img" aria-label={item.name}>
    <defs>
      <linearGradient id={`shade-${item.id}`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#fff" stopOpacity=".38" /><stop offset="1" stopColor="#000" stopOpacity=".10" />
      </linearGradient>
    </defs>
    <ellipse cx="150" cy="231" rx={item.visual === 'food' ? '69' : '99'} ry="9" fill="#242722" opacity=".07" />
    {item.visual === 'food' && <>
      <path d="M100 30 L202 30 L211 218 Q153 233 89 218 Z" fill="#ded6c4" />
      <path d="M106 31 L198 31 L204 211 Q151 220 96 211 Z" fill="#ece5d6" />
      <path d="M98 85 L202 85 L207 184 L93 184 Z" fill={item.color} />
      <path d="M100 30 L202 30 L211 218 Q153 233 89 218 Z" fill={`url(#shade-${item.id})`} />
      <path d="M106 37 H197 M106 43 H197" stroke="#b3a890" strokeWidth="2" />
      <text x="151" y="116" textAnchor="middle" fontFamily="Georgia, serif" fontSize="30" fill="#fffaf0">лапки</text>
      <path d="M147 130 C132 145 140 151 150 145 C160 151 168 145 153 130 Z" fill="#f9f3e7" opacity=".85" />
      <circle cx="136" cy="129" r="4" fill="#f9f3e7" /><circle cx="146" cy="123" r="4" fill="#f9f3e7" /><circle cx="158" cy="124" r="4" fill="#f9f3e7" /><circle cx="166" cy="132" r="4" fill="#f9f3e7" />
      <text x="151" y="169" textAnchor="middle" fontFamily="Arial, sans-serif" fontSize="9" letterSpacing="2" fill="#fffaf0">{item.id === 'food-dog' ? 'ДЛЯ СОБАК' : 'ДЛЯ КОШЕК'}</text>
      <text x="151" y="203" textAnchor="middle" fontFamily="Arial, sans-serif" fontSize="11" fill="#686355">{item.id === 'food-dog' ? '2 кг' : '1,5 кг'}</text>
    </>}
    {item.visual === 'bowl' && <>
      <path d="M60 136 Q60 220 150 220 Q240 220 240 136" fill={item.color} />
      <ellipse cx="150" cy="135" rx="90" ry="32" fill="#d6c9b6" />
      <ellipse cx="150" cy="135" rx="76" ry="23" fill="#a79a86" />
      <ellipse cx="150" cy="141" rx="67" ry="17" fill="#c5b8a4" />
      <path d="M65 154 Q73 199 101 208" fill="none" stroke="#e2d8c8" strokeWidth="5" opacity=".5" />
    </>}
    {item.visual === 'bed' && <>
      <path d="M40 152 Q40 117 75 112 L218 112 Q254 117 259 156 L253 212 Q150 247 45 215 Z" fill={item.color} />
      <ellipse cx="149" cy="167" rx="96" ry="44" fill="#747d63" />
      <ellipse cx="149" cy="176" rx="73" ry="30" fill="#a7ac94" />
      <path d="M49 175 Q40 132 76 122 M223 122 Q261 130 248 177" fill="none" stroke="#b9bda7" strokeWidth="13" strokeLinecap="round" />
      <path d="M84 190 Q149 209 214 190" fill="none" stroke="#969c84" strokeWidth="2" />
    </>}
  </svg>;
}
