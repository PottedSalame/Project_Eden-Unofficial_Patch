[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$GameDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$game = (Resolve-Path -LiteralPath $GameDirectory).ProviderPath
$source = Join-Path $game 'Eden.exe'
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Eden.exe was not found in the selected GOG game directory."
}

$build = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Path $build -Force | Out-Null
$patched = Join-Path $build 'Eden-patched.exe'
$manifest = Join-Path $build 'patch-manifest.bin'
$setup = Join-Path $build 'ProjectEdenUnofficialSetup.exe'

& py -3 (Join-Path $PSScriptRoot 'patch.py') --source $source --output $patched
if ($LASTEXITCODE -ne 0) { throw 'The game executable patch failed.' }
& py -3 (Join-Path $PSScriptRoot 'tools\make_patch_manifest.py') `
    --source $source --patched $patched --output $manifest
if ($LASTEXITCODE -ne 0) { throw 'The patch manifest build failed.' }

$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) {
    throw 'The .NET Framework C# compiler was not found.'
}
& $compiler /nologo /target:winexe /platform:x86 `
    "/out:$setup" "/resource:$manifest,ProjectEdenPatchManifest" `
    /reference:System.Windows.Forms.dll /reference:System.Drawing.dll `
    (Join-Path $PSScriptRoot 'installer\Program.cs')
if ($LASTEXITCODE -ne 0) { throw 'The installer build failed.' }
Write-Output "Installer ready: $setup"
