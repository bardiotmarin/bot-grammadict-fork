Set-Location $PSScriptRoot

Write-Output "=== Début du script launch_bot.ps1 ==="

Write-Output "Lancement de l'émulateur MEmu..."
Start-Process "D:\Program Files\Microvirt\MEmu\MEmu.exe" -ArgumentList "M4"

Write-Output "Attente de la connexion adb avec l'émulateur..."
$adbPath = Join-Path $PSScriptRoot "platform-tools\adb.exe"
$deviceId = "127.0.0.1:21523"
do {
    Start-Sleep -Seconds 5
    $devicesList = & $adbPath devices
    $connectedDevices = $devicesList | Select-Object -Skip 1 | ForEach-Object { $_.Trim().Split("`t")[0] } | Where-Object { $_ -ne "" }
} while (-not ($connectedDevices -contains $deviceId))

Write-Output "Emulator détecté: $deviceId"

$packageName = "com.github.uiautomator2"
Write-Output "Vérification du package $packageName..."
$check = & $adbPath -s $deviceId shell pm list packages | Select-String $packageName
if ($check) {
    Write-Output "Package $packageName trouvé, désinstallation en cours..."
    & $adbPath -s $deviceId uninstall $packageName
} else {
    Write-Output "Package $packageName non installé, pas de désinstallation."
}

# Met à jour le PATH pour utiliser python du venv
$venvScripts = Join-Path $PSScriptRoot ".venv\Scripts"
$env:PATH = "$venvScripts;$env:PATH"


Write-Output "Lancement du bot GramAddict via start_bot.bat..."
$scriptPath = Join-Path $PSScriptRoot "start_bot.bat"
$WshShell = New-Object -ComObject WScript.Shell
$WshShell.Run("cmd.exe /c `"$scriptPath`"", 0, $true)


Write-Output "Pause 10 secondes après lancement du bot..."
Start-Sleep -Seconds 10

Write-Output "=== Script terminé ==="
