"""Content-verified images stored under opaque UUIDs in a dedicated volume."""

import io
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
            image = oriented.convert("RGB" if format_name == "JPEG" else "RGBA")
            image.info.clear()
            output = io.BytesIO()
            image.save(output, format=format_name, **({"quality": 90} if format_name != "PNG" else {}))
            thumb = image.copy()
            thumb.thumbnail((480, 480))
            thumbnail = io.BytesIO()
            thumb.save(thumbnail, format=format_name, **({"quality": 85} if format_name != "PNG" else {}))
            if output.tell() > 50 * 1024 * 1024:
                raise ApiException(413, "IMAGE_TOO_LARGE", "Normalized image exceeds the storage limit")
            return output.getvalue(), thumbnail.getvalue(), FORMATS[format_name][0], image.width, image.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
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
        # A failed unlink can only leave an inaccessible orphan, never remove another record's files.
        for thumbnail in (False, True):
            try:
                self.path(identifier, row["mime_type"], thumbnail).unlink(missing_ok=True)
            except OSError:
                pass
