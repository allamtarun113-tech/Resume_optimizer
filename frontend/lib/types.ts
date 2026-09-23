// API types, generated from the backend's OpenAPI spec (lib/api-schema.d.ts).
// To refresh: `uv run python -m scripts.export_openapi` in backend/, then `pnpm gen:api`.
import type { components } from "./api-schema";

type Schemas = components["schemas"];

export type HealthResponse = Schemas["HealthResponse"];
export type DocumentResponse = Schemas["DocumentResponse"];
export type AnalysisCreate = Schemas["AnalysisCreate"];
export type AnalysisCreated = Schemas["AnalysisCreated"];
export type AnalysisResponse = Schemas["AnalysisResponse"];
export type AnalysisSummary = Schemas["AnalysisSummary"];
export type AnalysisRerun = Schemas["AnalysisRerun"];
export type AnalysisStatus = AnalysisResponse["status"];
export type StudentProfile = Schemas["StudentProfile"];
export type JobRequirements = Schemas["JobRequirements"];
export type RequirementMatch = Schemas["RequirementMatch"];
export type EvidenceRef = Schemas["EvidenceRef"];
export type Suggestion = Schemas["Suggestion"];
export type Gap = Schemas["Gap"];
export type LearningPath = Schemas["LearningPath"];
export type LearningStep = Schemas["LearningStep"];
export type InterviewSet = Schemas["InterviewSet"];
export type InterviewQuestion = Schemas["InterviewQuestion"];
export type AiSettings = Schemas["AiSettingsResponse"];
export type AiSettingsUpdate = Schemas["AiSettingsUpdate"];
export type ModelList = Schemas["ModelListResponse"];
