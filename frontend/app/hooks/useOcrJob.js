"use client"
// app/hooks/useOcrJob.js
/**
 * OCR 任務處理 Hook
 */

import { useEffect, useCallback } from "react"
import { useApp } from "../context/AppContext"
import { createJob, fetchJob, fetchResults, fetchArtifactMd, fetchArtifactJson } from "../utils/api"

export function useOcrJob() {
    const { state, dispatch, computed } = useApp()
    const { job, polling, busy } = state
    const { ocrDone } = computed

    // 建立 OCR 任務
    const startOcr = useCallback(async () => {
        if (!state.file || busy) return false

        dispatch({ type: "SET_BUSY", payload: true })
        dispatch({ type: "SET_ERROR", payload: "" })
        dispatch({ type: "SET_RESULTS", payload: null })
        dispatch({ type: "SET_RESULTS_ERROR", payload: "" })
        dispatch({ type: "SET_SELECTED_IMAGE_IDS", payload: [] })
        dispatch({ type: "SET_SESSION_BY_IMAGE", payload: {} })
        dispatch({ type: "SET_MESSAGES_BY_SESSION", payload: {} })
        dispatch({ type: "SET_SESSION_LOCKS", payload: {} })
        dispatch({ type: "SET_VLM_ERROR", payload: "" })

        try {
            const { ok, data } = await createJob(state.file)

            if (!ok) {
                dispatch({ type: "SET_ERROR", payload: data?.detail || "Upload failed." })
                dispatch({ type: "SET_BUSY", payload: false })
                return false
            }

            if (!data?.local_job_id || data.local_job_id === "undefined") {
                dispatch({ type: "SET_ERROR", payload: "Missing local_job_id from server response." })
                dispatch({ type: "SET_BUSY", payload: false })
                return false
            }

            dispatch({ type: "SET_JOB", payload: data })
            dispatch({ type: "SET_STATUS", payload: data })
            dispatch({ type: "SET_POLLING", payload: true })
            dispatch({ type: "SET_STEP_INDEX", payload: 2 })
            dispatch({ type: "SET_BUSY", payload: false })
            return true
        } catch (err) {
            dispatch({ type: "SET_ERROR", payload: "Upload failed. Check server logs." })
            dispatch({ type: "SET_BUSY", payload: false })
            return false
        }
    }, [state.file, busy, dispatch])

    // 手動重新整理狀態
    const refresh = useCallback(async () => {
        if (!job?.local_job_id || job.local_job_id === "undefined") return

        dispatch({ type: "SET_ERROR", payload: "" })

        try {
            const { ok, data } = await fetchJob(job.local_job_id)
            if (!ok) {
                dispatch({ type: "SET_ERROR", payload: data?.detail || "Failed to fetch status." })
                return
            }
            dispatch({ type: "SET_STATUS", payload: data })
        } catch (err) {
            dispatch({ type: "SET_ERROR", payload: "Network error while fetching status." })
        }
    }, [job?.local_job_id, dispatch])

    // 載入 OCR 結果
    const loadResults = useCallback(async () => {
        if (!job?.local_job_id || job.local_job_id === "undefined") return

        dispatch({ type: "SET_RESULTS_LOADING", payload: true })
        dispatch({ type: "SET_RESULTS_ERROR", payload: "" })

        try {
            const { ok, data } = await fetchResults(job.local_job_id)
            if (!ok) {
                dispatch({ type: "SET_RESULTS_ERROR", payload: data?.detail || "Failed to fetch OCR results." })
                dispatch({ type: "SET_RESULTS_LOADING", payload: false })
                return
            }
            dispatch({ type: "SET_RESULTS", payload: data })
            if (data?.pages?.length) {
                dispatch({ type: "SET_ACTIVE_PAGE_ID", payload: data.pages[0].page_id })
            }
        } catch {
            dispatch({ type: "SET_RESULTS_ERROR", payload: "Network error while fetching results." })
        } finally {
            dispatch({ type: "SET_RESULTS_LOADING", payload: false })
        }
    }, [job?.local_job_id, dispatch])

    // 載入 Artifact Markdown
    const loadArtifactMarkdown = useCallback(async (artifactId) => {
        if (!artifactId || Object.prototype.hasOwnProperty.call(state.artifactMarkdownById, artifactId)) {
            return
        }

        const { ok, text } = await fetchArtifactMd(artifactId)
        dispatch({
            type: "SET_ARTIFACT_MARKDOWN",
            payload: { id: artifactId, markdown: ok ? text : "" }
        })
    }, [state.artifactMarkdownById, dispatch])

    // 載入 Artifact JSON
    const loadArtifactJson = useCallback(async (artifactId) => {
        if (!artifactId || Object.prototype.hasOwnProperty.call(state.artifactJsonById || {}, artifactId)) {
            return
        }

        const { ok, data } = await fetchArtifactJson(artifactId)
        dispatch({
            type: "SET_ARTIFACT_JSON",
            payload: { id: artifactId, json: ok ? data : null }
        })
    }, [state.artifactJsonById, dispatch])

    // 輪詢狀態
    useEffect(() => {
        if (!polling || !job?.local_job_id || job.local_job_id === "undefined") {
            return
        }

        const tick = async () => {
            try {
                const { ok, data } = await fetchJob(job.local_job_id)
                if (!ok) {
                    dispatch({ type: "SET_ERROR", payload: data?.detail || "Failed to fetch status." })
                    dispatch({ type: "SET_POLLING", payload: false })
                    return
                }
                dispatch({ type: "SET_STATUS", payload: data })

                const done =
                    ["succeeded", "done", "completed", "failed", "error", "canceled"].includes(
                        (data?.status || "").toLowerCase()
                    ) || data?.progress >= 1

                if (done) {
                    dispatch({ type: "SET_POLLING", payload: false })
                }
            } catch {
                dispatch({ type: "SET_ERROR", payload: "Network error while polling." })
                dispatch({ type: "SET_POLLING", payload: false })
            }
        }

        tick()
        const timer = setInterval(tick, 2000)
        return () => clearInterval(timer)
    }, [polling, job?.local_job_id, dispatch])

    // OCR 完成後自動載入結果
    useEffect(() => {
        if (ocrDone && job?.local_job_id && !state.resultsLoading && !state.results) {
            loadResults()
        }
    }, [ocrDone, job?.local_job_id, state.resultsLoading, state.results, loadResults])

    return {
        startOcr,
        refresh,
        loadResults,
        loadArtifactMarkdown,
        loadArtifactJson,
    }
}
