import { NextResponse } from "next/server";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function POST(_request, { params }) {
  const { localJobId } = await params;
  const resp = await fetch(`${API_BASE}/local/ocr/jobs/${localJobId}/cancel`, {
    method: "POST",
  });
  const body = await resp.text();
  return new NextResponse(body, {
    status: resp.status,
    headers: {
      "content-type": resp.headers.get("content-type") || "application/json",
    },
  });
}
