# Image Handling Flow Analysis & Issues

## Current Image Processing Pipeline

### Flow Overview:
```
PDF Page → Render (200 DPI) → GLM-OCR Extraction → YOLO Detection → Translation → Reconstruction → Cropping → Final HTML
```

### Detailed Flow:

1. **PDF Rendering** (`pdf_service.py`)
   - Renders each page at 200 DPI to PNG bytes
   - Higher DPI = better OCR quality but larger file size

2. **GLM-OCR Extraction** (`glm_ocr_service.py`)
   - Extracts markdown with image placeholders: `![image](crop:[ymin, xmin, ymax, xmax])`
   - Coordinates are normalized 0-1000 scale
   - **Issue**: GLM-OCR bounding boxes are sometimes imprecise (too tight or too loose)

3. **YOLO Figure Detection** (`layout_detection_service.py`)
   - Runs DocLayout-YOLO to detect figures with precise bounding boxes
   - Only detects "figure" class (charts, diagrams, images)
   - Confidence threshold: 0.25
   - **Purpose**: Provide more accurate bounding boxes than GLM-OCR

4. **Translation** (`translation_service.py`)
   - Translates markdown while preserving crop tags
   - Skips LaTeX math and image references

5. **Reconstruction** (`reconstruction_service.py`)
   - Gemini converts translated markdown to HTML
   - Converts crop tags to `<img src="crop:[coords]">` tags
   - **Issue**: Sometimes Gemini drops crop tags or doesn't convert them properly

6. **Image Cropping** (`reconstruction_service.py` - `process_crops()`)
   - Finds all crop coordinates in HTML
   - Matches GLM-OCR coords with YOLO detections (IoU threshold: 0.3)
   - Crops from original page image
   - Applies padding (15 units on 0-1000 scale)
   - Smart trim: removes excess whitespace
   - Converts to base64 data URI
   - **Issues**: 
     - Coordinate validation sometimes fails
     - Padding may be insufficient for some images
     - Smart trim may be too aggressive

---

## Identified Issues

### Issue 1: Images Missing in Final Viewer
**Root Causes:**
- Gemini sometimes drops crop tags during reconstruction
- Regex pattern in `process_crops()` may not match all coordinate formats
- Broken image sources get replaced with 1x1 transparent pixel

**Evidence in Code:**
```python
# reconstruction_service.py line 195-200
crop_hits_html = crop_debug_pattern.findall(html_content)
md_img_hits = md_img_pattern.findall(html_content)
logger.info(
    f"Page {page_number}: Gemini output has {len(crop_hits_html)} crop refs, "
    f"{len(md_img_hits)} unconverted markdown image tags"
)
```

### Issue 2: Poor Bounding Boxes
**Root Causes:**
- GLM-OCR bounding boxes are sometimes inaccurate
- YOLO matching threshold (IoU 0.3) may be too strict
- Padding (15 units) may not be optimal for all image types
- Coordinate validation may reject valid boxes

**Evidence in Code:**
```python
# reconstruction_service.py line 265-275
# YOLO matching with IoU threshold
yolo_match = find_best_yolo_match(glm_coords, yolo_figures)
if yolo_match:
    # Uses YOLO coords
else:
    # Falls back to GLM-OCR coords (may be imprecise)
```

---

## Proposed Fixes

### Fix 1: Improve Crop Tag Preservation
**Problem**: Gemini drops or doesn't convert crop tags properly
**Solution**: Add post-processing to recover lost crop tags

### Fix 2: Adaptive Bounding Box Strategy
**Problem**: Fixed IoU threshold and padding don't work for all images
**Solution**: 
- Lower IoU threshold to 0.2 (more lenient matching)
- Adaptive padding based on image size
- Better coordinate validation

### Fix 3: Enhanced Coordinate Extraction
**Problem**: Regex may miss some coordinate formats
**Solution**: More robust regex pattern with better error handling

### Fix 4: Fallback Image Rendering
**Problem**: When cropping fails, images are lost
**Solution**: If crop fails, render the entire region with extra padding

### Fix 5: Better Logging & Debugging
**Problem**: Hard to diagnose why images are missing
**Solution**: Add detailed logging at each stage
