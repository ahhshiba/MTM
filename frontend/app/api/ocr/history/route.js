import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function GET(request) {
  try {
    const { search } = new URL(request.url);
    const resp = await fetch(`${API_BASE}/local/ocr/history${search}`, {
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
  } catch (error) {
    return NextResponse.json(
      { detail: `Failed to proxy history request: ${error.message}` },
      { status: 502 }
    );
  }
}
