import { describe, expect, it } from "vitest";
import { MAX_SKILLS, addSkills, buildExtraText, formatSkills } from "./skills";

describe("addSkills", () => {
  it("adds a single trimmed skill", () => {
    expect(addSkills([], "  Docker  ")).toEqual(["Docker"]);
  });

  it("splits pasted lists and collapses spaces", () => {
    expect(addSkills(["Python"], "AWS,  Redis ;Apache   Kafka\nSQL")).toEqual([
      "Python",
      "AWS",
      "Redis",
      "Apache Kafka",
      "SQL",
    ]);
  });

  it("ignores empties and case-insensitive duplicates", () => {
    expect(addSkills(["Docker"], "docker, , DOCKER, Git")).toEqual([
      "Docker",
      "Git",
    ]);
    expect(addSkills(["Docker"], "   ")).toEqual(["Docker"]);
  });

  it("caps length and count", () => {
    expect(addSkills([], "x".repeat(100))[0]).toHaveLength(60);
    const many = Array.from({ length: 60 }, (_, i) => `skill${i}`).join(",");
    expect(addSkills([], many)).toHaveLength(MAX_SKILLS);
  });
});

describe("formatSkills", () => {
  it("formats a sentence, or nothing", () => {
    expect(formatSkills(["Docker", "AWS"])).toBe(
      "Additional skills: Docker, AWS.",
    );
    expect(formatSkills([])).toBe("");
  });
});

describe("buildExtraText", () => {
  it("combines tags and the plain-English description", () => {
    expect(buildExtraText(["Docker"], "  I know REST APIs well.  ")).toBe(
      "Additional skills: Docker.\n\nAbout my skills and knowledge:\nI know REST APIs well.",
    );
    expect(buildExtraText([], "Only prose")).toBe(
      "About my skills and knowledge:\nOnly prose",
    );
    expect(buildExtraText([], "   ")).toBe("");
  });
});
