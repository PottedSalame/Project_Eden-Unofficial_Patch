[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GameDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$source = (Resolve-Path -LiteralPath $GameDirectory).ProviderPath
$test = Join-Path $PSScriptRoot 'test-install'
New-Item -ItemType Directory -Path $test -Force | Out-Null

$patchedExe = Join-Path $test 'Eden.exe'
if (-not (Test-Path -LiteralPath $patchedExe -PathType Leaf)) {
    throw "Create the patched Eden.exe with patch.py before preparing the test install."
}

foreach ($name in @('Images', 'Levels', 'Movies', 'Sounds')) {
    $from = Join-Path $source $name
    $to = Join-Path $test $name
    if (-not (Test-Path -LiteralPath $from -PathType Container)) {
        throw "Missing game asset directory: $from"
    }
    if (Test-Path -LiteralPath $to) {
        $item = Get-Item -LiteralPath $to -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Test asset path is a link; remove it before preparing: $to"
        }
    } else {
        Copy-Item -LiteralPath $from -Destination $to -Recurse
        Write-Host "Copied isolated game assets: $name"
    }
}

foreach ($name in @('d3d8.dll', 'title.edf')) {
    $from = Join-Path $source $name
    $to = Join-Path $test $name
    if (-not (Test-Path -LiteralPath $to)) {
        Copy-Item -LiteralPath $from -Destination $to
        Write-Host "Copied: $name"
    }
}

foreach ($name in @('SAVED GAMES', 'ScreenShots')) {
    $from = Join-Path $source $name
    $to = Join-Path $test $name
    if (-not (Test-Path -LiteralPath $to)) {
        if (Test-Path -LiteralPath $from -PathType Container) {
            Copy-Item -LiteralPath $from -Destination $to -Recurse
        } else {
            New-Item -ItemType Directory -Path $to | Out-Null
        }
        Write-Host "Created isolated: $name"
    }
}

Write-Host "Test install ready: $test"
Write-Host 'The source game folder was not modified.'
