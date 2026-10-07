"""Content-verified images stored under opaque UUIDs in a dedicated volume."""

import io
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import BoundedSemaphore
from uuid import UUID, uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from petstore.config import Settings
from petstore.data.database import Database, DbConnection, Row
from petstore.service.exceptions import ApiException

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40000000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
IMAGE_WORKERS = BoundedSemaphore(2)
FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
logger = logging.getLogger("petstore.media")


def normalize_image(payload: bytes) -> tuple[bytes, bytes, str, int, int]:
    """Verify type/frames/pixels, apply orientation and re-encode without metadata.

    :param payload: Bounded uploaded bytes; filenames/content-type are not trusted.
    """
    if not payload or len(payload) > MAX_BYTES:
        raise ApiException(413, "IMAGE_TOO_LARGE", "Image must be nonempty and at most 10 MiB")
    if not IMAGE_WORKERS.acquire(blocking=False):
        raise ApiException(503, "MEDIA_STORAGE_UNAVAILABLE", "Image processing is busy; retry later")
    try:
        with Image.open(io.BytesIO(payload)) as probe:
            format_name = probe.format
            if format_name not in FORMATS:
                raise ApiException(
                    415, "INVALID_IMAGE_FORMAT", "Only JPEG, PNG and static WebP are supported"
                )
            width, height = probe.size
            if width * height > MAX_PIXELS:
                raise ApiException(413, "IMAGE_TOO_LARGE", "Image exceeds 40 megapixels")
            if getattr(probe, "n_frames", 1) != 1:
                raise ApiException(422, "ANIMATED_IMAGE_NOT_ALLOWED", "Animated images are not supported")
            probe.verify()
        with Image.open(io.BytesIO(payload)) as opened:
            oriented = ImageOps.exif_transpose(opened)
            oriented.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            rgba = oriented.convert("RGBA")
            image = Image.new("RGB", rgba.size, "white")
            image.paste(rgba, mask=rgba.getchannel("A"))
            image.info.clear()
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=90)
            thumb = image.copy()
            thumb.thumbnail((400, 400), Image.Resampling.LANCZOS)
            thumbnail = io.BytesIO()
            thumb.save(thumbnail, format="JPEG", quality=85)
            if output.tell() > 50 * 1024 * 1024:
                raise ApiException(413, "IMAGE_TOO_LARGE", "Normalized image exceeds the storage limit")
            return output.getvalue(), thumbnail.getvalue(), "image/jpeg", image.width, image.height
    except Image.DecompressionBombError as exc:
        raise ApiException(413, "IMAGE_TOO_LARGE", "Image exceeds 40 megapixels") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ApiException(422, "INVALID_IMAGE", "Image content is invalid or cannot be decoded") from exc
    finally:
        IMAGE_WORKERS.release()


class MediaService:
    """Database metadata plus bounded, content-verified local storage."""

    def __init__(self, database: Database, settings: Settings) -> None:
        """Configure storage without touching files or opening connections."""
        self.database = database
        self.root = settings.media_root

    def path(self, identifier: UUID, mime: str, thumbnail: bool = False) -> Path:
        """Derive a safe path only from a parsed UUID and persisted MIME."""
        extension = next((ext for media_type, ext in FORMATS.values() if media_type == mime), None)
        if extension is None:
            raise ApiException(503, "MEDIA_STORAGE_UNAVAILABLE", "Stored image format is unavailable")
        return self.root / (str(identifier) + (".thumb" if thumbnail else "") + "." + extension)

    @staticmethod
    def public(row: Row) -> Row:
        """Expose metadata, not filenames, paths, creator identity or raw EXIF."""
        return {
            "id": row["id"],
            "name": "image-" + str(row["id"]),
            "mime": row["mime_type"],
            "width": row["width"],
            "height": row["height"],
            "size": row["size_bytes"],
            "sourceType": row["source_type"],
            "sourceNote": row["source_note"],
            "createdAt": row["created_at"],
            "imageUrl": f"/api/v3/media/{row['id']}/image",
            "thumbUrl": f"/api/v3/media/{row['id']}/thumb",
        }

    def upload(self, payload: bytes, source_type: str, source_note: str, actor: Row) -> Row:
        """Write sanitized files and metadata; roll back this upload's files on failure."""
        if source_type not in {"OWN", "SUPPLIER", "DEMO"} or len(source_note) > 1000:
            raise ApiException(422, "VALIDATION_ERROR", "Invalid image source metadata")
        image, thumb, mime, width, height = normalize_image(payload)
        identifier = uuid4()
        paths = [self.path(identifier, mime), self.path(identifier, mime, True)]
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            # Exclusive creation prevents accidental overwrite; identifiers never come from the client.
            for path, data in zip(paths, [image, thumb], strict=True):
                with path.open("xb") as target:
                    target.write(data)
            with self.database.connect() as connection:
                row = connection.execute(
                    "INSERT INTO media (id,mime_type,width,height,size_bytes,source_type,source_note,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                    (identifier, mime, width, height, len(image), source_type, source_note, actor["id"]),
                ).fetchone()
                assert row is not None
                return self.public(row)
        except Exception as exc:
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            if isinstance(exc, OSError):
                raise ApiException(503, "MEDIA_STORAGE_UNAVAILABLE", "Image storage is unavailable") from exc
            raise

    @staticmethod
    def visible(connection: DbConnection, identifier: UUID, actor: Row | None) -> bool:
        """Allow public published galleries or the owning order's retained cover."""
        if actor and actor["role"] == "ADMIN":
            return True
        published = connection.execute(
            """SELECT 1 FROM catalog_images i
               LEFT JOIN products p ON p.id=i.product_id LEFT JOIN pets a ON a.id=i.pet_id
               WHERE i.media_id=%s AND (p.publication_status='PUBLISHED' OR a.publication_status='PUBLISHED') LIMIT 1""",
            (identifier,),
        ).fetchone()
        if published:
            return True
        if actor:
            return (
                connection.execute(
                    "SELECT 1 FROM order_lines l JOIN store_orders o ON o.id=l.order_id WHERE l.cover_id=%s AND o.owner_user_id=%s LIMIT 1",
                    (identifier, actor["id"]),
                ).fetchone()
                is not None
            )
        return False

    def get(
        self, identifier: UUID, actor: Row | None, thumbnail: bool | None = None
    ) -> Row | tuple[bytes, str]:
        """Read authorized metadata or sanitized bytes without following client paths."""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM media WHERE id=%s AND NOT deleted", (identifier,)
            ).fetchone()
            if row is None or not self.visible(connection, identifier, actor):
                raise ApiException(404, "MEDIA_NOT_FOUND", "Media was not found")
            if thumbnail is None:
                return self.public(row)
            try:
                return self.path(identifier, row["mime_type"], thumbnail).read_bytes(), row["mime_type"]
            except OSError as exc:
                raise ApiException(503, "MEDIA_STORAGE_UNAVAILABLE", "Image storage is unavailable") from exc

    def delete(self, identifier: UUID) -> None:
        """Tombstone only unreferenced media; retained order covers forbid deletion."""
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM media WHERE id=%s AND NOT deleted FOR UPDATE", (identifier,)
            ).fetchone()
            if row is None:
                raise ApiException(404, "MEDIA_NOT_FOUND", "Media was not found")
            used = connection.execute(
                "SELECT 1 WHERE EXISTS (SELECT 1 FROM catalog_images WHERE media_id=%s) OR EXISTS (SELECT 1 FROM order_lines WHERE cover_id=%s)",
                (identifier, identifier),
            ).fetchone()
            if used:
                raise ApiException(409, "MEDIA_IN_USE", "Media is used by a card or order snapshot")
            connection.execute("UPDATE media SET deleted=TRUE WHERE id=%s", (identifier,))
        self.remove_files(row)

    def remove_files(self, row: Row) -> bool:
        """Remove only a tombstoned UUID's two files; failed removals remain retryable."""
        for thumbnail in (False, True):
            try:
                self.path(row["id"], row["mime_type"], thumbnail).unlink(missing_ok=True)
            except (OSError, ApiException):
                logger.warning("media_cleanup_failed resourceId=%s", row["id"])
                return False
        with self.database.connect() as connection:
            connection.execute("UPDATE media SET files_removed=TRUE WHERE id=%s AND deleted", (row["id"],))
        return True

    def cleanup(self, limit: int = 100) -> int:
        """Tombstone unlinked uploads older than 24 hours, then retry safe file removals.

        Gallery writers share the media row lock. SKIP LOCKED never delays a save;
        links are rechecked after locking, including drafts and immutable order covers.
        :param limit: Bounded batch size, never a client-provided filesystem path.
        :return: Number of completed file removals in this batch.
        """
        if not 1 <= limit <= 1000:
            raise ValueError("Cleanup batch must be between 1 and 1000")
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT m.* FROM media m WHERE (m.deleted AND NOT m.files_removed)
                   OR (NOT m.deleted AND m.created_at <= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                       AND NOT EXISTS (SELECT 1 FROM catalog_images i WHERE i.media_id=m.id)
                       AND NOT EXISTS (SELECT 1 FROM order_lines l WHERE l.cover_id=m.id))
                   ORDER BY m.created_at,m.id LIMIT %s FOR UPDATE OF m SKIP LOCKED""",
                (limit,),
            ).fetchall()
            removable: list[Row] = []
            for row in rows:
                linked = connection.execute(
                    "SELECT 1 WHERE EXISTS (SELECT 1 FROM catalog_images WHERE media_id=%s) OR EXISTS (SELECT 1 FROM order_lines WHERE cover_id=%s)",
                    (row["id"], row["id"]),
                ).fetchone()
                if linked:
                    continue
                connection.execute("UPDATE media SET deleted=TRUE WHERE id=%s", (row["id"],))
                removable.append(row)
        removed = sum(self.remove_files(row) for row in removable)
        self.cleanup_orphan_files(limit)
        return removed

    def cleanup_orphan_files(self, limit: int = 100) -> int:
        """Remove aged UUID files left before metadata commit, never arbitrary files or directories."""
        if not self.root.is_dir():
            return 0
        cutoff = datetime.now(UTC).timestamp() - 86400
        removed = 0
        for path in self.root.iterdir():
            match = re.fullmatch(r"([a-f0-9-]{36})(?:\.thumb)?\.(jpg|png|webp)", path.name)
            if not match or path.is_symlink() or not path.is_file():
                continue
            try:
                identifier = UUID(match[1])
                if path.stat().st_mtime > cutoff:
                    continue
                with self.database.connect() as connection:
                    existing = connection.execute(
                        "SELECT id FROM media WHERE id=%s", (identifier,)
                    ).fetchone()
                    if existing is None:
                        path.unlink(missing_ok=True)
                        removed += 1
                if removed >= limit:
                    break
            except (ValueError, OSError):
                continue
        return removed
