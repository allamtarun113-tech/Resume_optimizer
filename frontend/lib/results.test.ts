import { describe, expect, it } from "vitest";
import {
  groupMatches,
  scoreTone,
  sourceLabel,
  strengthLabel,
  whereToAdd,
  formatHours,
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
  it("maps strengths", () => {
    expect(strengthLabel(1)).toBe("Strong");
    expect(strengthLabel(0.7)).toBe("Listed");
    expect(strengthLabel(0.4)).toBe("Partial");
    expect(strengthLabel(0)).toBe("Missing");
  });

  it("maps score tones and sources", () => {
    expect(scoreTone(80)).toBe("good");
    expect(scoreTone(50)).toBe("ok");
    expect(scoreTone(49)).toBe("low");
    expect(sourceLabel("resume")).toBe("resume");
    expect(sourceLabel("supplementary:abc")).toBe("other docs");
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
