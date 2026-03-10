# Image Handling Flow - Visual Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PDF TRANSLATION PIPELINE                             │
│                         (Image Handling Focus)                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐
│  PDF Upload  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: PDF Rendering (pdf_service.py)                                 │
│  ─────────────────────────────────────────────────────────────────────   │
│  • Render each page at 200 DPI                                           │
│  • Output: PNG bytes (high quality for OCR)                              │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 2A: GLM-OCR Extraction (glm_ocr_service.py)                       │
│  ─────────────────────────────────────────────────────────────────────   │
│  • Extract text + layout                                                 │
│  • Detect images and create crop tags:                                   │
│    ![image](crop:[ymin, xmin, ymax, xmax])                              │
│  • Coordinates: 0-1000 normalized scale                                  │
│  ⚠️  ISSUE: Bounding boxes sometimes imprecise                           │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ├─────────────────────────────────────────────────────────────────┐
       │                                                                  │
       ▼                                                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 2B: YOLO Detection (layout_detection_service.py)                  │
│  ─────────────────────────────────────────────────────────────────────   │
│  • Run DocLayout-YOLO on page image                                      │
│  • Detect ONLY "figure" class (charts, diagrams, images)                 │
│  • Output: Precise bounding boxes with confidence scores                 │
│  • Coordinates: Same 0-1000 scale as GLM-OCR                             │
│  ✅ FIX: More accurate than GLM-OCR for visual elements                  │
└──────────────────────────────────────────────────────────────────────────┘
       │
       │ (Both outputs merge)
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: Translation (translation_service.py)                            │
│  ─────────────────────────────────────────────────────────────────────   │
│  • Translate markdown to target language                                 │
│  • PRESERVE crop tags unchanged                                          │
│  • Skip LaTeX math and image references                                  │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: Reconstruction (reconstruction_service.py)                      │
│  ─────────────────────────────────────────────────────────────────────   │
│  • Send to Gemini: page image + translated markdown + layout             │
│  • Gemini converts markdown → HTML                                        │
│  • Converts crop tags: ![image](crop:[...]) → <img src="crop:[...]">    │
│  ⚠️  ISSUE: Gemini sometimes drops crop tags                             │
│  ✅ FIX: Recovery mechanism detects and restores lost tags               │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 5: Crop Tag Recovery (NEW)                                        │
│  ─────────────────────────────────────────────────────────────────────   │
│  • Count expected vs actual crop tags                                    │
│  • If mismatch detected:                                                 │
│    - Extract missing crop tags from original markdown                    │
│    - Append recovered images to HTML                                     │
│  ✅ FIX: Prevents image loss from Gemini reconstruction                  │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 6: Image Cropping (reconstruction_service.py - process_crops())   │
│  ─────────────────────────────────────────────────────────────────────   │
│  Step 1: Find all crop:[...] coordinates in HTML                         │
│  Step 2: For each crop coordinate:                                       │
│    ┌────────────────────────────────────────────────────────────────┐   │
│    │ 2a. Match with YOLO detection (IoU threshold: 0.2)             │   │
│    │     ✅ FIX: Lowered from 0.3 for more matches                  │   │
│    │     If match found → use YOLO coords (more precise)            │   │
│    │     If no match → use GLM-OCR coords                           │   │
│    └────────────────────────────────────────────────────────────────┘   │
│    ┌────────────────────────────────────────────────────────────────┐   │
│    │ 2b. Calculate adaptive padding based on image size             │   │
│    │     ✅ FIX: Dynamic padding instead of fixed 15 units          │   │
│    │     Small (<50k): 12 units                                     │   │
│    │     Medium (<200k): 18 units                                   │   │
│    │     Large (>200k): 25 units                                    │   │
│    └────────────────────────────────────────────────────────────────┘   │
│    ┌────────────────────────────────────────────────────────────────┐   │
│    │ 2c. Validate and fix coordinates                               │   │
│    │     • Check for inverted coords (swap if needed)               │   │
│    │     • Ensure minimum size (20x20px)                            │   │
│    │     ✅ FIX: Expand tiny crops instead of skipping              │   │
│    └────────────────────────────────────────────────────────────────┘   │
│    ┌────────────────────────────────────────────────────────────────┐   │
│    │ 2d. Crop from original page image                              │   │
│    │     TRY:                                                        │   │
│    │       • Crop with calculated bounds                            │   │
│    │       • Apply smart trim (if image >100x100px)                 │   │
│    │         ✅ FIX: Less aggressive (threshold 240, margin 8px)    │   │
│    │       • Convert to PNG base64                                  │   │
│    │     CATCH (if crop fails):                                     │   │
│    │       ✅ FIX: Fallback with +50px padding                      │   │
│    │       • Retry crop with expanded bounds                        │   │
│    │       • If still fails, keep original crop tag                 │   │
│    └────────────────────────────────────────────────────────────────┘   │
│  Step 3: Replace crop:[...] with data:image/png;base64,...              │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STAGE 7: Final HTML Output                                              │
│  ─────────────────────────────────────────────────────────────────────   │
│  • HTML with embedded base64 images                                      │
│  • Wrapped in styled container                                           │
│  • Ready for frontend rendering                                          │
└──────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│   Frontend   │
│   Viewer     │
└──────────────┘
```

---

## Key Improvements Summary

### 🔴 BEFORE (Issues):
1. Fixed padding (15 units) → Too tight for large images, too loose for small
2. IoU threshold 0.3 → Many GLM crops didn't match YOLO (missed precision)
3. Skip tiny crops → Lost small icons/symbols
4. No fallback → Crop failures = lost images
5. Aggressive trim (threshold 245) → Cut image edges
6. No recovery → Gemini drops = permanent loss

### 🟢 AFTER (Fixes):
1. ✅ Adaptive padding (12-25 units) → Optimal for each image size
2. ✅ IoU threshold 0.2 → More GLM crops upgraded to YOLO precision
3. ✅ Expand tiny crops → Preserve all images
4. ✅ Fallback cropping → Second chance with +50px padding
5. ✅ Conservative trim (threshold 240) → Preserve edges
6. ✅ Recovery mechanism → Restore Gemini-dropped images

---

## Coordinate System Explained

```
GLM-OCR & YOLO use normalized 0-1000 scale:

  0,0 ─────────────────────────── 1000,0
   │                                 │
   │                                 │
   │         [ymin, xmin]            │
   │              ┌──────────┐       │
   │              │  IMAGE   │       │
   │              └──────────┘       │
   │                [ymax, xmax]     │
   │                                 │
  0,1000 ────────────────────── 1000,1000

Conversion to pixels:
  real_x = (x / 1000.0) * image_width
  real_y = (y / 1000.0) * image_height
```

---

## Adaptive Padding Logic

```
Box Area = (xmax - xmin) × (ymax - ymin)

┌─────────────────┬──────────┬─────────────────────────┐
│   Image Size    │ Padding  │      Use Case           │
├─────────────────┼──────────┼─────────────────────────┤
│ < 50,000        │  12      │ Icons, logos, symbols   │
│ 50k - 200k      │  18      │ Small charts, diagrams  │
│ > 200,000       │  25      │ Large graphs, tables    │
└─────────────────┴──────────┴─────────────────────────┘

Example:
  Small icon: 100×100 = 10,000 → padding 12
  Medium chart: 300×400 = 120,000 → padding 18
  Large graph: 600×800 = 480,000 → padding 25
```

---

## YOLO Matching Process

```
For each GLM-OCR crop tag:

1. Calculate IoU with all YOLO detections
   IoU = Intersection Area / Union Area

2. Find best match (highest IoU)

3. If IoU ≥ 0.2:
     Use YOLO coordinates (more precise)
   Else:
     Use GLM-OCR coordinates (fallback)

Example:
  GLM: [100, 200, 300, 400]
  YOLO: [95, 195, 305, 405]
  IoU: 0.85 → MATCH! Use YOLO coords
```

---

## Smart Trim Algorithm

```
1. Convert image to grayscale
2. Find pixels darker than threshold (240)
3. Calculate bounding box of dark pixels
4. Add 8px margin
5. Calculate trim percentage
6. If trim > 15%:
     Crop to content bounds
   Else:
     Keep original (minimal whitespace)

Only applied to images > 100×100px
```
