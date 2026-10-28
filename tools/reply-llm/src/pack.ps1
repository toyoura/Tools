# Build dist/reply-llm-<version>.xpi for "Install Add-on From File".
# Compress-Archive in Windows PowerShell 5.1 writes "\" into entry names,
# which Thunderbird rejects, so the zip is written entry by entry.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem

$root = $PSScriptRoot
$version = (Get-Content "$root\manifest.json" -Raw -Encoding UTF8 | ConvertFrom-Json).version
$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$xpi = Join-Path $dist "reply-llm-$version.xpi"
if (Test-Path $xpi) { Remove-Item $xpi }

$include = @("manifest.json", "icon.svg", "lib", "popup", "options")
$zip = [System.IO.Compression.ZipFile]::Open($xpi, "Create")
try {
    foreach ($item in $include) {
        Get-ChildItem (Join-Path $root $item) -Recurse -File | ForEach-Object {
            $name = $_.FullName.Substring($root.Length + 1).Replace("\", "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $name) | Out-Null
        }
    }
} finally {
    $zip.Dispose()
}
Write-Output $xpi
