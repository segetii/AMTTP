import win32com.client, fitz, time

src = r'C:\amttp\research\visa\SUBMISSION_ORGANISED_BY_CATEGORY\01_Mandatory_Criteria_MC\MC-1_AMTTP_Live_Demonstration.docx'
pdf = r'C:\amttp\research\visa\_orig_check.pdf'

word = win32com.client.Dispatch('Word.Application')
word.Visible = False
time.sleep(1)
doc = word.Documents.Open(src)
time.sleep(2)
doc.SaveAs2(pdf, FileFormat=17)
time.sleep(1)
doc.Close(False)
word.Quit()
pages = fitz.open(pdf).page_count
print('Original pages:', pages)
