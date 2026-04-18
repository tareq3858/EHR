$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('C:\Users\tareq\OneDrive\Desktop\Meditech EHR.lnk')
$sc.TargetPath = 'C:\Users\tareq\OneDrive\Desktop\Claud project dump\EHR\start_meditech.bat'
$sc.WorkingDirectory = 'C:\Users\tareq\OneDrive\Desktop\Claud project dump\EHR'
$sc.IconLocation = 'C:\Windows\System32\imageres.dll,80'
$sc.Description = 'Launch Meditech EHR'
$sc.Save()
Write-Host 'Shortcut created on Desktop.'
