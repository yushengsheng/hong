Option Explicit

Dim shell
Dim fso
Dim baseDir
Dim pythonwPath
Dim launcherArgs
Dim command

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)

pythonwPath = ""
launcherArgs = ""

If fso.FileExists(baseDir & "\.venv\Scripts\pythonw.exe") Then
    pythonwPath = baseDir & "\.venv\Scripts\pythonw.exe"
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\miniconda3\pythonw.exe") Then
    pythonwPath = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\miniconda3\pythonw.exe"
ElseIf fso.FileExists(shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python313\pythonw.exe") Then
    pythonwPath = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python313\pythonw.exe"
Else
    pythonwPath = FindOnPath("pyw.exe")
    If pythonwPath <> "" Then
        launcherArgs = " -3"
    Else
        pythonwPath = FindOnPath("pythonw.exe")
        If pythonwPath = "" Then
            pythonwPath = FindOnPath("py.exe")
            If pythonwPath <> "" Then
                launcherArgs = " -3"
            Else
                pythonwPath = FindOnPath("python.exe")
            End If
        End If
    End If
End If

If pythonwPath = "" Then
    MsgBox "未找到 pythonw.exe。" & vbCrLf & vbCrLf & _
        "请先安装 Python，或先创建本地 .venv 环境。" & vbCrLf & _
        "也可以确认 py/pythonw 是否已加入 PATH。", _
        vbCritical, "宏录制器"
    WScript.Quit 1
End If

command = Quote(pythonwPath) & launcherArgs & " " & Quote(baseDir & "\launch.pyw")
shell.Run command, 0, False

Function FindOnPath(fileName)
    Dim exec
    Dim commandLine
    Dim line

    commandLine = Quote(shell.ExpandEnvironmentStrings("%ComSpec%")) & " /c where " & fileName

    On Error Resume Next
    Set exec = shell.Exec(commandLine)
    If Err.Number <> 0 Then
        FindOnPath = ""
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If
    On Error GoTo 0

    Do While exec.Status = 0
        WScript.Sleep 10
    Loop

    If exec.ExitCode <> 0 Then
        FindOnPath = ""
        Exit Function
    End If

    line = ""
    If Not exec.StdOut.AtEndOfStream Then
        line = Trim(exec.StdOut.ReadLine())
    End If
    FindOnPath = line
End Function

Function Quote(value)
    Quote = Chr(34) & value & Chr(34)
End Function
