"use client"
// app/components/steps/UploadStep.jsx
/**
 * Step 0: Upload PDF (Tailwind CSS)
 * User Mode: 自動觸發 OCR 並跳轉到 Processing 步驟
 */

import { useEffect, useRef } from "react"
import { Upload, File, Loader2 } from "lucide-react"
import { useApp } from "../../context/AppContext"
import { usePdfHandler } from "../../hooks/usePdfHandler"
import { useOcrJob } from "../../hooks/useOcrJob"
import { formatBytes } from "../../utils/formatters"
import { cn } from "../../utils/cn"

export default function UploadStep() {
    const { state, dispatch } = useApp()
    const { file, pdfLoading, pdfPageCount, pdfError, pdfUrl, mode, busy } = state
    const { fileInputRef, handleFileChange } = usePdfHandler()
    const { startOcr } = useOcrJob()

    // 防止重複觸發
    const autoTriggeredRef = useRef(false)

    // User Mode: PDF 解析完成後自動觸發 OCR
    useEffect(() => {
        const isUserMode = mode === "user"
        const pdfReady = file && pdfPageCount && !pdfLoading && !pdfError

        if (isUserMode && pdfReady && !busy && !autoTriggeredRef.current) {
            autoTriggeredRef.current = true
            console.log('[UploadStep] User Mode: Auto-triggering OCR...')

            // 延遲執行以確保 UI 渲染完成
            setTimeout(async () => {
                const success = await startOcr()
                if (success) {
                    // startOcr 內部已經會跳轉到 step 2 (OCR Progress)
                    // 但 User Mode 應該去 Processing step (originalIndex 100)
                    // 需要找到 Processing 在 steps 中的 index
                    dispatch({ type: "SET_STEP_INDEX", payload: 1 }) // Processing 是 User Mode 的第 2 步 (index 1)
                }
            }, 500)
        }
    }, [mode, file, pdfPageCount, pdfLoading, pdfError, busy, startOcr, dispatch])

    // 重置 autoTriggeredRef 當檔案變更時
    useEffect(() => {
        autoTriggeredRef.current = false
    }, [file])

    return (
        <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm">
            <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
                <h3 className="font-semibold leading-none tracking-tight">Upload PDF</h3>
            </div>
            <div className="p-6">
                <div
                    className={cn(
                        "group relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-border p-12 text-center transition-all hover:bg-muted/20 hover:border-primary/50 cursor-pointer",
                        file && "border-primary/50 bg-primary/5"
                    )}
                    onClick={() => fileInputRef.current?.click()}
                >
                    <input
                        type="file"
                        accept="application/pdf"
                        className="hidden"
                        ref={fileInputRef}
                        onChange={handleFileChange}
                    />
                    <div className="flex flex-col items-center gap-3">
                        <div className={cn(
                            "p-4 rounded-full bg-muted transition-colors group-hover:bg-background",
                            file && "bg-background text-primary"
                        )}>
                            <Upload size={28} className="text-muted-foreground group-hover:text-primary transition-colors" />
                        </div>
                        {file ? (
                            <div className="space-y-1">
                                <div className="font-medium text-lg">{file.name}</div>
                                <div className="text-sm text-muted-foreground">{formatBytes(file.size)}</div>
                            </div>
                        ) : (
                            <div className="space-y-1">
                                <div className="font-medium text-lg">Click or Drag PDF Here</div>
                                <div className="text-sm text-muted-foreground">Select a file to begin extraction</div>
                            </div>
                        )}
                    </div>
                </div>

                {file && (
                    <div className="mt-6 animate-in fade-in slide-in-from-top-2 duration-300">
                        {pdfLoading ? (
                            <div className="flex items-center gap-3 text-muted-foreground">
                                <Loader2 size={18} className="animate-spin" />
                                <span>Parsing PDF structure...</span>
                            </div>
                        ) : pdfError ? (
                            <div className="flex items-center gap-2 text-destructive bg-destructive/10 p-3 rounded-md text-sm">
                                <span>{pdfError}</span>
                            </div>
                        ) : (
                            <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg border border-border">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 bg-background rounded-md border border-border">
                                        <File size={20} className="text-primary" />
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="font-medium text-sm">Document Ready</span>
                                        <span className="text-xs text-muted-foreground">
                                            {pdfPageCount ? `${pdfPageCount} Pages` : "Unknown Pages"}
                                        </span>
                                    </div>
                                </div>
                                <span className="inline-flex items-center rounded-full border border-transparent bg-green-500/15 px-2.5 py-0.5 text-xs font-semibold text-green-600">
                                    Ready
                                </span>
                            </div>
                        )}
                        {/* PDF Preview */}
                        {pdfUrl && !pdfLoading && !pdfError && (
                            <div className="mt-4 rounded-lg border border-border bg-muted/20 p-2">
                                <iframe
                                    src={pdfUrl}
                                    className="w-full h-[600px] rounded border border-border bg-white"
                                    title="PDF Preview"
                                />
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}
