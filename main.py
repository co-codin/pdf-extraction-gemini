import os
import io
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red

load_dotenv()

class BoundingBoxField(BaseModel):
    bounding_box: list[int] = Field(..., description='The bounding box where the information was found [y_min, x_min, y_max, x_max]')
    page: int = Field(..., description='Page number where the information was found. Start counting with 1.')

class TotalAmountField(BoundingBoxField):
    value: float = Field(..., description='The total amount of the invoice.')

class RecipientField(BoundingBoxField):
    name: str = Field(..., description='The name of the recipient.')

class TaxAmountField(BoundingBoxField):
    value: float = Field(..., description='The total amount of the tax.')

class SenderField(BoundingBoxField):
    name: str = Field(..., description='The name of the sender.')

class AccountNumberField(BoundingBoxField):
    account_no: str = Field(..., description='The number of the account.')


class InvoiceModel(BaseModel):
    total: TotalAmountField
    recipient: RecipientField
    tax: TaxAmountField
    sender: SenderField
    account_no: AccountNumberField

client = genai.Client(api_key=os.getenv("GEMENI_API_KEY"))


file_in = 'invoice.pdf'
file_out = 'invoice_annotated.pdf'
pdf = client.files.upload(file=file_in)

prompt = """
Extract the invoice recipient name and invoice total.
Return ONLY JSON that matches the provided schema.
If a field is missing, set it to null (and bounding_box to [0,0,0,0]).
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[pdf, prompt],
    config={
        "response_mime_type": "application/json",
        "response_schema": InvoiceModel
    },
)

invoice = InvoiceModel.model_validate_json(response.text)
print(invoice.model_dump())


items_to_draw = [
    ("TOTAL", invoice.total.bounding_box, invoice.total.page),
    ("RECIPIENT", invoice.recipient.bounding_box, invoice.recipient.page),
    ("TAX", invoice.tax.bounding_box, invoice.tax.page),
    ("SENDER", invoice.sender.bounding_box, invoice.sender.page),
    ("ACCOUNT_NO", invoice.account_no.bounding_box, invoice.account_no.page)
]


reader = PdfReader(file_in)
writer = PdfWriter()

# Iterate over every page in the original PDF
for i, page in enumerate(reader.pages):
    current_page_num = i + 1
    
    # Get page dimensions
    # mediabox returns [x, y, width, height] in points
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    
    # Create a temporary in-memory PDF for the annotations
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Setup drawing style
    can.setStrokeColor(red)
    can.setLineWidth(2)
    can.setFillColor(red)
    can.setFont("Helvetica", 6)
    
    drawn_something = False
    
    for label, box, page_no in items_to_draw:
        # Only draw items belonging to the current page
        if page_no != current_page_num:
            continue
            
        if not box or box == [0, 0, 0, 0]:
            continue

        # Gemini returns [y_min, x_min, y_max, x_max] normalized to 1000
        y_min_norm, x_min_norm, y_max_norm, x_max_norm = box

        # Convert normalized coordinates (0-1000) to PDF points
        # PDF Origin (0,0) is Bottom-Left. 
        # Gemini/Image Origin is usually Top-Left.
        
        # X is straightforward
        x = (x_min_norm / 1000) * page_width
        w = ((x_max_norm - x_min_norm) / 1000) * page_width
        
        # Y needs to be flipped because PDF Y grows upwards
        # Visual Top (y_min) corresponds to Higher Y in PDF
        # Visual Bottom (y_max) corresponds to Lower Y in PDF
        h = ((y_max_norm - y_min_norm) / 1000) * page_height
        y = page_height - ((y_max_norm / 1000) * page_height)

        can.rect(x, y, w, h)
        
        can.drawString(x, y + h + 2, label)
        
        drawn_something = True

    can.save()
    packet.seek(0)
    
    # Only merge if we actually drew something
    if drawn_something:
        annotation_pdf = PdfReader(packet)
        page.merge_page(annotation_pdf.pages[0])
    
    writer.add_page(page)

# Save the result
with open(file_out, "wb") as f:
    writer.write(f)

print(f"Annotated PDF saved to {file_out}")