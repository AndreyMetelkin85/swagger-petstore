import json
import os
import subprocess

import pytest

pytestmark = pytest.mark.system


def test_api_container_has_only_api_process_and_media_volume():
    container = os.getenv("PETSTORE_RESTART_CONTAINER")
    if not container:
        pytest.skip("Укажите контейнер изолированного API-стенда")
    assert container == "petstore-python-preview"
    processes = subprocess.run(
        ["docker", "top", container, "-eo", "pid,args"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout
    assert "uvicorn" in processes
    assert not any(name in processes for name in ("postgres -", "nginx", "Rnwood.Smtp4dev", "java -"))
    mounts = json.loads(
        subprocess.run(
            ["docker", "inspect", "--format", "{{json .Mounts}}", container],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    )
    assert {mount["Destination"] for mount in mounts} == {"/var/lib/petstore/media"}
