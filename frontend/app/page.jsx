"use client"

import { useApp } from "./context/AppContext"
import { getStepsForMode } from "./components/StepNav"
import StepNav from "./components/StepNav"
import ModeSwitch from "./components/ModeSwitch"
import { useState, useEffect } from "react"

// Steps
import UploadStep from "./components/steps/UploadStep"
import StartOcrStep from "./components/steps/StartOcrStep"
import OcrProgressStep from "./components/steps/OcrProgressStep"
import ImageSelectionStep from "./components/steps/ImageSelectionStep"
import VlmChatStep from "./components/steps/VlmChatStep"
import ProcessingStep from "./components/steps/ProcessingStep"
import FinalReviewStep from "./components/steps/FinalReviewStep"
import ExtractionStep from "./components/steps/ExtractionStep"
import PreviewStep from "./components/steps/PreviewStep"

import { RotateCcw, PanelLeftClose, PanelLeft, Clock, ShieldAlert, ShieldX, Copy, Check, Upload, Loader2 } from "lucide-react"
import { cn } from "./utils/cn"
import HistoryDrawer from "./components/HistoryDrawer"
import { fetchLicenseStatus, fetchFingerprint, uploadLicense } from "./utils/api"

export default function Page() {
  const { state, dispatch } = useApp()
  const { mode, stepIndex, job, status } = state

  const isUserMode = mode === "user"
  const steps = getStepsForMode(isUserMode)
  const currentStep = steps[stepIndex] || steps[0]

  // 側邊欄收合狀態
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  // 歷史抽屜狀態
  const [historyOpen, setHistoryOpen] = useState(false)
  // License 狀態
  const [licenseStatus, setLicenseStatus] = useState(null)
  // 指紋
  const [fingerprint, setFingerprint] = useState(null)
  const [copied, setCopied] = useState(false)
  // 上傳
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState("")
  const fileInputRef = useState(null)

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const { ok, data } = await fetchLicenseStatus()
        if (cancelled) return
        if (ok) {
          setLicenseStatus(data)
        } else {
          // 後端有回應但非 200 → 當作 invalid
          setLicenseStatus({ status: "invalid", is_expired: true })
        }
      } catch {
        // 後端還沒起來 → 3 秒後重試
        if (!cancelled) setTimeout(check, 3000)
      }
    }
    check()
    return () => { cancelled = true }
  }, [])

  // 當 license 無效/到期時，自動載入指紋
  const isLicenseExpired = licenseStatus?.is_expired === true
  const isHistoryOnly = licenseStatus?.is_history_only === true
  const isLicenseActive = licenseStatus?.is_active === true || licenseStatus === null

  useEffect(() => {
    if (isLicenseExpired) {
      fetchFingerprint().then(({ ok, data }) => {
        if (ok) setFingerprint(data)
      }).catch(() => { })
    }
  }, [isLicenseExpired])

  const handleCopyFingerprint = async () => {
    if (!fingerprint) return
    const text = JSON.stringify({
      fingerprint: fingerprint.fingerprint,
      component_hashes: fingerprint.component_hashes,
    }, null, 2)
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleUploadLicense = async (file) => {
    if (!file || !file.name.endsWith(".lic")) {
      setUploadMsg("error:請上傳 .lic 檔案")
      return
    }
    setUploading(true)
    setUploadMsg("")
    try {
      const { ok, data } = await uploadLicense(file)
      if (ok && data.is_active) {
        setUploadMsg("success:授權啟用成功！重新載入中...")
        setTimeout(() => window.location.reload(), 1500)
      } else if (ok) {
        setUploadMsg(`warn:License 已上傳，但狀態為: ${data.status}`)
        setLicenseStatus(data)
      } else {
        setUploadMsg(`error:上傳失敗: ${data?.detail || "未知錯誤"}`)
      }
    } catch (e) {
      setUploadMsg(`error:上傳失敗: ${e.message}`)
    } finally {
      setUploading(false)
    }
  }

  const handleStepClick = (index) => {
    dispatch({ type: "SET_STEP_INDEX", payload: index })
  }

  const handleReset = () => {
    if (confirm("Reset everything?")) {
      dispatch({ type: "RESET_WORKFLOW", payload: { keepFile: false } })
    }
  }

  // License 完全到期 / 無效 — 鎖定畫面（含指紋 + 上傳）
  if (isLicenseExpired) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-background text-foreground">
        <div className="text-center max-w-lg p-8">
          <ShieldX size={56} className="mx-auto mb-5 text-destructive opacity-80" />
          <h1 className="text-2xl font-bold mb-2">
            {licenseStatus?.status === "invalid" ? "系統尚未啟用" : "授權已到期"}
          </h1>
          <p className="text-muted-foreground mb-6 text-sm">
            {licenseStatus?.status === "tampered"
              ? "偵測到系統時間異常，服務已鎖定。請聯繫供應商。"
              : licenseStatus?.status === "invalid"
                ? "請將以下啟用碼傳給供應商，取得授權檔案後上傳即可啟用。"
                : "您的軟體授權已到期，請聯繫供應商續約。"}
          </p>

          {/* 指紋顯示 + 複製 */}
          {fingerprint && (
            <div className="mb-6">
              <p className="text-xs text-muted-foreground mb-2">啟用碼（請傳給供應商）：</p>
              <div className="flex items-center gap-2 bg-muted/30 border border-border rounded-lg p-3">
                <code className="text-xs font-mono text-foreground flex-1 text-left break-all select-all">
                  {fingerprint.fingerprint}
                </code>
                <button
                  onClick={handleCopyFingerprint}
                  className="shrink-0 p-2 rounded-md hover:bg-muted transition-colors"
                  title="複製完整啟用資訊"
                >
                  {copied
                    ? <Check size={16} className="text-green-500" />
                    : <Copy size={16} className="text-muted-foreground" />
                  }
                </button>
              </div>
              {copied && (
                <p className="text-xs text-green-500 mt-1">已複製到剪貼簿 ✓</p>
              )}
            </div>
          )}

          {/* License 上傳 */}
          <div className="mb-4">
            <p className="text-xs text-muted-foreground mb-2">收到授權檔後：</p>
            <label
              className={cn(
                "flex flex-col items-center gap-2 p-6 border-2 border-dashed rounded-lg cursor-pointer transition-colors",
                "border-border hover:border-primary/50 hover:bg-muted/20",
                uploading && "pointer-events-none opacity-50"
              )}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation() }}
              onDrop={(e) => {
                e.preventDefault()
                e.stopPropagation()
                const file = e.dataTransfer.files[0]
                if (file) handleUploadLicense(file)
              }}
            >
              <input
                type="file"
                accept=".lic"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files[0]
                  if (file) handleUploadLicense(file)
                }}
              />
              {uploading
                ? <Loader2 size={24} className="animate-spin text-primary" />
                : <Upload size={24} className="text-muted-foreground" />
              }
              <span className="text-sm text-muted-foreground">
                {uploading ? "上傳中..." : "點擊或拖曳 license.lic 到此處"}
              </span>
            </label>
          </div>

          {uploadMsg && (
            <p className={cn("text-sm mb-2", uploadMsg.startsWith("success:") ? "text-green-500" : uploadMsg.startsWith("warn:") ? "text-amber-500" : "text-destructive")}>
              {uploadMsg.replace(/^(success:|warn:|error:)/, "")}
            </p>
          )}

          {licenseStatus?.license_info?.customer && (
            <p className="text-xs text-muted-foreground mt-4 font-mono">
              客戶: {licenseStatus.license_info.customer}
            </p>
          )}
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="flex flex-col h-screen bg-background text-foreground overflow-hidden font-sans">
        <header className="h-14 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 flex items-center justify-between px-6 shrink-0 z-50">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight text-foreground">
              MTM OCR Pipeline
            </h1>
          </div>

          <div className="flex items-center gap-4">
            <button
              className={cn(
                "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
                "h-9 px-3"
              )}
              onClick={() => setHistoryOpen(true)}
              title="History"
            >
              <Clock className="mr-2 h-4 w-4" />
              History
            </button>

            <button
              className={cn(
                "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
                "h-9 px-3"
              )}
              onClick={handleReset}
              title="Reset Workflow"
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Reset
            </button>

            <div className="h-6 w-px bg-border mx-1" />

            <ModeSwitch />
          </div>
        </header>

        {/* License History-Only Banner */}
        {isHistoryOnly && (
          <div className="bg-amber-500/15 border-b border-amber-500/30 px-6 py-2.5 flex items-center gap-3 shrink-0">
            <ShieldAlert size={16} className="text-amber-500 flex-shrink-0" />
            <span className="text-sm text-amber-200">
              <strong>授權已到期</strong> — 僅可調閱歷史執行紀錄，新的 OCR / Extraction 功能已停用。請聯繫供應商續約。
            </span>
          </div>
        )}

        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar */}
          <aside className={cn(
            "border-r border-border bg-muted/10 flex flex-col shrink-0 transition-all duration-300",
            sidebarCollapsed ? "w-16" : "w-[280px]"
          )}>
            {/* 收合按鈕 */}
            <div className="flex items-center justify-end px-2 py-2 border-b border-border">
              <button
                className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
                title={sidebarCollapsed ? "展開側邊欄" : "收合側邊欄"}
              >
                {sidebarCollapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
              </button>
            </div>

            <div className="flex-1 overflow-y-auto py-2">
              <StepNav
                steps={steps}
                currentIndex={stepIndex}
                onStepClick={handleStepClick}
                collapsed={sidebarCollapsed}
              />
            </div>

            {!sidebarCollapsed && (
              <div className="p-4 border-t border-border bg-muted/5">
                <div className="text-xs text-muted-foreground space-y-1">
                  {job?.local_job_id && (
                    <div className="font-mono truncate" title={job.local_job_id}>
                      Job: {job.local_job_id.slice(0, 8)}...
                    </div>
                  )}
                  {status?.status && (
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                      <span className="capitalize">{status.status}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </aside>

          {/* Main Content */}
          <main className="flex-1 flex flex-col overflow-hidden bg-muted/5 relative">
            <div className="flex-1 overflow-y-auto w-full max-w-7xl mx-auto p-6">
              {currentStep.originalIndex === 0 && <UploadStep />}
              {currentStep.originalIndex === 1 && <StartOcrStep />}
              {currentStep.originalIndex === 2 && <OcrProgressStep />}
              {currentStep.originalIndex === 3 && <ImageSelectionStep />}
              {currentStep.originalIndex === 4 && <VlmChatStep />}
              {currentStep.originalIndex === 6 && <ExtractionStep />}
              {currentStep.originalIndex === 7 && <PreviewStep />}
              {currentStep.originalIndex === 100 && <ProcessingStep />}
              {currentStep.originalIndex === 5 && <FinalReviewStep />}
            </div>

            {/* Navigation Footer */}
            <div className="border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 p-4 shrink-0">
              <div className="w-full max-w-7xl mx-auto flex items-center justify-between">
                <button
                  className={cn(
                    "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                    "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
                    "h-9 px-4"
                  )}
                  onClick={() => dispatch({ type: "SET_STEP_INDEX", payload: Math.max(0, stepIndex - 1) })}
                  disabled={stepIndex === 0}
                >
                  ← Previous
                </button>

                <div className="text-sm text-muted-foreground">
                  Step {stepIndex + 1} of {steps.length}: <span className="font-medium text-foreground">{currentStep.label}</span>
                </div>

                <button
                  className={cn(
                    "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                    "bg-primary text-primary-foreground shadow hover:bg-primary/90",
                    "h-9 px-4"
                  )}
                  onClick={() => dispatch({ type: "SET_STEP_INDEX", payload: Math.min(steps.length - 1, stepIndex + 1) })}
                  disabled={stepIndex >= steps.length - 1}
                >
                  Next →
                </button>
              </div>
            </div>
          </main>
        </div>
      </div>

      {/* History Drawer */}
      <HistoryDrawer isOpen={historyOpen} onClose={() => setHistoryOpen(false)} />
    </>
  )
}
