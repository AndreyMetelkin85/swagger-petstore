"""Тестовые письма: шаблоны и безопасная SMTP-отправка."""

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape


@dataclass(frozen=True)
class EmailContent:
    """Русская тема, HTML и текст одного уведомления."""

    subject: str
    text: str
    html: str


def render_email(username: str, action_url: str, expires_at: datetime, reset: bool = False) -> EmailContent:
    """Формирует письмо подтверждения или восстановления без паролей и встроенных скриптов.

    :param username: Имя пользователя.
    :param action_url: Ссылка подтверждения или восстановления для письма.
    :param expires_at: Время окончания действия ссылки с часовым поясом.
    :param reset: Формировать письмо восстановления вместо подтверждения регистрации.
    :return: Результат операции типа EmailContent.
    """
    title = "Сброс пароля" if reset else "Подтвердите регистрацию"
    button = "Установить новый пароль" if reset else "Подтвердить регистрацию"
    description = (
        "Мы получили запрос на восстановление доступа к вашему аккаунту."
        if reset
        else "Спасибо за регистрацию в Petstore. Осталось подтвердить электронную почту."
    )
    duration = "30 минут" if reset else "24 часа"
    deadline = expires_at.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")
    text = f"Здравствуйте, {username}!\n\n{description}\n\n{button}:\n{action_url}\n\nСсылка действует {duration}, до {deadline}.\nЕсли вы не отправляли запрос, проигнорируйте это письмо.\nПароль никому сообщать не нужно."
    html = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;background:#f3f7f6;font-family:Arial,sans-serif;color:#223734">
<table role="presentation" style="width:100%;padding:32px 16px"><tr><td align="center">
<table role="presentation" style="width:100%;max-width:560px;background:#ffffff;border-radius:16px;padding:32px">
<tr><td style="color:#087f7b;font-size:22px;font-weight:bold;padding-bottom:28px">Petstore · Почта</td></tr>
<tr><td><h1 style="font-size:24px;margin:0 0 20px">{title}</h1>
<p style="line-height:1.6">Здравствуйте, {escape(username)}!</p><p style="line-height:1.6">{description}</p>
<p style="padding:16px 0"><a href="{escape(action_url, quote=True)}" style="display:inline-block;background:#087f7b;color:#fff;text-decoration:none;padding:14px 22px;border-radius:8px;font-weight:bold">{button}</a></p>
<p style="font-size:14px;line-height:1.6;color:#647771">Ссылка действует {duration}, до {deadline}.</p>
<p style="font-size:13px;line-height:1.6;color:#647771">Если кнопка не открывается, скопируйте адрес:<br><a href="{escape(action_url, quote=True)}" style="color:#087f7b;word-break:break-all">{escape(action_url)}</a></p>
<hr style="border:0;border-top:1px solid #e5ecea;margin:24px 0"><p style="font-size:13px;line-height:1.6;color:#647771">Если вы не отправляли запрос, проигнорируйте письмо. Пароль никому сообщать не нужно.</p>
</td></tr></table></td></tr></table></body></html>"""
    return EmailContent(title, text, html)
