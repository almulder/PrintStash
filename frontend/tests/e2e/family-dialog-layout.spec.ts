/** Long library paths must stay inside the Family creation dialog at supported widths. */
import { expect, test } from "@playwright/test";
import { aModelListItem } from "../../src/test-support/factories";
import { useMockApi } from "./_setup";

useMockApi();

for (const viewport of [
  { width: 928, height: 916 },
  { width: 390, height: 844 },
]) {
  test(`keeps the Family picker inside the dialog at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize({ width: 928, height: viewport.height });
    const collection =
      "printstash-data/printstash-data/house/garden/stackable-vertical-garden-planter";
    const models = [
      aModelListItem({ id: 101, name: "6in-build-tray", collection }),
      aModelListItem({ id: 102, name: "8in-build-tray", collection }),
    ];
    await page.route("**/api/v1/models/page**", (route) =>
      route.fulfill({ json: { items: models, next_cursor: null, total: models.length } }),
    );

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page
      .getByRole("button", { name: "Library tools" })
      .evaluate((button: HTMLButtonElement) => button.click());
    await page
      .getByRole("button", { name: "Create Family", exact: true })
      .evaluate((button: HTMLButtonElement) => button.click());
    const dialog = page.getByRole("dialog", { name: "Create Family" });
    await page.setViewportSize(viewport);
    await dialog
      .getByRole("checkbox", { name: "Select 6in-build-tray" })
      .evaluate((button: HTMLButtonElement) => button.click());
    await dialog
      .getByRole("checkbox", { name: "Select 8in-build-tray" })
      .evaluate((button: HTMLButtonElement) => button.click());
    await expect(dialog.getByRole("radio", { name: "8in-build-tray" })).toBeVisible();

    const bounds = await dialog.evaluate((element) => {
      const dialogRight = element.getBoundingClientRect().right;
      const pickerRight = element
        .querySelector('input[placeholder="Search your library…"]')
        ?.getBoundingClientRect().right;
      const selectedRight = element
        .querySelector('input[type="radio"]')
        ?.closest(".max-h-48")
        ?.getBoundingClientRect().right;
      return { dialogRight, pickerRight, selectedRight };
    });
    expect(bounds.pickerRight).toBeDefined();
    expect(bounds.selectedRight).toBeDefined();
    expect(bounds.pickerRight!).toBeLessThanOrEqual(bounds.dialogRight);
    expect(bounds.selectedRight!).toBeLessThanOrEqual(bounds.dialogRight);
  });
}
