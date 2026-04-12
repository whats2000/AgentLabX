import createClient from "openapi-fetch";
import type { components, paths } from "./generated";

const client = createClient<paths>({ baseUrl: "" });

export class APIError<B = unknown> extends Error {
  constructor(
    public status: number,
    public body: B,
  ) {
    super(`API ${status}: ${JSON.stringify(body)}`);
  }
}

export function isValidationError(
  err: unknown,
): err is APIError<components["schemas"]["HTTPValidationError"]> {
  return err instanceof APIError && err.status === 422;
}

function unwrap<T, E>(result: { data?: T; error?: E; response: Response }): T {
  if (result.error !== undefined) {
    throw new APIError<E>(result.response.status, result.error);
  }
  return result.data as T;
}

export const api = {
  async listSessions(userId?: string) {
    const result = await client.GET("/api/sessions", {
      params: { query: userId ? { user_id: userId } : {} },
    });
    return unwrap(result);
  },
  async createSession(
    body: NonNullable<
      paths["/api/sessions"]["post"]["requestBody"]
    >["content"]["application/json"],
  ) {
    const result = await client.POST("/api/sessions", { body });
    return unwrap(result);
  },
  async getSession(sessionId: string) {
    const result = await client.GET("/api/sessions/{session_id}", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async deleteSession(sessionId: string) {
    const result = await client.DELETE("/api/sessions/{session_id}", {
      params: { path: { session_id: sessionId } },
    });
    if (result.error !== undefined) {
      throw new APIError(result.response.status, result.error);
    }
  },
  async startSession(sessionId: string) {
    const result = await client.POST("/api/sessions/{session_id}/start", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async pauseSession(sessionId: string) {
    const result = await client.POST("/api/sessions/{session_id}/pause", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async resumeSession(sessionId: string) {
    const result = await client.POST("/api/sessions/{session_id}/resume", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async redirectSession(
    sessionId: string,
    body: NonNullable<
      paths["/api/sessions/{session_id}/redirect"]["post"]["requestBody"]
    >["content"]["application/json"],
  ) {
    const result = await client.POST("/api/sessions/{session_id}/redirect", {
      params: { path: { session_id: sessionId } },
      body,
    });
    return unwrap(result);
  },
  async updatePreferences(
    sessionId: string,
    body: NonNullable<
      paths["/api/sessions/{session_id}/preferences"]["patch"]["requestBody"]
    >["content"]["application/json"],
  ) {
    const result = await client.PATCH("/api/sessions/{session_id}/preferences", {
      params: { path: { session_id: sessionId } },
      body,
    });
    return unwrap(result);
  },
  async getArtifacts(sessionId: string) {
    const result = await client.GET("/api/sessions/{session_id}/artifacts", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async getTransitions(sessionId: string) {
    const result = await client.GET("/api/sessions/{session_id}/transitions", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async getCost(sessionId: string) {
    const result = await client.GET("/api/sessions/{session_id}/cost", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async getHypotheses(sessionId: string) {
    const result = await client.GET("/api/sessions/{session_id}/hypotheses", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result);
  },
  async listPlugins() {
    const result = await client.GET("/api/plugins", {});
    return unwrap(result);
  },
};
