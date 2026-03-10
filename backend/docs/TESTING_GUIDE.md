# Testing Guide - Image Handling Fixes

## Quick Test Checklist

Before deploying, verify these scenarios work correctly:

- [ ] Small icons/logos appear without excess whitespace
- [ ] Large charts/graphs aren't cut off at edges
- [ ] All images from OCR appear in final output (no missing images)
- [ ] Images appear in correct positions relative to text
- [ ] Bounding boxes are tight but not too tight
- [ ] Fallback mechanism works when primary crop fails
- [ ] Recovery mechanism restores Gemini-dropped images

---

## Test Scenarios

### Scenario 1: Small Icons & Logos
**Purpose**: Verify adaptive padding works for small images

**Test PDF**: Document with barcodes, small logos, icons

**Expected Behavior**:
- Icons appear clearly without being cut off
- Minimal excess whitespace around icons
- Padding ~12 units (check logs)

**Log to Check**:
```
"Page X: Using adaptive padding=12 for box area=XXXXX"
```

**Pass Criteria**:
- ✅ All icons visible
- ✅ No excessive white borders
- ✅ Icons not cut off

---

### Scenario 2: Large Charts & Graphs
**Purpose**: Verify large images get sufficient padding

**Test PDF**: Document with full-width charts, graphs, diagrams

**Expected Behavior**:
- Chart edges fully visible
- No content cut off at borders
- Padding ~25 units (check logs)

**Log to Check**:
```
"Page X: Using adaptive padding=25 for box area=XXXXX"
```

**Pass Criteria**:
- ✅ All chart content visible
- ✅ Axis labels not cut off
- ✅ Legend fully visible

---

### Scenario 3: Mixed Content Pages
**Purpose**: Verify all images preserved through pipeline

**Test PDF**: Page with text + multiple images of varying sizes

**Expected Behavior**:
- All images appear in final output
- Images in correct positions
- No "Recovered image" labels (means no loss)

**Log to Check**:
```
"Page X: Gemini output has Y crop refs, Z unconverted markdown image tags (expected: W)"
```
Where Y + Z = W (no loss)

**Pass Criteria**:
- ✅ Image count matches OCR output
- ✅ No recovery mechanism triggered
- ✅ Images positioned correctly

---

### Scenario 4: YOLO Precision Upgrade
**Purpose**: Verify YOLO improves bounding boxes

**Test PDF**: Document with figures (charts, diagrams)

**Expected Behavior**:
- YOLO detections match GLM crops
- Coordinates upgraded to YOLO precision
- IoU threshold 0.2 allows more matches

**Log to Check**:
```
"Page X: YOLO precision upgrade — GLM [a,b,c,d] → YOLO [e,f,g,h] (conf=0.XX)"
```

**Pass Criteria**:
- ✅ At least 50% of images get YOLO upgrade
- ✅ YOLO confidence > 0.25
- ✅ Bounding boxes more accurate

---

### Scenario 5: Tiny Image Handling
**Purpose**: Verify tiny crops are expanded, not skipped

**Test PDF**: Document with very small images (<20x20px)

**Expected Behavior**:
- Small images expanded to minimum 30x30px
- Images still visible in output
- No skipped crops

**Log to Check**:
```
"Page X: Crop region too small (WxH), expanding to minimum size"
```

**Pass Criteria**:
- ✅ All tiny images appear
- ✅ Expanded to visible size
- ✅ No crops skipped

---

### Scenario 6: Fallback Mechanism
**Purpose**: Verify fallback works when primary crop fails

**Test PDF**: Document with edge-case images (near page borders, unusual aspect ratios)

**Expected Behavior**:
- Primary crop may fail
- Fallback activates with +50px padding
- Image still appears in output

**Log to Check**:
```
"Page X: Crop failed for region [...]. Attempting fallback with expanded bounds."
"Page X: Fallback crop successful with expanded bounds"
```

**Pass Criteria**:
- ✅ Fallback activates on failure
- ✅ Image recovered with fallback
- ✅ No permanent crop failures

---

### Scenario 7: Recovery Mechanism
**Purpose**: Verify Gemini-dropped images are recovered

**Test PDF**: Complex document where Gemini might drop crop tags

**Expected Behavior**:
- If Gemini drops tags, recovery detects it
- Missing images appended to page
- "Recovered image" label appears

**Log to Check**:
```
"Page X: N crop tag(s) lost during reconstruction. Attempting recovery..."
"Page X: Recovering lost crop tag: crop:[...]"
```

**Pass Criteria**:
- ✅ Recovery mechanism activates when needed
- ✅ Lost images restored
- ✅ All expected images present

---

### Scenario 8: Smart Trim
**Purpose**: Verify smart trim preserves content while removing whitespace

**Test PDF**: Document with images that have whitespace borders

**Expected Behavior**:
- Significant whitespace (>15%) trimmed
- Content edges preserved (8px margin)
- Threshold 240 (less aggressive)

**Log to Check**:
```
"Page X: Smart trim removed XX.X% whitespace"
```
OR
```
"Page X: Minimal whitespace (XX.X%), keeping original"
```

**Pass Criteria**:
- ✅ Excess whitespace removed
- ✅ Image content not cut off
- ✅ Only applied to images >100x100px

---

## Automated Testing Script

Create a test script to verify fixes:

```python
# test_image_handling.py

import re
from pathlib import Path

def test_adaptive_padding(log_file):
    """Verify adaptive padding is being used"""
    with open(log_file) as f:
        logs = f.read()
    
    # Check for adaptive padding logs
    padding_logs = re.findall(r'Using adaptive padding=(\d+) for box area=(\d+)', logs)
    
    for padding, area in padding_logs:
        padding = int(padding)
        area = int(area)
        
        # Verify padding logic
        if area < 50000:
            assert padding == 12, f"Small image should use padding 12, got {padding}"
        elif area < 200000:
            assert padding == 18, f"Medium image should use padding 18, got {padding}"
        else:
            assert padding == 25, f"Large image should use padding 25, got {padding}"
    
    print(f"✅ Adaptive padding test passed ({len(padding_logs)} images)")

def test_yolo_matching(log_file):
    """Verify YOLO matching is working"""
    with open(log_file) as f:
        logs = f.read()
    
    yolo_upgrades = re.findall(r'YOLO precision upgrade', logs)
    total_crops = len(re.findall(r'Cropping region', logs))
    
    if total_crops > 0:
        upgrade_rate = len(yolo_upgrades) / total_crops * 100
        print(f"✅ YOLO upgrade rate: {upgrade_rate:.1f}% ({len(yolo_upgrades)}/{total_crops})")
    else:
        print("⚠️  No crops found in logs")

def test_recovery_mechanism(log_file):
    """Verify recovery mechanism activates when needed"""
    with open(log_file) as f:
        logs = f.read()
    
    recovery_activations = re.findall(r'crop tag\(s\) lost during reconstruction', logs)
    recovered_tags = re.findall(r'Recovering lost crop tag', logs)
    
    print(f"✅ Recovery mechanism: {len(recovery_activations)} activations, {len(recovered_tags)} tags recovered")

def test_fallback_mechanism(log_file):
    """Verify fallback mechanism works"""
    with open(log_file) as f:
        logs = f.read()
    
    fallback_attempts = re.findall(r'Attempting fallback with expanded bounds', logs)
    fallback_successes = re.findall(r'Fallback crop successful', logs)
    
    if fallback_attempts:
        success_rate = len(fallback_successes) / len(fallback_attempts) * 100
        print(f"✅ Fallback mechanism: {len(fallback_attempts)} attempts, {success_rate:.1f}% success rate")
    else:
        print("✅ No fallback needed (all crops succeeded)")

def test_no_missing_images(log_file):
    """Verify no images are missing"""
    with open(log_file) as f:
        logs = f.read()
    
    # Extract expected vs actual crop counts per page
    pages = re.findall(r'Page (\d+): Gemini output has (\d+) crop refs, (\d+) unconverted markdown image tags \(expected: (\d+)\)', logs)
    
    missing_images = []
    for page, crop_refs, md_imgs, expected in pages:
        actual = int(crop_refs) + int(md_imgs)
        expected = int(expected)
        if actual < expected:
            missing_images.append((page, expected - actual))
    
    if missing_images:
        print(f"⚠️  Missing images detected:")
        for page, count in missing_images:
            print(f"   Page {page}: {count} image(s) missing")
    else:
        print(f"✅ No missing images ({len(pages)} pages checked)")

if __name__ == "__main__":
    log_file = "backend/app.log"
    
    print("Running image handling tests...\n")
    
    test_adaptive_padding(log_file)
    test_yolo_matching(log_file)
    test_recovery_mechanism(log_file)
    test_fallback_mechanism(log_file)
    test_no_missing_images(log_file)
    
    print("\n✅ All tests completed!")
```

**Run with**:
```bash
cd /Users/codegnan2/Desktop/Back-up/GLM-5
python test_image_handling.py
```

---

## Manual Verification Steps

### Step 1: Check Logs
```bash
cd backend
tail -f app.log | grep -E "(adaptive padding|YOLO|Recovery|Fallback|crop tag)"
```

### Step 2: Compare OCR vs Final Output
1. Upload a test PDF
2. Check OCR output for crop tags:
   ```bash
   grep -o "crop:\[" app.log | wc -l
   ```
3. Check final HTML for images:
   ```bash
   grep -o "data:image/png;base64" app.log | wc -l
   ```
4. Counts should match

### Step 3: Visual Inspection
1. Open translated document in frontend viewer
2. Compare side-by-side with original PDF
3. Verify:
   - All images present
   - Correct positions
   - Proper bounding boxes
   - No cut-off content

---

## Performance Benchmarks

Expected performance after fixes:

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| Missing images | 10-20% | <2% | <5% |
| YOLO upgrade rate | 40-50% | 60-70% | >50% |
| Crop failures | 5-10% | <1% | <2% |
| Recovery activations | N/A | 5-10% | <15% |
| Fallback activations | N/A | 1-3% | <5% |

---

## Troubleshooting

### Issue: Images still missing
**Check**:
1. Are crop tags in OCR output? `grep "crop:" app.log`
2. Did Gemini drop them? Look for "lost during reconstruction"
3. Did recovery work? Look for "Recovering lost crop tag"
4. Are coordinates valid? Check for "Invalid coords" warnings

**Solution**:
- If OCR has no crop tags → GLM-OCR issue
- If Gemini drops tags → Recovery should catch them
- If recovery fails → Check regex pattern in reconstruction_service.py

### Issue: Bounding boxes still poor
**Check**:
1. Is YOLO detecting figures? Look for "YOLO detected X figure(s)"
2. Is IoU matching working? Look for "YOLO precision upgrade"
3. Is padding appropriate? Look for "Using adaptive padding=X"

**Solution**:
- If YOLO not detecting → Check YOLO model loaded
- If IoU not matching → Lower threshold further (0.15)
- If padding wrong → Adjust thresholds in reconstruction_service.py

### Issue: Images cut off
**Check**:
1. Is smart trim too aggressive? Look for "Smart trim removed X%"
2. Is padding too small? Check "adaptive padding=X"

**Solution**:
- Disable smart trim: `CROP_SMART_PADDING=false` in .env
- Increase padding: Adjust thresholds in code (12→15, 18→22, 25→30)

---

## Configuration Tuning

Fine-tune via environment variables:

```bash
# backend/.env

# Disable smart trim if it's cutting content
CROP_SMART_PADDING=false

# Increase base padding (will be multiplied by adaptive logic)
CROP_PADDING=20

# Lower YOLO matching threshold for more matches
YOLO_IOU_THRESHOLD=0.15

# Increase DPI for better OCR (slower)
RENDER_DPI=250
```

---

## Success Criteria

Deployment is successful if:

✅ **Zero missing images** in test documents
✅ **YOLO upgrade rate > 50%** (check logs)
✅ **No crop failures** without fallback recovery
✅ **Recovery mechanism < 10%** activation rate
✅ **Visual quality** matches or exceeds original
✅ **No performance degradation** (same processing time)

---

## Rollback Procedure

If issues occur in production:

1. **Immediate rollback**:
   ```bash
   cd backend/app/services
   git checkout HEAD~1 reconstruction_service.py
   cd ../../
   git checkout HEAD~1 app/config.py
   ```

2. **Restart backend**:
   ```bash
   pkill -f uvicorn
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. **Verify rollback**:
   - Check logs for old behavior (fixed padding=15)
   - Test a document
   - Confirm no new errors

4. **Report issues** with:
   - Log excerpts showing the problem
   - Test PDF that reproduces issue
   - Expected vs actual behavior
