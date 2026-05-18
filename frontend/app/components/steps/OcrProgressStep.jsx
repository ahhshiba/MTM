"use client"
// app/components/steps/OcrProgressStep.jsx
/**
 * Step 2: OCR Progress (Tailwind CSS)
 */

import React from "react"
import {
    RefreshCw,
    CheckCircle2,
    AlertCircle,
    Loader2,
    File
} from "lucide-react"
import ReactMarkdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import remarkGfm from "remark-gfm"
import { useApp } from "../../context/AppContext"
import { useOcrJob } from "../../hooks/useOcrJob"
import { API_BASE } from "../../utils/api"
import { cn } from "../../utils/cn"

// JSON Section Renderer
function JsonSectionRenderer({ sections }) {
    if (!sections || !sections.length) {
        return <p className="text-muted-foreground italic">No structured data found.</p>
    }

    return (
        <div className="space-y-8">
            {sections.map((section, idx) => {
                // BOM Section
                if (section.section_type === "BOM") {
                    return (
                        <div key={idx} className="space-y-3">
                            <h4 className="font-semibold text-lg flex items-center gap-2">
                                <span className="w-1 h-6 bg-primary rounded-full"></span>
                                BOM (Bill of Materials)
                            </h4>
                            <div className="overflow-x-auto rounded-lg border border-border">
                                <table className="w-full text-sm text-left">
                                    <thead className="text-xs uppercase bg-muted/50 text-muted-foreground font-semibold">
                                        <tr>
                                            <th className="px-4 py-3 border-b border-border">Product Code</th>
                                            <th className="px-4 py-3 border-b border-border">Material Name</th>
                                            <th className="px-4 py-3 border-b border-border">Usage</th>
                                            <th className="px-4 py-3 border-b border-border">Qty</th>
                                            <th className="px-4 py-3 border-b border-border">Supplier</th>
                                            <th className="px-4 py-3 border-b border-border">Comments</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                        {section.items?.map((item, i) => (
                                            <tr key={i} className="bg-card hover:bg-muted/20 transition-colors">
                                                <td className="px-4 py-3 border-r border-border font-medium">{item.product_code || "-"}</td>
                                                <td className="px-4 py-3 border-r border-border">
                                                    <div className="flex flex-col">
                                                        <span>{item.material_name?.zh || item.material_name?.original || "-"}</span>
                                                        {(item.material_name?.zh && item.material_name?.original) && (
                                                            <span className="text-xs text-muted-foreground">{item.material_name.original}</span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 border-r border-border">{item.usage?.zh || item.usage?.original || "-"}</td>
                                                <td className="px-4 py-3 border-r border-border">{item.quantity || "-"}</td>
                                                <td className="px-4 py-3 border-r border-border">{item.supplier?.zh || item.supplier?.original || "-"}</td>
                                                <td className="px-4 py-3 text-muted-foreground text-xs whitespace-pre-wrap max-w-xs">{item.comments?.zh || item.comments?.original || "-"}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )
                }

                // Measurement Section
                if (section.section_type === "Measurement") {
                    // Collect all unique sizes from all points
                    const allSizes = new Set()
                    section.points?.forEach(pt => {
                        Object.keys(pt.values || {}).forEach(s => allSizes.add(s))
                    })
                    const sortedSizes = Array.from(allSizes).sort() // Simple sort, maybe improve later

                    return (
                        <div key={idx} className="space-y-3">
                            <h4 className="font-semibold text-lg flex items-center gap-2">
                                <span className="w-1 h-6 bg-green-500 rounded-full"></span>
                                Measurement Chart
                            </h4>
                            <div className="overflow-x-auto rounded-lg border border-border">
                                <table className="w-full text-sm text-left">
                                    <thead className="text-xs uppercase bg-muted/50 text-muted-foreground font-semibold">
                                        <tr>
                                            <th className="px-4 py-3 border-b border-border">POM Code</th>
                                            <th className="px-4 py-3 border-b border-border">Point Name</th>
                                            <th className="px-4 py-3 border-b border-border">Tol -</th>
                                            <th className="px-4 py-3 border-b border-border">Tol +</th>
                                            {sortedSizes.map(size => (
                                                <th key={size} className="px-4 py-3 border-b border-border min-w-[3rem] text-center">{size}</th>
                                            ))}
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                        {section.points?.map((pt, i) => (
                                            <tr key={i} className="bg-card hover:bg-muted/20 transition-colors">
                                                <td className="px-4 py-3 border-r border-border font-mono text-xs">{pt.pom_code || "-"}</td>
                                                <td className="px-4 py-3 border-r border-border font-medium max-w-xs truncate" title={pt.point_name?.original}>
                                                    {pt.point_name?.zh || pt.point_name?.original || "-"}
                                                </td>
                                                <td className="px-4 py-3 border-r border-border text-xs">{pt.tolerance_minus || "-"}</td>
                                                <td className="px-4 py-3 border-r border-border text-xs">{pt.tolerance_plus || "-"}</td>
                                                {sortedSizes.map(size => (
                                                    <td key={size} className="px-4 py-3 border-r border-border text-center font-mono">
                                                        {pt.values?.[size] || "-"}
                                                    </td>
                                                ))}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )
                }

                return null
            })}
        </div>
    )
}

export default function OcrProgressStep() {
    const { state, dispatch, computed } = useApp()
    const {
        job,
        status,
        error,
        results,
        resultsLoading,
        resultsError,
        activePageId,
        artifactMarkdownById,
        artifactJsonById // New state
    } = state
    const {
        normalizedStep,
        progress,
        ocrDone,
        ocrFailed,
        pages
    } = computed
    const { refresh, loadArtifactMarkdown, loadArtifactJson } = useOcrJob() // Destructure new loader

    const activePage = pages.find((page) => page.page_id === activePageId)
    const activeArtifactId = activePage?.artifact?.artifact_id

    // Determine what content to show
    const activeJson = activeArtifactId ? artifactJsonById?.[activeArtifactId] : null
    const activeMarkdown = activeArtifactId ? artifactMarkdownById[activeArtifactId] : ""

    const API_ROOT = "/api/ocr"

    const activeRenderUrl = activePage?.render_image_url
        ? `${API_ROOT}/results/pages/${activePage.page_id}/render_image`
        : activeArtifactId
            ? `${API_ROOT}/results/artifacts/${activeArtifactId}/vis_image`
            : null

    // Load Data Effect
    if (activeArtifactId) {
        if (!activeMarkdown && !Object.prototype.hasOwnProperty.call(artifactMarkdownById, activeArtifactId)) {
            loadArtifactMarkdown(activeArtifactId)
        }
        if (!activeJson && !Object.prototype.hasOwnProperty.call(artifactJsonById || {}, activeArtifactId)) {
            loadArtifactJson(activeArtifactId)
        }
    }

    // Fake Progress Simulation
    const [simulatedProgress, setSimulatedProgress] = React.useState(0)

    // Reset simulated progress when job changes
    React.useEffect(() => {
        if (!status) {
            setSimulatedProgress(0)
            return
        }

        // If done, jump to 100
        if (ocrDone) {
            setSimulatedProgress(100)
            return
        }

        // If running, simulate progress
        if (status.status === "running" || status?.status === "processing") {
            const interval = setInterval(() => {
                setSimulatedProgress(prev => {
                    // Fast at first, then slower as it approaches 95%
                    if (prev >= 95) return 95
                    const increment = prev < 50 ? 5 : prev < 80 ? 2 : 0.5
                    return Math.min(95, prev + increment)
                })
            }, 800) // Update every 800ms
            return () => clearInterval(interval)
        }
    }, [status?.status, ocrDone, job?.local_job_id])

    // Use simulated progress unless real progress is higher (and reliable) or done
    const displayProgress = ocrDone ? 100 : Math.max(simulatedProgress, Math.round((status?.progress || 0) * 100))

    return (
        <div className="space-y-6">
            {/* Status Card */}
            <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm">
                <div className="flex flex-row items-center justify-between p-6 pb-2">
                    <h3 className="tracking-tight text-sm font-medium text-muted-foreground">OCR Status</h3>
                    <div className="flex items-center gap-2">
                        <span className={cn(
                            "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
                            ocrDone ? "bg-green-500/15 text-green-700" :
                                ocrFailed ? "bg-destructive/15 text-destructive" :
                                    "bg-secondary text-secondary-foreground"
                        )}>
                            {status?.status || "Unknown"}
                        </span>
                        <button
                            className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-8 w-8"
                            onClick={refresh}
                        >
                            <RefreshCw size={14} />
                        </button>
                    </div>
                </div>
                <div className="p-6 pt-0">
                    <div className="text-2xl font-bold">
                        {Math.round(displayProgress)}%
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-secondary h-2.5 rounded-full mt-2 overflow-hidden relative">
                        <div
                            className="bg-primary h-2.5 rounded-full transition-all duration-300 ease-in-out relative overflow-hidden"
                            style={{ width: `${Math.max(5, Math.min(100, displayProgress))}%` }}
                        >
                            {(status?.status === "running" || status?.status === "processing") && (
                                <div className="absolute inset-0 bg-white/30 w-full animate-[shimmer_2s_infinite] -translate-x-full"></div>
                            )}
                        </div>
                    </div>

                    <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1.5 min-h-[1.25rem]">
                        {(status?.status === "running" || status?.status === "processing") && (
                            <Loader2 size={12} className="animate-spin text-primary shrink-0" />
                        )}
                        <span>{status?.message || (ocrDone ? "Processing complete." : ocrFailed ? "Processing failed." : "Initializing...")}</span>
                    </p>

                    {error && (
                        <div className="mt-4 p-3 text-sm text-destructive bg-destructive/10 rounded-md flex items-start gap-2">
                            <AlertCircle size={16} className="mt-0.5 shrink-0" />
                            <span>{error}</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Results Section */}
            {
                ocrDone && (
                    <div className="rounded-xl border border-border bg-card text-card-foreground shadow-sm">
                        <div className="flex flex-col space-y-1.5 p-6 border-b border-border">
                            <h3 className="font-semibold leading-none tracking-tight">OCR Results</h3>
                        </div>
                        <div className="p-6">
                            {resultsLoading ? (
                                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                                    <Loader2 size={40} className="animate-spin mb-4 text-primary/50" />
                                    <p>Loading OCR results...</p>
                                </div>
                            ) : resultsError ? (
                                <div className="rounded-md bg-destructive/15 p-4 text-sm text-destructive flex items-center gap-2">
                                    <AlertCircle size={16} />
                                    {resultsError}
                                </div>
                            ) : pages.length ? (
                                <div className="space-y-6">
                                    {/* Thumbnails */}
                                    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
                                        {pages.map((page) => {
                                            const artifactId = page?.artifact?.artifact_id
                                            const visUrl = artifactId ? `${API_ROOT}/results/artifacts/${artifactId}/vis_image` : null
                                            const isActive = activePageId === page.page_id

                                            return (
                                                <button
                                                    key={page.page_id}
                                                    type="button"
                                                    className={cn(
                                                        "group relative aspect-[3/4] rounded-md overflow-hidden border border-border bg-muted transaction-all",
                                                        "hover:ring-2 hover:ring-primary/50 hover:border-transparent",
                                                        "focus:outline-none focus:ring-2 focus:ring-primary",
                                                        isActive && "ring-2 ring-primary border-transparent"
                                                    )}
                                                    onClick={() => dispatch({ type: "SET_ACTIVE_PAGE_ID", payload: page.page_id })}
                                                >
                                                    {visUrl ? (
                                                        <img
                                                            src={visUrl || "/placeholder.svg"}
                                                            alt={`Page ${page.page_no + 1}`}
                                                            className="w-full h-full object-cover transition-transform group-hover:scale-105"
                                                        />
                                                    ) : (
                                                        <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                                                            <File size={20} className="mb-1 opacity-50" />
                                                            <span className="text-[10px] font-medium">P{page.page_no + 1}</span>
                                                        </div>
                                                    )}
                                                    <div className={cn(
                                                        "absolute inset-0 bg-black/0 transition-colors group-hover:bg-black/10",
                                                        isActive && "bg-primary/10"
                                                    )} />
                                                </button>
                                            )
                                        })}
                                    </div>

                                    {/* Content View */}
                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-6 border-t border-border">
                                        {/* Data Output (JSON prioritized, fallback to Markdown) */}
                                        <div className="bg-muted/30 rounded-lg border border-border overflow-hidden flex flex-col h-[600px]">
                                            <div className="px-4 py-2 border-b border-border bg-muted/50 text-xs font-medium text-muted-foreground flex items-center justify-between">
                                                <span>
                                                    {activeJson?.sections?.length ? "Structured Data" : "Markdown Output"}
                                                </span>
                                            </div>
                                            <div className="flex-1 overflow-y-auto p-4">
                                                {activeJson?.sections?.length > 0 ? (
                                                    <JsonSectionRenderer sections={activeJson.sections} />
                                                ) : activeMarkdown ? (
                                                    <article className="prose prose-sm max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary hover:prose-a:underline">
                                                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                                                            {activeMarkdown}
                                                        </ReactMarkdown>
                                                    </article>
                                                ) : (
                                                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground/50">
                                                        <p>Select a page to view content</p>
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        {/* Visual Preview */}
                                        <div className="bg-muted/30 rounded-lg border border-border overflow-hidden flex flex-col h-[600px]">
                                            <div className="px-4 py-2 border-b border-border bg-muted/50 text-xs font-medium text-muted-foreground">
                                                Preview
                                            </div>
                                            <div className="flex-1 overflow-y-auto p-4 flex items-center justify-center bg-zinc-100/50 dark:bg-zinc-900/50">
                                                {activeRenderUrl ? (
                                                    <img
                                                        src={activeRenderUrl || "/placeholder.svg"}
                                                        alt="OCR page preview"
                                                        className="max-w-full h-auto shadow-lg rounded-sm border border-border/50"
                                                    />
                                                ) : (
                                                    <div className="flex flex-col items-center justify-center text-muted-foreground/50">
                                                        <p>No preview available</p>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center py-16 text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
                                    <File size={32} className="opacity-20 mb-3" />
                                    <p>No detailed results found.</p>
                                </div>
                            )}
                        </div>
                    </div>
                )
            }
        </div >
    )
}
