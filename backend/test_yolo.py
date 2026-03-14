import asyncio
from app.services.layout_detection_service import LayoutDetectionService
from app.services.pdf_service import PDFService

async def test_yolo():
    pdf_path = "/Users/codegnan/Downloads/RRB ALP CBT II PAPER-43.pdf"
    
    detector = LayoutDetectionService()
    # allow all classes to print what it finds
    detector.FIGURE_CLASSES = {"figure", "table", "isolate_formula", "equation"}
    
    for i in range(1, 5):
        print(f"--- PAGE {i} ---")
        try:
            page_bytes = PDFService.render_page_as_image(pdf_path, i)
            figures = await detector.detect_figures(page_bytes, conf_threshold=0.15)
            print(f"Found {len(figures)} items")
            for f in figures:
                print(f)
        except Exception as e:
            print("Error rendering", e)

if __name__ == "__main__":
    asyncio.run(test_yolo())
