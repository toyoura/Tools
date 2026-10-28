param([string]$Path, [string]$Targets)
# Per-section: how many text lines sit beyond the section's allotted last page.
# Targets is the same "2=4,3=5,4=6" string used by fit_pages.ps1.
$startTargets = @{}
foreach ($pair in $Targets.Split(',')) {
    $kv = $pair.Split('='); $startTargets[[int]$kv[0]] = [int]$kv[1]
}
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($Path, $false, $true)
    $doc.Repaginate()
    Write-Output ("TOTAL_PAGES={0}" -f $doc.ComputeStatistics(2))
    $n = $doc.Sections.Count
    for ($i = 1; $i -le $n; $i++) {
        # allotted last page for section i = (start of section i+1) - 1
        if ($startTargets.ContainsKey($i + 1)) { $last = $startTargets[$i + 1] - 1 }
        else { $last = $startTargets[$n] }
        $sec = $doc.Sections.Item($i).Range
        $first = $doc.Range($sec.Start, $sec.Start).Information(3)
        $endPg = $doc.Range($sec.End - 1, $sec.End - 1).Information(3)
        $over = 0
        foreach ($p in $sec.Paragraphs) {
            if ($p.Range.Information(3) -gt $last) { $over += $p.Range.ComputeStatistics(1) }
        }
        Write-Output ("SECTION {0}: pages {1}-{2}  allotted last p{3}  lines_beyond={4}" -f $i, $first, $endPg, $last, $over)
    }
    $doc.Close($false)
} finally {
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
}
