from fastapi import FastAPI, HTTPException
from app.models import ExtractRequest, APIResponse, ExtractionData, TokenUsage
from app.utils import download_file, process_document
from app.services import extract_from_image
from dotenv import load_dotenv

# Load environment variables (API keys)
load_dotenv()

# Initialize the API
app = FastAPI(
    title="HackRx Bill Extractor",
    description="API to extract line items from medical bills using Vision LLMs."
)

@app.post("/extract-bill-data", response_model=APIResponse)
def extract_bill_data(request: ExtractRequest):
    """
    Main endpoint to process a document URL and return structured bill data.
    """
    try:
        print(f"Processing document: {request.document}")

        # 1. Download the Document
        # We fetch the file bytes from the provided URL
        try:
            file_content = download_file(request.document)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to download file: {str(e)}")
        
        # 2. Convert Document to Images
        # LLMs (Vision models) cannot read PDFs directly; they need images.
        # This function converts PDF pages -> List of Base64 Images.
        try:
            images = process_document(file_content, request.document)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to process document content: {str(e)}")
        
        # 3. Process Each Page with the LLM
        pagewise_items = []
        
        # Initialize token counter
        total_usage = {
            "total_tokens": 0, 
            "input_tokens": 0, 
            "output_tokens": 0
        }
        
        print(f"Total pages to process: {len(images)}")

        # Loop through every page image
        for idx, img in enumerate(images):
            page_number = idx + 1
            print(f"Analyzing Page {page_number}...")
            
            # Call the AI service (Groq/OpenAI/Gemini)
            page_data, usage = extract_from_image(img, page_number)
            
            # Store the data
            pagewise_items.append(page_data)
            
            # Add up the token usage (cost tracking)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)
            total_usage["input_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["output_tokens"] += usage.get("completion_tokens", 0)

        # 4. Reconciliation Logic (The "Smart" Part)
        # PROBLEM: Some bills have "Detail Pages" AND a "Summary Page".
        # If we add everything, we get double the amount.
        # SOLUTION: If we see "Bill Detail" pages, we ignore "Final Bill" pages.
        
        has_details = any(p.page_type == "Bill Detail" for p in pagewise_items)
        
        final_line_items = []
        reconciled_total = 0.0
        
        for page in pagewise_items:
            # If we have detailed breakdown, skip the summary page to avoid double counting
            if has_details and page.page_type == "Final Bill":
                continue
            
            # If it's a pharmacy sheet or detail sheet (or the only sheet), keep it
            final_line_items.append(page)
            
            # Calculate total from the specific line items
            for item in page.bill_items:
                reconciled_total += item.item_amount

        # Calculate total number of items across all valid pages
        total_count = sum(len(p.bill_items) for p in final_line_items)

        # 5. Return the Response
        return APIResponse(
            is_success=True,
            token_usage=TokenUsage(**total_usage),
            data=ExtractionData(
                pagewise_line_items=final_line_items,
                total_item_count=total_count,
                # Round to 2 decimal places for currency format
                reconciled_amount=round(reconciled_total, 2)
            )
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        # Catch-all for unexpected server errors
        print(f"Critical Error: {str(e)}")
        # In a real job, you would log this to a file or monitoring service (DataDog/Sentry)
        raise HTTPException(status_code=500, detail=str(e))