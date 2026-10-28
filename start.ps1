$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Set up the Python environment using README.md first.'
}
& '.\.venv\Scripts\python.exe' app.py
