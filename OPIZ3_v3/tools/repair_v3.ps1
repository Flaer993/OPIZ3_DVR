$ErrorActionPreference='Stop'
$dir='C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist'
Add-Type -Path "$dir\SolidWorks.Interop.sldworks.dll"
Add-Type -Path "$dir\SolidWorks.Interop.swconst.dll"
$src=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'build_v3.cs')
Add-Type -TypeDefinition $src -ReferencedAssemblies "$dir\SolidWorks.Interop.sldworks.dll","$dir\SolidWorks.Interop.swconst.dll"
[CaseV3]::RepairHousing((Split-Path (Split-Path $PSScriptRoot -Parent) -Parent))


