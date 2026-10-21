' SPARK desktop launcher: runs start-spark.ps1 with no console window flash.
' Double-clicking the desktop shortcut invokes this file.
Option Explicit
Dim shell, fso, root, script, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(root, "scripts\launch-desktop.ps1")
If Not fso.FileExists(script) Then
    MsgBox "SPARK launcher could not find scripts\launch-desktop.ps1.", vbCritical, "SPARK"
    WScript.Quit 1
End If
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & script & """"
' 0 = hidden window; the Electron cockpit becomes the visible UI.
shell.Run cmd, 0, False
