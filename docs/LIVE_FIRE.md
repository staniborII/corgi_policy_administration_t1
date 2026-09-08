# Live-Fire Testing

## Current State

Persona integration is configured for simulated mode (no sandbox credentials configured by default). When `PERSONA_API_KEY` and `PERSONA_TEMPLATE_ID` are set, the system calls the real Persona sandbox API.

## Persona Sandbox Testing

### Prerequisites
1. Set environment variables:
   - `PERSONA_API_KEY` — sandbox API key from Persona dashboard
   - `PERSONA_WEBHOOK_SECRET` — webhook signing secret
   - `PERSONA_TEMPLATE_ID` — business verification template ID

2. Configure Persona webhook endpoint:
   - URL: `{your_base_url}/api/integrations/webhooks/persona/`
   - For local development, use ngrok or similar tunnel

### Test Flow
1. Staff creates a broker via `/staff/brokers`
2. Staff clicks "Initiate KYB" — creates Persona inquiry
3. Complete the Persona verification flow in the sandbox
4. Persona sends webhook to `/api/integrations/webhooks/persona/`
5. Broker status transitions to APPROVED or REJECTED
6. Staff can now create policies through the approved broker

### Simulated Mode
When credentials are not configured:
- KYB initiation returns a `SIMULATED-{uuid}` inquiry ID
- UI displays a "SIMULATED" warning
- Broker state can be advanced manually via webhook testing tools

## Stripe Live-Fire

Not yet implemented. Will be added in Milestone 3.
