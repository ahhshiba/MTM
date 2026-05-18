import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function GET(_request, { params }) {
  const { sessionId } = await params;
  const resp = await fetch(`${API_BASE}/local/ocr/vlm/sessions/${sessionId}/tokens`, {
    cache: "no-store",
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
