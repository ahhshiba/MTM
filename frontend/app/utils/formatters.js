// app/utils/formatters.js
/**
 * 格式化工具函數
 */

export function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return "-"
    const sizes = ["B", "KB", "MB", "GB"]
    let value = bytes
    let idx = 0
    while (value >= 1024 && idx < sizes.length - 1) {
        value /= 1024
        idx += 1
    }
    return `${value.toFixed(1)} ${sizes[idx]}`
}

export function formatTimestamp(ts) {
    if (!ts) return "-"
    const date = new Date(ts * 1000)
    return date.toLocaleString()
}

export function formatNumber(value) {
    if (value === null || value === undefined) return "-"
    return Number(value).toLocaleString()
}

export function normalizeId(value) {
    return String(value)
}

export const SESSION_STORAGE_KEY = "mtm_vlm_sessions"
export const MODE_STORAGE_KEY = "mtm_pipeline_mode"

export function readSessionStore() {
    if (typeof window === "undefined") return {}
    try {
        const raw = window.localStorage.getItem(SESSION_STORAGE_KEY)
        if (!raw) return {}
        const parsed = JSON.parse(raw)
        return typeof parsed === "object" && parsed ? parsed : {}
    } catch {
        return {}
    }
}

export function writeSessionStore(map) {
    if (typeof window === "undefined") return
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(map))
}
