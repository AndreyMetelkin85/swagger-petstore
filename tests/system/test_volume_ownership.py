import json
import os
import smtplib
import subprocess
import time
from email.message import EmailMessage
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.system


def docker(*args: str) -> str:
    """Выполняет команду Docker только с явно выбранными тестовыми ресурсами.

    :param args: Аргументы операции без секретов и пользовательских данных.
    :return: Вывод успешно выполненной команды.
    """
    return subprocess.run(
        ["docker", *args], check=True, capture_output=True, text=True, timeout=90
    ).stdout.strip()


def wait_ready(url: str) -> None:
    """Ожидает восстановления изолированного сервиса после перезапуска.

    :param url: URL проверки API либо почты текущего теста.
    :return: Ничего не возвращает при готовности сервиса.
    """
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    pytest.fail("Тестовый сервис не восстановил доступ к прежнему тому")


@pytest.mark.parametrize("previous_uid", [998, 999])
def test_private_media_and_existing_mail_survive_ownership_migration(previous_uid):
    api_container = os.getenv("PETSTORE_RESTART_CONTAINER")
    mail_container = os.getenv("PETSTORE_MAIL_RESTART_CONTAINER")
    if not api_container or not mail_container:
        pytest.skip("Укажите изолированные API и почту")
    assert (api_container, mail_container) == ("petstore-python-preview", "petstore-mail")
    for container in (api_container, mail_container):
        mounts = json.loads(docker("inspect", "--format", "{{json .Mounts}}", container))
        assert mounts and all(mount["Type"] == "volume" for mount in mounts)
        assert "swagger-petstore-data" not in {mount["Name"] for mount in mounts}
    api_url = os.environ["BASE_URL"].rstrip("/")
    mail_url = os.environ["PETSTORE_MAIL_UI_URL"].rstrip("/")
    marker = "ownership-" + uuid4().hex
    message = EmailMessage()
    message["From"] = "noreply@petstore.test"
    message["To"] = marker + "@petstore.test"
    message["Subject"] = marker
    message.set_content("Сохранённое письмо до смены владельца тома")
    message_id = None
    filename = "." + marker
    try:
        with smtplib.SMTP("127.0.0.1", int(os.getenv("PETSTORE_MAIL_SMTP_PORT", "2525")), timeout=5) as smtp:
            smtp.send_message(message)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            rows = httpx.get(
                mail_url + "/api/Messages", params={"mailboxName": "Tests", "searchTerms": marker}
            ).json()["results"]
            if rows:
                message_id = rows[0]["id"]
                break
            time.sleep(0.2)
        assert message_id is not None
        before = httpx.get(mail_url + f"/api/Messages/{message_id}/plaintext").text
        docker("stop", "--timeout", "30", api_container, mail_container)
        image = docker("inspect", "--format", "{{.Config.Image}}", api_container)
        script = (
            "import os,subprocess; from pathlib import Path; "
            f"uid={previous_uid}; "
            "subprocess.run(['chown','--no-dereference','-R',f'{uid}:{uid}','/smtp4dev'],check=True); "
            f"roots=['/smtp4dev','/var/lib/petstore/media']; name='{filename}'; "
            "[(p.write_text('retained'),p.chmod(0o600),os.chown(p,uid,uid)) for p in [Path(root)/name for root in roots]]"
        )
        docker(
            "run",
            "--rm",
            "--user",
            "0",
            "--volumes-from",
            api_container,
            "--volumes-from",
            mail_container,
            "--entrypoint",
            "python",
            image,
            "-c",
            script,
        )
        docker("start", mail_container, api_container)
        wait_ready(api_url + "/health")
        wait_ready(mail_url + "/api/Mailboxes")
        for container, root in ((api_container, "/var/lib/petstore/media"), (mail_container, "/smtp4dev")):
            code = f"from pathlib import Path; p=Path('{root}/{filename}'); assert p.read_text()=='retained'; assert p.stat().st_uid==998; assert p.stat().st_mode & 0o777==0o600"
            docker("exec", "--user", "998:998", container, "python", "-c", code)
        assert httpx.get(mail_url + f"/api/Messages/{message_id}/plaintext").text == before
        processes = docker("top", mail_container, "-eo", "pid,user,args")
        assert "Rnwood.Smtp4dev" in processes
    finally:
        # Восстанавливаем оба собственных сервиса даже после неуспешной проверки.
        docker("start", mail_container, api_container)
        wait_ready(api_url + "/health")
        wait_ready(mail_url + "/api/Mailboxes")
        for container, root in ((api_container, "/var/lib/petstore/media"), (mail_container, "/smtp4dev")):
            docker(
                "exec",
                "--user",
                "0",
                container,
                "python",
                "-c",
                f"from pathlib import Path; Path('{root}/{filename}').unlink(missing_ok=True)",
            )
        if message_id:
            assert httpx.delete(mail_url + f"/api/Messages/{message_id}").status_code in {200, 204}
