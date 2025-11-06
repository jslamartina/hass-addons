<!-- 5875b85a-3bcf-46fc-b051-832811e8b255 c5810a28-1fca-48db-a60f-958c1e0f07b5 -->

# Test Plan: MQTT Integration Automation in `scripts/setup-fresh-ha.sh`

### Scope

Validate the new MQTT automation in `scripts/setup-fresh-ha.sh`:

- EMQX reachability and host selection (localhost → fallback `a0d7b954-emqx`)
- REST config flow creation and completion
- Idempotency (already configured / single instance)
- Publish verification (`mqtt.publish` service)
- Error handling (missing creds, broker down, missing jq)

### Implementation notes (what the script does)

- Handles MQTT config flow menu step by POSTing `{ "next_step_id": "broker" }`.
- Submits form fields at the top level (not wrapped in `user_input`).
- Picks broker host: try `localhost:1883`, fallback to `a0d7b954-emqx:1883` (reachability tested from `hassio_cli`).
- Verifies by calling `mqtt.publish` (expects HTTP 200) after configuration.

### Prerequisites

- Devcontainer + Supervisor running; `ha` CLI works
- `hass-credentials.env` contains `HASS_USERNAME`, `HASS_PASSWORD`, `MQTT_USER`, `MQTT_PASS`
- Script can create a long-lived token (Node available)
- EMQX add-on present (script installs/starts it)

### Global variables (examples)

```bash
export HA_URL=http://homeassistant.local:8123
source ./hass-credentials.env
```

### Happy-path (fresh setup)

1. Ensure EMQX not started: `ha addons stop a0d7b954_emqx || true`
2. Run setup: `./scripts/setup-fresh-ha.sh`
3. Expect:
   - EMQX installed/started
   - Logs show: "MQTT broker reachable ..." and "MQTT integration configured successfully" OR "already configured"
   - Verify MQTT services present:

```bash
curl -sf -H "Authorization: Bearer $LONG_LIVED_ACCESS_TOKEN" \
  "$HA_URL/api/services" | jq 'any(.[]; .domain=="mqtt")'
```

- Verify publish works (HTTP 200):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $LONG_LIVED_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  "$HA_URL/api/services/mqtt/publish" \
  -d '{"topic":"cync_controller_addon/test","payload":"ok"}'
```

### Idempotency (re-run)

1. Re-run setup: `./scripts/setup-fresh-ha.sh`
2. Expect log: "MQTT integration already configured"; no errors; publish still 200.

### Host selection fallback

1. With EMQX running, the script checks `localhost` then falls back to `a0d7b954-emqx` if unreachable from `hassio_cli`.
2. Verify the active host decision from logs: "MQTT broker reachable at <host>:1883"; accept either `localhost` or `a0d7b954-emqx`.
3. Optional (deep check): use WS API (`config_entries/list`) to inspect the MQTT entry data `broker` field.

### Error handling: missing credentials

1. Temporarily move creds: `cp hass-credentials.env /tmp/creds && grep -v '^MQTT_' /tmp/creds > hass-credentials.env`
2. Run setup: `./scripts/setup-fresh-ha.sh`
3. Expect log: "MQTT credentials missing... skipping MQTT integration setup"; script continues.
4. Restore creds: `mv /tmp/creds hass-credentials.env`

### Error handling: broker unreachable

1. Stop EMQX: `ha addons stop a0d7b954_emqx`
2. Run setup: `./scripts/setup-fresh-ha.sh`
3. Expect: "Could not reach MQTT broker ..." and "Skipping MQTT integration setup because broker is unreachable" (no crash).
4. Start EMQX: `ha addons start a0d7b954_emqx`

### Error handling: jq unavailable (informational)

- If `jq` is unavailable inside `hassio_cli`, expect: "jq not available; skipping automated MQTT integration setup".

### Optional retained message sanity (MQTT behavior)

- Using an external client, publish retained `retain:true`, then subscribe as a new client; expect only the new subscriber receives the retained message.

### Logs and evidence

- Script logs for each phase
- `ha addons logs a0d7b954_emqx` for broker side confirmations
- `GET /api/services` output shows `mqtt` domain present
- HTTP 200 from `mqtt/publish`

### Cleanup / Reset (if needed)

- Remove MQTT integration via UI (Settings → Devices & Services → MQTT → Delete) to re-run fresh
- Or use WS API (`config_entries/remove`) for the MQTT entry

### Results so far

- Happy-path: PASSED
- Idempotency: PASSED
- Host fallback: OBSERVED (used `a0d7b954-emqx`)

### Remaining optional tests

- Missing credentials handling
- Broker down handling
- Retained message sanity
