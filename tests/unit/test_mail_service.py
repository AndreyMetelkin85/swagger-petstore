import smtplib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from petstore.config import Settings
from petstore.notification.mail_service import MailService
from petstore.notification.templates import render_email


@pytest.mark.parametrize(
    "reset,subject,duration",
    [(False, "Подтвердите регистрацию", "24 часа"), (True, "Сброс пароля", "30 минут")],
)
def test_mail_templates_have_matching_html_text_and_expiry(reset, subject, duration):
    result = render_email(
        '<img src=x onerror="alert(1)">',
        "http://localhost:8081/action?code=secret-test&x=1",
        datetime.now(UTC),
        reset,
    )
    assert result.subject == subject
    assert duration in result.text and duration in result.html
    assert "UTC" in result.text
    assert "<img src=x" not in result.html
    assert "&lt;img" in result.html
    assert "&amp;x=1" in result.html


def test_mail_disabled_without_smtp_host(monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr("petstore.notification.mail_service.smtplib.SMTP", smtp)
    assert not MailService(Settings()).send_link(
        uuid4(), "user@petstore.test", "user", "code", datetime.now(UTC)
    )
    smtp.assert_not_called()


@pytest.mark.parametrize("reset", [False, True])
def test_multipart_smtp_message_and_no_sensitive_logs(monkeypatch, caplog, reset):
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value.send_message.return_value = {}
    monkeypatch.setattr("petstore.notification.mail_service.smtplib.SMTP", smtp)
    service = MailService(
        replace(Settings(), smtp_host="mail", public_base_url="http://localhost:8081/api/v3")
    )
    caplog.set_level("INFO", logger="petstore.mail")
    assert service.send_link(
        uuid4(),
        "private-recipient@example.com",
        "username",
        "secret-one-time-code",
        datetime.now(UTC) + timedelta(minutes=30),
        reset,
    )
    message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
    assert message.is_multipart()
    assert message.get_body(preferencelist=("plain",)).get_content_type() == "text/plain"
    assert message.get_body(preferencelist=("html",)).get_content_type() == "text/html"
    assert message["X-Petstore-Event"] == ("password_reset" if reset else "registration_confirmation")
    assert "secret-one-time-code" not in caplog.text
    assert "private-recipient@example.com" not in caplog.text


@pytest.mark.parametrize(
    "failure", [OSError("private-server-name"), smtplib.SMTPException("secret-one-time-code")]
)
def test_smtp_failure_is_bounded_and_does_not_expose_exception_values(monkeypatch, caplog, failure):
    smtp = MagicMock(side_effect=failure)
    monkeypatch.setattr("petstore.notification.mail_service.smtplib.SMTP", smtp)
    service = MailService(replace(Settings(), smtp_host="mail"))
    assert not service.send_link(uuid4(), "user@petstore.test", "user", "code", datetime.now(UTC))
    assert "mail_delivery_failed" in caplog.text
    assert "private-server-name" not in caplog.text
    assert "secret-one-time-code" not in caplog.text


def test_refused_recipient_returns_delivery_failure(monkeypatch):
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value.send_message.return_value = {
        "user@petstore.test": (550, b"rejected")
    }
    monkeypatch.setattr("petstore.notification.mail_service.smtplib.SMTP", smtp)
    assert not MailService(replace(Settings(), smtp_host="mail")).send_link(
        uuid4(), "user@petstore.test", "user", "code", datetime.now(UTC)
    )


@pytest.mark.parametrize("reset", [False, True])
def test_optional_frontend_links_and_working_backend_reset_fallback(reset):
    user_id = uuid4()
    service = MailService(replace(Settings(), mail_frontend_url="http://localhost:8088"))
    url = service.action_url(user_id, "safe_code", reset)
    assert url == (
        "http://localhost:8088/reset-password?code=safe_code"
        if reset
        else f"http://localhost:8088/confirm/{user_id}?code=safe_code"
    )
    fallback = MailService(replace(Settings(), public_base_url="http://localhost:8081/api/v3"))
    assert (
        fallback.action_url(user_id, "safe_code", True)
        == "http://localhost:8081/reset-password.html?code=safe_code"
    )
