import csv,io,re,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from fastapi import HTTPException,UploadFile
from pydantic import ValidationError
from app.products.schema import ProductImportRow
NS="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
def xlsx(data):
    try:
        z=zipfile.ZipFile(io.BytesIO(data)); shared=[]
        if "xl/sharedStrings.xml" in z.namelist(): shared=["".join(n.text or "" for n in x.iter(NS+"t")) for x in ET.fromstring(z.read("xl/sharedStrings.xml"))]
        sheet=sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml",n))[0]; out=[]
        for row in ET.fromstring(z.read(sheet)).iter(NS+"row"):
            cells={}
            for c in row.findall(NS+"c"):
                letters="".join(x for x in c.attrib.get("r","A") if x.isalpha()); idx=0
                for x in letters: idx=idx*26+ord(x.upper())-64
                v=c.find(NS+"v"); value=v.text if v is not None and v.text else ""
                if c.attrib.get("t")=="s" and value: value=shared[int(value)]
                cells[idx-1]=value
            out.append([cells.get(i,"") for i in range(max(cells,default=-1)+1)])
        return out
    except Exception as e: raise HTTPException(400,"Invalid XLSX workbook") from e
async def preview(file:UploadFile):
    name=Path(file.filename or "products.csv").name; suffix=Path(name).suffix.lower(); data=await file.read(2097153)
    if len(data)>2097152: raise HTTPException(413,"Import files must not exceed 2 MB")
    if suffix==".csv":
        try: rows=list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        except Exception as e: raise HTTPException(400,"Invalid UTF-8 CSV") from e
    elif suffix==".xlsx": rows=xlsx(data)
    else: raise HTTPException(415,"Only CSV and XLSX files are supported")
    rows=[r for r in rows if any(str(v).strip() for v in r)]
    if len(rows)<2 or len(rows)>1001: raise HTTPException(400,"Import requires 1 to 1000 data rows")
    headers=[str(v).strip().lower().replace(" ","_") for v in rows[0]]; result=[]
    for number,raw in enumerate(rows[1:],2):
        values={h:(str(raw[i]).strip() or None) if i<len(raw) else None for i,h in enumerate(headers)}; errors=[]
        try: ProductImportRow.model_validate(values)
        except ValidationError as e: errors=[f"{'.'.join(map(str,x['loc']))}: {x['msg']}" for x in e.errors()]
        result.append({"row_number":number,"values":values,"errors":errors})
    return {"filename":name,"total_rows":len(result),"valid_rows":sum(not r["errors"] for r in result),"rows":result}
