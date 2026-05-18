// app/utils/api.js
/**
 * API 呼叫工具函數
 */

export const API_BASE = "/api/ocr"

export async function readJson(response) {
    const text = await response.text()
    if (!text) return {}
    try {
        return JSON.parse(text)
    } catch {
        return {}
    }
}

export async function fetchJob(localJobId) {
    const resp = await fetch(`${API_BASE}/jobs/${localJobId}`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function createJob(file) {
    const formData = new FormData()
    formData.append("file", file)
    const resp = await fetch(`${API_BASE}/jobs`, {
        method: "POST",
        body: formData,
    })
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchResults(localJobId) {
    const resp = await fetch(`${API_BASE}/jobs/${localJobId}/results`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchArtifactMd(artifactId) {
    const resp = await fetch(`${API_BASE}/results/artifacts/${artifactId}/result_md`)
    const text = await resp.text()
    return { ok: resp.ok, text: resp.ok ? text : "" }
}

export async function fetchArtifactJson(artifactId) {
    const resp = await fetch(`${API_BASE}/results/artifacts/${artifactId}/result_json`)
    return { ok: resp.ok, data: await readJson(resp) }
}

// VLM APIs
export async function createVlmSession(imageId) {
    const resp = await fetch(`${API_BASE}/vlm/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ image_id: String(imageId) }),
    })
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function createVlmSessionsBatch(imageIds) {
    const resp = await fetch(`${API_BASE}/vlm/sessions/batch`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ image_ids: imageIds.map(String) }),
    })
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchVlmSession(sessionId) {
    const resp = await fetch(`${API_BASE}/vlm/sessions/${sessionId}`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function postVlmMessage(sessionId, content) {
    const resp = await fetch(`${API_BASE}/vlm/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role: "user", content }),
    })
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchVlmTokens(sessionIds) {
    const resp = await fetch(`${API_BASE}/vlm/tokens`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_ids: sessionIds }),
    })
    return { ok: resp.ok, data: await readJson(resp) }
}

// Extraction APIs
export async function startExtraction(payload) {
    const resp = await fetch(`${API_BASE}/extraction/start`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
    })
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchExtractionStatus(extractionId) {
    const resp = await fetch(`${API_BASE}/extraction/${extractionId}`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchExtractionResult(extractionId) {
    const resp = await fetch(`${API_BASE}/extraction/${extractionId}/result`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchExtractionByOcrRun(ocrRunId) {
    const resp = await fetch(`${API_BASE}/extraction/by-ocr/${ocrRunId}`)
    return { ok: resp.ok, data: await readJson(resp) }
}

// History APIs
export async function fetchHistory(limit = 30, offset = 0) {
    const resp = await fetch(`${API_BASE}/history?limit=${limit}&offset=${offset}`)
    return { ok: resp.ok, status: resp.status, data: await readJson(resp) }
}

export async function restoreHistoryRun(ocrRunId) {
    const resp = await fetch(`${API_BASE}/history/${ocrRunId}/restore`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function deleteHistoryRun(ocrRunId) {
    const resp = await fetch(`${API_BASE}/history/${ocrRunId}`, { method: "DELETE" })
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchLicenseStatus() {
    const resp = await fetch(`${API_BASE}/license/status`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function fetchFingerprint() {
    const resp = await fetch(`${API_BASE}/license/fingerprint`)
    return { ok: resp.ok, data: await readJson(resp) }
}

export async function uploadLicense(file) {
    const formData = new FormData()
    formData.append("file", file)
    const resp = await fetch(`${API_BASE}/license/upload`, {
        method: "POST",
        body: formData,
    })
    return { ok: resp.ok, data: await readJson(resp) }
}
