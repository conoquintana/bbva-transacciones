import os
import tempfile
import fitz  # PyMuPDF
import pandas as pd
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import re

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


def extract_transactions_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    transactions = []
    capture = False

    for page in doc:
        text = page.get_text("text")
        lines = text.split("\n")

        for i, line in enumerate(lines):
            if "Detalle de Movimientos Realizados" in line:
                capture = True
                continue
            if "Total de Movimientos" in line:
                capture = False
                continue

            if capture and re.search(r'\d{2}/[A-Z]{3}', line):
                parts = line.split()
                if len(parts) >= 6:
                    fecha_oper, fecha_liq = parts[0], parts[1]
                    cod_desc = parts[2]
                    desc_line = ' '.join(parts[3:])

                    ref_lines = lines[i+1:i+4]
                    referencia = ' '.join(l for l in ref_lines if not re.match(r'\d{2}/[A-Z]{3}', l))
                    cargos = abonos = saldo_op = saldo_liq = None

                    monto_match = re.findall(r"\d{1,3}(?:,\d{3})*(?:\.\d{2})", desc_line)
                    if monto_match:
                        cargos = float(monto_match[0].replace(',', ''))

                    clabe_match = re.search(r'\b\d{20}\b', referencia)
                    clave_match = re.search(r'\b[A-Z]{4}\d{20}\b', referencia)
                    clabe = clabe_match.group(0) if clabe_match else None
                    clave = clave_match.group(0) if clave_match else None

                    transactions.append({
                        "Fecha Operación": fecha_oper,
                        "Fecha Liquidación": fecha_liq,
                        "Cod. Descripción": cod_desc,
                        "Referencia": referencia.strip(),
                        "CLABE": clabe,
                        "Clave de rastreo": clave,
                        "Cargos": cargos,
                        "Abonos": abonos,
                        "Saldo Operación": saldo_op,
                        "Saldo Liquidación": saldo_liq
                    })

    return transactions

@app.post("/extract")
async def extract(files: List[UploadFile] = File(...)):
    all_transactions = []
    for file in files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            contents = await file.read()
            tmp.write(contents)
            tmp_path = tmp.name

        transactions = extract_transactions_from_pdf(tmp_path)
        all_transactions.extend(transactions)
        os.remove(tmp_path)

    df = pd.DataFrame(all_transactions)
    return JSONResponse(content=df.to_dict(orient="records"))

