from decimal import Decimal
from uuid import uuid4

import pytest

from petstore.model.requests import (
    Address,
    AdminUserUpdateRequest,
    LoginRequest,
    OrderCreateRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    PaymentRequest,
    PetCreateRequest,
    PetUpdateRequest,
    RegisterRequest,
    UserUpdateRequest,
)
from petstore.service.validation_service import ValidationService as V


@pytest.mark.parametrize(
    "changes,field,message",
    [
        ({"username": None}, "username", "Username is required"),
        ({"username": " "}, "username", "Username is required"),
        (
            {"username": "ab"},
            "username",
            "Username must be 3-30 characters and contain only letters, digits, dot, underscore or hyphen",
        ),
        ({"password": "123"}, "password", "Password must be between 6 and 100 characters"),
        ({"password": "я" * 37}, "password", "Password must not exceed 72 UTF-8 bytes"),
        ({"password": ""}, "password", "Password is required"),
        ({"email": "wrong"}, "email", "Email must be a valid email address"),
        ({"email": " "}, "email", "Email is required"),
        ({"firstName": " "}, "firstName", "firstName must not be blank"),
        ({"lastName": "x" * 51}, "lastName", "lastName must not exceed 50 characters"),
        ({"phone": "abc"}, "phone", "Phone must contain 7-30 digits and phone punctuation"),
    ],
)
def test_registration_validation_messages(changes, field, message):
    request = RegisterRequest.model_validate(
        {"username": "valid-name", "password": "ValidPass123", "email": "valid@example.com"} | changes
    )
    assert V.registration(request) == [{"field": field, "message": message}]


def test_valid_registration_with_unicode_profile():
    request = RegisterRequest(
        username="valid-name",
        password="ValidPass123",
        email="valid@example.com",
        firstName="Иван",
        lastName="Иванов",
        phone="+7 (999) 123-45-67",
        address=Address(city="Москва", street="Тестовая", house="1", postalCode="123456"),
    )
    assert V.registration(request) == []


@pytest.mark.parametrize(
    "data,fields",
    [
        ({}, ["address.city", "address.street", "address.house", "address.postalCode"]),
        (
            {"city": "Москва", "street": "Улица", "house": "1", "postalCode": "abc", "country": "RU"},
            ["address.postalCode", "address.country"],
        ),
        ({"city": "x" * 101, "street": "Улица", "house": "1", "postalCode": "123456"}, ["address.city"]),
    ],
)
def test_address_validation(data, fields):
    errors = []
    V.address(Address.model_validate(data), errors)
    assert [error["field"] for error in errors] == fields


def test_optional_fields_and_explicit_null_address():
    assert V.user_update(UserUpdateRequest(address=None)) == []
    assert V.user_update(UserUpdateRequest()) == [
        {"field": "body", "message": "At least one profile field is required"}
    ]
    assert V.user_update(UserUpdateRequest(role="ADMIN"))[0]["field"] == "role"


def test_admin_update_requires_email_username_role_and_address_presence():
    assert [error["field"] for error in V.admin_update(AdminUserUpdateRequest())] == [
        "username",
        "email",
        "address",
        "role",
    ]
    assert (
        V.admin_update(
            AdminUserUpdateRequest(
                username="valid-name", email="valid@example.com", role="USER", address=None
            )
        )
        == []
    )


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"name": None}, "name"),
        ({"name": "x" * 101}, "name"),
        ({"price": None}, "price"),
        ({"price": "0"}, "price"),
        ({"price": "1.001"}, "price"),
        ({"price": "10000000000"}, "price"),
        ({"status": "reserved"}, "status"),
        ({"status": "wrong"}, "status"),
        ({"category": {}}, "category.name"),
        ({"tags": [None]}, "tags[0].name"),
        ({"tags": [{"name": "wrong tag"}]}, "tags[0].name"),
        ({"photoUrls": ["relative"]}, "photoUrls[0]"),
        ({"photoUrls": ["https://example.com/with space"]}, "photoUrls[0]"),
        ({"id": str(uuid4())}, "id"),
    ],
)
def test_pet_validation(changes, field):
    request = PetCreateRequest.model_validate({"name": "Test pet", "price": "10.00"} | changes)
    assert V.pet(request)[0]["field"] == field


def test_pet_update_requires_version_and_accepts_exact_decimal():
    assert V.pet(PetUpdateRequest(name="pet", price=Decimal("10.00")))[0]["field"] == "version"
    assert V.pet(PetUpdateRequest(name="pet", price=Decimal("10.00"), version=-1))[0]["field"] == "version"
    assert V.pet(PetUpdateRequest(name="pet", price=Decimal("10.00"), version=0)) == []


@pytest.mark.parametrize("quantity", [None, 0, 2, -1])
def test_individual_pet_order_quantity(quantity):
    errors = V.order(OrderCreateRequest(petId=uuid4(), quantity=quantity))
    assert errors == [{"field": "quantity", "message": "Quantity must be 1 for an individual pet"}]


def test_order_missing_pet_and_server_managed_fields():
    assert [error["field"] for error in V.order(OrderCreateRequest(quantity=1, status="placed"))] == [
        "petId",
        "status",
    ]
    assert V.order(OrderCreateRequest(petId=uuid4(), quantity=1)) == []


def test_missing_profile_reports_every_required_checkout_field():
    assert [error["field"] for error in V.missing_order_profile_fields({})] == [
        "firstName",
        "lastName",
        "phone",
        "address.city",
        "address.street",
        "address.house",
        "address.postalCode",
    ]
    assert V.missing_order_profile_fields(None)[0]["field"] == "user"


@pytest.mark.parametrize("card", list(V.TEST_CARDS))
def test_documented_test_cards_are_valid(card):
    request = PaymentRequest(
        cardNumber=card, expiryMonth=12, expiryYear=2099, cvv="123", cardholderName="Test User"
    )
    assert V.payment(request) == []


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"cardNumber": "wrong"}, "cardNumber"),
        ({"cardNumber": "4111111111111111"}, "cardNumber"),
        ({"expiryMonth": 13}, "expiryMonth"),
        ({"expiryYear": None}, "expiryYear"),
        ({"expiryYear": 2000}, "expiryYear"),
        ({"cvv": "12"}, "cvv"),
        ({"cardholderName": " "}, "cardholderName"),
        ({"cardholderName": "x" * 101}, "cardholderName"),
        ({"amount": 1}, "amount"),
    ],
)
def test_payment_validation(changes, field):
    request = PaymentRequest.model_validate(
        {
            "cardNumber": "4242424242424242",
            "expiryMonth": 12,
            "expiryYear": 2099,
            "cvv": "123",
            "cardholderName": "Test User",
        }
        | changes
    )
    assert V.payment(request)[0]["field"] == field


def test_empty_recovery_login_and_reset_validation():
    assert [error["field"] for error in V.login(LoginRequest())] == ["email", "password"]
    assert V.forgot(PasswordForgotRequest())[0]["field"] == "email"
    assert V.reset(PasswordResetRequest())[0]["field"] == "newPassword"
