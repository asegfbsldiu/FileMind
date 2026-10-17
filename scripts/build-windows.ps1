[CmdletBinding()]
param(
    [ValidateSet('Prepare', 'Bundle', 'Installer', 'All')]
    [string]$Stage = 'All',
    [string]$PythonLauncher = 'py',
    [string]$IsccPath = '',
    [switch]$ValidateOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildPython = Join-Path $projectRoot '.venv-build\Scripts\python.exe'
$releaseTool = Join-Path $projectRoot 'tools\windows_release.py'

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Program"
    }
}

function Find-InnoCompiler {
    if ($IsccPath) {
        if (-not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
            throw "ISCC.exe not found: $IsccPath"
        }
        return (Resolve-Path -LiteralPath $IsccPath).Path
    }
    $command = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $compilerRoots = @(${env:ProgramFiles(x86)}, $env:ProgramFiles, 'D:\devtools')
    foreach ($compilerRoot in $compilerRoots) {
        if (-not $compilerRoot -or -not (Test-Path -LiteralPath $compilerRoot -PathType Container)) { continue }
        foreach ($directory in (Get-ChildItem -LiteralPath $compilerRoot -Directory -Filter 'Inno Setup*' | Sort-Object Name -Descending)) {
            $candidate = Join-Path $directory.FullName 'ISCC.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
        }
    }
    throw 'Install Inno Setup 6.5+ or pass -IsccPath with the actual ISCC.exe path.'
}

function Initialize-BuildEnvironment {
    if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
        Invoke-Checked $PythonLauncher @('-3.13', '-m', 'venv', (Join-Path $projectRoot '.venv-build'))
    }
    Invoke-Checked $buildPython @('-c', 'import sys, struct; assert sys.version_info[:2] == (3, 13) and struct.calcsize(chr(80)) == 8')
    Invoke-Checked $buildPython @('-m', 'pip', 'install', '--disable-pip-version-check',
        '-r', (Join-Path $projectRoot 'packaging\requirements-windows.lock'),
        '-r', (Join-Path $projectRoot 'packaging\requirements-build.lock'))
    Invoke-Checked $buildPython @('-m', 'pip', 'check')
}

function Initialize-ReleaseMetadata {
    if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
        throw 'Run the Prepare stage first.'
    }
    Invoke-Checked $buildPython @((Join-Path $projectRoot 'tools\export_installer_art.py'))
    Invoke-Checked $buildPython @($releaseTool, 'prepare', '--root', $projectRoot)
}

function Build-Application {
    Initialize-ReleaseMetadata
    Invoke-Checked $buildPython @('-m', 'PyInstaller', '--noconfirm', '--clean',
        '--distpath', (Join-Path $projectRoot 'dist'),
        '--workpath', (Join-Path $projectRoot 'build\pyinstaller'),
        (Join-Path $projectRoot 'packaging\FileMind.spec'))
    Invoke-Checked $buildPython @($releaseTool, 'verify-bundle', '--root', $projectRoot)
}

function Build-Installer {
    Initialize-ReleaseMetadata
    Invoke-Checked $buildPython @($releaseTool, 'verify-bundle', '--root', $projectRoot)
    $compiler = Find-InnoCompiler
    $metadata = Get-Content -LiteralPath (Join-Path $projectRoot 'build\release\metadata.json') -Raw | ConvertFrom-Json
    Invoke-Checked $compiler @("/DAppVersion=$($metadata.version)", (Join-Path $projectRoot 'packaging\FileMind.iss'))
    $compilerVersion = (Get-Item -LiteralPath $compiler).VersionInfo.ProductVersion
    Invoke-Checked $buildPython @($releaseTool, 'artifacts', '--root', $projectRoot,
        '--compiler-version', $compilerVersion)
}

Push-Location -LiteralPath $projectRoot
try {
    if ($ValidateOnly) {
        Invoke-Checked $PythonLauncher @('-3.13', $releaseTool, 'validate-config', '--root', $projectRoot)
    } else {
        if ($Stage -in @('Prepare', 'All')) { Initialize-BuildEnvironment; Initialize-ReleaseMetadata }
        if ($Stage -in @('Bundle', 'All')) { Build-Application }
        if ($Stage -in @('Installer', 'All')) { Build-Installer }
    }
} finally {
    Pop-Location
}
