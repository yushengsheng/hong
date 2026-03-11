Option Explicit

Dim shell
Dim fso
Dim baseDir
Dim pythonwPath
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)

pythonwPath = ""

If fso.FileExists(baseDir & "\.venv\Scripts\pythonw.exe") Then
    pythonwPath = baseDir & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\miniconda3\pythonw.exe") Then
    pythonwPath = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\miniconda3\pythonw.exe"
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python313\pythonw.exe") Then
    pythonwPath = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python313\pythonw.exe"
End If

If pythonwPath = "" Then
    MsgBox "未找到 pythonw.exe。" & vbCrLf & vbCrLf & _
        "请先安装 Python，或先创建本地 .venv 环境。", _
        vbCritical, "宏录制器"
    WScript.Quit 1
End If

command = Chr(34) & pythonwPath & Chr(34) & " " & Chr(34) & baseDir & "\launch.pyw" & Chr(34)
shell.Run command, 0, False
