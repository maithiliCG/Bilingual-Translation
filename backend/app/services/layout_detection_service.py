"""
Document layout detection service using DocLayout-YOLO.

Detects ONLY figure/image regions in document page images with precise bounding boxes.
Text, tables, headers, etc. are all handled by GLM-OCR — this service focuses solely
on giving us accurate image boundaries for better cropping.
"""

import asyncio
import io
import logging
from typing import Dict, List

from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level singleton (lazy-loaded, thread-safe)
_model = None
_model_lock = None


def _get_model_lock():
    """Lazy-init asyncio.Lock inside the running event loop (Python 3.10+ safe)."""
    global _model_lock
    if _model_lock is None:
        _model_lock = asyncio.Lock()
    return _model_lock
_model_load_failed = False


async def _load_model():
    """Lazy-load the DocLayout-YOLO model (singleton)."""
    global _model, _model_load_failed

    if _model is not None:
        return _model

    if _model_load_failed:
        return None

    async with _get_model_lock():
        # Double-check after acquiring lock
        if _model is not None:
            return _model
        if _model_load_failed:
            return None

        try:
            from doclayout_yolo import YOLOv10

            model_path = getattr(settings, "DOCLAYOUT_MODEL_PATH", "")

            if not model_path:
                # Auto-download from HuggingFace on first use
                # (works offline if already cached — respects HF_HUB_OFFLINE=1)
                from huggingface_hub import hf_hub_download

                try:
                    logger.info("Loading DocLayout-YOLO model from HuggingFace cache...")
                    model_path = hf_hub_download(
                        repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
                        filename="doclayout_yolo_docstructbench_imgsz1024.pt",
                    )
                    logger.info(f"DocLayout-YOLO model loaded from: {model_path}")
                except Exception as dl_err:
                    logger.warning(
                        f"DocLayout-YOLO download failed ({dl_err}). "
                        f"If HF_HUB_OFFLINE=1, run 'python setup_env.py' first to pre-download models. "
                        f"Figure detection disabled."
                    )
                    _model_load_failed = True
                    return None

            _model = YOLOv10(model_path)
            logger.info("DocLayout-YOLO model loaded successfully")
            return _model

        except ImportError:
            logger.warning(
                "doclayout-yolo package not installed. "
                "Figure detection disabled — falling back to GLM-OCR coordinates."
            )
            _model_load_failed = True
            return None

        except Exception as e:
            logger.error(f"Failed to load DocLayout-YOLO model: {e}", exc_info=True)
            _model_load_failed = True
            return None


class LayoutDetectionService:
    """
    Detects figure/image regions in document pages using DocLayout-YOLO.

    Only extracts 'figure' class detections. Everything else (text, tables,
    headers, etc.) is handled by GLM-OCR.
    """

    # We want figure detections and isolated formulas (often complex geometry/diagrams)
    FIGURE_CLASSES = {"figure", "isolate_formula"}

    async def detect_figures(
        self,
        page_image_bytes: bytes,
        conf_threshold: float = 0.25,
    ) -> List[Dict]:
        """
        Detect figure/image regions in a page image.

        Args:
            page_image_bytes: PNG bytes of the rendered page
            conf_threshold: Minimum confidence threshold for detections

        Returns:
            List of figure detections, each containing:
            - bbox_normalized: [ymin, xmin, ymax, xmax] in 0-1000 scale
              (same coordinate system as GLM-OCR's crop tags)
            - bbox_pixels: [x1, y1, x2, y2] in pixel coordinates
            - confidence: float 0-1
        """
        model = await _load_model()
        if model is None:
            return []

        try:
            # Open image to get dimensions
            img = Image.open(io.BytesIO(page_image_bytes)).convert("RGB")
            img_width, img_height = img.size

            # Run detection in a thread (YOLO is synchronous, fast ~12ms on CPU)
            results = await asyncio.to_thread(
                model.predict,
                img,
                imgsz=1024,
                conf=conf_threshold,
                device="cpu",
                verbose=False,
            )

            figures = []
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id].lower()

                # Only keep figure detections — skip text, tables, headers, etc.
                if cls_name not in self.FIGURE_CLASSES:
                    continue

                confidence = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                # Convert pixel coords to normalized 0-1000 scale
                # Format: [ymin, xmin, ymax, xmax] to match GLM-OCR's convention
                ymin = int((y1 / img_height) * 1000)
                xmin = int((x1 / img_width) * 1000)
                ymax = int((y2 / img_height) * 1000)
                xmax = int((x2 / img_width) * 1000)

                figures.append(
                    {
                        "bbox_normalized": [ymin, xmin, ymax, xmax],
                        "bbox_pixels": [int(x1), int(y1), int(x2), int(y2)],
                        "confidence": round(confidence, 3),
                    }
                )

            if figures:
                logger.info(
                    f"DocLayout-YOLO: detected {len(figures)} figure(s) — "
                    + ", ".join(
                        f"[{f['bbox_normalized']}] conf={f['confidence']}"
                        for f in figures
                    )
                )
            else:
                logger.info("DocLayout-YOLO: no figures detected on this page")

            return figures

        except Exception as e:
            logger.error(f"Layout detection failed: {e}", exc_info=True)
            return []


def compute_iou(box1: list, box2: list) -> float:
    """
    Compute Intersection over Union between two boxes.
    Both boxes use [ymin, xmin, ymax, xmax] format (0-1000 normalized).
    """
    inter_ymin = max(box1[0], box2[0])
    inter_xmin = max(box1[1], box2[1])
    inter_ymax = min(box1[2], box2[2])
    inter_xmax = min(box1[3], box2[3])

    inter_area = max(0, inter_ymax - inter_ymin) * max(0, inter_xmax - inter_xmin)

    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = area1 + area2 - inter_area

    return inter_area / union_area if union_area > 0 else 0.0


def find_best_yolo_match(
    glm_coords: list,
    yolo_detections: List[Dict],
    iou_threshold: float = 0.3,
) -> Dict | None:
    """
    Find the YOLO detection that best matches a GLM-OCR crop tag.

    Args:
        glm_coords: [ymin, xmin, ymax, xmax] from GLM-OCR (0-1000 scale)
        yolo_detections: List of YOLO figure detections
        iou_threshold: Minimum IoU to consider a match

    Returns:
        Best matching YOLO detection dict, or None if no match
    """
    best_match = None
    best_iou = 0.0

    for det in yolo_detections:
        iou = compute_iou(glm_coords, det["bbox_normalized"])
        if iou > best_iou:
            best_iou = iou
            best_match = det

    if best_match and best_iou >= iou_threshold:
        return best_match

    return None
