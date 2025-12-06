/**
 * Onboarding WebSocket Reverse Engineering Script
 *
 * Automates Home Assistant onboarding flow while capturing all WebSocket messages
 * for reverse engineering analysis.
 */

import { test, expect, Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const BASE_URL = process.env.HA_BASE_URL || "http://localhost:8123";
const USERNAME = process.env.HA_USERNAME || "dev";
const PASSWORD = process.env.HA_PASSWORD || "dev";

interface WebSocketMessage {
  timestamp: string;
  direction: "sent" | "received";
  step: string;
  message: any;
  raw: string;
}

interface NetworkRequest {
  timestamp: string;
  step: string;
  method: string;
  url: string;
  status?: number;
  requestHeaders?: Record<string, string>;
  responseHeaders?: Record<string, string>;
  requestBody?: any;
  responseBody?: any;
}

class OnboardingTracer {
  private page: Page;
  private wsMessages: WebSocketMessage[] = [];
  private networkRequests: NetworkRequest[] = [];
  private currentStep: string = "unknown";
  private outputDir: string;
  private screenshotsDir: string;

  constructor(page: Page) {
    this.page = page;
    this.outputDir = path.join(process.cwd(), "test-results");
    this.screenshotsDir = path.join(
      this.outputDir,
      "onboarding-steps-screenshots",
    );

    // Ensure output directories exist
    if (!fs.existsSync(this.outputDir)) {
      fs.mkdirSync(this.outputDir, { recursive: true });
    }
    if (!fs.existsSync(this.screenshotsDir)) {
      fs.mkdirSync(this.screenshotsDir, { recursive: true });
    }
  }

  /**
   * Set up WebSocket monitoring
   */
  setupWebSocketMonitoring(): void {
    this.page.on("websocket", (ws) => {
      console.log(`[WebSocket] Opened: ${ws.url()}`);

      ws.on("framesent", (event) => {
        this.logWebSocketMessage("sent", event.payload);
      });

      ws.on("framereceived", (event) => {
        this.logWebSocketMessage("received", event.payload);
      });

      ws.on("close", () => {
        console.log(`[WebSocket] Closed: ${ws.url()}`);
      });

      ws.on("socketerror", (error) => {
        console.error(`[WebSocket] Error: ${error}`);
      });
    });
  }

  /**
   * Set up network request monitoring
   */
  setupNetworkMonitoring(): void {
    this.page.on("request", (request) => {
      const url = request.url();
      // Only capture API and onboarding-related requests
      if (url.includes("/api/") || url.includes("/onboarding")) {
        request.allHeaders().then((headers) => {
          const networkReq: NetworkRequest = {
            timestamp: new Date().toISOString(),
            step: this.currentStep,
            method: request.method(),
            url: url,
            requestHeaders: headers,
          };

          // Capture request body if available
          const postData = request.postDataJSON();
          if (postData) {
            Promise.resolve(postData)
              .then((body: any) => {
                networkReq.requestBody = body;
              })
              .catch(() => {
                // Ignore if not JSON or no body
              });
          }

          this.networkRequests.push(networkReq);
        });
      }
    });

    this.page.on("response", async (response) => {
      const url = response.url();
      if (url.includes("/api/") || url.includes("/onboarding")) {
        // Find the most recent matching request without status
        const matchingRequest = [...this.networkRequests]
          .reverse()
          .find((req) => req.url === url && !req.status);

        if (matchingRequest) {
          matchingRequest.status = response.status();

          // Capture response headers
          try {
            const headers = await response.allHeaders();
            matchingRequest.responseHeaders = headers;
          } catch (error) {
            // Ignore if headers unavailable
          }

          // Capture response body if available
          try {
            const body = await response.json();
            matchingRequest.responseBody = body;
          } catch (error) {
            // Ignore if not JSON
          }
        }
      }
    });
  }

  /**
   * Log a WebSocket message with structured format
   */
  private logWebSocketMessage(
    direction: "sent" | "received",
    payload: string | Buffer,
  ): void {
    const raw =
      typeof payload === "string"
        ? payload
        : Buffer.isBuffer(payload)
          ? payload.toString()
          : String(payload);
    let message: any;

    try {
      message = JSON.parse(raw);
    } catch (e) {
      // Not JSON, keep as string
      message = raw;
    }

    const wsMessage: WebSocketMessage = {
      timestamp: new Date().toISOString(),
      direction,
      step: this.currentStep,
      message,
      raw,
    };

    this.wsMessages.push(wsMessage);
    console.log(
      `[WS ${direction.toUpperCase()}] [${this.currentStep}] ${JSON.stringify(message).substring(0, 100)}...`,
    );
  }

  /**
   * Update current step context
   */
  setStep(step: string): void {
    this.currentStep = step;
    console.log(`[Step] Current step: ${step}`);
  }

  /**
   * Take a screenshot of the current UI state
   */
  async takeScreenshot(stepName: string): Promise<void> {
    const filename = `${Date.now()}-${stepName}.png`;
    const filepath = path.join(this.screenshotsDir, filename);
    await this.page.screenshot({ path: filepath, fullPage: true });
    console.log(`[Screenshot] Saved: ${filepath}`);
  }

  /**
   * Save all captured data to files
   */
  async saveTraceFiles(): Promise<void> {
    // Save WebSocket messages
    const wsTracePath = path.join(
      this.outputDir,
      "onboarding-websocket-trace.json",
    );
    fs.writeFileSync(
      wsTracePath,
      JSON.stringify(this.wsMessages, null, 2),
      "utf-8",
    );
    console.log(`[Trace] WebSocket messages saved: ${wsTracePath}`);

    // Save network requests
    const networkTracePath = path.join(
      this.outputDir,
      "onboarding-network-requests.json",
    );
    fs.writeFileSync(
      networkTracePath,
      JSON.stringify(this.networkRequests, null, 2),
      "utf-8",
    );
    console.log(`[Trace] Network requests saved: ${networkTracePath}`);

    // Summary
    console.log(`\n[Summary]`);
    console.log(`  WebSocket messages: ${this.wsMessages.length}`);
    console.log(`  Network requests: ${this.networkRequests.length}`);
    console.log(`  Screenshots: ${this.screenshotsDir}`);
  }
}

/**
 * Detect current onboarding step from the UI and API
 */
async function detectCurrentStep(page: Page): Promise<string> {
  try {
    // First, try to get from API (most reliable)
    try {
      const response = await page.request.get(`${BASE_URL}/api/onboarding`);
      if (response.ok()) {
        const data = await response.json();
        const incompleteSteps = data.filter((step: any) => !step.done);
        if (incompleteSteps.length > 0) {
          console.log(
            `[Detection] API detected incomplete step: ${incompleteSteps[0].step}`,
          );
          return incompleteSteps[0].step;
        } else {
          // All steps complete
          return "complete";
        }
      }
    } catch (apiError) {
      // API might not be available, continue with UI detection
      console.log("[Detection] API not available, using UI detection");
    }

    // UI-based detection fallback
    // Check for location picker step
    const locationIndicators = [
      /pick.*location/i,
      /select.*location/i,
      /where.*are.*you/i,
      /set.*location/i,
    ];

    for (const indicator of locationIndicators) {
      const visible = await page
        .getByText(indicator)
        .isVisible({ timeout: 1000 })
        .catch(() => false);
      if (visible) {
        console.log(
          `[Detection] UI detected: core_config (matched: ${indicator})`,
        );
        return "core_config";
      }
    }

    // Check for analytics step
    const analyticsIndicators = [
      /analytics/i,
      /help.*improve/i,
      /usage.*data/i,
      /share.*data/i,
    ];

    for (const indicator of analyticsIndicators) {
      const visible = await page
        .getByText(indicator)
        .isVisible({ timeout: 1000 })
        .catch(() => false);
      if (visible) {
        console.log(
          `[Detection] UI detected: analytics (matched: ${indicator})`,
        );
        return "analytics";
      }
    }

    // Check for user creation step
    const userIndicators = [
      /create.*account/i,
      /create.*user/i,
      /sign.*up/i,
      /username/i,
    ];

    for (const indicator of userIndicators) {
      const visible = await page
        .getByText(indicator)
        .isVisible({ timeout: 1000 })
        .catch(() => false);
      if (visible) {
        console.log(`[Detection] UI detected: user (matched: ${indicator})`);
        return "user";
      }
    }

    // Check if onboarding is complete (on dashboard)
    const currentUrl = page.url();
    if (
      currentUrl.includes("/lovelace") ||
      currentUrl.includes("/config") ||
      currentUrl.includes("/dashboard")
    ) {
      console.log("[Detection] UI detected: complete (on dashboard)");
      return "complete";
    }

    // Check for onboarding URLs
    if (currentUrl.includes("/onboarding")) {
      console.log("[Detection] URL indicates onboarding in progress");
      return "onboarding";
    }
  } catch (error) {
    console.warn(`[Detection] Error detecting step: ${error}`);
  }

  console.log("[Detection] Could not detect step, returning 'unknown'");
  return "unknown";
}

/**
 * Get all available onboarding steps from API
 */
async function getAvailableSteps(
  page: Page,
): Promise<Array<{ step: string; done: boolean }>> {
  try {
    const response = await page.request.get(`${BASE_URL}/api/onboarding`);
    if (response.ok()) {
      const data = await response.json();
      return data;
    }
  } catch (error) {
    console.warn(`[Steps] Failed to get available steps: ${error}`);
  }
  return [];
}

/**
 * Retry an operation with exponential backoff
 */
async function retryWithBackoff<T>(
  operation: () => Promise<T>,
  maxRetries: number = 3,
  initialDelay: number = 1000,
  description: string = "Operation",
): Promise<T> {
  let lastError: Error | unknown;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (attempt < maxRetries - 1) {
        const delay = initialDelay * Math.pow(2, attempt);
        console.warn(
          `[Retry] ${description} failed (attempt ${attempt + 1}/${maxRetries}), retrying in ${delay}ms...`,
        );
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError;
}

/**
 * Wait for element to be actionable with timeout
 */
async function waitForActionable(
  page: Page,
  locator: any,
  timeout: number = 10000,
): Promise<boolean> {
  try {
    await locator.waitFor({ state: "visible", timeout });
    await locator.waitFor({ state: "attached", timeout });
    return true;
  } catch (error) {
    return false;
  }
}

/**
 * Safe click with retry
 */
async function safeClick(
  page: Page,
  locator: any,
  timeout: number = 5000,
  description: string = "Element",
): Promise<boolean> {
  try {
    if (await waitForActionable(page, locator, timeout)) {
      await locator.click({ timeout: 5000 });
      return true;
    }
    return false;
  } catch (error) {
    console.warn(`[Click] Failed to click ${description}: ${error}`);
    return false;
  }
}

test.describe("Onboarding WebSocket Trace", () => {
  test.setTimeout(120000); // 2 minutes for full onboarding

  test("trace onboarding process and capture WebSocket messages", async ({
    page,
  }) => {
    // Increase timeout for this specific test
    test.setTimeout(180000); // 3 minutes

    let errorOccurred = false;
    let errorMessage = "";
    const tracer = new OnboardingTracer(page);

    try {
      // Set up monitoring
      tracer.setupWebSocketMonitoring();
      tracer.setupNetworkMonitoring();

      // Navigate to Home Assistant
      console.log(`[Navigate] Going to ${BASE_URL}`);
      await page.goto(BASE_URL);

      // Wait for page to load
      await page.waitForLoadState("networkidle");

      // Detect current step
      const initialStep = await detectCurrentStep(page);
      tracer.setStep(initialStep);
      await tracer.takeScreenshot(`initial-${initialStep}`);

      // Check if already logged in or at onboarding
      const isLoginPage = await page
        .getByRole("textbox", { name: /username/i })
        .isVisible({ timeout: 2000 })
        .catch(() => false);

      if (isLoginPage) {
        console.log("[Login] Logging in...");
        tracer.setStep("login");

        await page.getByRole("textbox", { name: /username/i }).fill(USERNAME);
        await page.getByRole("textbox", { name: /password/i }).fill(PASSWORD);
        await page.getByRole("button", { name: /log in|sign in/i }).click();

        // Wait for navigation after login
        await page.waitForURL(/onboarding|lovelace|config/, { timeout: 10000 });

        await tracer.takeScreenshot("after-login");
        await page.waitForTimeout(2000); // Wait for WebSocket connections

        // Re-detect step after login
        const stepAfterLogin = await detectCurrentStep(page);
        tracer.setStep(stepAfterLogin);
      }

      // Handle core_config step (location picker)
      if (tracer["currentStep"] === "core_config") {
        console.log("[Step] Handling core_config (location picker)");
        await tracer.takeScreenshot("core_config-before");

        // Wait for the onboarding UI to be ready
        await page.waitForTimeout(2000);

        // Wait for onboarding location component or map to be visible
        await page.waitForLoadState("load");
        await page.waitForTimeout(1000); // Allow time for network requests

        // Try multiple strategies to interact with location picker
        let locationSet = false;

        // Strategy 1: Click on map element (shadow DOM safe via role/label)
        try {
          const mapContainer = page.locator("ha-onboarding-location").first();
          if (await mapContainer.isVisible({ timeout: 3000 })) {
            console.log("[Location] Found ha-onboarding-location component");

            // Click somewhere in the center of the map (approximately Chicago)
            const mapBox = await mapContainer.boundingBox();
            if (mapBox) {
              // Click near center of map (slightly to the left for US)
              const clickX = mapBox.x + mapBox.width * 0.25;
              const clickY = mapBox.y + mapBox.height * 0.5;
              await page.mouse.click(clickX, clickY);
              console.log("[Location] Clicked on map");
              locationSet = true;
              await page.waitForTimeout(500);
            }
          }
        } catch (error) {
          console.warn(`[Location] Strategy 1 failed: ${error}`);
        }

        // Strategy 2: Look for latitude/longitude input fields
        if (!locationSet) {
          try {
            const latInput = page
              .getByLabel(/latitude/i)
              .or(page.getByPlaceholder(/latitude/i));
            const lonInput = page
              .getByLabel(/longitude/i)
              .or(page.getByPlaceholder(/longitude/i));

            if (
              await latInput.isVisible({ timeout: 2000 }).catch(() => false)
            ) {
              console.log("[Location] Found latitude/longitude inputs");
              await latInput.fill("41.8781");
              await lonInput.fill("-87.6298");
              locationSet = true;
              await page.waitForTimeout(500);
            }
          } catch (error) {
            console.warn(`[Location] Strategy 2 failed: ${error}`);
          }
        }

        // Strategy 3: Use location search/autocomplete
        if (!locationSet) {
          try {
            const searchInput = page
              .getByPlaceholder(/search.*location|city/i)
              .or(page.getByRole("textbox", { name: /location|city/i }));

            if (
              await searchInput.isVisible({ timeout: 2000 }).catch(() => false)
            ) {
              console.log("[Location] Found location search input");
              await searchInput.fill("Chicago");
              await page.waitForTimeout(1000);

              // Click on first suggestion
              const suggestion = page.getByRole("option").first();
              if (
                await suggestion.isVisible({ timeout: 2000 }).catch(() => false)
              ) {
                await suggestion.click();
                locationSet = true;
              }
            }
          } catch (error) {
            console.warn(`[Location] Strategy 3 failed: ${error}`);
          }
        }

        if (!locationSet) {
          console.warn("[Location] Could not set location automatically");
        }

        // Set timezone selector if available
        try {
          const timezoneSelectors = [
            page.getByRole("combobox", { name: /time.?zone/i }),
            page.getByLabel(/time.?zone/i),
            page
              .locator("select")
              .filter({ hasText: /time.?zone/i })
              .first(),
          ];

          for (const selector of timezoneSelectors) {
            if (
              await selector.isVisible({ timeout: 2000 }).catch(() => false)
            ) {
              console.log("[Location] Found timezone selector");
              await selector.click();
              await page.waitForTimeout(500);

              // Try to select Chicago timezone
              const chicagoOption = page
                .getByText(/america.*chicago|chicago/i)
                .first();
              if (
                await chicagoOption
                  .isVisible({ timeout: 2000 })
                  .catch(() => false)
              ) {
                await chicagoOption.click();
              } else {
                // Select first option as fallback
                const firstOption = page.getByRole("option").first();
                if (
                  await firstOption
                    .isVisible({ timeout: 1000 })
                    .catch(() => false)
                ) {
                  await firstOption.click();
                }
              }
              await page.waitForTimeout(500);
              break;
            }
          }
        } catch (error) {
          console.warn(`[Location] Timezone selection failed: ${error}`);
        }

        // Set unit system if available
        try {
          const unitSelectors = [
            page.getByRole("combobox", { name: /unit/i }),
            page.getByLabel(/unit|imperial|metric/i),
            page
              .locator("select")
              .filter({ hasText: /imperial|metric/i })
              .first(),
          ];

          for (const selector of unitSelectors) {
            if (
              await selector.isVisible({ timeout: 2000 }).catch(() => false)
            ) {
              console.log("[Location] Found unit selector");
              await selector.click();
              await page.waitForTimeout(500);

              // Try to select imperial
              const imperialOption = page.getByText(/imperial/i).first();
              if (
                await imperialOption
                  .isVisible({ timeout: 2000 })
                  .catch(() => false)
              ) {
                await imperialOption.click();
              } else {
                // Select first option as fallback
                const firstOption = page.getByRole("option").first();
                if (
                  await firstOption
                    .isVisible({ timeout: 1000 })
                    .catch(() => false)
                ) {
                  await firstOption.click();
                }
              }
              await page.waitForTimeout(500);
              break;
            }
          }
        } catch (error) {
          console.warn(`[Location] Unit selection failed: ${error}`);
        }

        // Click continue/next button
        const continueButtonSelectors = [
          page.getByRole("button", { name: /continue|next/i }),
          page.getByRole("button", { name: /save|done/i }),
          page
            .locator("mwc-button")
            .filter({ hasText: /continue|next/i })
            .first(),
          page
            .locator("ha-button")
            .filter({ hasText: /continue|next/i })
            .first(),
        ];

        let continued = false;
        for (const button of continueButtonSelectors) {
          try {
            if (await button.isVisible({ timeout: 2000 }).catch(() => false)) {
              console.log("[Location] Found continue button, clicking...");
              await button.click();
              continued = true;
              break;
            }
          } catch (error) {
            // Try next selector
          }
        }

        if (!continued) {
          console.warn("[Location] Could not find continue button");
        } else {
          // Wait for step transition
          await page.waitForTimeout(2000);
          await page.waitForLoadState("networkidle");
        }

        await tracer.takeScreenshot("core_config-after");
        await page.waitForTimeout(1000);
      }

      // Handle analytics step
      const analyticsStep = await detectCurrentStep(page);
      if (analyticsStep === "analytics") {
        tracer.setStep("analytics");
        console.log("[Step] Handling analytics step");
        await tracer.takeScreenshot("analytics-before");

        // Wait for UI to be ready
        await page.waitForTimeout(2000);
        await page.waitForLoadState("networkidle");

        // Try multiple strategies to opt-out/skip analytics
        let analyticsHandled = false;

        // Strategy 1: Look for opt-out toggle/switch
        try {
          const optOutToggle = page
            .getByRole("switch")
            .filter({ hasText: /analytics|share.*data|usage.*data/i })
            .first();
          if (
            await optOutToggle.isVisible({ timeout: 3000 }).catch(() => false)
          ) {
            const checked = await optOutToggle.isChecked().catch(() => false);
            if (checked) {
              console.log("[Analytics] Found analytics toggle, disabling...");
              await optOutToggle.click();
              analyticsHandled = true;
              await page.waitForTimeout(500);
            }
          }
        } catch (error) {
          console.warn(`[Analytics] Strategy 1 failed: ${error}`);
        }

        // Strategy 2: Look for opt-out button (no thanks, skip, etc.)
        if (!analyticsHandled) {
          const optOutButtons = [
            page.getByRole("button", { name: /no thanks|not now|decline/i }),
            page.getByRole("button", { name: /opt.?out/i }),
            page.getByRole("button", { name: /skip/i }),
          ];

          for (const button of optOutButtons) {
            if (await button.isVisible({ timeout: 2000 }).catch(() => false)) {
              console.log("[Analytics] Found opt-out button, clicking...");
              await button.click();
              analyticsHandled = true;
              await page.waitForTimeout(500);
              break;
            }
          }
        }

        // Strategy 3: Look for continue/skip button
        if (!analyticsHandled) {
          const continueButtons = [
            page.getByRole("button", { name: /continue|next/i }),
            page.getByRole("button", { name: /skip/i }),
            page
              .locator("mwc-button")
              .filter({ hasText: /continue|next|skip/i })
              .first(),
            page
              .locator("ha-button")
              .filter({ hasText: /continue|next|skip/i })
              .first(),
          ];

          for (const button of continueButtons) {
            if (await button.isVisible({ timeout: 2000 }).catch(() => false)) {
              console.log(
                "[Analytics] Found continue/skip button, clicking...",
              );
              await button.click();
              analyticsHandled = true;
              await page.waitForTimeout(500);
              break;
            }
          }
        }

        if (!analyticsHandled) {
          console.warn(
            "[Analytics] Could not find analytics opt-out option, continuing...",
          );
        } else {
          // Wait for step transition
          await page.waitForTimeout(2000);
          await page.waitForLoadState("networkidle");
        }

        await tracer.takeScreenshot("analytics-after");
        await page.waitForTimeout(1000);
      }

      // Check for any remaining steps
      const finalStep = await detectCurrentStep(page);
      tracer.setStep(finalStep);
      await tracer.takeScreenshot(`final-${finalStep}`);

      // Wait a bit more to capture any final WebSocket messages
      await page.waitForTimeout(3000);

      // Save all trace files
      await tracer.saveTraceFiles();

      console.log("\n[Complete] Onboarding trace completed!");
      console.log(`[Final Step] ${finalStep}`);
    } catch (error) {
      errorOccurred = true;
      errorMessage = error instanceof Error ? error.message : String(error);
      console.error(`\n[Error] Onboarding trace failed: ${errorMessage}`);
      console.error(error);

      // Still save trace files even on error
      try {
        await tracer.saveTraceFiles();
        console.log("[Recovery] Trace files saved despite error");
      } catch (saveError) {
        console.error(`[Error] Failed to save trace files: ${saveError}`);
      }

      // Take final screenshot for debugging
      try {
        await tracer.takeScreenshot("error-state");
      } catch (screenshotError) {
        console.error(
          `[Error] Failed to take error screenshot: ${screenshotError}`,
        );
      }
    } finally {
      // Ensure we always save trace files
      try {
        await tracer.saveTraceFiles();
      } catch (saveError) {
        console.error(`[Error] Final save attempt failed: ${saveError}`);
      }

      if (errorOccurred) {
        throw new Error(`Onboarding trace failed: ${errorMessage}`);
      }
    }
  });
});
