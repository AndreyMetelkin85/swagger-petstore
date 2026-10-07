from uuid import uuid4

import pytest
from psycopg import sql

from petstore.service.commerce_order_service import CommerceOrderService

pytestmark = pytest.mark.integration


def test_v12_preserves_paid_order_and_migrates_debit_once(integration_database):
    settings, database = integration_database
    database.start()
    schema = "upgrade_" + uuid4().hex
    try:
        with database.connect() as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        migrations = settings.resources / "db/migration"
        for number in range(1, 12):
            migration = next(migrations.glob(f"V{number}__*.sql"))
            with database.connect() as connection:
                connection.execute(
                    sql.SQL("SET LOCAL search_path TO {},public").format(sql.Identifier(schema))
                )
                connection.execute(migration.read_text(encoding="utf-8"))
        product_id, order_id = uuid4(), uuid4()
        with database.connect() as connection:
            connection.execute(sql.SQL("SET LOCAL search_path TO {},public").format(sql.Identifier(schema)))
            owner = connection.execute("SELECT id FROM users WHERE username='user1'").fetchone()["id"]
            connection.execute(
                "INSERT INTO products (id,sku,name,product_type,price,publication_status,stock,reserved) VALUES (%s,'MIGRATE','Preserved','OTHER',10,'PUBLISHED',5,2)",
                (product_id,),
            )
            connection.execute(
                "INSERT INTO store_orders (id,owner_user_id,pet_id,quantity,status,order_kind,payment_status,total_amount) VALUES (%s,%s,NULL,1,'placed','MIXED','PAID',20)",
                (order_id, owner),
            )
            connection.execute(
                "INSERT INTO order_lines (order_id,position,item_type,item_id,quantity,name,unit_price,snapshot,allocation) VALUES (%s,0,'product',%s,2,'Preserved',10,'{}','RESERVED')",
                (order_id, product_id),
            )
        with database.connect() as connection:
            connection.execute(sql.SQL("SET LOCAL search_path TO {},public").format(sql.Identifier(schema)))
            connection.execute(next(migrations.glob("V12__*.sql")).read_text(encoding="utf-8"))
            product = connection.execute(
                "SELECT stock,reserved FROM products WHERE id=%s", (product_id,)
            ).fetchone()
            assert product == {"stock": 3, "reserved": 0}
            order = connection.execute(
                "SELECT * FROM store_orders WHERE id=%s FOR UPDATE", (order_id,)
            ).fetchone()
            assert order["payment_status"] == "PAID" and order["total_amount"] == 20
            assert (
                connection.execute(
                    "SELECT allocation FROM order_lines WHERE order_id=%s", (order_id,)
                ).fetchone()["allocation"]
                == "CONSUMED"
            )
            CommerceOrderService.release(connection, order)
            CommerceOrderService.release(connection, order)
            assert connection.execute(
                "SELECT stock,reserved FROM products WHERE id=%s", (product_id,)
            ).fetchone() == {"stock": 5, "reserved": 0}
    finally:
        with database.connect() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        database.close()
