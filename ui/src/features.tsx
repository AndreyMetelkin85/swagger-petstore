import { mailViewerUrl } from './api';
import { ActionLink } from './ui';
export function FeaturePending({ title = 'Раздел готовится' }: { title?: string }) {
  return <section className="page-section" data-testid="feature-pending"><h1>{title}</h1><p className="page-intro">Скоро здесь появятся товары, фотографии и новые возможности магазина. Уже сейчас можно выбрать питомца и оформить заказ.</p><ActionLink testId="feature-pets" className="primary-button" to="/pets">Посмотреть питомцев</ActionLink></section>;
}
export function MailInboxLink() {
  if (!mailViewerUrl || !/^https?:\/\//i.test(mailViewerUrl)) return null;
  return <a data-testid="mail-inbox" className="text-link" href={mailViewerUrl} target="_blank" rel="noopener noreferrer">Открыть тестовую почту</a>;
}
