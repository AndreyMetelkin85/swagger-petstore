"""Авторизация и передача HTTP-команд сервисам приложения."""

from starlette.responses import Response

from petstore.controller.context import RequestContext
from petstore.data.database import Database
from petstore.data.order_data import OrderData
from petstore.model.enums import OrderStatus
from petstore.model.requests import (
    OrderCreateRequest,
)
from petstore.service.validation_service import ValidationService as V
from petstore.utils.responses import Responses, public_order


class OrderController:
    """Черновики, оформление, состояния и удаление заказов с проверкой ролей."""

    def __init__(self, database: Database) -> None:
        """Настраивает зависимости операции на общем пуле приложения.

        :param database: Общий пул соединений PostgreSQL этого экземпляра приложения.
        :return: Ничего не возвращает.
        """
        self.data = OrderData(database)

    def get_inventory(self, context: RequestContext) -> Response:
        """Возвращает сводку заказов только администратору.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        context.authorize("ADMIN")
        return Responses(self.data.get_count_by_status())

    def list_orders(self, context: RequestContext) -> Response:
        """Возвращает все заказы ADMIN или только заказы текущего покупателя.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(
            [public_order(row) for row in self.data.find_all(context.authorize("USER", "ADMIN"))]
        )

    def get_order_by_id(self, context: RequestContext) -> Response:
        """Возвращает заказ после проверки владельца.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(public_order(self.data.get_order_by_id(context.identifier("orderId"), actor)))

    def create_order_draft(self, context: RequestContext) -> Response:
        """Создаёт черновик без резервирования питомца.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            public_order(self.data.create_draft(context.validated(OrderCreateRequest, V.order), actor)),
            status_code=201,
        )

    def update_order_draft(self, context: RequestContext) -> Response:
        """Заменяет редактируемые поля собственного черновика.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize("USER", "ADMIN")
        return Responses(
            public_order(
                self.data.update_draft(
                    context.identifier("orderId"), context.validated(OrderCreateRequest, V.order), actor
                )
            )
        )

    def place_order_draft(self, context: RequestContext) -> Response:
        """Сохраняет снимки оформления и резервирует питомца из черновика.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return Responses(
            public_order(
                self.data.place_draft(context.identifier("orderId"), context.authorize("USER", "ADMIN"))
            )
        )

    def delete_order(self, context: RequestContext) -> Response:
        """Удаляет только черновик либо завершённый заказ, доступный для удаления ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        self.data.delete_order(context.identifier("orderId"), context.authorize("USER", "ADMIN"))
        return Response(status_code=204)

    def transition(self, context: RequestContext, target: OrderStatus, admin_only: bool) -> Response:
        """Проверяет права и выполняет разрешённый переход состояния заказа.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :param target: Целевое состояние жизненного цикла.
        :param admin_only: Требуется ли административный доступ к неопубликованным данным.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        actor = context.authorize(*(("ADMIN",) if admin_only else ("USER", "ADMIN")))
        return Responses(public_order(self.data.transition(context.identifier("orderId"), target, actor)))

    def approve_order(self, context: RequestContext) -> Response:
        """Подтверждает допустимый заказ с проверкой роли ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return self.transition(context, OrderStatus.APPROVED, True)

    def ship_order(self, context: RequestContext) -> Response:
        """Переводит подтверждённый заказ в отправленный с проверкой ADMIN.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return self.transition(context, OrderStatus.SHIPPED, True)

    def deliver_order(self, context: RequestContext) -> Response:
        """Завершает доставку отправленного заказа и отмечает питомца проданным.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return self.transition(context, OrderStatus.DELIVERED, True)

    def cancel_order(self, context: RequestContext) -> Response:
        """Отменяет допустимый собственный заказ и возвращает успешную оплату.

        :param context: Контекст текущего HTTP-запроса с сервисом авторизации и разобранными данными.
        :return: HTTP-ответ с публичными данными и статусом операции.
        """
        return self.transition(context, OrderStatus.CANCELLED, False)
