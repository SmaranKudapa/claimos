/** The real Naïve client, driven through the SDK against a faked HTTP response (no network). */
import { describe, expect, it } from "vitest";
import { NaiveLlmClient } from "../src/llm/naive.js";
import { qualify } from "../src/pipeline.js";
import { NOW, candidate, passReview, withLlm } from "./helpers.js";

function fakeFetch(calls: { url: string; init: RequestInit }[], reply: unknown) {
  return (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return new Response(JSON.stringify(reply), { status: 200, headers: { "content-type": "application/json", "x-request-id": "req_1" } });
  }) as typeof fetch;
}

const message = (input: unknown) => ({
  id: "req_1",
  type: "message",
  role: "assistant",
  model: "test-model",
  content: [{ type: "tool_use", id: "tu_1", name: "submit_review", input }],
  stop_reason: "tool_use",
  stop_sequence: null,
  usage: { input_tokens: 1200, output_tokens: 350, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
});

describe("NaiveLlmClient", () => {
  it("calls the model proxy with the tool and window, and parses the tool call", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const llm = new NaiveLlmClient({ apiKey: "test-key", baseUrl: "https://api.example.test", fetch: fakeFetch(calls, message(passReview())) });
    const r = await qualify(candidate(), withLlm(llm), { now: NOW });

    expect(r.llm?.ran).toBe(true);
    expect(r.status).toBe("QUALIFIED");
    expect(calls).toHaveLength(1);
    const call = calls[0]!;
    expect(call.url).toContain("/v1/proxy/anthropic/v1/messages");
    const headers = new Headers(call.init.headers);
    expect(headers.get("authorization")).toMatch(/test-key/);
    expect([...headers.entries()].some(([k, v]) => k.toLowerCase() === "vetta-window" && v === "immediate")).toBe(true);
    const body = JSON.parse(String(call.init.body));
    expect(body.model).toBe("test-model");
    expect(body.tools[0].name).toBe("submit_review");
    expect(body.system).toMatch(/C1/);
    // cost from usage: (1200 × $1 + 350 × $3) / 1M
    expect(r.llm?.costUsd).toBeCloseTo(0.00225, 5);
  });
});
