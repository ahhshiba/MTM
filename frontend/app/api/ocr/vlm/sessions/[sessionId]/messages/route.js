import { NextResponse } from "next/server";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function POST(request, { params }) {
  const { sessionId } = await params;
  const payload = await request.json();
  const resp = await fetch(`${API_BASE}/local/ocr/vlm/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await resp.text();
  return new NextResponse(body, {
    status: resp.status,
    headers: {
      "content-type": resp.headers.get("content-type") || "application/json",
    },
  });
}
