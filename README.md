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
endpoints will be added in later modules. The shopping-session repository and
service layers now create and retrieve household-scoped sessions, permit only
current members, and prevent more than one active session per household.
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
