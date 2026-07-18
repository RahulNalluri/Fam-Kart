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

Household invitations use expiring, one-time codes. Only invitation hashes are
stored in PostgreSQL; invitation creation and joining APIs are under development.

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
