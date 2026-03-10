import React, { useState, useMemo, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { IoArrowBack, IoDocument } from 'react-icons/io5'
import { FiChevronLeft, FiChevronRight, FiCheck, FiLoader, FiAlertCircle, FiMaximize2, FiDownload } from 'react-icons/fi'
import { translateAPI } from '../../services/api'

/**
 * WPS-style page-by-page viewer.
 * Shows original page image on the left, translated/reconstructed content on the right.
 * Pages appear as they stream in via SSE.
 */
const PageViewer = ({
    pages,
    totalPages,
    currentPage,
    setCurrentPage,
    isProcessing,
    progressMessage,
    progressStage,
    completedPagesCount,
    jobComplete,
    jobError,
    fileName,
    onBack,
    jobId,
    originalPdfUrl,
}) => {
    const [viewMode, setViewMode] = useState('split') // 'split', 'original', 'translated'
    const [downloadingDocx, setDownloadingDocx] = useState(false)
    const [downloadingPdf, setDownloadingPdf] = useState(false)

    const currentPageData = pages[currentPage] || null
    const isCurrentPageReady = currentPageData?.status === 'completed'

    const [autoFollow, setAutoFollow] = useState(true)

    // Retrigger MathJax parsing whenever HTML is injected 
    useEffect(() => {
        if (window.MathJax && currentPageData?.reconstructed_html) {
            // Small delay to let React render the HTML first
            const timer = setTimeout(() => {
                if (window.MathJax.typesetPromise) {
                    window.MathJax.typesetClear?.();
                    window.MathJax.typesetPromise().catch((err) => console.error("MathJax processing error:", err));
                }
            }, 100);
            return () => clearTimeout(timer);
        }
    }, [currentPageData?.reconstructed_html, viewMode, currentPage]);

    // Auto-scroll logic: Follow the current processing page sequentially
    useEffect(() => {
        if (isProcessing && autoFollow) {
            const processingPage = completedPagesCount + 1;
            if (processingPage <= totalPages && processingPage !== currentPage) {
                setCurrentPage(processingPage);
            }
        }
    }, [completedPagesCount, isProcessing, totalPages, autoFollow, currentPage, setCurrentPage]);

    // Page navigation
    const canGoPrev = currentPage > 1
    const canGoNext = currentPage < totalPages

    const goToPage = (num) => {
        if (num >= 1 && num <= totalPages) {
            setAutoFollow(false) // User manually navigated, stop auto-following
            setCurrentPage(num)
        }
    }

    // Progress percentage
    const progress = totalPages > 0 ? (completedPagesCount / totalPages) * 100 : 0

    // --- Download real DOCX from backend ---
    const handleDownloadDocx = async () => {
        if (!jobId) return
        setDownloadingDocx(true)
        try {
            const url = translateAPI.getDocxDownloadUrl(jobId)
            const response = await fetch(url)
            if (!response.ok) {
                const errText = await response.text().catch(() => 'Unknown error')
                throw new Error(`Server error ${response.status}: ${errText}`)
            }
            const blob = await response.blob()
            const blobUrl = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = blobUrl
            link.download = `${fileName.replace('.pdf', '')}_translated.docx`
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            URL.revokeObjectURL(blobUrl)
        } catch (err) {
            console.error('DOCX download error:', err)
            alert(`DOCX download failed: ${err.message}`)
        } finally {
            setDownloadingDocx(false)
        }
    }

    // --- Download PDF directly from backend (Playwright-rendered) ---
    const handleDownloadPdf = async () => {
        if (!jobId) return
        setDownloadingPdf(true)
        try {
            const url = translateAPI.getPdfDownloadUrl(jobId)
            const response = await fetch(url)
            if (!response.ok) {
                const errText = await response.text().catch(() => 'Unknown error')
                throw new Error(`Server error ${response.status}: ${errText}`)
            }
            const blob = await response.blob()
            const blobUrl = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = blobUrl
            link.download = `${fileName.replace('.pdf', '')}_translated.pdf`
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            URL.revokeObjectURL(blobUrl)
        } catch (err) {
            console.error('PDF download error:', err)
            alert(`PDF download failed: ${err.message}`)
        } finally {
            setDownloadingPdf(false)
        }
    }

    return (
        <div className="h-screen w-full flex flex-col relative overflow-hidden print:bg-white print:overflow-visible">
            {/* Background */}
            <div className="fixed inset-0 bg-gradient-to-br from-[#0a0a0f] via-[#0d0d1a] to-[#0a0a0f] z-0 print:hidden" />

            {/* Content */}
            <div className="relative z-[2] flex flex-col h-full w-full">

                {/* Top Bar - Styled like old PDF Output Header */}
                <div className="flex flex-col gap-4 items-start relative shrink-0 w-full px-5 pt-5 pb-2 border-b border-[#434242] bg-[#1a1a1a]">
                    <div className="flex items-center justify-between px-1.5 py-0 relative shrink-0 w-full">
                        <div className="flex gap-4 items-center relative shrink-0">
                            {/* Back Button */}
                            <motion.button
                                onClick={onBack}
                                whileTap={{ scale: 0.95 }}
                                className="cursor-pointer flex items-center justify-center p-2 rounded-lg"
                            >
                                <IoArrowBack className="w-5 h-5 text-[#b5b5b5]" />
                            </motion.button>
                            <p className="font-semibold leading-7 text-lg text-[#d9d9d9] text-center relative shrink-0">
                                {fileName}
                            </p>

                            {/* Center: Page Navigation */}
                            <div className="flex items-center gap-2 border-l border-[#333] pl-4 ml-2">
                                <button
                                    onClick={() => goToPage(currentPage - 1)}
                                    disabled={!canGoPrev}
                                    className={`p-1.5 rounded-lg transition-colors cursor-pointer ${canGoPrev ? 'hover:bg-white/5 text-white/60' : 'text-white/15 cursor-not-allowed'}`}
                                >
                                    <FiChevronLeft className="w-5 h-5" />
                                </button>
                                <div className="flex items-center gap-1.5 bg-white/[0.04] rounded-lg px-3 py-1.5">
                                    <span className="text-sm text-white font-medium">{currentPage}</span>
                                    <span className="text-xs text-white/30">/</span>
                                    <span className="text-sm text-white/40">{totalPages || '?'}</span>
                                </div>
                                <button
                                    onClick={() => goToPage(currentPage + 1)}
                                    disabled={!canGoNext}
                                    className={`p-1.5 rounded-lg transition-colors cursor-pointer ${canGoNext ? 'hover:bg-white/5 text-white/60' : 'text-white/15 cursor-not-allowed'}`}
                                >
                                    <FiChevronRight className="w-5 h-5" />
                                </button>
                            </div>
                        </div>

                        {/* Right Actions */}
                        <div className="flex gap-2.5 items-center justify-end relative shrink-0">
                            {/* View Mode Toggle */}
                            <div className="flex bg-[#2e2e2e] rounded-lg overflow-hidden border border-[#4a4a4a] shadow-sm mr-2">
                                {[
                                    { key: 'split', label: 'Split' },
                                    { key: 'original', label: 'Original' },
                                    { key: 'translated', label: 'Translated' },
                                ].map(mode => (
                                    <button
                                        key={mode.key}
                                        onClick={() => setViewMode(mode.key)}
                                        className={`px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-all cursor-pointer border-r last:border-r-0 border-[#3a3a3a] ${viewMode === mode.key
                                            ? 'bg-violet-600 border-violet-500 text-white'
                                            : 'text-[#888] hover:text-[#bbb] hover:bg-white/5'
                                            }`}
                                    >
                                        {mode.label}
                                    </button>
                                ))}
                            </div>

                            {/* Status Indicator */}
                            {jobComplete ? (
                                <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-3 py-1.5 mr-2">
                                    <FiCheck className="w-3.5 h-3.5 text-emerald-400" />
                                    <span className="text-xs text-emerald-300 font-medium">Complete</span>
                                </div>
                            ) : isProcessing ? (
                                <div className="flex items-center gap-1.5 bg-violet-500/10 border border-violet-500/20 rounded-full px-3 py-1.5 mr-2">
                                    <FiLoader className="w-3.5 h-3.5 text-violet-400 animate-spin" />
                                    <span className="text-xs text-violet-300 font-medium">{completedPagesCount}/{totalPages}</span>
                                </div>
                            ) : null}

                            {/* Download Buttons */}
                            {jobComplete && (
                                <div className="flex gap-2 shrink-0">
                                    <motion.button
                                        onClick={handleDownloadDocx}
                                        disabled={downloadingDocx}
                                        whileTap={{ scale: 0.95 }}
                                        className="bg-[#2453c5] border border-[#3b6fe8] border-solid flex gap-1.5 items-center justify-center px-4 py-2 relative rounded-lg shrink-0 cursor-pointer shadow-lg hover:brightness-110 transition-all text-white text-sm font-bold disabled:opacity-50"
                                    >
                                        {downloadingDocx ? (
                                            <FiLoader className="size-4 animate-spin" />
                                        ) : (
                                            <IoDocument className="size-4" />
                                        )}
                                        DOCX
                                    </motion.button>
                                    <motion.button
                                        onClick={handleDownloadPdf}
                                        disabled={downloadingPdf}
                                        whileTap={{ scale: 0.95 }}
                                        className="bg-[#0e7a0d] border border-[#1bc119] border-solid flex gap-1.5 items-center justify-center px-4 py-2 relative rounded-lg shrink-0 cursor-pointer shadow-lg hover:brightness-110 transition-all text-white text-sm font-bold disabled:opacity-50"
                                    >
                                        {downloadingPdf ? (
                                            <FiLoader className="size-4 animate-spin" />
                                        ) : (
                                            <FiDownload className="size-4 text-white" />
                                        )}
                                        PDF
                                    </motion.button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Progress Bar */}
                {isProcessing && (
                    <div className="w-full h-1 bg-white/5 shrink-0">
                        <motion.div
                            className="h-full bg-gradient-to-r from-violet-500 to-blue-500"
                            initial={{ width: 0 }}
                            animate={{ width: `${progress}%` }}
                            transition={{ duration: 0.5, ease: "easeOut" }}
                        />
                    </div>
                )}

                {/* Status Message Bar */}
                {progressMessage && isProcessing && (
                    <div className="px-4 py-2 bg-violet-500/5 border-b border-white/5 shrink-0">
                        <p className="text-xs text-violet-300/80 text-center truncate">{progressMessage}</p>
                    </div>
                )}

                {/* Error Bar */}
                {jobError && (
                    <div className="px-4 py-3 bg-red-500/10 border-b border-red-500/20 shrink-0">
                        <div className="flex items-center gap-2 justify-center">
                            <FiAlertCircle className="w-4 h-4 text-red-400" />
                            <p className="text-sm text-red-300">{jobError}</p>
                        </div>
                    </div>
                )}

                {/* Main Content: Split View - Animated */}
                <div className="flex-1 flex gap-6 min-h-0 min-w-0 pb-4 px-4 pt-4 bg-[#000]">
                    <AnimatePresence mode="popLayout" initial={false}>
                        <motion.div
                            key={"page_" + currentPage + "_" + viewMode}
                            initial={{ opacity: 0, y: 15, scale: 0.98 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: -15, scale: 0.98 }}
                            transition={{ duration: 0.4, type: "spring", bounce: 0.2 }}
                            className="w-full flex-1 flex gap-6 min-h-0 min-w-0"
                        >
                            {/* Left Panel: Original Page Image */}
                            {(viewMode === 'split' || viewMode === 'original') && (
                                <div className={`bg-[#2a2a2a] border border-[#434242] border-solid flex flex-col gap-3 items-start min-h-0 min-w-0 p-4 rounded-[10px] overflow-hidden ${viewMode === 'split' ? 'w-1/2 flex-1' : 'w-full flex-1'}`}>
                                    {/* Header Section */}
                                    <div className="flex flex-col gap-4 items-start justify-center relative shrink-0 w-full border-b border-[#434242] pb-4">
                                        <div className="flex items-center justify-between px-1.5 py-0 relative shrink-0 w-full">
                                            <div className="flex gap-1.5 items-center relative shrink-0">
                                                <p className="font-semibold leading-7 text-lg text-[#d9d9d9] text-center relative shrink-0">
                                                    Original Page
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Viewer Container */}
                                    <div className="flex flex-1 flex-col items-start min-h-0 min-w-0 relative w-full overflow-hidden">
                                        <div className="flex flex-1 flex-col min-h-0 min-w-full relative w-full bg-[#1c1c1c] overflow-y-auto overflow-x-hidden rounded-lg items-center p-4 sidebar-scroll">
                                            {currentPageData?.original_image_base64 ? (
                                                <img
                                                    src={`data:image/png;base64,${currentPageData.original_image_base64}`}
                                                    alt={`Page ${currentPage}`}
                                                    className="max-w-full h-auto w-auto rounded shadow-xl object-contain"
                                                />
                                            ) : (
                                                <div className="flex flex-col items-center justify-center h-full text-white/20 gap-3 min-h-[400px]">
                                                    {isProcessing ? (
                                                        <>
                                                            <FiLoader className="w-8 h-8 animate-spin text-violet-400/40" />
                                                            <p className="text-sm">Processing page {currentPage}...</p>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <IoDocument className="w-12 h-12" />
                                                            <p className="text-sm">Page not yet processed</p>
                                                        </>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Right Panel: Translated/Reconstructed Content */}
                            {(viewMode === 'split' || viewMode === 'translated') && (
                                <div className={`bg-[#2a2a2a] border border-[#434242] border-solid flex flex-col gap-3 items-start min-h-0 min-w-0 p-4 rounded-[10px] overflow-hidden ${viewMode === 'split' ? 'w-1/2 flex-1' : 'w-full flex-1'}`}>
                                    {/* Header Section */}
                                    <div className="flex flex-col gap-4 items-start relative shrink-0 w-full border-b border-[#434242] pb-4">
                                        <div className="flex items-center justify-between px-1.5 py-0 relative shrink-0 w-full">
                                            <div className="flex gap-1.5 items-center relative shrink-0">
                                                <p className="font-semibold leading-7 text-lg text-[#d9d9d9] text-center relative shrink-0">
                                                    Translated Page
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Viewer Container */}
                                    <div className="flex flex-1 flex-col items-start min-h-0 min-w-0 relative w-full overflow-hidden">
                                        <div className="flex flex-col min-h-0 min-w-full relative w-full bg-white overflow-y-auto overflow-x-hidden rounded-lg px-6 py-4 flex-1 sidebar-scroll">
                                            {currentPageData?.status === 'completed' && currentPageData?.reconstructed_html ? (
                                                <div
                                                    className="translated-content w-full h-full text-black"
                                                    dangerouslySetInnerHTML={{ __html: currentPageData.reconstructed_html }}
                                                />
                                            ) : currentPageData?.status === 'failed' ? (
                                                <div className="flex flex-col items-center justify-center h-full gap-3 p-8 min-h-[400px]">
                                                    <FiAlertCircle className="w-8 h-8 text-red-400" />
                                                    <p className="text-sm text-red-500 text-center">{currentPageData.error || 'Page processing failed'}</p>
                                                </div>
                                            ) : (
                                                <div className="flex flex-col items-center justify-center h-full text-gray-500 gap-3 p-8 min-h-[400px]">
                                                    {isProcessing ? (
                                                        <>
                                                            <FiLoader className="w-8 h-8 animate-spin text-violet-400" />
                                                            <p className="text-sm text-gray-400">{progressMessage || 'Processing...'}</p>
                                                        </>
                                                    ) : (
                                                        <>
                                                            <IoDocument className="w-12 h-12 text-gray-200" />
                                                            <p className="text-sm text-gray-400">Waiting for translation...</p>
                                                        </>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </motion.div>
                    </AnimatePresence>
                </div>

                {/* Bottom: Page Thumbnails Strip */}
                <div className="border-t border-white/5 bg-black/30 backdrop-blur-xl px-4 py-3 shrink-0">
                    <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
                        {Array.from({ length: totalPages || 0 }, (_, i) => i + 1).map(pageNum => {
                            const pageData = pages[pageNum]
                            const isActive = pageNum === currentPage
                            const isComplete = pageData?.status === 'completed'
                            const isFailed = pageData?.status === 'failed'

                            return (
                                <button
                                    key={pageNum}
                                    onClick={() => goToPage(pageNum)}
                                    className={`relative shrink-0 w-12 h-16 rounded-lg border-2 transition-all duration-200 overflow-hidden cursor-pointer ${isActive
                                        ? 'border-violet-500 shadow-lg shadow-violet-500/20'
                                        : isComplete
                                            ? 'border-emerald-500/30 hover:border-emerald-500/50'
                                            : isFailed
                                                ? 'border-red-500/30'
                                                : 'border-white/10 hover:border-white/20'
                                        }`}
                                >
                                    {/* Thumbnail preview */}
                                    {pageData?.original_image_base64 ? (
                                        <img
                                            src={`data:image/png;base64,${pageData.original_image_base64}`}
                                            alt={`Page ${pageNum}`}
                                            className="w-full h-full object-cover"
                                        />
                                    ) : (
                                        <div className="w-full h-full bg-white/[0.03] flex items-center justify-center">
                                            <span className="text-[10px] text-white/20">{pageNum}</span>
                                        </div>
                                    )}

                                    {/* Status indicator */}
                                    <div className="absolute bottom-0.5 right-0.5">
                                        {isComplete && <FiCheck className="w-3 h-3 text-emerald-400 drop-shadow-md" />}
                                        {isFailed && <FiAlertCircle className="w-3 h-3 text-red-400 drop-shadow-md" />}
                                        {!isComplete && !isFailed && isProcessing && pageNum <= (completedPagesCount + 1) && (
                                            <FiLoader className="w-3 h-3 text-violet-400 animate-spin" />
                                        )}
                                    </div>
                                </button>
                            )
                        })}
                    </div>
                </div>
            </div>

            {/* Print-only container for generating PDFs */}
            <div className="hidden print:block w-full bg-white text-black p-8">
                {Object.values(pages)
                    .sort((a, b) => a.page_number - b.page_number)
                    .map((pageData) => (
                        <div key={pageData.page_number} className="w-full min-h-[297mm] break-after-page border-b border-gray-200 pb-8 mb-8">
                            <h2 className="text-gray-400 text-sm mb-4 border-b pb-2">Page {pageData.page_number}</h2>
                            {pageData.reconstructed_html ? (
                                <div
                                    className="print-content"
                                    dangerouslySetInnerHTML={{ __html: pageData.reconstructed_html }}
                                />
                            ) : (
                                <div className="text-center text-gray-500 py-20">Page {pageData.page_number} failed to translate.</div>
                            )}
                        </div>
                    ))}
            </div>
        </div>
    )
}

export default PageViewer
