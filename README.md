# Project Eden Unofficial Patch

A patch for the GOG Project Eden `Eden.exe` version 1.0.0.2. It patches the
existing GOG installation and saves the original as `Eden.exe.original`.
Game files and generated executables are not included in this repository.

## Install

1. Download `ProjectEdenUnofficialSetup.exe` from the [latest release](https://github.com/PottedSalame/Project_Eden-Unofficial_Patch/releases/latest). No Python is needed.
2. Close the game, run setup, select the GOG folder containing `Eden.exe`, and click **Install**.
3. Launch the game normally. To undo the patch, close the game and copy `Eden.exe.original` over `Eden.exe`.

To verify the download, compare its SHA-256 with the release's `SHA256SUMS.txt`.

## Features

- Windowed and borderless modes in **Graphics Settings**, with saved mode,
  window size, and position.
- Aspect-correct scaling with black bars when the window or monitor ratio
  differs from the game image.
- Alt+Tab, mouse capture, and window dragging that work in the patched modes.
- **Startup Movies: ON/OFF** in the main **Options** menu. The choice is saved
  and takes effect on the next launch. It affects only `Logos.mpg` and
  `Eden_Int.mpg` when those files are present.

Settings are stored in `ProjectEdenPatch.ini` beside the patched executable.

## Build the installer

Requires Python 3 and the Windows .NET Framework compiler:

```powershell
$gameDir = 'C:\Games\Project Eden'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Build-Installer.ps1 `
  -GameDirectory $gameDir
```

The installer verifies the original executable, backs it up, and patches it
in place. Existing saves and other game files are left alone.

The build also writes `build/SHA256SUMS.txt`. Compare its SHA-256 with the
checksum published alongside the release executable. To verify the release
from source, build its tag with the same GOG game, .NET Framework compiler,
and reference assemblies. The build normalizes the PE timestamp and .NET
module ID so repeated builds with the same inputs match.

## Development

`patch.py` verifies the source executable's SHA-256 and exact patch bytes.
`extension.bin` is the generated code section used by the patcher. To rebuild
it, install `keystone-engine` and run
`python .\tools\assemble_extension.py`.

For a separate local test install, run `patch.py` with a `test-install/Eden.exe`
output, then `prepare-test.ps1 -GameDirectory $gameDir`. Launch the game from
`test-install/` so its relative asset paths resolve.
