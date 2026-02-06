from pathlib import Path
from typing import List, Dict, Any
from rapidocr_onnxruntime import RapidOCR


class OCRService:
    def __init__(self):
        self.ocr = RapidOCR()

    def recognize_image(self, image_path: Path) -> List[Dict[str, Any]]:
        try:
            result, _ = self.ocr(str(image_path))

            if not result:
                return []

            lines = []
            for line_data in result:
                if len(line_data) >= 2:
                    bbox = line_data[0]
                    text = line_data[1]
                    confidence = line_data[2] if len(line_data) > 2 else 0.0

                    lines.append(
                        {"text": text, "confidence": float(confidence), "bbox": bbox}
                    )

            return lines
        except Exception as e:
            raise Exception(f"OCR failed: {str(e)}")

    def recognize_images(self, image_paths: List[Path]) -> Dict[str, Any]:
        all_lines = []
        full_text_parts = []
        total_pages = len(image_paths)

        for idx, image_path in enumerate(image_paths):
            try:
                lines = self.recognize_image(image_path)
                all_lines.extend(lines)
                page_text = "\n".join([line["text"] for line in lines])
                full_text_parts.append(f"--- Page {idx + 1} ---\n{page_text}")
            except Exception as e:
                print(f"Warning: Failed to process page {idx + 1}: {e}")
                continue

        full_text = "\n\n".join(full_text_parts)

        return {"lines": all_lines, "full_text": full_text, "page_count": total_pages}


_ocr_service = None


def get_ocr_service() -> OCRService:
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service
