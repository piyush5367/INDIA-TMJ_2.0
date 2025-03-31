import os
import re
import pdfplumber
import pandas as pd
import openpyxl
import logging
from pywebio import start_server
from pywebio.input import file_upload, input
from pywebio.output import put_text, put_loading, put_file, toast
from pywebio.session import set_env
from typing import Dict, List

# Configure logging
logging.basicConfig(
    filename="pdf_extraction.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def extract_numbers(text: str, pattern: str) -> List[int]:
    """Extract numbers from text using regex pattern."""
    try:
        return list(map(int, re.findall(pattern, text)))
    except (ValueError, TypeError):
        return []

def extract_advertisement_numbers(text: str) -> List[str]:
    """Extract advertisement numbers from text."""
    advertisement_numbers = []
    for line in text.split("\n"):
        line = line.strip()
        if "CORRIGENDA" in line:  # Stop when Corrigenda section starts
            break
        matches = re.findall(r'(?:^|\s)(\d{5,})\s+\d{2}/\d{2}/\d{4}(?:\s|$)', line)
        advertisement_numbers.extend(matches)
    return advertisement_numbers

def extract_corrigenda_numbers(text: str) -> List[str]:
    """Extract corrigenda numbers from text."""
    corrigenda_numbers = []
    in_corrigenda_section = False
    
    for line in text.split("\n"):
        line = line.strip()
        if "CORRIGENDA" in line:
            in_corrigenda_section = True
            continue
        if "Following Trade Mark applications have been Registered" in line:
            break
        if in_corrigenda_section:
            matches = re.findall(r'(?:^|\s)(\d{5,})(?:\s|$)', line)
            corrigenda_numbers.extend(matches)
    return corrigenda_numbers

def extract_rc_numbers(text: str) -> List[str]:
    """Extract RC numbers from text."""
    rc_numbers = []
    for line in text.split("\n"):
        line = line.strip()
        if "Following Trade Marks Registration Renewed" in line:
            break
        columns = re.split(r'\s{2,}', line)
        if len(columns) >= 1:
            for col in columns:
                if re.fullmatch(r'\d{5,}', col):
                    rc_numbers.append(col)
    return rc_numbers

def extract_renewal_numbers(text: str) -> List[str]:
    """Extract renewal numbers from text."""
    renewal_numbers = []
    in_renewal_section = False
    
    for line in text.split("\n"):
        line = line.strip()
        if "Following Trade Marks Registration Renewed" in line:
            in_renewal_section = True
            continue
        if in_renewal_section:
            matches = re.findall(r'(?:^|\s)(\d{5,})(?:\s|$)', line)
            renewal_numbers.extend(matches)
            renewal_numbers.extend(re.findall(r'Application No[\s:]+(\d{5,})', line))
    return renewal_numbers

def extract_numbers_from_pdf(pdf_content: bytes) -> Dict[str, List[str]]:
    """Extract numbers from PDF content."""
    extracted_data = {
        "Advertisement": [],
        "Corrigenda": [],
        "RC": [],
        "Renewal": []
    }
    
    try:
        with pdfplumber.open(pdf_content) as pdf:
            for page in pdf.pages:
                try:
                    text = page.extract_text()
                    if not text:
                        continue
                        
                    extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                    extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                    extracted_data["RC"].extend(extract_rc_numbers(text))
                    extracted_data["Renewal"].extend(extract_renewal_numbers(text))
                    
                except Exception as page_error:
                    logging.error(f"Error processing page: {str(page_error)}")
                    continue
                    
    except Exception as e:
        logging.error(f"Error opening PDF: {str(e)}")
        raise Exception(f"Error processing PDF: {str(e)}")
    
    # Deduplicate and sort all lists
    for key in extracted_data:
        try:
            extracted_data[key] = sorted(set(int(num) for num in extracted_data[key] if num))
        except (ValueError, TypeError):
            extracted_data[key] = []
    
    return extracted_data

def save_to_excel(data_dict: Dict[str, List[int]]) -> bytes:
    """Save extracted data to Excel file in memory."""
    try:
        with pd.ExcelWriter("output.xlsx", engine="openpyxl") as writer:
            for sheet_name, numbers in data_dict.items():
                if numbers:
                    df = pd.DataFrame(numbers, columns=["Numbers"])
                    df.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        
        with open("output.xlsx", "rb") as f:
            excel_bytes = f.read()
        
        os.remove("output.xlsx")
        return excel_bytes
        
    except Exception as e:
        logging.error(f"Excel save error: {str(e)}")
        raise Exception(f"Error saving to Excel: {str(e)}")

def app():
    """Main PyWebIO application."""
    set_env(title="PDF Number Extractor")
    
    put_text("## PDF Number Extractor")
    put_text("Upload a PDF file to extract numbers from different sections")
    
    # File upload
    file = file_upload(
        "Select a PDF file",
        accept=".pdf",
        required=True
    )
    
    with put_loading(shape="grow", color="primary"):
        try:
            # Process the PDF
            extracted_data = extract_numbers_from_pdf(file['content'])
            
            # Check if any data was extracted
            if not any(extracted_data.values()):
                toast("No matching numbers found in the PDF", color="warning")
                put_text("No matching numbers found in the PDF file.")
                return
            
            # Generate Excel file
            excel_bytes = save_to_excel(extracted_data)
            
            # Show success message
            toast("Extraction completed successfully!", color="success")
            put_text("### Extraction Results:")
            
            # Show counts for each section
            for section, numbers in extracted_data.items():
                put_text(f"{section}: {len(numbers)} numbers found")
            
            # Download button for Excel file
            put_file(
                "extracted_numbers.xlsx",
                excel_bytes,
                "Download Extracted Numbers"
            )
            
        except Exception as e:
            toast("Error during processing", color="error")
            put_text(f"An error occurred: {str(e)}")
            logging.error(f"Application error: {str(e)}")

if __name__ == "__main__":
    start_server(app, port=8080, debug=True)
