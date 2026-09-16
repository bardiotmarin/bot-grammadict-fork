<#
    run_session_loop.ps1 - Orchestrateur de sessions GramAddict sur MEmu.

    Lance par le Planificateur de taches Windows a l'ouverture de session.
    Pour chaque session de la journee :
        start VM -> attente boot complet -> bot (1 session) -> stop VM -> pause aleatoire

    Le process du bot n'est JAMAIS tue en cours de route (sauf -HardTimeoutMinutes > 0).
    La variation "sessions longues / courtes" se fait en surchargeant les limites
    d'interaction en ligne de commande : configargparse donne la priorite a la CLI
    sur le fichier config.yml, qui n'est donc jamais modifie.

    Un compte = une VM = une tache planifiee. Tout est parametre, rien n'est code en dur.
#>

[CmdletBinding()]
param(
    # Obligatoire : le nom du compte ne doit pas figurer dans le depot. La tache
    # planifiee le passe en argument (-Account).
    [Parameter(Mandatory = $true)]
    [string] $Account,
    [int]    $VmIndex            = 2,
    [string] $DeviceId           = "127.0.0.1:21523",
    [string] $MemucPath          = "D:\Program Files\Microvirt\MEmu\memuc.exe",

    [int]    $MinSessions        = 3,
    [int]    $MaxSessions        = 5,
    # Les sessions durent desormais 60-100 min (le correctif decorators.py les
    # empeche de mourir au premier incident reseau). Avec des pauses de 100-210
    # min par-dessus, le bot passait plus de temps a attendre qu'a travailler.
    [int]    $MinGapMinutes      = 25,
    [int]    $MaxGapMinutes      = 60,

    [string] $WorkStart          = "00:00",
    [string] $WorkEnd            = "23:59",

    # Doit rester aligne avec MODEL_NAME dans GramAddict/core/ai_commenter.py
    [string] $AiModel            = "gemma3:12b",
    [string] $OllamaUrl          = "http://localhost:11434",

    [int]    $BootTimeoutMinutes = 6,
    # Filet anti-boucle : avec total-crashes-limit a 500, une session peut
    # theoriquement enchainer des centaines de redemarrages sans jamais rendre
    # la main. Au-dela de 3h une session n'a plus rien de normal.
    [int]    $HardTimeoutMinutes = 180,
    [int]    $MaxRetriesPerSession = 3,
    [int]    $MinRetryGapMinutes   = 20,
    [int]    $MaxRetryGapMinutes   = 40,

    [switch] $DryRun,
    [switch] $TestRun
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python  = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$Adb     = Join-Path $PSScriptRoot "platform-tools\adb.exe"
$LogDir  = Join-Path $PSScriptRoot "logs"
$LogFile = Join-Path $LogDir ("session_loop_{0}_{1}.log" -f $Account, (Get-Date -Format "yyyy-MM-dd"))
$VmMarker = Join-Path $LogDir (".vm_owned_{0}.json" -f $Account)

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# ---------------------------------------------------------------- utilitaires

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    # Write-Host et non Write-Output : Write-Output injecterait chaque ligne de log
    # dans le pipeline de sortie de la fonction appelante, ce qui corromprait sa
    # valeur de retour (un "return $false" deviendrait un tableau non vide = truthy).
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# Les .exe natifs (adb, memuc) ecrivent sur stderr des messages parfaitement
# normaux ("device offline" pendant le boot). Sous PowerShell 5.1, la combinaison
# $ErrorActionPreference = "Stop" + redirection 2>&1 transforme CHAQUE ligne de
# stderr en erreur terminante. Ces deux wrappers isolent les appels natifs :
# stderr est jete, la sortie reste propre, et on lit le code de retour.
function Invoke-Native {
    param([string]$FilePath, [string[]]$Arguments)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $global:LASTEXITCODE = 0
        # adb renvoie des fins de ligne CRLF : le CR residuel fait echouer les
        # ancrages "$" des expressions regulieres cote PowerShell. On normalise
        # ici, une fois pour toutes, plutot que dans chaque appelant.
        $out = ((& $FilePath @Arguments 2>$null | Out-String) -replace "`r`n", "`n" -replace "`r", "`n").Trim()
        return [pscustomobject]@{ Output = $out; ExitCode = $LASTEXITCODE }
    } catch {
        return [pscustomobject]@{ Output = ""; ExitCode = -1 }
    } finally {
        $ErrorActionPreference = $prev
    }
}

# Les arguments sont passes explicitement en tableau nommme : en positionnel,
# PowerShell tenterait de lier "-i" ou "-s" aux parametres communs de la fonction
# (-InformationAction, -InformationVariable...) au lieu de les transmettre a l'exe.
function Invoke-Adb {
    param([Parameter(Mandatory = $true)][string[]]$AdbArgs)
    return Invoke-Native -FilePath $Adb -Arguments $AdbArgs
}

function Invoke-Memuc {
    param([Parameter(Mandatory = $true)][string[]]$MemucArgs)
    return Invoke-Native -FilePath $MemucPath -Arguments $MemucArgs
}

function Test-Prerequisites {
    $missing = @()
    foreach ($p in @($Python, $Adb, $MemucPath)) {
        if (-not (Test-Path $p)) { $missing += $p }
    }
    $cfg = Join-Path $PSScriptRoot "accounts\$Account\config.yml"
    if (-not (Test-Path $cfg)) { $missing += $cfg }
    if ($missing.Count -gt 0) {
        foreach ($m in $missing) { Write-Log "Introuvable: $m" "ERROR" }
        throw "Prerequis manquants, abandon."
    }
    Write-Log "Prerequis OK (python, adb, memuc, config)."
}

function Test-InsideWorkingHours {
    $now   = (Get-Date).TimeOfDay
    $start = [TimeSpan]::Parse($WorkStart)
    $end   = [TimeSpan]::Parse($WorkEnd)
    if ($start -le $end) { return ($now -ge $start -and $now -le $end) }
    # plage a cheval sur minuit
    return ($now -ge $start -or $now -le $end)
}

function Wait-ForWorkingHours {
    # "Trop tot" et "trop tard" ne sont PAS le meme cas. Le PC est souvent allume
    # avant l'ouverture de la plage : abandonner la journee a ce moment-la revient
    # a ne rien faire du tout, car le declencheur d'ouverture de session ne se
    # representera pas. On patiente donc jusqu'a l'heure d'ouverture.
    # Apres la fermeture, en revanche, il n'y a plus rien a attendre.
    if (Test-InsideWorkingHours) { return $true }

    $now   = (Get-Date).TimeOfDay
    $start = [TimeSpan]::Parse($WorkStart)
    $end   = [TimeSpan]::Parse($WorkEnd)

    if (($start -le $end) -and ($now -lt $start)) {
        # Petit decalage aleatoire pour ne pas demarrer pile a l'heure ronde tous
        # les jours -- mais borne a quelques minutes : attendre 25 min de plus
        # alors que la plage ouvre dans 6 min ne sert a rien.
        $jitter = Get-Random -Minimum 0 -Maximum 6
        $wait   = [int]($start - $now).TotalMinutes + $jitter
        $at     = (Get-Date).AddMinutes($wait).ToString("HH:mm")
        Write-Log "Trop tot pour commencer. Attente de $wait min, premiere session vers $at."
        Start-Sleep -Seconds ($wait * 60)
        return $true
    }

    Write-Log "Hors plage horaire ($WorkStart-$WorkEnd), plus rien a faire aujourd'hui."
    return $false
}

function Invoke-Pause {
    param([int]$Min, [int]$Max, [string]$Motif)
    $gap  = Get-Random -Minimum $Min -Maximum ($Max + 1)
    $next = (Get-Date).AddMinutes($gap)
    if ($next.TimeOfDay -gt [TimeSpan]::Parse($WorkEnd)) {
        Write-Log "La reprise tomberait a $($next.ToString('HH:mm')), hors plage. Fin de la journee."
        return $false
    }
    Write-Log "$Motif : $gap min, reprise vers $($next.ToString('HH:mm'))."
    Start-Sleep -Seconds ($gap * 60)
    return $true
}

function Start-ModelPreload {
    # Le tout premier appel a Ollama paie le chargement du modele sur le GPU
    # (~290s mesurees pour gemma3:12b). Sans cela, c'est le premier commentaire
    # de la session qui l'encaisse. On le declenche en tache de fond AVANT de
    # demarrer la VM : le modele se charge pendant le boot et la stabilisation,
    # donc le cout est masque. keep_alive=24h le garde ensuite resident.
    try {
        $ps = Invoke-RestMethod "$OllamaUrl/api/ps" -TimeoutSec 8 -ErrorAction Stop
        if ($ps.models | Where-Object { $_.name -eq $AiModel }) {
            Write-Log "Modele $AiModel deja resident, rien a precharger."
            return
        }
    } catch {
        Write-Log "Ollama injoignable : l'AI Commenter retombera sur comments_list.txt." "WARN"
        return
    }

    Write-Log "Prechargement de $AiModel en tache de fond (masque par le boot de la VM)..."
    $body = '{"model":"' + $AiModel + '","prompt":"hi","stream":false,"keep_alive":"24h","options":{"num_predict":1}}'
    $cmd  = "try { Invoke-RestMethod '$OllamaUrl/api/generate' -Method POST -Body '$body' -ContentType 'application/json' -TimeoutSec 900 | Out-Null } catch {}"
    Start-Process powershell.exe -ArgumentList "-NoProfile", "-WindowStyle", "Hidden", "-Command", $cmd -WindowStyle Hidden
}

function Test-DiskSpace {
    # Un disque plein fait echouer les ecritures (PermissionError WinError 5 du
    # 27/08) et destabilise MEmu comme adb. Inutile de lancer une session dans
    # ces conditions : on prefere attendre que de la place se libere.
    param([int]$MinimumGo = 3)
    foreach ($d in @("C","D")) {
        $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${d}:'" -ErrorAction SilentlyContinue
        if (-not $disk) { continue }
        $go = [math]::Round($disk.FreeSpace / 1GB, 1)
        if ($go -lt $MinimumGo) {
            Write-Log "Disque ${d}: n'a plus que $go Go libres (minimum $MinimumGo). Session reportee." "ERROR"
            return $false
        }
        if ($go -lt ($MinimumGo * 3)) {
            Write-Log "Attention: disque ${d}: a seulement $go Go libres." "WARN"
        }
    }
    return $true
}

function Invoke-LogRotation {
    # Sans purge, le dossier logs atteint plus de 1600 fichiers en une semaine.
    param([int]$JoursConserves = 7)
    $limite = (Get-Date).AddDays(-$JoursConserves)
    $n = 0; $mo = 0.0
    # On derive de $LogDir plutot que de $PSScriptRoot : une seule source de
    # verite pour la racine du projet.
    foreach ($dir in @($LogDir, (Join-Path (Split-Path $LogDir -Parent) "crashes"))) {
        if (-not (Test-Path $dir)) { continue }
        foreach ($f in @(Get-ChildItem $dir -File -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt $limite })) {
            try { $mo += $f.Length / 1MB; [System.IO.File]::Delete($f.FullName); $n++ } catch {}
        }
    }
    if ($n -gt 0) { Write-Log ("Rotation: {0} fichier(s) de plus de {1} jours supprimes ({2:N0} Mo)." -f $n, $JoursConserves, $mo) }
}

function Wait-ForNetwork {
    # Sans connexion, Instagram ne charge rien : demarrer la VM et le bot
    # reviendrait a gaspiller la session (c'est ce qui s'est produit le 25/08,
    # 3 tentatives perdues sur une coupure Internet). On teste la resolution DNS
    # d'instagram.com, qui valide a la fois le DNS et l'acces reseau.
    $deadline = (Get-Date).AddMinutes(15)
    $prevenu  = $false
    while ((Get-Date) -lt $deadline) {
        try {
            [void][System.Net.Dns]::GetHostEntry("instagram.com")
            if ($prevenu) { Write-Log "Connexion Internet retablie." }
            return $true
        } catch {
            if (-not $prevenu) {
                Write-Log "Pas de connexion Internet : on patiente au lieu de gaspiller la session." "WARN"
                $prevenu = $true
            }
            Start-Sleep -Seconds 60
        }
    }
    Write-Log "Toujours pas de connexion apres 15 min, session reportee." "ERROR"
    return $false
}

# --------------------------------------------------------------- pilotage VM

function Get-VmRunning {
    $out = (Invoke-Memuc -MemucArgs @("isvmrunning", "-i", "$VmIndex")).Output
    return ($out -match "(?i)\bRunning\b" -and $out -notmatch "(?i)Not\s+Running")
}

function Assert-MemuService {
    # MemuService.exe pilote les VMs MEmu. Il est cense demarrer avec Windows
    # (cle MEmuSVC du registre Run) mais ne le fait pas toujours : apres le
    # redemarrage du 29/08 il etait absent, et "memuc start" rendait la main
    # sans rien lancer -- la session restait bloquee 31 min sur "Demarrage de
    # la VM". On s'assure donc qu'il tourne avant de toucher a la VM.
    if (Get-Process -Name MemuService -ErrorAction SilentlyContinue) { return $true }

    $svc = Join-Path (Split-Path $MemucPath) "MemuService.exe"
    if (-not (Test-Path $svc)) {
        Write-Log "MemuService.exe introuvable ($svc) : la VM ne pourra pas demarrer." "ERROR"
        return $false
    }
    Write-Log "MemuService absent, demarrage..." "WARN"
    Start-Process $svc
    for ($i = 0; $i -lt 12; $i++) {
        Start-Sleep -Seconds 2
        if (Get-Process -Name MemuService -ErrorAction SilentlyContinue) {
            Write-Log "MemuService demarre."
            Start-Sleep -Seconds 3
            return $true
        }
    }
    Write-Log "MemuService n'a pas demarre." "ERROR"
    return $false
}

# Marqueur de propriete de la VM, relu par watchdog_vm.ps1.
#
# Raison d'etre : l'extinction de la VM ne peut PAS dependre de la survie de ce
# process. Un arret de tache (STATUS_CONTROL_C_EXIT) comme un plantage du PC
# (vu le 10/09, Kernel-Power 41) n'executent aucun bloc finally -- la VM restait
# alors allumee des heures sans que rien ne tourne. Le marqueur vit sur le
# disque : un tiers independant peut donc constater l'abandon et nettoyer, meme
# apres un redemarrage.
function Set-VmOwnership {
    try {
        [pscustomobject]@{
            Account   = $Account
            VmIndex   = $VmIndex
            DeviceId  = $DeviceId
            MemucPath = $MemucPath
            OwnerPid  = $PID
            StartedAt = (Get-Date).ToString("o")
        } | ConvertTo-Json -Compress | Set-Content -Path $VmMarker -Encoding UTF8
    } catch {
        Write-Log "Impossible d'ecrire le marqueur de VM: $($_.Exception.Message)" "WARN"
    }
}

function Clear-VmOwnership {
    try {
        if (Test-Path $VmMarker) { Remove-Item $VmMarker -Force -ErrorAction Stop }
    } catch {
        Write-Log "Impossible de supprimer le marqueur de VM: $($_.Exception.Message)" "WARN"
    }
}

function Start-Vm {
    if (-not (Assert-MemuService)) { return }
    # Le marqueur est pose AVANT le demarrage : si on mourait pendant le boot,
    # la VM serait deja allumee et personne ne saurait qu'elle est orpheline.
    Set-VmOwnership
    if (Get-VmRunning) {
        Write-Log "VM $VmIndex deja demarree, on la reutilise."
        return
    }
    Write-Log "Demarrage de la VM index $VmIndex ..."
    $out = (Invoke-Memuc -MemucArgs @("start", "-i", "$VmIndex")).Output
    if ($out) { Write-Log "memuc: $out" }
}

function Stop-Vm {
    Write-Log "Arret de la VM index $VmIndex ..."
    Invoke-Memuc -MemucArgs @("stop", "-i", "$VmIndex") | Out-Null

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if (-not (Get-VmRunning)) {
            Write-Log "VM arretee proprement."
            Clear-VmOwnership
            return
        }
        Start-Sleep -Seconds 5
    }

    Write-Log "La VM ne repond pas a memuc stop, arret force des process MEmu." "WARN"
    # MEmuConsole est le gestionnaire d'instances, pas la VM : le tuer n'aide pas
    # et gene le demarrage suivant. On ne touche qu'a la VM elle-meme.
    foreach ($n in @("MEmu", "MEmuHeadless")) {
        try {
            Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        } catch { }
    }
    Clear-VmOwnership
}

function Wait-VmReady {
    # Attend que la VM soit reellement utilisable : boot termine, animation de
    # demarrage finie, et gestionnaire de paquets qui repond (= home page prete).
    $deadline  = (Get-Date).AddMinutes($BootTimeoutMinutes)
    $lastState = ""
    Write-Log "Attente du boot complet (timeout $BootTimeoutMinutes min) ..."

    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        Invoke-Adb -AdbArgs @("connect", $DeviceId) | Out-Null

        # Etape 1 : le device doit etre en etat "device". Pendant le boot il passe
        # par "offline" puis "unauthorized" : ce sont des etats normaux, on attend.
        $devices = (Invoke-Adb -AdbArgs @("devices")).Output
        $state = "injoignable"
        if ($devices -match ([regex]::Escape($DeviceId) + '\s+(\S+)')) { $state = $Matches[1] }
        if ($state -ne "device") {
            if ($state -ne $lastState) { Write-Log "  adb: device $state, on attend..."; $lastState = $state }
            continue
        }

        # Etape 2 : boot Android termine
        $booted = (Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "getprop", "sys.boot_completed")).Output
        if ($booted -ne "1") {
            if ($lastState -ne "booting") { Write-Log "  adb: device en ligne, boot en cours..."; $lastState = "booting" }
            continue
        }

        # Etape 3 : animation de demarrage finie (= on arrive sur la home page).
        # MEmu ne declare PAS bootanim comme service init : "init.svc.bootanim"
        # y renvoie une chaine vide en permanence. C'est "service.bootanim.exit"
        # qui passe a 1. On accepte les deux pour rester valable sur un vrai
        # device ou un autre emulateur.
        $anim     = (Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "getprop", "init.svc.bootanim")).Output
        $animExit = (Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "getprop", "service.bootanim.exit")).Output
        if (($anim -ne "stopped") -and ($animExit -ne "1")) {
            if ($lastState -ne "bootanim") { Write-Log "  adb: boot OK, animation en cours..."; $lastState = "bootanim" }
            continue
        }

        # Etape 4 : le package manager repond et Instagram est bien installe
        $pkg = (Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "pm", "list", "packages", "com.instagram.android")).Output
        if ($pkg -notmatch "com\.instagram\.android") {
            if ($lastState -ne "pm") { Write-Log "  adb: home page OK, package manager pas encore pret..."; $lastState = "pm" }
            continue
        }

        # La VM repond, mais elle charge encore ses services en arriere-plan.
        # Lancer Instagram trop tot le fait partir en ANR ("isn't responding"),
        # et le bot abandonne apres 3 tentatives. D'ou une stabilisation large.
        $settle = Get-Random -Minimum 40 -Maximum 61
        Write-Log "Boot termine et Instagram present. Stabilisation ${settle}s avant lancement."
        Start-Sleep -Seconds $settle
        return $true
    }

    Write-Log "Timeout: la VM n'a pas fini de booter en $BootTimeoutMinutes min (dernier etat: $lastState)." "ERROR"
    return $false
}

function Reset-Uiautomator {
    # Les paquets s'appellent "com.github.uiautomator" et ".test" -- PAS
    # "com.github.uiautomator2" (nom herite de launch_bot.ps1, qui ne correspond
    # a rien : le nettoyage n'a donc jamais eu lieu). Consequence : l'agent
    # gardait son etat d'une session a l'autre, et une instrumentation cassee le
    # restait, d'ou les "am instrument ... Read timed out" a repetition.
    #
    # On force-stop plutot que desinstaller : c'est ce que faisait le watchdog,
    # c'est immediat, et uiautomator2 relance une instrumentation neuve derriere.
    foreach ($pkg in @("com.github.uiautomator", "com.github.uiautomator.test")) {
        $installed = (Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "pm", "list", "packages", $pkg)).Output
        # (?m) : "pm list packages com.github.uiautomator" renvoie DEUX lignes
        # (le paquet et son .test). Sans ancrage par ligne, seule la derniere
        # serait reconnue.
        if ($installed -match ("(?m)^package:" + [regex]::Escape($pkg) + "$")) {
            Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "am", "force-stop", $pkg) | Out-Null
            Write-Log "Agent $pkg arrete (instrumentation repartira a neuf)."
        } else {
            Write-Log "$pkg pas installe (uiautomator2 l'installera)."
        }
    }
    Start-Sleep -Seconds 2
}

# -------------------------------------------------- recuperation en session

$script:LastRecovery   = [datetime]::MinValue
$script:RecoveryTimes  = @()

function Test-RecoveryAllowed {
    # Trois relances a une minute d'intervalle ne reparent rien : le force-stop
    # retombe sur une application en train de demarrer et l'empeche d'aboutir
    # ("Unable to open Instagram"). On impose donc un repos entre deux tentatives,
    # et au-dela de 3 tentatives en 10 minutes on cesse d'insister : la session
    # est perdue, le retry global la rejouera sur une VM neuve.
    $now = Get-Date
    if (($now - $script:LastRecovery).TotalSeconds -lt 180) {
        Write-Log "  (recovery ignoree : moins de 3 min depuis la precedente)"
        return $false
    }
    $script:RecoveryTimes = @($script:RecoveryTimes | Where-Object { ($now - $_).TotalMinutes -lt 10 })
    if ($script:RecoveryTimes.Count -ge 3) {
        Write-Log "  3 recuperations en moins de 10 min : Instagram ne repart pas, on arrete d'insister." "WARN"
        return $false
    }
    return $true
}

function Invoke-ScreenRecovery {
    # Repris du watchdog : quand l'automatisation se coince, il ne suffit pas de
    # relancer atx-agent. L'app uiautomator elle-meme a besoin d'une nouvelle
    # session d'instrumentation, d'ou le force-stop des trois paquets.
    # Le bot python n'est JAMAIS tue ici : on remet juste l'ecran d'aplomb
    # sous ses pieds, et il repart tout seul.
    param([string]$Reason)
    Write-Log "  RECOVERY ($Reason): force-stop uiautomator + Instagram, relance." "WARN"
    $script:LastRecovery  = Get-Date
    $script:RecoveryTimes += (Get-Date)
    foreach ($p in @("com.github.uiautomator", "com.github.uiautomator.test", "com.instagram.android")) {
        Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "am", "force-stop", $p) | Out-Null
    }
    Start-Sleep -Seconds 2
    # Passer par HOME avant de relancer : MEmu glisse parfois une pub plein
    # ecran qui avalerait le lancement d'Instagram.
    Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "input", "keyevent", "KEYCODE_HOME") | Out-Null
    Start-Sleep -Seconds 1
    Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "am", "start", "-n", "com.instagram.android/.activity.MainTabActivity") | Out-Null
    Start-Sleep -Seconds 3
}

function Reset-InstagramState {
    # Instagram peut rester dans un etat bancal apres un arret brutal (VM coupee
    # en pleine session, process tue) et repartir en ANR au lancement suivant,
    # ce qui fait echouer toute la session pour 0 interaction. Un force-stop
    # garantit un demarrage propre.
    # On ne fait volontairement PAS "pm clear" : cela effacerait la session
    # de connexion et demanderait de se reconnecter a la main.
    Write-Log "Remise a plat de l'etat d'Instagram (force-stop)..."
    Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "am", "force-stop", "com.instagram.android") | Out-Null
    Start-Sleep -Seconds 3
    # Retour a l'accueil pour chasser un eventuel dialogue ANR encore affiche
    Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "input", "keyevent", "KEYCODE_HOME") | Out-Null
    Start-Sleep -Seconds 2
}

function Get-ScreenHash {
    # La capture est prise ET hachee cote device : on ne rapatrie qu'une chaine
    # de 32 caracteres. Rapatrier le PNG binaire le ferait passer par Out-String,
    # qui le corromprait.
    $r = Invoke-Adb -AdbArgs @("-s", $DeviceId, "shell", "screencap -p /sdcard/_wd.png && md5sum /sdcard/_wd.png")
    if ($r.Output -match '([0-9a-f]{32})') { return $Matches[1] }
    return ""
}

# ------------------------------------------------------------ profil session

function Get-SessionProfile {
    # Retourne un profil de session tire au sort. On ne coupe jamais le bot au
    # chrono : c'est la hauteur des limites qui fait la duree.
    if ($TestRun) {
        return [pscustomobject]@{
            Name      = "TEST"
            Overrides = @(
                "--total-interactions-limit", "3-5",
                "--total-likes-limit",        "2-4",
                "--interactions-count",       "2-3"
            )
        }
    }

    # Repartition 20/40/40 : le poids est mis sur les sessions productives.
    # En 40/40/20, un tirage de 3 COURTE sur 4 sessions plafonnait la journee.
    #
    # Les plafonds d'interactions sont volontairement larges par rapport aux
    # likes : sur les sessions reelles, seuls ~0.75 like sort par interaction
    # (les filtres ecartent beaucoup de profils). Un plafond d'interactions trop
    # serre couperait la session avant que le quota de likes soit atteint --
    # c'est le quota de likes qui doit decider de la fin.
    $roll = Get-Random -Minimum 1 -Maximum 101
    if ($roll -le 20) {
        return [pscustomobject]@{
            Name      = "COURTE"
            Overrides = @(
                "--total-interactions-limit", "70-120",
                "--total-likes-limit",        "40-70",
                "--interactions-count",       "20-40"
            )
        }
    }
    if ($roll -le 60) {
        return [pscustomobject]@{
            Name      = "MOYENNE"
            Overrides = @(
                "--total-interactions-limit", "140-220",
                "--total-likes-limit",        "90-140",
                "--interactions-count",       "40-80"
            )
        }
    }
    # 20% : aucune surcharge, on garde les limites du config.yml
    return [pscustomobject]@{ Name = "LONGUE"; Overrides = @() }
}

function Invoke-BotSession {
    param([object]$SessionProfile)

    $stamp   = Get-Date -Format "yyyyMMdd_HHmmss"
    $outFile = Join-Path $LogDir "bot_${Account}_${stamp}.out.log"
    $errFile = Join-Path $LogDir "bot_${Account}_${stamp}.err.log"

    # --total-sessions 1 : bot_flow sort du process apres une session
    # (can_repeat() renvoie false), au lieu de boucler en gardant la VM allumee.
    $botArgs = @(
        "run.py",
        "--config", "accounts/$Account/config.yml",
        "--total-sessions", "1"
    ) + $SessionProfile.Overrides

    # Deux binaires adb coexistent : celui de MEmu (qui lance et tient le serveur)
    # et platform-tools. adbutils prend celui du PATH, donc un client d'une version
    # differente de celle du serveur. C'est un suspect serieux pour les
    # "USB disconnected" qui coupent une session sur deux au bout d'un temps
    # aleatoire. ADBUTILS_ADB_PATH aligne le client du bot sur le binaire qui
    # detient le serveur -- variable d'environnement, aucun code modifie.
    $memuAdb = Join-Path (Split-Path $MemucPath) "adb.exe"
    if (Test-Path $memuAdb) {
        $env:ADBUTILS_ADB_PATH = $memuAdb
        Write-Log "adb du bot aligne sur celui du serveur : $memuAdb"
    }

    # Fenetre de reconnexion du device. uiautomator2 SAIT se reconnecter tout
    # seul quand le transport MEmu tombe : _wait_for_device() boucle sur
    # "adb disconnect" + "adb connect" tant qu'il a du temps. Mais ce temps vaut
    # 3 secondes en dur, sauf si TMQ=true -- auquel cas il prend
    # WAIT_FOR_DEVICE_TIMEOUT. Trois secondes ne suffisent jamais a une VM MEmu
    # dont l'adbd vient de tomber : la boucle rend la main et leve
    # "RuntimeError: USB device 127.0.0.1:21523 is offline" (l'erreur qui a tue
    # le plus de sessions), ou laisse _setup_atx_agent() taper dans un adb mort
    # ("AdbError: closed"). On lui laisse 120 s pour recoller le transport.
    #
    # TMQ n'a pas d'autre effet ici : son second usage (uiautomator2
    # __init__.py:291, repli sur une URL atx-agent WiFi) exige un
    # _atx_agent_url non vide, or on se connecte par serial 127.0.0.1:21523
    # donc il vaut None. Verifie avant activation.
    # Persona de l'AI Commenter : nom d'artiste lu dans un fichier local ignore
    # par git, pour qu'il n'apparaisse jamais dans le depot. Absent = persona
    # anonyme, le bot fonctionne quand meme.
    $personaFile = Join-Path $PSScriptRoot "accounts\$Account\persona.txt"
    if (Test-Path $personaFile) {
        $env:AI_PERSONA_NAME = (Get-Content $personaFile -Raw).Trim()
    } else {
        Remove-Item Env:\AI_PERSONA_NAME -ErrorAction SilentlyContinue
        Write-Log "Pas de $personaFile : persona IA anonyme." "WARN"
    }

    $env:TMQ = "true"
    $env:WAIT_FOR_DEVICE_TIMEOUT = "120"
    Write-Log "Fenetre de reconnexion du device portee a 120s (TMQ=true)."

    Write-Log "Lancement du bot: python $($botArgs -join ' ')"
    Write-Log "Sortie -> $outFile"

    $proc = Start-Process -FilePath $Python -ArgumentList $botArgs `
                          -WorkingDirectory $PSScriptRoot -NoNewWindow -PassThru `
                          -RedirectStandardOutput $outFile -RedirectStandardError $errFile

    # Acceder a .Handle force .NET a conserver le handle du process : sans ca,
    # $proc.ExitCode reste vide apres WaitForExit et on ne sait pas si le bot
    # a fini normalement ou crashe.
    $null = $proc.Handle

    $started = Get-Date
    # On attend par tranches de 2 min pour relayer l'activite du bot dans le log
    # d'orchestration : sinon il reste muet pendant toute la session et on croit
    # a un blocage. Le bot n'est jamais interrompu, sauf garde-fou explicite.
    $hardMs    = if ($HardTimeoutMinutes -gt 0) { $HardTimeoutMinutes * 60 * 1000 } else { 0 }
    $tick      = 0
    $prevHash  = ""
    $sameCount = 0
    $errPos    = 0

    while (-not $proc.WaitForExit(60000)) {
        $tick++
        $mins = [int]((Get-Date) - $started).TotalMinutes

        # Surveillance 1 : navigation coincee dans la tab bar (bug Reels connu).
        $recovered = $false
        if (Test-Path $errFile) {
            $lines = @(Get-Content $errFile -ErrorAction SilentlyContinue)
            if ($lines.Count -gt $errPos) {
                $fresh  = $lines[$errPos..($lines.Count - 1)]
                $errPos = $lines.Count
                # "App has crashed / has been closed" = Instagram est mort dans la
                # VM. GramAddict ne le relance pas et continue a taper dans le vide,
                # en repetant la meme erreur des dizaines de fois : c'est le "scroll
                # en boucle" visible a l'ecran. C'est le signal le plus franc pour
                # declencher une relance d'Instagram.
                if ($fresh -match "App has crashed / has been closed") {
                    if (Test-RecoveryAllowed) { Invoke-ScreenRecovery -Reason "Instagram a crashe dans la VM" }
                    $recovered = $true
                } elseif ($fresh -match "Didn't find tab .* in the tab bar") {
                    if (Test-RecoveryAllowed) { Invoke-ScreenRecovery -Reason "tab bar coincee" }
                    $recovered = $true
                }
            }
        }

        # Surveillance 2 : rendu fige. Une surface video bloquee dans MEmu peut
        # geler toute l'automatisation sans produire la moindre ligne de log,
        # d'ou la comparaison d'images plutot que la lecture du log.
        if (-not $recovered) {
            $h = Get-ScreenHash
            if ($h -and $h -eq $prevHash) { $sameCount++ } else { $sameCount = 0 }
            $prevHash = $h
            if ($sameCount -ge 3) {
                if (Test-RecoveryAllowed) { Invoke-ScreenRecovery -Reason "ecran identique depuis ~3 min" }
                $sameCount = 0
                $prevHash  = ""
            }
        }

        # Heartbeat toutes les 2 minutes (un tour sur deux)
        if ($tick % 2 -eq 0) {
            $last = ""
            if (Test-Path $errFile) {
                $l = Get-Content $errFile -Tail 1 -ErrorAction SilentlyContinue
                if ($l) {
                    $last = ($l -replace "\s+", " ").Trim()
                    if ($last.Length -gt 110) { $last = $last.Substring($last.Length - 110) }
                }
            }
            Write-Log "  bot en cours ($mins min) | $last"
        }

        if ($hardMs -gt 0 -and ((Get-Date) - $started).TotalMilliseconds -ge $hardMs) {
            Write-Log "Garde-fou: le bot depasse $HardTimeoutMinutes min, arret force." "WARN"
            try { $proc.Kill($true) } catch { $proc.Kill() }
            $proc.WaitForExit()
            break
        }
    }

    $elapsed = [int]((Get-Date) - $started).TotalMinutes
    Write-Log "Bot termine en $elapsed min (code de sortie $($proc.ExitCode))."

    # Le code de sortie ne suffit pas : le bot peut renvoyer 0 alors qu'il n'a
    # rien fait du tout (Instagram en ANR, soft-ban...). On lit donc son rapport
    # final pour dire clairement si la session a produit quelque chose.
    # Absence de rapport final = le bot est mort en cours de route (NPE
    # d'accessibilite uiautomator2, ANR...). GramAddict classe ces erreurs comme
    # non recuperables et sort, parfois meme avec un code 0. C'est ce drapeau,
    # pas le code de sortie, qui declenche une nouvelle tentative.
    $hasReport  = $false
    $productive = $false
    $likesDone = "?"
    $interDone = "?"

    if (Test-Path $errFile) {
        # Fenetre large : GramAddict imprime parfois son rapport final PUIS une
        # longue stack trace par-dessus. Une fenetre trop courte ferait passer une
        # session reussie pour un crash, et declencherait une relance inutile.
        $report   = @(Get-Content $errFile -Tail 400 -ErrorAction SilentlyContinue)
        $critical = $report | Where-Object { $_ -match "CRITICAL|NullPointerException|Unable to open Instagram" } | Select-Object -First 1
        # "FINISH" est imprime par bot_flow a la fin d'une session, AVANT les
        # rapports. C'est le marqueur fiable : le rapport final, lui, peut manquer
        # alors que la session a reussi (bug connu de telegram.py/daily_summary qui
        # leve un TypeError en agregeant les stats). Se fier au seul rapport ferait
        # relancer des sessions parfaitement abouties.
        $done     = $report | Where-Object { $_ -match "FINISH:|Completed sessions:" }    | Select-Object -Last 1
        $likes    = $report | Where-Object { $_ -match "Total likes:\s*\d+" }             | Select-Object -Last 1
        $inter    = $report | Where-Object { $_ -match "Total interactions:\s*\(\d+\)" }  | Select-Object -Last 1

        if ($done) {
            $hasReport = $true
            if ($likes -match "Total likes:\s*(\d+)")            { $likesDone = $Matches[1] }
            if ($inter -match "Total interactions:\s*\((\d+)\)") { $interDone = $Matches[1] }
        }

        # Le rapport final de GramAddict manque parfois ses compteurs (son module
        # telegram leve un TypeError en agregeant les stats). Plutot qu'afficher
        # "?" pour une session qui a bien travaille, on compte les likes reels
        # dans le journal complet : les trois formulations correspondent aux
        # differents chemins de like (bouton, double-tap, grille de profil).
        if ($likesDone -eq "?") {
            $all = @(Get-Content $errFile -ErrorAction SilentlyContinue)
            $n = ($all | Select-String -Pattern "Liking post\.\.\.|Like button clicked successfully|Double clicked media to like").Count
            if ($n -gt 0) { $likesDone = "$n (comptes dans le journal)" }
        }

        # "Completed sessions: 0" ne veut PAS dire session inutile : une session
        # ayant fait 27 likes puis crashe a la toute fin l'affiche quand meme.
        # Ce qui compte est le travail reellement produit :
        #   - "FINISH:" present     -> session terminee proprement
        #   - des likes/interactions -> elle a produit, meme si elle a crashe apres
        #   - duree >= 20 min        -> elle a forcement travaille, meme sans rapport
        #     (evite de doubler l'activite en relancant une longue session)
        $nLikes = 0
        if ($likesDone -match "^(\d+)") { $nLikes = [int]$Matches[1] }
        $finish = $report | Where-Object { $_ -match "FINISH:" } | Select-Object -Last 1

        # On juge sur le RESULTAT, pas sur la duree. Une session de 21 min qui a
        # fait 8 likes alors qu'elle en visait 140 n'est pas une session aboutie :
        # l'ancienne regle "20 min ou plus = c'est bon" la laissait passer.
        # GramAddict journalise "Total Likes: OK (realise/quota)" : on s'en sert
        # pour comparer ce qui a ete fait a ce qui etait vise.
        $quota = 0
        $lim = $report | Where-Object { $_ -match "Total Likes: (?:OK|Limit Reached) \((\d+)/(\d+)\)" } | Select-Object -Last 1
        if ($lim -match "Total Likes: (?:OK|Limit Reached) \((\d+)/(\d+)\)") {
            $nLikes = [int]$Matches[1]
            $quota  = [int]$Matches[2]
        }

        if ($finish) {
            $productive = $true          # session cloturee proprement
        } elseif ($quota -gt 0) {
            $productive = $nLikes -ge [int]($quota * 0.25)
        } else {
            $productive = $nLikes -ge 10 # quota inconnu : seuil plancher
        }

        if (-not $hasReport) {
            Write-Log "CRASH TECHNIQUE: le bot s'est arrete sans produire son rapport final." "WARN"
            if ($critical) { Write-Log "  cause: $(($critical -replace '\s+', ' ').Trim())" "WARN" }
        } elseif ($done -match "Completed sessions:\s*0") {
            # "Completed sessions: 0" signifie que la session n'a pas ete cloturee
            # proprement, PAS qu'elle n'a rien fait : elle a pu liker 18 fois avant
            # de crasher. On affiche donc le travail reel, pas un "0" trompeur.
            Write-Log "SESSION INTERROMPUE avant cloture: $interDone interaction(s), $likesDone like(s) tout de meme realises." "WARN"
            if ($critical) { Write-Log "  cause: $(($critical -replace '\s+', ' ').Trim())" "WARN" }
        } else {
            Write-Log "Bilan session: $interDone interaction(s), $likesDone like(s)."
        }
    }

    return [pscustomobject]@{
        ExitCode     = $proc.ExitCode
        HasReport    = $hasReport
        Productive   = $productive
        Likes        = $likesDone
        Interactions = $interDone
    }
}

# --------------------------------------------------------------------- boucle

Write-Log "==================== DEMARRAGE run_session_loop ===================="
Write-Log "Compte=$Account VM=$VmIndex Device=$DeviceId Horaires=$WorkStart-$WorkEnd"

Test-Prerequisites
Invoke-LogRotation

if ($TestRun) {
    $sessionCount = 1
    Write-Log "MODE TEST: 1 seule session avec des limites minuscules." "WARN"
} else {
    $sessionCount = Get-Random -Minimum $MinSessions -Maximum ($MaxSessions + 1)
}
Write-Log "Objectif du jour: $sessionCount session(s)."

# Une session qui echoue n'est PAS comptee comme faite : sinon une serie de
# crashes epuise le quota de la journee sans rien produire (cas du 23/08 :
# 1 session, 8 likes, puis 2h17 de pause). On rejoue la meme session apres une
# pause courte, jusqu'a ce qu'elle aboutisse. $maxRounds borne l'ensemble pour
# eviter de tourner en boucle si l'environnement est durablement casse.
$done      = 0
$rounds    = 0
$maxRounds = $sessionCount * 3

while (($done -lt $sessionCount) -and ($rounds -lt $maxRounds)) {
    $rounds++

    if (-not (Wait-ForWorkingHours)) {
        Write-Log "Fin de la journee apres $done session(s) aboutie(s)."
        break
    }

    if (-not (Test-DiskSpace)) {
        if (-not (Invoke-Pause -Min 30 -Max 60 -Motif "Disque plein, attente")) { break }
        continue
    }

    $prof = Get-SessionProfile
    Write-Log "---------- Session $($done + 1)/$sessionCount - profil $($prof.Name) (essai global $rounds/$maxRounds) ----------"

    if ($DryRun) {
        Write-Log "[DRYRUN] memuc start -i $VmIndex"
        Write-Log "[DRYRUN] attente boot complet, puis desinstall uiautomator2"
        Write-Log "[DRYRUN] python run.py --config accounts/$Account/config.yml --total-sessions 1 $($prof.Overrides -join ' ')"
        Write-Log "[DRYRUN] memuc stop -i $VmIndex"
        $done++
        if ($done -lt $sessionCount) {
            $g = Get-Random -Minimum $MinGapMinutes -Maximum ($MaxGapMinutes + 1)
            Write-Log "[DRYRUN] pause de $g min"
        }
        continue
    }

    # Relances rapprochees sur VM neuve : un crash technique ne doit pas couter
    # la session. Le bot lui-meme n'est jamais interrompu.
    $attempt = 0
    $ok      = $false
    while ($true) {
        $attempt++
        $res = $null
        try {
            if (-not (Wait-ForNetwork)) { break }
            # Lance AVANT la VM : les ~290s de chargement du modele se deroulent
            # pendant le boot et la stabilisation, au lieu d'etre payees par le
            # premier commentaire de la session.
            Start-ModelPreload
            Start-Vm
            if (Wait-VmReady) {
                Reset-Uiautomator
                Reset-InstagramState
                $res = Invoke-BotSession -SessionProfile $prof
            } else {
                Write-Log "VM non prete." "ERROR"
            }
        } catch {
            Write-Log "Erreur pendant la session: $($_.Exception.Message)" "ERROR"
        } finally {
            # Stop-Vm est dans un finally : une exception ICI n'est rattrapee par
            # personne et tue l'orchestrateur en silence, sans meme journaliser.
            # Vu le 29/08 : le log s'arretait net sur "Arret de la VM index 2 ..."
            # et le process disparaissait. On protege donc l'arret lui-meme.
            try {
                Stop-Vm
            } catch {
                Write-Log "Echec de l'arret de la VM: $($_.Exception.Message)" "ERROR"
                foreach ($n in @("MEmu", "MEmuHeadless")) {
                    Get-Process -Name $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
                }
            }
        }

        if ($res -and $res.Productive) { $ok = $true; break }
        if ($attempt -le $MaxRetriesPerSession) {
            Write-Log "Relance immediate ($attempt/$MaxRetriesPerSession) dans 30s, VM redemarree a neuf." "WARN"
            Start-Sleep -Seconds 30
            continue
        }
        break
    }

    if ($ok) {
        $done++
        Write-Log "Session $done/$sessionCount aboutie."
        if ($done -lt $sessionCount) {
            if (-not (Invoke-Pause -Min $MinGapMinutes -Max $MaxGapMinutes -Motif "Pause entre sessions")) { break }
        }
    } else {
        Write-Log "Session non aboutie apres $attempt tentatives : elle sera rejouee." "ERROR"
        if (-not (Invoke-Pause -Min $MinRetryGapMinutes -Max $MaxRetryGapMinutes -Motif "Pause courte avant de rejouer")) { break }
    }
}

if ($rounds -ge $maxRounds -and $done -lt $sessionCount) {
    Write-Log "Plafond d'essais atteint ($maxRounds) avec $done session(s) aboutie(s) : l'environnement semble instable." "ERROR"
}

Write-Log "==================== FIN run_session_loop ===================="
