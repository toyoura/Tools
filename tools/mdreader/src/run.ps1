# MdReader - Markdown 読み上げビューア
#   powershell -ExecutionPolicy Bypass -File run.ps1 path\to\note.md
param([string]$Path, [int]$Port = 8765)
$server = Join-Path $PSScriptRoot "server.py"
if ($Path) { python $server $Path --port $Port } else { python $server --port $Port }
