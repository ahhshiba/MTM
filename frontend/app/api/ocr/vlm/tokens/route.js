import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function POST(request) {
  const payload = await request.text();
  const resp = await fetch(`${API_BASE}/local/ocr/vlm/tokens`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: payload,
  });
  const body = await resp.text();
  return new NextResponse(body, {
    status: resp.status,
    headers: {
      "content-type": resp.headers.get("content-type") || "application/json",
      "cache-control": "no-store",
    },
  });
}
