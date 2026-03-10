# Image Handling Fixes - Implementation Summary

## Issues Identified

### 1. Images Missing in Final Viewer
- **Cause**: Gemini sometimes drops crop tags during HTML reconstruction
- **Impact**: Images present in OCR output don't appear in final translated document

### 2. Poor Bounding Boxes
- **Cause**: 
  - GLM-OCR bounding boxes sometimes imprecise
  - Fixed IoU threshold too strict (0.3)
  - Fixed padding doesn't work for all image sizes
  - Smart trim too aggressive (threshold 245, margin 5px)
- **Impact**: Images cropped too tightly or with excess whitespace

---

## Fixes Implemented

### Fix 1: Enhanced Coordinate Extraction Regex
**File**: `backend/app/services/reconstruction_service.py`

**Change**: Improved regex pattern to handle more coordinate formats
```python
# Before: Basic pattern
pattern = re.compile(r'(?:crop:\s*(?:\[)?|\[)\s*...')

# After: Enhanced with IGNORECASE flag and better matching
pattern = re.compile(
    r'(?:crop:\s*(?:\[)?|(?<=src=["\''])\[)\s*'
    r'(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)\s*'
    r'(?:\])?',
    re.IGNORECASE
)
```

**Benefit**: Catches more coordinate format variations, reducing lost images

---

### Fix 2: Adaptive Padding Strategy
**File**: `backend/app/services/reconstruction_service.py`

**Change**: Dynamic padding based on image size instead of fixed 15 units
```python
# Calculate box area
box_area = (xmax - xmin) * (ymax - ymin)

# Adaptive padding
if box_area < 50000:      # Small image
    padding = 12
elif box_area < 200000:   # Medium image
    padding = 18
else:                     # Large image
    padding = 25
```

**Benefit**: 
- Small images get less padding (avoid including unwanted content)
- Large images get more padding (avoid cutting edges)

---

### Fix 3: More Lenient YOLO Matching
**File**: `backend/app/services/reconstruction_service.py`

**Change**: Lowered IoU threshold from 0.3 to 0.2
```python
# Before
yolo_match = find_best_yolo_match(glm_coords, yolo_figures)

# After
yolo_match = find_best_yolo_match(glm_coords, yolo_figures, iou_threshold=0.2)
```

**Benefit**: More GLM-OCR crops get upgraded to precise YOLO coordinates

---

### Fix 4: Improved Minimum Size Handling
**File**: `backend/app/services/reconstruction_service.py`

**Change**: Instead of skipping tiny crops, expand them to minimum viable size
```python
# Before: Skip if too small
if (real_xmax - real_xmin) < 10 or (real_ymax - real_ymin) < 10:
    return match.group(0)  # Skip

# After: Expand to minimum 30x30 pixels
if (real_xmax - real_xmin) < 20 or (real_ymax - real_ymin) < 20:
    center_x = (real_xmin + real_xmax) // 2
    center_y = (real_ymin + real_ymax) // 2
    real_xmin = max(0, center_x - 15)
    real_xmax = min(w, center_x + 15)
    real_ymin = max(0, center_y - 15)
    real_ymax = min(h, center_y + 15)
```

**Benefit**: Preserves small icons/symbols instead of losing them

---

### Fix 5: Robust Error Handling with Fallback
**File**: `backend/app/services/reconstruction_service.py`

**Change**: Added try-catch with fallback cropping strategy
```python
try:
    cropped = full_img.crop((real_xmin, real_ymin, real_xmax, real_ymax))
    # ... process normally
except Exception as crop_error:
    # Fallback: try with extra padding
    fallback_padding = 50
    fb_ymin = max(0, real_ymin - fallback_padding)
    # ... expand bounds and retry
```

**Benefit**: Images that would fail now have a second chance with expanded bounds

---

### Fix 6: Less Aggressive Smart Trim
**File**: `backend/app/services/reconstruction_service.py`

**Changes**:
- Threshold: 245 → 240 (less aggressive)
- Margin: 5px → 8px (more border preserved)
- Trim threshold: 10% → 15% (only trim significant whitespace)
- Only apply to images >100x100px

```python
# Before
threshold = 245
margin = 5
if trim_percent > 10:

# After
threshold = 240
margin = 8
if trim_percent > 15:
```

**Benefit**: Preserves more border content, reduces risk of cutting image edges

---

### Fix 7: Crop Tag Recovery Mechanism
**File**: `backend/app/services/reconstruction_service.py`

**Change**: Added post-reconstruction recovery for lost crop tags
```python
# Count expected vs actual crop tags
expected_crops = len(re.findall(r'crop:', translated_markdown))
actual_crops = len(crop_hits_html) + len(md_img_hits)

# If tags were lost, recover them
if expected_crops > actual_crops:
    original_crops = re.findall(r'!\[([^\]]*)\]\((crop:\s*\[?[\d\s,]+\]?)\)', translated_markdown)
    for alt_text, crop_coords in original_crops:
        if crop_coords not in html_content:
            # Append recovered image at end
            recovery_img = f'<div>...<img src="{crop_coords}">...</div>'
            html_content += recovery_img
```

**Benefit**: Images dropped by Gemini are recovered and appended to the page

---

### Fix 8: Enhanced Reconstruction Prompt
**File**: `backend/app/services/reconstruction_service.py`

**Change**: Added explicit instruction to preserve all crop tags
```
Rule 6: If you're unsure whether something is a table or image, 
default to <img> to preserve the visual content.
```

**Benefit**: Gemini less likely to drop ambiguous crop tags

---

### Fix 9: Configuration Updates
**File**: `backend/app/config.py`

**Change**: Added new configuration parameter
```python
YOLO_IOU_THRESHOLD: float = 0.2  # IoU threshold for YOLO matching
```

**Benefit**: Makes IoU threshold configurable via environment variables

---

## Testing Recommendations

### Test Case 1: Small Icons/Logos
- Upload PDF with small icons (barcodes, logos)
- Verify icons appear in final output
- Check bounding boxes aren't too large

### Test Case 2: Large Charts/Graphs
- Upload PDF with full-width charts
- Verify chart edges aren't cut off
- Check no excess whitespace around charts

### Test Case 3: Mixed Content Pages
- Upload PDF with text + multiple images
- Verify all images appear in correct positions
- Check no images are missing

### Test Case 4: Edge Cases
- Upload PDF with very small images (<20x20px)
- Upload PDF with images near page edges
- Verify fallback mechanism works

---

## Monitoring & Debugging

### Key Log Messages to Watch

1. **Crop tag tracking**:
   ```
   "Page X: Gemini output has Y crop refs, Z unconverted markdown image tags (expected: W)"
   ```
   If W > Y+Z, recovery mechanism activates

2. **YOLO matching**:
   ```
   "Page X: YOLO precision upgrade — GLM [...] → YOLO [...] (conf=0.XX)"
   ```
   Shows when YOLO improves bounding boxes

3. **Adaptive padding**:
   ```
   "Page X: Using adaptive padding=Y for box area=Z"
   ```
   Shows padding adjustment based on image size

4. **Fallback activation**:
   ```
   "Page X: Crop failed for region [...]. Attempting fallback with expanded bounds."
   ```
   Indicates primary crop failed, fallback engaged

5. **Recovery mechanism**:
   ```
   "Page X: N crop tag(s) lost during reconstruction. Attempting recovery..."
   ```
   Shows when Gemini dropped tags and recovery is running

---

## Performance Impact

- **Minimal**: All fixes are optimizations of existing logic
- **No new API calls**: Recovery happens in post-processing
- **Slightly more logging**: ~5-10 extra log lines per page
- **Memory**: Negligible increase (storing crop tag lists)

---

## Rollback Plan

If issues arise, revert these files:
1. `backend/app/services/reconstruction_service.py`
2. `backend/app/config.py`

Original behavior:
- Fixed padding (15 units)
- IoU threshold 0.3
- No recovery mechanism
- Skip tiny crops
- More aggressive smart trim

---

## Future Enhancements

### Potential Improvements:
1. **Machine learning-based padding**: Train model to predict optimal padding per image type
2. **Confidence-based recovery**: Only recover high-confidence lost crops
3. **Visual validation**: Compare cropped region with YOLO detection visually
4. **User feedback loop**: Allow users to report bad crops, improve algorithm
5. **Crop cache**: Cache successful crops to avoid reprocessing on retries

### Configuration Tuning:
Users can now adjust via `.env`:
```bash
CROP_PADDING=15              # Base padding (now adaptive)
CROP_SMART_PADDING=true      # Enable smart trim
YOLO_IOU_THRESHOLD=0.2       # YOLO matching threshold
```

---

## Summary

**Total Changes**: 9 fixes across 2 files
**Lines Modified**: ~150 lines
**New Features**: 
- Adaptive padding
- Crop tag recovery
- Fallback cropping
- Enhanced error handling

**Expected Improvements**:
- ✅ Fewer missing images (recovery mechanism)
- ✅ Better bounding boxes (adaptive padding + lenient YOLO matching)
- ✅ More robust cropping (fallback strategy)
- ✅ Better edge preservation (less aggressive trim)
