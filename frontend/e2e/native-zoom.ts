import { writeFileSync } from "node:fs";
import type { Page } from "@playwright/test";

/** Chromium screenshot clips use device-independent pixels while native zoom changes CSS pixels.
 * Capture the real window without a CSS-sized clip, which otherwise crops high-zoom evidence.
 */
export async function captureNativeWindow(page: Page, path: string) {
  const session = await page.context().newCDPSession(page);
  try {
    const result = await session.send("Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: false,
    });
    writeFileSync(path, Buffer.from(result.data, "base64"));
  } finally {
    await session.detach();
  }
}
