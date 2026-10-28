param([string]$InPath, [string]$OutPath)
# Export a docx to PDF via Word COM (for layout verification).
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($InPath, $false, $true)
    $doc.SaveAs2($OutPath, 17)  # wdFormatPDF
    $doc.Close($false)
} finally {
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
}
