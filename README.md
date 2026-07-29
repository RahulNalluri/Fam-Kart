# FamilyKart AI

FamilyKart AI is a multilingual grocery list app for Indian families.

The app is designed to help family members manage a shared shopping list together. Each person in a household will be able to add, update, complete, and remove grocery items so everyone stays in sync.

FamilyKart AI will initially support English and Telugu, with future support planned for voice-based grocery commands and Telugu-English mixed input.

## Status

This project is currently under development.

Phase 1 builds the project foundation: backend health API, mobile welcome screen, local Docker services, and test tooling.

The backend is under development. It currently provides health checks, database
foundations, password security utilities, and user registration through
`POST /api/v1/auth/register`. Registered users can authenticate and receive
access and refresh tokens through `POST /api/v1/auth/login`.
Successful logins store a hashed authentication session in the database,
and `POST /api/v1/auth/refresh` securely rotates refresh tokens while issuing a
new access token. `POST /api/v1/auth/logout` revokes the current login session.
Authenticated users can retrieve their personal profile through
`GET /api/v1/users/me` with a Bearer access token.

Authenticated users can update their display name or preferred language through
`PATCH /api/v1/users/me`. Email and password changes are handled separately.

Authenticated users can permanently delete their account through
`DELETE /api/v1/users/me` after confirming their password. Household owners must
transfer ownership before deletion.

Authenticated users can create a household through `POST /api/v1/households`.
The creator becomes the household owner automatically.
`GET /api/v1/households` returns only the households that the authenticated user
belongs to, together with their role in each household.
Household members can retrieve one membership-scoped household through
`GET /api/v1/households/{household_id}`; outsiders receive a not-found response.
They can also list that household's members through
`GET /api/v1/households/{household_id}/members` without exposing private account
or authentication fields.
Regular members can leave through
`DELETE /api/v1/households/{household_id}/members/me`. Owners must transfer
ownership before leaving so a household cannot be left without an owner.
An owner can atomically transfer ownership to an existing member through
`PATCH /api/v1/households/{household_id}/owner`. The previous owner remains in
the household as a regular member.
Household owners can remove regular members through
`DELETE /api/v1/households/{household_id}/members/{member_user_id}`. Removing a
membership does not delete that user's account.
Household owners can rename their household through
`PATCH /api/v1/households/{household_id}`. Names are trimmed and validated before
the existing household is updated.

Household invitations use expiring, one-time codes. Only invitation hashes are
stored in PostgreSQL. Any current household member can create an invitation through
`POST /api/v1/households/{household_id}/invitations`. Authenticated users can join
as members through `POST /api/v1/households/join` with a valid invitation code.
Owners can list usable invitation metadata through
`GET /api/v1/households/{household_id}/invitations` and revoke an unused code
through `DELETE /api/v1/households/{household_id}/invitations/{invitation_id}`.
Listing never exposes plaintext codes or stored code hashes.
Combined authorization workflows verify owner/member/outsider isolation and
permission changes after transfer, removal, leaving, and rejoining.

The grocery-list phase now includes the `shopping_sessions` database foundation.
Each session belongs to one household, records who created it when available, and
supports active and completed lifecycle states. Grocery items and session API
endpoints build on this foundation. The shopping-session repository and service
layers create and retrieve household-scoped sessions, permit only current members,
and prevent more than one active session per household.
Authenticated household members can access this behavior through
`POST /api/v1/households/{household_id}/shopping-sessions`,
`GET /api/v1/households/{household_id}/shopping-sessions`, and
`GET /api/v1/households/{household_id}/shopping-sessions/{session_id}`.
Members can idempotently complete an active session through
`PATCH /api/v1/households/{household_id}/shopping-sessions/{session_id}/complete`.
Completing the active session allows the household to start a new one.
The `grocery_items` database foundation stores multilingual item names, optional
decimal quantities, units, notes, assignment and completion attribution, and
pending/completed lifecycle timestamps within a shopping session.
Grocery-item request schemas normalize user-entered text and validate quantities,
field lengths, optional assignment IDs, and server-managed fields before any
future repository or API operation receives the data.
The grocery-item repository persists pending items, scopes individual lookups to
their shopping session, lists pending items before completed items, and rolls
back failed writes.
The grocery-item service permits current household members to add items only to
active sessions, validates that assignees belong to the same household, protects
session completion races with row locking, and keeps completed-session lists
available as history.
Authenticated household members can add and list grocery items through
`POST /api/v1/households/{household_id}/shopping-sessions/{session_id}/items`
and `GET /api/v1/households/{household_id}/shopping-sessions/{session_id}/items`.
Pending items in active sessions can be edited through
`PATCH /api/v1/households/{household_id}/shopping-sessions/{session_id}/items/{item_id}`.
Household members can idempotently complete or reopen items in an active session
through the corresponding `.../items/{item_id}/complete` and
`.../items/{item_id}/reopen` PATCH endpoints.
Pending items in active sessions can be permanently removed through
`DELETE /api/v1/households/{household_id}/shopping-sessions/{session_id}/items/{item_id}`.
Grocery mutations are recorded as activity events and can be listed newest first
through `GET /api/v1/households/{household_id}/shopping-sessions/{session_id}/items/activity`.
Pending grocery-item names are unique within each shopping session after trimming,
whitespace normalization, and case-insensitive comparison. Duplicate adds, renames,
and reopens return a clear conflict response, while completed items and items in
other shopping sessions do not conflict.
Grocery authorization tests verify immediate access revocation after membership
removal and prevent cross-household sessions or cross-session item IDs from being
used to read or mutate another grocery list.
A complete grocery workflow test covers API-based session creation, collaborative
assignment and editing, duplicate rejection, completion, reopening, deletion,
session completion, and retained activity history.

### Real-Time Event Contract

Phase 6 begins with a strict, versioned notification contract for grocery changes.
The future WebSocket and Redis layers will exchange messages shaped like this:

```json
{
  "schema_version": 1,
  "event_id": "6dd50ac8-8465-4be6-9036-c323d8805621",
  "event_type": "grocery.item_added",
  "household_id": "43af621f-932b-4721-aed4-7db4367cfed5",
  "occurred_at": "2026-07-27T12:00:00Z",
  "payload": {
    "shopping_session_id": "10538635-a8d4-4284-bc75-d975fb2e56c7",
    "grocery_item_id": "8d009993-4557-4ca2-b34b-0e027e43dd41",
    "actor_user_id": "a097321c-deba-4877-84f1-d60c742c7d21",
    "item_name": "Rice",
    "sequence_number": 1
  }
}
```

Messages contain identifiers and ordering information rather than a second copy of
the grocery record. Mobile clients will refresh authoritative API data after
receiving an event.

Authenticated household members can open
`WS /api/v1/households/{household_id}/ws` with their access token in the
`Authorization: Bearer <token>` header. Tokens are intentionally rejected in query
strings. Invalid authentication closes with code `4401`; unknown, inaccessible, or
previously left households close with privacy-preserving code `4404`. The current
endpoint keeps authorized connections open, but grocery mutations do not publish
events yet.

An in-memory connection manager now tracks authenticated sockets by household and
user, supports multiple devices, broadcasts validated event JSON only within the
target household, and removes disconnected or failed sockets. This local registry
is process-specific; Redis Pub/Sub is still required to coordinate multiple backend
containers.

The backend now owns one asynchronous Redis client per application process. Its
connection URL is validated from `REDIS_URL`, Docker routes it to the Redis service,
and FastAPI closes its connection pool during shutdown. Redis availability can be
checked through `GET /api/v1/health/redis`. Pub/Sub messaging is not implemented yet.

Household real-time messages use deterministic, environment-isolated Redis channel
names such as
`familykart:development:households:<household-id>:events`. The same household and
environment always resolve to the same channel, while different households or
environments cannot share a channel. Publishing and subscribing are separate
modules and are not implemented yet.

## Quick Start

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
cd backend
pip install -e ".[dev]"
pytest
```

Unix:

```bash
source .venv/bin/activate
cd backend
pip install -e ".[dev]"
pytest
```

Docker:

```bash
docker compose up --build
```

Mobile:

```bash
cd mobile
npm install
npm start
```
