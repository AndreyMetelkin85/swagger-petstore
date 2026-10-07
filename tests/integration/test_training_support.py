from dataclasses import replace
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from petstore.app import create_app
from petstore.data.database import Database
from petstore.testing import expire_order, reset_lab

pytestmark = pytest.mark.integration


def test_reset_expiry_and_repeated_seed_are_restricted_to_the_owned_lab(integration_database, tmp_path):
    settings, _ = integration_database
    name = "petstore_training_" + uuid4().hex[:12]
    lab_settings = replace(
        settings,
        db_url=settings.db_url.rsplit("/", 1)[0] + "/" + name,
        test_support=True,
        media_root=tmp_path,
        expire_interval=0,
    )
    with psycopg.connect(
        settings.db_url, user=settings.db_user, password=settings.db_password, autocommit=True
    ) as owner:
        owner.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        database = Database(lab_settings)
        database.start()
        try:
            for number in range(1, 13):
                with database.connect() as connection:
                    connection.execute(
                        next(settings.resources.glob(f"db/migration/V{number}__*.sql")).read_text(
                            encoding="utf-8"
                        )
                    )
            first = reset_lab(database, lab_settings, confirmed=True)
            assert len(list(tmp_path.iterdir())) == 2
            with TestClient(create_app(lab_settings, database=database, start_database=False)) as client:
                buyer = client.post(
                    "/api/v3/auth/login", json={"email": "test@example.com", "password": "password123"}
                )
                assert buyer.status_code == 200
                headers = {"Authorization": "Bearer " + buyer.json()["access_token"]}
                cart = client.get("/api/v3/store/cart", headers=headers).json()
                cart = client.put(
                    "/api/v3/store/cart",
                    headers=headers,
                    json={
                        "version": cart["version"],
                        "lines": [{"kind": "product", "id": first["productId"], "quantity": 2}],
                    },
                ).json()
                draft = client.post(
                    "/api/v3/store/orders",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={"cartVersion": cart["version"]},
                ).json()
                placed = client.post(
                    "/api/v3/store/orders/" + draft["id"] + "/place",
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                    json={"version": draft["version"]},
                )
                assert placed.status_code == 200
                expire_order(database, lab_settings, UUID(draft["id"]))
                assert (
                    client.get("/api/v3/store/orders/" + draft["id"], headers=headers).json()["status"]
                    == "expired"
                )
                assert client.get("/api/v3/products/" + first["productId"]).json()["reserved"] == 0
                with pytest.raises(ValueError):
                    expire_order(database, lab_settings, UUID(draft["id"]))
                reset_lab(database, lab_settings, confirmed=True)
                assert client.get("/api/v3/user/me", headers=headers).status_code == 401
                assert client.get("/api/v3/products/" + first["productId"]).json()["stock"] == 5
                assert len(list(tmp_path.iterdir())) == 2
                with database.connect() as connection:
                    assert connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"] == 2
        finally:
            database.close()
            owner.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
