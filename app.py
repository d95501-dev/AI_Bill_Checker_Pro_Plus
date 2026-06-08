#!/usr/bin/env python3
"""
AI Multi-Bill OCR Processor - All Providers Support
Deep CSC AI | ID: 256423250015 | Owner: Deepak
Fixes multi-page PDF extraction for all OCR providers
"""

import os
import json
import base64
from pathlib import Path
from typing import List, Dict, Any
import fitz  # PyMuPDF
from pdf2image import convert_from_path

# ==================== CONFIGURATION ====================
class Config:
    GCP_CREDENTIALS_PATH = "google_credentials.json"
    GCP_PROJECT_ID = "your-project-id"
    AWS_PROFILE = "default"
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your-gemini-key")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-openai-key")
    PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "your-perplexity-key")
    OUTPUT_DIR = "extracted_bills"

# ==================== PDF UTILITIES ====================
class PDFProcessor:
    @staticmethod
    def split_pdf_to_pages(pdf_path: str) -> List[fitz.Document]:
        """Split PDF into individual pages"""
        doc = fitz.open(pdf_path)
        pages = []
        for i in range(len(doc)):
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=i, to_page=i)
            pages.append(new_doc)
        return pages
    
    @staticmethod
    def pdf_to_images(pdf_path: str, dpi=200) -> List:
        """Convert PDF pages to images"""
        images = convert_from_path(pdf_path, dpi=dpi)
        return images
    
    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """Get total pages in PDF"""
        doc = fitz.open(pdf_path)
        return len(doc)

# ==================== PROVIDER 1: Google Vision OCR ====================
class GoogleVisionOCR:
    def __init__(self):
        from google.cloud import vision
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = Config.GCP_CREDENTIALS_PATH
        self.client = vision.ImageAnnotatorClient()
    
    def extract_all_bills(self, pdf_path: str) -> List[Dict]:
        """Extract text from ALL pages of PDF"""
        from google.cloud import vision
        import io
        
        images = PDFProcessor.pdf_to_images(pdf_path)
        all_bills = []
        
        for i, image in enumerate(images):
            # Convert PIL image to byte data
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')
            img_bytes = img_byte_arr.getvalue()
            
            response = self.client.document_text_detection(
                image=vision.Image(content=img_bytes)
            )
            
            bill_data = {
                "page": i + 1,
                "text": response.full_text_annotation.text,
                "provider": "Google Vision OCR"
            }
            all_bills.append(bill_data)
            print(f"✓ Page {i+1} extracted via Google Vision")
        
        return all_bills

# ==================== PROVIDER 2: Google Document AI ====================
class GoogleDocumentAI:
    def __init__(self):
        from google.cloud import documentai
        self.client = documentai.DocumentProcessorServiceClient()
        self.processor_name = (
            f"projects/{Config.GCP_PROJECT_ID}/locations/us/processors/YOUR_PROCESSOR_ID"
        )
    
    def extract_all_bills(self, pdf_path: str) -> List[Dict]:
        """Process multi-page PDF with Document AI"""
        from google.cloud import documentai
        
        # Read PDF
        with open(pdf_path, "rb") as image:
            content = image.read()
        
        document = documentai.Document(
            gutted_bytes=content,
            mime_type="application/pdf"
        )
        
        request = documentai.ProcessRequest(
            name=self.processor_name,
            raw_document=document
        )
        
        result = self.client.process_document(request=request)
        document = result.document
        
        # All pages are processed together - extract entities
        bill_data = {
            "page": 1,  # Document AI processes entire PDF
            "text": document.text,
            "entities": [
                {
                    "type": entity.type,
                    "text": document.text[entity.start_offset:entity.end_offset]
                }
                for entity in document.entities
            ],
            "provider": "Google Document AI",
            "total_pages": PDFProcessor.get_page_count(pdf_path)
        }
        
        print(f"✓ PDF processed ({bill_data['total_pages']} pages) via Document AI")
        return [bill_data]

# ==================== PROVIDER 3: AWS Textract ====================
class AWSTextract:
    def __init__(self):
        import boto3
        self.client = boto3.client('textract', profile_name=Config.AWS_PROFILE)
        self.s3_client = boto3.client('s3', profile_name=Config.AWS_PROFILE)
        self.bucket_name = "your-bucket-name"
    
    def extract_all_bills(self, pdf_path: str) -> List[Dict]:
        """Extract ALL pages using asynchronous Textract"""
        import boto3
        import time
        
        # Upload PDF to S3
        file_name = os.path.basename(pdf_path)
        self.s3_client.upload_file(pdf_path, self.bucket_name, file_name)
        
        # Start async text detection (handles multi-page)
        response = self.client.start_document_text_detection(
            DocumentLocation={
                'S3Object': {
                    'Bucket': self.bucket_name,
                    'Name': file_name
                }
            }
        )
        
        job_id = response['JobId']
        
        # Poll for completion
        while True:
            result = self.client.get_document_text_detection(JobId=job_id)
            
            if result['JobStatus'] == 'SUCCEEDED':
                break
            elif result['JobStatus'] == 'FAILED':
                raise Exception("Textract job failed")
            
            time.sleep(5)
        
        # Extract text with NextToken for ALL pages
        all_text = []
        blocks = result.get('Blocks', [])
        
        # Handle pagination with NextToken
        while 'NextToken' in result:
            result = self.client.get_document_text_detection(
                JobId=job_id,
                NextToken=result['NextToken']
            )
            blocks.extend(result.get('Blocks', []))
        
        # Group by page
        page_texts = {}
        for block in blocks:
            if block['BlockType'] == 'LINE':
                page_num = block.get('Page', 1)
                if page_num not in page_texts:
                    page_texts[page_num] = []
                page_texts[page_num].append(block['Text'])
        
        all_bills = []
        for page_num, text_lines in sorted(page_texts.items()):
            all_bills.append({
                "page": page_num,
                "text": "\n".join(text_lines),
                "provider": "AWS Textract"
            })
        
        print(f"✓ {len(all_bills)} pages extracted via AWS Textract")
        return all_bills

# ==================== PROVIDER 4: Gemini (FIXED) ====================
class GeminiOCR:
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-3.5-flash")
    
    def extract_all_bills(self, pdf_path: str) -> List[Dict]:
        """Extract ALL bills from multi-page PDF - FIXED"""
        import google.generativeai as genai
        
        # METHOD 1: Use Files API (recommended for multi-page)
        sample_doc = genai.upload_file(
            path=pdf_path,
            mime_type='application/pdf'
        )
        
        # Wait for processing
        while sample_doc.state.name == "PROCESSING":
            import time
            time.sleep(2)
            sample_doc = genai.get_file(sample_doc.name)
        
        # Prompt explicitly asks for ALL pages
        prompt = """Extract ALL bills from this multi-page PDF.
        - This PDF contains multiple separate bills on different pages
        - Extract each bill's data separately
        - Return data for each page separately
        - Don't skip any pages
        - Format as JSON array with page number and extracted data"""
        
        response = self.model.generate_content(
            [sample_doc, prompt]
        )
        
        # METHOD 2: Alternative - Split PDF manually
        pages = PDFProcessor.split_pdf_to_pages(pdf_path)
        all_bills = []
        
        for i, page_doc in enumerate(pages):
            page_bytes = page_doc.write()
            
            response = self.model.generate_content([
                genai.types.Part.from_bytes(
                    data=page_bytes, 
                    mime_type='application/pdf'
                ),
                "Extract bill data from page " + str(i+1)
            ])
            
            all_bills.append({
                "page": i + 1,
                "text": response.text,
                "provider": "Gemini"
            })
        
        print(f"✓ {len(all_bills)} pages extracted via Gemini")
        return all_bills

# ==================== PROVIDER 5: OpenAI ====================
class OpenAIOCR:
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
    
    def extract_all_bills(self, pdf_path: str) -> List[Dict]:
        """Extract all pages using OpenAI GPT-4o"""
        images = PDFProcessor.pdf_to_images(pdf_path)
        all_bills = []
        
        for i, image in enumerate(images):
            # Convert to base64
            import io
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_base64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": f"Extract bill data from page {i+1}. Return structured JSON."
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )
            
            all_bills.append({
                "page": i + 1,
                "text": response.choices[0].message.content,
                "provider": "OpenAI GPT-4o"
            })
        
        print(f"✓ {len(all_bills)} pages extracted via OpenAI")
        return all_bills

# ==================== PROVIDER 6: Perplexity ====================
class PerplexityOCR:
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=Config.PERPLEXITY_API_KEY,
            base_url="https://api.perplexity.ai"
        )
    
    def extract_all_bills(self, pdf_path: str) -> List[Dict]:
        """Extract all pages using Perplexity Sonar"""
        images = PDFProcessor.pdf_to_images(pdf_path)
        all_bills = []
        
        for i, image in enumerate(images):
            import io
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            response = self.client.chat.completions.create(
                model="sonar-pro",
                messages=[
                    {
                        "role": "user",
                        "content": f"""Extract bill data from page {i+1}.
                        Base64 image: {img_base64[:100]}...
                        Return structured JSON with bill details."""
                    }
                ],
                max_tokens=1000
            )
            
            all_bills.append({
                "page": i + 1,
                "text": response.choices[0].message.content,
                "provider": "Perplexity"
            })
        
        print(f"✓ {len(all_bills)} pages extracted via Perplexity")
        return all_bills

# ==================== MAIN PROCESSOR ====================
class MultiBillOCRProcessor:
    def __init__(self):
        self.providers = {
            "Google Vision": GoogleVisionOCR(),
            "Google Document AI": GoogleDocumentAI(),
            "AWS Textract": AWSTextract(),
            "Gemini": GeminiOCR(),
            "OpenAI": OpenAIOCR()
            # Perplexity uses similar pattern as OpenAI
        }
    
    def process(self, pdf_path: str, provider: str = "Gemini") -> List[Dict]:
        """Process PDF with selected provider"""
        if provider not in self.providers:
            raise ValueError(f"Unknown provider: {provider}. Choose from {list(self.providers.keys())}")
        
        print(f"\n📄 Processing: {pdf_path}")
        print(f"🔧 Provider: {provider}")
        print(f"📊 Total pages: {PDFProcessor.get_page_count(pdf_path)}\n")
        
        results = self.providers[provider].extract_all_bills(pdf_path)
        
        # Save results
        os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
        output_file = f"{Config.OUTPUT_DIR}/{Path(pdf_path).stem}_{provider.replace(' ', '_')}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved to: {output_file}")
        print(f"📦 Total bills extracted: {len(results)}")
        
        return results
    
    def compare_all_providers(self, pdf_path: str) -> Dict[str, List[Dict]]:
        """Process with ALL providers and compare"""
        all_results = {}
        
        for provider in self.providers.keys():
            print(f"\n{'='*60}")
            print(f"Testing: {provider}")
            print(f"{'='*60}")
            all_results[provider] = self.process(pdf_path, provider)
        
        return all_results

# ==================== USAGE ====================
if __name__ == "__main__":
    processor = MultiBillOCRProcessor()
    
    # Process single PDF with Gemini (FIXED for multi-page)
    pdf_file = "bill.pdf"
    
    if os.path.exists(pdf_file):
        # Option 1: Single provider
        results = processor.process(pdf_file, provider="Gemini")
        
        # Option 2: Compare all providers (uncomment to run)
        # all_results = processor.compare_all_providers(pdf_file)
        
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Original PDF has {PDFProcessor.get_page_count(pdf_file)} pages")
        print(f"Extracted {len(results)} bills successfully ✓")
        
        # Show first bill preview
        if results:
            print("\n📋 First bill preview:")
            print(f"Page: {results[0]['page']}")
            print(f"Provider: {results[0]['provider']}")
    else:
        print(f"❌ File not found: {pdf_file}")
        print("Please place bill.pdf in the same directory")

# ==================== INSTALLATION ====================
"""
Required packages - install with:
pip install PyMuPDF pdf2image pillow google-cloud-vision google-cloud-documentai boto3 google-generativeai openai python-dotenv

System dependencies:
sudo apt-get install poppler-utils  # For pdf2image
"""
