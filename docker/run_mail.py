"""Тестовая почта с совместимыми правами тома и безопасными логами."""

import os
import signal
import subprocess
from pathlib import Path

APPLICATION_UID = 998
APPLICATION_GID = 998
STORAGE_ROOT = Path("/smtp4dev")


def prepare_storage() -> None:
    """Восстанавливает владельца почтового тома и отзывает права root.

    Обрабатывается только /smtp4dev без перехода по символическим ссылкам.
    Старый UID 998 и промежуточный UID 999 приводятся к постоянному UID 998.
    Письма и SQLite не изменяются; smtp4dev запускается непривилегированно.

    :return: Ничего не возвращает.
    :raises subprocess.CalledProcessError: Не удалось восстановить права тома.
    """
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        subprocess.run(
            [
                "chown",
                "--no-dereference",
                "-R",
                f"{APPLICATION_UID}:{APPLICATION_GID}",
                STORAGE_ROOT.as_posix(),
            ],
            check=True,
        )
        os.setgroups([])
        os.setgid(APPLICATION_GID)
        os.setuid(APPLICATION_UID)


def main() -> None:
    """Запускает smtp4dev после восстановления доступа к сохранённым письмам.

    Логи не содержат получателей, темы и содержимого письма. Сигнал остановки
    передаётся только дочернему процессу этого сервиса.

    :return: Ничего не возвращает.
    :raises SystemExit: Завершение с кодом дочернего процесса.
    """
    prepare_storage()
    process = subprocess.Popen(
        ["/opt/dotnet/dotnet", "/opt/smtp4dev/Rnwood.Smtp4dev.dll", "--baseappdatapath=/smtp4dev"],
        cwd="/opt/smtp4dev",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def stop(_signal: int, _frame: object) -> None:
        """Передаёт остановку только собственному процессу smtp4dev.

        :param _signal: Номер сигнала ОС.
        :param _frame: Кадр исполнения обработчика сигнала.
        :return: Ничего не возвращает.
        """
        if process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    assert process.stdout is not None
    for line in process.stdout:
        if line.startswith(("[ERR]", "[FTL]", "fail:", "crit:")):
            print("mail_error", flush=True)
        elif "SMTP Server is listening" in line:
            print("mail_ready", flush=True)
    status = process.wait()
    print(f"mail_stopped status={status}", flush=True)
    raise SystemExit(status if status >= 0 else 128 - status)


if __name__ == "__main__":
    main()
