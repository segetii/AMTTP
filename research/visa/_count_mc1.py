from pathlib import Path
import time, fitz, win32com.client, pythoncom

SRC = Path(r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-1_AMTTP_Live_Demonstration_v2.docx')
PDF = SRC.with_suffix('.pdf')

pythoncom.CoInitialize()
word = win32com.client.DispatchEx('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(str(SRC), ReadOnly=True)
    doc.SaveAs2(str(PDF), FileFormat=17)
    doc.Close(False)
finally:
    word.Quit()

pages = fitz.open(str(PDF)).page_count
print('Pages:', pages)
