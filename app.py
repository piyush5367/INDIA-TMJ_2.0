from flask import Flask, request, render_template, send_file, redirect, url_for
import pdfplumber
import pandas as pd
import re
from io import BytesIO
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Extraction functions
def extract_numbers(text, pattern):
    return list(map(int, re.findall(pattern, text)))

def extract_advertisement_numbers(text):
    advertisement_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:
            break
        matches = re.findall(r' (\d{5,})\s+\d{2}/\d{2}/\d{4} ', line)
        advertisement_numbers.extend(matches)
    return advertisement_numbers

def extract_corrigenda_numbers(text):
    corrigenda_numbers = []
    found_corrigenda_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "CORRIGENDA" in line:
            found_corrigenda_section = True
            continue
        if "Following Trade Mark applications have been Registered" in line:
            break
        if found_corrigenda_section:
            matches = re.findall(r' (\d{5,})\s*[ ]', line)
            corrigenda_numbers.extend(matches)
    return corrigenda_numbers

def extract_rc_numbers(text):
    rc_numbers = []
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed" in line:
            break
        columns = line.split()
        if len(columns) == 5 and all(col.isdigit() for col in columns):
            rc_numbers.extend(columns)
    return rc_numbers

def extract_renewal_numbers(text):
    renewal_numbers = []
    found_renewal_section = False
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if "Following Trade Marks Registration Renewed" in line:
            found_renewal_section = True
            continue
        if found_renewal_section:
            renewal_numbers.extend(extract_numbers(line, r' \b(\d{5})\b'))
            renewal_numbers.extend(extract_numbers(line, r'Application No\s+(\d{5,}) '))
    return renewal_numbers

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        if 'pdf_file' not in request.files:
            return redirect(request.url)
        
        file = request.files['pdf_file']
        if file.filename == '':
            return redirect(request.url)
        
        if file and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            extracted_data = {
                "Advertisement": [],
                "Corrigenda": [],
                "RC": [],
                "Renewal": []
            }
            
            try:
                with pdfplumber.open(filepath) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            extracted_data["Advertisement"].extend(extract_advertisement_numbers(text))
                            extracted_data["Corrigenda"].extend(extract_corrigenda_numbers(text))
                            extracted_data["RC"].extend(extract_rc_numbers(text))
                            extracted_data["Renewal"].extend(extract_renewal_numbers(text))
                
                # Remove duplicates and sort
                for key in extracted_data:
                    extracted_data[key] = sorted(list(set(extracted_data[key])))
                
                # Generate CSV files
                csv_files = {}
                for category, numbers in extracted_data.items():
                    if numbers:
                        df = pd.DataFrame({"Numbers": numbers})
                        output = BytesIO()
                        df.to_csv(output, index=False)
                        output.seek(0)
                        csv_files[f"{category.lower()}_numbers.csv"] = output.getvalue()
                
                os.remove(filepath)  # Clean up uploaded file
                
                if not csv_files:
                    return render_template("upload.html", error="No matching numbers found in the PDF")
                
                return render_template("results.html", files=csv_files.keys())
            
            except Exception as e:
                os.remove(filepath)  # Clean up if error occurs
                return render_template("upload.html", error=f"Error processing PDF: {str(e)}")
        
        return render_template("upload.html", error="Please upload a valid PDF file")
    
    return render_template("upload.html")

@app.route("/download/<filename>")
def download(filename):
    if filename in ["advertisement_numbers.csv", "corrigenda_numbers.csv", "rc_numbers.csv", "renewal_numbers.csv"]:
        category = filename.split("_")[0].capitalize()
        return send_file(
            BytesIO(request.args.get('data').encode('latin1')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
