"""Application-scoped controller composition and explicit router registration."""

from dataclasses import dataclass

from fastapi import FastAPI

from petstore.api import (
    administration,
    authentication,
    cart,
    catalog,
    checkout,
    health,
    media,
    orders,
    payments,
    pets,
    registration,
    telemetry,
    users,
)
from petstore.config import Settings
from petstore.controller.admin_user_controller import AdminUserController
from petstore.controller.authentication_controller import AuthenticationController
from petstore.controller.cart_controller import CartController
from petstore.controller.catalog_controller import CatalogController
from petstore.controller.commerce_order_controller import CommerceOrderController
from petstore.controller.health_controller import HealthController
from petstore.controller.media_controller import MediaController
from petstore.controller.order_controller import OrderController
from petstore.controller.payment_controller import PaymentController
from petstore.controller.pet_controller import PetController
from petstore.controller.registration_controller import RegistrationController
from petstore.controller.telemetry_controller import TelemetryController
from petstore.controller.user_controller import UserController
from petstore.data.database import Database


@dataclass(frozen=True)
class Controllers:
    """Typed dependency container: each controller owns one bounded HTTP responsibility."""

    health: HealthController
    registration: RegistrationController
    authentication: AuthenticationController
    pets: PetController
    orders: OrderController
    payments: PaymentController
    users: UserController
    administration: AdminUserController
    catalog: CatalogController
    media: MediaController
    cart: CartController
    checkout: CommerceOrderController
    telemetry: TelemetryController

    @classmethod
    def create(cls, database: Database, settings: Settings) -> "Controllers":
        """Compose dependencies once per application, never once per incoming request."""
        return cls(
            health=HealthController(database),
            registration=RegistrationController(),
            authentication=AuthenticationController(),
            pets=PetController(database),
            orders=OrderController(database),
            payments=PaymentController(database),
            users=UserController(),
            administration=AdminUserController(),
            catalog=CatalogController(database),
            media=MediaController(database, settings),
            cart=CartController(database),
            checkout=CommerceOrderController(database),
            telemetry=TelemetryController(settings=settings),
        )


def include_routers(app: FastAPI) -> None:
    """Register concrete native routers, independent of the OpenAPI YAML's contents."""
    app.include_router(health.router)
    app.include_router(registration.router)
    app.include_router(authentication.router)
    app.include_router(pets.router)
    app.include_router(orders.router)
    app.include_router(payments.router)
    app.include_router(users.router)
    app.include_router(administration.router)
    app.include_router(catalog.router)
    app.include_router(media.router)
    app.include_router(cart.router)
    app.include_router(checkout.router)
    app.include_router(telemetry.router)
