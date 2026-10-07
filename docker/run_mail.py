"""Supervise embedded SMTP without writing recipients or message content to container logs."""

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
    """Forward shutdown to this wrapper's own child."""
    if process.poll() is None:
        process.terminate()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
assert process.stdout is not None
for line in process.stdout:
    if line.startswith(("[ERR]", "[FTL]", "fail:", "crit:")):
        print("embedded_mail_error", flush=True)
    elif "SMTP Server is listening" in line:
        print("embedded_mail_ready", flush=True)
status = process.wait()
print(f"embedded_mail_stopped status={status}", flush=True)
raise SystemExit(status if status >= 0 else 128 - status)
