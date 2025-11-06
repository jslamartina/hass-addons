# Add MQTT Integration (EMQX) during setup-fresh-ha.sh

### What we’ll change

- Extend `scripts/setup-fresh-ha.sh` to create/configure the MQTT integration pointing to EMQX via REST config entries flow.
- Use credentials from `hass-credentials.env` (`MQTT_USER`, `MQTT_PASS`).
- Use the long‑lived token the script already generates to authenticate REST calls to `HA_URL`.
- Make it idempotent: skip if MQTT already configured, or gracefully handle `abort` reasons.
- Leave Cync Controller `mqtt_host` as `localhost` (unchanged).

### Key assumptions

- Broker is EMQX add-on, reachable as `localhost:1883`. If not reachable, fallback to `a0d7b954-emqx:1883`.
- Credentials are present in `hass-credentials.env`.

### Implementation details

1. Add constants and derive configuration ✅

- Compute:
  - `MQTT_BROKER_HOST=localhost` (fallback: `MQTT_BROKER_HOST_FALLBACK=a0d7b954-emqx`)
  - `MQTT_BROKER_PORT=1883`
  - `MQTT_USERNAME=$MQTT_USER`, `MQTT_PASSWORD=$MQTT_PASS`
  - `AUTH_TOKEN=$LONG_LIVED_ACCESS_TOKEN` (created earlier in the script)

2. Wait for EMQX to be reachable ✅

- Poll TCP `localhost:1883`; if not reachable within short timeout, try `a0d7b954-emqx:1883` (overall timeout + retries). Use whichever host succeeds for subsequent steps.

3. Run MQTT config flow via REST (idempotent) ✅

- Start flow:

```bash
curl -sf -X POST "$HA_URL/api/config/config_entries/flow" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"handler":"mqtt","show_advanced_options":true}'
```

- If response has `type:"abort"` with reasons like `already_configured` or `single_instance_allowed`, treat as success and skip.
- Else extract `flow_id` and `data_schema`. Build `user_input` only for fields present (typical fields: `broker`, `port`, `username`, `password`, optionally `discovery`, `client_id`). Submit:

```bash
curl -sf -X POST "$HA_URL/api/config/config_entries/flow/$FLOW_ID" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_input":{"broker":"$MQTT_BROKER_HOST","port":$MQTT_BROKER_PORT,"username":"$MQTT_USERNAME","password":"$MQTT_PASSWORD","discovery":true}}'
```

- If another step is returned, repeat: read `data_schema`, fill only known fields with safe defaults. Stop when `type:"create_entry"`.

4. Verify integration is active ✅

- Publish a test message via HA service to confirm the `mqtt` domain is loaded:

```bash
curl -sf -X POST "$HA_URL/api/services/mqtt/publish" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topic":"cync_controller_addon/test","payload":"ok","qos":0,"retain":false}'
```

- On success (HTTP 200), print success message. If 404, the integration didn’t load; log and continue with guidance.

5. Wire into main flow ✅

- Call new steps after `start_emqx` and before installing/configuring Cync Controller.

### Edge cases & handling

- Missing `MQTT_USER`/`MQTT_PASS`: log a warning and skip integration (user can configure later).
- EMQX not reachable within timeout: log error and continue the rest of setup.
- Flow aborts with `cannot_connect`: retry once (broker may still be starting), then warn.
- Re-runs: The flow will abort as already configured; we treat it as success (idempotent).
- ShellCheck compliance noted (SC2181 resolved via direct `if !` checks).

### To-dos (completed)

- [x] Add EMQX host/port and MQTT creds derivation in setup-fresh-ha.sh
- [x] Implement wait for EMQX TCP 1883 to be reachable (localhost, fallback to a0d7b954-emqx)
- [x] Start MQTT config flow via REST and handle aborts
- [x] Submit user_input with broker/port/username/password; loop until create_entry
- [x] Verify MQTT domain by publishing test message via HA services API
- [x] Call MQTT integration setup after start_emqx and before Cync config
