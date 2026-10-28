param([string]$Path)
# Report total pages and the starting page of each document section.
# Run on the pristine template to derive the page_targets value.
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($Path, $false, $true)
    $doc.Repaginate()
    $total = $doc.ComputeStatistics(2)
    Write-Output "TOTAL_PAGES=$total"
    for ($i = 1; $i -le $doc.Sections.Count; $i++) {
        $r = $doc.Sections.Item($i).Range
        $r2 = $doc.Range($r.Start, $r.Start)
        Write-Output ("SECTION {0} starts page {1}" -f $i, $r2.Information(3))
    }
    $doc.Close($false)
} finally {
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
}
