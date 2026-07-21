import pythoncom, win32com.client, fitz
from pathlib import Path
docx = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-3_Smart_Contracts.docx')
pdf  = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-3_Smart_Contracts.pdf')
pythoncom.CoInitialize()
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False; word.DisplayAlerts = 0
d = word.Documents.Open(str(docx), ReadOnly=True)
d.SaveAs2(str(pdf), FileFormat=17)
d.Close(False); word.Quit()
pages = fitz.open(str(pdf)).page_count
tick = "OK" if pages <= 3 else "OVER"
print(f'MC-3 PDF: {pages} pages {tick}')
