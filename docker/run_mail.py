"""Запуск тестовой почты без получателей и содержимого писем в логах контейнера."""

import signal
import subprocess

process = subprocess.Popen(
    ["/opt/dotnet/dotnet", "/opt/smtp4dev/Rnwood.Smtp4dev.dll", "--baseappdatapath=/smtp4dev"],
    cwd="/opt/smtp4dev",
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
)


def stop(_signal: int, _frame: object) -> None:
    """Передаёт сигнал остановки только дочернему процессу smtp4dev.

    :param _signal: Номер полученного сигнала ОС.
    :param _frame: Кадр исполнения, переданный обработчику сигнала.
    :return: None после отправки сигнала дочернему процессу.
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
