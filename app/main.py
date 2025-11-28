from fastapi import FastAPI, HTTPException
from app.models import ExtractRequest, APIResponse, ExtractionData, TokenUsage
from app.utils import download_file, process_document
from app.services import extract_from_image
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="HackRx Bill Extractor")

@app.post("/extract-bill-data", response_model=APIResponse)
def extract_bill_data(request: ExtractRequest):
    try:
        # 1. Download
        file_content = download_file(request.document)
        
        # 2. Process to Images
        images = process_document(file_content, request.document)
        
        # 3. AI Extraction
        pagewise_items = []
        total_usage = {"total_tokens": 0, "input_tokens": 0, "output_tokens": 0}
        
        for idx, img in enumerate(images):
            page_data, usage = extract_from_image(img, idx + 1)
            pagewise_items.append(page_data)
            
            total_usage["total_tokens"] += usage.get("total_tokens", 0)
            total_usage["input_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["output_tokens"] += usage.get("completion_tokens", 0)

        # 4. Reconciliation Logic
        has_details = any(p.page_type == "Bill Detail" for p in pagewise_items)
        final_line_items = []
        reconciled_total = 0.0
        
        for page in pagewise_items:
            if has_details and page.page_type == "Final Bill":
                continue
            final_line_items.append(page)
            for item in page.bill_items:
                reconciled_total += item.item_amount

        total_count = sum(len(p.bill_items) for p in final_line_items)

        # 5. Return Data Directly
        return APIResponse(
            is_success=True,
            token_usage=TokenUsage(**total_usage),
            data=ExtractionData(
                pagewise_line_items=final_line_items,
                total_item_count=total_count,
                reconciled_amount=round(reconciled_total, 2)
            )
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))