$ErrorActionPreference='Stop'
$d='C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist'
Add-Type -Path "$d\SolidWorks.Interop.sldworks.dll"
Add-Type -Path "$d\SolidWorks.Interop.swconst.dll"
$s=@'
using System;using System.IO;using SolidWorks.Interop.sldworks;using SolidWorks.Interop.swconst;
public class InspectTFT {public static void Run(string root,string path){var sw=(SldWorks)Activator.CreateInstance(Type.GetTypeFromProgID("SldWorks.Application.32"));sw.Visible=true;sw.SetUserPreferenceStringValue((int)swUserPreferenceStringValue_e.swDefaultTemplatePart,"C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2024\\templates\\gost-part.prtdot");sw.SetUserPreferenceStringValue((int)swUserPreferenceStringValue_e.swDefaultTemplateAssembly,"C:\\ProgramData\\SOLIDWORKS\\SOLIDWORKS 2024\\templates\\gost-assy.asmdot");sw.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swMultiCAD_Enable3DInterconnect,false);int e=0,w=0;var m=(ModelDoc2)sw.LoadFile4(path,"r",sw.GetImportFileData(path),ref e);if(m==null)throw new Exception("Import failed code="+e+" path="+path);Console.WriteLine("Import="+e+" type="+m.GetType()+" title="+m.GetTitle());if(m.GetType()!=1)throw new Exception("Assembly import");Directory.CreateDirectory(Path.Combine(root,"OPIZ3_v3"));m.Extension.SaveAs(Path.Combine(root,"OPIZ3_v3","REF_TFT_exact.SLDPRT"),0,1,null,ref e,ref w);Console.WriteLine("Save="+e);var bs=(object[])((PartDoc)m).GetBodies2(0,false);foreach(Body2 b in bs){Console.WriteLine("BODY "+b.Name+" BOX "+String.Join(",",(double[])b.GetBodyBox()));foreach(Face2 f in (object[])b.GetFaces()){var s=(Surface)f.GetSurface();if(s.IsCylinder()){var p=(double[])s.CylinderParams;if(p[6]>0.001)Console.WriteLine("CYL "+String.Join(",",p));}}}m.ShowNamedView2("*Isometric",7);m.ViewZoomtofit2();m.Extension.SaveAs(Path.Combine(root,"OPIZ3_v3","tft_import.png"),0,1,null,ref e,ref w);}}
'@
Add-Type -TypeDefinition $s -ReferencedAssemblies "$d\SolidWorks.Interop.sldworks.dll","$d\SolidWorks.Interop.swconst.dll"
[InspectTFT]::Run((Split-Path (Split-Path $PSScriptRoot -Parent) -Parent),(Join-Path $PSScriptRoot 'display_reference.stp'))






