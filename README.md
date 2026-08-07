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

Committed grocery activity records are converted into this contract by the
real-time event builder. It explicitly maps all five grocery mutations, reuses the
activity record ID for stable event identity, preserves database ordering and
timestamps, and performs no database writes or Redis publishing.

Successful grocery add, edit, complete, reopen, and delete requests now schedule
their exact committed activity event for Redis publication. Idempotent requests do
not publish duplicate events, and Redis delivery failures are logged without
rolling back or hiding the grocery change already committed to PostgreSQL.

Real-time publication follows a best-effort failure policy. PostgreSQL and its
grocery activity records are the source of truth, so Redis publication runs only
after the database commit. A Redis connection failure is recorded as a structured
warning containing the event, household, event type, policy, and safe error type;
it never changes a successful grocery API response or removes committed data.
Publishing to zero active subscribers is also a success because it is a valid
Pub/Sub state. The API process does not retry publication: in-process retries can
delay requests and cannot make ephemeral Pub/Sub delivery durable. Clients refresh
authoritative grocery data through the API when they connect or reconnect.

Messages contain identifiers and ordering information rather than a second copy of
the grocery record. Mobile clients will refresh authoritative API data after
receiving an event.

Authenticated household members can open
`WS /api/v1/households/{household_id}/ws` with their access token in the
`Authorization: Bearer <token>` header. Tokens are intentionally rejected in query
strings. Invalid authentication closes with code `4401`; unknown, inaccessible, or
previously left households close with privacy-preserving code `4404`.

An in-memory connection manager now tracks authenticated sockets by household and
user, supports multiple devices, broadcasts validated event JSON only within the
target household, and removes disconnected or failed sockets. This local registry
is process-specific; Redis Pub/Sub coordinates events across backend containers.

The backend now owns one asynchronous Redis client per application process. Its
connection URL is validated from `REDIS_URL`, Docker routes it to the Redis service,
and FastAPI closes its connection pool during shutdown. Redis availability can be
checked through `GET /api/v1/health/redis`.

Household real-time messages use deterministic, environment-isolated Redis channel
names such as
`familykart:development:households:<household-id>:events`. The same household and
environment always resolve to the same channel, while different households or
environments cannot share a channel. Publishing and subscribing are separate
modules. The event publisher now serializes validated event envelopes, sends them
to the correct household channel, reports the number of active Redis subscribers,
and translates Redis connection failures into a service-level error. Committed
grocery mutations use the best-effort wrapper around this strict publisher.

The Redis event subscriber listens to one household channel, validates each event
envelope and its household ownership, and forwards accepted events to the local
WebSocket connection manager. Malformed and cross-household messages are ignored,
Redis failures become service-level errors, and Pub/Sub resources close during
normal completion, failure, or cancellation.

Each backend process now coordinates its own household subscriptions. The first
local WebSocket connection starts and awaits one Redis subscriber; additional
devices in that household share it through reference counting. The final local
disconnect cancels the task, and application shutdown stops every subscriber
before closing Redis. Separate backend processes subscribe independently, allowing
one published household event to reach WebSockets connected to any backend.

After a subscription has connected successfully, temporary Redis failures trigger
automatic household resubscription with bounded exponential backoff. Recovery
starts at `REALTIME_RECONNECT_INITIAL_DELAY_SECONDS` and is capped by
`REALTIME_RECONNECT_MAX_DELAY_SECONDS`. Failures and successful recovery are logged
with household and attempt information. An initial Redis failure still rejects the
new WebSocket as temporarily unavailable, while final disconnect and application
shutdown cancel pending recovery immediately.

The complete backend real-time workflow is covered by an opt-in Redis integration
test. It connects two authenticated household members through the real WebSocket
route, adds a grocery item through the real HTTP API, and verifies that the
committed activity is published through Redis and received as the same validated
event by both connections. The event identity is also matched to the activity row
stored in the database.

The mobile foundation now includes a household WebSocket client. It derives
`ws://` or `wss://` endpoints from `EXPO_PUBLIC_API_URL`, authenticates through the
`Authorization` header, validates the versioned grocery event contract with Zod,
reports connection and close states, rejects malformed or cross-household events,
and detaches all handlers during local disconnect. Authentication storage remains
a separate module.

Temporary mobile WebSocket closures now reconnect automatically with exponential
backoff from one second up to 30 seconds. A successful recovery resets the delay
and emits a reconnect callback for later data recovery. Normal local/server closure
and backend close codes `4401` and `4404` do not retry, while manual disconnect
cancels any pending timer and prevents stale sockets from reconnecting.

TanStack React Query is now provided at the Expo application root. Stable grocery
query keys isolate cached data by household and shopping session. Validated
real-time events invalidate only the affected session's item list and activity
feed; edit, complete, and reopen events also invalidate the affected item details,
while delete events remove stale item details. Active queries can therefore refetch
authoritative API data without changing unrelated household or session caches.

The `useHouseholdRealtime` hook now owns the mobile real-time lifecycle. It creates
one authenticated client when a household and access token are available, forwards
events to targeted React Query synchronization, refreshes all cached grocery data
for that household after reconnection, replaces the connection when credentials or
household change, and disconnects on unmount. Late callbacks from an obsolete
client are ignored.

Mobile real-time processing now tracks event IDs and per-session sequence numbers.
Repeated event IDs and stale sequence numbers are ignored, consecutive events use
targeted cache synchronization, and a detected sequence gap refreshes the complete
affected shopping session. The tracker keeps a bounded event-ID history and resets
after reconnection, when the household API refresh establishes a new ordering
baseline.

A complete mobile integration suite now drives raw WebSocket JSON through the real
client validator, lifecycle hook, ordering tracker, and React Query synchronizer.
It verifies successful cache updates, malformed and cross-household rejection,
duplicate and stale suppression, gap recovery, reconnection refresh, and ordering
reset without opening a network connection during mobile unit tests.

The mobile lifecycle hook now follows React Native AppState transitions. It opens
the household socket only while the app is active, disconnects once during
inactive/background transitions, ignores late background events, and reconnects
with a household cache refresh when the app returns to the foreground. Repeated
state notifications cannot create duplicate sockets, and unmount removes both the
AppState listener and WebSocket connection.

Mobile real-time closures are now converted into typed, understandable outcomes.
An expired session (`4401`) asks the user to sign in again, unavailable household
access (`4404`) stops without retrying, and temporary service (`1013`) or network
interruptions report recovery messages while automatic reconnection continues.
Normal client closure remains silent at the lifecycle-hook boundary.

The reusable mobile `RealtimeStatusNotice` presents these safe messages as an
accessible status band without exposing numeric WebSocket codes or raw server
reasons. Permanent session and household failures are visually distinct from
temporary interruptions that are reconnecting. It is ready to mount in the
authenticated grocery interface when that screen is implemented.

The household real-time lifecycle now routes permanent failures to explicit app
actions: expired authentication requests a sign-in flow, while unavailable
household access identifies which selected household must be cleared. Temporary
service and network interruptions continue reconnecting without triggering either
permanent action, and successful recovery emits a callback that can clear a stale
warning. Navigation and account-state changes remain owned by their future mobile
screens rather than the WebSocket layer.

A focused mobile presentation integration now joins the lifecycle hook, notice
state, and accessible status component. Retryable warnings appear while recovery
is pending and clear after reconnection; permanent authentication or household
warnings remain until their owning app action explicitly clears them. Normal and
late background closures produce no visible warning, and technical close codes
and server reasons remain outside rendered UI.

The Phase 6 reliability review now forces household sockets to reconnect when a
backend loses its Redis subscription, preventing a silent stale-data window.
Household leave and member removal revoke local sockets and publish an internal
Redis control message so connections on other backend instances are revoked with
the same privacy-preserving household close outcome. Mobile recovery also runs
after a retry succeeds even when the original socket never opened, ensuring cache
refresh and temporary-warning cleanup always occur.

Membership-revocation publishing is currently best effort: the backend always
revokes its local sockets, while healthy Redis delivery propagates the action to
other backend instances. Durable cross-service delivery belongs to the production
outbox and hardening work in Phase 13.

The mobile localization foundation uses Expo Localization to inspect device
language preferences, i18next to resolve supported languages and English fallback,
and react-i18next to provide the configured instance to React Native screens.
English (`en`) and Telugu (`te`) resources now cover the welcome screen, backend
status, accessibility status, and real-time connection messages. Both dictionaries
share a typed structure and are tested for matching keys. The welcome screen and
real-time status notice consume these resources, including their accessibility
labels, so they follow the active i18next language. A mobile language-preference
hook now applies a supported authenticated profile preference when it becomes
available, while preserving the device-selected language during profile loading
and ignoring malformed values. The future mobile authentication flow will supply
the profile value to this hook. An accessible English/Telugu segmented selector is
ready for the future registration screen, where the chosen value will be submitted
as `preferred_language`, and for profile settings where users can change it later.
The selector is intentionally not mounted on the temporary welcome screen.
Manual selections are stored locally with Expo SecureStore and restored before the
application renders, preventing a flash in the device language. A valid account
preference can then override the local selection after authentication. Mobile
registration submits the selected language, and authenticated profile updates save
the server-confirmed preference before switching the visible app language.

The mobile grocery dictionary foundation defines canonical keys for common Indian
household staples alongside English names, Telugu names, English plurals, Telugu
forms, and Telugu transliterations. Unicode, case, and whitespace normalization
support deterministic exact-alias lookup, while index construction rejects an
alias assigned to two different items. Fuzzy matching, quantities, units,
and AI extraction remain separate later modules.

Household grocery aliases now form a validated in-memory overlay on the standard
mobile dictionary. Alias lists supplied by the authenticated household API can map
family nicknames, regional Telugu terms, or transliterations to canonical keys.
Each household builds an independent index; standard aliases remain available as
fallbacks, while blank aliases, unknown keys, cross-item duplicates, and attempts
to remap standard terms are rejected.

The backend household-alias database foundation stores the original display alias,
its normalized collision key, and a canonical grocery key under one household.
Database constraints prevent blank values and duplicate normalized aliases inside
the same household while allowing another household to use the same phrase.
Household deletion cascades to its aliases, and optional creator attribution is
cleared rather than deleting shared aliases when an account is removed.

The household-alias repository provides household-scoped create, list, lookup,
update, and delete operations with rollback handling and database-race translation.
The service authorizes both owners and members, hides household data from
outsiders, normalizes multilingual aliases, validates the 15 current canonical
grocery keys, prevents standard English, Telugu, or transliterated terms from being
remapped, and returns domain-level duplicate errors. Authenticated household
members can manage these aliases through `POST` and `GET` at
`/api/v1/households/{household_id}/grocery-aliases`, plus `PATCH` and `DELETE` at
`/api/v1/households/{household_id}/grocery-aliases/{alias_id}`. API responses use
privacy-preserving household isolation and understandable validation messages.
Backend workflow tests verify owner/member collaboration, household-scoped alias
reuse, failed-update data integrity, and immediate access revocation after member
removal across every alias operation.
The mobile household-alias API client now validates authenticated CRUD requests and
backend responses, converts the server's snake-case contract into mobile camel-case
records, and rejects malformed household data before it reaches the local grocery
dictionary. React Query hooks and alias-management screens remain later modules.
Mobile registration now reads the active English or Telugu selection, validates
the account request and response, and sends that value to the backend as
`preferred_language`. The future registration screen can compose this integration
with the existing language selector without maintaining separate language state.
Authenticated profile language updates now persist the server-confirmed preference
locally and switch i18next immediately. Backend rejection, malformed profile data,
and local persistence failure leave the currently visible mobile language intact
so a future profile screen can present a clear retry state.

Localization workflow tests now exercise the complete mobile precedence chain:
device fallback, persisted manual selection, simulated app restart, and
authenticated account override. They also confirm that switching languages updates
multiple mounted surfaces together, unsupported account values cannot replace a
valid restored language, and neither English nor Telugu resources contain blank
translations.

The Phase 7 localization review verified translated visible surfaces,
accessibility labels, device/local/account precedence, persistence failure
fallbacks, dictionary collision checks, and household alias isolation. It also
corrected external language normalization so values such as `TE` are canonicalized
to `te` before reaching i18next without weakening the TypeScript language guard.
Registration and settings screens still need to mount these foundations, and
household alias management still needs React Query hooks and authenticated screens.

### AI Configuration

Phase 8 begins with backend-only OpenRouter settings. Development defaults use the
`openrouter/free` router, a 30-second timeout, a 2,000-character command limit, and
a 512-token response limit. `OPENROUTER_API_KEY` is optional so the application can
start without AI access and later use the rule-based fallback. When configured, the
key is loaded as a secret and must never be added to mobile code or committed.

Copy `backend/.env.example` values into the ignored `backend/.env` file and set only
your own key locally:

```text
OPENROUTER_API_KEY=sk-or-v1-your-key
```

The API base URL must use HTTPS. The model, timeout, input/output limits, optional
HTTP referer, and app title can be changed through environment variables. OpenRouter
requests are made only by the backend provider through the application-scoped HTTPX
client.

The structured grocery extraction contracts define the validated boundary shared
by the OpenRouter and rule-based parsers. Commands accept English or Telugu
language context, while results contain one to 25 grocery items with an explicit
name, optional canonical dictionary key, positive quantity, and normalized unit.
Unknown fields, unsupported canonical values or units, and invalid quantities are
rejected before extracted data can reach the grocery service. Both extraction paths
must satisfy these contracts before the API returns a preview.

The rule-based parser provides the first extraction implementation without using
an external service. It recognizes the shared grocery dictionary, validated
household aliases supplied by the caller, common quantities from one to ten in
English, Telugu, and transliterated Telugu, decimal numbers, and normalized grocery
units. It supports multiple items and quantity placement before or after an item.
Commands containing unknown grocery words or ambiguous quantities are rejected
instead of returning a potentially incomplete shopping list. The AI parsing service
uses this parser automatically when OpenRouter cannot provide a usable result.

The OpenRouter provider now performs backend-only structured grocery extraction
through the Chat Completions API. It sends the Pydantic extraction JSON Schema in
strict mode, requires a provider endpoint that supports the requested parameters,
applies configured input, output, and timeout limits, and validates every returned
item before use. HTTPX is injected so application lifecycle management and tests do
not create hidden clients. Missing configuration, transport failures, API errors,
rate limits, empty output, and malformed model data use controlled exceptions that
never include the API key. The AI parsing service converts expected provider
failures into deterministic fallback reasons without hiding programming errors.

The prompt and security policy separates immutable extraction instructions from a
JSON-encoded user-data message before any OpenRouter request is made. Commands are
normalized for detection and blocked for high-confidence instruction overrides,
role spoofing, model control tokens, safety bypasses, prompt or secret extraction,
character-spacing evasions, encoded attacks, and unsafe control characters. Policy
exceptions contain only a stable reason code, never the rejected command. Structured
output validation and the model's lack of tools provide additional boundaries, but
pattern detection is only one defense layer and must continue to be reviewed as
attack techniques evolve.

The AI parsing service now coordinates the complete extraction path. It applies the
prompt security policy first, prefers a validated OpenRouter result, and falls back
to the deterministic parser when OpenRouter is unconfigured, over its input limit,
unreachable, returns an API failure, or supplies invalid structured data. Outcomes
record whether `openrouter` or `rule_based` produced the items and retain only a
safe fallback category for later observability. Authorized household aliases are
passed to both paths, while only aliases relevant to the current command enter the
external AI prompt. Security-policy rejections and unexpected implementation errors
are never hidden by fallback.

Authenticated household members can now preview parsed grocery commands through
`POST /api/v1/households/{household_id}/grocery-items/parse`. The endpoint verifies
membership before loading household aliases, uses the application-scoped HTTPX
client, and returns only validated proposed items. It does not write grocery rows;
the mobile confirmation flow must submit approved items through the existing item
creation endpoint. Outsiders receive the same household-not-found response, while
unsafe or unrecognized commands receive understandable validation messages.

Household aliases are now integrated into both extraction paths. The AI prompt
receives only aliases whose text actually appears in the current command, capped at
25 and validated against the shared canonical dictionary and standard-term owners.
Relevant aliases are sorted and encoded as untrusted JSON reference data; they may
map existing command text to a canonical key but cannot introduce items. Unrelated
household aliases remain inside the backend, while the full authorized mapping is
still available to the deterministic parser if OpenRouter fallback is needed.

AI parsing workflow tests now exercise the authenticated API through household
alias isolation, secure OpenRouter prompt construction, strict structured-response
validation, and the deterministic fallback. They also verify that prompt injection
is rejected before an external request and that parsing remains a preview operation
which does not create grocery-list rows. OpenRouter is simulated in these tests, so
the suite requires neither internet access nor a real API key.

### Phase 8 Validation

Phase 8 backend validation covers configuration and secret redaction, strict
extraction schemas, English, Telugu, and mixed-language rule parsing, OpenRouter
request and response handling, prompt-injection defenses, household authorization
and alias isolation, deterministic fallback, understandable API errors, and the
complete authenticated parsing workflow. Parsing intentionally returns proposed
items only; voice capture, mobile confirmation UI, and saving approved items belong
to later phases.

### Voice Input Requirements and Permissions

Phase 9 begins with an Expo Audio permission boundary. The native app declares
foreground microphone access with a purpose-specific explanation, while the mobile
permission service exposes `granted`, `requestable`, and `blocked` states without
coupling native APIs to a screen. Permission should be requested only after a user
starts a voice action; a blocked permission must direct the user to system settings
instead of repeatedly opening the native prompt.

Voice recordings are limited to 30 seconds and 5 MB, and background recording is
disabled. These shared mobile requirements prepare later recording and upload
modules; this foundation does not record, retain, upload, or transcribe audio.

### Speech Provider Abstraction

Speech transcription is defined behind a backend-only asynchronous provider
contract so mobile code never contains speech-service credentials. Providers receive
an immutable, previously validated audio input with its media type, safe file name,
and English or Telugu language hint. They must return a normalized, validated
transcript before any text can continue to grocery parsing.

Controlled unavailable and invalid-response errors contain no audio content. This
module defines the contract only: no real speech provider, audio upload endpoint,
recording storage, or transcription fallback is implemented.

### Transcript Simulation

The backend includes a deterministic simulated speech provider for development and
automated tests. It implements the same asynchronous contract as a real provider,
discards the supplied audio reference without reading or retaining its bytes, and
returns a preconfigured `SpeechTranscript` that has already passed language, length,
and text validation.

Simulation is disabled by default through `TRANSCRIPT_SIMULATION_ENABLED=false` and
application settings reject any attempt to enable it in production. No API endpoint
or mobile control exposes simulation yet, and the simulator does not replace future
audio validation or a real transcription provider.

### Mobile Recording Interface

The mobile voice recorder is implemented as a reusable localized component backed
by a platform-neutral lifecycle hook and a thin Expo Audio adapter. Microphone access
is requested only after the user starts recording. The controller prepares the audio
session, applies the 30-second native limit, exposes elapsed time, and returns only a
local URI and bounded duration after a successful stop.

Users can stop, cancel, retry, or open system settings after a blocked permission.
Recordings are discarded when cancelled or when the app leaves the foreground, and
the audio session is released after every terminal path. The component is not mounted
in the temporary home screen yet because final grocery-screen UI and confirmation
flow belong to later modules. No audio is uploaded or transcribed in this module.

### Audio Upload Security

The backend now has a secure ingestion boundary for future voice uploads. Audio is
read in 64 KiB chunks, rejected above a configurable 5 MB limit, and accepted only
when its declared media type matches a supported M4A, WebM, or WAV file signature.
Empty files, unknown formats, and disguised non-audio content are rejected with
controlled errors that do not include private audio bytes.

Client-provided filenames are never trusted. Valid uploads receive a generated safe
name and normalized media type before entering the speech-provider contract, and the
temporary upload is closed on both success and failure. This module does not expose
an upload endpoint, retain recordings, decode audio, or call a transcription service.

### Voice Transcription Integration

The backend voice-transcription service now joins secure audio validation to the
speech-provider contract. Unsupported or unsafe uploads stop before provider access;
validated audio reaches the provider with a normalized media type, generated safe
filename, and English or Telugu language hint. Provider output is validated again as
a `SpeechTranscript` before it can move further through the application.

Known provider errors remain controlled, while malformed responses and unexpected
provider exceptions are converted to safe errors without exposing audio or provider
details. The integration service does not persist audio or transcripts. A public
upload endpoint, production speech provider, grocery parsing, confirmation, and item
creation remain outside this module.

### Transcript-to-Grocery Parsing

Validated English, Telugu, and Telugu-English mixed transcripts can now enter the
same grocery extraction pipeline used by typed commands. The adapter converts the
transcript into a `GroceryExtractionRequest`, uses the speech provider's detected
language, and forwards the caller's already-authorized household aliases to the
existing AI parser and rule-based fallback.

The existing prompt security policy still runs before grocery extraction, and parser
source and fallback metadata remain available for a later confirmation response. The
adapter stores no transcript and creates no grocery items. Audio orchestration, an
HTTP endpoint, mobile confirmation, and explicit item saving remain separate work.

### Voice Confirmation Screen

The mobile app now has a reusable English and Telugu review screen for parsed voice
commands. It displays the transcript and extracted grocery items, lets the user edit
names and quantities, select or clear units, remove incorrect items, cancel, or record
again. Validation mirrors backend limits for names, positive quantities, decimal
precision, and units that require quantities. Editing a name clears the AI's previous
canonical classification so a stale item identity cannot be submitted accidentally.

Adding items requires an explicit enabled confirmation action. Submission and errors
remain controlled by the parent workflow, so this screen cannot save anything by
itself. It is not mounted in Expo Router yet because a later authenticated upload API
and navigation-state module must provide real household transcript data.

### English and Telugu Voice Localization

The complete mobile voice interface now changes between English and Telugu at
runtime, including microphone permissions, recorder states, confirmation controls,
validation, units, accessibility labels, and controlled submission failures. Family
transcripts and grocery names remain exactly as spoken instead of being translated.

Voice submission failures use known error codes rather than arbitrary backend text,
preventing untranslated or sensitive server details from appearing in the app.
Automated checks enforce matching translation keys, interpolation variables, plural
forms, and live language switching across the voice workflow.

### Voice Workflow Tests

Cross-module backend tests now run validated M4A input through simulated speech
transcription, transcript conversion, secure grocery parsing, and the deterministic
rule-based fallback. The suite covers English, Telugu, Telugu-English mixed commands,
multiple items, quantities, units, and household grocery aliases.

Failure-path tests prove that invalid audio never reaches transcription, speech
provider failures never reach grocery parsing, and unsafe transcripts never reach an
extraction provider. Successful results remain confirmation candidates only; these
tests do not create database grocery items or call external AI or speech services.

### Phase 9 Validation

Phase 9 voice-input foundations are validated end to end at their current boundaries:
microphone requirements and permissions, recording lifecycle, bounded audio
validation, speech-provider abstraction, development-only transcript simulation,
transcription orchestration, secure grocery parsing, confirmation controls, and
English/Telugu localization. Backend formatting, linting, typing, unit tests, Redis
integration tests, the backend Docker image build, mobile linting, TypeScript, Jest,
Expo configuration, and Expo SDK 54 dependency compatibility all pass.

The validated foundation does not yet expose an authenticated audio-upload endpoint,
select a production speech provider, mount voice screens in navigation, or save
confirmed items. Those integrations require real account, household, and navigation
state and must retain the explicit confirmation boundary. Physical-device microphone
testing remains pending until that route-level workflow exists.

### Offline Synchronization Requirements and Conflict Policy

Phase 10 starts with a deterministic contract for grocery changes created while a
device has no connection. The server remains the source of truth, while each local
mutation must retain a unique client mutation ID, household and shopping-session
scope, operation and payload, target item ID, base `updated_at` value, creation time,
and retry count. Mutations are replayed in first-in-first-out order within a
household and removed only after server acknowledgement; affected server queries are
then refreshed.

Network failures, timeouts, rate limits, and server failures remain queued for a
later retry. Authentication failures pause replay until the session is refreshed.
Missing or inaccessible household resources discard the affected stale work and
refresh server state, validation failures are rejected, and version or duplicate
conflicts require user review instead of silently overwriting another family
member's work. A delete is considered successful when the item is already absent.

The backend exposes grocery `updated_at` timestamps, while version preconditions and
idempotency are implemented in later Phase 10 modules. This module therefore defines
and tests policy only; Expo SQLite storage, optimistic updates, queue processing,
connectivity detection, and user-facing conflict screens are documented separately.

### Expo SQLite Foundation

The mobile app now includes the Expo SDK 54-compatible `expo-sqlite` module and a
single asynchronous entry point for opening `familykart.db`. Initialization enables
SQLite foreign-key enforcement and write-ahead logging, reads SQLite's
`user_version`, and applies the first schema migration inside an exclusive
transaction. Failed initialization is never cached as a successful connection, so a
later call can retry safely.

The first schema contains only local database metadata and migration versioning. It
does not copy PostgreSQL data or replace the backend: PostgreSQL remains the shared
source of truth, while this SQLite database exists only on one mobile device. Cached
grocery tables, pending mutations, replay processing, and conflict screens remain
separate Phase 10 modules.

### Local Database Schema and Migrations

The local database now has ordered, transactional migrations through schema version 2. New installations run every migration in sequence, while existing version-1
installations apply only the new schema. The initializer refuses newer unsupported
versions and advances SQLite's `user_version` only inside the same exclusive
transaction as each schema change.

Version 2 adds cached shopping-session and grocery-item tables that mirror the
backend's identifiers, statuses, values, and timestamps. Household/session indexes
support later list reads, and deleting a cached session removes only its cached
items. It also adds a durable pending-mutation table with unique mutation IDs, JSON
payload validation, base server timestamps, retry counts, review status, and indexes
that preserve household FIFO replay order. The queue deliberately has no foreign key
to cache tables, so a cache refresh cannot erase unsynchronized user work.

This module defines storage and migration rules only. Repositories for reading and
writing cached groceries, queue compaction and replay, connectivity detection, and
conflict presentation are not implemented yet.

### Local Grocery Cache Repository

The mobile app now has a parameterized SQLite repository for server grocery
snapshots. It atomically upserts one shopping session, removes that session's stale
cached items, and inserts the latest item list with a shared synchronization time.
Decimal quantities remain strings so values such as `5.000` are not changed by
JavaScript floating-point conversion.

Cached reads require household and shopping-session identifiers, return camel-case
application records, and preserve the backend's pending-first ordering. Individual
sessions or complete household caches can be removed without querying or deleting
the independent pending-mutation table. Snapshot validation rejects an item assigned
to a different session before opening a transaction.

This repository stores authoritative snapshots only. Optimistic item overlays,
pending-mutation repository operations, queue replay, and React Query integration
remain separate Phase 10 modules.

### React Query Cache Hydration

Cached grocery snapshots can now hydrate the household/session item query before an
online response is available. Hydration first verifies that the cached session
exists, so a deliberately empty grocery list is distinguishable from a device that
has never cached that session. SQLite's synchronization timestamp becomes React
Query's data timestamp, allowing normal online query behavior to treat older local
data as stale while still rendering it immediately.

Hydration checks the query cache both before and after reading SQLite. Existing
query data skips local reads, and an online response that arrives during the local
read always wins instead of being overwritten by an older snapshot. Storage errors
leave React Query unchanged, and query keys retain household/session isolation.

This module exposes hydration orchestration only. Mounting it in an authenticated
grocery screen, persisting successful network responses, optimistic overlays, and
background queue replay remain separate Phase 10 work.

### Offline Mutation Queue

Offline grocery changes can now be stored in the device's durable SQLite mutation
queue using parameterized queries. Each entry retains its client mutation ID,
household and session scope, target item, operation, JSON payload, base server
timestamp, creation time, retry count, state, and safe failure code. Re-enqueuing the
same mutation ID does not create a duplicate row.

Pending entries are returned only for the requested household in creation-time and
mutation-ID order, matching the agreed FIFO replay policy. Temporary failures
increment the attempt count, conflicts move an entry to `requires_review`, and only
an explicitly acknowledged entry is removed. Review entries are excluded from
normal replay reads. Payload serialization failures and malformed stored JSON use
controlled errors, while arbitrary server text cannot be stored as an error code.

This module manages queue persistence and state only. Mutation compaction, network
replay, backend idempotency/version enforcement, optimistic cache overlays, and
user-facing conflict review remain separate Phase 10 work.

### Backend Grocery Idempotency

All five grocery mutation endpoints now accept an optional UUID in the
`Idempotency-Key` header. The backend stores a SHA-256 fingerprint and the successful
response before committing the grocery item and its activity event. Retrying the
same key, authenticated user, household, session, operation, item, and payload
returns the stored response without repeating PostgreSQL changes or Redis
publication. Existing clients may omit the header and keep their previous behavior.

Idempotency ownership, scope, operation, payload fingerprint, response status, and
response body are committed atomically in PostgreSQL. A concurrent duplicate loses
the primary-key race and replays the winner after its transaction rolls back. Reusing
a key for different mutation data returns an understandable `409` without exposing
the original request. Delete retries retain their successful `204` result after the
grocery row is gone.

Records currently follow household, session, and account cascade cleanup. A bounded
retention task can be added with scheduled production maintenance later. Version
preconditions for stale offline edits and mobile queue replay remain separate Phase
10 modules.

### Optimistic Grocery Updates

Mobile grocery add, edit, complete, reopen, and delete actions can now update their
household and shopping-session React Query caches immediately. Optimistic records
carry the same client mutation ID intended for SQLite queue entries and backend
idempotency headers, expose a pending synchronization marker, and preserve decimal
quantities as strings. Completing and reopening items also preserve the list's
pending-first ordering.

Successful requests replace temporary values with the authoritative server item,
including replacing a temporary add ID with the server-generated ID. Failed requests
can restore the previous list and item detail. Rollback and confirmation refuse to
overwrite the cache after a newer server refresh or real-time update has replaced the
optimistic result. This module provides cache operations only; grocery API mutation
hooks, offline replay, connectivity monitoring, and conflict presentation remain
separate Phase 10 work.

### Connectivity and Sync Coordinator

The mobile app now classifies Expo Network state as online, offline, or unknown and
observes changes through a removable native listener. An active connection requires
an attached network that is not known to lack internet access; unavailable and
indeterminate states never start queued synchronization.

A household-scoped coordinator starts synchronization after an online launch or an
offline-to-online transition. It serializes replay requests, coalesces repeated
triggers, and performs one follow-up run when new work arrives during an active run.
Observable states distinguish connection waiting, active synchronization, temporary
retry waiting, authentication pause, conflict review, and controlled internal errors.
Stopping removes the connectivity listener and prevents late asynchronous results
from changing state.

The coordinator accepts a replay runner interface and does not inspect or transmit
queued payloads itself. Actual grocery HTTP replay, connectivity lifecycle mounting,
and localized status presentation remain separate Phase 10 modules.

### Server Reconciliation and Conflict Handling

Grocery edit, complete, reopen, and delete endpoints now accept an optional
`X-Base-Updated-At` header. When supplied, its timestamp is compared with the current
item `updated_at` value while the shopping session and grocery item rows are locked.
A stale request receives `412 Precondition Failed` with a controlled refresh-and-review
message and creates no item change, activity event, or real-time publication. Existing
online clients may omit the header, while offline replay must send its stored base
timestamp.

The base version is part of the idempotency fingerprint. A retry with the same key,
payload, and base version replays the committed response even though the item version
has advanced; changing the base version while reusing that key is rejected. This
preserves both optimistic concurrency and retry safety.

On mobile, deterministic reconciliation maps successful responses, already-applied
deletes, temporary failures, authentication pauses, inaccessible resources, stale
versions, and invalid mutations to queue actions. Authoritative grocery state is
refreshed before acknowledged or discarded work is removed. Conflicts and invalid
mutations move to `requires_review`, while temporary failures remain queued with an
incremented retry count. The HTTP queue replay loop and user-facing conflict review
screen remain separate Phase 10 modules.

### App Lifecycle Recovery

A household-scoped mobile lifecycle hook now starts offline synchronization only
while React Native reports the app as active. Entering an inactive or background
state stops the coordinator and its connectivity listener. Returning to the
foreground starts it again, causing a fresh connectivity check and a safe queued-work
recovery attempt. Repeated state notifications are ignored, so an
`inactive`-to-`background` transition does not stop twice and duplicate `active`
events do not create overlapping replay runs.

The hook replaces the coordinator when the selected household changes, removes both
AppState and coordinator listeners during cleanup, and ignores late asynchronous
results from an obsolete lifecycle. Its controlled snapshot can later drive a
localized synchronization status component without exposing technical errors. The
hook is not mounted in the temporary home route because authenticated household state
and the HTTP queue replay runner are not available there yet.

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

Redis integration tests require the Docker Redis service and are excluded from the
normal unit-test run. The commands are the same in PowerShell and Unix shells:

```text
docker compose up -d redis
cd backend
pytest -m redis_integration
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
