import React, { useState, useRef, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { IoArrowBack, IoCloudUpload, IoImage } from 'react-icons/io5'
import { FiClock, FiFileText, FiGrid, FiZap, FiAlertCircle, FiCheck, FiLoader, FiMaximize2, FiMinimize2 } from 'react-icons/fi'
import { useNavigate } from 'react-router-dom'
import config from '../../config'

const API_BASE_URL = config.API_BASE_URL

const OcrTest = () => {
    const navigate = useNavigate()
    const fileInputRef = useRef(null)
    const canvasRef = useRef(null)

    const [file, setFile] = useState(null)
    const [preview, setPreview] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [result, setResult] = useState(null)
    const [showBoxes, setShowBoxes] = useState(true)
    const [activeTab, setActiveTab] = useState('visual')  // 'visual', 'markdown', 'json'
    const [expandedImage, setExpandedImage] = useState(false)

    // Handle file selection
    const handleFile = useCallback((selectedFile) => {
        if (!selectedFile) return
        const allowed = ['image/png', 'image/jpeg', 'image/jpg', 'image/bmp', 'image/webp', 'image/tiff']
        if (!allowed.includes(selectedFile.type)) {
            setError('Only image files (PNG, JPEG, BMP, WebP, TIFF) are accepted')
            return
        }
        setFile(selectedFile)
        setError(null)
        setResult(null)

        const reader = new FileReader()
        reader.onload = (e) => setPreview(e.target.result)
        reader.readAsDataURL(selectedFile)
    }, [])

    // Drag & drop
    const handleDrop = useCallback((e) => {
        e.preventDefault()
        const droppedFile = e.dataTransfer.files[0]
        if (droppedFile) handleFile(droppedFile)
    }, [handleFile])

    const handleDragOver = (e) => e.preventDefault()

    // Send to OCR API
    const handleTestOcr = async () => {
        if (!file) return
        setLoading(true)
        setError(null)

        try {
            const formData = new FormData()
            formData.append('file', file)

            const response = await fetch(`${API_BASE_URL}/api/ocr-test`, {
                method: 'POST',
                body: formData,
            })

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}))
                throw new Error(errData.detail || `Server error: ${response.status}`)
            }

            const data = await response.json()
            setResult(data)
            setActiveTab('visual')
        } catch (err) {
            setError(err.message || 'Failed to process image')
        } finally {
            setLoading(false)
        }
    }

    // Draw bounding boxes on canvas
    useEffect(() => {
        if (!result || !canvasRef.current || !showBoxes) return

        const canvas = canvasRef.current
        const ctx = canvas.getContext('2d')

        const img = new Image()
        img.onload = () => {
            canvas.width = img.width
            canvas.height = img.height
            ctx.drawImage(img, 0, 0)

            // Draw layout bounding boxes
            const layout = result.layout_details || []
            const colors = {
                text: '#4CAF50',
                paragraph_title: '#2196F3',
                title: '#2196F3',
                image: '#FF5722',
                chart: '#FF9800',
                table: '#9C27B0',
                formula: '#E91E63',
                header: '#00BCD4',
                footer: '#607D8B',
            }

            layout.forEach((elem, idx) => {
                const bbox = elem.bbox_2d
                if (!bbox || bbox.length < 4) return

                const [x1, y1, x2, y2] = bbox
                const label = elem.native_label || elem.label || 'unknown'
                const color = colors[label] || '#FFD600'

                // Draw rectangle
                ctx.strokeStyle = color
                ctx.lineWidth = 3
                ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)

                // Semi-transparent fill
                ctx.fillStyle = color + '18'
                ctx.fillRect(x1, y1, x2 - x1, y2 - y1)

                // Label background
                const labelText = `${idx}: ${label}`
                ctx.font = 'bold 14px Inter, sans-serif'
                const metrics = ctx.measureText(labelText)
                const labelH = 22
                ctx.fillStyle = color
                ctx.fillRect(x1, y1 - labelH, metrics.width + 12, labelH)

                // Label text
                ctx.fillStyle = '#fff'
                ctx.fillText(labelText, x1 + 6, y1 - 6)
            })
        }
        img.src = `data:${result.optimized_image_mime};base64,${result.optimized_image_base64}`
    }, [result, showBoxes])

    // Color for element type
    const getTypeColor = (label) => {
        const map = {
            text: 'bg-green-500/20 text-green-300 border-green-500/40',
            paragraph_title: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
            title: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
            image: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
            chart: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
            table: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
            formula: 'bg-pink-500/20 text-pink-300 border-pink-500/40',
        }
        return map[label] || 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40'
    }

    return (
        <div className="min-h-screen w-full flex flex-col relative overflow-hidden">
            {/* Background */}
            <div className="fixed inset-0 bg-gradient-to-br from-[#0a0a0f] via-[#0d0d1a] to-[#0a0a0f] z-0" />

            {/* Content */}
            <div className="relative z-[2] flex flex-col h-screen w-full">

                {/* Top Bar */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-black/30 backdrop-blur-xl shrink-0">
                    <div className="flex items-center gap-4">
                        <motion.button
                            onClick={() => navigate('/')}
                            whileTap={{ scale: 0.95 }}
                            className="p-2 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
                        >
                            <IoArrowBack className="w-5 h-5 text-white/60" />
                        </motion.button>
                        <div>
                            <h1 className="text-lg font-semibold text-white">OCR API Tester</h1>
                            <p className="text-xs text-white/40">
                                Test remote GLM-OCR endpoint → {API_BASE_URL}/api/ocr-test
                            </p>
                        </div>
                    </div>

                    {/* API Status */}
                    <div className="flex items-center gap-2 bg-white/5 rounded-full px-4 py-2 border border-white/10">
                        <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-xs text-white/60 font-mono truncate max-w-[300px]">
                            {result?.api_url || 'Ready'}
                        </span>
                    </div>
                </div>

                {/* Main Content */}
                <div className="flex-1 flex gap-5 p-5 min-h-0">

                    {/* Left Panel: Upload & Image */}
                    <div className="w-[45%] flex flex-col gap-4 min-h-0">

                        {/* Upload Zone */}
                        {!preview ? (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="flex-1 border-2 border-dashed border-white/15 rounded-2xl flex flex-col items-center justify-center gap-4 cursor-pointer hover:border-violet-500/40 hover:bg-violet-500/5 transition-all"
                                onClick={() => fileInputRef.current?.click()}
                                onDrop={handleDrop}
                                onDragOver={handleDragOver}
                            >
                                <IoCloudUpload className="w-16 h-16 text-white/15" />
                                <p className="text-white/40 text-sm font-medium">
                                    Drop an image here or click to upload
                                </p>
                                <p className="text-white/20 text-xs">
                                    PNG, JPEG, BMP, WebP, TIFF
                                </p>
                            </motion.div>
                        ) : (
                            <div className="flex-1 flex flex-col min-h-0 bg-[#1a1a2e] rounded-2xl border border-white/10 overflow-hidden">
                                {/* Image Header */}
                                <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 shrink-0">
                                    <div className="flex items-center gap-2">
                                        <IoImage className="w-4 h-4 text-violet-400" />
                                        <span className="text-sm font-medium text-white/70 truncate max-w-[200px]">
                                            {file?.name}
                                        </span>
                                        {result && (
                                            <span className="text-xs text-white/30 ml-2">
                                                {result.original_size_kb}KB → {result.optimized_size_kb}KB
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex gap-2">
                                        {result && (
                                            <button
                                                onClick={() => setShowBoxes(!showBoxes)}
                                                className={`px-3 py-1 text-xs rounded-lg border transition-colors cursor-pointer ${showBoxes
                                                    ? 'bg-violet-500/20 border-violet-500/40 text-violet-300'
                                                    : 'bg-white/5 border-white/10 text-white/40'
                                                    }`}
                                            >
                                                {showBoxes ? '☑ Boxes' : '☐ Boxes'}
                                            </button>
                                        )}
                                        <button
                                            onClick={() => { setFile(null); setPreview(null); setResult(null); setError(null) }}
                                            className="px-3 py-1 text-xs rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 hover:bg-red-500/20 transition-colors cursor-pointer"
                                        >
                                            Clear
                                        </button>
                                    </div>
                                </div>

                                {/* Image Display */}
                                <div className="flex-1 overflow-auto p-4 flex items-start justify-center sidebar-scroll">
                                    {result && showBoxes ? (
                                        <canvas
                                            ref={canvasRef}
                                            className="max-w-full h-auto rounded-lg shadow-2xl"
                                            style={{ maxHeight: expandedImage ? 'none' : '100%' }}
                                        />
                                    ) : (
                                        <img
                                            src={preview}
                                            alt="Upload preview"
                                            className="max-w-full h-auto rounded-lg shadow-2xl"
                                            style={{ maxHeight: expandedImage ? 'none' : '100%' }}
                                        />
                                    )}
                                </div>

                                {/* Test Button */}
                                <div className="px-4 py-3 border-t border-white/10 shrink-0">
                                    <motion.button
                                        onClick={handleTestOcr}
                                        disabled={loading}
                                        whileTap={{ scale: 0.98 }}
                                        className="w-full py-3 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 cursor-pointer transition-all disabled:opacity-50 disabled:cursor-not-allowed bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-500 hover:to-blue-500 text-white shadow-lg shadow-violet-500/20"
                                    >
                                        {loading ? (
                                            <>
                                                <FiLoader className="w-4 h-4 animate-spin" />
                                                Processing... (may take 30-60s)
                                            </>
                                        ) : (
                                            <>
                                                <FiZap className="w-4 h-4" />
                                                Test OCR API
                                            </>
                                        )}
                                    </motion.button>
                                </div>
                            </div>
                        )}

                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={(e) => handleFile(e.target.files[0])}
                        />
                    </div>

                    {/* Right Panel: Results */}
                    <div className="flex-1 flex flex-col min-h-0 bg-[#1a1a2e] rounded-2xl border border-white/10 overflow-hidden">

                        {/* Tabs */}
                        <div className="flex items-center gap-1 px-4 pt-3 pb-0 shrink-0">
                            {[
                                { key: 'visual', label: 'Layout Elements', icon: FiGrid },
                                { key: 'markdown', label: 'Markdown', icon: FiFileText },
                                { key: 'json', label: 'Raw JSON', icon: FiFileText },
                            ].map(tab => (
                                <button
                                    key={tab.key}
                                    onClick={() => setActiveTab(tab.key)}
                                    className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold tracking-wide rounded-t-lg transition-all cursor-pointer ${activeTab === tab.key
                                        ? 'bg-white/10 text-white border-b-2 border-violet-500'
                                        : 'text-white/30 hover:text-white/50'
                                        }`}
                                >
                                    <tab.icon className="w-3.5 h-3.5" />
                                    {tab.label}
                                </button>
                            ))}
                        </div>

                        {/* Results Content */}
                        <div className="flex-1 overflow-auto p-4 sidebar-scroll">

                            {error && (
                                <motion.div
                                    initial={{ opacity: 0, y: -10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 mb-4"
                                >
                                    <FiAlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                                    <div>
                                        <p className="text-sm text-red-300 font-medium">Error</p>
                                        <p className="text-xs text-red-300/70 mt-1">{error}</p>
                                    </div>
                                </motion.div>
                            )}

                            {!result && !loading && !error && (
                                <div className="flex flex-col items-center justify-center h-full text-white/15 gap-4">
                                    <FiGrid className="w-16 h-16" />
                                    <p className="text-sm font-medium">Upload an image and click "Test OCR API"</p>
                                    <p className="text-xs text-white/10">Results will appear here with bounding boxes visualization</p>
                                </div>
                            )}

                            {loading && (
                                <div className="flex flex-col items-center justify-center h-full text-white/30 gap-4">
                                    <FiLoader className="w-12 h-12 animate-spin text-violet-400/50" />
                                    <p className="text-sm font-medium">Sending image to remote API...</p>
                                    <p className="text-xs text-white/20">This may take 30-60 seconds depending on image complexity</p>
                                </div>
                            )}

                            {result && (
                                <AnimatePresence mode="wait">
                                    <motion.div
                                        key={activeTab}
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -10 }}
                                        transition={{ duration: 0.2 }}
                                    >
                                        {/* Stats Bar */}
                                        <div className="flex gap-3 mb-4 flex-wrap">
                                            <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2">
                                                <FiCheck className="w-3.5 h-3.5 text-emerald-400" />
                                                <span className="text-xs text-emerald-300">Success</span>
                                            </div>
                                            <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
                                                <FiClock className="w-3.5 h-3.5 text-white/40" />
                                                <span className="text-xs text-white/60">{result.processing_time_seconds}s</span>
                                            </div>
                                            <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
                                                <FiGrid className="w-3.5 h-3.5 text-white/40" />
                                                <span className="text-xs text-white/60">{result.layout_details?.length || 0} elements</span>
                                            </div>
                                            <div className="flex items-center gap-1.5 bg-white/5 border border-white/10 rounded-lg px-3 py-2">
                                                <FiFileText className="w-3.5 h-3.5 text-white/40" />
                                                <span className="text-xs text-white/60">{result.markdown_result?.length || 0} chars</span>
                                            </div>
                                        </div>

                                        {activeTab === 'visual' && (
                                            <div className="space-y-3">
                                                {result.layout_details?.length === 0 && (
                                                    <div className="p-6 text-center text-white/20 text-sm border border-white/5 rounded-xl">
                                                        No layout elements detected
                                                    </div>
                                                )}
                                                {result.layout_details?.map((elem, idx) => (
                                                    <div
                                                        key={idx}
                                                        className="p-4 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/10 transition-colors"
                                                    >
                                                        <div className="flex items-center justify-between mb-2">
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-xs font-mono text-white/30">#{idx}</span>
                                                                <span className={`px-2 py-0.5 text-xs font-semibold rounded-full border ${getTypeColor(elem.native_label || elem.label)}`}>
                                                                    {elem.native_label || elem.label}
                                                                </span>
                                                            </div>
                                                            <span className="text-xs font-mono text-white/20">
                                                                bbox: [{elem.bbox_2d?.join(', ')}]
                                                            </span>
                                                        </div>
                                                        {elem.content && (
                                                            <div className="mt-2 p-3 bg-black/30 rounded-lg">
                                                                <p className="text-sm text-white/70 font-mono whitespace-pre-wrap break-all">
                                                                    {elem.content}
                                                                </p>
                                                            </div>
                                                        )}
                                                        {!elem.content && (
                                                            <p className="text-xs text-white/15 italic mt-1">No text content extracted</p>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {activeTab === 'markdown' && (
                                            <div className="rounded-xl bg-black/30 border border-white/5 p-4">
                                                {result.markdown_result ? (
                                                    <pre className="text-sm text-white/70 font-mono whitespace-pre-wrap break-all leading-relaxed">
                                                        {result.markdown_result}
                                                    </pre>
                                                ) : (
                                                    <p className="text-white/20 text-sm italic text-center py-8">
                                                        No markdown content returned by the API
                                                    </p>
                                                )}
                                            </div>
                                        )}

                                        {activeTab === 'json' && (
                                            <div className="rounded-xl bg-black/30 border border-white/5 p-4">
                                                <pre className="text-xs text-white/60 font-mono whitespace-pre-wrap break-all leading-relaxed max-h-[600px] overflow-auto sidebar-scroll">
                                                    {JSON.stringify({
                                                        api_url: result.api_url,
                                                        processing_time_seconds: result.processing_time_seconds,
                                                        original_size_kb: result.original_size_kb,
                                                        optimized_size_kb: result.optimized_size_kb,
                                                        markdown_result: result.markdown_result,
                                                        layout_details: result.layout_details,
                                                    }, null, 2)}
                                                </pre>
                                            </div>
                                        )}
                                    </motion.div>
                                </AnimatePresence>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default OcrTest
