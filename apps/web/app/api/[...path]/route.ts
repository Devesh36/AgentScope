import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
export const runtime = "nodejs";
async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (path.some((p) => p === ".." || p === "."))
    return Response.json({ detail: "Invalid path" }, { status: 400 });
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== request.headers.get("host"))
    return Response.json(
      { detail: "Cross-origin requests are not allowed" },
      { status: 403 },
    );
  try {
    const token =
      process.env.AGENTSCOPE_ADMIN_TOKEN ||
      (
        await readFile(
          /* turbopackIgnore: true */ process.env.AGENTSCOPE_TOKEN_FILE ||
            resolve(process.cwd(), "../../.local/admin-token"),
          "utf8",
        )
      ).trim();
    const headers = new Headers({ Authorization: `Bearer ${token}` });
    for (const name of ["content-type", "x-project-id", "last-event-id"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    const apiPath =
      path[0] === "health" ? `/${path.join("/")}` : `/api/${path.join("/")}`;
    const upstream = await fetch(
      `${process.env.API_URL || "http://127.0.0.1:8000"}${apiPath}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        body: ["GET", "HEAD"].includes(request.method)
          ? undefined
          : await request.arrayBuffer(),
        cache: "no-store",
        signal: request.signal,
      },
    );
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
        ...(upstream.headers.get("content-type")?.includes("event-stream")
          ? { "X-Accel-Buffering": "no" }
          : {}),
      },
    });
  } catch {
    return Response.json(
      { detail: "The API is unavailable. Start the backend and try again." },
      { status: 503 },
    );
  }
}
export {
  forward as GET,
  forward as POST,
  forward as PUT,
  forward as PATCH,
  forward as DELETE,
};
