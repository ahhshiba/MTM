import { NextResponse } from "next/server";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function GET(_request, { params }) {
  const { imageId } = await params;
  const resp = await fetch(`${API_BASE}/local/ocr/results/images/${imageId}`);
  const buffer = await resp.arrayBuffer();
  return new NextResponse(buffer, {
    status: resp.status,
    headers: {
      "content-type": resp.headers.get("content-type") || "application/octet-stream",
    },
  });
}
