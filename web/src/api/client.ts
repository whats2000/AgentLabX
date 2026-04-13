import createClient from "openapi-fetch";
import type { components, paths } from "./generated";
import type {
  GraphTopology,
  SessionAgentInfo,
  AgentContextResponse,
  AgentHistoryResponse,
  AgentMemoryRecord,
  PIDecisionRecord,
  RequestsResponse,
  ExperimentsResponse,
} from "../types/domain";

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

  async getGraph(sessionId: string): Promise<GraphTopology> {
    const result = await client.GET("/api/sessions/{session_id}/graph", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result) as GraphTopology;
  },

  async listAgents(sessionId: string): Promise<SessionAgentInfo[]> {
    const result = await client.GET("/api/sessions/{session_id}/agents", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result) as SessionAgentInfo[];
  },

  async getAgentContext(sessionId: string, agent: string): Promise<AgentContextResponse> {
    const result = await client.GET("/api/sessions/{session_id}/agents/{name}/context", {
      params: { path: { session_id: sessionId, name: agent } },
    });
    return unwrap(result) as AgentContextResponse;
  },

  async getAgentHistory(
    sessionId: string,
    agent: string,
    params?: { limit?: number; after_ts?: string | null },
  ): Promise<AgentHistoryResponse> {
    const result = await client.GET("/api/sessions/{session_id}/agents/{name}/history", {
      params: {
        path: { session_id: sessionId, name: agent },
        query: params,
      },
    });
    return unwrap(result) as AgentHistoryResponse;
  },

  async getAgentMemory(sessionId: string, agent: string): Promise<AgentMemoryRecord> {
    const result = await client.GET("/api/sessions/{session_id}/agents/{name}/memory", {
      params: { path: { session_id: sessionId, name: agent } },
    });
    return unwrap(result) as AgentMemoryRecord;
  },

  async getPIHistory(sessionId: string): Promise<PIDecisionRecord[]> {
    const result = await client.GET("/api/sessions/{session_id}/pi/history", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result) as PIDecisionRecord[];
  },

  async getRequests(sessionId: string): Promise<RequestsResponse> {
    const result = await client.GET("/api/sessions/{session_id}/requests", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result) as RequestsResponse;
  },

  async getExperiments(sessionId: string): Promise<ExperimentsResponse> {
    const result = await client.GET("/api/sessions/{session_id}/experiments", {
      params: { path: { session_id: sessionId } },
    });
    return unwrap(result) as ExperimentsResponse;
  },
};
