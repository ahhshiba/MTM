"use client"
// app/components/steps/ExtractionStep.jsx
/**
 * 結構化萃取 Step - 顯示萃取進度和 Token 統計 (Tailwind CSS)
 */

import { useEffect } from "react"
import { Loader2, CheckCircle2, AlertCircle, FileText, Coins, RefreshCw } from "lucide-react"
import { useApp } from "../../context/AppContext"
import { useExtraction } from "../../hooks/useExtraction"
import { formatNumber } from "../../utils/formatters"
import { cn } from "../../utils/cn"

export default function ExtractionStep() {
  const { state, dispatch, computed } = useApp()
  const { extractionRun, extractionStatus, extractionPolling, extractionError, extractionResult } = state
  const { ocrDone } = computed
  const { start, getByOcrRun } = useExtraction()

  const status = extractionStatus?.status || extractionRun?.status || ""
  const normalizedStatus = status.toLowerCase()
  const isRunning = normalizedStatus === "running" || normalizedStatus === "pending"
  const isCompleted = normalizedStatus === "completed"
  const isFailed = normalizedStatus === "failed"

  // Token 統計
  const tokenUsage = extractionStatus || extractionRun || {}
  const totalTokens = tokenUsage.total_tokens || 0
  const promptTokens = tokenUsage.total_prompt_tokens || 0
  const candidateTokens = tokenUsage.total_candidate_tokens || 0

  // 自動開始萃取 (當 OCR 完成且沒有萃取記錄時)
  useEffect(() => {
    if (!ocrDone || extractionRun || extractionPolling) return

    const ocrRunId = state.status?.ocr_run_id || state.job?.ocr_run_id
    if (!ocrRunId) return

    const checkExisting = async () => {
      const existing = await getByOcrRun(ocrRunId)
      if (!existing) {
        await start()
      }
    }

    checkExisting()
  }, [ocrDone, extractionRun, extractionPolling, state.status?.ocr_run_id, state.job?.ocr_run_id, getByOcrRun, start])

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-8">
      <div className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">結構化萃取</h2>
        <p className="text-muted-foreground">
          從 OCR 結果中提取 BOM、尺寸規格、圖片分類等結構化資料
        </p>
      </div>

      {/* 狀態指示 */}
      <div className="flex items-center gap-6 p-6 bg-muted/30 rounded-xl border border-border">
        <div className="flex-shrink-0">
          {isRunning && <Loader2 className="animate-spin text-primary" size={48} />}
          {isCompleted && <CheckCircle2 className="text-green-500" size={48} />}
          {isFailed && <AlertCircle className="text-destructive" size={48} />}
          {!status && <FileText className="text-muted-foreground" size={48} />}
        </div>

        <div className="flex-1 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-semibold">
              {isRunning && "正在萃取..."}
              {isCompleted && "萃取完成"}
              {isFailed && "萃取失敗"}
              {!status && "準備中..."}
            </h3>
            {isRunning && (
              <span className="text-xl font-bold text-primary">
                {Math.round(extractionStatus?.progress || 0)}%
              </span>
            )}
          </div>

          {/* Progress Bar */}
          {isRunning && (
            <div className="w-full bg-secondary h-2.5 rounded-full overflow-hidden relative">
              <div
                className="bg-primary h-2.5 rounded-full transition-all duration-300 ease-in-out relative overflow-hidden"
                style={{ width: `${Math.max(5, Math.min(100, extractionStatus?.progress || 0))}%` }}
              >
                <div className="absolute inset-0 bg-white/30 w-full animate-[shimmer_2s_infinite] -translate-x-full"></div>
              </div>
            </div>
          )}

          <div className="flex items-center gap-2 min-h-[1.5rem]">
            {isRunning && <Loader2 size={14} className="animate-spin text-primary shrink-0" />}
            <p className="text-sm text-muted-foreground">
              {extractionStatus?.message || extractionError || (isCompleted ? "所有步驟已完成" : "等待開始...")}
            </p>
          </div>

          {extractionRun?.extraction_run_id && (
            <p className="text-xs text-muted-foreground font-mono mt-1">
              ID: {extractionRun.extraction_run_id}
            </p>
          )}
        </div>

        {/* 手動重新萃取按鈕 */}
        {(isCompleted || isFailed) && (
          <button
            className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-9 px-4 py-2"
            onClick={() => start()}
            disabled={isRunning}
          >
            <RefreshCw size={14} className="mr-2" />
            重新萃取
          </button>
        )}
      </div>

      {/* Token 統計 */}
      {(isCompleted || totalTokens > 0) && (
        <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm">
          <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
            <h3 className="font-semibold leading-none tracking-tight flex items-center gap-2">
              <Coins size={18} />
              Token 使用統計
            </h3>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-3 gap-4">
              <div className="flex flex-col items-center p-4 bg-muted/50 rounded-lg">
                <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-1">總計</span>
                <span className="text-2xl font-bold font-mono">{formatNumber(totalTokens)}</span>
              </div>
              <div className="flex flex-col items-center p-4 bg-muted/30 rounded-lg">
                <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-1">輸入</span>
                <span className="text-lg font-semibold font-mono">{formatNumber(promptTokens)}</span>
              </div>
              <div className="flex flex-col items-center p-4 bg-muted/30 rounded-lg">
                <span className="text-xs uppercase tracking-wider text-muted-foreground font-medium mb-1">輸出</span>
                <span className="text-lg font-semibold font-mono">{formatNumber(candidateTokens)}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 萃取結果摘要 */}
      {isCompleted && extractionResult?.result && (
        <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm">
          <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
            <h3 className="font-semibold leading-none tracking-tight">萃取結果摘要</h3>
          </div>
          <div className="p-6 space-y-8">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {extractionResult.result.extraction_summary && (
                <>
                  <div className="p-4 bg-muted/20 rounded-lg border border-border/50 text-center">
                    <span className="block text-xs font-medium text-muted-foreground mb-1">區塊數</span>
                    <span className="text-xl font-bold">{extractionResult.result.extraction_summary.sections_detected || 0}</span>
                  </div>
                  <div className="p-4 bg-muted/20 rounded-lg border border-border/50 text-center">
                    <span className="block text-xs font-medium text-muted-foreground mb-1">圖片數</span>
                    <span className="text-xl font-bold">{extractionResult.result.extraction_summary.images_processed || 0}</span>
                  </div>
                  <div className="p-4 bg-muted/20 rounded-lg border border-border/50 text-center">
                    <span className="block text-xs font-medium text-muted-foreground mb-1">Email 記錄</span>
                    <span className="text-xl font-bold">{extractionResult.result.extraction_summary.email_notes || 0}</span>
                  </div>
                  <div className="p-4 bg-muted/20 rounded-lg border border-border/50 text-center">
                    <span className="block text-xs font-medium text-muted-foreground mb-1">作工備註</span>
                    <span className="text-xl font-bold">{extractionResult.result.extraction_summary.construction_notes || 0}</span>
                  </div>
                </>
              )}
            </div>

            {/* 基本資訊 */}
            {extractionResult.result.basic_info && (
              <div className="pt-6 border-t border-border">
                <h4 className="font-medium mb-4">基本資訊</h4>
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4 text-sm">
                  {extractionResult.result.basic_info.style_no?.original && (
                    <div className="flex justify-between sm:justify-start sm:gap-4 border-b border-border/50 pb-2 sm:border-none sm:pb-0">
                      <dt className="text-muted-foreground min-w-[60px]">款號</dt>
                      <dd className="font-medium">{extractionResult.result.basic_info.style_no.original}</dd>
                    </div>
                  )}
                  {extractionResult.result.basic_info.season?.original && (
                    <div className="flex justify-between sm:justify-start sm:gap-4 border-b border-border/50 pb-2 sm:border-none sm:pb-0">
                      <dt className="text-muted-foreground min-w-[60px]">季節</dt>
                      <dd className="font-medium">{extractionResult.result.basic_info.season.original}</dd>
                    </div>
                  )}
                  {extractionResult.result.basic_info.brand?.original && (
                    <div className="flex justify-between sm:justify-start sm:gap-4 border-b border-border/50 pb-2 sm:border-none sm:pb-0">
                      <dt className="text-muted-foreground min-w-[60px]">品牌</dt>
                      <dd className="font-medium">{extractionResult.result.basic_info.brand.original}</dd>
                    </div>
                  )}
                </dl>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
