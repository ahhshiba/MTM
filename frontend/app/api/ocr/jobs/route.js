import { NextResponse } from "next/server";

export const runtime = "nodejs";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function POST(request) {
  const formData = await request.formData();
  const resp = await fetch(`${API_BASE}/local/ocr/jobs`, {
    method: "POST",
    body: formData,
  });

  const body = await resp.text();
  return new NextResponse(body, {
    status: resp.status,
    headers: {
      "content-type": resp.headers.get("content-type") || "application/json",
    },
  });
}
