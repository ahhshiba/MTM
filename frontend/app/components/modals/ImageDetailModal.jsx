"use client"
import { useEffect, useRef } from "react"
import { X, ExternalLink } from "lucide-react"
import { cn } from "../../utils/cn"

export default function ImageDetailModal({ isOpen, onClose, image, activeTab = "info" }) {
    const modalRef = useRef(null)

    // Handle escape key
    useEffect(() => {
        const handleEscape = (e) => {
            if (e.key === "Escape") onClose()
        }
        if (isOpen) {
            document.addEventListener("keydown", handleEscape)
            // Prevent body scroll
            document.body.style.overflow = "hidden"
        }
        return () => {
            document.removeEventListener("keydown", handleEscape)
            document.body.style.overflow = "unset"
        }
    }, [isOpen, onClose])

    // Handle click outside
    const handleClickOutside = (e) => {
        if (modalRef.current && !modalRef.current.contains(e.target)) {
            onClose()
        }
    }

    if (!isOpen || !image) return null

    // Helper to get text from bilingual field
    const getText = (field) => {
        if (field === null || field === undefined) return "-"
        if (typeof field === 'string') return field || "-"
        if (typeof field === 'object') {
            return field.original || field.zh || field.en || "-"
        }
        return String(field) || "-"
    }

    // Determine image source
    const imageSrc = image.image_path || image.image_id
        ? `/api/ocr/results/images/${image.image_id || 0}`
        : null

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 md:p-8"
            onClick={handleClickOutside}
        >
            <div
                ref={modalRef}
                className="relative bg-background w-full max-w-6xl max-h-[90vh] rounded-xl shadow-2xl overflow-hidden flex flex-col md:flex-row border border-border"
                onClick={e => e.stopPropagation()}
            >
                {/* Close button */}
                <button
                    onClick={onClose}
                    className="absolute top-4 right-4 z-10 bg-background/50 hover:bg-background p-2 rounded-full backdrop-blur-md border border-border transition-all"
                >
                    <X size={20} />
                </button>

                {/* Left: Image View */}
                <div className="flex-1 bg-black/95 flex items-center justify-center p-4 md:p-8 overflow-hidden min-h-[300px] md:min-h-0 relative group">
                    <div className="absolute inset-0 bg-[radial-gradient(#333_1px,transparent_1px)] [background-size:20px_20px] opacity-20"></div>

                    {imageSrc ? (
                        <img
                            src={imageSrc}
                            alt={getText(image.description)}
                            className="max-w-full max-h-full object-contain shadow-lg"
                        />
                    ) : (
                        <div className="text-muted-foreground">No Image Available</div>
                    )}
                </div>

                {/* Right: Info Panel */}
                <div className="w-full md:w-[400px] bg-card border-l border-border flex flex-col overflow-hidden">
                    <div className="p-6 border-b border-border bg-muted/5">
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <span className="inline-flex items-center rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 mb-2">
                                    {image.img_type || image.image_type || "未分類"}
                                </span>
                                <h3 className="font-semibold text-lg leading-tight text-foreground">
                                    {getText(image.description) || "無描述"}
                                </h3>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto p-6 space-y-6">
                        {/* Tags */}
                        {image.feature_tags && image.feature_tags.length > 0 && (
                            <div>
                                <h4 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wider">特徵標籤</h4>
                                <div className="flex flex-wrap gap-2">
                                    {image.feature_tags.map((tag, idx) => (
                                        <span
                                            key={idx}
                                            className="inline-flex items-center rounded-md border border-border bg-muted px-2 py-1 text-sm font-medium text-foreground"
                                        >
                                            # {tag}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Analysis Details (Hidden by user request) */}
                        {/* 
                        <div>
                            <h4 className="text-sm font-medium text-muted-foreground mb-3 uppercase tracking-wider">分析細節</h4>
                            ...
                        </div>
                        */}

                        {/* Additional Metadata */}
                        {['garment_type', 'view_point', 'print_type_primary', 'print_type_secondary'].map(key => (
                            image[key] && (
                                <div key={key}>
                                    <h4 className="text-sm font-medium text-muted-foreground mb-2 capitalize">{key.replace(/_/g, ' ')}</h4>
                                    <p className="text-sm">{getText(image[key])}</p>
                                </div>
                            )
                        ))}

                    </div>

                    <div className="p-4 border-t border-border bg-muted/5 text-xs text-center text-muted-foreground">
                        TechPack AI Analysis
                    </div>
                </div>
            </div>
        </div>
    )
}
