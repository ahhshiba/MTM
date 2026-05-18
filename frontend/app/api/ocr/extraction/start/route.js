import { NextResponse } from "next/server";

export const runtime = "nodejs";

const API_BASE = process.env.LOCAL_API_BASE || "http://127.0.0.1:8001";

export async function POST(request) {
    try {
        const body = await request.json();
        const resp = await fetch(`${API_BASE}/local/ocr/extraction/start`, {
            method: "POST",
            headers: {
                "content-type": "application/json",
            },
            body: JSON.stringify(body),
        });

        const data = await resp.json();
        return NextResponse.json(data, { status: resp.status });
    } catch (error) {
        return NextResponse.json({ detail: String(error) }, { status: 500 });
    }
}
