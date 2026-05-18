"use client"
// app/components/HistoryDrawer.jsx
/**
 * 歷史紀錄側邊抽屜
 * 顯示過去的 OCR / Extraction 執行紀錄
 * 點擊可還原至 Preview 步驟
 */

import { useEffect, useState, useCallback } from "react"
import {
    X,
    Clock,
    FileText,
    CheckCircle2,
    AlertCircle,
    Loader2,
    Cpu,
    ChevronRight,
    Search,
    RefreshCw,
    Trash2,
} from "lucide-react"
import { useApp } from "../context/AppContext"
import { fetchHistory, restoreHistoryRun, deleteHistoryRun } from "../utils/api"
import { getStepsForMode } from "./StepNav"
import { cn } from "../utils/cn"

function formatHistoryError(status, data, fallback = "Failed to load history") {
    const detail = data?.detail
    if (typeof detail === "string") return `${fallback} (${status}): ${detail}`
    if (detail?.message) return `${fallback} (${status}): ${detail.message}`
    if (data?.error) return `${fallback} (${status}): ${data.error}`
    return status ? `${fallback} (${status})` : fallback
}

function timeAgo(isoString) {
    if (!isoString) return ""
    const diff = Date.now() - new Date(isoString).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return "just now"
    if (mins < 60) return `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    if (days < 7) return `${days}d ago`
    return new Date(isoString).toLocaleDateString()
}

function StatusBadge({ status }) {
    if (!status) return null
    const s = status.toLowerCase()
    const isOk = ["completed", "succeeded", "done"].includes(s)
    const isFail = ["failed", "error"].includes(s)
    const isRun = ["running", "pending", "queued"].includes(s)

    return (
        <span
            className={cn(
                "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide",
                isOk && "bg-green-500/15 text-green-400",
                isFail && "bg-red-500/15 text-red-400",
                isRun && "bg-blue-500/15 text-blue-400",
                !isOk && !isFail && !isRun && "bg-muted text-muted-foreground"
            )}
        >
            {isOk && <CheckCircle2 size={10} />}
            {isFail && <AlertCircle size={10} />}
            {isRun && <Loader2 size={10} className="animate-spin" />}
            {status}
        </span>
    )
}

export default function HistoryDrawer({ isOpen, onClose }) {
    const { state, dispatch } = useApp()
    const [items, setItems] = useState([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(false)
    const [restoring, setRestoring] = useState(null) // ocr_run_id being restored
    const [deleting, setDeleting] = useState(null) // ocr_run_id being deleted
    const [searchQuery, setSearchQuery] = useState("")
    const [error, setError] = useState("")

    const loadHistory = useCallback(async () => {
        setLoading(true)
        setError("")
        try {
            const { ok, status, data } = await fetchHistory(50, 0)
            if (ok) {
                setItems(data.items || [])
                setTotal(data.total || 0)
            } else {
                setError(formatHistoryError(status, data))
            }
        } catch (e) {
            setError(`Failed to load history: ${e.message}`)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        if (isOpen) {
            loadHistory()
        }
    }, [isOpen, loadHistory])

    const handleRestore = async (item) => {
        setRestoring(item.ocr_run_id)
        try {
            const { ok, data } = await restoreHistoryRun(item.ocr_run_id)
            if (!ok) {
                setError("Failed to restore run")
                setRestoring(null)
                return
            }

            // Find the preview step index
            const isUserMode = state.mode === "user"
            const steps = getStepsForMode(isUserMode)
            const previewIdx = steps.findIndex(s => s.originalIndex === 7)
            const targetStep = previewIdx >= 0 ? previewIdx : steps.length - 1

            // Dispatch restore action
            dispatch({
                type: "RESTORE_HISTORY_RUN",
                payload: {
                    job: {
                        ocr_run_id: data.ocr_run?.id,
                        document_id: data.ocr_run?.document_id,
                        status: data.ocr_run?.status || "completed",
                    },
                    status: {
                        ocr_run_id: data.ocr_run?.id,
                        document_id: data.ocr_run?.document_id,
                        status: "completed",
                        step: "done",
                        progress: 1,
                    },
                    extractionRun: data.extraction_run ? {
                        extraction_run_id: data.extraction_run.id,
                        status: data.extraction_run.status,
                    } : null,
                    extractionStatus: data.extraction_run ? {
                        status: data.extraction_run.status,
                        extraction_run_id: data.extraction_run.id,
                    } : null,
                    extractionResult: data.extraction_result || null,
                    stepIndex: targetStep,
                },
            })

            onClose()
        } catch {
            setError("Failed to restore run")
        } finally {
            setRestoring(null)
        }
    }

    const handleDelete = async (e, item) => {
        e.stopPropagation()
        const title = item.document_title || "Untitled"
        if (!confirm(`確定要刪除「${title}」的執行紀錄嗎？\n\n此操作會刪除所有相關資料（OCR 結果、Extraction 結果、輸出檔案）且無法恢復。`)) {
            return
        }
        setDeleting(item.ocr_run_id)
        try {
            const { ok } = await deleteHistoryRun(item.ocr_run_id)
            if (ok) {
                setItems(prev => prev.filter(i => i.ocr_run_id !== item.ocr_run_id))
                setTotal(prev => prev - 1)
            } else {
                setError("刪除失敗")
            }
        } catch {
            setError("刪除失敗")
        } finally {
            setDeleting(null)
        }
    }

    // Filter items by search query
    const filtered = searchQuery.trim()
        ? items.filter(item =>
            (item.document_title || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
            (item.document_id || "").toLowerCase().includes(searchQuery.toLowerCase())
        )
        : items

    const recentItems = filtered.filter(i => i.is_recent)
    const historyItems = filtered.filter(i => !i.is_recent)

    if (!isOpen) return null

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[60] transition-opacity"
                onClick={onClose}
            />

            {/* Drawer */}
            <div className="fixed right-0 top-0 h-full w-[420px] max-w-[90vw] bg-background border-l border-border shadow-2xl z-[70] flex flex-col animate-in slide-in-from-right duration-300">
                {/* Header */}
                <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/10">
                    <div className="flex items-center gap-2">
                        <Clock size={18} className="text-primary" />
                        <h2 className="text-lg font-semibold">History</h2>
                        {total > 0 && (
                            <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                                {total}
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-1">
                        <button
                            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                            onClick={loadHistory}
                            title="Refresh"
                        >
                            <RefreshCw size={16} className={cn(loading && "animate-spin")} />
                        </button>
                        <button
                            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                            onClick={onClose}
                        >
                            <X size={18} />
                        </button>
                    </div>
                </div>

                {/* Search */}
                <div className="px-4 py-3 border-b border-border">
                    <div className="relative">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                        <input
                            type="text"
                            className="w-full bg-muted/30 border border-border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/50"
                            placeholder="Search by filename..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto">
                    {error && (
                        <div className="mx-4 mt-4 p-3 rounded-lg bg-destructive/10 text-destructive text-sm flex items-center gap-2">
                            <AlertCircle size={14} />
                            {error}
                        </div>
                    )}

                    {loading && items.length === 0 ? (
                        <div className="flex items-center justify-center py-16 text-muted-foreground">
                            <Loader2 size={24} className="animate-spin mr-2" />
                            Loading...
                        </div>
                    ) : filtered.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                            <Clock size={40} className="mb-3 opacity-30" />
                            <p className="text-sm">No history records</p>
                        </div>
                    ) : (
                        <>
                            {/* Recent Section */}
                            {recentItems.length > 0 && (
                                <div className="px-4 pt-4">
                                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-2">
                                        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                                        Recent ({recentItems.length})
                                    </h3>
                                    <div className="space-y-2">
                                        {recentItems.map((item) => (
                                            <HistoryItem
                                                key={`recent-${item.ocr_run_id}`}
                                                item={item}
                                                isRecent
                                                restoring={restoring === item.ocr_run_id}
                                                deleting={deleting === item.ocr_run_id}
                                                onRestore={() => handleRestore(item)}
                                                onDelete={(e) => handleDelete(e, item)}
                                            />
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* History Section */}
                            {historyItems.length > 0 && (
                                <div className="px-4 pt-4 pb-4">
                                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                                        History ({historyItems.length})
                                    </h3>
                                    <div className="space-y-2">
                                        {historyItems.map((item) => (
                                            <HistoryItem
                                                key={`hist-${item.ocr_run_id}`}
                                                item={item}
                                                restoring={restoring === item.ocr_run_id}
                                                deleting={deleting === item.ocr_run_id}
                                                onRestore={() => handleRestore(item)}
                                                onDelete={(e) => handleDelete(e, item)}
                                            />
                                        ))}
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </>
    )
}

function HistoryItem({ item, isRecent = false, restoring, deleting, onRestore, onDelete }) {
    return (
        <button
            className={cn(
                "w-full text-left rounded-lg border border-border p-3 transition-all group",
                "hover:border-primary/40 hover:bg-muted/30 hover:shadow-sm",
                (restoring || deleting) && "opacity-60 pointer-events-none",
                isRecent && "border-green-500/20 bg-green-500/5"
            )}
            onClick={onRestore}
            disabled={restoring || deleting}
        >
            <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                    {/* Title */}
                    <div className="flex items-center gap-2 mb-1">
                        <FileText size={14} className="text-primary flex-shrink-0" />
                        <span className="text-sm font-medium truncate" title={item.document_title}>
                            {item.document_title || "Untitled"}
                        </span>
                    </div>

                    {/* Metadata row */}
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                        <span>{item.page_count || 0} pages</span>
                        <span className="text-border">·</span>
                        <StatusBadge status={item.ocr_status} />
                        {item.has_extraction && (
                            <>
                                <span className="text-border">·</span>
                                <span className="flex items-center gap-1">
                                    <Cpu size={10} />
                                    <StatusBadge status={item.extraction_status} />
                                </span>
                            </>
                        )}
                    </div>

                    {/* Time and tokens */}
                    <div className="flex items-center gap-3 mt-1.5 text-[11px] text-muted-foreground">
                        <span>{timeAgo(item.created_at)}</span>
                        {item.total_tokens > 0 && (
                            <span className="font-mono">
                                {item.total_tokens.toLocaleString()} tokens
                            </span>
                        )}
                        {item.extraction_model && (
                            <span className="px-1 py-0 bg-muted rounded text-[10px]">
                                {item.extraction_model}
                            </span>
                        )}
                    </div>
                </div>

                {/* Arrow / Delete / Loading */}
                <div className="flex items-center gap-1 pt-1 flex-shrink-0">
                    <span
                        className={cn(
                            "p-1 rounded-md opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer",
                            "hover:bg-destructive/10 hover:text-destructive text-muted-foreground/40"
                        )}
                        onClick={onDelete}
                        title="刪除此紀錄"
                        role="button"
                    >
                        {deleting ? (
                            <Loader2 size={14} className="animate-spin" />
                        ) : (
                            <Trash2 size={14} />
                        )}
                    </span>
                    {restoring ? (
                        <Loader2 size={16} className="animate-spin text-primary" />
                    ) : (
                        <ChevronRight size={16} className="text-muted-foreground/40 group-hover:text-primary transition-colors" />
                    )}
                </div>
            </div>
        </button>
    )
}
