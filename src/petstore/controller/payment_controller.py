"""Авторизация и передача HTTP-команд сервисам приложения."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.payment_data import PaymentData
from petstore.model.requests import (
    PaymentRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_payment


class PaymentController:
    """Симуляция оплаты, повторы, история и удаление отклонённых попыток."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.data = PaymentData(database)

    def create_payment(self, context: RequestContext) -> Response:
        """Создаёт платёж или возвращает результат повтора по обязательному ключу идемпотентности.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        payment, replayed = self.data.create_payment(
            context.identifier("orderId"),
            context.identifier("Idempotency-Key"),
            context.validated(PaymentRequest, V.payment),
            actor,
        )
        return Responses(public_payment(payment), status_code=200 if replayed else 201)

    def list_payments(self, context: RequestContext) -> Response:
        """Возвращает историю платежей после проверки доступа к заказу.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            [public_payment(row) for row in self.data.find_payments(context.identifier("orderId"), actor)]
        )

    def get_payment(self, context: RequestContext) -> Response:
        """Возвращает безопасную сводку доступного платежа.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            public_payment(
                self.data.get_payment(context.identifier("orderId"), context.identifier("paymentId"), actor)
            )
        )

    def delete_payment(self, context: RequestContext) -> Response:
        """Удаляет отклонённую попытку оплаты только как ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        self.data.delete_declined_payment(context.identifier("orderId"), context.identifier("paymentId"))
        return Response(status_code=204)
