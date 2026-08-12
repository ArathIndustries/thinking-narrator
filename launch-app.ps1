# thinking-narrator — "app" layout: Claude Code on the left, narrator on the right.
#
# Opens two windows side by side on the primary monitor's work area:
#   left  — Windows Terminal running `claude` (falls back to PowerShell)
#   right — the narrator in a chromeless Edge app window, panel layout
# and starts server.py first if it is not already answering.
#
#   powershell -ExecutionPolicy Bypass -File launch-app.ps1
#   ...           -PanelPercent 40      # give the narrator more room
#   ...           -NoTerminal           # narrator only, snap the terminal yourself
#
# Windows placement goes through SetWindowPos rather than the browser's
# --window-size, because an already-running Edge hands the app window to the
# existing process and silently ignores the geometry flags.

param(
  [int]$Port = 8917,
  [ValidateRange(15, 85)][int]$PanelPercent = 32,
  [string]$StartDir = $HOME,
  [switch]$NoTerminal
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

Add-Type -AssemblyName System.Windows.Forms
$sig = @"
[DllImport("user32.dll")] public static extern bool SetWindowPos(
    IntPtr hWnd, IntPtr after, int X, int Y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
"@
$U = Add-Type -MemberDefinition $sig -Name Win32 -Namespace TN -PassThru

function Test-Port([int]$p) {
  # Connect-probe, never a bind attempt: http.server sets SO_REUSEADDR, so on
  # Windows a second bind on a live port succeeds and silently serves.
  $c = New-Object Net.Sockets.TcpClient
  try { $c.Connect("127.0.0.1", $p); return $true } catch { return $false }
  finally { $c.Dispose() }
}

function Wait-NewWindow([string]$name, [int[]]$before, [int]$timeoutMs = 10000) {
  # wt.exe and msedge.exe both hand off to another process, so the PID from
  # Start-Process is not the one holding the window. Diff the process list.
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while ($sw.ElapsedMilliseconds -lt $timeoutMs) {
    $p = @(Get-Process -Name $name -ErrorAction SilentlyContinue |
           Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero -and
                          $before -notcontains $_.Id })
    if ($p.Count) { return $p[0] }
    Start-Sleep -Milliseconds 200
  }
  return $null
}

function Move-Win($proc, [int]$x, [int]$y, [int]$w, [int]$h, [string]$label) {
  if ($null -eq $proc) {
    Write-Warning "$label window did not appear in time - snap it yourself (Win+Left / Win+Right)."
    return
  }
  [void]$U::ShowWindow($proc.MainWindowHandle, 9)          # SW_RESTORE: un-maximize
  Start-Sleep -Milliseconds 150                            # let the restore settle
  [void]$U::SetWindowPos($proc.MainWindowHandle, [IntPtr]::Zero, $x, $y, $w, $h, 0x0004)
  Write-Host ("[app] {0,-8} -> {1}x{2} at {3},{4}" -f $label, $w, $h, $x, $y)
}

# ---- 1. server ----
if (Test-Port $Port) {
  Write-Host "[app] server already running on $Port"
} else {
  Start-Process -WindowStyle Minimized -FilePath "py" `
    -ArgumentList @("$here\server.py", "--no-browser", "--port", $Port)
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while (-not (Test-Port $Port) -and $sw.ElapsedMilliseconds -lt 15000) {
    Start-Sleep -Milliseconds 250
  }
  if (-not (Test-Port $Port)) { throw "server.py did not start on port $Port" }
  Write-Host "[app] server started on $Port"
}

# ---- 2. geometry ----
$wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$panelW = [int]($wa.Width * $PanelPercent / 100)
$termW  = $wa.Width - $panelW

# ---- 3. narrator panel (right) ----
$edge = @(
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw "Microsoft Edge not found - needed for the chromeless app window" }

# --user-data-dir is load-bearing, not hygiene: without it an already-running
# Edge opens the app window inside an EXISTING process, so no new PID and no
# new MainWindowHandle ever appears and the placement poll times out
# (measured 2026-08-12). A private profile also keeps the panel's saved voice
# and read mode separate from the browser you actually browse in.
$profileDir = Join-Path $env:LOCALAPPDATA "thinking-narrator\edge-profile"
$before = @(Get-Process -Name msedge -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
Start-Process $edge -ArgumentList @(
  "--app=http://127.0.0.1:$Port/?panel=1",
  "--user-data-dir=`"$profileDir`"",
  "--no-first-run", "--no-default-browser-check",
  "--window-position=$($wa.X + $termW),$($wa.Y)",
  "--window-size=$panelW,$($wa.Height)")
Move-Win (Wait-NewWindow "msedge" $before) ($wa.X + $termW) $wa.Y $panelW $wa.Height "narrator"

# ---- 4. Claude Code (left) ----
if (-not $NoTerminal) {
  $wt = Get-Command wt.exe -ErrorAction SilentlyContinue
  if ($wt) {
    $before = @(Get-Process -Name WindowsTerminal -ErrorAction SilentlyContinue |
                ForEach-Object { $_.Id })
    Start-Process "wt.exe" -ArgumentList @("-d", "`"$StartDir`"",
                                           "powershell", "-NoExit", "-Command", "claude")
    Move-Win (Wait-NewWindow "WindowsTerminal" $before) $wa.X $wa.Y $termW $wa.Height "terminal"
  } else {
    $before = @(Get-Process -Name powershell -ErrorAction SilentlyContinue |
                ForEach-Object { $_.Id })
    Start-Process "powershell" -ArgumentList @("-NoExit", "-Command", "cd `"$StartDir`"; claude")
    Move-Win (Wait-NewWindow "powershell" $before) $wa.X $wa.Y $termW $wa.Height "terminal"
  }
}

Write-Host "[app] ready - narrator follows the active chat; switch read mode in its footer."
