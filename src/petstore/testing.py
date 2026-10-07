"""Opt-in CLI for dedicated training/test databases; never a public reset endpoint."""

import argparse
import io
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from PIL import Image
from psycopg.types.json import Jsonb

from petstore.config import Settings
from petstore.data.database import Database, DbConnection, Row
from petstore.data.order_data import OrderData
from petstore.service.credential_service import CredentialService
from petstore.service.media_service import MediaService, normalize_image

ADMIN_ID = UUID(int=1)
USER_ID = UUID(int=2)
PRODUCT_CATEGORY_ID = UUID(int=3)
PET_CATEGORY_ID = UUID(int=4)
PRODUCT_ID = UUID(int=10)
PET_ID = UUID(int=20)


def require_test_database(settings: Settings) -> None:
    """Require both explicit opt-in and a dedicated name; reject the normal petstore database."""
    name = urlsplit(settings.db_url).path.removeprefix("/")
    dedicated = name in {"petstore_python_test", "petstore_training"} or re.fullmatch(
        r"petstore_training_[a-f0-9]{12}", name
    )
    if not settings.test_support or not dedicated:
        raise ValueError("Test support requires PETSTORE_TEST_SUPPORT=true and a dedicated test database")


def verify_connected_database(connection: DbConnection, settings: Settings) -> None:
    """Do not trust a claimed URL: the actual connection must point at that isolated database."""
    row = connection.execute("SELECT current_database() AS name").fetchone()
    if row is None or row["name"] != urlsplit(settings.db_url).path.removeprefix("/"):
        raise ValueError("Actual connection is not the requested isolated database")


def expire_order(database: Database, settings: Settings, identifier: UUID) -> None:
    """Expire only an unpaid placed order in the isolated lab, using the real stock reconciliation."""
    require_test_database(settings)
    with database.connect() as connection:
        verify_connected_database(connection, settings)
        order = OrderData.lock_order(connection, identifier)
        if order["status"] != "placed" or order["payment_status"] != "UNPAID":
            raise ValueError("Only an unpaid placed order may be expired by test support")
        deadline = datetime.now(UTC)
        connection.execute(
            "UPDATE store_orders SET payment_expires_at=%s WHERE id=%s", (deadline, identifier)
        )
        order["payment_expires_at"] = deadline
        OrderData.expire_locked_order_if_needed(connection, order)


def reset_lab(database: Database, settings: Settings, confirmed: bool = False) -> Row:
    """Restore a known lab dataset; preserve Flyway history and invalidate old demo sessions.

    :param confirmed: Explicit destructive-reset acknowledgment for this isolated database only.
    :return: Fixed IDs for examples, without credentials, tokens or personal data.
    """
    require_test_database(settings)
    if not confirmed:
        raise ValueError("Use --confirm-test-reset to acknowledge removal of the isolated lab data")
    service = MediaService(database, settings)
    picture = io.BytesIO()
    Image.new("RGB", (640, 400), "#e8d9c2").save(picture, format="PNG")
    image, thumb, mime, width, height = normalize_image(picture.getvalue())
    media_id = uuid4()
    settings.media_root.mkdir(parents=True, exist_ok=True)
    paths = [service.path(media_id, mime), service.path(media_id, mime, True)]
    try:
        for path, payload in zip(paths, (image, thumb), strict=True):
            with path.open("xb") as file:
                file.write(payload)
        with database.connect() as connection:
            verify_connected_database(connection, settings)
            connection.execute("SELECT pg_advisory_xact_lock(1813511001)")
            version = connection.execute(
                "SELECT COALESCE(MAX(token_version),0)+1 AS version FROM users"
            ).fetchone()
            assert version is not None
            old_media = connection.execute("SELECT * FROM media").fetchall()
            connection.execute(
                "TRUNCATE payments,order_lines,api_idempotency,cart_lines,carts,store_orders,catalog_images,stock_adjustments,products,pets,protected_user_accounts,media,catalog_categories,users RESTART IDENTITY"
            )
            for identifier, username, email, password, role in (
                (ADMIN_ID, "admin", "admin@example.com", "admin123", "ADMIN"),
                (USER_ID, "user1", "test@example.com", "password123", "USER"),
            ):
                connection.execute(
                    """INSERT INTO users (id,username,first_name,last_name,email,password,phone,role,user_status,confirmed_at,token_version,address_city,address_street,address_house,address_postal_code)
                   VALUES (%s,%s,'Учебный','Пользователь',%s,%s,'+79990000000',%s,'ACTIVE',CURRENT_TIMESTAMP,%s,'Учебный город','Учебная улица','1','123456')""",
                    (
                        identifier,
                        username,
                        email,
                        CredentialService.hash_password(password),
                        role,
                        version["version"],
                    ),
                )
            connection.execute(
                "INSERT INTO protected_user_accounts (user_id,reason) VALUES (%s,'DEMO_USER')", (USER_ID,)
            )
            for identifier, name, kind in (
                (PRODUCT_CATEGORY_ID, "Корма", "product"),
                (PET_CATEGORY_ID, "Питомцы", "pet"),
            ):
                connection.execute(
                    "INSERT INTO catalog_categories (id,name,kind) VALUES (%s,%s,%s)",
                    (identifier, name, kind),
                )
            connection.execute(
                "INSERT INTO media (id,mime_type,width,height,size_bytes,source_type,source_note,created_by) VALUES (%s,%s,%s,%s,%s,'DEMO','Учебный каталог',%s)",
                (media_id, mime, width, height, len(image), ADMIN_ID),
            )
            connection.execute(
                """INSERT INTO products (id,sku,name,category_id,brand,product_type,animal_types,price,feed_form,life_stages,net_weight_grams,publication_status,stock)
                VALUES (%s,'TRAINING-FEED','Учебный корм',%s,'Учебный бренд','FEED',%s,100,'DRY',%s,1000,'PUBLISHED',5)""",
                (PRODUCT_ID, PRODUCT_CATEGORY_ID, Jsonb(["cat"]), Jsonb(["ADULT"])),
            )
            connection.execute(
                "INSERT INTO pets (id,name,price,category_id,animal_type,publication_status,status) VALUES (%s,'Учебный кот',50,%s,'cat','PUBLISHED','available')",
                (PET_ID, PET_CATEGORY_ID),
            )
            connection.execute(
                "INSERT INTO catalog_images (media_id,product_id,position,alt,is_cover) VALUES (%s,%s,0,'Учебный корм, фото 1',TRUE)",
                (media_id, PRODUCT_ID),
            )
            connection.execute(
                "INSERT INTO catalog_images (media_id,pet_id,position,alt,is_cover) VALUES (%s,%s,0,'Учебный кот, фото 1',TRUE)",
                (media_id, PET_ID),
            )
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    for row in old_media:
        for thumbnail in (False, True):
            try:
                service.path(row["id"], row["mime_type"], thumbnail).unlink(missing_ok=True)
            except OSError:
                pass
    return {"productId": str(PRODUCT_ID), "petId": str(PET_ID), "mediaId": str(media_id)}


def main() -> None:
    """Run only a requested isolated-lab action; fail closed without echoing database settings."""
    parser = argparse.ArgumentParser(description="Isolated Petstore test support")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset")
    reset.add_argument("--confirm-test-reset", action="store_true")
    expire = commands.add_parser("expire-order")
    expire.add_argument("order_id", type=UUID)
    args = parser.parse_args()
    settings = Settings.from_env()
    require_test_database(settings)
    database = Database(settings)
    database.start()
    try:
        if args.command == "reset":
            result = reset_lab(database, settings, args.confirm_test_reset)
            print("Test dataset restored", result)
        else:
            expire_order(database, settings, args.order_id)
            print("Unpaid test order expired")
    finally:
        database.close()


if __name__ == "__main__":
    main()
