"use client"
// app/hooks/useExtraction.js
/**
 * 結構化萃取處理 Hook
 */

import { useEffect, useCallback } from "react"
import { useApp } from "../context/AppContext"
import { startExtraction, fetchExtractionStatus, fetchExtractionResult, fetchExtractionByOcrRun } from "../utils/api"

export function useExtraction() {
    const { state, dispatch, computed } = useApp()
    const { extractionRun, extractionPolling, status } = state
    const { ocrDone } = computed

    // 開始結構化萃取
    const start = useCallback(async () => {
        const ocrRunId = status?.ocr_run_id || state.job?.ocr_run_id || state.status?.ocr_run_id
        const documentId = status?.document_id || state.job?.document_id || state.status?.document_id

        console.log('[useExtraction] start() called with:', {
            ocrRunId,
            documentId,
            status,
            stateJob: state.job,
            stateStatus: state.status,
        })

        if (!ocrRunId || !documentId) {
            dispatch({ type: "SET_EXTRACTION_ERROR", payload: "OCR Run ID or Document ID not available" })
            return false
        }

        dispatch({ type: "SET_EXTRACTION_ERROR", payload: "" })

        try {
            const { ok, data } = await startExtraction({
                ocr_run_id: ocrRunId,
                document_id: documentId,
                mode: state.mode,
                model: "gemini-2.5-flash",
            })

            if (!ok) {
                dispatch({ type: "SET_EXTRACTION_ERROR", payload: data?.detail || "Failed to start extraction" })
                return false
            }

            dispatch({ type: "SET_EXTRACTION_RUN", payload: data })
            dispatch({ type: "SET_EXTRACTION_STATUS", payload: data })
            dispatch({ type: "SET_EXTRACTION_POLLING", payload: true })
            return true
        } catch (err) {
            dispatch({ type: "SET_EXTRACTION_ERROR", payload: "Failed to start extraction" })
            return false
        }
    }, [status, state.job, state.mode, dispatch])

    // 取得萃取狀態
    const getStatus = useCallback(async (extractionId) => {
        const id = extractionId || extractionRun?.extraction_run_id
        if (!id) return null

        const { ok, data } = await fetchExtractionStatus(id)
        if (ok) {
            dispatch({ type: "SET_EXTRACTION_STATUS", payload: data })
            return data
        }
        return null
    }, [extractionRun, dispatch])

    // 取得萃取結果
    const getResult = useCallback(async (extractionId) => {
        const id = extractionId || extractionRun?.extraction_run_id
        if (!id) return null

        const { ok, data } = await fetchExtractionResult(id)
        if (ok) {
            dispatch({ type: "SET_EXTRACTION_RESULT", payload: data })
            return data
        }
        return null
    }, [extractionRun, dispatch])

    // 根據 OCR Run ID 取得萃取記錄
    const getByOcrRun = useCallback(async (ocrRunId) => {
        const { ok, data } = await fetchExtractionByOcrRun(ocrRunId)
        if (ok && data.extraction_run) {
            dispatch({ type: "SET_EXTRACTION_RUN", payload: data.extraction_run })
            dispatch({ type: "SET_EXTRACTION_STATUS", payload: data.extraction_run })

            // Auto-start polling if running
            const s = (data.extraction_run.status || "").toLowerCase()
            if (s === "running" || s === "pending") {
                dispatch({ type: "SET_EXTRACTION_POLLING", payload: true })
            }

            return data.extraction_run
        }
        return null
    }, [dispatch])

    // 輪詢萃取狀態
    useEffect(() => {
        let intervalId = null;

        // 如果 polling 為 true，嘗試輪詢
        if (extractionPolling) {
            console.log("[useExtraction] Polling active...", {
                extractionId: extractionRun?.extraction_run_id,
                ocrRunId: status?.ocr_run_id
            });

            // 1. 如果有 Extraction ID，直接查狀態
            if (extractionRun?.extraction_run_id) {
                intervalId = setInterval(async () => {
                    const latest = await getStatus(extractionRun.extraction_run_id);

                    if (latest) {
                        const s = latest.status?.toLowerCase();
                        if (s === "completed" || s === "failed") {
                            dispatch({ type: "SET_EXTRACTION_POLLING", payload: false });
                            if (s === "completed") {
                                getResult(extractionRun.extraction_run_id);
                            }
                        }
                    }
                }, 2000);
            }
            // 2. 如果只有 OCR Run ID (剛開始尚未建立 Extraction Run)，嘗試透過 OCR Run ID 查找
            else if (status?.ocr_run_id || state.job?.ocr_run_id) {
                const targetOcrId = status?.ocr_run_id || state.job?.ocr_run_id;
                intervalId = setInterval(async () => {
                    const run = await getByOcrRun(targetOcrId);
                    // 如果找到了 extraction run，下次 loop 就會進入上面那個 if block (因為 state 更新了)
                    if (run?.extraction_run_id) {
                        console.log("[useExtraction] Found extraction run:", run.extraction_run_id);
                    }
                }, 2000);
            }
        }

        return () => {
            if (intervalId) clearInterval(intervalId);
        };
    }, [
        extractionPolling,
        extractionRun?.extraction_run_id,
        status?.ocr_run_id,
        state.job?.ocr_run_id,
        getStatus,
        getResult,
        getByOcrRun,
        dispatch
    ]); // Dependencies verified consistent

    return {
        start,
        getStatus,
        getResult,
        getByOcrRun,
    }
}
