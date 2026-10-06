from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


def code_from(url):
    return parse_qs(urlsplit(url).query)["code"][0]


def test_registration_confirmation_login_profile_and_cleanup(scenario):
    request, registration, headers = scenario.user()
    user_id = registration["user"]["id"]
    response = scenario.client.get("/user/me", headers=headers)
    assert response.json()["userStatus"] == "ACTIVE"
    assert "password" not in response.text
    assert scenario.client.get(f"/users/{user_id}", headers=headers).status_code == 403
    assert (
        scenario.client.get(f"/users/{user_id}", headers=scenario.admin).json()["email"] == request["email"]
    )
    assert scenario.client.get("/users", headers=scenario.admin).status_code == 200
    response = scenario.client.put("/user/me", headers=headers, json={"firstName": "Новое", "address": None})
    assert response.status_code == 200
    assert response.json()["address"] is None
    assert response.json()["firstName"] == "Новое"
    assert scenario.client.delete(f"/users/{user_id}", headers=scenario.admin).status_code == 204
    assert scenario.client.get("/user/me", headers=headers).status_code == 401


def test_resend_old_link_invalid_new_link_active(scenario):
    request, registration, _ = scenario.user(active=False)
    resend = scenario.client.post(
        "/auth/confirmation/resend", json={"email": request["email"], "password": request["password"]}
    )
    assert resend.status_code == 200
    path = f"/auth/confirm/{registration['user']['id']}"
    old = scenario.client.get(path, params={"code": code_from(registration["confirmationUrl"])})
    assert old.status_code == 400
    assert old.json()["error"] == "INVALID_CONFIRMATION_LINK"
    new = scenario.client.get(path, params={"code": code_from(resend.json()["confirmationUrl"])})
    assert new.status_code == 200
    assert new.json()["userStatus"] == "ACTIVE"
    assert (
        scenario.client.get(path, params={"code": code_from(resend.json()["confirmationUrl"])}).status_code
        == 409
    )
    assert (
        scenario.client.post(
            "/auth/confirmation/resend", json={"email": request["email"], "password": request["password"]}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("kind", ["confirmation", "reset"])
def test_expired_one_time_links_are_410(scenario, kind):
    request, registration, _ = scenario.user(active=kind == "reset")
    user_id = registration["user"]["id"]
    if kind == "confirmation":
        with scenario.database.connect() as connection:
            connection.execute(
                "UPDATE users SET confirmation_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute' WHERE id = %s",
                (user_id,),
            )
        response = scenario.client.get(
            f"/auth/confirm/{user_id}", params={"code": code_from(registration["confirmationUrl"])}
        )
    else:
        forgot = scenario.client.post("/auth/password/forgot", json={"email": request["email"]}).json()
        with scenario.database.connect() as connection:
            connection.execute(
                "UPDATE users SET reset_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute' WHERE id = %s",
                (user_id,),
            )
        response = scenario.client.post(
            "/auth/password/reset",
            params={"code": code_from(forgot["resetUrl"])},
            json={"newPassword": "NewValidPass123"},
        )
    assert response.status_code == 410


def test_password_reset_replay_and_token_revocation(scenario):
    request, _, headers = scenario.user()
    forgot = scenario.client.post("/auth/password/forgot", json={"email": request["email"]})
    assert forgot.status_code == 200
    code = code_from(forgot.json()["resetUrl"])
    assert (
        scenario.client.post(
            "/auth/password/reset", params={"code": code}, json={"newPassword": "NewValidPass123"}
        ).status_code
        == 204
    )
    assert scenario.client.get("/user/me", headers=headers).status_code == 401
    assert (
        scenario.client.post(
            "/auth/password/reset", params={"code": code}, json={"newPassword": "AnotherPass123"}
        ).status_code
        == 409
    )
    assert (
        scenario.client.post(
            "/auth/login", json={"email": request["email"], "password": "NewValidPass123"}
        ).status_code
        == 200
    )


def test_pending_blocking_unblocking_preserves_confirmation(scenario):
    request, registration, _ = scenario.user(active=False)
    user_id = registration["user"]["id"]
    assert (
        scenario.client.post(
            "/auth/login", json={"email": request["email"], "password": request["password"]}
        ).status_code
        == 403
    )
    assert scenario.client.post(f"/admin/users/{user_id}/block", headers=scenario.admin).status_code == 200
    assert (
        scenario.client.get(
            f"/auth/confirm/{user_id}", params={"code": code_from(registration["confirmationUrl"])}
        ).json()["userStatus"]
        == "BLOCKED"
    )
    assert (
        scenario.client.post(f"/admin/users/{user_id}/unblock", headers=scenario.admin).json()["userStatus"]
        == "ACTIVE"
    )
    assert scenario.client.post(f"/admin/users/{user_id}/unblock", headers=scenario.admin).status_code == 409


def test_draft_has_no_reservation_or_checkout_data_and_can_be_replaced(scenario):
    _, _, headers = scenario.user(profile=False)
    pet = scenario.pet()
    other_pet = scenario.pet()
    draft = scenario.draft(pet, headers)
    assert draft["status"] == "draft"
    assert draft["paymentStatus"] == "NOT_STARTED"
    assert all(
        draft[field] is None
        for field in ("unitPrice", "totalAmount", "deliveryDetails", "paymentExpiresAt", "shipDate")
    )
    assert scenario.client.get(f"/pet/{pet['id']}").json()["status"] == "available"
    updated = scenario.client.put(
        f"/store/order/{draft['id']}", headers=headers, json={"petId": other_pet["id"], "quantity": 1}
    )
    assert updated.json()["petId"] == other_pet["id"]
    assert (
        scenario.client.post(f"/store/order/{draft['id']}/place", headers=headers).json()["error"]
        == "PROFILE_INCOMPLETE"
    )
    assert scenario.client.delete(f"/store/order/{draft['id']}", headers=headers).status_code == 204


def test_paid_lifecycle_and_terminal_order_payment_cleanup(scenario):
    _, _, headers = scenario.user()
    pet = scenario.pet()
    order = scenario.place(scenario.draft(pet, headers), headers)
    path = f"/store/order/{order['id']}"
    assert scenario.client.delete(path, headers=scenario.admin).json()["error"] == "ORDER_NOT_DELETABLE"
    assert scenario.client.post(path + "/approve", headers=scenario.admin).json()["error"] == "ORDER_NOT_PAID"
    paid = scenario.pay(order, headers)
    assert paid.status_code == 201
    for action in ("approve", "ship", "deliver"):
        assert scenario.client.post(path + "/" + action, headers=headers).status_code == 403
        assert scenario.client.post(path + "/" + action, headers=scenario.admin).status_code == 200
    assert scenario.client.get(f"/pet/{pet['id']}").json()["status"] == "sold"
    assert scenario.client.post(path + "/cancel", headers=headers).status_code == 409
    assert scenario.client.delete(path, headers=headers).status_code == 403
    assert scenario.client.delete(path, headers=scenario.admin).status_code == 204
    with scenario.database.connect() as connection:
        assert (
            connection.execute("SELECT id FROM payments WHERE order_id = %s", (order["id"],)).fetchone()
            is None
        )


def test_cancellation_refunds_once_and_releases_pet(scenario):
    _, _, headers = scenario.user()
    pet = scenario.pet()
    order = scenario.place(scenario.draft(pet, headers), headers)
    assert scenario.pay(order, headers).status_code == 201
    response = scenario.client.post(f"/store/order/{order['id']}/cancel", headers=headers)
    assert response.json()["paymentStatus"] == "REFUNDED"
    assert scenario.client.get(f"/pet/{pet['id']}").json()["status"] == "available"
    assert (
        scenario.client.get(f"/store/order/{order['id']}/payments", headers=headers).json()[0]["status"]
        == "REFUNDED"
    )
    assert scenario.client.post(f"/store/order/{order['id']}/cancel", headers=headers).status_code == 409


@pytest.mark.parametrize(
    "card,expected_status,code",
    [
        ("4242424242424242", 201, None),
        ("4000000000000002", 402, "PAYMENT_DECLINED"),
        ("4000000000009995", 402, "INSUFFICIENT_FUNDS"),
    ],
)
def test_payment_saved_results_idempotency_and_deletion(scenario, card, expected_status, code):
    _, _, headers = scenario.user()
    order = scenario.place(scenario.draft(scenario.pet(), headers), headers)
    key = uuid4()
    first = scenario.pay(order, headers, card=card, key=key)
    assert first.status_code == expected_status
    replay = scenario.pay(order, headers, card=card, key=key)
    assert replay.status_code == (200 if expected_status == 201 else 402)
    attempts = scenario.client.get(f"/store/order/{order['id']}/payments", headers=headers).json()
    assert len(attempts) == 1
    payment_path = f"/store/order/{order['id']}/payments/{attempts[0]['id']}"
    assert scenario.client.get(payment_path, headers=headers).json()["cardLast4"] == card[-4:]
    assert scenario.client.delete(payment_path, headers=headers).status_code == 403
    assert scenario.client.delete(payment_path, headers=scenario.admin).status_code == (
        409 if expected_status == 201 else 204
    )
    if code:
        assert first.json()["error"] == code


def test_expiry_during_payment_is_committed_and_releases_reservation(scenario):
    _, _, headers = scenario.user()
    pet = scenario.pet()
    order = scenario.place(scenario.draft(pet, headers), headers)
    with scenario.database.connect() as connection:
        connection.execute(
            "UPDATE store_orders SET payment_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute' WHERE id = %s",
            (order["id"],),
        )
    response = scenario.pay(order, headers)
    assert response.status_code == 410
    assert scenario.client.get(f"/store/order/{order['id']}", headers=headers).json()["status"] == "expired"
    assert scenario.client.get(f"/pet/{pet['id']}").json()["status"] == "available"


@pytest.mark.parametrize(
    "race", ["place_delete", "payment_delete", "cancel_payment", "payment_payment", "place_place"]
)
def test_parallel_order_operations_preserve_atomic_invariants(scenario, race):
    _, _, headers = scenario.user()
    pet = scenario.pet()
    order = scenario.draft(pet, headers)
    path = f"/store/order/{order['id']}"
    if race not in {"place_delete", "place_place"}:
        scenario.place(order, headers)
    if race == "place_delete":
        operations = [
            lambda: scenario.client.post(path + "/place", headers=headers),
            lambda: scenario.client.delete(path, headers=headers),
        ]
    elif race == "payment_delete":
        operations = [
            lambda: scenario.pay(order, headers),
            lambda: scenario.client.delete(path, headers=scenario.admin),
        ]
    elif race == "cancel_payment":
        operations = [
            lambda: scenario.pay(order, headers),
            lambda: scenario.client.post(path + "/cancel", headers=headers),
        ]
    elif race == "payment_payment":
        key = uuid4()
        operations = [
            lambda: scenario.pay(order, headers, key=key),
            lambda: scenario.pay(order, headers, key=key),
        ]
    else:
        other = scenario.draft(pet, headers)
        operations = [
            lambda: scenario.client.post(path + "/place", headers=headers),
            lambda: scenario.client.post(f"/store/order/{other['id']}/place", headers=headers),
        ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda operation: operation(), operations))
    assert all(response.status_code < 500 for response in responses)
    with scenario.database.connect() as connection:
        payments = connection.execute("SELECT * FROM payments WHERE order_id = %s", (order["id"],)).fetchall()
        active = connection.execute(
            "SELECT id FROM store_orders WHERE pet_id = %s AND status IN ('placed', 'approved', 'shipped')",
            (pet["id"],),
        ).fetchall()
        assert len(active) <= 1
        assert len(payments) <= 1
        if race == "payment_payment":
            assert sorted(response.status_code for response in responses) == [200, 201]
        if race == "cancel_payment":
            persisted = connection.execute(
                "SELECT * FROM store_orders WHERE id = %s", (order["id"],)
            ).fetchone()
            assert persisted["status"] == "cancelled"
            assert not payments or payments[0]["status"] == "REFUNDED"


def test_other_owner_cannot_read_modify_pay_or_delete(scenario):
    _, _, owner = scenario.user()
    _, _, stranger = scenario.user()
    order = scenario.place(scenario.draft(scenario.pet(), owner), owner)
    path = f"/store/order/{order['id']}"
    assert scenario.client.get(path, headers=stranger).status_code == 403
    assert scenario.client.post(path + "/cancel", headers=stranger).status_code == 403
    assert scenario.pay(order, stranger).status_code == 403
    assert scenario.client.get(path + "/payments", headers=stranger).status_code == 403
    assert scenario.client.delete(path, headers=stranger).status_code == 403


def test_profile_price_snapshots_do_not_change_after_checkout(scenario):
    _, _, headers = scenario.user()
    pet = scenario.pet(price="10.25")
    order = scenario.place(scenario.draft(pet, headers), headers)
    scenario.client.put("/user/me", headers=headers, json={"firstName": "Changed", "address": None})
    latest = scenario.client.get(f"/pet/{pet['id']}").json()
    assert (
        scenario.client.put(
            f"/pet/{pet['id']}",
            headers=scenario.admin,
            json={"name": "Changed", "price": "100.99", "version": latest["version"]},
        ).status_code
        == 200
    )
    stored = scenario.client.get(f"/store/order/{order['id']}", headers=headers).json()
    assert stored["unitPrice"] == 10.25
    assert stored["deliveryDetails"] == order["deliveryDetails"]


def test_admin_demo_and_users_with_orders_are_protected(scenario):
    all_users = scenario.client.get("/users", headers=scenario.admin).json()
    for username, code in (("admin", "ADMIN_ACCOUNT_PROTECTED"), ("user1", "DEMO_ACCOUNT_PROTECTED")):
        user = next(user for user in all_users if user["username"] == username)
        response = scenario.client.delete(f"/users/{user['id']}", headers=scenario.admin)
        assert response.status_code == 403
        assert response.json()["error"] == code
    _, registration, headers = scenario.user()
    scenario.draft(scenario.pet(), headers)
    response = scenario.client.delete(f"/users/{registration['user']['id']}", headers=scenario.admin)
    assert response.status_code == 409
    assert response.json()["error"] == "USER_HAS_ORDERS"


def test_pet_version_searches_and_history_protection(scenario):
    _, _, headers = scenario.user()
    pet = scenario.pet()
    update = {"name": "Edited", "price": "12.99", "version": pet["version"], "tags": [{"name": "python"}]}
    assert scenario.client.put(f"/pet/{pet['id']}", headers=scenario.admin, json=update).status_code == 200
    assert (
        scenario.client.put(f"/pet/{pet['id']}", headers=scenario.admin, json=update).json()["error"]
        == "PET_VERSION_CONFLICT"
    )
    assert scenario.client.get("/pet/findByTags", params={"tags": "python"}).status_code == 200
    assert scenario.client.get("/pet/findByStatus", params={"status": "available,pending"}).status_code == 200
    scenario.draft(pet, headers)
    assert (
        scenario.client.delete(f"/pet/{pet['id']}", headers=scenario.admin).json()["error"]
        == "PET_HAS_ORDERS"
    )


def test_cleanup_runs_after_an_original_test_failure(scenario):
    _, registration, _ = scenario.user()
    user_id = registration["user"]["id"]
    with pytest.raises(RuntimeError, match="original failure"):
        try:
            raise RuntimeError("original failure")
        finally:
            assert scenario.client.delete(f"/users/{user_id}", headers=scenario.admin).status_code == 204
    with scenario.database.connect() as connection:
        assert connection.execute("SELECT id FROM users WHERE id = %s", (user_id,)).fetchone() is None


def test_admin_full_update_invalidates_tokens_and_pending_promotion_is_denied(scenario):
    request, registration, headers = scenario.user()
    user = registration["user"]
    payload = {"username": user["username"], "email": request["email"], "role": "ADMIN", "address": None}
    updated = scenario.client.put(f"/users/{user['id']}", headers=scenario.admin, json=payload)
    assert updated.status_code == 200
    assert updated.json()["role"] == "ADMIN"
    assert scenario.client.get("/user/me", headers=headers).status_code == 401
    payload["role"] = "USER"
    assert (
        scenario.client.put(f"/users/{user['id']}", headers=scenario.admin, json=payload).status_code == 200
    )
    pending_request, pending, _ = scenario.user(active=False)
    payload = {
        "username": pending["user"]["username"],
        "email": pending_request["email"],
        "role": "ADMIN",
        "address": None,
    }
    assert (
        scenario.client.put(f"/users/{pending['user']['id']}", headers=scenario.admin, json=payload).json()[
            "error"
        ]
        == "INVALID_ROLE_TRANSITION"
    )


@pytest.mark.parametrize(
    "field,error", [("username", "USERNAME_ALREADY_EXISTS"), ("email", "EMAIL_ALREADY_EXISTS")]
)
def test_admin_update_unique_conflicts(scenario, field, error):
    request, registration, _ = scenario.user()
    other_request, other, _ = scenario.user()
    payload = {
        "username": registration["user"]["username"],
        "email": request["email"],
        "role": "USER",
        "address": None,
    }
    payload[field] = other_request[field]
    response = scenario.client.put(
        f"/users/{registration['user']['id']}", headers=scenario.admin, json=payload
    )
    assert response.status_code == 409
    assert response.json()["error"] == error


@pytest.mark.parametrize("field", ["username", "email"])
def test_registration_duplicates_preserve_master_field_details(scenario, field):
    request, _, _ = scenario.user()
    duplicate = {
        "username": "py-" + uuid4().hex[:20],
        "email": uuid4().hex + "@example.com",
        "password": "ValidPass123",
    }
    duplicate[field] = request[field]
    response = scenario.client.post("/auth/register", json=duplicate)
    assert response.status_code == 409
    assert response.json()["error"] == "USER_ALREADY_EXISTS"
    assert response.json()["details"] == [
        {"field": field, "message": f"A user with this {field} already exists"}
    ]


def test_registration_both_conflicts_are_reported_without_values(scenario):
    request, _, _ = scenario.user()
    response = scenario.client.post("/auth/register", json=request)
    assert response.status_code == 409
    assert response.json()["details"] == [
        {"field": "username", "message": "A user with this username already exists"},
        {"field": "email", "message": "A user with this email already exists"},
    ]
    assert request["email"] not in response.text
    assert request["username"] not in response.text


@pytest.mark.parametrize("race", ["confirm_resend", "resend_resend", "confirm_confirm"])
def test_master_confirmation_races_never_return_removed_state_changed(scenario, race):
    request, registration, _ = scenario.user(active=False)
    path = f"/auth/confirm/{registration['user']['id']}"
    code = code_from(registration["confirmationUrl"])
    credentials = {"email": request["email"], "password": request["password"]}

    def confirm():
        return scenario.client.get(path, params={"code": code})

    def resend():
        return scenario.client.post("/auth/confirmation/resend", json=credentials)

    operations = (
        [confirm, resend]
        if race == "confirm_resend"
        else [resend, resend]
        if race == "resend_resend"
        else [confirm, confirm]
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda operation: operation(), operations))
    assert all(response.status_code < 500 for response in responses)
    assert all(response.json().get("error") != "CONFIRMATION_STATE_CHANGED" for response in responses)
    if race == "confirm_confirm":
        assert sorted(response.status_code for response in responses) == [200, 409]
    elif race == "confirm_resend":
        assert [response.status_code for response in responses] in ([200, 409], [400, 200])
    else:
        assert [response.status_code for response in responses] == [200, 200]
        valid_codes = 0
        for response in responses:
            result = scenario.client.get(path, params={"code": code_from(response.json()["confirmationUrl"])})
            if result.status_code == 200:
                valid_codes += 1
            else:
                assert result.status_code in {400, 409}
        assert valid_codes == 1


def test_missing_resources_and_nonpayable_draft(scenario):
    _, _, headers = scenario.user()
    assert scenario.client.get(f"/pet/{uuid4()}").status_code == 404
    assert scenario.client.get(f"/users/{uuid4()}", headers=scenario.admin).status_code == 404
    assert scenario.client.get(f"/store/order/{uuid4()}", headers=headers).status_code == 404
    assert scenario.client.delete(f"/store/order/{uuid4()}", headers=scenario.admin).status_code == 404
    assert (
        scenario.client.post(
            "/store/order", headers=headers, json={"petId": str(uuid4()), "quantity": 1}
        ).json()["error"]
        == "PET_NOT_FOUND"
    )
    draft = scenario.draft(scenario.pet(), headers)
    assert scenario.pay(draft, headers).json()["error"] == "ORDER_NOT_PAYABLE"
    assert (
        scenario.client.get(f"/store/order/{draft['id']}/payments/{uuid4()}", headers=headers).json()["error"]
        == "PAYMENT_NOT_FOUND"
    )
    assert (
        scenario.client.delete(
            f"/store/order/{draft['id']}/payments/{uuid4()}", headers=scenario.admin
        ).json()["error"]
        == "PAYMENT_NOT_FOUND"
    )


def test_idempotency_reuse_and_already_paid_are_distinct(scenario):
    _, _, headers = scenario.user()
    order = scenario.place(scenario.draft(scenario.pet(), headers), headers)
    key = uuid4()
    assert scenario.pay(order, headers, key=key).status_code == 201
    assert (
        scenario.pay(order, headers, key=key, card="4000000000000002").json()["error"]
        == "IDEMPOTENCY_KEY_REUSED"
    )
    assert scenario.pay(order, headers).json()["error"] == "ORDER_ALREADY_PAID"


def test_parallel_expiry_and_payment_keeps_one_consistent_result(scenario):
    _, _, headers = scenario.user()
    pet = scenario.pet()
    order = scenario.place(scenario.draft(pet, headers), headers)
    with scenario.database.connect() as connection:
        connection.execute(
            "UPDATE store_orders SET payment_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute' WHERE id = %s",
            (order["id"],),
        )
    from petstore.data.order_data import OrderData

    with ThreadPoolExecutor(max_workers=2) as executor:
        payment_future = executor.submit(scenario.pay, order, headers)
        expiry_future = executor.submit(OrderData(scenario.database).expire_overdue_orders)
        assert payment_future.result().status_code == 410
        expiry_future.result()
    with scenario.database.connect() as connection:
        assert (
            connection.execute("SELECT * FROM payments WHERE order_id = %s", (order["id"],)).fetchone()
            is None
        )
    assert scenario.client.get(f"/pet/{pet['id']}").json()["status"] == "available"


def test_inventory_permissions_and_pet_status_filter_validation(scenario):
    assert scenario.client.get("/health").status_code == 200
    _, _, headers = scenario.user()
    assert scenario.client.get("/store/inventory", headers=headers).status_code == 403
    assert scenario.client.get("/store/inventory", headers=scenario.admin).status_code == 200
    assert scenario.client.get("/store/order", headers=headers).status_code == 200
    assert scenario.client.get("/pet/findByStatus", params={"status": "invalid"}).status_code == 422


def test_last_administrator_demotion_is_rejected_without_changing_seed(scenario):
    admin = scenario.client.get("/user/me", headers=scenario.admin).json()
    payload = {
        "username": admin["username"],
        "email": admin["email"],
        "role": "USER",
        "address": admin["address"],
    }
    response = scenario.client.put(f"/users/{admin['id']}", headers=scenario.admin, json=payload)
    assert response.status_code == 409
    assert response.json()["error"] == "LAST_ADMIN_PROTECTED"
    assert scenario.client.get("/user/me", headers=scenario.admin).json()["role"] == "ADMIN"
