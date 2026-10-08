"""Авторизация и передача HTTP-команд сервисам приложения."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.payment_data import PaymentData
from petstore.model.commerce import CheckoutCommand, VersionCommand
from petstore.model.enums import OrderStatus
from petstore.model.requests import PaymentRequest
from petstore.service.commerce_order_service import CommerceOrderService
from petstore.service.validation_service import ValidationService
from petstore.utils.responses import Responses, public_payment


class CommerceOrderController:
    """Адаптация авторизованных команд смешанного заказа к транзакционному сервису."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.orders = CommerceOrderService(database)
        self.payments = PaymentData(database)

    def list_orders(self, context: RequestContext) -> Response:
        """Возвращает собственные заказы пользователя или всю историю для ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(self.orders.find_all(context.authorize("USER", "ADMIN")))

    def create(self, context: RequestContext) -> Response:
        """Создаёт снимок корзины; безопасный повтор возвращает прежний результат со статусом 200.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        assert isinstance(context.body, CheckoutCommand)
        result, replayed = self.orders.create(
            context.body, context.authorize("USER", "ADMIN"), context.identifier("Idempotency-Key")
        )
        return Responses(result, status_code=200 if replayed else 201)

    def get(self, context: RequestContext) -> Response:
        """Возвращает доступный заказ после проверки владельца и срока резерва.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(self.orders.get(context.identifier("id"), context.authorize("USER", "ADMIN")))

    def delete(self, context: RequestContext) -> Response:
        """Атомарно удаляет разрешённый заказ и связанные платежи.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        self.orders.delete(context.identifier("id"), context.authorize("USER", "ADMIN"))
        return Response(status_code=204)

    def place(self, context: RequestContext) -> Response:
        """Передаёт полный состав черновика сервису для атомарного резервирования.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        assert isinstance(context.body, VersionCommand)
        return Responses(
            self.orders.place(
                context.identifier("id"),
                context.authorize("USER", "ADMIN"),
                context.body.version,
                context.identifier("Idempotency-Key"),
            )
        )

    def transition(self, context: RequestContext, target: OrderStatus) -> Response:
        """Проверяет права на смену статуса; владелец может отменить допустимый заказ.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param target: Целевое состояние жизненного цикла.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        if target != OrderStatus.CANCELLED:
            context.authorize("ADMIN")
        assert isinstance(context.body, VersionCommand)
        return Responses(
            self.orders.transition(context.identifier("id"), target, actor, context.body.version)
        )

    def list_payments(self, context: RequestContext) -> Response:
        """Возвращает безопасную историю платежей доступного заказа.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(
            [
                public_payment(row)
                for row in self.payments.find_payments(
                    context.identifier("id"), context.authorize("USER", "ADMIN")
                )
            ]
        )

    def create_payment(self, context: RequestContext) -> Response:
        """Вызывает симулятор оплаты под той же блокировкой заказа, что оформление и истечение резерва.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        request = context.validated(PaymentRequest, ValidationService.payment)
        result, replayed = self.payments.create_payment(
            context.identifier("id"), context.identifier("Idempotency-Key"), request, actor
        )
        return Responses(public_payment(result), status_code=200 if replayed else 201)
