"use client"
// app/components/steps/PreviewStep.jsx
/**
 * 結構化資料預覽 Step - 完整版 (包含所有 JSON 資料區塊)
 */

import { useState, useMemo, useRef, useCallback, useEffect } from "react"
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Image as ImageIcon,
  Table2,
  Mail,
  Settings,
  ExternalLink,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Wrench,
  Layers
} from "lucide-react"
import { useApp } from "../../context/AppContext"
import { formatNumber } from "../../utils/formatters"
import { cn } from "../../utils/cn"
// Import Image Modal
import ImageDetailModal from "../modals/ImageDetailModal"

// Tab 定義 - 新增 components 和 construction
const TABS = [
  { id: "basic", label: "Basic Info", icon: FileText },
  { id: "bom", label: "BOM", icon: Table2 },
  { id: "measurement", label: "Measurement", icon: Settings },
  { id: "components", label: "Components", icon: Layers },
  { id: "construction", label: "Construction", icon: Wrench },
  { id: "images", label: "Images", icon: ImageIcon },
  { id: "emails", label: "Email", icon: Mail },
]

// Helper: 從雙語欄位取得文字
function getText(field) {
  if (field === null || field === undefined) return "-"
  if (typeof field === 'string') return field || "-"
  if (typeof field === 'object') {
    return field.original || field.zh || field.en || "-"
  }
  return String(field) || "-"
}

// Helper: 雙語顯示元件
function hasChinese(text) {
  return /[\u4e00-\u9fff]/.test(String(text || ""))
}

function BilingualText({ value, className }) {
  if (!value) return <span className="text-muted-foreground">-</span>

  // Handle string or number
  if (typeof value !== 'object') {
    return <span className={className}>{value}</span>
  }

  const original = String(value.original || value.en || value.value || "").trim()
  const zh = String(value.zh || "").trim()
  const hasTranslation = Boolean(zh && zh !== original)
  const originalIsChinese = hasChinese(original)

  // 非中文原文有翻譯時，以中文作為主行、原文作為副行。
  // 原文已是中文或翻譯相同時，只顯示一次，避免重複。
  const mainText = (!originalIsChinese && hasTranslation) ? zh : (original || zh || "-")
  const subText = (!originalIsChinese && hasTranslation) ? original : null
  const title = subText ? `${mainText}\n${subText}` : String(mainText)

  return (
    <div className={cn("min-w-0", className)}>
      <div className="font-medium truncate" title={title}>{mainText}</div>
      {subText && (
        <div className="text-xs text-muted-foreground truncate" title={subText}>{subText}</div>
      )}
    </div>
  )
}

export default function PreviewStep() {
  const { state } = useApp()
  const { extractionResult } = state

  const [activeTab, setActiveTab] = useState("basic")
  const [selectedPageIndex, setSelectedPageIndex] = useState(0)
  const [zoom, setZoom] = useState(100)

  // Image Modal State
  const [selectedImage, setSelectedImage] = useState(null)

  // 可調整寬度的面板
  const [leftPanelWidth, setLeftPanelWidth] = useState(60) // 百分比
  const [isDragging, setIsDragging] = useState(false)
  const containerRef = useRef(null)

  const result = extractionResult?.result || {}
  const pageImages = result.page_images || []

  // 統計 - 擴展更多資訊
  const stats = useMemo(() => ({
    styleNo: getText(result.basic_info?.style_no),
    styleName: getText(result.basic_info?.style_name),
    season: getText(result.basic_info?.season),
    brand: getText(result.basic_info?.brand),
    sections: result.sections?.length || 0,
    images: result.images?.length || 0,
    emails: result.email_notes?.length || 0,
    construction: (result.construction_notes?.length || 0) + (result.construction_options?.length || 0),
    tokens: result.extraction_summary?.llm_tokens_used || 0,
  }), [result])

  // BOM 區塊
  const bomSections = useMemo(() => {
    return (result.sections || []).filter(
      s => s.section_type?.toLowerCase().includes("bom") ||
        s.section_type?.toLowerCase().includes("material")
    )
  }, [result.sections])

  // Measurement 區塊
  const measurementSections = useMemo(() => {
    return (result.sections || []).filter(
      s => s.section_type?.toLowerCase().includes("measurement") ||
        s.section_type?.toLowerCase().includes("size")
    )
  }, [result.sections])

  // Components 區塊
  const componentsSections = useMemo(() => {
    return (result.sections || []).filter(
      s => s.section_type?.toLowerCase().includes("component")
    )
  }, [result.sections])

  // Documents/Inspiration 區塊 (合併到 Images)
  const docSections = useMemo(() => {
    return (result.sections || []).filter(
      s => s.section_type?.toLowerCase().includes("document") ||
        s.section_type?.toLowerCase().includes("inspiration")
    )
  }, [result.sections])

  const handleGoToPage = (pageIndex) => {
    if (pageIndex >= 0 && pageIndex < pageImages.length) {
      setSelectedPageIndex(pageIndex)
    }
  }

  const handleBboxClick = (item, parentSection = null) => {
    console.log('[handleBboxClick] item:', item, 'parentSection:', parentSection)

    // 優先使用 source_page（如果存在）
    if (typeof item.source_page === 'number' && item.source_page >= 0) {
      console.log('[handleBboxClick] using item.source_page:', item.source_page)
      handleGoToPage(item.source_page)
      return
    }

    // 其次使用 bbox_refs 的 page_index（如果存在）
    const bboxRefs = item.bbox_refs || []
    if (bboxRefs.length > 0) {
      const firstRef = bboxRefs[0]
      if (typeof firstRef.page_index === 'number') {
        console.log('[handleBboxClick] using bbox_refs.page_index:', firstRef.page_index)
        handleGoToPage(firstRef.page_index)
        return
      }
    }

    // 最後使用 parentSection 的 source_page
    if (typeof parentSection?.source_page === 'number' && parentSection.source_page >= 0) {
      console.log('[handleBboxClick] using parentSection.source_page:', parentSection.source_page)
      handleGoToPage(parentSection.source_page)
      return
    }

    console.log('[handleBboxClick] no valid source_page found')
  }

  // Handle Image Click (for Modal)
  const handleImageClick = useCallback((img) => {
    console.log("Image clicked:", img)
    setSelectedImage(img)
  }, [])

  // 拖曳調整面板寬度
  const handleMouseDown = useCallback((e) => {
    setIsDragging(true)
    e.preventDefault()
  }, [])

  const handleMouseMove = useCallback((e) => {
    if (!isDragging || !containerRef.current) return
    const containerRect = containerRef.current.getBoundingClientRect()
    const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100
    // 限制範圍 30% - 80%
    setLeftPanelWidth(Math.max(30, Math.min(80, newWidth)))
  }, [isDragging])

  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
  }, [])

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      return () => {
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [isDragging, handleMouseMove, handleMouseUp])

  if (!result || Object.keys(result).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-muted-foreground opacity-70">
        <FileText size={64} className="mb-4 opacity-30" />
        <h3 className="text-xl font-medium mb-1">尚無資料</h3>
        <p>請先完成結構化萃取</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-[calc(100vh-140px)] -m-6 box-border">
      {/* 統計儀表板 - 擴展更多欄位 */}
      <div className="flex flex-wrap gap-x-6 gap-y-2 px-6 py-3 bg-muted/30 border-b border-border text-sm">
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Style No</span>
          <span className="font-semibold">{stats.styleNo}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Style Name</span>
          <span className="font-semibold max-w-[200px] truncate" title={stats.styleName}>{stats.styleName}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Season</span>
          <span className="font-semibold">{stats.season}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Brand</span>
          <span className="font-semibold">{stats.brand}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Sections</span>
          <span className="font-semibold">{stats.sections}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Images</span>
          <span className="font-semibold">{stats.images}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Constr.</span>
          <span className="font-semibold">{stats.construction}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Email</span>
          <span className="font-semibold">{stats.emails}</span>
        </div>
        <div className="flex flex-col gap-0.5 ml-auto text-right">
          <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">Tokens</span>
          <span className="font-mono">{formatNumber(stats.tokens)}</span>
        </div>
      </div>

      <div ref={containerRef} className={cn("flex flex-1 overflow-hidden", isDragging && "select-none")}>
        {/* 左側：資料面板 */}
        <div
          className="flex flex-col border-r border-border min-w-[300px] bg-background"
          style={{ width: `${leftPanelWidth}%` }}
        >
          {/* Tab 導航 */}
          <div className="flex gap-1 px-4 py-2 border-b border-border bg-muted/10 overflow-x-auto">
            {TABS.map(tab => (
              <button
                key={tab.id}
                className={cn(
                  "flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap",
                  activeTab === tab.id
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
                onClick={() => setActiveTab(tab.id)}
              >
                <tab.icon size={14} />
                <span>{tab.label}</span>
              </button>
            ))}
          </div>

          {/* Tab 內容 */}
          <div className="flex-1 overflow-auto p-6 bg-muted/5">
            {activeTab === "basic" && (
              <BasicInfoPanel basicInfo={result.basic_info} metadata={result.metadata} extractionSummary={result.extraction_summary} />
            )}

            {activeTab === "bom" && (
              <BomPanel sections={bomSections} onBboxClick={handleBboxClick} />
            )}

            {activeTab === "measurement" && (
              <MeasurementPanel sections={measurementSections} onBboxClick={handleBboxClick} />
            )}

            {activeTab === "components" && (
              <ComponentsPanel sections={componentsSections} onBboxClick={handleBboxClick} />
            )}

            {activeTab === "construction" && (
              <ConstructionPanel
                notes={result.construction_notes || []}
                options={result.construction_options || []}
                onBboxClick={handleBboxClick}
              />
            )}

            {activeTab === "images" && (
              <ImagesPanel
                images={result.images || []}
                docSections={docSections}
                onBboxClick={handleImageClick} // Use Modal handler for images
              />
            )}

            {activeTab === "emails" && (
              <EmailsPanel emails={result.email_notes || []} onBboxClick={handleBboxClick} />
            )}
          </div>
        </div>

        {/* 可拖曳的分隔線 */}
        <div
          className={cn(
            "w-1.5 bg-border hover:bg-primary/50 cursor-col-resize transition-colors flex-shrink-0",
            isDragging && "bg-primary"
          )}
          onMouseDown={handleMouseDown}
          title="拖曳調整寬度"
        />

        {/* 右側：頁面預覽 */}
        <div className="flex flex-col flex-1 min-w-[300px] bg-neutral-900 relative">
          <div className="flex justify-between items-center px-3 py-2 bg-neutral-800 border-b border-neutral-700 text-neutral-300 z-10">
            <div className="flex items-center gap-2">
              <button
                className="p-1 rounded hover:bg-neutral-700 disabled:opacity-30"
                onClick={() => handleGoToPage(selectedPageIndex - 1)}
                disabled={selectedPageIndex === 0}
              >
                <ChevronLeft size={16} />
              </button>
              <span className="text-xs font-mono">
                Page {selectedPageIndex + 1} / {pageImages.length || 0}
              </span>
              <button
                className="p-1 rounded hover:bg-neutral-700 disabled:opacity-30"
                onClick={() => handleGoToPage(selectedPageIndex + 1)}
                disabled={selectedPageIndex >= pageImages.length - 1}
              >
                <ChevronRight size={16} />
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button className="p-1 rounded hover:bg-neutral-700" onClick={() => setZoom(z => Math.max(50, z - 10))}>
                <ZoomOut size={16} />
              </button>
              <span className="text-xs w-10 text-center">{zoom}%</span>
              <button className="p-1 rounded hover:bg-neutral-700" onClick={() => setZoom(z => Math.min(200, z + 10))}>
                <ZoomIn size={16} />
              </button>
              <div className="w-px h-3 bg-neutral-600 mx-1"></div>
              <button className="p-1 rounded hover:bg-neutral-700" onClick={() => setZoom(100)}>
                <Maximize2 size={16} />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto flex justify-center p-8 bg-neutral-950">
            {pageImages[selectedPageIndex] ? (
              <img
                src={`/api/ocr/results/pages/${pageImages[selectedPageIndex].page_id}/render_image`}
                alt={`Page ${selectedPageIndex + 1}`}
                style={{ width: `${zoom}%` }}
                className="object-contain shadow-lg max-w-none transition-all duration-200"
              />
            ) : (
              <div className="flex flex-col items-center justify-center text-neutral-600">
                <ImageIcon size={48} className="mb-2 opacity-50" />
                <p className="text-sm">無頁面圖片</p>
              </div>
            )}
          </div>
        </div>
      </div>
      <ImageDetailModal
        isOpen={!!selectedImage}
        onClose={() => setSelectedImage(null)}
        image={selectedImage}
      />
    </div>
  )
}

// ==================== BasicInfoPanel ====================
function BasicInfoPanel({ basicInfo, metadata, extractionSummary }) {
  if (!basicInfo) return <p className="text-muted-foreground">無基本資訊</p>

  // 擴展所有欄位
  const fields = [
    { label: "Style No", value: basicInfo.style_no },
    { label: "Style Name", value: basicInfo.style_name },
    { label: "BOM No", value: basicInfo.bom_number },
    { label: "Season", value: basicInfo.season },
    { label: "Brand", value: basicInfo.brand },
    { label: "Department", value: basicInfo.department },
    { label: "Collection", value: basicInfo.collection },
    { label: "Category", value: basicInfo.category },
    { label: "Sub Category", value: basicInfo.sub_category },
    { label: "Design Type", value: basicInfo.design_type },
    { label: "Vendor", value: basicInfo.vendor },
    { label: "Supplier", value: basicInfo.supplier },
    { label: "Gender", value: basicInfo.gender },
    { label: "Size Range", value: basicInfo.size_range },
    { label: "Base Size", value: basicInfo.base_size },
    { label: "Status", value: basicInfo.status },
    { label: "Order No", value: basicInfo.order_no },
    { label: "Version", value: basicInfo.version },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <FileText size={18} className="text-primary" />
          Basic Info
        </h3>
        <dl className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {fields.map(({ label, value }) => (
            value && getText(value) !== "-" && (
              <div key={label} className="bg-card p-3 rounded-lg border border-border">
                <dt className="text-xs text-muted-foreground font-medium mb-1">{label}</dt>
                <dd className="text-sm">
                  <BilingualText value={value} />
                </dd>
              </div>
            )
          ))}
        </dl>
      </div>

      {/* 時間資訊 */}
      {(basicInfo.created || basicInfo.modified) && (
        <div className="pt-4 border-t border-border">
          <h4 className="text-sm font-semibold mb-2 text-muted-foreground uppercase tracking-wider">Timestamps</h4>
          <div className="flex gap-4 text-sm">
            {basicInfo.created && <span>Created: <span className="font-mono text-muted-foreground">{basicInfo.created}</span></span>}
            {basicInfo.modified && <span>Modified: <span className="font-mono text-muted-foreground">{basicInfo.modified}</span></span>}
          </div>
        </div>
      )}

      {/* 文件資訊 */}
      {metadata && (
        <div className="pt-4 border-t border-border">
          <h4 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wider">文件資訊</h4>
          <dl className="grid grid-cols-2 gap-4">
            <div className="bg-muted/30 p-3 rounded-lg border border-border">
              <dt className="text-xs text-muted-foreground mb-1">Filename</dt>
              <dd className="text-sm font-medium truncate" title={metadata.filename}>{metadata.filename || "-"}</dd>
            </div>
            <div className="bg-muted/30 p-3 rounded-lg border border-border">
              <dt className="text-xs text-muted-foreground mb-1">Total Pages</dt>
              <dd className="text-sm font-medium">{metadata.total_pages || "-"}</dd>
            </div>
          </dl>
        </div>
      )}

      {/* 萃取統計 */}
      {extractionSummary && (
        <div className="pt-4 border-t border-border">
          <h4 className="text-sm font-semibold mb-3 text-muted-foreground uppercase tracking-wider">Extraction Stats</h4>
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-muted/30 p-3 rounded-lg border border-border text-center">
              <dt className="text-xs text-muted-foreground mb-1">Sections</dt>
              <dd className="text-lg font-bold text-primary">{extractionSummary.sections_detected || 0}</dd>
            </div>
            <div className="bg-muted/30 p-3 rounded-lg border border-border text-center">
              <dt className="text-xs text-muted-foreground mb-1">Images</dt>
              <dd className="text-lg font-bold text-primary">{extractionSummary.images_processed || 0}</dd>
            </div>
            <div className="bg-muted/30 p-3 rounded-lg border border-border text-center">
              <dt className="text-xs text-muted-foreground mb-1">Constr. Notes</dt>
              <dd className="text-lg font-bold text-primary">{extractionSummary.construction_notes || 0}</dd>
            </div>
            <div className="bg-muted/30 p-3 rounded-lg border border-border text-center">
              <dt className="text-xs text-muted-foreground mb-1">LLM Tokens</dt>
              <dd className="text-lg font-bold font-mono text-primary">{formatNumber(extractionSummary.llm_tokens_used || 0)}</dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  )
}

// ==================== BomPanel ====================
function BomPanel({ sections, onBboxClick }) {
  if (!sections.length) return <p className="text-muted-foreground">No BOM Data</p>

  return (
    <div className="space-y-6">
      {sections.map((section, idx) => (
        <div key={idx} className="bg-card rounded-lg border border-border overflow-hidden shadow-sm">
          <h3
            onClick={() => onBboxClick(section)}
            className="flex items-center gap-2 px-4 py-3 bg-muted/30 border-b border-border text-sm font-semibold cursor-pointer hover:bg-muted/50 transition-colors"
          >
            {getText(section.section_name) !== "-" ? getText(section.section_name) : (section.section_type || `區塊 ${idx + 1}`)}
            <ExternalLink size={14} className="text-muted-foreground ml-auto" />
          </h3>

          {section.items?.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/10 text-xs text-muted-foreground font-medium uppercase">
                  <tr>
                    <th className="px-3 py-2 text-left whitespace-nowrap">Part</th>
                    <th className="px-3 py-2 text-left">Material Name</th>
                    <th className="px-3 py-2 text-left whitespace-nowrap">Gauge</th>
                    <th className="px-3 py-2 text-left whitespace-nowrap">Width</th>
                    <th className="px-3 py-2 text-left whitespace-nowrap">Weight</th>
                    <th className="px-3 py-2 text-left">Composition</th>
                    <th className="px-3 py-2 text-left">Color</th>
                    <th className="px-3 py-2 text-left">Supplier</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {section.items.map((item, i) => (
                    <tr
                      key={i}
                      onClick={() => onBboxClick(item, section)}
                      className="hover:bg-muted/30 cursor-pointer transition-colors"
                    >
                      <td className="px-3 py-2"><BilingualText value={item.part || item.usage} /></td>
                      <td className="px-3 py-2">
                        <BilingualText value={item.material_name} />
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-primary">{item.gauge || "-"}</td>
                      <td className="px-3 py-2 font-mono text-xs">{item.width || "-"}</td>
                      <td className="px-3 py-2 font-mono text-xs">{item.weight || "-"}</td>
                      <td className="px-3 py-2 text-xs max-w-[150px]"><BilingualText value={item.composition} /></td>
                      <td className="px-3 py-2"><BilingualText value={item.color} /></td>
                      <td className="px-3 py-2"><BilingualText value={item.supplier || item.allocated_supplier} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ==================== MeasurementPanel ====================
function MeasurementPanel({ sections, onBboxClick }) {
  if (!sections.length) return <p className="text-muted-foreground">No Measurement Data</p>

  return (
    <div className="space-y-6">
      {sections.map((section, idx) => {
        // 收集所有尺碼
        const allSizes = new Set()
        section.points?.forEach(pt => {
          if (pt.values) Object.keys(pt.values).forEach(s => allSizes.add(s))
        })
        const sortedSizes = Array.from(allSizes).sort()

        return (
          <div key={idx} className="bg-card rounded-lg border border-border overflow-hidden shadow-sm">
            <h3
              onClick={() => onBboxClick(section)}
              className="flex items-center gap-2 px-4 py-3 bg-muted/30 border-b border-border text-sm font-semibold cursor-pointer hover:bg-muted/50 transition-colors"
            >
              {getText(section.section_name) !== "-" ? getText(section.section_name) : (section.section_type || `區塊 ${idx + 1}`)}
              {section.chart_type && <span className="text-xs font-normal text-muted-foreground ml-2">({section.chart_type})</span>}
              <ExternalLink size={14} className="text-muted-foreground ml-auto" />
            </h3>

            {section.points?.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted/10 text-xs text-muted-foreground font-medium uppercase">
                    <tr>
                      <th className="px-3 py-2 text-left whitespace-nowrap">POM</th>
                      <th className="px-3 py-2 text-left">Point Name</th>
                      <th className="px-3 py-2 text-left whitespace-nowrap">Tolerance</th>
                      {sortedSizes.map(size => (
                        <th key={size} className="px-3 py-2 text-center min-w-[50px]">{size}</th>
                      ))}
                      <th className="px-3 py-2 text-left">How to Measure</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {section.points.map((point, i) => (
                      <tr
                        key={i}
                        onClick={() => onBboxClick(point, section)}
                        className="hover:bg-muted/30 cursor-pointer transition-colors"
                      >
                        <td className="px-3 py-2 font-mono text-xs text-primary">{point.pom_code || "-"}</td>
                        <td className="px-3 py-2">
                          <BilingualText value={point.point_name} />
                        </td>
                        <td className="px-3 py-2 text-xs font-mono">
                          {point.tolerance_minus && point.tolerance_plus
                            ? `${point.tolerance_minus} / +${point.tolerance_plus}`
                            : (point.tolerance || "-")
                          }
                        </td>
                        {sortedSizes.map(size => (
                          <td key={size} className="px-3 py-2 text-center font-mono">
                            {point.values?.[size] || "-"}
                          </td>
                        ))}
                        <td className="px-3 py-2 text-xs max-w-[150px]">
                          <BilingualText value={point.how_to_measure} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ==================== ComponentsPanel (新增) ====================
function ComponentsPanel({ sections, onBboxClick }) {
  if (!sections.length) return <p className="text-muted-foreground">No Component Data</p>

  return (
    <div className="space-y-6">
      {sections.map((section, idx) => (
        <div key={idx} className="bg-card rounded-lg border border-border overflow-hidden shadow-sm">
          <h3
            onClick={() => onBboxClick(section)}
            className="flex items-center gap-2 px-4 py-3 bg-muted/30 border-b border-border text-sm font-semibold cursor-pointer hover:bg-muted/50 transition-colors"
          >
            {getText(section.section_name) !== "-" ? getText(section.section_name) : (section.section_type || `區塊 ${idx + 1}`)}
            <ExternalLink size={14} className="text-muted-foreground ml-auto" />
          </h3>

          {section.items?.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/10 text-xs text-muted-foreground font-medium uppercase">
                  <tr>
                    <th className="px-4 py-3 text-left">Component Name</th>
                    <th className="px-4 py-3 text-left">Specs</th>
                    <th className="px-4 py-3 text-left">Remarks</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {section.items.map((item, i) => (
                    <tr
                      key={i}
                      onClick={() => onBboxClick(item, section)}
                      className="hover:bg-muted/30 cursor-pointer transition-colors"
                    >
                      <td className="px-4 py-3 font-medium"><BilingualText value={item.component_name} /></td>
                      <td className="px-4 py-3"><BilingualText value={item.specifications || item.specification} /></td>
                      <td className="px-4 py-3 text-muted-foreground"><BilingualText value={item.remarks || item.notes} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ==================== ConstructionPanel (新增) ====================
function ConstructionPanel({ notes, options, onBboxClick }) {
  if (!notes.length && !options.length) return <p className="text-muted-foreground">No Construction Data</p>

  return (
    <div className="space-y-6">
      {/* Construction Notes */}
      {notes.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Wrench size={18} className="text-primary" />
            Construction Notes <span className="text-sm font-normal text-muted-foreground">({notes.length})</span>
          </h3>
          <div className="space-y-3">
            {notes.map((note, idx) => (
              <div
                key={idx}
                onClick={() => onBboxClick(note)}
                className="bg-card rounded-lg border border-border p-4 cursor-pointer hover:border-primary/50 hover:shadow-sm transition-all"
              >
                <div className="flex justify-between items-center mb-2">
                  <span className="font-semibold text-primary"><BilingualText value={note.source} /></span>
                  {note.source_page !== undefined && (
                    <span className="text-xs bg-muted px-2 py-0.5 rounded">Page {note.source_page + 1}</span>
                  )}
                </div>
                <div className="text-sm text-foreground/90 leading-relaxed"><BilingualText value={note.content} /></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Construction Options */}
      {options.length > 0 && (
        <div className="pt-4 border-t border-border">
          <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Settings size={18} className="text-primary" />
            Construction Options <span className="text-sm font-normal text-muted-foreground">({options.length})</span>
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {options.map((option, idx) => (
              <div
                key={idx}
                onClick={() => onBboxClick(option)}
                className="bg-card rounded-lg border border-border p-3 cursor-pointer hover:border-primary/50 transition-all"
              >
                <div className="font-medium mb-1"><BilingualText value={option.option_name || option.name} /></div>
                <div className="text-sm text-muted-foreground"><BilingualText value={option.value || option.description} /></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ==================== ImagesPanel ====================
function ImagesPanel({ images, docSections, onBboxClick }) {
  // 合併 Documents/Inspiration sections 的圖片
  const allImages = [...images]
  docSections?.forEach(section => {
    section.items?.forEach(item => {
      if (item.image_path || item.image_paths) {
        allImages.push({
          ...item,
          image_type: section.section_type,
          description: item.title || item.description
        })
      }
    })
  })

  if (!allImages.length) return <p className="text-muted-foreground">No Images</p>

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {allImages.map((img, idx) => (
          <div
            key={idx}
            className="group bg-card rounded-lg border border-border overflow-hidden cursor-pointer hover:shadow-md hover:border-primary/50 transition-all"
            onClick={() => onBboxClick(img)}
          >
            <div className="h-40 bg-muted/10 flex flex-col items-center justify-center p-2 border-b border-border group-hover:bg-muted/20">
              {img.image_path || img.image_id ? (
                <img
                  src={`/api/ocr/results/images/${img.image_id || idx}`}
                  alt={getText(img.description)}
                  className="max-w-full max-h-full object-contain"
                />
              ) : (
                <ImageIcon className="text-muted-foreground opacity-20" size={32} />
              )}
            </div>
            <div className="p-3 space-y-2">
              <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary">
                {img.image_type || "Uncategorized"}
              </span>
              <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed" title={getText(img.description)}>
                {getText(img.description)}
              </p>
              {/* 顯示更多細節 */}
              {(img.feature_tags?.length > 0 || img.image_role || img.importance_score) && (
                <div className="flex flex-wrap gap-1 pt-1 border-t border-border">
                  {img.image_role && (
                    <span className="text-[10px] px-1 py-0.5 bg-muted rounded">{img.image_role}</span>
                  )}
                  {img.importance_score && (
                    <span className="text-[10px] px-1 py-0.5 bg-yellow-500/20 text-yellow-700 rounded">★ {img.importance_score}</span>
                  )}
                  {img.feature_tags?.slice(0, 3).map((tag, i) => (
                    <span key={i} className="text-[10px] px-1 py-0.5 bg-blue-500/10 text-blue-600 rounded">
                      #{tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ==================== EmailsPanel ====================
function EmailsPanel({ emails, onBboxClick }) {
  if (!emails.length) return <p className="text-muted-foreground">No Email Records</p>

  return (
    <div className="space-y-4">
      {emails.map((email, idx) => (
        <div
          key={idx}
          className="bg-card rounded-lg border border-border p-4 cursor-pointer hover:shadow-md hover:border-primary/30 transition-all"
          onClick={() => onBboxClick(email)}
        >
          <div className="flex justify-between items-center mb-2 text-xs text-muted-foreground">
            <span className="font-medium bg-muted px-1.5 py-0.5 rounded">{email.date || "-"}</span>
            <span>{email.sender || "-"}</span>
          </div>
          <h4 className="font-semibold text-lg mb-2">
            {getText(email.subject) !== "-" ? getText(email.subject) : "無主旨"}
          </h4>
          {email.recipient && (
            <p className="text-xs text-muted-foreground mb-2">To: {email.recipient}</p>
          )}
          <p className="text-sm text-foreground/80 mb-4 bg-muted/20 p-3 rounded-md line-clamp-3">
            {getText(email.content_summary)}
          </p>
          {email.action_items?.length > 0 && (
            <div className="text-sm bg-yellow-500/10 border border-yellow-500/20 p-3 rounded-md">
              <strong className="text-yellow-700 dark:text-yellow-500 text-xs uppercase tracking-wider block mb-2">待辦事項</strong>
              <ul className="list-disc pl-4 space-y-1 text-yellow-900 dark:text-yellow-200">
                {email.action_items.map((item, i) => (
                  <li key={i}>{getText(item)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
