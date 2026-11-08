import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client";

function mockFetch(status: number, body?: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("GET returns parsed json without X-Requested-With", async () => {
    const fn = mockFetch(200, { ok: 1 });
    await expect(api.get("/api/x")).resolves.toEqual({ ok: 1 });
    const headers = fn.mock.calls[0]![1].headers as Record<string, string>;
    expect(headers["X-Requested-With"]).toBeUndefined();
  });

  it("mutations send X-Requested-With and json body", async () => {
    const fn = mockFetch(201, { id: "a" });
    await api.post("/api/x", { a: 1 });
    const init = fn.mock.calls[0]![1];
    expect(init.headers["X-Requested-With"]).toBe("expense-tracker");
    expect(init.body).toBe('{"a":1}');
  });

  it("204 resolves undefined", async () => {
    mockFetch(204);
    await expect(api.del("/api/x")).resolves.toBeUndefined();
  });

  it("errors raise ApiError with code", async () => {
    mockFetch(422, {
      error: { code: "category_required", message: "need category" },
    });
    await expect(api.put("/api/x", {})).rejects.toMatchObject({
      status: 422,
      code: "category_required",
      message: "need category",
    });
  });

  it("errors without body use generic code", async () => {
    mockFetch(500);
    const err = await api.patch("/api/x", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("http_error");
  });
});
