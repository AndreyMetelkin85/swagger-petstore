"""Fetch pinned Flyway parser libraries; reject bad CDN responses instead of caching them."""

import hashlib
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

REPOSITORIES = ("https://repo.maven.apache.org/maven2/", "https://repo1.maven.org/maven2/")
ARTIFACTS = {
    "tools/jackson/core/jackson-core/3.1.7/jackson-core-3.1.7.jar": "7608c367fd8a92666d28711519599543c180298259963184ce04d2947a8f71e7",
    "tools/jackson/core/jackson-databind/3.1.7/jackson-databind-3.1.7.jar": "48c781de87e2016e1f0d973748a27130f11643e7ac080173f40e2d9669d84be3",
    "tools/jackson/dataformat/jackson-dataformat-toml/3.1.7/jackson-dataformat-toml-3.1.7.jar": "ad24a4f51c9a2dcb397dd1f89938fdf3c38ff48f61b85c4a4edd02fe7671fdf0",
}
MAX_BYTES = 10 * 1024 * 1024


def fetch_verified(relative: str, expected: str) -> bytes:
    """Retry official Central mirrors without accepting HTTP errors or altered content.

    :param relative: Pinned artifact path from the build manifest.
    :param expected: Independently pinned SHA-256, unchanged from the released Dockerfile.
    """
    for attempt in range(6):
        try:
            with urlopen(REPOSITORIES[attempt % len(REPOSITORIES)] + relative, timeout=30) as response:
                payload = bytes(response.read(MAX_BYTES + 1))
            if len(payload) > MAX_BYTES or hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError("Artifact integrity verification failed")
            return payload
        except (URLError, OSError, ValueError) as exc:
            if attempt == 5:
                raise RuntimeError(
                    "Verified migration artifact is unavailable: " + Path(relative).name
                ) from exc
            # Public artifact name and attempt only; never print response bodies.
            print(
                "artifact_fetch_retry name=" + Path(relative).name + " attempt=" + str(attempt + 1),
                flush=True,
            )
            time.sleep(min(2**attempt, 30))
    raise AssertionError("Unreachable artifact retry state")


def main(destination: Path = Path("/migration-artifacts")) -> None:
    """Write only verified libraries into this isolated build stage.

    :param destination: Build-owned output directory, never a runtime data volume.
    """
    destination.mkdir(parents=True, exist_ok=True)
    for relative, expected in ARTIFACTS.items():
        payload = fetch_verified(relative, expected)
        (destination / Path(relative).name).write_bytes(payload)


if __name__ == "__main__":
    main()
