import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from redis.asyncio import Redis

from app.services.realtime_connections import RealtimeConnectionManager
from app.services.realtime_memberships import revoke_realtime_membership


def test_revocation_closes_local_connections_and_notifies_other_backends() -> None:
    redis_client = Mock(spec=Redis)
    manager = Mock(spec=RealtimeConnectionManager)
    manager.disconnect_user = AsyncMock(return_value=1)
    household_id = uuid4()
    user_id = uuid4()

    with patch(
        "app.services.realtime_memberships.try_publish_realtime_membership_revoked",
        new_callable=AsyncMock,
        return_value=True,
    ) as publisher:
        asyncio.run(
            revoke_realtime_membership(
                redis_client,
                manager,
                household_id,
                user_id,
            ),
        )

    manager.disconnect_user.assert_awaited_once_with(
        household_id,
        user_id,
        code=4404,
        reason="Household not found.",
    )
    publisher.assert_awaited_once()
    published_message = publisher.await_args.args[1]
    assert published_message.household_id == household_id
    assert published_message.user_id == user_id
