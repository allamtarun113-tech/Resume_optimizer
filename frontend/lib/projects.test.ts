import { describe, expect, it } from "vitest";
import {
  emptyProject,
  filledProjects,
  formatProject,
  projectProblem,
} from "./projects";

const food = {
  name: "Campus Food Ordering App",
  description: "Built a FastAPI backend with PostgreSQL for 2,000 students.",
  skills: ["FastAPI", "PostgreSQL", "Docker"],
};

describe("projects", () => {
  it("formats a labelled document", () => {
    expect(formatProject(food)).toBe(
      "Project: Campus Food Ordering App\n" +
        "Skills and frameworks used: FastAPI, PostgreSQL, Docker\n\n" +
        "Description:\nBuilt a FastAPI backend with PostgreSQL for 2,000 students.",
    );
    expect(formatProject({ ...food, skills: [], description: "  " })).toBe(
      "Project: Campus Food Ordering App",
    );
  });

  it("ignores blank entries", () => {
    expect(filledProjects([emptyProject(), food, emptyProject()])).toEqual([
      food,
    ]);
    expect(projectProblem([emptyProject()])).toBeNull();
  });

  it("requires a name and some detail", () => {
    expect(projectProblem([{ ...food, name: " " }])).toBe(
      "Project 1: add a project name.",
    );
    expect(
      projectProblem([food, { name: "Bot", description: "", skills: [] }]),
    ).toMatch(/Project 2: add a description or the skills/);
    expect(
      projectProblem([{ name: "Bot", description: "", skills: ["Python"] }]),
    ).toBeNull();
  });

  it("limits description length", () => {
    expect(
      projectProblem([{ ...food, description: "x".repeat(20_001) }]),
    ).toMatch(/up to 20,000/);
  });
});
