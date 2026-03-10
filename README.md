# GLM-OCR Bilingual PDF Translation Engine

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![React](https://img.shields.io/badge/react-18-blue)

An advanced, end-to-end PDF Translation Pipeline designed specifically to process visually complex PDFs (including mathematical formulas, charts, embedded images, and non-selectable scanned text). It accurately reconstructs the exact original structural layout in a **Bilingual format** (English + localized Indian languages like Telugu, Hindi, Tamil, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, Urdu) without corrupting mathematical equations.

## ✨ Core Features
The pipeline functions via a highly-optimized Multi-Stage Architecture:

1. **GLM-OCR Intelligent Extraction**: 
   - Runs `zai-org/GLM-OCR` model **locally** (default) or via remote API
   - Extracts text, detects spatial layout coordinates, captures nested tables
   - Intelligently parses visual mathematics into pure LaTeX equations
   - Outputs Markdown with embedded crop coordinates for images/charts

2. **DocLayout-YOLO Figure Detection**:
   - Detects figure/image regions with precise bounding boxes
   - Provides higher accuracy than GLM-OCR coordinates alone
   - Automatically matches and upgrades crop coordinates via IoU matching
   - Falls back gracefully to GLM-OCR coordinates if YOLO unavailable

3. **Gemini Bilingual Markdown Translation**: 
   - Uses Google's `gemini-2.0-flash` for fast, accurate translation
   - Generates a **Bilingual** output, keeping the original English text alongside the translated regional language
   - Custom prompts preserve LaTeX math, numbers, option labels, and image tags
   - Language-specific formal vocabulary (government exam paper style)
   - Skips institute logos, headers, and non-content elements

4. **Gemini Multimodal Layout Reconstruction**:
   - Sends original page image + translated Markdown to Gemini
   - Reconstructs HTML matching original visual layout (columns, spacing, positioning)
   - Converts crop coordinates to base64-embedded images with smart padding
   - Handles tables, MCQ options, math expressions, and complex layouts
   - Post-processes fractions, superscripts, and removes unwanted separators

5. **Real-Time Streaming & Export**:
   - Server-Sent Events (SSE) for live page-by-page progress
   - Split-view interface: original PDF vs bilingual translated content side-by-side
   - MathJax 3 renders LaTeX as **SVG** (scalable, crisp math rendering)
   - Export to PDF via Playwright (Chromium headless rendering)
   - Export to DOCX via pdf2docx (PDF→DOCX conversion preserves layout)

## 🏗 System Architecture
This is a monorepo containing everything you need to run the full application:

### Backend (`/backend/`)
**FastAPI + Async Uvicorn Python Engine**
- **Services**:
  - `glm_ocr_local_service.py`: Local GLM-OCR inference via Transformers (default)
  - `glm_ocr_service.py`: Remote GLM-OCR API client (fallback)
  - `layout_detection_service.py`: DocLayout-YOLO figure detection
  - `translation_service.py`: Gemini-based Markdown translation
  - `reconstruction_service.py`: Gemini multimodal layout reconstruction
  - `pdf_service.py`: PyMuPDF page rendering with sharpening/contrast enhancement
  - `download_service.py`: Playwright PDF generation + pdf2docx conversion
  - `pipeline.py`: Orchestrates full OCR→Translate→Reconstruct flow
- **Routers**: SSE streaming (`/api/translate/stream`), upload, download, health checks
- **Models**: Pydantic schemas, enums, job status tracking
- **Storage**: In-memory job store (resets on server restart)

### Frontend (`/frontend/`)
**React 18 + Vite + Tailwind CSS + Framer Motion**
- **Pages**:
  - `PdfTranslator.jsx`: Upload interface with language selection
  - `PageViewer.jsx`: Split-view real-time streaming viewer
  - `OcrTest.jsx`: Standalone OCR API testing tool
- **Features**:
  - Real-time SSE event handling for page-by-page progress
  - Animated page transitions with Framer Motion
  - MathJax 3 integration for LaTeX rendering (SVG output)
  - Split/Original/Translated view modes
  - Page thumbnail strip with status indicators
  - Google Fonts for 11 Indian language scripts + custom Gautami font

## ⚙️ Quick Start & Installation

### Requirements
* **Python 3.10+** (Optimized for Apple Silicon M1-M4, also supports CUDA/CPU)
* **Node.js v18+** & npm
* **Google Gemini API Key** (required)
* **8GB+ RAM** (for local GLM-OCR model)
* **Playwright** (auto-installs Chromium for PDF generation)

### Installation

#### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium  # Install Chromium for PDF export
```

#### 2. Configure Environment
Create `backend/.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GLM_USE_LOCAL=True
GLM_LOCAL_MODEL_PATH=zai-org/GLM-OCR
GEMINI_MODEL=gemini-2.0-flash
RENDER_DPI=200
CROP_PADDING=15
CROP_SMART_PADDING=True
YOLO_IOU_THRESHOLD=0.2
```

**First-time model download** (optional, happens automatically on first run):
```bash
python setup_env.py  # Pre-downloads GLM-OCR + DocLayout-YOLO models
```

#### 3. Frontend Setup
```bash
cd frontend
npm install
```

### Running the System

**Terminal 1 (Backend):**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```

Open browser: `http://localhost:5173` (Vite default port)

## 🧠 Technologies & Dependencies

### Backend Stack
- **GLM-OCR**: `zai-org/GLM-OCR` (HuggingFace Transformers)
- **DocLayout-YOLO**: `doclayout-yolo==0.0.4` (figure detection)
- **Google Gemini**: `google-genai==1.5.0` (translation + reconstruction)
- **FastAPI**: `fastapi==0.115.6` + `uvicorn==0.34.0`
- **PDF Processing**: `PyMuPDF==1.27.1` (fitz)
- **Image Processing**: `Pillow==11.1.0`
- **PDF Export**: `playwright==1.58.0` (Chromium rendering)
- **DOCX Export**: `pdf2docx==0.5.10`
- **Streaming**: `sse-starlette==2.2.1`
- **ML Framework**: `torch` (CPU/CUDA/MPS support)

### Frontend Stack
- **React**: `react==18.3.1` + `react-dom==18.3.1`
- **Build Tool**: `vite==7.3.1`
- **Styling**: `tailwindcss==4.1.17` + `@tailwindcss/vite`
- **Animations**: `framer-motion==12.23.25`
- **Math Rendering**: MathJax 3 (CDN, SVG output)
- **Icons**: `react-icons==5.5.0`
- **Routing**: `react-router-dom==6.30.2`
- **HTTP Client**: `axios==1.13.2`
- **Fonts**: Google Fonts (Noto Sans family for 11 Indian scripts)

## 📊 How Math Equations Are Rendered

### Pipeline Flow:
1. **GLM-OCR Extraction**: Visual math → LaTeX format (e.g., `$\frac{2}{5}$`, `$x^2 + y^2 = z^2$`)
2. **Translation**: Gemini preserves LaTeX blocks unchanged (skips translation)
3. **Reconstruction**: Gemini embeds LaTeX in HTML output
4. **Frontend Rendering**: MathJax 3 converts LaTeX → **SVG** (not HTML/CSS)
5. **PDF Export**: Playwright renders MathJax SVG → embedded in final PDF

### Math Rendering Format: **SVG**
- MathJax 3 uses `tex-mml-svg.js` renderer
- Output: Scalable Vector Graphics (crisp at any zoom level)
- Inline math: `$...$` renders inline with text
- Display math: `$$...$$` renders centered on new line
- SVG elements are embedded directly in HTML DOM

### Why SVG?
- **Scalable**: No pixelation when zooming
- **Print-ready**: Perfect for PDF export
- **Accessible**: Can be styled with CSS
- **Fast**: Client-side rendering, no server calls

## 🎯 Supported Languages
11 Indian regional languages with formal government exam paper vocabulary:
- **Telugu** (తెలుగు) - Gautami + Noto Sans Telugu
- **Hindi** (हिन्दी) - Noto Sans Devanagari
- **Tamil** (தமிழ்) - Noto Sans Tamil
- **Kannada** (ಕನ್ನಡ) - Noto Sans Kannada
- **Malayalam** (മലയാളം) - Noto Sans Malayalam
- **Bengali** (বাংলা) - Noto Sans Bengali
- **Marathi** (मराठी) - Noto Sans Devanagari
- **Gujarati** (ગુજરાતી) - Noto Sans Gujarati
- **Punjabi** (ਪੰਜਾਬੀ) - Noto Sans Gurmukhi
- **Odia** (ଓଡ଼ିଆ) - Noto Sans Oriya
- **Urdu** (اردو) - Noto Nastaliq Urdu

## 🔧 Configuration Options

Key settings in `backend/.env`:

```env
# GLM-OCR Mode
GLM_USE_LOCAL=True              # True=local model, False=remote API
GLM_LOCAL_MODEL_PATH=zai-org/GLM-OCR
GLM_LOCAL_MAX_TOKENS=8192

# Rendering Quality
RENDER_DPI=200                  # PDF→PNG resolution (higher=better OCR)
OCR_MAX_IMAGE_DIM=1200          # Max dimension for remote API

# Image Cropping
CROP_PADDING=15                 # Base padding around crops (0-1000 scale)
CROP_SMART_PADDING=True         # Enable intelligent whitespace trimming
YOLO_IOU_THRESHOLD=0.2          # IoU threshold for YOLO/GLM matching

# Gemini
GEMINI_MODEL=gemini-2.0-flash
GEMINI_MAX_OUTPUT_TOKENS=16384
```

## 📁 Project Structure
```
GLM-5/
├── backend/
│   ├── app/
│   │   ├── core/           # Exceptions
│   │   ├── models/         # Pydantic schemas, enums
│   │   ├── routers/        # API endpoints (translate, health, languages)
│   │   ├── services/       # Core pipeline logic
│   │   ├── utils/          # File utilities
│   │   ├── config.py       # Settings management
│   │   └── main.py         # FastAPI app
│   ├── static/fonts/       # Custom fonts (Gautami)
│   ├── uploads/            # Temporary PDF storage
│   ├── outputs/            # Generated files
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard/  # PdfTranslator, PageViewer
│   │   │   └── OcrTest/    # OCR testing tool
│   │   ├── services/       # API client (axios)
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── public/Images/      # UI assets
│   ├── index.html          # MathJax + Google Fonts
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## 🚀 API Endpoints

- `POST /api/translate/upload` - Upload PDF + start job
- `POST /api/translate/start/{job_id}` - Register pipeline
- `GET /api/translate/stream/{job_id}` - SSE event stream
- `GET /api/translate/status/{job_id}` - Job status (JSON)
- `GET /api/translate/download/pdf/{job_id}` - Download translated PDF
- `GET /api/translate/download/docx/{job_id}` - Download translated DOCX
- `GET /api/languages` - List supported languages
- `GET /api/health` - Health check

## ⚠️ Known Limitations

1. **Job Storage**: In-memory only (resets on server restart). Use Redis for production.
2. **Concurrent Jobs**: Single-threaded pipeline. Add task queue (Celery) for scaling.
3. **Model Size**: GLM-OCR requires ~8GB RAM. Use remote API for low-memory systems.
4. **DOCX Fidelity**: Complex layouts may not convert perfectly (PDF is more reliable).
5. **MPS on Apple Silicon**: Model runs on CPU to avoid Metal memory issues (still fast).
