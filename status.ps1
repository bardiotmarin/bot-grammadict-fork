<#
    status.ps1 - Etat en un coup d'oeil de l'orchestrateur et du bot.
    Aucune action, lecture seule. Usage : powershell -File status.ps1
#>
param([string]$Account, [int]$VmIndex = 2)

# Le compte n'est pas code en dur (il ne doit pas figurer dans le depot) : a
# defaut d'argument, on le relit dans la tache planifiee qui lance l'orchestrateur.
if (-not $Account) {
    $act = (Get-ScheduledTask -TaskName "memu-m4" -ErrorAction SilentlyContinue).Actions |
           Select-Object -First 1
    if ($act.Arguments -match '-Account\s+(\S+)') { $Account = $Matches[1] }
}
if (-not $Account) { Write-Host "Usage : status.ps1 -Account <compte>"; exit 1 }

$ErrorActionPreference = "SilentlyContinue"
$root   = $PSScriptRoot
$logDir = Join-Path $root "logs"
$today  = Get-Date -Format "yyyy-MM-dd"
$loop   = Join-Path $logDir "session_loop_${Account}_${today}.log"
$memuc  = "D:\Program Files\Microvirt\MEmu\memuc.exe"

function Line($k, $v) { "{0,-22}{1}" -f $k, $v }

Write-Host ""
Write-Host "  ETAT DU BOT - $Account" -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'dddd dd MMMM HH:mm:ss')"
Write-Host ("  " + ("-" * 60))

# --- La tache tourne-t-elle ?
$task = Get-ScheduledTask -TaskName "memu-m4"
$info = Get-ScheduledTaskInfo -TaskName "memu-m4"
$orch = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -like "*run_session_loop*" }
$vm   = (& $memuc isvmrunning -i $VmIndex 2>$null | Out-String).Trim()
$bot  = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*run.py*" }

Write-Host (Line "  Tache planifiee" $task.State)
Write-Host (Line "  Orchestrateur" $(if ($orch) { "actif (PID $($orch.ProcessId -join ','))" } else { "arrete" }))
Write-Host (Line "  VM MEmu" $vm)
Write-Host (Line "  Bot" $(if ($bot) { "EN TRAIN DE TOURNER" } else { "en pause" }))
Write-Host ""

if (-not (Test-Path $loop)) {
    Write-Host "  Aucune activite enregistree aujourd'hui." -ForegroundColor Yellow
    Write-Host ""
    return
}
$c = Get-Content $loop

# --- Ou en est-on dans la journee ?
$obj  = ($c | Select-String 'Objectif du jour: (\d+)' | Select-Object -Last 1)
$cur  = ($c | Select-String 'Session (\d+)/(\d+) - profil (\w+)' | Select-Object -Last 1)
$next = ($c | Select-String 'Prochaine session vers (\d\d:\d\d)' | Select-Object -Last 1)
$wait = ($c | Select-String 'premiere session vers (\d\d:\d\d)' | Select-Object -Last 1)

if ($obj.Line  -match 'Objectif du jour: (\d+)')            { Write-Host (Line "  Sessions prevues" $Matches[1]) }
if ($cur.Line  -match 'Session (\d+)/(\d+) - profil (\w+)') { Write-Host (Line "  Session en cours" "$($Matches[1])/$($Matches[2]) - profil $($Matches[3])") }
if ($bot) {
    Write-Host (Line "  Prochaine session" "apres celle-ci")
} elseif ($next.Line -match 'Prochaine session vers (\d\d:\d\d)') {
    Write-Host (Line "  Prochaine session" "$($Matches[1])")
} elseif ($wait.Line -match 'premiere session vers (\d\d:\d\d)') {
    Write-Host (Line "  Premiere session" "$($Matches[1]) (il patiente)")
}
Write-Host ""

# --- Travail reellement produit aujourd'hui
$likes = 0; $comments = 0; $inter = 0; $n = 0
Get-ChildItem (Join-Path $logDir "bot_${Account}_$(Get-Date -Format 'yyyyMMdd')_*.err.log") | ForEach-Object {
    $e = Get-Content $_.FullName
    $likes    += ($e | Select-String 'Liking post\.\.\.|Like button clicked successfully|Double clicked media to like').Count
    $comments += ($e | Select-String 'Write comment').Count
    $inter    += ($e | Select-String ': interact$').Count
    $n++
}
Write-Host "  TRAVAIL DU JOUR" -ForegroundColor Green
Write-Host (Line "  Sessions jouees" $n)
Write-Host (Line "  Likes" $likes)
Write-Host (Line "  Commentaires" $comments)
Write-Host (Line "  Profils interagis" $inter)
Write-Host ""

# --- Incidents
$rec   = ($c | Select-String 'RECOVERY').Count
$crash = ($c | Select-String 'CRASH TECHNIQUE|SESSION INTERROMPUE').Count
$retry = ($c | Select-String 'Nouvelle tentative').Count
if ($rec -or $crash -or $retry) {
    Write-Host "  INCIDENTS (rattrapes automatiquement)" -ForegroundColor Yellow
    if ($rec)   { Write-Host (Line "  Recuperations" $rec) }
    if ($crash) { Write-Host (Line "  Sessions ecourtees" $crash) }
    if ($retry) { Write-Host (Line "  Relances" $retry) }
    Write-Host ""
}

Write-Host "  Detail complet :" -ForegroundColor DarkGray
Write-Host "    Get-Content '$loop' -Tail 30" -ForegroundColor DarkGray
Write-Host ""
