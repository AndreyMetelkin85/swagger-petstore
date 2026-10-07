import imaplib
import os
import smtplib
import subprocess
import time
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from playwright.sync_api import sync_playwright

from petstore.notification.templates import render_email

pytestmark = pytest.mark.system


def test_mail_storage_survives_its_own_container_restart():
    url = os.getenv("PETSTORE_MAIL_UI_URL")
    container = os.getenv("PETSTORE_MAIL_RESTART_CONTAINER")
    if not url or not container:
        pytest.skip("Set local mail URL and owned mail container for restart verification")
    assert container in {"petstore-mail", "petstore-python-preview"}, (
        "Only isolated CI mail/store containers may restart"
    )
    marker = "mail-persistence-" + uuid4().hex
    message = EmailMessage()
    message["From"] = "noreply@petstore.test"
    message["To"] = marker + "@petstore.test"
    message["Subject"] = marker
    message.set_content("Persistent local mail test")
    received = None
    try:
        with smtplib.SMTP("127.0.0.1", int(os.getenv("PETSTORE_MAIL_SMTP_PORT", "2525")), timeout=5) as smtp:
            smtp.send_message(message)
        received = find_message("Tests", marker)
        subprocess.run(["docker", "restart", container], check=True, capture_output=True, timeout=60)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(url.rstrip("/") + "/api/Mailboxes", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            pytest.fail("Local mail server did not recover after restart")
        assert find_message("Tests", marker)["id"] == received["id"]
        assert str(read_by_imap("tests", marker)["To"]) == marker + "@petstore.test"
    finally:
        if received:
            assert httpx.delete(url.rstrip("/") + f"/api/Messages/{received['id']}").status_code in {200, 204}


@pytest.mark.parametrize("username,mailbox_name", [("user1", "User1"), ("user2", "User2")])
def test_smtp_routes_each_recipient_to_its_own_imap_mailbox(username, mailbox_name):
    url = os.getenv("PETSTORE_MAIL_UI_URL")
    if not url:
        pytest.skip("Set PETSTORE_MAIL_UI_URL for the local mail lab")
    marker = "mail-routing-" + uuid4().hex
    message = EmailMessage()
    message["From"] = "noreply@petstore.test"
    message["To"] = username + "@petstore.test"
    message["Subject"] = marker
    message.set_content("Проверка доставки конкретному получателю.")
    content = render_email(username, "http://localhost:8081/", datetime.now(UTC) + timedelta(hours=24))
    message.add_alternative(content.html, subtype="html")
    received = None
    try:
        with smtplib.SMTP("127.0.0.1", int(os.getenv("PETSTORE_MAIL_SMTP_PORT", "2525")), timeout=5) as smtp:
            assert smtp.send_message(message) == {}
        received = find_message(mailbox_name, marker)
        assert str(read_by_imap(username, marker)["To"]) == username + "@petstore.test"
        other = "User2" if mailbox_name == "User1" else "User1"
        unrelated = httpx.get(
            url.rstrip("/") + "/api/Messages", params={"mailboxName": other, "searchTerms": marker}
        ).json()
        assert unrelated["rowCount"] == 0
    finally:
        if received:
            assert httpx.delete(url.rstrip("/") + f"/api/Messages/{received['id']}").status_code in {200, 204}


def find_message(mailbox_name: str, subject: str) -> dict:
    """Find one uniquely marked message without consuming another test's mail.

    :param mailbox_name: Configured local mailbox.
    :param subject: Unique subject or recipient marker.
    """
    url = os.environ["PETSTORE_MAIL_UI_URL"].rstrip("/")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = httpx.get(
            url + "/api/Messages",
            params={"mailboxName": mailbox_name, "searchTerms": subject, "pageSize": 100},
            timeout=5,
        )
        response.raise_for_status()
        results = response.json()["results"]
        if results:
            assert len(results) == 1
            return results[0]
        time.sleep(0.1)
    pytest.fail("The expected local email did not arrive")


def read_by_imap(username: str, subject: str) -> EmailMessage:
    """Retrieve the exact received message via IMAP without marking all mail as read.

    :param username: Local IMAP test account.
    :param subject: Subject searched in this mailbox.
    """
    port = int(os.getenv("PETSTORE_MAIL_IMAP_PORT", "1143"))
    with imaplib.IMAP4("127.0.0.1", port, timeout=5) as mailbox:
        assert mailbox.login(username, "mail-test-only")[0] == "OK"
        assert mailbox.select("INBOX", readonly=True)[0] == "OK"
        status, data = mailbox.uid("search", None, "SUBJECT", '"' + subject + '"')
        assert status == "OK" and data[0]
        uids = data[0].split()
        assert len(uids) == 1
        status, parts = mailbox.uid("fetch", uids[0], "(BODY.PEEK[])")
        assert status == "OK"
        raw = next(part[1] for part in parts if isinstance(part, tuple))
        return BytesParser(policy=policy.default).parsebytes(raw)


@pytest.fixture
def mail_lab():
    url = os.getenv("PETSTORE_MAIL_UI_URL")
    api_url = os.getenv("BASE_URL")
    if not url or not api_url:
        pytest.skip("Set local mail UI and isolated API URLs for email system tests")
    with httpx.Client(base_url=api_url, timeout=10) as client:
        login = client.post("/auth/login", json={"email": "admin@example.com", "password": "admin123"})
        assert login.status_code == 200
        users = []
        messages = []
        try:
            yield client, {"Authorization": "Bearer " + login.json()["access_token"]}, users, messages
        finally:
            for message_id in messages:
                response = httpx.delete(url.rstrip("/") + f"/api/Messages/{message_id}", timeout=5)
                assert response.status_code in {200, 204, 404}
            for user_id in users:
                assert (
                    client.delete(
                        f"/users/{user_id}",
                        headers={"Authorization": "Bearer " + login.json()["access_token"]},
                    ).status_code
                    == 204
                )


def test_registration_resend_and_hidden_reset_link_arrive_in_local_mail(mail_lab):
    client, admin, users, messages = mail_lab
    marker = uuid4().hex
    email = marker + "@petstore.test"
    request = {"username": "mail-" + marker[:20], "email": email, "password": "MailValidPass123"}
    response = client.post("/auth/register", json=request)
    assert response.status_code == 201
    user_id = response.json()["user"]["id"]
    users.append(user_id)
    ui = os.environ["PETSTORE_MAIL_UI_URL"].rstrip("/")
    first = find_message("Tests", email)
    messages.append(first["id"])
    body = httpx.get(ui + f"/api/Messages/{first['id']}/plaintext", timeout=5).text
    assert "24 часа" in body
    assert request["password"] not in body
    # Read the same MIME message through IMAP using its unique recipient marker.
    with imaplib.IMAP4("127.0.0.1", int(os.getenv("PETSTORE_MAIL_IMAP_PORT", "1143")), timeout=5) as mailbox:
        assert mailbox.login("tests", "mail-test-only")[0] == "OK"
        assert mailbox.select("INBOX", readonly=True)[0] == "OK"
        status, data = mailbox.uid("search", None, "TO", '"' + email + '"')
        assert status == "OK" and data[0]
        status, parts = mailbox.uid("fetch", data[0].split()[0], "(BODY.PEEK[])")
        mime = BytesParser(policy=policy.default).parsebytes(
            next(part[1] for part in parts if isinstance(part, tuple))
        )
        assert mime.get_body(preferencelist=("html",)) is not None
    old_code = parse_qs(urlsplit(response.json()["confirmationUrl"]).query)["code"][0]
    assert httpx.delete(ui + f"/api/Messages/{first['id']}").status_code in {200, 204}
    resend = client.post("/auth/confirmation/resend", json={"email": email, "password": request["password"]})
    assert resend.status_code == 200
    second = find_message("Tests", email)
    messages.append(second["id"])
    assert client.get(f"/auth/confirm/{user_id}", params={"code": old_code}).status_code == 400
    new_code = parse_qs(urlsplit(resend.json()["confirmationUrl"]).query)["code"][0]
    assert client.get(f"/auth/confirm/{user_id}", params={"code": new_code}).status_code == 200
    assert httpx.delete(ui + f"/api/Messages/{second['id']}").status_code in {200, 204}
    recovery = client.post("/auth/password/forgot", json={"email": email})
    assert recovery.status_code == 200
    recovery_mail = find_message("Tests", email)
    messages.append(recovery_mail["id"])
    plain = httpx.get(ui + f"/api/Messages/{recovery_mail['id']}/plaintext").text
    assert "30 минут" in plain
    assert request["password"] not in plain
    link = next(line for line in plain.splitlines() if "reset-password.html?code=" in line).strip()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE"))
        page = browser.new_page()
        page.goto(link)
        assert "code=" not in page.url
        page.locator("#password").fill("NewMailValidPass123")
        page.locator("#repeat").fill("NewMailValidPass123")
        page.locator("#submit").click()
        page.get_by_text(
            "Пароль обновлён. Теперь можно войти в магазин с новым паролем.", exact=True
        ).wait_for()
        browser.close()
    assert (
        client.post("/auth/login", json={"email": email, "password": "NewMailValidPass123"}).status_code
        == 200
    )
