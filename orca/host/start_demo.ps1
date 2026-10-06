<#
Start everything for a demo, each program in its own window.

    cd orca\host
    powershell -ExecutionPolicy Bypass -File .\start_demo.ps1              # agents + OG shell
    powershell -ExecutionPolicy Bypass -File .\start_demo.ps1 -Simulated   # also plays the SIMULATED patient
    powershell -ExecutionPolicy Bypass -File .\start_demo.ps1 -Agentverse  # the four agents on Agentverse

What it does, in order:
  1. stops any old Orca agent / shell programs (they hold ports and the OGs' serial ports);
  2. counts the OGs it can see (you want 3: left hand, right hand, screen);
  3. sets the SIMULATED participant (DEMO-Maya) for the windows it opens, so nothing is saved under a
     real person; values already in .env do not override these, and .env is never read or printed here;
  4. opens the agents in one window and the OG shell in another.
Close the windows to stop the demo. Nothing here flashes or changes an OG.
#>
param(
    [switch]$Agentverse,    # run agent_stage (four Agentverse agents) instead of agents_main (local, private)
    [switch]$Simulated      # shorter windows, and start the simulated patient after the agents are up
)

$ErrorActionPreference = "Stop"
$hostDir = $PSScriptRoot                                   # orca\host
$repo = Split-Path -Parent (Split-Path -Parent $hostDir)   # the repository root
$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Cannot find $py. Create the virtual environment first (see the README)." }

# 1. Stop old programs that would hold the same ports.
$old = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -match 'orca\.(agent_stage|agents_main|agent_gateway|og_shell)\b'
}
foreach ($p in $old) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
if ($old) { Write-Host "Stopped $(@($old).Count) old Orca program(s)." }

# 2. Count the OGs (display CPUs: USB 093C:2055).
$count = & $py -c "from serial.tools import list_ports; print(sum(1 for p in list_ports.comports() if p.vid == 0x093C and p.pid == 0x2055))"
if ([int]$count -lt 3) {
    Write-Warning "Only $count OG(s) found (expected 3: left, right, screen). Check the cables, then continue or Ctrl+C."
} else {
    Write-Host "Found $count OGs."
}

# 3. The simulated participant and the window sizes (the demo notes explain both).
$env:ORCA_PARTICIPANT = "DEMO-Maya"
if ($Simulated) { $env:ORCA_WINDOW_S = "2"; $env:ORCA_SAMPLE_S = "0.5" }
else            { $env:ORCA_WINDOW_S = "4"; $env:ORCA_SAMPLE_S = "1" }
if ($Agentverse) { $env:ORCA_PUBLIC_ANSWERS = "1" }
$agents = if ($Agentverse) { "orca.agent_stage" } else { "orca.agents_main" }

function Start-Window([string]$title, [string]$module) {
    $cmd = "`$Host.UI.RawUI.WindowTitle = '$title'; & '$py' -u -m $module"
    Start-Process powershell -WorkingDirectory $hostDir -ArgumentList @("-NoExit", "-Command", $cmd)
}

# 4. Agents first, then the shell (the games look for the agents when they start).
Start-Window "Orca agents" $agents
Write-Host "Started $agents. Waiting for it to come up..."
Start-Sleep -Seconds 6
Start-Window "Orca OG shell" "orca.og_shell"
Write-Host "Started orca.og_shell."

if ($Simulated) {
    Start-Sleep -Seconds 8
    Start-Window "Orca simulated patient" "orca.demo_data"
    Write-Host "Started orca.demo_data (SIMULATED patient, DEMO-Maya)."
}

Write-Host ""
Write-Host "Demo is up as participant DEMO-Maya (simulated). Keep the game window on the main monitor, uncovered."
