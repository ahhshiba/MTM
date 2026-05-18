"use client"
// app/components/steps/StartOcrStep.jsx
/**
 * Step 1: Start OCR (Tailwind CSS)
 */

import { Play, AlertCircle, Loader2 } from "lucide-react"
import { useApp } from "../../context/AppContext"
import { useOcrJob } from "../../hooks/useOcrJob"
import { cn } from "../../utils/cn"

export default function StartOcrStep() {
    const { state } = useApp()
    const { busy, error } = state
    const { startOcr } = useOcrJob()

    return (
        <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm max-w-2xl mx-auto">
            <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
                <h3 className="font-semibold leading-none tracking-tight">Start OCR Job</h3>
            </div>
            <div className="p-6 space-y-6">
                <div className="bg-muted/30 p-4 rounded-lg text-sm text-muted-foreground">
                    This will upload the PDF to the local server, which then proxies it to the Lab OCR Service for intelligent text and layout analysis.
                </div>


                {error && (
                    <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive flex items-center gap-2">
                        <AlertCircle size={16} />
                        {typeof error === 'string' ? error : JSON.stringify(error)}
                    </div>
                )}


                <div className="flex justify-end">
                    <button
                        className={cn(
                            "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                            "bg-primary text-primary-foreground shadow hover:bg-primary/90",
                            "h-10 px-8 py-2 w-full sm:w-auto"
                        )}
                        onClick={startOcr}
                        disabled={busy}
                    >
                        {busy ? (
                            <>
                                <Loader2 size={16} className="mr-2 animate-spin" />
                                Starting Job...
                            </>
                        ) : (
                            <>
                                <Play size={16} className="mr-2 fill-current" />
                                Start OCR Processing
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    )
}
