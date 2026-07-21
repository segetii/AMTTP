Dim word, doc, f, pages, fso, ts, folder, outFile
folder = "C:\amttp\research\visa\EVIDENCE_DOCX_COPIES\"
outFile = "C:\amttp\research\visa\_pages_result.txt"

Dim files(9)
files(0) = "MC-1_AMTTP_Live_Demonstration.docx"
files(1) = "MC-2_GitHub_Contributions.docx"
files(2) = "MC-3_Smart_Contracts.docx"
files(3) = "OC3-1_ML_Pipeline.docx"
files(4) = "OC3-2_War_Room_Dashboard.docx"
files(5) = "OC3-3_CrossChain_SDK.docx"
files(6) = "OC3-4_Security_Auditing.docx"
files(7) = "OC4-1_BSDT_Research.docx"
files(8) = "OC4-2_Academic_Publications.docx"
files(9) = "OC4-3_Academic_Adoption.docx"

Set fso = CreateObject("Scripting.FileSystemObject")
Set ts = fso.CreateTextFile(outFile, True)

Set word = CreateObject("Word.Application")
word.Visible = False
word.DisplayAlerts = 0

Dim i
For i = 0 To 9
    f = folder & files(i)
    Set doc = word.Documents.Open(f, False, True)
    pages = doc.ComputeStatistics(2)
    doc.Close False
    Dim flag
    If pages > 3 Then
        flag = "  <-- OVER"
    Else
        flag = ""
    End If
    ts.WriteLine(pages & "p  " & files(i) & flag)
Next

word.Quit
ts.Close

WScript.Echo "Done. Results in " & outFile
