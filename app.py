#!/usr/bin/env python3
import os
import json
import base64
import time
from pathlib import Path
from typing import List, Dict, Any

import fitz
from PIL import Image

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

class PDFProcessor:
    @staticmethod
    def page_count(pdf_path: str) -> int:
        return len(fitz.open(pdf_path))

    @staticmethod
    def split_to_single_page_pdfs(pdf_path: str) -> List[bytes]:
        src = fitz.open(pdf_path)
        pages = []
        for i in range(len(src)):
            dst = fitz.open()
            dst.insert_pdf(src, from_page=i, to_page=i)
            pages.append(dst.tobytes())
        return pages

    @staticmethod
    def pdf_to_images(pdf_path: str, dpi: int = 220) -> List[Image.Image]:
        doc = fitz.open(pdf_path)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            images.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return images

    @staticmethod
    def save_results(pdf_path: str, provider: str, results: List[Dict[str, Any]]) -> str:
        out = OUTPUT_DIR / f"{Path(pdf_path).stem}_{provider.replace(' ', '_')}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        return str(out)

class GoogleVisionOCR:
    def __init__(self, credentials_path: str | None = None):
        from google.cloud import vision
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        self.client = vision.ImageAnnotatorClient()

    def extract_all(self, pdf_path: str) -> List[Dict[str, Any]]:
        from google.cloud import vision
        results = []
        for idx, img in enumerate(PDFProcessor.pdf_to_images(pdf_path), start=1):
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            resp = self.client.document_text_detection(image=vision.Image(content=buf.getvalue()))
            results.append({
                "page": idx,
                "provider": "Google Vision",
                "text": getattr(resp.full_text_annotation, "text", "") or ""
            })
        return results

class GoogleDocumentAI:
    def __init__(self, project_id: str, location: str, processor_id: str):
        from google.cloud import documentai
        self.client = documentai.DocumentProcessorServiceClient()
        self.name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"

    def extract_all(self, pdf_path: str) -> List[Dict[str, Any]]:
        from google.cloud import documentai
        with open(pdf_path, "rb") as f:
            content = f.read()
        raw_document = documentai.RawDocument(content=content, mime_type="application/pdf")
        req = documentai.ProcessRequest(name=self.name, raw_document=raw_document)
        resp = self.client.process_document(request=req)
        doc = resp.document
        if getattr(doc, "pages", None):
            return [{"page": p.page_number, "provider": "Google Document AI", "text": doc.text} for p in doc.pages]
        return [{"page": 1, "provider": "Google Document AI", "text": doc.text}]

class AWSTextract:
    def __init__(self, region_name: str | None = None):
        import boto3
        session = boto3.session.Session(region_name=region_name)
        self.client = session.client("textract")
        self.s3 = session.client("s3")

    def extract_all(self, pdf_path: str, bucket: str | None = None, s3_key: str | None = None) -> List[Dict[str, Any]]:
        if not bucket:
            raise ValueError("AWS Textract needs an S3 bucket for multi-page PDF processing.")
        key = s3_key or Path(pdf_path).name
        self.s3.upload_file(pdf_path, bucket, key)
        start = self.client.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
        )
        job_id = start["JobId"]
        while True:
            r = self.client.get_document_text_detection(JobId=job_id)
            if r["JobStatus"] == "SUCCEEDED":
                result = r
                break
            if r["JobStatus"] == "FAILED":
                raise RuntimeError("Textract job failed")
            time.sleep(2)
        blocks = list(result.get("Blocks", []))
        while result.get("NextToken"):
            result = self.client.get_document_text_detection(JobId=job_id, NextToken=result["NextToken"])
            blocks.extend(result.get("Blocks", []))
        pages: Dict[int, List[str]] = {}
        for b in blocks:
            if b.get("BlockType") == "LINE":
                pages.setdefault(int(b.get("Page", 1)), []).append(b.get("Text", ""))
        return [{"page": p, "provider": "AWS Textract", "text": "\n".join(lines)} for p, lines in sorted(pages.items())]

class GeminiOCR:
    def __init__(self, api_key: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.genai = genai
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def extract_all(self, pdf_path: str) -> List[Dict[str, Any]]:
        file_obj = self.genai.upload_file(path=pdf_path, mime_type="application/pdf")
        while getattr(file_obj, "state", None) and getattr(file_obj.state, "name", None) == "PROCESSING":
            time.sleep(2)
            file_obj = self.genai.get_file(file_obj.name)
        prompt = "Extract ALL bills from this multi-page PDF. Return a JSON array. Do not skip any page."
        resp = self.model.generate_content([file_obj, prompt])
        return [{"page": 1, "provider": "Gemini", "text": getattr(resp, "text", "") or ""}]

class OpenAIOCR:
    def __init__(self, api_key: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)

    def extract_all(self, pdf_path: str) -> List[Dict[str, Any]]:
        results = []
        for idx, img in enumerate(PDFProcessor.pdf_to_images(pdf_path), start=1):
            import io
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": f"Extract bill data from page {idx}. Return JSON."}
                        ]
                    }
                ],
            )
            results.append({"page": idx, "provider": "OpenAI", "text": resp.choices[0].message.content})
        return results

class PerplexityOCR:
    def __init__(self, api_key: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

    def extract_all(self, pdf_path: str) -> List[Dict[str, Any]]:
        results = []
        for idx, img in enumerate(PDFProcessor.pdf_to_images(pdf_path), start=1):
            import io
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            b64 = base64.b64encode(buf.getvalue()).decode()
            resp = self.client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                            {"type": "text", "text": f"Extract bill data from page {idx}. Return JSON."}
                        ]
                    }
                ],
            )
            results.append({"page": idx, "provider": "Perplexity", "text": resp.choices[0].message.content})
        return results

class MultiBillOCRProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.providers = {}
        if config.get("google_vision_credentials"):
            self.providers["Google Vision"] = GoogleVisionOCR(config["google_vision_credentials"])
        if config.get("gcp_project_id") and config.get("gcp_location") and config.get("gcp_processor_id"):
            self.providers["Google Document AI"] = GoogleDocumentAI(
                config["gcp_project_id"], config["gcp_location"], config["gcp_processor_id"]
            )
        if config.get("aws_region"):
            self.providers["AWS Textract"] = AWSTextract(config["aws_region"])
        if config.get("gemini_api_key"):
            self.providers["Gemini"] = GeminiOCR(config["gemini_api_key"])
        if config.get("openai_api_key"):
            self.providers["OpenAI"] = OpenAIOCR(config["openai_api_key"])
        if config.get("perplexity_api_key"):
            self.providers["Perplexity"] = PerplexityOCR(config["perplexity_api_key"])

    def process(self, pdf_path: str, provider: str) -> List[Dict[str, Any]]:
        if provider not in self.providers:
            raise ValueError(f"Provider not configured: {provider}")
        results = self.providers[provider].extract_all(pdf_path)
        PDFProcessor.save_results(pdf_path, provider, results)
        return results

    def process_all(self, pdf_path: str) -> Dict[str, List[Dict[str, Any]]]:
        out = {}
        for p in self.providers:
            out[p] = self.process(pdf_path, p)
        return out

if __name__ == "__main__":
    pdf_file = "bill.pdf"
    config = {
        "google_vision_credentials": os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        "gcp_project_id": os.getenv("GCP_PROJECT_ID"),
        "gcp_location": os.getenv("GCP_LOCATION", "us"),
        "gcp_processor_id": os.getenv("GCP_PROCESSOR_ID"),
        "aws_region": os.getenv("AWS_REGION"),
        "gemini_api_key": os.getenv("GEMINI_API_KEY"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "perplexity_api_key": os.getenv("PERPLEXITY_API_KEY"),
    }
    processor = MultiBillOCRProcessor(config)
    print(json.dumps({
        "page_count": PDFProcessor.page_count(pdf_file),
        "providers": list(processor.providers.keys())
    }, indent=2))
