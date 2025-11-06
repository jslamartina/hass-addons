# Automated WebSocket Long-Lived Access Token Creation Plan

**Goal:** Fully automated token creation without any manual intervention

## The Challenge

We need a **bootstrap token** to authenticate with WebSocket, but we can't get one programmatically because:

- Password grant is deprecated (`grant_type=password` returns "unsupported_grant_type")
- Login flow is complex and requires CSRF tokens
- We need an existing token to create a new token (chicken-and-egg problem)

## Solution: Browser Automation + WebSocket

**Strategy:** Use Playwright to login and extract bootstrap token, then use WebSocket to create long-lived token

### Phase 1: Automated Bootstrap Token Extraction

**File:** `scripts/create-token-automated.js`

```javascript
async function createTokenFullyAutomated() {
  // 1. Launch browser and login automatically
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // 2. Navigate and login
  await page.goto(HA_URL);
  await page.fill('[name="username"]', USERNAME);
  await page.fill('[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForLoadState("networkidle");

  // 3. Extract bootstrap token from localStorage
  const bootstrapToken = await page.evaluate(() => {
    const tokens = localStorage.getItem("hassTokens");
    return JSON.parse(tokens).access_token;
  });

  await browser.close();

  // 4. Use bootstrap token with WebSocket to create long-lived token
  return await createLongLivedTokenViaWebSocket(bootstrapToken);
}
```

### Phase 2: WebSocket Token Creation

**File:** `scripts/lib/websocket-token.js`

```javascript
async function createLongLivedTokenViaWebSocket(bootstrapToken) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(WS_URL);

    ws.on("message", (data) => {
      const message = JSON.parse(data);

      if (message.type === "auth_required") {
        ws.send(
          JSON.stringify({
            type: "auth",
            access_token: bootstrapToken,
          }),
        );
      } else if (message.type === "auth_ok") {
        ws.send(
          JSON.stringify({
            id: 1,
            type: "auth/long_lived_access_token",
            client_name: "Setup Script",
            lifespan: 3650,
          }),
        );
      } else if (message.type === "result" && message.success) {
        ws.close();
        resolve(message.result);
      }
    });
  });
}
```

### Phase 3: Integration with Setup Script

**File:** `scripts/setup-fresh-ha.sh` (modify `get_ha_auth_token()`)

```bash
get_ha_auth_token() {
  log_info "Setting up Home Assistant auth token for Core API..."

  # Check if we already have a token from onboarding
  if [ -n "$HA_AUTH_TOKEN" ]; then
    log_success "Using auth token from onboarding"
    return 0
  fi

  # Check if we have a token in credentials file
  if [ -n "$LONG_LIVED_ACCESS_TOKEN" ]; then
    log_info "Using long-lived access token from credentials file"
    HA_AUTH_TOKEN="$LONG_LIVED_ACCESS_TOKEN"
    return 0
  fi

  # No token available - create one automatically
  log_info "No authentication token available, creating one automatically..."

  local new_token
  new_token=$(node scripts/create-token-automated.js 2>&1)

  if [ -n "$new_token" ] && [[ "$new_token" =~ ^eyJ ]]; then
    HA_AUTH_TOKEN="$new_token"
    log_success "Long-lived access token created automatically"

    # Save to credentials file for future use
    if grep -q "LONG_LIVED_ACCESS_TOKEN=" "$CREDENTIALS_FILE" 2> /dev/null; then
      sed -i "s|^LONG_LIVED_ACCESS_TOKEN=.*|LONG_LIVED_ACCESS_TOKEN=$new_token|" "$CREDENTIALS_FILE"
    else
      echo "LONG_LIVED_ACCESS_TOKEN=$new_token" >> "$CREDENTIALS_FILE"
    fi
    log_success "Token saved to credentials file"
    return 0
  else
    log_error "Failed to create token automatically: $new_token"
    log_warn "MQTT integration will need to be configured manually"
    return 1
  fi
}
```

## Implementation Steps

### Step 1: Create Automated Token Creator

**File:** `scripts/create-token-automated.js`

```javascript
const { chromium } = require("playwright");
const WebSocket = require("ws");
const fs = require("fs");
const path = require("path");

const HA_URL = process.env.HA_URL || "http://localhost:8123";
const WS_URL = HA_URL.replace("http", "ws") + "/api/websocket";
const USERNAME = process.env.HASS_USERNAME || "dev";
const PASSWORD = process.env.HASS_PASSWORD || "dev";
const TOKEN_NAME = "Setup Script";
const CREDENTIALS_FILE = path.join(__dirname, "..", "hass-credentials.env");

async function createTokenFullyAutomated() {
  console.log("[auto-token] Starting fully automated token creation...");

  // Phase 1: Get bootstrap token via browser automation
  const bootstrapToken = await getBootstrapToken();
  if (!bootstrapToken) {
    throw new Error("Failed to get bootstrap token");
  }

  console.log(
    "[auto-token] Bootstrap token obtained, creating long-lived token...",
  );

  // Phase 2: Create long-lived token via WebSocket
  const longLivedToken = await createLongLivedTokenViaWebSocket(bootstrapToken);
  if (!longLivedToken) {
    throw new Error("Failed to create long-lived token");
  }

  console.log("[auto-token] Long-lived token created successfully");

  // Phase 3: Save to credentials file
  updateCredentialsFile(longLivedToken);

  return longLivedToken;
}

async function getBootstrapToken() {
  console.log("[auto-token] Launching browser for login...");

  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  try {
    const page = await browser.newPage();

    // Navigate to Home Assistant
    await page.goto(HA_URL, { timeout: 30000 });
    await page.waitForLoadState("networkidle");

    // Login
    console.log("[auto-token] Logging in...");
    await page.fill('[name="username"]', USERNAME);
    await page.fill('[name="password"]', PASSWORD);
    await page.click('button[type="submit"]');
    await page.waitForLoadState("networkidle", { timeout: 10000 });

    // Extract token from localStorage
    console.log("[auto-token] Extracting bootstrap token...");
    const tokenData = await page.evaluate(() => {
      const hassTokens = localStorage.getItem("hassTokens");
      if (hassTokens) {
        const parsed = JSON.parse(hassTokens);
        return parsed.access_token;
      }
      return null;
    });

    if (!tokenData) {
      throw new Error("No token found in localStorage");
    }

    console.log("[auto-token] Bootstrap token extracted");
    return tokenData;
  } finally {
    await browser.close();
  }
}

async function createLongLivedTokenViaWebSocket(bootstrapToken) {
  console.log("[auto-token] Creating long-lived token via WebSocket...");

  return new Promise((resolve, reject) => {
    const ws = new WebSocket(WS_URL);
    let messageId = 1;

    ws.on("open", () => {
      console.log("[auto-token] WebSocket connected");
    });

    ws.on("message", (data) => {
      try {
        const message = JSON.parse(data);

        if (message.type === "auth_required") {
          console.log("[auto-token] Authenticating with bootstrap token...");
          ws.send(
            JSON.stringify({
              type: "auth",
              access_token: bootstrapToken,
            }),
          );
        } else if (message.type === "auth_ok") {
          console.log(
            "[auto-token] Authenticated, requesting long-lived token...",
          );
          ws.send(
            JSON.stringify({
              id: messageId++,
              type: "auth/long_lived_access_token",
              client_name: TOKEN_NAME,
              lifespan: 3650,
            }),
          );
        } else if (message.type === "result" && message.success) {
          console.log("[auto-token] Long-lived token created!");
          ws.close();
          resolve(message.result);
        } else if (message.type === "result" && !message.success) {
          reject(
            new Error("Failed to create token: " + JSON.stringify(message)),
          );
        } else if (message.type === "auth_invalid") {
          reject(new Error("Authentication failed: " + message.message));
        }
      } catch (error) {
        reject(error);
      }
    });

    ws.on("error", reject);
    ws.on("close", () => {
      console.log("[auto-token] WebSocket closed");
    });
  });
}

function updateCredentialsFile(token) {
  console.log("[auto-token] Updating credentials file...");

  let content = "";
  if (fs.existsSync(CREDENTIALS_FILE)) {
    content = fs.readFileSync(CREDENTIALS_FILE, "utf8");
  }

  if (content.includes("LONG_LIVED_ACCESS_TOKEN=")) {
    content = content.replace(
      /LONG_LIVED_ACCESS_TOKEN=.*/g,
      `LONG_LIVED_ACCESS_TOKEN=${token}`,
    );
  } else {
    content += `\nLONG_LIVED_ACCESS_TOKEN=${token}\n`;
  }

  fs.writeFileSync(CREDENTIALS_FILE, content);
  console.log("[auto-token] Credentials file updated");
}

// Run the automated token creation
createTokenFullyAutomated()
  .then((token) => {
    console.log(
      "[auto-token] ✅ Success! Token:",
      token.substring(0, 50) + "...",
    );
    process.exit(0);
  })
  .catch((error) => {
    console.error("[auto-token] ❌ Error:", error.message);
    process.exit(1);
  });
```

### Step 2: Update Setup Script

Modify `scripts/setup-fresh-ha.sh` to use the automated token creation.

### Step 3: Test End-to-End

```bash
# Test the automated token creation
cd /workspaces/hass-addons
source hass-credentials.env
node scripts/create-token-automated.js

# Test the full setup script
./scripts/setup-fresh-ha.sh
```

## Benefits

✅ **Fully automated** - No manual intervention required
✅ **Uses legitimate auth** - Real username/password login
✅ **Creates proper tokens** - Uses official WebSocket API
✅ **Integrates seamlessly** - Works with existing setup script
✅ **Handles errors gracefully** - Falls back to manual instructions

## Error Handling

- **Browser automation fails** → Fall back to manual token creation instructions
- **WebSocket fails** → Log error and continue without MQTT setup
- **Token validation fails** → Retry or fall back to manual process

## Testing Plan

1. **Fresh HA instance** → Should work automatically
2. **Already onboarded HA** → Should create token automatically
3. **Invalid credentials** → Should fail gracefully with instructions
4. **Network issues** → Should handle timeouts and retries

---

**Status:** 📋 Ready for Implementation
**Priority:** HIGH
**Estimated Time:** 2-3 hours
