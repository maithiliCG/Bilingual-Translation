import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { IoChevronDown, IoCloudUpload, IoClose, IoDocument } from 'react-icons/io5'
import { FiChevronLeft, FiChevronRight, FiDownload, FiLoader, FiCheck, FiAlertCircle } from 'react-icons/fi'
import { resourceAPI, translateAPI } from '../../services/api'
import config from '../../config'
import PageViewer from './PageViewer'

const Dashboard = () => {
  const navigate = useNavigate()
  // Upload state
  const [activeTab, setActiveTab] = useState('monolingual') // 'monolingual' or 'bilingual'
  const [uploadedFile, setUploadedFile] = useState(null)
  const [selectedLanguage, setSelectedLanguage] = useState('')
  const [languages, setLanguages] = useState([])
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)
  const [error, setError] = useState('')

  // Pipeline state
  const [isProcessing, setIsProcessing] = useState(false)
  const [showViewer, setShowViewer] = useState(false)
  const [jobId, setJobId] = useState(null)
  const [totalPages, setTotalPages] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [progressMessage, setProgressMessage] = useState('')
  const [progressStage, setProgressStage] = useState('')
  const [pages, setPages] = useState({})  // { pageNum: { ...pageData } }
  const [jobComplete, setJobComplete] = useState(false)
  const [jobError, setJobError] = useState(null)

  const fileInputRef = useRef(null)
  const dropdownRef = useRef(null)
  const eventSourceRef = useRef(null)

  // Fetch languages
  useEffect(() => {
    const fetchLanguages = async () => {
      try {
        const response = await resourceAPI.getLanguages()
        const langs = response.data.languages || []
        setLanguages(langs)
        if (langs.length > 0) {
          const defaultLang = langs.find(l => l.code === 'te') || langs[0]
          setSelectedLanguage(defaultLang.code)
        }
      } catch (err) {
        console.error("Failed to fetch languages:", err)
        setError("Failed to load languages. Is the backend running?")
      }
    }
    fetchLanguages()
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (file) {
      if (file.type !== 'application/pdf') {
        setError('Please select a valid PDF file')
        return
      }
      if (file.size > 500 * 1024 * 1024) {
        setError('File size exceeds 500MB limit')
        return
      }
      setUploadedFile({
        name: file.name,
        size: file.size,
        url: URL.createObjectURL(file),
        file: file,
      })
      setError('')
    }
  }

  const handleRemoveFile = () => {
    if (uploadedFile?.url) URL.revokeObjectURL(uploadedFile.url)
    setUploadedFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file && file.type === 'application/pdf') {
      setUploadedFile({
        name: file.name,
        size: file.size,
        url: URL.createObjectURL(file),
        file: file,
      })
      setError('')
    }
  }

  // --- Start Translation Pipeline ---
  const handleGenerate = async () => {
    if (!uploadedFile) { setError('Please upload a PDF first'); return }
    if (!selectedLanguage) { setError('Please select a language'); return }

    setError('')
    setIsProcessing(true)
    setShowViewer(true)
    setPages({})
    setJobComplete(false)
    setJobError(null)
    setCurrentPage(1)
    setProgressMessage('Uploading PDF...')
    setProgressStage('uploading')

    try {
      // Step 1: Upload PDF
      const formData = new FormData()
      formData.append('file', uploadedFile.file)
      formData.append('target_language', selectedLanguage)
      formData.append('translation_mode', activeTab)

      const uploadRes = await translateAPI.uploadAndTranslate(formData)
      const newJobId = uploadRes.data.job_id

      setJobId(newJobId)
      setProgressMessage('PDF uploaded. Starting pipeline...')

      // Step 2: Register pipeline
      await translateAPI.startPipeline(newJobId, selectedLanguage, activeTab)

      // Step 3: Connect SSE stream
      connectSSE(newJobId)

    } catch (err) {
      console.error('Upload failed:', err)
      setIsProcessing(false)
      setJobError(err.response?.data?.detail || err.message || 'Upload failed')
      setProgressMessage('')
    }
  }

  // --- SSE Connection ---
  const connectSSE = useCallback((jId) => {
    const streamUrl = translateAPI.getStreamUrl(jId)
    const es = new EventSource(streamUrl)
    eventSourceRef.current = es

    es.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data)
        setProgressMessage(data.message || '')
        setProgressStage(data.stage || '')
        if (data.total_pages) setTotalPages(data.total_pages)
      } catch (err) {
        console.error('Progress parse error:', err)
      }
    })

    es.addEventListener('page_complete', (e) => {
      try {
        const data = JSON.parse(e.data)
        const pageNum = data.page_number
        setTotalPages(data.total_pages)

        setPages(prev => ({
          ...prev,
          [pageNum]: {
            page_number: pageNum,
            status: 'completed',
            original_image_base64: data.original_image_base64,
            original_markdown: data.original_markdown,
            translated_markdown: data.translated_markdown,
            reconstructed_html: data.reconstructed_html,
          }
        }))

        setProgressMessage(`Page ${pageNum}/${data.total_pages} completed`)
      } catch (err) {
        console.error('Page complete parse error:', err)
      }
    })

    es.addEventListener('page_error', (e) => {
      try {
        const data = JSON.parse(e.data)
        const pageNum = data.page_number
        setPages(prev => ({
          ...prev,
          [pageNum]: {
            page_number: pageNum,
            status: 'failed',
            error: data.error,
          }
        }))
      } catch (err) {
        console.error('Page error parse error:', err)
      }
    })

    es.addEventListener('job_complete', (e) => {
      try {
        const data = JSON.parse(e.data)
        setJobComplete(true)
        setIsProcessing(false)
        setProgressMessage(data.message || 'All pages completed!')
        setProgressStage('completed')
      } catch (err) {
        console.error('Job complete parse error:', err)
      }
      es.close()
    })

    es.addEventListener('job_error', (e) => {
      try {
        const data = JSON.parse(e.data)
        setJobError(data.error || 'Pipeline failed')
        setIsProcessing(false)
        setProgressMessage('')
      } catch (err) {
        console.error('Job error parse error:', err)
      }
      es.close()
    })

    es.addEventListener('done', () => {
      setIsProcessing(false)
      es.close()
    })

    es.addEventListener('error', () => {
      // Don't set error on close
      if (es.readyState === EventSource.CLOSED) return
      console.error('SSE connection error')
    })

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) return
      // Auto-reconnect is built-in for EventSource
    }
  }, [])

  const handleBack = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }
    setShowViewer(false)
    setIsProcessing(false)
    setPages({})
    setJobId(null)
    setTotalPages(0)
    setCurrentPage(1)
    setJobComplete(false)
    setJobError(null)
    setProgressMessage('')
  }

  const selectedLangName = languages.find(l => l.code === selectedLanguage)?.name || 'Select language'
  const completedPagesCount = Object.values(pages).filter(p => p.status === 'completed').length

  // --- Viewer Mode ---
  if (showViewer) {
    return (
      <PageViewer
        pages={pages}
        totalPages={totalPages}
        currentPage={currentPage}
        setCurrentPage={setCurrentPage}
        isProcessing={isProcessing}
        progressMessage={progressMessage}
        progressStage={progressStage}
        completedPagesCount={completedPagesCount}
        jobComplete={jobComplete}
        jobError={jobError}
        fileName={uploadedFile?.name || 'Document'}
        onBack={handleBack}
        jobId={jobId}
        originalPdfUrl={uploadedFile?.url}
      />
    )
  }

  // --- Upload Mode ---
  return (
    <div className="min-h-screen w-full flex">
      {/* Main Content Area with Background */}
      <motion.main
        className="flex flex-1 flex-col min-h-screen items-center min-w-0 relative overflow-y-auto"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        {/* LAYER 1 — Solid background color */}
        <div className="fixed inset-0 bg-[#000000] z-0" />

        {/* LAYER 2 — Spotlight PNG background */}
        <div
          className="fixed inset-0 bg-no-repeat bg-cover bg-center z-[1] pointer-events-none"
          style={{
            backgroundImage: 'url(/Images/backgroundimage.png)'
          }}
        />

        {/* LAYER 3 — Content */}
        <div className="relative z-[2] flex flex-col min-h-screen w-full">
          {/* Content Header */}
          <motion.div
            className="flex items-center justify-between p-3 sm:p-4 md:p-5 w-full"
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.2 }}
          >
            <div className="flex gap-2 items-center px-2 py-2 rounded-lg">
              <p className="text-base sm:text-lg md:text-xl font-semibold text-[#b5b5b5] leading-tight">
                PDF Translator V2
              </p>
              <div className="w-4 h-4 sm:w-5 sm:h-5 shrink-0">
                <img src="/Images/magic-pen-icon.png" alt="Magic pen" className="w-full h-full object-contain" />
              </div>
            </div>
            <motion.button
              onClick={() => navigate('/ocr-test')}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-600/20 border border-violet-500/30 text-violet-300 text-xs sm:text-sm font-semibold hover:bg-violet-600/30 transition-colors cursor-pointer"
            >
              <span className="text-base">🔬</span>
              Test OCR API
            </motion.button>
          </motion.div>

          {/* Main Content Section */}
          <div className="flex flex-1 flex-col gap-6 sm:gap-8 md:gap-[3.125rem] items-center justify-center min-h-0 min-w-0 pb-8 sm:pb-12 md:pb-[9.375rem] pt-4 sm:pt-6 md:pt-0 px-4 sm:px-6 md:px-0 w-full">
            {/* Heading Section */}
            <motion.div
              className="flex flex-col gap-2 sm:gap-3 md:gap-4 items-center w-full"
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              <div className="w-10 h-10 sm:w-12 sm:h-12 md:w-[3.125rem] md:h-[3.125rem]">
                <img src="/Images/magic-pen-icon.png" alt="Magic pen" className="w-full h-full object-contain" />
              </div>

              <div className="flex flex-col font-semibold items-center text-center px-2">
                <h1 className="text-[clamp(1.25rem,5vw,3rem)] font-semibold leading-[clamp(1.75rem,6vw,3.75rem)] text-[#d9d9d9] tracking-[-0.02rem] sm:tracking-[-0.045rem]">
                  Your <span className="text-[clamp(1.25rem,5vw,3rem)]">All-in-One AI</span> Tool for PDFs
                </h1>
                <motion.p
                  className="leading-[clamp(1.5rem,4vw,2.75rem)] text-[clamp(1rem,3vw,2.25rem)] text-[#d9d9d9] tracking-[-0.02rem] sm:tracking-[-0.045rem] mt-1 sm:mt-2"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.5 }}
                >
                  AI that Understands Your PDFs
                </motion.p>
              </div>
            </motion.div>

            {/* Main Card */}
            <motion.div
              className="bg-black border border-[rgba(255,255,255,0.32)] border-solid flex flex-col items-start overflow-hidden relative rounded-lg sm:rounded-xl w-full max-w-[50rem]"
              initial={{ y: 30, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.4 }}
            >
              <div className="bg-gradient-to-b from-[rgba(255,255,255,0.12)] via-[rgba(255,255,255,0.04)] to-[rgba(255,255,255,0.07)] flex flex-col gap-6 sm:gap-8 md:gap-10 items-start pb-4 sm:pb-5 md:pb-6 pt-3 sm:pt-4 px-4 sm:px-5 md:px-6 w-full">

                {/* Tab Switcher */}
                <div className="flex items-center gap-1 sm:gap-2 bg-[#1a1a1a] border border-[#333333] rounded-full p-1 sm:p-1.5 w-max mb-2">
                  <button
                    onClick={() => setActiveTab('monolingual')}
                    className={`flex items-center gap-2 px-4 py-2 sm:px-5 sm:py-2.5 rounded-full text-xs sm:text-sm font-medium transition-all duration-200 ${
                      activeTab === 'monolingual'
                        ? 'bg-[#2a2a2a] text-white border border-[#444444] shadow-sm'
                        : 'text-[#888888] hover:text-[#cccccc] border border-transparent'
                    }`}
                  >
                    <IoDocument className="w-4 h-4 sm:w-4 sm:h-4" />
                    PDF Translator
                  </button>
                  <button
                    onClick={() => setActiveTab('bilingual')}
                    className={`flex items-center gap-2 px-4 py-2 sm:px-5 sm:py-2.5 rounded-full text-xs sm:text-sm font-medium transition-all duration-200 ${
                      activeTab === 'bilingual'
                        ? 'bg-[#2a2a2a] text-white border border-[#444444] shadow-sm'
                        : 'text-[#888888] hover:text-[#cccccc] border border-transparent'
                    }`}
                  >
                    <IoDocument className="w-4 h-4 sm:w-4 sm:h-4" />
                    Bilingual Translator
                  </button>
                </div>

                {/* Upload Section exact matching PDFTranslatorTab */}
                <div className="flex flex-col gap-4 sm:gap-5 items-start w-full">
                  {/* Heading */}
                  <motion.div className="flex flex-col items-start w-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
                    <div className="flex flex-nowrap items-center gap-2 sm:gap-3 whitespace-nowrap">
                      <p className="text-base sm:text-lg md:text-xl font-bold text-white">Upload</p>
                      <div className="w-5 h-5 sm:w-6 sm:h-6">
                        <img src="/Images/pdf-icon.png" alt="PDF Icon" className="w-full h-full object-contain" />
                      </div>
                      <p className="text-base sm:text-lg md:text-xl font-bold text-white">PDF and</p>
                      <p className="text-base sm:text-lg md:text-xl font-bold text-white">Translate</p>
                      <div className="w-5 h-5 sm:w-6 sm:h-6">
                        <img src="/Images/codingicon.png" alt="Translate Icon" className="w-full h-full object-contain" />
                      </div>
                      <p className="text-base sm:text-lg md:text-xl font-bold text-white">full PDF instantly.</p>
                    </div>
                  </motion.div>

                  {/* Error Message */}
                  {error && (
                    <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="w-full bg-red-500/10 border border-red-500/20 rounded-lg p-3 text-red-400 text-sm flex items-center justify-between">
                      <span>{error}</span>
                    </motion.div>
                  )}

                  <div className="flex flex-col gap-4 sm:gap-5 md:gap-6 items-start w-full">
                    {/* Language Dropdown */}
                    <div className="relative w-full" ref={dropdownRef}>
                      <motion.button onClick={() => setIsDropdownOpen(!isDropdownOpen)} whileTap={{ scale: 0.99 }} className="cursor-pointer flex flex-col items-start w-full">
                        <div className="bg-[#2e2e2e] border border-[#4a4a4a] border-solid flex gap-2 items-center overflow-hidden px-3 sm:px-[0.875rem] py-2.5 sm:py-[0.625rem] rounded-lg shadow-[0_0.0625rem_0.125rem_0_rgba(10,13,18,0.05)] w-full transition-all duration-200 hover:border-[#5a5a5a]">
                          <div className="flex flex-1 items-center min-h-0 min-w-0">
                            <p className={`font-normal leading-5 text-xs sm:text-sm text-left ${selectedLanguage ? 'text-white' : 'text-[#d9d9d9]'}`}>{selectedLangName}</p>
                          </div>
                          <div className="flex items-center">
                            <IoChevronDown className={`w-4 h-4 sm:w-5 sm:h-5 text-[#d9d9d9] transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
                          </div>
                        </div>
                      </motion.button>
                      <AnimatePresence>
                        {isDropdownOpen && (
                          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="absolute z-50 mt-2 w-full bg-[#2e2e2e] border border-[#4a4a4a] rounded-lg shadow-lg max-h-60 overflow-y-auto">
                            {languages.map((language) => (
                              <button key={language.code} onClick={() => { setSelectedLanguage(language.code); setIsDropdownOpen(false); }} className={`cursor-pointer w-full text-left px-3 sm:px-[0.875rem] py-2.5 sm:py-[0.625rem] text-xs sm:text-sm transition-colors ${selectedLanguage === language.code ? 'bg-[#4a4a4a] text-white' : 'text-[#d9d9d9] hover:bg-[#3a3a3a]'}`}>
                                {language.name}
                              </button>
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>

                    {/* File Upload Area */}
                    <div className="w-full flex flex-col gap-2">
                      <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleFileChange} className="hidden" />
                      <motion.div onClick={() => fileInputRef.current?.click()} onDrop={handleDrop} onDragOver={(e) => e.preventDefault()} whileTap={{ scale: 0.99 }} className="cursor-pointer w-full">
                        <div className="bg-[#2a2a2a] border border-[#4a4a4a] border-dashed flex flex-col gap-2 items-center p-4 sm:p-6 rounded-lg sm:rounded-xl w-full transition-all duration-200 hover:border-[#5a5a5a] hover:bg-[#2f2f2f]">
                          <div className="h-10 w-10 sm:h-[2.625rem] sm:w-[2.5rem] shrink-0">
                            <img src="/Images/translate-icon.png" alt="Upload" className="w-full h-full object-contain" />
                          </div>
                          <div className="flex flex-col items-center w-full gap-1.5">
                            <div className="flex flex-col sm:flex-row items-center gap-1 sm:gap-1.5">
                              <p className="text-xs sm:text-sm font-semibold text-[#d9d9d9]">Click to upload</p>
                              <p className="text-xs sm:text-sm font-normal text-[#d9d9d9]">or drag and drop</p>
                            </div>
                            <p className="text-xs sm:text-sm font-normal text-[#d9d9d9]">Limit 500MB per file</p>
                          </div>
                        </div>
                      </motion.div>

                      {/* File Display */}
                      <AnimatePresence>
                        {uploadedFile && (
                          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="bg-[#2a2a2a] border border-[#4a4a4a] flex gap-2.5 items-center p-2.5 rounded-lg w-full mt-2">
                            <div className="bg-[#f53e3b] rounded-md shrink-0 w-10 h-10 flex items-center justify-center">
                              <IoDocument className="w-5 h-5 text-white" />
                            </div>
                            <div className="flex flex-col flex-1 min-w-0">
                              <p className="font-medium text-xs sm:text-sm text-white truncate w-full">{uploadedFile.name}</p>
                              <p className="font-normal text-xs sm:text-sm text-[#d9d9d9]">PDF • {(uploadedFile.size / 1024 / 1024).toFixed(2)} MB</p>
                            </div>
                            <motion.button onClick={(e) => { e.stopPropagation(); handleRemoveFile() }} whileTap={{ scale: 0.9 }} className="cursor-pointer p-1.5 hover:bg-white/10 rounded-full">
                              <IoClose className="w-5 h-5 text-white/60 hover:text-white" />
                            </motion.button>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>

                    {/* Generate Button */}
                    <button onClick={handleGenerate} disabled={!uploadedFile || !selectedLanguage} className={`w-full py-3.5 rounded-xl font-semibold text-sm tracking-wide transition-all duration-300 ${uploadedFile && selectedLanguage ? 'cursor-pointer bg-gradient-to-r from-violet-600 to-blue-600 text-white shadow-lg shadow-violet-500/25 hover:brightness-110' : 'bg-[#3a3a3a] text-[#888888] cursor-not-allowed'}`}>
                      Generate
                    </button>
                  </div>
                </div>

              </div>
            </motion.div>
          </div>
        </div>
      </motion.main>
    </div>
  )
}

export default Dashboard
