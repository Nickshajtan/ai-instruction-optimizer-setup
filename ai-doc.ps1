$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  Write-Error "ai-doc runtime is missing. Run: python tools/bootstrap.py"
  exit 1
}
& $Python -m ai_doc @args
exit $LASTEXITCODE
