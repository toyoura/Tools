param([string]$Path)
# Lines and characters actually laid out on each page.
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($Path, $false, $true)
    $doc.Repaginate()
    $total = $doc.ComputeStatistics(2)
    for ($pg = 1; $pg -le $total; $pg++) {
        $start = $doc.GoTo(1, 1, $pg).Start
        if ($pg -lt $total) { $end = $doc.GoTo(1, 1, $pg + 1).Start } else { $end = $doc.Content.End }
        $rng = $doc.Range($start, $end)
        $chars = ($rng.Text -replace '\s', '').Length
        Write-Output ("p{0,-3} lines={1,-4} chars={2}" -f $pg, $rng.ComputeStatistics(1), $chars)
    }
    $doc.Close($false)
} finally {
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
}
