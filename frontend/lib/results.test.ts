import { describe, expect, it } from "vitest";
import {
  groupMatches,
  scoreTone,
  whereToAdd,
  formatHours,
  groupByTopic,
  sourceText,
} from "./results";
import type { RequirementMatch } from "./types";

function match(
  name: string,
  bucket: RequirementMatch["bucket"],
  importance: RequirementMatch["importance"] = "must",
  weight = 3,
  requirement_index = 0,
): RequirementMatch {
  return {
    requirement_index,
    name,
    category: "skill",
    importance,
    min_years: null,
    skill_id: null,
    method: "taxonomy",
    weight,
    resume_strength: 0,
    best_strength: 0,
    resume_years: null,
    total_years: null,
    bucket,
    evidence: [],
  };
}

describe("groupMatches", () => {
  it("orders groups by bucket and drops empty ones", () => {
    const groups = groupMatches([
      match("Rust", "true_gap"),
      match("Python", "strong_in_resume"),
    ]);
    expect(groups.map((g) => g.bucket)).toEqual([
      "strong_in_resume",
      "true_gap",
    ]);
  });

  it("can skip buckets", () => {
    const groups = groupMatches(
      [match("Rust", "true_gap"), match("Python", "strong_in_resume")],
      ["true_gap"],
    );
    expect(groups.map((g) => g.bucket)).toEqual(["strong_in_resume"]);
  });

  it("puts must-haves first, then heavier weights, then JD order", () => {
    const [group] = groupMatches([
      match("AWS", "true_gap", "nice", 1, 0),
      match("Teamwork", "true_gap", "must", 1.2, 1),
      match("Go", "true_gap", "must", 3, 3),
      match("Rust", "true_gap", "must", 3, 2),
    ]);
    expect(group.items.map((m) => m.name)).toEqual([
      "Rust",
      "Go",
      "Teamwork",
      "AWS",
    ]);
  });
});

describe("labels", () => {
  it("maps score tones", () => {
    expect(scoreTone(80)).toBe("good");
    expect(scoreTone(50)).toBe("ok");
    expect(scoreTone(49)).toBe("low");
  });

  it("describes where to add a suggestion", () => {
    expect(whereToAdd("projects", "Campus Food App")).toBe(
      "Projects → Campus Food App",
    );
    expect(whereToAdd("skills", null)).toBe("Skills");
  });
});

describe("formatHours", () => {
  it("formats estimates", () => {
    expect(formatHours(null)).toBeNull();
    expect(formatHours(0)).toBeNull();
    expect(formatHours(0.5)).toBe("under 1 hour");
    expect(formatHours(1)).toBe("about 1 hour");
    expect(formatHours(14.4)).toBe("about 14 hours");
  });
});

describe("interview helpers", () => {
  const github = {
    kind: "github",
    label: "owner/repo",
    url: "https://github.com/owner/repo",
    license: "MIT",
  };
  it("groups technical questions by topic in first-seen order", () => {
    const groups = groupByTopic([
      { topic: "Docker", source: github },
      { topic: "SQL", source: github },
      { topic: "Docker", source: github },
      { topic: null, source: github },
    ]);
    expect(groups.map((g) => [g.topic, g.questions.length])).toEqual([
      ["Docker", 2],
      ["SQL", 1],
      ["Other", 1],
    ]);
  });

  it("describes sources", () => {
    expect(sourceText(github)).toBe("owner/repo (MIT)");
    expect(sourceText({ kind: "template", label: "bank" })).toBe(
      "Project deep-dive template",
    );
  });
});
