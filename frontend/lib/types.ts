// Mirrors backend Pydantic schemas (backend/app/schemas). Later phases will
// generate these from the FastAPI OpenAPI spec with openapi-typescript.

export type HealthResponse = {
  status: "ok";
  version: string;
};

export type MeResponse = {
  user_id: string;
  email: string | null;
};
