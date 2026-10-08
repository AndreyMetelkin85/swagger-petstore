"""Add bundled photographs through catalog services, without resetting existing data."""

import hashlib
import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, override
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from petstore.config import Settings
from petstore.data.database import Database, DbConnection, Row
from petstore.model.commerce import CategoryCommand, PetCardCommand, ProductCommand
from petstore.service.catalog_service import CatalogService
from petstore.service.media_service import MediaService, normalize_image

logger = logging.getLogger("petstore.demo_catalog")
STATE_FILE = ".demo-catalog-v1.json"
PREFIX = "lapki-photo-catalog-v1:"


class PhotoCard(BaseModel):
    """Validate the trusted package manifest before making database changes."""

    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern="^[a-z][a-z0-9-]+$")
    kind: Literal["product", "pet"]
    category: str
    file: str = Field(pattern="^[a-z0-9-]+\\.jpg$")
    sha256: str = Field(pattern="^[a-f0-9]{64}$")
    source_note: str = Field(max_length=850)
    card: ProductCommand | PetCardCommand


class SeedState(BaseModel):
    """Persistent references only; no credentials or customer information."""

    model_config = ConfigDict(extra="forbid")
    namespace: str
    completed: bool = False
    entries: dict[str, UUID] = Field(default_factory=dict)
    pending_media: list[UUID] = Field(default_factory=list[UUID])


class _TransactionDatabase(Database):
    """Bind existing services to the bootstrap transaction, including the row locks."""

    def __init__(self, connection: DbConnection) -> None:
        self.connection = connection

    @override
    @contextmanager
    def connect(self) -> Generator[DbConnection, None, None]:
        yield self.connection


def save_state(path: Path, state: SeedState) -> None:
    """Atomically replace a journal located inside the existing media volume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_package(settings: Settings) -> list[tuple[PhotoCard, bytes]]:
    """Reject damaged images or commands before creating any card."""
    root = settings.resources / "demo-catalog"
    records = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    result: list[tuple[PhotoCard, bytes]] = []
    for raw in records:
        kind = raw["kind"]
        raw["card"] = (
            ProductCommand.model_validate(raw["card"])
            if kind == "product"
            else PetCardCommand.model_validate(raw["card"])
        )
        entry = PhotoCard.model_validate(raw)
        payload = (root / entry.file).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry.sha256:
            raise ValueError("Bundled catalog photograph checksum mismatch")
        normalize_image(payload)
        result.append((entry, payload))
    if len(result) != 8 or len({entry.key for entry, _ in result}) != 8:
        raise ValueError("Bundled catalog requires eight unique cards")
    return result


def populate_demo_catalog(database: Database, settings: Settings) -> SeedState:
    """Create the agreed sample once; retain sales, edits, archives and deliberate deletions.

    The whole package uses one database transaction. A durable file journal records pending
    uploads so a killed startup can remove only its own rolled-back files on the next attempt.
    The media provenance recovers committed cards if journal finalization was interrupted.
    """
    package = load_package(settings)
    state_path = settings.media_root / STATE_FILE
    created_media: list[UUID] = []
    media: MediaService | None = None
    try:
        with database.connect() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(742819015)")
            actor = connection.execute(
                "SELECT id,role FROM users WHERE role='ADMIN' AND user_status='ACTIVE' ORDER BY id LIMIT 1"
            ).fetchone()
            if actor is None:
                raise ValueError("Demo catalog needs an active administrator")
            identity = connection.execute(
                "SELECT current_database() AS name,installed_on FROM flyway_schema_history ORDER BY installed_rank LIMIT 1"
            ).fetchone()
            assert identity is not None
            namespace = f"{identity['name']}:{identity['installed_on']}"
            state = SeedState(namespace=namespace)
            if state_path.exists():
                saved = SeedState.model_validate_json(state_path.read_text(encoding="utf-8"))
                if saved.namespace == namespace:
                    state = saved
            bound = _TransactionDatabase(connection)
            catalog = CatalogService(bound)
            media = MediaService(bound, settings)
            for identifier in state.pending_media:
                stored = connection.execute("SELECT id FROM media WHERE id=%s", (identifier,)).fetchone()
                if stored is None:
                    for thumbnail in (False, True):
                        media.path(identifier, "image/jpeg", thumbnail).unlink(missing_ok=True)
            state.pending_media = []
            if state.completed:
                return state
            for entry, payload in package:
                note = PREFIX + entry.key + " | " + entry.source_note
                parent = "product_id" if entry.kind == "product" else "pet_id"
                recovered = connection.execute(
                    f"SELECT i.{parent} AS id FROM catalog_images i JOIN media m ON m.id=i.media_id "
                    f"WHERE m.source_type='DEMO' AND m.source_note=%s AND i.{parent} IS NOT NULL LIMIT 1",
                    (note,),
                ).fetchone()
                if recovered is not None:
                    state.entries[entry.key] = recovered["id"]
                    continue
                categories = catalog.categories(False, entry.kind)
                category = next((row for row in categories if row["name"] == entry.category), None)
                if category is None:
                    category = catalog.save_category(CategoryCommand(name=entry.category, kind=entry.kind))
                if not category["active"]:
                    raise ValueError("Demo category is inactive; bootstrap cannot override it")
                uploaded = media.upload(payload, "DEMO", note, actor)
                identifier = UUID(str(uploaded["id"]))
                created_media.append(identifier)
                state.pending_media.append(identifier)
                save_state(state_path, state)
                command: Row = entry.card.model_dump(by_alias=True)
                command["categoryId"] = category["id"]
                command["images"] = [{"mediaId": identifier, "alt": entry.card.name, "isCover": True}]
                request = (
                    ProductCommand.model_validate(command)
                    if entry.kind == "product"
                    else PetCardCommand.model_validate(command)
                )
                record = catalog.save(request)
                catalog.publish(entry.kind, record["id"], record["version"], "PUBLISHED")
                state.entries[entry.key] = record["id"]
        state.completed = True
        state.pending_media = []
        save_state(state_path, state)
        logger.info("demo_catalog_ready cards=%s", len(state.entries))
        return state
    except Exception:
        # Only paths for uploads made by this attempt; never remove pre-existing records or files.
        if media is not None:
            with database.connect() as connection:
                for identifier in created_media:
                    if (
                        connection.execute("SELECT id FROM media WHERE id=%s", (identifier,)).fetchone()
                        is None
                    ):
                        for thumbnail in (False, True):
                            media.path(identifier, "image/jpeg", thumbnail).unlink(missing_ok=True)
        logger.error("demo_catalog_failed")
        raise
