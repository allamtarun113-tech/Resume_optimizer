import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// End-to-end on the deployed site: sign in, make sure an OpenAI key is saved, analyze,
// prepare for the interview, export, then delete the analysis again. Inputs are fixed,
// so repeat runs are LLM cache hits.

const JOB_DESCRIPTION = `Backend Engineer (New Grad)
Requirements:
- Strong Python and FastAPI
- Experience with PostgreSQL and REST API design
- Familiarity with Docker and Kubernetes
Nice to have: AWS, Redis
- Good communication skills`;

const NOTES =
  "I containerized the Campus Food Ordering App with Docker and deployed it on a 3-node k3s cluster.";

async function ensureOpenAiKey(page: Page, apiKey: string) {
  await page.goto("/settings");
  const connected = page.getByText("Connected", { exact: true });
  const notConnected = page.getByText("Not connected", { exact: true });
  await expect(connected.or(notConnected)).toBeVisible();
  if (await connected.isVisible()) return;

  await page.getByLabel("API key").fill(apiKey);
  await page.getByRole("button", { name: "Check key" }).click();
  await expect(page.getByText(/Key works/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(connected).toBeVisible();
}

test("student analyses a job end to end", async ({ page }) => {
  const email = process.env.E2E_EMAIL;
  const password = process.env.E2E_PASSWORD;
  const apiKey = process.env.E2E_OPENAI_API_KEY;
  test.skip(!email || !password || !apiKey, "E2E_* settings not set");

  // Sign in.
  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page
    .getByRole("main")
    .getByRole("button", { name: "Sign in", exact: true })
    .click();
  await expect(page.getByText("Recent analyses")).toBeVisible();

  await ensureOpenAiKey(page, apiKey!);

  // Start an analysis.
  await page.goto("/analyze");
  await page
    .getByLabel("Drop your resume here, or click to choose")
    .setInputFiles(path.join(__dirname, "fixtures", "resume.pdf"));
  await page
    .getByLabel("Job description", { exact: true })
    .fill(JOB_DESCRIPTION);
  await page.getByLabel("Additional skills").fill("Git");
  await page.getByRole("button", { name: "Add skill" }).click();
  await expect(page.getByRole("button", { name: "Remove Git" })).toBeVisible();
  // A skill typed without clicking "Add skill" is added when leaving the box.
  await page.getByLabel("Additional skills").fill("Linear Algebra");
  await page
    .getByLabel("About your skills & knowledge")
    .fill("I am comfortable writing SQL queries and REST APIs.");
  await expect(
    page.getByRole("button", { name: "Remove Linear Algebra" }),
  ).toBeVisible();
  await page
    .getByLabel("Project 1 name")
    .fill("Campus Food Ordering App deployment");
  await page.getByLabel("Project 1 Description").fill(NOTES);
  const projectSkills = page.getByLabel("Project 1 Skills & frameworks used");
  await projectSkills.fill("Docker, Kubernetes,");
  await expect(
    page.getByRole("button", { name: "Remove Kubernetes" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
  await page.waitForURL(/\/analysis\/[0-9a-f-]{36}$/, { timeout: 120_000 });
  const analysisId = page.url().split("/").pop()!;

  // Results: final score (job fit + ATS) and the tabs.
  await expect(
    page.getByRole("img", { name: /Final score: \d+%/ }),
  ).toBeVisible({ timeout: 180_000 });
  await expect(page.getByRole("img", { name: /Job fit: \d+%/ })).toBeVisible();
  await expect(
    page.getByRole("img", { name: /ATS score: \d+%/ }),
  ).toBeVisible();
  await expect(page.getByText("What to do next")).toBeVisible();
  await expect(page.getByText("Everything the job asks for")).toBeVisible();

  // "Explain" asks the AI about one item and shows the answer inline.
  await page
    .getByRole("button", { name: "How was my score calculated?" })
    .click();
  await expect(page.getByRole("region", { name: "Explanation" })).toBeVisible({
    timeout: 60_000,
  });

  await page.getByRole("tab", { name: /Improve resume/ }).click();
  await expect(
    page.getByText("Already have it? Add it to your resume"),
  ).toBeVisible();

  await page.getByRole("tab", { name: /ATS check/ }).click();
  await expect(
    page.getByRole("heading", { name: "Can hiring software read it?" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "The job's keywords" }),
  ).toBeVisible();

  await page.getByRole("tab", { name: /Learn/ }).click();
  await expect(
    page.getByText(/Still to learn|Nothing to learn/).first(),
  ).toBeVisible();
  if (await page.getByText("Your learning path").isVisible()) {
    // Every step has YouTube links (curated videos and/or a search link).
    await expect(page.getByText("Watch on YouTube").first()).toBeVisible();
  }

  // Interview preparation: grouped questions, every one with a source.
  await page.getByRole("tab", { name: /Interview/ }).click();
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
  await page.getByRole("button", { name: /Download report/ }).click();
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
