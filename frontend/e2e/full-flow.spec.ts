import path from "node:path";
import { expect, test } from "@playwright/test";

// End-to-end on the deployed site: sign in, analyze, prepare for the interview, export,
// then delete the analysis again. Inputs are fixed, so repeat runs are LLM cache hits.

const JOB_DESCRIPTION = `Backend Engineer (New Grad)
Requirements:
- Strong Python and FastAPI
- Experience with PostgreSQL and REST API design
- Familiarity with Docker and Kubernetes
Nice to have: AWS, Redis
- Good communication skills`;

const NOTES =
  "I containerized the Campus Food Ordering App with Docker and deployed it on a 3-node k3s cluster.";

test("student analyses a job end to end", async ({ page }) => {
  const email = process.env.E2E_EMAIL;
  const password = process.env.E2E_PASSWORD;
  test.skip(!email || !password, "E2E_EMAIL / E2E_PASSWORD not set");

  // Sign in.
  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText(`Signed in as ${email}`)).toBeVisible();

  // Start an analysis.
  await page.goto("/analyze");
  await page
    .getByLabel("Resume")
    .setInputFiles(path.join(__dirname, "fixtures", "resume.pdf"));
  await page.getByLabel("Job description").fill(JOB_DESCRIPTION);
  await page.getByLabel("Additional skills or experience").fill(NOTES);
  await page.getByRole("button", { name: "Analyze" }).click();
  await page.waitForURL(/\/analysis\/[0-9a-f-]{36}$/, { timeout: 120_000 });
  const analysisId = page.url().split("/").pop()!;

  // Results: score, suggestions backed by the notes, the breakdown.
  await expect(page.getByText("Done", { exact: true })).toBeVisible({
    timeout: 180_000,
  });
  await expect(
    page.getByRole("img", { name: /Job fit \(resume\): \d+%/ }),
  ).toBeVisible();
  await expect(
    page.getByText("Already have it? Add it to your resume"),
  ).toBeVisible();
  await expect(page.getByText("Requirement by requirement")).toBeVisible();

  // Interview preparation: grouped questions, every one with a source.
  await page.getByRole("button", { name: "Prepare Me for Interview" }).click();
  await expect(
    page.getByRole("heading", { name: "Interview preparation" }),
  ).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Your projects, in depth")).toBeVisible();
  await expect(page.getByText("Technical, for this job")).toBeVisible();
  const sourced = page.getByText(
    /Project deep-dive template|\((MIT|Apache-2\.0|CC0-1\.0|CC-BY-4\.0|Unlicense)\)/,
  );
  expect(await sourced.count()).toBeGreaterThan(10);

  // Export.
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download report (.md)" }).click();
  expect((await download).suggestedFilename()).toMatch(
    /^resume-optimizer-.*\.md$/,
  );

  // History lists it; delete it to clean up.
  await page.goto("/history");
  const row = page.getByRole("listitem").filter({
    has: page.locator(`a[href="/analysis/${analysisId}"]`),
  });
  await expect(row).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(row).toHaveCount(0);
});
