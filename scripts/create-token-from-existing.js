#!/usr/bin/env node
/**
 * Create Home Assistant long-lived access token from existing token via WebSocket API
 * This script uses an existing token (e.g., from onboarding) to bootstrap creation of a long-lived token
 */

const WebSocket = require("ws");

const HA_URL = process.env.HA_URL || "http://localhost:8123";
const WS_URL = HA_URL.replace("http", "ws") + "/api/websocket";
const EXISTING_TOKEN =
  process.env.EXISTING_TOKEN || process.env.ONBOARDING_TOKEN;
const TOKEN_NAME =
  process.env.TOKEN_NAME || `Setup Script ${new Date().toISOString()}`;

async function validateToken(token) {
  console.log("[token-bootstrap] Validating existing token...");
  try {
    const response = await fetch(`${HA_URL}/api/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      console.log("[token-bootstrap] ✅ Token is valid");
      return true;
    } else {
      console.error(
        `[token-bootstrap] ❌ Token validation failed: HTTP ${response.status}`,
      );
      return false;
    }
  } catch (error) {
    console.error(
      `[token-bootstrap] ❌ Token validation error: ${error.message}`,
    );
    return false;
  }
}

async function createLongLivedToken() {
  if (!EXISTING_TOKEN) {
    console.error(
      "[token-bootstrap] ❌ EXISTING_TOKEN or ONBOARDING_TOKEN environment variable is required",
    );
    process.exit(1);
  }

  console.log(
    "[token-bootstrap] Starting long-lived token creation from existing token...",
  );

  // Validate the existing token first
  const isValid = await validateToken(EXISTING_TOKEN);
  if (!isValid) {
    console.error(
      "[token-bootstrap] ❌ Existing token is invalid or expired, cannot proceed",
    );
    process.exit(1);
  }

  return new Promise((resolve, reject) => {
    const ws = new WebSocket(WS_URL);
    let messageId = 1;
    let retryCount = 0;
    const maxRetries = 3;

    ws.on("open", () => {
      console.log("[token-bootstrap] Connected to Home Assistant WebSocket");
    });

    ws.on("message", async (data) => {
      try {
        const message = JSON.parse(data);
        console.log("[token-bootstrap] Received:", message.type);

        if (message.type === "auth_required") {
          console.log(
            "[token-bootstrap] Authentication required, using existing token...",
          );

          // Send authentication with existing token
          const authRequest = {
            type: "auth",
            access_token: EXISTING_TOKEN,
          };
          console.log(
            "[token-bootstrap] Sending auth request with existing token",
          );
          ws.send(JSON.stringify(authRequest));
        } else if (message.type === "auth_ok") {
          console.log("[token-bootstrap] Authenticated successfully!");
          console.log("[token-bootstrap] Creating long-lived access token...");

          // Request long-lived token
          const requestId = messageId++;
          const tokenRequest = {
            id: requestId,
            type: "auth/long_lived_access_token",
            client_name: TOKEN_NAME,
            lifespan: 3650, // 10 years
          };
          console.log(
            "[token-bootstrap] Sending token request:",
            JSON.stringify(tokenRequest, null, 2),
          );
          ws.send(JSON.stringify(tokenRequest));
        } else if (message.type === "result" && message.success) {
          console.log("[token-bootstrap] ✅ Long-lived token created!");
          console.log(
            "[token-bootstrap] Token:",
            message.result.substring(0, 50) + "...",
          );

          ws.close();
          resolve(message.result);
        } else if (message.type === "result" && !message.success) {
          console.error(
            "[token-bootstrap] Failed to create long-lived token:",
            JSON.stringify(message),
          );

          // If it's an unknown error, try waiting a bit more and retry
          if (message.error && message.error.code === "unknown_error") {
            retryCount++;
            if (retryCount <= maxRetries) {
              console.log(
                `[token-bootstrap] Unknown error, retrying... (${retryCount}/${maxRetries})`,
              );
              console.log(
                `[token-bootstrap] Error details:`,
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
                "[token-bootstrap] Sending retry request:",
                JSON.stringify(retryRequest, null, 2),
              );
              ws.send(JSON.stringify(retryRequest));
              return;
            } else {
              console.error(
                `[token-bootstrap] Max retries (${maxRetries}) exceeded for unknown_error`,
              );
              console.error(
                `[token-bootstrap] Error details:`,
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
          reject(
            new Error(
              `Authentication failed: ${message.message}. The existing token may be invalid or expired.`,
            ),
          );
        }
      } catch (error) {
        console.error("[token-bootstrap] Error parsing message:", error);
        reject(error);
      }
    });

    ws.on("error", (error) => {
      console.error("[token-bootstrap] WebSocket error:", error);
      reject(error);
    });

    ws.on("close", () => {
      console.log("[token-bootstrap] WebSocket connection closed");
    });
  });
}

// Add fetch polyfill for Node.js
if (typeof fetch === "undefined") {
  global.fetch = require("node-fetch");
}

createLongLivedToken()
  .then((token) => {
    console.log("[token-bootstrap] ✅ Done! Long-lived token created.");
    console.log("[token-bootstrap] Full token:", token);
    process.exit(0);
  })
  .catch((error) => {
    console.error("[token-bootstrap] ❌ Error:", error.message);
    process.exit(1);
  });
