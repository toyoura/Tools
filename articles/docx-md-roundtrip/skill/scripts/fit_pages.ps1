param([string]$InPath, [string]$OutPath, [string]$Targets)
# Adjust trailing empty paragraphs in each document section so that the next
# section starts on its target page (from a pristine-template baseline).
# Targets format: "2=6,3=8,4=9"  (section N starts on page P)
# Requires Microsoft Word (COM). Repaginate() before every page read is
# essential: Word returns stale page numbers otherwise.
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
    $doc = $word.Documents.Open($InPath)

    function Get-SectionStartPage($doc, $i) {
        $doc.Repaginate()
        $r = $doc.Sections.Item($i).Range
        $r2 = $doc.Range($r.Start, $r.Start)
        return $r2.Information(3)  # wdActiveEndPageNumber
    }

    $tmap = @{}
    foreach ($pair in $Targets.Split(",")) {
        $kv = $pair.Split("=")
        $tmap[[int]$kv[0]] = [int]$kv[1]
    }

    for ($i = 1; $i -lt 10; $i++) {
        if (-not $tmap.ContainsKey($i + 1)) { continue }
        if ($doc.Sections.Count -lt ($i + 1)) { break }
        $target = $tmap[$i + 1]
        $guard = 0
        # too long: delete trailing empty paragraphs (never ones with pictures)
        while ((Get-SectionStartPage $doc ($i + 1)) -gt $target -and $guard -lt 300) {
            $paras = $doc.Sections.Item($i).Range.Paragraphs
            $n = $paras.Count
            if ($n -lt 2) { break }
            $p = $paras.Item($n - 1)
            if ($p.Range.Text.Trim().Length -eq 0 -and $p.Range.InlineShapes.Count -eq 0) {
                $p.Range.Delete() | Out-Null
            } else {
                Write-Output ("SECTION {0}: OVERFLOW (next starts p{1}, target p{2}) - reduce content" -f $i, (Get-SectionStartPage $doc ($i + 1)), $target)
                break
            }
            $guard++
        }
        # too short: append empty paragraphs
        $guard = 0
        while ((Get-SectionStartPage $doc ($i + 1)) -lt $target -and $guard -lt 300) {
            $paras = $doc.Sections.Item($i).Range.Paragraphs
            $n = $paras.Count
            $paras.Item($n - 1).Range.InsertParagraphAfter()
            $guard++
        }
        Write-Output ("SECTION {0}: next section starts p{1} (target p{2})" -f $i, (Get-SectionStartPage $doc ($i + 1)), $target)
    }

    $total = $doc.ComputeStatistics(2)
    Write-Output "TOTAL_PAGES=$total"
    $doc.SaveAs2($OutPath, 16)  # wdFormatXMLDocument
    $doc.Close($false)
} finally {
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
}
