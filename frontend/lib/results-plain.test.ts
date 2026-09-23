import { describe, expect, it } from "vitest";
import type { RequirementMatch } from "@/lib/types";
import {
  evidenceWhere,
  nextSteps,
  plainStatus,
  plural,
  afterAddingText,
  atsIssues,
  headlineScore,
  keywordHint,
  scoreSentence,
  scoreVerdict,
} from "@/lib/results";

type Evidence = RequirementMatch["evidence"][number];

const ev = (over: Partial<Evidence>): Evidence => ({
  kind: "skill",
  index: 0,
  context: "skills_section",
  source: "resume",
  label: "Python",
  snippet: "Python",
  direct: true,
  ...over,
});

const match = (over: Partial<RequirementMatch>): RequirementMatch => ({
  requirement_index: 0,
  name: "Python",
  category: "skill",
  importance: "must",
  min_years: null,
  skill_id: "python",
  method: "taxonomy",
  weight: 3,
  resume_strength: 1,
  best_strength: 1,
  resume_years: null,
  total_years: null,
  bucket: "strong_in_resume",
  evidence: [],
  ...over,
});

describe("plain wording", () => {
  it("names the project for strong matches", () => {
    const m = match({
      evidence: [
        ev({}),
        ev({ kind: "project", context: "project", label: "Food App" }),
      ],
    });
    expect(plainStatus(m)).toBe("On your resume, and you show it in Food App.");
  });

  it("explains weak matches", () => {
    expect(
      plainStatus(
        match({
          bucket: "weak_in_resume",
          resume_strength: 0.7,
          evidence: [ev({})],
        }),
      ),
    ).toContain("Listed on your resume, but no project");
    const usedOnly = match({
      bucket: "weak_in_resume",
      resume_strength: 0.7,
      best_strength: 1,
      evidence: [
        ev({ kind: "project", context: "project", label: "Food App" }),
      ],
    });
    expect(plainStatus(usedOnly)).toBe(
      "You used it in Food App, but your resume doesn't name it clearly. Your other documents show more: see Improve resume.",
    );
    expect(
      plainStatus(
        match({ bucket: "weak_in_resume", evidence: [ev({ direct: false })] }),
      ),
    ).toBe("Only hinted at on your resume, not stated clearly.");
    expect(
      plainStatus(
        match({
          bucket: "weak_in_resume",
          category: "experience",
          min_years: 2,
          resume_years: 0.5,
        }),
      ),
    ).toBe(
      "On your resume, but with less experience than the job asks for. The job asks for 2 years; your resume shows about 0.5 years.",
    );
  });

  it("separates 'add it' from real gaps", () => {
    expect(
      plainStatus(match({ bucket: "missing_from_resume_but_evidenced" })),
    ).toContain("Not on your resume, but your other documents");
    expect(plainStatus(match({ bucket: "true_gap" }))).toContain(
      "learning path",
    );
    expect(
      plainStatus(match({ bucket: "true_gap", category: "soft_skill" })),
    ).toBe("Not found in anything you gave us yet.");
  });

  it("describes where evidence came from", () => {
    expect(evidenceWhere(ev({}))).toBe("skills list in your resume");
    expect(
      evidenceWhere(
        ev({ kind: "project", context: "project", source: "supplementary:x" }),
      ),
    ).toBe("project in your other documents or notes");
    expect(evidenceWhere(ev({ context: "other", direct: false }))).toBe(
      "other in your resume (related, not exact)",
    );
  });

  it("summarises the score", () => {
    expect(scoreVerdict(80)).toBe("Strong match");
    expect(scoreVerdict(60)).toBe("Good start");
    expect(scoreVerdict(10)).toBe("Needs work");
    expect(scoreSentence(74, 90)).toContain("could raise it to 90%");
    expect(scoreSentence(74, 74)).toBe(
      "Your resume shows 74% of what this job asks for.",
    );
    expect(afterAddingText(74, 90)).toContain("from 74% to 90% (+16 points)");
    expect(afterAddingText(35, 35)).toContain(
      "wouldn't change the score (35%)",
    );
    expect(plural(1, "gap")).toBe("1 gap");
    expect(plural(3, "gap")).toBe("3 gaps");
  });

  it("builds next steps", () => {
    const steps = nextSteps({
      fitScore: 74,
      potentialScore: 90,
      suggestionCount: 2,
      gapNames: ["AWS", "Redis", "Go", "Rust"],
    });
    expect(steps.map((s) => s.tab)).toEqual(["improve", "learn", "interview"]);
    expect(steps[0].title).toBe("Add 2 things you already have to your resume");
    expect(steps[1].title).toBe(
      "Learn what's missing: AWS, Redis, Go and 1 more",
    );
    expect(
      nextSteps({
        fitScore: 90,
        potentialScore: 90,
        suggestionCount: 0,
        gapNames: [],
      }).map((s) => s.tab),
    ).toEqual(["interview"]);
  });
});

describe("YouTube links", () => {
  it("recognises YouTube URLs", async () => {
    const { isYouTube } = await import("@/lib/results");
    expect(isYouTube("https://www.youtube.com/watch?v=abc")).toBe(true);
    expect(isYouTube("https://youtu.be/abc")).toBe(true);
    expect(isYouTube("https://notyoutube.com/x")).toBe(false);
    expect(isYouTube("not a url")).toBe(false);
  });

  it("builds a search link", async () => {
    const { youTubeSearchUrl } = await import("@/lib/results");
    expect(youTubeSearchUrl("Linear algebra")).toBe(
      "https://www.youtube.com/results?search_query=Linear%20algebra%20tutorial",
    );
  });
});

describe("ATS and final score", () => {
  it("prefers the final score and explains missing keywords", () => {
    expect(headlineScore({ final_score: 46, fit_score: 35 })).toBe(46);
    expect(headlineScore({ final_score: null, fit_score: 35 })).toBe(35);
    expect(keywordHint("missing_from_resume_but_evidenced")).toContain(
      "Improve resume",
    );
    expect(keywordHint("true_gap")).toContain("Learn");
    expect(keywordHint(null)).toBe("Not written in your resume.");
    const check = {
      id: "no_tables",
      group: "readable" as const,
      title: "No tables",
      points: 2,
      max_points: 8,
      detail: "",
      fix: null,
      items: [],
    };
    expect(
      atsIssues([
        { ...check, status: "warn" },
        { ...check, status: "pass" },
      ]),
    ).toHaveLength(1);
    const steps = nextSteps({
      fitScore: 35,
      potentialScore: 35,
      suggestionCount: 0,
      gapNames: [],
      atsIssues: 3,
      atsScore: 64,
    });
    expect(steps[0]).toMatchObject({ tab: "ats" });
    expect(steps[0].detail).toContain("64%");
  });
});
