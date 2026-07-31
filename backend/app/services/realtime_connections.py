import asyncio
from uuid import UUID

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.schemas.realtime import RealtimeEventEnvelope


class RealtimeConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, dict[UUID, set[WebSocket]]] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        household_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ) -> None:
        async with self._lock:
            household_connections = self._connections.setdefault(household_id, {})
            user_connections = household_connections.setdefault(user_id, set())
            user_connections.add(websocket)

    async def unregister(
        self,
        household_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ) -> None:
        async with self._lock:
            self._remove_connection(household_id, user_id, websocket)

    async def connection_count(
        self,
        household_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> int:
        async with self._lock:
            households = (
                [self._connections.get(household_id, {})]
                if household_id is not None
                else list(self._connections.values())
            )
            if user_id is not None:
                return sum(
                    len(household_connections.get(user_id, set()))
                    for household_connections in households
                )
            return sum(
                len(connections)
                for household_connections in households
                for connections in household_connections.values()
            )

    async def disconnect_user(
        self,
        household_id: UUID,
        user_id: UUID,
        *,
        code: int,
        reason: str,
    ) -> int:
        async with self._lock:
            household_connections = self._connections.get(household_id)
            if household_connections is None:
                connections: list[WebSocket] = []
            else:
                connections = list(household_connections.pop(user_id, set()))
                if not household_connections:
                    self._connections.pop(household_id)

        return await self._close_connections(connections, code, reason)

    async def disconnect_household(
        self,
        household_id: UUID,
        *,
        code: int,
        reason: str,
    ) -> int:
        async with self._lock:
            household_connections = self._connections.pop(household_id, {})
            connections = [
                websocket
                for user_connections in household_connections.values()
                for websocket in user_connections
            ]

        return await self._close_connections(connections, code, reason)

    async def broadcast(
        self,
        household_id: UUID,
        event: RealtimeEventEnvelope,
    ) -> int:
        if event.household_id != household_id:
            raise ValueError("Real-time event does not belong to this household.")

        async with self._lock:
            recipients = [
                (user_id, websocket)
                for user_id, connections in self._connections.get(
                    household_id,
                    {},
                ).items()
                for websocket in connections
            ]

        if not recipients:
            return 0

        serialized_event = event.model_dump_json()
        results = await asyncio.gather(
            *(
                self._send_event(websocket, serialized_event)
                for _, websocket in recipients
            ),
        )
        failed_connections = [
            (user_id, websocket)
            for (user_id, websocket), delivered in zip(
                recipients,
                results,
                strict=True,
            )
            if not delivered
        ]
        if failed_connections:
            async with self._lock:
                for user_id, websocket in failed_connections:
                    self._remove_connection(household_id, user_id, websocket)

        return sum(results)

    async def _send_event(self, websocket: WebSocket, event_json: str) -> bool:
        try:
            await websocket.send_text(event_json)
        except (OSError, RuntimeError, WebSocketDisconnect):
            return False
        return True

    async def _close_connections(
        self,
        connections: list[WebSocket],
        code: int,
        reason: str,
    ) -> int:
        if not connections:
            return 0

        results = await asyncio.gather(
            *(
                self._close_connection(websocket, code, reason)
                for websocket in connections
            ),
        )
        return sum(results)

    async def _close_connection(
        self,
        websocket: WebSocket,
        code: int,
        reason: str,
    ) -> bool:
        try:
            await websocket.close(code=code, reason=reason)
        except (OSError, RuntimeError, WebSocketDisconnect):
            return False
        return True

    def _remove_connection(
        self,
        household_id: UUID,
        user_id: UUID,
        websocket: WebSocket,
    ) -> None:
        household_connections = self._connections.get(household_id)
        if household_connections is None:
            return

        user_connections = household_connections.get(user_id)
        if user_connections is None:
            return

        user_connections.discard(websocket)
        if not user_connections:
            household_connections.pop(user_id)
        if not household_connections:
            self._connections.pop(household_id)


connection_manager = RealtimeConnectionManager()
