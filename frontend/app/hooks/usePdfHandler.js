"use client"
// app/hooks/usePdfHandler.js
/**
 * PDF 檔案處理 Hook
 */

import { useEffect, useRef } from "react"
import { PDFDocument } from "pdf-lib"
import { useApp } from "../context/AppContext"

export function usePdfHandler() {
    const { state, dispatch } = useApp()
    const { file } = state
    const fileInputRef = useRef(null)

    const handleFileChange = (event) => {
        const selected = event.target.files?.[0] || null
        // Reset workflow but keep the new file roughly (logic in reducer needs to be careful)
        // Actually we want to clear everything else. 
        // The reducer RESET_WORKFLOW with keepFile: true keeps the OLD file.
        // So we should RESET_WORKFLOW with keepFile: false, then SET_FILE.

        dispatch({ type: "RESET_WORKFLOW", payload: { keepFile: false } })
        dispatch({ type: "SET_FILE", payload: selected })
    }

    // Parse PDF effect
    useEffect(() => {
        let cancelled = false
        if (!file) {
            dispatch({ type: "SET_PDF_INFO", payload: { pdfUrl: "", pdfPageCount: null, pdfError: "" } })
            return undefined
        }

        const url = URL.createObjectURL(file)
        // Initial loading state
        dispatch({
            type: "SET_PDF_INFO",
            payload: { pdfUrl: url, pdfPageCount: null, pdfError: "", pdfLoading: true }
        })

        const parsePdf = async () => {
            try {
                const arrayBuffer = await file.arrayBuffer()
                const doc = await PDFDocument.load(arrayBuffer, { ignoreEncryption: true })
                if (!cancelled) {
                    dispatch({
                        type: "SET_PDF_INFO",
                        payload: { pdfUrl: url, pdfPageCount: doc.getPageCount(), pdfError: "", pdfLoading: false }
                    })
                }
            } catch (err) {
                if (!cancelled) {
                    dispatch({
                        type: "SET_PDF_INFO",
                        payload: { pdfUrl: url, pdfPageCount: null, pdfError: "Unable to parse PDF pages.", pdfLoading: false }
                    })
                }
            }
        }

        parsePdf()

        return () => {
            cancelled = true
            URL.revokeObjectURL(url)
        }
    }, [file, dispatch])

    return {
        fileInputRef,
        handleFileChange
    }
}
