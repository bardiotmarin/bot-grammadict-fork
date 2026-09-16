<#
    watchdog_vm.ps1 - Filet de reconciliation des VMs MEmu.

    Probleme resolu
    ---------------
    run_session_loop.ps1 eteint la VM dans un bloc finally. Or ce bloc n'est PAS
    execute quand le process meurt sans preavis, et c'est justement ce qui
    arrive :
      - la tache planifiee se fait arreter de l'exterieur
        (LastTaskResult = 0xC000013A, STATUS_CONTROL_C_EXIT) : aucun finally,
        aucune ligne de log -- le journal s'arrete net sur "Arret de la VM" ;
      - le PC plante (constate le 10/09 : Kernel-Power 41 + dump memoire).
    Resultat : la VM tourne des heures dans le vide et rien ne travaille.

    Aucune correction interne a l'orchestrateur ne peut couvrir ce cas : elle
    supposerait que le process survit assez longtemps pour se rattraper. D'ou ce
    tiers, qui ne partage ni le sort ni la memoire de l'orchestrateur.

    Fonctionnement
    --------------
    run_session_loop.ps1 depose logs\.vm_owned_<compte>.json avant de demarrer
    une VM, et le supprime quand il l'a arretee. Si un marqueur subsiste alors
    que son proprietaire n'existe plus, la VM est orpheline : on l'eteint et on
    nettoie. Le marqueur etant sur le disque, cela vaut aussi apres un
    redemarrage du PC.

    Ne touche JAMAIS une VM dont le proprietaire est vivant, ni une VM demarree
    a la main (sans marqueur, elle est ignoree).
#>

[CmdletBinding()]
param(
    # Delai de courtoisie avant de declarer un marqueur orphelin, pour ne pas
    # entrer en course avec un orchestrateur qui vient tout juste de demarrer.
    [int]    $GraceMinutes = 2,
    [switch] $DryRun
)

Set-Location $PSScriptRoot

$LogDir  = Join-Path $PSScriptRoot "logs"
$LogFile = Join-Path $LogDir "watchdog_vm.log"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch { }
}

# Meme precaution que dans l'orchestrateur : memuc ecrit sur stderr des choses
# parfaitement normales, il ne faut pas que cela devienne une erreur terminante.
function Invoke-Native {
    param([string]$FilePath, [string[]]$Arguments)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        $out = ((& $FilePath @Arguments 2>$null | Out-String) -replace "`r`n", "`n" -replace "`r", "`n").Trim()
        return [pscustomobject]@{ Output = $out; ExitCode = $LASTEXITCODE }
    } catch {
        return [pscustomobject]@{ Output = ""; ExitCode = -1 }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Test-VmRunning {
    param([string]$MemucPath, [int]$VmIndex)
    $out = (Invoke-Native -FilePath $MemucPath -Arguments @("isvmrunning", "-i", "$VmIndex")).Output
    return @{
        Running = ($out -match "(?i)\bRunning\b" -and $out -notmatch "(?i)Not\s+Running")
        State   = $out
    }
}

# Le PID seul ne suffit pas : Windows recycle les numeros de process. On verifie
# donc que le PID correspond encore a un interpreteur PowerShell. On n'exige pas
# que sa ligne de commande contienne run_session_loop, afin de ne pas conclure a
# l'abandon quand quelqu'un lance l'orchestrateur a la main depuis une console.
function Test-OwnerAlive {
    param($OwnerPid)
    if (-not $OwnerPid) { return $false }
    try {
        $p = Get-Process -Id ([int]$OwnerPid) -ErrorAction Stop
        return ($p.ProcessName -in @("powershell", "pwsh", "powershell_ise"))
    } catch {
        return $false
    }
}

function Stop-OrphanVm {
    param([string]$MemucPath, [int]$VmIndex)

    if (-not (Test-Path $MemucPath)) {
        Write-Log "  memuc introuvable ($MemucPath), impossible d'arreter la VM $VmIndex." "ERROR"
        return $false
    }

    $st = Test-VmRunning -MemucPath $MemucPath -VmIndex $VmIndex
    if (-not $st.Running) {
        Write-Log "  VM $VmIndex deja eteinte, rien a arreter (etat: $($st.State))."
        return $true
    }

    if ($DryRun) {
        Write-Log "  [DRYRUN] j'arreterais la VM $VmIndex (etat: $($st.State))." "WARN"
        return $true
    }

    Write-Log "  Arret de la VM orpheline $VmIndex ..." "WARN"
    Invoke-Native -FilePath $MemucPath -Arguments @("stop", "-i", "$VmIndex") | Out-Null

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        if (-not (Test-VmRunning -MemucPath $MemucPath -VmIndex $VmIndex).Running) {
            Write-Log "  VM $VmIndex arretee."
            return $true
        }
    }

    # Comme dans l'orchestrateur : on ne touche qu'a la VM, pas a MEmuConsole
    # (le gestionnaire d'instances), dont la mort gene le demarrage suivant.
    Write-Log "  La VM $VmIndex ignore memuc stop, arret force des process MEmu." "WARN"
    foreach ($n in @("MEmu", "MEmuHeadless")) {
        Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    return $true
}

# ------------------------------------------------------------------ execution

try {
    $markers = @(Get-ChildItem -Path (Join-Path $LogDir ".vm_owned_*.json") -ErrorAction SilentlyContinue)

    if ($markers.Count -eq 0) {
        # Cas nominal et silencieux : aucune VM revendiquee. On ne journalise
        # rien pour ne pas noyer le log sous un passage toutes les 15 min.
        exit 0
    }

    foreach ($m in $markers) {
        $info = $null
        try {
            $info = Get-Content $m.FullName -Raw -ErrorAction Stop | ConvertFrom-Json
        } catch {
            Write-Log "Marqueur illisible ($($m.Name)) : $($_.Exception.Message). Suppression." "WARN"
            if (-not $DryRun) { Remove-Item $m.FullName -Force -ErrorAction SilentlyContinue }
            continue
        }

        $account = if ($info.Account) { $info.Account } else { "?" }

        if (Test-OwnerAlive -OwnerPid $info.OwnerPid) {
            # Un orchestrateur bloque n'est pas traite ici : le tuer serait plus
            # dangereux que de le laisser finir. On le rend simplement visible.
            $ageHours = $null
            try { $ageHours = ((Get-Date) - [datetime]$info.StartedAt).TotalHours } catch { }
            if ($null -ne $ageHours -and $ageHours -gt 6) {
                Write-Log "$account : VM $($info.VmIndex) revendiquee depuis $([int]$ageHours)h par le PID $($info.OwnerPid), toujours vivant. A surveiller." "WARN"
            }
            continue
        }

        # Delai de courtoisie : un marqueur tout juste ecrit dont on ne voit pas
        # encore le proprietaire ne doit pas etre pris pour un abandon.
        try {
            $ageMin = ((Get-Date) - [datetime]$info.StartedAt).TotalMinutes
            if ($ageMin -lt $GraceMinutes) {
                Write-Log "$account : marqueur vieux de $([int]$ageMin) min, proprietaire pas encore visible. On repasse plus tard."
                continue
            }
        } catch { }

        Write-Log "$account : ORPHELINE -- le proprietaire (PID $($info.OwnerPid)) n'existe plus, VM $($info.VmIndex) allumee pour rien." "WARN"

        $memuc = if ($info.MemucPath) { $info.MemucPath } else { "D:\Program Files\Microvirt\MEmu\memuc.exe" }
        if (Stop-OrphanVm -MemucPath $memuc -VmIndex ([int]$info.VmIndex)) {
            if ($DryRun) {
                Write-Log "  [DRYRUN] je supprimerais le marqueur $($m.Name)."
            } else {
                Remove-Item $m.FullName -Force -ErrorAction SilentlyContinue
                Write-Log "  Marqueur libere. La prochaine execution de la tache repartira sur une VM propre."
            }
        }
    }
} catch {
    Write-Log "Erreur inattendue du watchdog : $($_.Exception.Message)" "ERROR"
    exit 1
}

exit 0
