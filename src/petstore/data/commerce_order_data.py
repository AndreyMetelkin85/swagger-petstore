"""Mixed checkout over the existing order/payment parent, with atomic allocations."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from psycopg.types.json import Jsonb

from petstore.data.cart_data import CartData
from petstore.data.catalog_data import CatalogData
from petstore.data.database import Database, DbConnection, Row
from petstore.data.idempotency_data import IdempotencyData
from petstore.data.order_data import OrderData
from petstore.data.user_data import UserData
from petstore.model.commerce import CheckoutCommand
from petstore.model.enums import OrderStatus
from petstore.service.exceptions import ApiException
from petstore.service.validation_service import ValidationService
from petstore.utils.responses import Responses, public_user


class CommerceOrderData:
    """Order lock precedes all sorted inventory locks; payment uses that same parent."""

    def __init__(self, database: Database) -> None:
        """Use one pool and never split inventory changes across transactions."""
        self.database = database

    @staticmethod
    def lines(connection: DbConnection, identifier: UUID) -> list[Row]:
        """Read immutable checkout lines in their display order."""
        return connection.execute(
            "SELECT * FROM order_lines WHERE order_id=%s ORDER BY position", (identifier,)
        ).fetchall()

    @classmethod
    def public(cls, connection: DbConnection, order: Row) -> Row:
        """Expose a common history DTO, adapting legacy single-pet parents on reads."""
        lines = cls.lines(connection, order["id"])
        if order["order_kind"] == "LEGACY":
            pet = connection.execute("SELECT name FROM pets WHERE id=%s", (order["pet_id"],)).fetchone()
            items: list[Row] = [
                {
                    "kind": "pet",
                    "itemId": order["pet_id"],
                    "name": pet["name"] if pet else "Legacy pet",
                    "sku": "",
                    "quantity": order["quantity"],
                    "price": order["unit_price"],
                    "images": [],
                }
            ]
        else:
            items = [
                {
                    "kind": r["item_type"],
                    "itemId": r["item_id"],
                    "name": r["name"],
                    "sku": r["sku"],
                    "quantity": r["quantity"],
                    "price": r["unit_price"],
                    "images": r["snapshot"].get("images", []),
                    "allocation": r["allocation"],
                }
                for r in lines
            ]
        return {
            "id": order["id"],
            "userId": order["owner_user_id"],
            "status": order["status"],
            "paymentStatus": order["payment_status"],
            "version": order["version"],
            "cartVersion": order["cart_version"],
            "createdAt": order["created_at"],
            "shipDate": order["ship_date"],
            "paymentExpiresAt": order["payment_expires_at"],
            "lines": items,
            "total": order["total_amount"],
            "currency": order["currency"],
            "delivery": order["delivery_details"],
            "complete": order["complete"],
        }

    def get(self, identifier: UUID, actor: Row) -> Row:
        """Read only an owned order (or any order as ADMIN), reconciling expiry first."""
        self.expire()
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor)
            return self.public(connection, order)

    def find_all(self, actor: Row) -> list[Row]:
        """Include preserved legacy records in the new order history."""
        self.expire()
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM store_orders WHERE (%s = 'ADMIN' OR owner_user_id=%s) ORDER BY created_at DESC,id",
                (actor["role"], actor["id"]),
            ).fetchall()
            return [self.public(connection, row) for row in rows]

    def create(self, command: CheckoutCommand, actor: Row, key: UUID) -> tuple[Row, bool]:
        """Snapshot server-side cart quotes without reserving stock."""
        payload = command.model_dump()
        with self.database.connect() as connection:
            replay = IdempotencyData.replay(connection, actor["id"], "order:create", key, payload)
            if replay:
                return replay[0], True
            cart = CartData.lock(connection, actor["id"])
            if cart["version"] != command.cart_version:
                raise ApiException(409, "CART_VERSION_CONFLICT", "Cart changed before checkout")
            lines = connection.execute(
                "SELECT * FROM cart_lines WHERE user_id=%s ORDER BY item_type,item_id", (actor["id"],)
            ).fetchall()
            if not lines:
                raise ApiException(422, "CART_EMPTY", "Cart must contain at least one item")
            parent = connection.execute(
                """INSERT INTO store_orders (owner_user_id,pet_id,quantity,status,order_kind,payment_status,cart_version)
                   VALUES (%s,NULL,1,'draft','MIXED','NOT_STARTED',%s) RETURNING *""",
                (actor["id"], cart["version"]),
            ).fetchone()
            assert parent is not None
            inventory = self.inventory_locks(connection, lines)
            galleries = {
                (line["item_type"], line["item_id"]): CatalogData.gallery(
                    connection, line["item_type"], line["item_id"]
                )
                for line in lines
            }
            covers = {
                identity: next((image for image in gallery if image["isCover"]), None)
                for identity, gallery in galleries.items()
            }
            # Inventory always precedes all sorted media locks, including multi-card checkout.
            for media_id in sorted({image["mediaId"] for image in covers.values() if image}, key=str):
                connection.execute("SELECT id FROM media WHERE id=%s AND NOT deleted FOR UPDATE", (media_id,))
            for position, line in enumerate(lines):
                identity = (line["item_type"], line["item_id"])
                item = inventory[identity]
                if item["publication_status"] != "PUBLISHED":
                    raise ApiException(409, "PRODUCT_UNAVAILABLE", "A cart item is no longer published")
                cover = covers[identity]
                price = line["price_snapshot"] if line["price_snapshot"] is not None else item["price"]
                snapshot = {"images": [cover] if cover else []}
                connection.execute(
                    """INSERT INTO order_lines (order_id,position,item_type,item_id,quantity,name,sku,unit_price,cover_id,snapshot)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        parent["id"],
                        position,
                        line["item_type"],
                        line["item_id"],
                        line["quantity"],
                        item["name"],
                        item.get("sku", ""),
                        price,
                        cover["mediaId"] if cover else None,
                        Jsonb(json.loads(bytes(Responses(snapshot).body))),
                    ),
                )
            result = self.public(connection, parent)
            IdempotencyData.save(connection, actor["id"], "order:create", key, payload, result, 201)
            return result, False

    @staticmethod
    def inventory_locks(connection: DbConnection, lines: list[Row]) -> dict[tuple[str, UUID], Row]:
        """Lock all resources in one deterministic order across checkout/cancel/expiry."""
        return {
            (r["item_type"], r["item_id"]): CatalogData.locked(connection, r["item_type"], r["item_id"])
            for r in sorted(lines, key=lambda r: (r["item_type"], str(r["item_id"])))
        }

    def place(self, identifier: UUID, actor: Row, version: int, key: UUID) -> Row:
        """Validate the entire composition before atomically reserving any item."""
        self.expire()
        payload: Row = {"orderId": str(identifier), "version": version}
        with self.database.connect() as connection:
            replay = IdempotencyData.replay(connection, actor["id"], "order:place", key, payload)
            if replay:
                return replay[0]
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor, modifying=True)
            CatalogData.version(order, version, "ORDER_VERSION_CONFLICT")
            if order["order_kind"] != "MIXED" or order["status"] != "draft":
                raise ApiException(409, "INVALID_STATUS_TRANSITION", "Only a mixed draft can be placed")
            owner = UserData.locked_user(connection, order["owner_user_id"])
            missing = ValidationService.missing_order_profile_fields(owner)
            if missing:
                raise ApiException(
                    409,
                    "PROFILE_INCOMPLETE",
                    "Complete the delivery profile before placing an order",
                    missing,
                )
            lines = self.lines(connection, identifier)
            inventory = self.inventory_locks(connection, lines)
            total = Decimal("0")
            for line in lines:
                item = inventory[(line["item_type"], line["item_id"])]
                if item["publication_status"] != "PUBLISHED":
                    raise ApiException(409, "PRODUCT_UNAVAILABLE", "A checkout item is unpublished")
                if item["price"] != line["unit_price"]:
                    raise ApiException(409, "PRICE_CHANGED", "A checkout price changed; refresh the cart")
                if line["item_type"] == "product" and item["stock"] - item["reserved"] < line["quantity"]:
                    raise ApiException(409, "INSUFFICIENT_STOCK", "Not enough unreserved stock")
                if line["item_type"] == "pet" and item["status"] != "available":
                    raise ApiException(409, "PET_NOT_AVAILABLE", "Pet is already reserved or unavailable")
                total += item["price"] * line["quantity"]
            if total > Decimal("999999999999.99"):
                raise ApiException(422, "VALIDATION_ERROR", "Order total exceeds the monetary limit")
            for line in lines:
                if line["item_type"] == "product":
                    connection.execute(
                        "UPDATE products SET reserved=reserved+%s,version=version+1 WHERE id=%s",
                        (line["quantity"], line["item_id"]),
                    )
                else:
                    OrderData.update_pet_status(connection, line["item_id"], "reserved")
                connection.execute(
                    "UPDATE order_lines SET allocation='RESERVED' WHERE order_id=%s AND position=%s",
                    (identifier, line["position"]),
                )
            profile = public_user(owner)
            delivery = {name: profile[name] for name in ("firstName", "lastName", "phone", "address")}
            updated = connection.execute(
                """UPDATE store_orders SET status='placed',payment_status='UNPAID',total_amount=%s,delivery_details=%s,
                   payment_expires_at=CURRENT_TIMESTAMP+INTERVAL '15 minutes',version=version+1 WHERE id=%s RETURNING *""",
                (total, Jsonb(delivery), identifier),
            ).fetchone()
            assert updated is not None
            result = self.public(connection, updated)
            IdempotencyData.save(connection, actor["id"], "order:place", key, payload, result, 200)
            return result

    @classmethod
    def release(cls, connection: DbConnection, order: Row, consume: bool = False) -> None:
        """Release/consume RESERVED allocations exactly once under the parent lock."""
        if order["order_kind"] == "LEGACY":
            connection.execute("SELECT id FROM pets WHERE id=%s FOR UPDATE", (order["pet_id"],))
            OrderData.update_pet_status(connection, order["pet_id"], "sold" if consume else "available")
            return
        lines = [r for r in cls.lines(connection, order["id"]) if r["allocation"] == "RESERVED"]
        cls.inventory_locks(connection, lines)
        for line in lines:
            if line["item_type"] == "product":
                delta = line["quantity"] if consume else 0
                updated = connection.execute(
                    "UPDATE products SET stock=stock-%s,reserved=reserved-%s,version=version+1 WHERE id=%s AND reserved >= %s",
                    (delta, line["quantity"], line["item_id"], line["quantity"]),
                )
                if updated.rowcount != 1:
                    raise ApiException(
                        409, "INVENTORY_STATE_CONFLICT", "Reserved inventory cannot be reconciled"
                    )
            else:
                OrderData.update_pet_status(connection, line["item_id"], "sold" if consume else "available")
            connection.execute(
                "UPDATE order_lines SET allocation=%s WHERE order_id=%s AND position=%s AND allocation='RESERVED'",
                ("CONSUMED" if consume else "RELEASED", order["id"], line["position"]),
            )

    @classmethod
    def expire_locked(cls, connection: DbConnection, order: Row) -> bool:
        """Reconcile unpaid expiry while the caller holds the same payment/order lock."""
        if (
            order["status"] != "placed"
            or order["payment_status"] != "UNPAID"
            or order["payment_expires_at"] is None
            or order["payment_expires_at"] > datetime.now(UTC)
        ):
            return False
        cls.release(connection, order)
        connection.execute(
            "UPDATE store_orders SET status='expired',payment_status='EXPIRED',complete=TRUE,version=version+1 WHERE id=%s",
            (order["id"],),
        )
        order.update(status="expired", payment_status="EXPIRED", complete=True, version=order["version"] + 1)
        return True

    def expire(self) -> int:
        """Expire only unlocked mixed orders; SKIP LOCKED prevents parallel double release."""
        legacy = OrderData(self.database).expire_overdue_orders()
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM store_orders WHERE order_kind='MIXED' AND status='placed' AND payment_status='UNPAID'
                   AND payment_expires_at<=CURRENT_TIMESTAMP ORDER BY id FOR UPDATE SKIP LOCKED"""
            ).fetchall()
            return legacy + sum(self.expire_locked(connection, row) for row in rows)

    def transition(self, identifier: UUID, target: OrderStatus, actor: Row, version: int) -> Row:
        """Use the existing state matrix and refund successful payments atomically."""
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor, modifying=True)
            OrderData.expire_locked_order_if_needed(connection, order)
            CatalogData.version(order, version, "ORDER_VERSION_CONFLICT")
            if not OrderStatus(order["status"]).can_transition_to(target):
                raise ApiException(409, "INVALID_STATUS_TRANSITION", "This order transition is not allowed")
            if target == OrderStatus.APPROVED and order["payment_status"] != "PAID":
                raise ApiException(409, "ORDER_NOT_PAID", "Successful payment is required")
            payment_status = order["payment_status"]
            if target == OrderStatus.CANCELLED:
                if payment_status == "PAID":
                    refunded = connection.execute(
                        "UPDATE payments SET status='REFUNDED',updated_at=CURRENT_TIMESTAMP WHERE order_id=%s AND status='SUCCEEDED'",
                        (identifier,),
                    )
                    if refunded.rowcount != 1:
                        raise ApiException(
                            409, "PAYMENT_STATE_CONFLICT", "Successful payment cannot be refunded"
                        )
                    payment_status = "REFUNDED"
                self.release(connection, order)
            if target == OrderStatus.DELIVERED:
                self.release(connection, order, consume=True)
            row = connection.execute(
                "UPDATE store_orders SET status=%s::order_status,payment_status=%s::order_payment_status,complete=%s,ship_date=%s,version=version+1 WHERE id=%s RETURNING *",
                (
                    target.value,
                    payment_status,
                    target.is_complete,
                    datetime.now(UTC) if target == OrderStatus.SHIPPED else order["ship_date"],
                    identifier,
                ),
            ).fetchone()
            assert row is not None
            return self.public(connection, row)

    def delete(self, identifier: UUID, actor: Row) -> None:
        """Clean only an owned draft or ADMIN terminal order and its dependent records."""
        with self.database.connect() as connection:
            order = OrderData.lock_order(connection, identifier)
            OrderData.assert_access(order, actor, modifying=True)
            if order["status"] in {"placed", "approved", "shipped"}:
                raise ApiException(409, "ORDER_NOT_DELETABLE", "Active orders cannot be deleted")
            if order["status"] != "draft" and actor["role"] != "ADMIN":
                raise ApiException(403, "ORDER_ACCESS_DENIED", "Only ADMIN may delete terminal orders")
            connection.execute("DELETE FROM payments WHERE order_id=%s", (identifier,))
            connection.execute("DELETE FROM order_lines WHERE order_id=%s", (identifier,))
            connection.execute("DELETE FROM store_orders WHERE id=%s", (identifier,))
