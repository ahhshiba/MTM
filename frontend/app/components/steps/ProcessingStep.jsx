"use client"
// app/components/steps/ProcessingStep.jsx
/**
 * Step 100: Processing (User Mode only) - Tailwind CSS
 * Shows combined progress of OCR and Extraction
 * Auto-triggers extraction after OCR completes
 */

import { useEffect, useRef, useCallback, useState } from "react"
import { Loader2, CheckCircle2, AlertCircle, Cpu } from "lucide-react"
import { useApp } from "../../context/AppContext"
import { useExtraction } from "../../hooks/useExtraction"
import { useOcrJob } from "../../hooks/useOcrJob"
import { cn } from "../../utils/cn"

export default function ProcessingStep() {
    const { state, dispatch, computed } = useApp()
    const { extractionStatus, extractionError, extractionResult, polling } = state
    const { ocrDone, ocrFailed, progress } = computed
    const { start: startExtraction, getResult } = useExtraction()
    const { refresh } = useOcrJob()

    // OCR Polling
    useEffect(() => {
        let interval
        if (polling && !ocrDone && !ocrFailed) {
            console.log('[ProcessingStep] OCR Polling active...')
            interval = setInterval(() => {
                refresh()
            }, 2000)
        }
        return () => clearInterval(interval)
    }, [polling, ocrDone, ocrFailed, refresh])

    // 防止重複觸發萃取
    const extractionTriggeredRef = useRef(false)

    // OCR Status
    const isOcrRunning = !ocrDone && !ocrFailed
    // const ocrPercent = Math.round(progress * 100) // Real progress (mostly 0)

    // Fake progress for OCR (Requested by user)
    // Simulates progress up to 90% while running, then jumps to 100% when done
    const [fakeOcrProgress, setFakeOcrProgress] = useState(0)

    useEffect(() => {
        let interval
        if (isOcrRunning) {
            interval = setInterval(() => {
                setFakeOcrProgress(prev => {
                    if (prev >= 90) return prev
                    // Increment logic: fast at start, slowing down
                    const remaining = 90 - prev
                    const increment = Math.max(0.1, remaining / 60)
                    return Math.min(90, prev + increment)
                })
            }, 500)
        } else if (ocrDone) {
            setFakeOcrProgress(100)
        }
        return () => clearInterval(interval)
    }, [isOcrRunning, ocrDone])

    const ocrPercent = ocrDone ? 100 : (ocrFailed ? 0 : Math.round(fakeOcrProgress))

    // Extraction Status
    const extractionStatusText = extractionStatus?.status || ""
    const isExtractionRunning = ["pending", "running"].includes(extractionStatusText.toLowerCase())
    const isExtractionDone = extractionStatusText.toLowerCase() === "completed"
    const isExtractionFailed = extractionStatusText.toLowerCase() === "failed"
    const extractionProgress = extractionStatus?.progress || 0
    const extractionPercent = Math.round(extractionProgress * 100)

    // Smooth animation for Extraction Progress
    const [visualExtractionPercent, setVisualExtractionPercent] = useState(0)

    useEffect(() => {
        if (Math.abs(visualExtractionPercent - extractionPercent) < 0.5) {
            if (visualExtractionPercent !== extractionPercent) setVisualExtractionPercent(extractionPercent)
            return
        }

        const interval = setInterval(() => {
            setVisualExtractionPercent(prev => {
                const diff = extractionPercent - prev
                if (Math.abs(diff) < 0.5) {
                    clearInterval(interval)
                    return extractionPercent
                }
                // Easing factor: moves 5% of the distance per tick (50ms)
                // Creates smooth deceleration
                return prev + diff * 0.05
            })
        }, 30)

        return () => clearInterval(interval)
    }, [extractionPercent, visualExtractionPercent])

    const displayExtractionPercent = Math.round(visualExtractionPercent)

    // Debug - log state every render
    console.log('[ProcessingStep] Render:', {
        ocrDone,
        ocrPercent,
        extractionTriggered: extractionTriggeredRef.current,
        extractionStatus: extractionStatusText,
        extractionPercent,
        hasResult: !!extractionResult
    })

    // Wrap startExtraction to avoid dependency issues
    const triggerExtraction = useCallback(() => {
        if (!extractionTriggeredRef.current) {
            extractionTriggeredRef.current = true
            console.log('[ProcessingStep] ✓ OCR done, auto-triggering extraction...')

            setTimeout(async () => {
                const success = await startExtraction()
                console.log('[ProcessingStep] Extraction started:', success)
            }, 1000)
        }
    }, [startExtraction])

    // Auto-trigger extraction after OCR completes
    useEffect(() => {
        console.log('[ProcessingStep] Extraction trigger check:', {
            ocrDone,
            extractionTriggered: extractionTriggeredRef.current,
            hasExtractionStatus: !!extractionStatus
        })

        if (ocrDone && !extractionTriggeredRef.current && !extractionStatus) {
            triggerExtraction()
        }
    }, [ocrDone, extractionStatus, triggerExtraction])

    // Reset trigger when OCR restarts
    useEffect(() => {
        if (!ocrDone) {
            console.log('[ProcessingStep] Resetting extraction trigger (OCR not done)')
            extractionTriggeredRef.current = false
        }
    }, [ocrDone])

    // Auto-fetch result when extraction completes
    useEffect(() => {
        if (isExtractionDone && !extractionResult) {
            console.log('[ProcessingStep] ✓ Extraction done, fetching result...')
            getResult()
        }
    }, [isExtractionDone, extractionResult, getResult])

    // Track previous status to prevent loop when navigating back
    const prevStatusRef = useRef(extractionStatusText)

    // Auto-navigate to Preview when result is ready AND we just finished (not already finished)
    useEffect(() => {
        if (isExtractionDone && extractionResult) {
            // Only navigate if we triggered the transition (prev was not completed)
            // Or if we are just verifying, maybe we want to allow user to go back.
            // Using ref initialized to current status on mount prevents auto-jump on revisit.

            if (prevStatusRef.current !== "completed") {
                console.log('[ProcessingStep] ✓ Extraction JUST completed, navigating to Preview...')
                setTimeout(() => {
                    dispatch({ type: "SET_STEP_INDEX", payload: 2 })
                }, 1500)
            } else {
                console.log('[ProcessingStep] Extraction already completed on mount, skipping auto-nav.')
            }
        }
        // Update ref
        prevStatusRef.current = extractionStatusText
    }, [isExtractionDone, extractionResult, dispatch, extractionStatusText])

    return (
        <div className="max-w-3xl mx-auto py-10">
            <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm overflow-hidden">
                <div className="flex flex-col space-y-1.5 p-6 border-b border-border bg-muted/5">
                    <h3 className="font-semibold leading-none tracking-tight text-xl">Processing Document</h3>
                    <p className="text-sm text-muted-foreground">Please wait while we analyze the document and extract structured data.</p>
                </div>

                <div className="p-8 space-y-8">
                    {/* OCR Section */}
                    <div className="flex gap-5">
                        <div className="flex flex-col items-center">
                            <div className={cn(
                                "relative flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all z-10 bg-card",
                                ocrDone ? "border-green-500 text-green-500" :
                                    ocrFailed ? "border-destructive text-destructive" :
                                        "border-primary text-primary"
                            )}>
                                {ocrDone ? <CheckCircle2 size={20} /> :
                                    ocrFailed ? <AlertCircle size={20} /> :
                                        <Loader2 size={20} className="animate-spin" />}
                            </div>
                            <div className="w-0.5 h-full bg-border -my-2" />
                        </div>

                        <div className="flex-1 pb-8">
                            <div className="flex justify-between items-center mb-2">
                                <h4 className="font-medium text-foreground">Step 1: Analyzing Layout (OCR)</h4>
                                <span className="text-sm font-medium text-muted-foreground">{ocrPercent}%</span>
                            </div>
                            <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                                <div
                                    className={cn(
                                        "h-full bg-primary transition-all duration-500 ease-in-out",
                                        ocrDone && "bg-green-500",
                                        ocrFailed && "bg-destructive"
                                    )}
                                    style={{ width: `${ocrPercent}%` }}
                                />
                            </div>
                            {state.error && <p className="text-destructive text-sm mt-2 flex items-center gap-1"><AlertCircle size={12} /> {state.error}</p>}
                            <p className="text-sm text-muted-foreground mt-2">Extracting text, identifying images, and analyzing page structure.</p>
                        </div>
                    </div>

                    {/* Extraction Section */}
                    <div className={cn("flex gap-5", !ocrDone && "opacity-50 grayscale")}>
                        <div className="flex flex-col items-center">
                            <div className={cn(
                                "relative flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all z-10 bg-card",
                                isExtractionDone ? "border-green-500 text-green-500" :
                                    isExtractionFailed ? "border-destructive text-destructive" :
                                        isExtractionRunning ? "border-primary text-primary" : "border-muted-foreground/30 text-muted-foreground/30"
                            )}>
                                {isExtractionDone ? <CheckCircle2 size={20} /> :
                                    isExtractionFailed ? <AlertCircle size={20} /> :
                                        isExtractionRunning ? <Loader2 size={20} className="animate-spin" /> :
                                            <Cpu size={16} className="opacity-50" />}
                            </div>
                        </div>

                        <div className="flex-1">
                            <div className="flex justify-between items-center mb-2">
                                <h4 className="font-medium text-foreground">Step 2: Extracting Structured Data</h4>
                                <span className="text-sm font-medium text-muted-foreground">{displayExtractionPercent}%</span>
                            </div>
                            <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                                <div
                                    className={cn(
                                        "h-full bg-primary transition-all duration-500 ease-in-out",
                                        isExtractionDone && "bg-green-500",
                                        isExtractionFailed && "bg-destructive"
                                    )}
                                    style={{ width: `${displayExtractionPercent}%` }}
                                />
                            </div>
                            {extractionError && <p className="text-destructive text-sm mt-2 flex items-center gap-1"><AlertCircle size={12} /> {extractionError}</p>}
                            <p className="text-sm text-muted-foreground mt-2">
                                {isExtractionRunning
                                    ? (extractionStatus?.message || "Extracting BOM, measurements, and specifications using AI...")
                                    : "Extracting BOM, measurements, and specifications using AI."}
                            </p>
                        </div>
                    </div>

                    {/* Summary */}
                    {ocrDone && isExtractionDone && (
                        <div className="mt-8 rounded-lg border border-green-500/20 bg-green-500/10 p-6 text-center animate-in fade-in zoom-in-95 duration-500">
                            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/30 mb-4">
                                <CheckCircle2 className="h-6 w-6 text-green-600 dark:text-green-400" />
                            </div>
                            <h3 className="text-lg font-medium text-green-800 dark:text-green-300">Processing Completed</h3>
                            <p className="mt-2 text-sm text-green-700 dark:text-green-400/80">
                                Document has been analyzed and structured data has been extracted.
                            </p>
                            <div className="mt-6">
                                <p className="text-sm text-muted-foreground animate-pulse">Navigating to preview...</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
