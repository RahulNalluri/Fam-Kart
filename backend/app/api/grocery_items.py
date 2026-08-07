from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.redis import get_redis
from app.db.session import get_db
from app.models.grocery_mutation_idempotency import GroceryMutationIdempotency
from app.models.user import User
from app.repositories.grocery_activity_events import GroceryActivityEventRepository
from app.repositories.grocery_items import GroceryItemRepository
from app.repositories.grocery_mutation_idempotency import (
    DuplicateGroceryMutationIdempotencyError,
    GroceryMutationIdempotencyContext,
    GroceryMutationIdempotencyRepository,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import ShoppingSessionRepository
from app.schemas.grocery_activity_events import GroceryActivityEventResponse
from app.schemas.grocery_items import (
    CreateGroceryItemRequest,
    GroceryItemResponse,
    UpdateGroceryItemRequest,
)
from app.services.grocery_items import (
    GroceryItemAssigneeNotFoundError,
    GroceryItemCompletedError,
    GroceryItemDuplicateError,
    GroceryItemNotFoundError,
    GroceryItemShoppingSessionCompletedError,
    GroceryItemShoppingSessionNotFoundError,
    GroceryItemVersionConflictError,
    complete_grocery_item,
    create_grocery_item,
    delete_grocery_item,
    list_grocery_activity_events,
    list_grocery_items,
    reopen_grocery_item,
    update_grocery_item,
)
from app.services.grocery_mutation_idempotency import (
    GroceryMutationIdempotencyConflictError,
    GroceryMutationOperation,
    build_grocery_mutation_idempotency_context,
    validate_grocery_mutation_replay,
)
from app.services.realtime_events import build_realtime_event
from app.services.realtime_publisher import try_publish_realtime_event

router = APIRouter(
    prefix=("/api/v1/households/{household_id}/shopping-sessions/{session_id}/items"),
    tags=["grocery items"],
)

IDEMPOTENCY_CONFLICT_DETAIL = (
    "This idempotency key was already used for a different grocery change."
)
VERSION_CONFLICT_DETAIL = (
    "This grocery item was changed by another household member. Refresh the list "
    "and review your change."
)


def _versioned_idempotency_payload(
    payload: dict[str, object],
    base_updated_at: datetime | None,
) -> dict[str, object]:
    if base_updated_at is None:
        return payload
    return {
        **payload,
        "_base_updated_at": base_updated_at.isoformat(),
    }


def _raise_version_conflict(error: GroceryItemVersionConflictError) -> None:
    raise HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail=VERSION_CONFLICT_DETAIL,
    ) from error


def _prepare_idempotent_mutation(
    *,
    mutation_id: UUID | None,
    user_id: UUID,
    household_id: UUID,
    session_id: UUID,
    operation: GroceryMutationOperation,
    response_status: int,
    item_id: UUID | None,
    payload: dict[str, object],
    db: Session,
) -> tuple[
    GroceryMutationIdempotencyContext | None,
    GroceryMutationIdempotency | None,
]:
    if mutation_id is None:
        return None, None

    context = build_grocery_mutation_idempotency_context(
        mutation_id=mutation_id,
        user_id=user_id,
        household_id=household_id,
        shopping_session_id=session_id,
        operation=operation,
        response_status=response_status,
        item_id=item_id,
        payload=payload,
    )
    record = GroceryMutationIdempotencyRepository(db).get(mutation_id)
    if record is not None:
        _validate_replay(record, context)
        _validate_replay_access(
            db=db,
            user_id=user_id,
            household_id=household_id,
            session_id=session_id,
        )
    return context, record


def _validate_replay(
    record: GroceryMutationIdempotency,
    context: GroceryMutationIdempotencyContext,
) -> None:
    try:
        validate_grocery_mutation_replay(record, context)
    except GroceryMutationIdempotencyConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=IDEMPOTENCY_CONFLICT_DETAIL,
        ) from error


def _validate_replay_access(
    *,
    db: Session,
    user_id: UUID,
    household_id: UUID,
    session_id: UUID,
) -> None:
    membership = HouseholdMemberRepository(db).get_for_user_and_household(
        user_id=user_id,
        household_id=household_id,
    )
    shopping_session = ShoppingSessionRepository(db).get_for_household(
        session_id=session_id,
        household_id=household_id,
    )
    if membership is None or shopping_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This shopping session could not be found or you do not have "
                "access to it."
            ),
        )


def _load_concurrent_replay(
    db: Session,
    context: GroceryMutationIdempotencyContext | None,
) -> GroceryMutationIdempotency:
    if context is None:
        raise RuntimeError("An idempotency conflict requires a mutation context.")
    record = GroceryMutationIdempotencyRepository(db).get(context.mutation_id)
    if record is None:
        raise RuntimeError("The committed idempotency result could not be loaded.")
    _validate_replay(record, context)
    return record


def _replay_item_response(
    record: GroceryMutationIdempotency,
) -> GroceryItemResponse:
    if record.response_body is None:
        raise RuntimeError("The stored grocery mutation response is missing.")
    return GroceryItemResponse.model_validate(record.response_body)


def _schedule_committed_realtime_event(
    background_tasks: BackgroundTasks,
    redis_client: Redis,
    item_repository: GroceryItemRepository,
) -> None:
    activity_event = item_repository.take_committed_activity_event()
    if activity_event is None:
        return

    event = build_realtime_event(activity_event)
    background_tasks.add_task(try_publish_realtime_event, redis_client, event)


@router.post(
    "",
    response_model=GroceryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_current_session_grocery_item(
    household_id: UUID,
    session_id: UUID,
    data: CreateGroceryItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        UUID | None,
        Header(alias="Idempotency-Key"),
    ] = None,
) -> GroceryItemResponse:
    idempotency_context, replay = _prepare_idempotent_mutation(
        mutation_id=idempotency_key,
        user_id=current_user.id,
        household_id=household_id,
        session_id=session_id,
        operation=GroceryMutationOperation.ADD,
        response_status=status.HTTP_201_CREATED,
        item_id=None,
        payload=data.model_dump(mode="json"),
        db=db,
    )
    if replay is not None:
        return _replay_item_response(replay)

    item_repository = GroceryItemRepository(db)
    try:
        item = create_grocery_item(
            household_id,
            session_id,
            data,
            current_user,
            item_repository,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
            idempotency_context=idempotency_context,
        )
    except DuplicateGroceryMutationIdempotencyError:
        return _replay_item_response(
            _load_concurrent_replay(db, idempotency_context),
        )
    except GroceryItemShoppingSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This shopping session could not be found or you do not have "
                "access to it."
            ),
        ) from error
    except GroceryItemShoppingSessionCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot add items because this shopping session is already "
                "completed."
            ),
        ) from error
    except GroceryItemAssigneeNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected person is not a member of this household.",
        ) from error
    except GroceryItemDuplicateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This item is already pending in this shopping session.",
        ) from error
    _schedule_committed_realtime_event(
        background_tasks,
        redis_client,
        item_repository,
    )
    return GroceryItemResponse.model_validate(item)


@router.get("", response_model=list[GroceryItemResponse])
def list_current_session_grocery_items(
    household_id: UUID,
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[GroceryItemResponse]:
    try:
        items = list_grocery_items(
            household_id,
            session_id,
            current_user,
            GroceryItemRepository(db),
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except GroceryItemShoppingSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This shopping session could not be found or you do not have "
                "access to it."
            ),
        ) from error

    return [GroceryItemResponse.model_validate(item) for item in items]


@router.get("/activity", response_model=list[GroceryActivityEventResponse])
def list_current_session_grocery_activity(
    household_id: UUID,
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[GroceryActivityEventResponse]:
    try:
        events = list_grocery_activity_events(
            household_id,
            session_id,
            current_user,
            GroceryActivityEventRepository(db),
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
            limit=limit,
        )
    except GroceryItemShoppingSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This shopping session could not be found or you do not have "
                "access to it."
            ),
        ) from error

    return [GroceryActivityEventResponse.model_validate(event) for event in events]


@router.patch("/{item_id}", response_model=GroceryItemResponse)
def update_current_session_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    data: UpdateGroceryItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        UUID | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    base_updated_at: Annotated[
        datetime | None,
        Header(alias="X-Base-Updated-At"),
    ] = None,
) -> GroceryItemResponse:
    idempotency_context, replay = _prepare_idempotent_mutation(
        mutation_id=idempotency_key,
        user_id=current_user.id,
        household_id=household_id,
        session_id=session_id,
        operation=GroceryMutationOperation.EDIT,
        response_status=status.HTTP_200_OK,
        item_id=item_id,
        payload=_versioned_idempotency_payload(
            data.model_dump(mode="json", exclude_unset=True),
            base_updated_at,
        ),
        db=db,
    )
    if replay is not None:
        return _replay_item_response(replay)

    item_repository = GroceryItemRepository(db)
    try:
        item = update_grocery_item(
            household_id,
            session_id,
            item_id,
            data,
            current_user,
            item_repository,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
            expected_updated_at=base_updated_at,
            idempotency_context=idempotency_context,
        )
    except DuplicateGroceryMutationIdempotencyError:
        return _replay_item_response(
            _load_concurrent_replay(db, idempotency_context),
        )
    except GroceryItemNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This grocery item could not be found or you do not have access "
                "to it."
            ),
        ) from error
    except GroceryItemShoppingSessionCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot edit items because this shopping session is already "
                "completed."
            ),
        ) from error
    except GroceryItemCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reopen this grocery item before editing it.",
        ) from error
    except GroceryItemAssigneeNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected person is not a member of this household.",
        ) from error
    except GroceryItemDuplicateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This item is already pending in this shopping session.",
        ) from error
    except GroceryItemVersionConflictError as error:
        _raise_version_conflict(error)
    _schedule_committed_realtime_event(
        background_tasks,
        redis_client,
        item_repository,
    )
    return GroceryItemResponse.model_validate(item)


@router.patch("/{item_id}/complete", response_model=GroceryItemResponse)
def complete_current_session_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        UUID | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    base_updated_at: Annotated[
        datetime | None,
        Header(alias="X-Base-Updated-At"),
    ] = None,
) -> GroceryItemResponse:
    idempotency_context, replay = _prepare_idempotent_mutation(
        mutation_id=idempotency_key,
        user_id=current_user.id,
        household_id=household_id,
        session_id=session_id,
        operation=GroceryMutationOperation.COMPLETE,
        response_status=status.HTTP_200_OK,
        item_id=item_id,
        payload=_versioned_idempotency_payload({}, base_updated_at),
        db=db,
    )
    if replay is not None:
        return _replay_item_response(replay)

    item_repository = GroceryItemRepository(db)
    try:
        item = complete_grocery_item(
            household_id,
            session_id,
            item_id,
            current_user,
            item_repository,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
            expected_updated_at=base_updated_at,
            idempotency_context=idempotency_context,
        )
    except DuplicateGroceryMutationIdempotencyError:
        return _replay_item_response(
            _load_concurrent_replay(db, idempotency_context),
        )
    except GroceryItemNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This grocery item could not be found or you do not have access "
                "to it."
            ),
        ) from error
    except GroceryItemShoppingSessionCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot complete items because this shopping session is "
                "already completed."
            ),
        ) from error
    except GroceryItemVersionConflictError as error:
        _raise_version_conflict(error)

    _schedule_committed_realtime_event(
        background_tasks,
        redis_client,
        item_repository,
    )
    return GroceryItemResponse.model_validate(item)


@router.patch("/{item_id}/reopen", response_model=GroceryItemResponse)
def reopen_current_session_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        UUID | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    base_updated_at: Annotated[
        datetime | None,
        Header(alias="X-Base-Updated-At"),
    ] = None,
) -> GroceryItemResponse:
    idempotency_context, replay = _prepare_idempotent_mutation(
        mutation_id=idempotency_key,
        user_id=current_user.id,
        household_id=household_id,
        session_id=session_id,
        operation=GroceryMutationOperation.REOPEN,
        response_status=status.HTTP_200_OK,
        item_id=item_id,
        payload=_versioned_idempotency_payload({}, base_updated_at),
        db=db,
    )
    if replay is not None:
        return _replay_item_response(replay)

    item_repository = GroceryItemRepository(db)
    try:
        item = reopen_grocery_item(
            household_id,
            session_id,
            item_id,
            current_user,
            item_repository,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
            expected_updated_at=base_updated_at,
            idempotency_context=idempotency_context,
        )
    except DuplicateGroceryMutationIdempotencyError:
        return _replay_item_response(
            _load_concurrent_replay(db, idempotency_context),
        )
    except GroceryItemNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This grocery item could not be found or you do not have access "
                "to it."
            ),
        ) from error
    except GroceryItemShoppingSessionCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot reopen items because this shopping session is already "
                "completed."
            ),
        ) from error
    except GroceryItemDuplicateError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This item is already pending in this shopping session.",
        ) from error
    except GroceryItemVersionConflictError as error:
        _raise_version_conflict(error)

    _schedule_committed_realtime_event(
        background_tasks,
        redis_client,
        item_repository,
    )
    return GroceryItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_session_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    redis_client: Annotated[Redis, Depends(get_redis)],
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[
        UUID | None,
        Header(alias="Idempotency-Key"),
    ] = None,
    base_updated_at: Annotated[
        datetime | None,
        Header(alias="X-Base-Updated-At"),
    ] = None,
) -> Response:
    idempotency_context, replay = _prepare_idempotent_mutation(
        mutation_id=idempotency_key,
        user_id=current_user.id,
        household_id=household_id,
        session_id=session_id,
        operation=GroceryMutationOperation.DELETE,
        response_status=status.HTTP_204_NO_CONTENT,
        item_id=item_id,
        payload=_versioned_idempotency_payload({}, base_updated_at),
        db=db,
    )
    if replay is not None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    item_repository = GroceryItemRepository(db)
    try:
        delete_grocery_item(
            household_id,
            session_id,
            item_id,
            current_user,
            item_repository,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
            expected_updated_at=base_updated_at,
            idempotency_context=idempotency_context,
        )
    except DuplicateGroceryMutationIdempotencyError:
        _load_concurrent_replay(db, idempotency_context)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except GroceryItemNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This grocery item could not be found or you do not have access "
                "to it."
            ),
        ) from error
    except GroceryItemShoppingSessionCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot delete items because this shopping session is already "
                "completed."
            ),
        ) from error
    except GroceryItemCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reopen this grocery item before deleting it.",
        ) from error
    except GroceryItemVersionConflictError as error:
        _raise_version_conflict(error)

    _schedule_committed_realtime_event(
        background_tasks,
        redis_client,
        item_repository,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
