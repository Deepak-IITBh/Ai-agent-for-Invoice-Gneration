
import streamlit as st
import tempfile
import os
import re
import zipfile
import base64
from typing import List
from pydantic import BaseModel, validator, Field
from groq import Groq
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
api=os.getenv("GROQ_API_KEY")
print(api)
# Initialize Groq client
client = Groq(api_key=api)

# Define Pydantic models with validation
class Item(BaseModel):
    name: str
    quantity: int
    price: float
    
    @validator('price', pre=True)
    def clean_price(cls, value):
        if isinstance(value, str):
            cleaned = re.sub(r'[^\d.]', '', value)
            try:
                return float(cleaned)
            except ValueError:
                cleaned = cleaned.replace(',', '.')
                return float(cleaned)
        return value

class Invoice(BaseModel):
    invoice_number: str = Field(..., alias="invoice_number")
    date: str
    vendor_name: str = Field(..., alias="vendor_name")
    items: List[Item]
    total: float
    
    @validator('total', pre=True)
    def clean_total(cls, value):
        if isinstance(value, str):
            cleaned = re.sub(r'[^\d.]', '', value)
            try:
                return float(cleaned)
            except ValueError:
                cleaned = cleaned.replace(',', '.')
                return float(cleaned)
        return value

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def get_invoice(image_path):
    """Extract invoice data from image using Groq API"""
    try:
        base64_image = encode_image(image_path)
        
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": """Extract invoice details as valid JSON with this exact structure:
                        {
                            "invoice_number": "string",
                            "date": "string",
                            "vendor_name": "string",
                            "items": [
                                {
                                    "name": "string",
                                    "quantity": integer,
                                    "price": float
                                }
                            ],
                            "total": float
                        }
                        Ensure numeric values don't have any special characters. Use double quotes for strings."""},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            },
                        },
                    ],
                }
            ],
            model="llama-3.2-11b-vision-preview",
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        json_response = chat_completion.choices[0].message.content
        json_response = json_response.replace("'", '"')
        json_response = re.sub(r'(\d+),(\d+)', r'\1.\2', json_response)
        
        return Invoice.model_validate_json(json_response)
        
    except Exception as e:
        st.error(f"Error processing image: {str(e)}")
        return None

# Rest of the original code remains the same for processing ZIP files and Streamlit UI
# ... [Keep the process_zip and main functions unchanged] ...


def process_zip(uploaded_zip):
    temp_dir = tempfile.mkdtemp()
    extracted_files = []
    
    with zipfile.ZipFile(uploaded_zip, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
        extracted_files = [os.path.join(temp_dir, file) for file in zip_ref.namelist() if file.lower().endswith(('png', 'jpg', 'jpeg'))]
    
    return extracted_files

def main():
    st.title("📄 Invoice Extraction App")
    st.write("Upload invoice images (ZIP folder or multiple image files) to extract structured data")

    uploaded_zip = st.file_uploader("Upload ZIP file containing invoices", type=["zip"], key="zip_uploader")
    uploaded_images = st.file_uploader("Upload multiple invoice images", type=["png", "jpg", "jpeg"], accept_multiple_files=True, key="image_uploader")
    
    all_invoices = []
    image_paths = []
    
    if uploaded_zip:
        image_paths.extend(process_zip(uploaded_zip))
    
    if uploaded_images:
        for uploaded_file in uploaded_images:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[-1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                image_paths.append(tmp_file.name)
    
    if image_paths:
        for image_path in image_paths:
            with st.spinner(f"Extracting invoice details from {os.path.basename(image_path)}..."):
                invoice = get_invoice(image_path)
            
            if invoice:
                all_invoices.append(invoice)
        
        if all_invoices:
            st.success("✅ All invoices processed successfully!")
            
            final_data = []
            
            for invoice in all_invoices:
                row = {
                    "Invoice Number": invoice.invoice_number,
                    "Date": invoice.date,
                    "Vendor Name": invoice.vendor_name,
                    "Total": invoice.total
                }
                
                for i, item in enumerate(invoice.items):
                    row[f"Item {i+1} Name"] = item.name
                    row[f"Item {i+1} Quantity"] = item.quantity
                    row[f"Item {i+1} Price"] = item.price
                
                final_data.append(row)
            
            df = pd.DataFrame(final_data)
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", csv, "invoices.csv", "text/csv", key="download-csv")

if __name__ == "__main__":
    main()
