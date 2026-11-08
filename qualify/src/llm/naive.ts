/**
 * LLM client backed by Naïve's model proxy (`client.proxy.messages`): one org-level model call,
 * no agent, no session, billed to the org's credits. Structured output comes from forcing a
 * single tool call (`submit_review`).
 */
import { createClient } from "@usenaive-sdk/managed-agents";
import type { LlmClient, LlmRequest, LlmResponse } from "./client.js";

export const DEFAULT_NAIVE_BASE_URL = "https://api.vetta.sh";

/**
 * Read Naïve credentials from the environment. Accepts this step's NAIVE_* names and the
 * VETTA_* names the rest of the Claim OS repo uses (prototype server, Vercel functions).
 */
export function naiveCredentialsFromEnv(env: Record<string, string | undefined> = process.env): { apiKey: string; baseUrl?: string } {
  const apiKey = env.NAIVE_API_KEY || env.VETTA_API_KEY || "";
  const baseUrl = env.NAIVE_API_BASE_URL || env.VETTA_API_BASE_URL || undefined;
  return baseUrl ? { apiKey, baseUrl } : { apiKey };
}

export class NaiveLlmClient implements LlmClient {
  readonly name = "naive-proxy";
  private client: ReturnType<typeof createClient>;

  constructor(opts: { apiKey: string; baseUrl?: string; fetch?: typeof globalThis.fetch }) {
    this.client = createClient({
      baseUrl: opts.baseUrl ?? DEFAULT_NAIVE_BASE_URL,
      apiKey: opts.apiKey,
      ...(opts.fetch ? { fetch: opts.fetch } : {}),
    });
  }

  async complete(req: LlmRequest): Promise<LlmResponse> {
    const res = await this.client.proxy.messages(
      {
        model: req.model,
        max_tokens: req.maxTokens,
        system: req.system,
        messages: [{ role: "user", content: req.user }],
        tools: [req.tool],
      },
      req.window,
    );
    const toolUse = res.content.find((b) => b.type === "tool_use" && b.name === req.tool.name);
    const text = res.content
      .filter((b): b is { type: "text"; text: string } => b.type === "text")
      .map((b) => b.text)
      .join("\n");
    return {
      toolInput: toolUse && toolUse.type === "tool_use" ? toolUse.input : undefined,
      text,
      model: res.model,
      usage: {
        inputTokens: res.usage.input_tokens + res.usage.cache_read_input_tokens + res.usage.cache_creation_input_tokens,
        outputTokens: res.usage.output_tokens,
      },
    };
  }
}
