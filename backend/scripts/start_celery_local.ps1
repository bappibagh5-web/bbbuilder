$ErrorActionPreference = "Stop"

# Windows' prefork pool is not supported reliably. Analysis is network-I/O bound,
# so a bounded threads pool provides real local page concurrency.
$concurrency = 3
$configured = Get-Content "$PSScriptRoot\..\.env" -ErrorAction SilentlyContinue |
  Where-Object { $_ -match '^AI_PAGE_CONCURRENCY=\d+$' } |
  Select-Object -First 1
if ($configured) {
  $concurrency = [int]($configured -split '=', 2)[1]
}
& "$PSScriptRoot\..\.venv\Scripts\celery.exe" -A config worker `
  --loglevel=INFO `
  --pool=threads `
  --concurrency=$concurrency `
  --prefetch-multiplier=1 `
  --queues=analysis-pages,analysis-synthesis,celery
