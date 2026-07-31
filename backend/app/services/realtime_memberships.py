from uuid import UUID

from redis.asyncio import Redis

from app.schemas.realtime import RealtimeCloseCode, RealtimeMembershipRevokedEnvelope
from app.services.realtime_connections import RealtimeConnectionManager
from app.services.realtime_publisher import try_publish_realtime_membership_revoked


async def revoke_realtime_membership(
    redis_client: Redis,
    connection_manager: RealtimeConnectionManager,
    household_id: UUID,
    user_id: UUID,
) -> None:
    await connection_manager.disconnect_user(
        household_id,
        user_id,
        code=int(RealtimeCloseCode.HOUSEHOLD_NOT_FOUND),
        reason="Household not found.",
    )
    await try_publish_realtime_membership_revoked(
        redis_client,
        RealtimeMembershipRevokedEnvelope(
            household_id=household_id,
            user_id=user_id,
        ),
    )
