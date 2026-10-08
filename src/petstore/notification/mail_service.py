"""Тестовые письма: шаблоны и безопасная SMTP-отправка."""

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from urllib.parse import quote, urlsplit
from uuid import UUID

from petstore.config import Settings
from petstore.notification.templates import render_email

logger = logging.getLogger("petstore.mail")


class MailService:
    """Необязательная SMTP-отправка без паролей приложения и ссылок в логах."""

    def __init__(self, settings: Settings) -> None:
        """Настраивает локальный SMTP; без адреса сервера отправка отключена.

        :param settings: Настройки приложения и его инфраструктурных подключений.
        :return: Ничего не возвращает.
        """
        self.settings = settings

    def action_url(self, user_id: UUID, code: str, reset: bool) -> str:
        """Строит ссылку на настроенный фронтенд либо рабочую страницу восстановления бэкенда.

        :param user_id: UUID целевого пользователя.
        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :param reset: Формировать письмо восстановления вместо подтверждения регистрации.
        :return: Строковый результат описанной операции.
        """
        token = quote(code, safe="")
        if self.settings.mail_frontend_url:
            path = f"/reset-password?code={token}" if reset else f"/confirm/{user_id}?code={token}"
            return self.settings.mail_frontend_url + path
        if reset:
            base = urlsplit(self.settings.public_base_url)
            return f"{base.scheme}://{base.netloc}/reset-password.html?code={token}"
        return f"{self.settings.public_base_url}/auth/confirm/{user_id}?code={token}"

    def send_link(
        self,
        user_id: UUID,
        recipient: str,
        username: str,
        code: str,
        expires_at: datetime,
        reset: bool = False,
    ) -> bool:
        """Отправляет HTML и текст; сбой SMTP не отменяет уже зафиксированное изменение аккаунта.

        :param user_id: UUID целевого пользователя.
        :param recipient: Получатель тестового письма.
        :param username: Имя пользователя.
        :param code: Одноразовый код ссылки либо машинный код ошибки согласно операции.
        :param expires_at: Время окончания действия ссылки с часовым поясом.
        :param reset: Формировать письмо восстановления вместо подтверждения регистрации.
        :return: True при выполнении проверяемого условия, иначе False.
        """
        host = self.settings.smtp_host
        if not host:
            return False
        content = render_email(username, self.action_url(user_id, code, reset), expires_at, reset)
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = recipient
        message["Subject"] = content.subject
        message["Message-ID"] = make_msgid(domain="petstore.test")
        message["Date"] = format_datetime(datetime.now().astimezone())
        message["X-Petstore-Event"] = "password_reset" if reset else "registration_confirmation"
        message.set_content(content.text)
        message.add_alternative(content.html, subtype="html")
        try:
            with smtplib.SMTP(host, self.settings.smtp_port, timeout=self.settings.smtp_timeout) as smtp:
                refused = smtp.send_message(message)
                if refused:
                    logger.warning(
                        "mail_delivery_failed kind=%s reason=recipient_refused", message["X-Petstore-Event"]
                    )
                    return False
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning(
                "mail_delivery_failed kind=%s error=%s", message["X-Petstore-Event"], type(exc).__name__
            )
            return False
        logger.info("mail_delivered kind=%s", message["X-Petstore-Event"])
        return True
