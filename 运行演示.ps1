param([switch]$TestOnly)

$ErrorActionPreference = 'Stop'
$taskCachedPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskPython = $null
$taskPythonPrefix = @()

if (Test-Path -LiteralPath $taskCachedPython) {
    $taskPython = $taskCachedPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $taskPython = (Get-Command py).Source
    $taskPythonPrefix = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $taskPython = (Get-Command python).Source
} else {
    throw 'Python was not found. Install Python 3.10 or newer.'
}

$taskPreviousIOEncoding = $env:PYTHONIOENCODING
$env:PYTHONIOENCODING = 'utf-8'
Push-Location -LiteralPath $PSScriptRoot
try {
    & $taskPython @taskPythonPrefix -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Demo was not started.' }
    if (-not $TestOnly) {
        & $taskPython @taskPythonPrefix run_demo.py
        if ($LASTEXITCODE -ne 0) { throw 'Demo failed. See the error above.' }
    }
} finally {
    Pop-Location
    $env:PYTHONIOENCODING = $taskPreviousIOEncoding
}
