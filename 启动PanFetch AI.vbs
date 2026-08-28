Option Explicit

Dim shell, fileSystem, projectRoot, pythonwPath, exePath, command
Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")
projectRoot = fileSystem.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = projectRoot
pythonwPath = projectRoot & "\.venv\Scripts\pythonw.exe"
exePath = projectRoot & "\dist\PanFetch AI.exe"

If fileSystem.FileExists(pythonwPath) And fileSystem.FolderExists(projectRoot & "\panfetch_ai") Then
    command = Chr(34) & pythonwPath & Chr(34) & " -m panfetch_ai"
    shell.Run command, 1, False
ElseIf fileSystem.FileExists(exePath) Then
    shell.Run Chr(34) & exePath & Chr(34), 1, False
Else
    command = "cmd.exe /d /c " & Chr(34) & projectRoot & "\launch_panfetch_ai.cmd" & Chr(34) & " --silent"
    shell.Run command, 0, False
End If
