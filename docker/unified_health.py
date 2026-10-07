"""Readiness of every embedded component, without printing diagnostic payloads."""

import os
from urllib.request import urlopen

urls = ["http://127.0.0.1:8080/api/v3/health", "http://127.0.0.1:8090/healthz"]
if os.getenv("PETSTORE_EMBEDDED_MAIL", "true").lower() == "true":
    urls.append("http://127.0.0.1:8025/api/Messages?pageSize=1")
for url in urls:
    with urlopen(url, timeout=3) as response:
        if response.status != 200:
            raise SystemExit(1)
