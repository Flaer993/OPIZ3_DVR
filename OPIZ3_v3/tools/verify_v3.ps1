$ErrorActionPreference='Stop'
$d='C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist'
Add-Type -Path "$d\SolidWorks.Interop.sldworks.dll"
Add-Type -Path "$d\SolidWorks.Interop.swconst.dll"
$s=Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'verify_v3.cs')
Add-Type -TypeDefinition $s -ReferencedAssemblies "$d\SolidWorks.Interop.sldworks.dll","$d\SolidWorks.Interop.swconst.dll"
[VerifyV3]::Run((Split-Path (Split-Path $PSScriptRoot -Parent) -Parent))



