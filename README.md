# Glow Studio · da Salon Home prototype

A single-page Next.js salon site with the existing daSalon-bot voice engine in a bottom-right panel. The owner workspace is at `/settings`. Bookings use an isolated mock Partner API, not the actual da Salon platform.

## Start locally (Windows)

Prerequisites: Node 22+ and Python 3.12. From the project root:

```powershell
npm.cmd ci
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
```

Configure `backend/.env` using `backend/.env.example` for `FIREWORKS_API_KEY` and `SARVAM_API_KEY`. The provided project environment has been retained locally; environment files are ignored by Git. Never put provider keys in `NEXT_PUBLIC_*` variables.

```powershell
./scripts/start.ps1
```

Or use two terminals:

```powershell
# Terminal 1, from backend/
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
# Terminal 2, from the project root
npm.cmd run dev
```

- Salon: http://127.0.0.1:3000
- Agent settings: http://127.0.0.1:3000/settings
- Mock API documentation: http://127.0.0.1:8001/docs

## Try it

1. Open Talk to Glow. Type a request, or tap the orb to enable the microphone.
2. Ask about a haircut, choose a future date, and ask for Ananya or Rohan.
3. Confirm the service, stylist, time, name and phone number.
4. When prompted, enter your phone and **any six ASCII digits** in the phone form.
5. Confirm the booking read-back. A successful booking displays a demo receipt.
6. Try the same stylist/time in a second browser session: overlapping appointments are rejected.

The phone step deliberately does not send SMS or verify ownership. It only accepts a six-digit value and associates the phone with the current demo session. This behavior must be replaced before real use.

## Scope and integration

```text
Next.js landing page + settings
  ├─ HTTP /api/backend/* → FastAPI :8001
  └─ audio WebSocket → FastAPI /voice/ws
       ├─ existing Sarvam STT/TTS + Fireworks conversation engine
       ├─ uploaded salon knowledge (Chroma)
       └─ tools → HTTP mock Partner API → local demo records
```

`backend/app/partner_api.py` is the adapter boundary for future authorized Partner integration. Operations are `get_services`, `get_staff`, `get_offers`, `get_hours`, `check_availability`, and `book_appointment`. Each accepts `{arguments, session_id}` under `/mock-partner/{salon_id}/{operation}`. Availability considers opening hours, service duration, qualified staff, working days and existing bookings. Full roster exceptions and room/equipment capacity are outside this initial mock.

### Conversation behavior

The shared text/voice policy covers brief off-topic detours, budget objections, approved aftercare, human-contact requests and unsupported actions. The owner cannot enable cancellation or a pretend human transfer in this demo. Exact `stop` requests clear the draft without cancelling an existing appointment.

Booking read-backs include service, stylist, local date/time, duration and price. The panel shows an appointment review card. Explicit confirmation is tied to the exact draft and its quoted price/duration; an intervening question disarms that confirmation. Phone collection preserves the draft, and any six ASCII digits still complete the demo step without SMS. A fresh read-back follows that step.

The mock booking boundary also checks server-issued consent. Lost write responses are reconciled through `get_booking_status`, using the original request fingerprint. An unresolved result blocks new creation and is shown as pending, never as a definite success or failure. This remains a single-process local prototype, not production identity or distributed transaction infrastructure.

The existing Python voice, language, interruption, audio-worklet and speech playback code is retained. The JavaScript voice client is mounted through a Next.js client component, with cleanup on unmount. The GPT-OSS path buffers parsed LLM completion text to prevent raw reasoning from being spoken; audio output remains streamed on live calls. Provider latency depends on the services and network.

Settings include instructions, tone, languages, greeting, voice, pace, provider, waiting phrases, preview and knowledge upload/removal. Prices and offers come from mock records. Upload salon-approved aftercare; the agent should acknowledge missing knowledge rather than invent treatment advice. The supplied policy file is illustrative demo content, not a real salon's clinical guidance.

## Configuration and limits

- `BACKEND_URL` (Next server) defaults to `http://127.0.0.1:8001`.
- `NEXT_PUBLIC_VOICE_WS_URL` defaults to `ws://127.0.0.1:8001/voice/ws`.
- `PARTNER_API_BASE_URL` (Python) defaults to `http://127.0.0.1:8001/mock-partner`.
- `VOICE_ALLOWED_ORIGINS` defaults to the localhost Next.js origins on port 3000.
- `VOICE_ADMIN_TOKEN` enables Bearer-token access for owner endpoints. Without it, access is allowed only from loopback for this local demo. Do not deploy the loopback proxy publicly without configuring authentication.
- Local storage is disk-persisted mongomock under ignored `backend/data/`. Run **one backend process**: booking locks and session guards are process-local.
- No real Partner connection, payment processing, outbound SMS or human handoff is implemented.
- Browser recognition varies by browser. Microphone capture requires localhost or HTTPS. Live speech requires valid Sarvam credentials; typed conversation requires valid Fireworks credentials.

## Checks

```powershell
npm.cmd run build
cd backend
.venv/Scripts/python.exe -m pytest tests/test_home_integration.py tests/test_availability.py tests/test_booking_conflicts.py tests/test_voice_core.py -q
.venv/Scripts/python.exe -m pytest tests/test_conversation_branches.py tests/test_turn_contract.py -q
```

The archive's original tests are retained as reference; some assert the old demo routes/behavior. The integration tests above cover the new phone/session and API boundaries. Tests use isolated temporary data and no provider credentials.

Salon photograph: [Unsplash image](https://images.unsplash.com/photo-1560066984-138dadb4c035). The brand, address, service menu and bookings are demonstration content inherited from the supplied project. Original archive logs, audio recordings, backup trees and database snapshots were not imported.
