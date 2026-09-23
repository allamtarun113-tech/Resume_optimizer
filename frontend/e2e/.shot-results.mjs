import { chromium } from "@playwright/test";
import { config } from "dotenv";
config({ path: ".env.e2e.local" });
const OUT =
  "/private/tmp/claude-501/-Users-allamtharun-Desktop-Resume-optimizer/2ea338f1-dcff-455f-87b6-2717a971584d/scratchpad/shots";
const BASE = process.env.SHOT_BASE ?? "http://localhost:3000";
const ID = process.argv[2];
const PREFIX = process.argv[3] ?? "r";
const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 1360, height: 900 },
});
const page = await ctx.newPage();
await page.goto(BASE + "/login");
await page.getByLabel("Email").fill(process.env.E2E_EMAIL);
await page.getByLabel("Password").fill(process.env.E2E_PASSWORD);
await page
  .getByRole("main")
  .getByRole("button", { name: "Sign in", exact: true })
  .click();
await page.getByText("Recent analyses").waitFor();
await page.goto(`${BASE}/analysis/${ID}`);
await page
  .getByRole("img", { name: /Job fit/ })
  .first()
  .waitFor({ timeout: 90000 });
const shot = async (n) => {
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${PREFIX}-${n}.png`, fullPage: true });
  console.log("shot", n);
};
await shot("overview");
await page.getByRole("button", { name: "How was my score calculated?" }).click();
await page.getByRole("region", { name: "Explanation" }).first().waitFor({ timeout: 60000 });
await page.getByRole("button", { name: "Explain", exact: true }).first().click();
await page.getByRole("region", { name: "Explanation" }).nth(1).waitFor({ timeout: 60000 });
await shot("overview-explained");
for (const [tab, n] of [
  [/Improve resume/, "improve"],
  [/Learn/, "learn"],
]) {
  await page.getByRole("tab", { name: tab }).click();
  await shot(n);
}
await browser.close();
