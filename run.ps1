# NEXUS OpsAI launcher
# Optional: $env:ANTHROPIC_API_KEY = "sk-ant-..."   (enables live Claude; otherwise offline mode)
Set-Location $PSScriptRoot
pip install -q -r requirements.txt
Write-Host ""
Write-Host "  NEXUS OpsAI console ->  http://localhost:8611" -ForegroundColor Cyan
Write-Host ""
python -m uvicorn nexus.main:app --port 8611
