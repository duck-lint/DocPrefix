param(
    [switch]$OneFile,
    [switch]$SkipSmokeTest,
    [string]$PythonLauncher = "py",
    [string]$VenvPath = ".venv_packaging",
    [string]$PyInstallerVersion = "6.11.1"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$WorkingDirectory
    )

    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
    }
    try {
        Write-Host ">> $FilePath $($ArgumentList -join ' ')"
        & $FilePath @ArgumentList
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($ArgumentList -join ' ')"
        }
    }
    finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

function Resolve-BuilderPython {
    param([string]$PreferredLauncher)

    $preferred = Get-Command $PreferredLauncher -ErrorAction SilentlyContinue
    if ($preferred) {
        return $preferred.Source
    }

    $python = Get-Command "python" -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    throw "Could not find '$PreferredLauncher' or 'python' on PATH."
}

function Get-AppVersion {
    param([string]$DocPrefixPath)

    $content = Get-Content -Path $DocPrefixPath -Raw
    $match = [regex]::Match($content, '__version__\s*=\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "Could not find __version__ in $DocPrefixPath"
    }
    return $match.Groups[1].Value
}

function Write-HashLine {
    param([string]$Path)
    $hash = Get-FileHash -Path $Path -Algorithm SHA256
    Write-Host ("SHA256  {0}  {1}" -f $hash.Hash, $hash.Path)
    return $hash
}

# Resolve paths relative to this script to avoid cwd-dependent behavior.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildDir = Join-Path $RepoRoot "build"
$DistDir = Join-Path $RepoRoot "dist"
$ReleaseDir = Join-Path $RepoRoot "release"
$PackagingDir = Join-Path $RepoRoot "packaging"
$DocPrefixPy = Join-Path $RepoRoot "doc_prefix.py"
$SpecPath = Join-Path $PackagingDir "docprefix.spec"
$GuiEntry = Join-Path $RepoRoot "doc_prefix_gui.pyw"
$SmokeTest = Join-Path $PackagingDir "smoke_test.py"
$DistReadme = Join-Path $PackagingDir "README_DISTRIBUTION.txt"
$VenvDir = Join-Path $RepoRoot $VenvPath
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

$BuilderPython = Resolve-BuilderPython -PreferredLauncher $PythonLauncher

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating packaging venv at $VenvDir"
    if ([System.IO.Path]::GetFileName($BuilderPython).ToLowerInvariant() -eq "py.exe") {
        Invoke-External -FilePath $BuilderPython -ArgumentList @("-3", "-m", "venv", $VenvDir)
    }
    else {
        Invoke-External -FilePath $BuilderPython -ArgumentList @("-m", "venv", $VenvDir)
    }
}

if (-not (Test-Path $VenvPython)) {
    throw "Packaging virtual environment was not created successfully: $VenvPython"
}

Invoke-External -FilePath $VenvPython -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
Invoke-External -FilePath $VenvPython -ArgumentList @(
    "-m", "pip", "install", ("pyinstaller=={0}" -f $PyInstallerVersion)
)

$Version = Get-AppVersion -DocPrefixPath $DocPrefixPy
$ReleaseBaseName = "DocPrefix-v$Version-windows-x64"

Write-Host "Building DocPrefix version $Version"

if (-not $SkipSmokeTest) {
    Invoke-External -FilePath $VenvPython -ArgumentList @($SmokeTest) -WorkingDirectory $RepoRoot
}
else {
    Write-Host "Skipping smoke test (-SkipSmokeTest)."
}

# Clean local build artifacts before packaging for more reproducible outputs.
foreach ($path in @($BuildDir, $DistDir)) {
    if (Test-Path $path) {
        Write-Host "Removing $path"
        Remove-Item -Path $path -Recurse -Force
    }
}
if (-not (Test-Path $ReleaseDir)) {
    New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
}

# ONEDIR is the default because corporate AV often flags ONEFILE more aggressively.
Invoke-External -FilePath $VenvPython -ArgumentList @(
    "-m", "PyInstaller", "--noconfirm", "--clean", $SpecPath
) -WorkingDirectory $RepoRoot

$OnedirExe = Join-Path $DistDir "DocPrefix\DocPrefix.exe"
if (-not (Test-Path $OnedirExe)) {
    throw "ONEDIR build failed; expected executable not found: $OnedirExe"
}

$StagingRoot = Join-Path $ReleaseDir "_staging"
$StagingFolder = Join-Path $StagingRoot $ReleaseBaseName
if (Test-Path $StagingRoot) {
    Remove-Item -Path $StagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingFolder | Out-Null

Copy-Item -Path (Join-Path $DistDir "DocPrefix\*") -Destination $StagingFolder -Recurse -Force
Copy-Item -Path $DistReadme -Destination (Join-Path $StagingFolder "README.txt") -Force

$ZipPath = Join-Path $ReleaseDir "$ReleaseBaseName.zip"
if (Test-Path $ZipPath) {
    Remove-Item -Path $ZipPath -Force
}

Compress-Archive -Path $StagingFolder -DestinationPath $ZipPath -Force

$ZipHash = Write-HashLine -Path $ZipPath
$OnedirExeHash = Write-HashLine -Path $OnedirExe

$ZipHashFile = "$ZipPath.sha256.txt"
$OnedirExeHashFile = "$OnedirExe.sha256.txt"
Set-Content -Path $ZipHashFile -Value ("{0} *{1}" -f $ZipHash.Hash, [IO.Path]::GetFileName($ZipPath))
Set-Content -Path $OnedirExeHashFile -Value ("{0} *{1}" -f $OnedirExeHash.Hash, [IO.Path]::GetFileName($OnedirExe))

$OneFileReleasePath = $null
if ($OneFile) {
    # Optional convenience build. ONEFILE is more likely to trigger AV/Security prompts.
    Invoke-External -FilePath $VenvPython -ArgumentList @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "DocPrefix",
        "--noupx",
        "--paths", $RepoRoot,
        $GuiEntry
    ) -WorkingDirectory $RepoRoot

    $OneFileDistExe = Join-Path $DistDir "DocPrefix.exe"
    if (-not (Test-Path $OneFileDistExe)) {
        throw "ONEFILE build failed; expected executable not found: $OneFileDistExe"
    }

    $OneFileReleasePath = Join-Path $ReleaseDir "$ReleaseBaseName-onefile.exe"
    Copy-Item -Path $OneFileDistExe -Destination $OneFileReleasePath -Force
    $OneFileHash = Write-HashLine -Path $OneFileReleasePath
    Set-Content -Path "$OneFileReleasePath.sha256.txt" -Value (
        "{0} *{1}" -f $OneFileHash.Hash, [IO.Path]::GetFileName($OneFileReleasePath)
    )
}

if (Test-Path $StagingRoot) {
    Remove-Item -Path $StagingRoot -Recurse -Force
}

Write-Host ""
Write-Host "Build complete."
Write-Host "ONEDIR executable : $OnedirExe"
Write-Host "Release zip       : $ZipPath"
Write-Host "Zip SHA256 file   : $ZipHashFile"
Write-Host "Exe SHA256 file   : $OnedirExeHashFile"
if ($OneFileReleasePath) {
    Write-Host "ONEFILE exe       : $OneFileReleasePath"
    Write-Host "ONEFILE SHA256    : $OneFileReleasePath.sha256.txt"
}
