"""Catalog routes with native typed FastAPI parameters and preserved operation IDs."""

from decimal import Decimal
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Path, Query
from pydantic import BeforeValidator
from starlette.responses import Response

from petstore.api.dependencies import Context, ContractRoute, decode_response
from petstore.controller.catalog_controller import CatalogController
from petstore.model.commerce import (
    CategoryCommand,
    PetCardCommand,
    ProductCommand,
    StockCommand,
    VersionCommand,
)
from petstore.model.responses import CatalogCategory, PetCard, PetPage, ProductCard, ProductPage

router = APIRouter(prefix="/api/v3", route_class=ContractRoute)


def get_controller(context: Context) -> CatalogController:
    """Inject this application's catalog controller without module-global dependencies."""
    return cast(CatalogController, context.request.app.state.controllers.catalog)


Controller = Annotated[CatalogController, Depends(get_controller)]


@router.get(
    "/products",
    name="listProducts",
    operation_id="listProducts",
    tags=["commerce"],
    response_model=ProductPage,
    response_model_exclude_unset=True,
    status_code=200,
)
def list_products(
    context: Context,
    controller: Controller,
    response: Response,
    page: Annotated[int | None, Query(alias="page")] = None,
    page_size: Annotated[int | None, Query(alias="pageSize")] = None,
    q: Annotated[str | None, Query(alias="q")] = None,
    sort: Annotated[str | None, Query(alias="sort")] = None,
    category_id: Annotated[UUID | None, Query(alias="categoryId")] = None,
    min_price: Annotated[Decimal | None, Query(alias="minPrice")] = None,
    max_price: Annotated[Decimal | None, Query(alias="maxPrice")] = None,
    animal_type: Annotated[str | None, Query(alias="animalType")] = None,
    brand: Annotated[str | None, Query(alias="brand")] = None,
    product_type: Annotated[str | None, Query(alias="productType")] = None,
    feed_form: Annotated[str | None, Query(alias="feedForm")] = None,
) -> ProductPage:
    """Публичный каталог."""
    context.parameters = {
        "page": page,
        "pageSize": page_size,
        "q": q,
        "sort": sort,
        "categoryId": category_id,
        "minPrice": min_price,
        "maxPrice": max_price,
        "animalType": animal_type,
        "brand": brand,
        "productType": product_type,
        "feedForm": feed_form,
    }
    result = controller.list_cards(context, "product", True)
    return decode_response(result, response)


@router.post(
    "/products",
    name="createProduct",
    operation_id="createProduct",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=201,
)
def create_product(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[ProductCommand, BeforeValidator(ProductCommand.from_wire), Body()],
) -> ProductCard:
    """Создать черновик карточки."""
    context.body = body
    result = controller.save_card(context, "product", None)
    return decode_response(result, response)


@router.get(
    "/products/{id}",
    name="getProduct",
    operation_id="getProduct",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_product(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> ProductCard:
    """Карточка каталога."""
    context.parameters = {"id": resource_id}
    result = controller.get_card(context, "product", True)
    return decode_response(result, response)


@router.put(
    "/products/{id}",
    name="updateProduct",
    operation_id="updateProduct",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def update_product(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[ProductCommand, BeforeValidator(ProductCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> ProductCard:
    """Обновить карточку по версии."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.save_card(context, "product", resource_id)
    return decode_response(result, response)


@router.get(
    "/admin/products",
    name="listAdminProducts",
    operation_id="listAdminProducts",
    tags=["commerce"],
    response_model=ProductPage,
    response_model_exclude_unset=True,
    status_code=200,
)
def list_admin_products(
    context: Context,
    controller: Controller,
    response: Response,
    page: Annotated[int | None, Query(alias="page")] = None,
    page_size: Annotated[int | None, Query(alias="pageSize")] = None,
    q: Annotated[str | None, Query(alias="q")] = None,
    sort: Annotated[str | None, Query(alias="sort")] = None,
    category_id: Annotated[UUID | None, Query(alias="categoryId")] = None,
    min_price: Annotated[Decimal | None, Query(alias="minPrice")] = None,
    max_price: Annotated[Decimal | None, Query(alias="maxPrice")] = None,
    animal_type: Annotated[str | None, Query(alias="animalType")] = None,
    brand: Annotated[str | None, Query(alias="brand")] = None,
    product_type: Annotated[str | None, Query(alias="productType")] = None,
    feed_form: Annotated[str | None, Query(alias="feedForm")] = None,
    publication_status: Annotated[str | None, Query(alias="publicationStatus")] = None,
) -> ProductPage:
    """Каталог администратора."""
    context.parameters = {
        "page": page,
        "pageSize": page_size,
        "q": q,
        "sort": sort,
        "categoryId": category_id,
        "minPrice": min_price,
        "maxPrice": max_price,
        "animalType": animal_type,
        "brand": brand,
        "productType": product_type,
        "feedForm": feed_form,
        "publicationStatus": publication_status,
    }
    result = controller.list_cards(context, "product", False)
    return decode_response(result, response)


@router.get(
    "/admin/products/{id}",
    name="getAdminProduct",
    operation_id="getAdminProduct",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_admin_product(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> ProductCard:
    """Карточка администратора."""
    context.parameters = {"id": resource_id}
    result = controller.get_card(context, "product", False)
    return decode_response(result, response)


@router.post(
    "/products/{id}/publish",
    name="publishProduct",
    operation_id="publishProduct",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def publish_product(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> ProductCard:
    """Изменить публикацию карточки."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.publish(context, "product", "PUBLISHED")
    return decode_response(result, response)


@router.post(
    "/products/{id}/unpublish",
    name="unpublishProduct",
    operation_id="unpublishProduct",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def unpublish_product(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> ProductCard:
    """Изменить публикацию карточки."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.publish(context, "product", "DRAFT")
    return decode_response(result, response)


@router.post(
    "/products/{id}/archive",
    name="archiveProduct",
    operation_id="archiveProduct",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def archive_product(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> ProductCard:
    """Изменить публикацию карточки."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.publish(context, "product", "ARCHIVED")
    return decode_response(result, response)


@router.get(
    "/catalog/pets",
    name="listCatalogPets",
    operation_id="listCatalogPets",
    tags=["commerce"],
    response_model=PetPage,
    response_model_exclude_unset=True,
    status_code=200,
)
def list_catalog_pets(
    context: Context,
    controller: Controller,
    response: Response,
    page: Annotated[int | None, Query(alias="page")] = None,
    page_size: Annotated[int | None, Query(alias="pageSize")] = None,
    q: Annotated[str | None, Query(alias="q")] = None,
    sort: Annotated[str | None, Query(alias="sort")] = None,
    category_id: Annotated[UUID | None, Query(alias="categoryId")] = None,
    min_price: Annotated[Decimal | None, Query(alias="minPrice")] = None,
    max_price: Annotated[Decimal | None, Query(alias="maxPrice")] = None,
    animal_type: Annotated[str | None, Query(alias="animalType")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
) -> PetPage:
    """Публичный каталог."""
    context.parameters = {
        "page": page,
        "pageSize": page_size,
        "q": q,
        "sort": sort,
        "categoryId": category_id,
        "minPrice": min_price,
        "maxPrice": max_price,
        "animalType": animal_type,
        "status": status,
    }
    result = controller.list_cards(context, "pet", True)
    return decode_response(result, response)


@router.get(
    "/catalog/pets/{id}",
    name="getCatalogPet",
    operation_id="getCatalogPet",
    tags=["commerce"],
    response_model=PetCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_catalog_pet(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> PetCard:
    """Карточка каталога."""
    context.parameters = {"id": resource_id}
    result = controller.get_card(context, "pet", True)
    return decode_response(result, response)


@router.get(
    "/admin/pets",
    name="listAdminPets",
    operation_id="listAdminPets",
    tags=["commerce"],
    response_model=PetPage,
    response_model_exclude_unset=True,
    status_code=200,
)
def list_admin_pets(
    context: Context,
    controller: Controller,
    response: Response,
    page: Annotated[int | None, Query(alias="page")] = None,
    page_size: Annotated[int | None, Query(alias="pageSize")] = None,
    q: Annotated[str | None, Query(alias="q")] = None,
    sort: Annotated[str | None, Query(alias="sort")] = None,
    category_id: Annotated[UUID | None, Query(alias="categoryId")] = None,
    min_price: Annotated[Decimal | None, Query(alias="minPrice")] = None,
    max_price: Annotated[Decimal | None, Query(alias="maxPrice")] = None,
    animal_type: Annotated[str | None, Query(alias="animalType")] = None,
    status: Annotated[str | None, Query(alias="status")] = None,
    publication_status: Annotated[str | None, Query(alias="publicationStatus")] = None,
) -> PetPage:
    """Каталог администратора."""
    context.parameters = {
        "page": page,
        "pageSize": page_size,
        "q": q,
        "sort": sort,
        "categoryId": category_id,
        "minPrice": min_price,
        "maxPrice": max_price,
        "animalType": animal_type,
        "status": status,
        "publicationStatus": publication_status,
    }
    result = controller.list_cards(context, "pet", False)
    return decode_response(result, response)


@router.post(
    "/admin/pets",
    name="createPetCard",
    operation_id="createPetCard",
    tags=["commerce"],
    response_model=PetCard,
    response_model_exclude_unset=True,
    status_code=201,
)
def create_pet_card(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PetCardCommand, BeforeValidator(PetCardCommand.from_wire), Body()],
) -> PetCard:
    """Создать черновик карточки."""
    context.body = body
    result = controller.save_card(context, "pet", None)
    return decode_response(result, response)


@router.get(
    "/admin/pets/{id}",
    name="getAdminPet",
    operation_id="getAdminPet",
    tags=["commerce"],
    response_model=PetCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def get_admin_pet(
    context: Context,
    controller: Controller,
    response: Response,
    resource_id: Annotated[UUID, Path(alias="id")],
) -> PetCard:
    """Карточка администратора."""
    context.parameters = {"id": resource_id}
    result = controller.get_card(context, "pet", False)
    return decode_response(result, response)


@router.put(
    "/admin/pets/{id}",
    name="updatePetCard",
    operation_id="updatePetCard",
    tags=["commerce"],
    response_model=PetCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def update_pet_card(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[PetCardCommand, BeforeValidator(PetCardCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> PetCard:
    """Обновить карточку по версии."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.save_card(context, "pet", resource_id)
    return decode_response(result, response)


@router.post(
    "/admin/pets/{id}/publish",
    name="publishPetCard",
    operation_id="publishPetCard",
    tags=["commerce"],
    response_model=PetCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def publish_pet_card(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> PetCard:
    """Изменить публикацию карточки."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.publish(context, "pet", "PUBLISHED")
    return decode_response(result, response)


@router.post(
    "/admin/pets/{id}/unpublish",
    name="unpublishPetCard",
    operation_id="unpublishPetCard",
    tags=["commerce"],
    response_model=PetCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def unpublish_pet_card(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> PetCard:
    """Изменить публикацию карточки."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.publish(context, "pet", "DRAFT")
    return decode_response(result, response)


@router.post(
    "/admin/pets/{id}/archive",
    name="archivePetCard",
    operation_id="archivePetCard",
    tags=["commerce"],
    response_model=PetCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def archive_pet_card(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[VersionCommand, BeforeValidator(VersionCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> PetCard:
    """Изменить публикацию карточки."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.publish(context, "pet", "ARCHIVED")
    return decode_response(result, response)


@router.post(
    "/products/{id}/stock-adjustments",
    name="adjustProductStock",
    operation_id="adjustProductStock",
    tags=["commerce"],
    response_model=ProductCard,
    response_model_exclude_unset=True,
    status_code=200,
)
def adjust_product_stock(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[StockCommand, BeforeValidator(StockCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> ProductCard:
    """Корректировка остатков."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.adjust_stock(context)
    return decode_response(result, response)


@router.get(
    "/catalog/categories",
    name="listCategories",
    operation_id="listCategories",
    tags=["commerce"],
    response_model=list[CatalogCategory],
    response_model_exclude_unset=True,
    status_code=200,
)
def list_categories(
    context: Context,
    controller: Controller,
    response: Response,
    kind: Annotated[str | None, Query(alias="kind")] = None,
) -> list[CatalogCategory]:
    """Активные категории."""
    context.parameters = {"kind": kind}
    result = controller.categories(context, True)
    return decode_response(result, response)


@router.get(
    "/admin/catalog/categories",
    name="listAdminCategories",
    operation_id="listAdminCategories",
    tags=["commerce"],
    response_model=list[CatalogCategory],
    response_model_exclude_unset=True,
    status_code=200,
)
def list_admin_categories(
    context: Context,
    controller: Controller,
    response: Response,
) -> list[CatalogCategory]:
    """Все категории."""
    result = controller.categories(context, False)
    return decode_response(result, response)


@router.post(
    "/admin/catalog/categories",
    name="createCategory",
    operation_id="createCategory",
    tags=["commerce"],
    response_model=CatalogCategory,
    response_model_exclude_unset=True,
    status_code=201,
)
def create_category(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[CategoryCommand, BeforeValidator(CategoryCommand.from_wire), Body()],
) -> CatalogCategory:
    """Создать категорию."""
    context.body = body
    result = controller.save_category(context, None)
    return decode_response(result, response)


@router.put(
    "/admin/catalog/categories/{id}",
    name="updateCategory",
    operation_id="updateCategory",
    tags=["commerce"],
    response_model=CatalogCategory,
    response_model_exclude_unset=True,
    status_code=200,
)
def update_category(
    context: Context,
    controller: Controller,
    response: Response,
    body: Annotated[CategoryCommand, BeforeValidator(CategoryCommand.from_wire), Body()],
    resource_id: Annotated[UUID, Path(alias="id")],
) -> CatalogCategory:
    """Обновить или деактивировать категорию."""
    context.parameters = {"id": resource_id}
    context.body = body
    result = controller.save_category(context, resource_id)
    return decode_response(result, response)
