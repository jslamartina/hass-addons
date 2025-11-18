#!/usr/bin/env node
/**
 * Create Home Assistant long-lived access token via WebSocket API
 * This is the "legitimate" way to create tokens programmatically
 */

const fs = require("fs");
const path = require("path");
const WebSocket = require("ws");

const HA_URL = process.env.HA_URL || "http://localhost:8123";
const WS_URL = HA_URL.replace("http", "ws") + "/api/websocket";
const USERNAME = process.env.HASS_USERNAME || "dev";
const PASSWORD = process.env.HASS_PASSWORD || "dev";
const TOKEN_NAME =
  process.env.TOKEN_NAME || `Setup Script ${new Date().toISOString()}`;
const TOKEN_OUTPUT_FILE =
  process.env.TOKEN_OUTPUT_FILE ||
  path.resolve(process.cwd(), "long_lived_access_token.txt");

function logSensitiveAction(message, meta = "") {
  const suffix = meta ? ` ${meta}` : "";
  console.log(`[websocket-token] ${message}${suffix}`);
}

function persistTokenToFile(token) {
  try {
    fs.writeFileSync(TOKEN_OUTPUT_FILE, token, { mode: 0o600 });
    fs.chmodSync(TOKEN_OUTPUT_FILE, 0o600);
    console.log(
      `[websocket-token] Token securely stored at ${TOKEN_OUTPUT_FILE}`,
    );
  } catch (error) {
    console.error(
      "[websocket-token] Failed to persist token to file:",
      error.message,
    );
    throw error;
  }
}

async function createToken() {
  console.log("[websocket-token] Starting WebSocket token creation...");

  return new Promise((resolve, reject) => {
    const ws = new WebSocket(WS_URL);
    let messageId = 1;
    let retryCount = 0;
    const maxRetries = 3;

    ws.on("open", () => {
      console.log("[websocket-token] Connected to Home Assistant WebSocket");
    });

    ws.on("message", async (data) => {
      try {
        const message = JSON.parse(data);
        console.log("[websocket-token] Received:", message.type);

        if (message.type === "auth_required") {
          console.log(
            "[websocket-token] Authentication required, logging in...",
          );

          // First, we need to get an access token via HTTP login
          const accessToken = await getAccessTokenViaLogin();
          if (!accessToken) {
            reject(new Error("Failed to get access token via login"));
            return;
          }

          // Send authentication
          const authRequest = {
            type: "auth",
            access_token: accessToken,
          };
          logSensitiveAction(
            "Sending auth request with redacted token.",
            `(length=${authRequest.access_token.length})`,
          );
          ws.send(JSON.stringify(authRequest));
        } else if (message.type === "auth_ok") {
          console.log("[websocket-token] Authenticated successfully!");
          console.log("[websocket-token] Creating long-lived access token...");

          // Request long-lived token
          const requestId = messageId++;
          const tokenRequest = {
            id: requestId,
            type: "auth/long_lived_access_token",
            client_name: TOKEN_NAME,
            lifespan: 3650, // 10 years
          };
          console.log(
            "[websocket-token] Sending token request:",
            JSON.stringify(tokenRequest, null, 2),
          );
          ws.send(JSON.stringify(tokenRequest));
        } else if (message.type === "result" && message.success) {
          console.log("[websocket-token] ✅ Long-lived token created!");
          logSensitiveAction(
            "Token generated (value redacted).",
            `(length=${message.result.length})`,
          );

          ws.close();
          resolve(message.result);
        } else if (message.type === "result" && !message.success) {
          console.error(
            "[websocket-token] Failed to create long-lived token:",
            JSON.stringify(message),
          );

          // If it's an unknown error, try waiting a bit more and retry
          if (message.error && message.error.code === "unknown_error") {
            retryCount++;
            if (retryCount <= maxRetries) {
              console.log(
                `[websocket-token] Unknown error, retrying... (${retryCount}/${maxRetries})`,
              );
              console.log(
                `[websocket-token] Error details:`,
                JSON.stringify(message.error, null, 2),
              );
              await new Promise((resolve) => setTimeout(resolve, 3000));

              // Retry the token creation
              const retryRequestId = messageId++;
              const retryRequest = {
                id: retryRequestId,
                type: "auth/long_lived_access_token",
                client_name: TOKEN_NAME,
                lifespan: 3650,
              };
              console.log(
                "[websocket-token] Sending retry request:",
                JSON.stringify(retryRequest, null, 2),
              );
              ws.send(JSON.stringify(retryRequest));
              return;
            } else {
              console.error(
                `[websocket-token] Max retries (${maxRetries}) exceeded for unknown_error`,
              );
              console.error(
                `[websocket-token] Error details:`,
                JSON.stringify(message.error, null, 2),
              );
              reject(
                new Error(
                  `Failed to create token after ${maxRetries} retries. Error: ${message.error?.message || "Unknown error"} (Code: ${message.error?.code || "unknown"})`,
                ),
              );
              return;
            }
          }

          reject(
            new Error("Failed to create token: " + JSON.stringify(message)),
          );
        } else if (message.type === "auth_invalid") {
          reject(new Error("Authentication failed: " + message.message));
        }
      } catch (error) {
        console.error("[websocket-token] Error parsing message:", error);
        reject(error);
      }
    });

    ws.on("error", (error) => {
      console.error("[websocket-token] WebSocket error:", error);
      reject(error);
    });

    ws.on("close", () => {
      console.log("[websocket-token] WebSocket connection closed");
    });
  });
}

async function getAccessTokenViaLogin() {
  console.log("[websocket-token] Getting access token via HTTP login...");
  return await getAccessTokenViaRegularLogin();
}

async function getAccessTokenViaRegularLogin() {
  console.log("[websocket-token] Trying regular login flow...");

  // Try the login flow
  const loginFlowRequest = {
    client_id: HA_URL + "/",
    handler: ["homeassistant", null],
    redirect_uri: HA_URL + "/",
  };
  console.log("[websocket-token] Sending login flow request.");

  const response = await fetch(`${HA_URL}/auth/login_flow`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(loginFlowRequest),
  });

  if (!response.ok) {
    console.error(
      "[websocket-token] Failed to initiate login flow:",
      response.status,
    );
    return null;
  }

  const flowData = await response.json();
  console.log("[websocket-token] Login flow initiated.");

  // Submit credentials
  const credentialRequest = {
    client_id: HA_URL + "/",
    username: USERNAME,
    password: PASSWORD,
  };
  logSensitiveAction(
    "Sending credentials request with password redacted.",
  );

  const submitResponse = await fetch(
    `${HA_URL}/auth/login_flow/${flowData.flow_id}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(credentialRequest),
    },
  );

  if (!submitResponse.ok) {
    console.error(
      "[websocket-token] Failed to submit credentials:",
      submitResponse.status,
    );
    return null;
  }

  const result = await submitResponse.json();
  console.log("[websocket-token] Login result:", result.result);

  // The result is an auth code that needs to be exchanged for an access token
  if (result.type === "create_entry" && result.result) {
    console.log(
      "[websocket-token] Got auth code, exchanging for access token...",
    );

    // Exchange auth code for access token
    const tokenExchangeParams = {
      grant_type: "authorization_code",
      code: result.result,
      client_id: HA_URL + "/",
    };
    logSensitiveAction(
      "Sending token exchange request with authorization code redacted.",
    );

    const tokenResponse = await fetch(`${HA_URL}/auth/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: new URLSearchParams(tokenExchangeParams),
    });

    if (!tokenResponse.ok) {
      console.error(
        "[websocket-token] Failed to exchange auth code:",
        tokenResponse.status,
      );
      return null;
    }

    const tokenData = await tokenResponse.json();
    console.log(
      "[websocket-token] Successfully exchanged auth code for access token",
    );
    return tokenData.access_token;
  }

  if (result.result === "ok" && result.result_data) {
    return result.result_data.access_token;
  }

  return null;
}

// Add fetch polyfill for Node.js
if (typeof fetch === "undefined") {
  global.fetch = require("node-fetch");
}

createToken()
  .then((token) => {
    persistTokenToFile(token);
    console.log("[websocket-token] ✅ Done! Token available on disk.");
    process.exit(0);
  })
  .catch((error) => {
    console.error("[websocket-token] ❌ Error:", error.message);
    process.exit(1);
  });
