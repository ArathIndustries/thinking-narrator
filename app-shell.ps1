# thinking-narrator — single-window app shell.
#
# One window, one taskbar entry, containing two REAL windows adopted with
# SetParent: Windows Terminal (left, running `claude`) and the narrator
# (right, a chromeless Edge app window on the panel layout). Reparenting
# rather than re-implementing keeps every Windows Terminal feature — tabs,
# panes, profiles, settings, its own keybindings — which is the whole point:
# new chats open as terminal tabs and the narrator follows whichever is
# active.
#
#   powershell -ExecutionPolicy Bypass -File app-shell.ps1
#   ...  -PanelPercent 40     # wider narrator column
#   ...  -NoClaude            # plain shell instead of launching claude
#
# Drag the divider to re-split. Closing the shell releases the terminal back
# to the desktop as a normal window (an in-progress chat is not killed) and
# closes the narrator pane.

param(
  [int]$Port = 8917,
  [ValidateRange(15, 85)][int]$PanelPercent = 32,
  [string]$StartDir = $HOME,
  [switch]$NoClaude
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$sig = @"
[DllImport("user32.dll", SetLastError=true)] public static extern IntPtr SetParent(IntPtr child, IntPtr newParent);
[DllImport("user32.dll", SetLastError=true)] public static extern IntPtr GetParent(IntPtr hWnd);
[DllImport("user32.dll", SetLastError=true)] public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
[DllImport("user32.dll", SetLastError=true)] public static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
[DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool repaint);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern IntPtr SetFocus(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
"@
$U = Add-Type -MemberDefinition $sig -Name Shell -Namespace TN -PassThru

# Window-level enumeration, because process-level detection cannot see a new
# Windows Terminal window: WT hosts additional windows inside the SAME
# process, so no new PID and no new MainWindowHandle appears (measured
# 2026-08-12 — the first attempt silently fell back to plain PowerShell).
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class TNWin {
  private delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] private static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] private static extern int GetClassName(IntPtr h, StringBuilder s, int m);
  [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  public static IntPtr[] ByClass(string cls) {
    var found = new List<IntPtr>();
    EnumWindows((h, l) => {
      if (!IsWindowVisible(h)) return true;
      var sb = new StringBuilder(256);
      GetClassName(h, sb, 256);
      if (sb.ToString() == cls) found.Add(h);
      return true;
    }, IntPtr.Zero);
    return found.ToArray();
  }
  public static uint PidOf(IntPtr h) { uint pid; GetWindowThreadProcessId(h, out pid); return pid; }
}
"@

$WT_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"

function Wait-NewClassWindow([string]$cls, $before, [int]$timeoutMs = 20000) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  do {
    foreach ($h in [TNWin]::ByClass($cls)) {
      if ($before -notcontains $h) { return $h }
    }
    Start-Sleep -Milliseconds 250
  } while ($sw.ElapsedMilliseconds -lt $timeoutMs)
  return [IntPtr]::Zero
}

$GWL_STYLE   = -16
$WS_CHILD    = 0x40000000
$WS_POPUP    = -2147483648   # 0x80000000 as signed int
$WS_CAPTION  = 0x00C00000
$WS_THICKFRAME = 0x00040000
$SW_SHOW = 5

function Test-Port([int]$p) {
  $c = New-Object Net.Sockets.TcpClient
  try { $c.Connect("127.0.0.1", $p); return $true } catch { return $false }
  finally { $c.Dispose() }
}

# Find the narrator's browser window by COMMAND LINE, not by PID diff. Edge
# hands a second --app launch for the same profile to the process that
# already owns it, so no new PID ever appears once the panel is open (that is
# how the first attempt failed). The browser process is the one carrying
# --app=; its renderer/GPU/utility children carry --type= instead.
function Find-NarratorWindow([string]$profileDir, [int]$timeoutMs = 15000) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  do {
    $ids = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
             Where-Object { $_.CommandLine -like "*--app=*" -and
                            $_.CommandLine -like "*$profileDir*" } |
             ForEach-Object { $_.ProcessId })
    foreach ($id in $ids) {
      $p = Get-Process -Id $id -ErrorAction SilentlyContinue
      if ($p -and $p.MainWindowHandle -ne [IntPtr]::Zero) { return $p }
    }
    Start-Sleep -Milliseconds 250
  } while ($sw.ElapsedMilliseconds -lt $timeoutMs)
  return $null
}

function Wait-NewWindow([string]$name, [int[]]$before, [int]$timeoutMs = 15000) {
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

# Adopting an external top-level window means stripping the styles that make
# it top-level (popup, caption, resize frame) and adding WS_CHILD before the
# SetParent call; skipping the restyle leaves a title bar floating inside the
# host and breaks hit-testing.
function Adopt($hwnd, $hostHwnd) {
  $style = $U::GetWindowLong($hwnd, $GWL_STYLE)
  $new = ($style -band (-bnot $WS_POPUP) -band (-bnot $WS_CAPTION) `
                 -band (-bnot $WS_THICKFRAME)) -bor $WS_CHILD
  [void]$U::SetWindowLong($hwnd, $GWL_STYLE, $new)
  [void]$U::SetParent($hwnd, $hostHwnd)
  [void]$U::ShowWindow($hwnd, $SW_SHOW)
  return $style        # keep the original so Release can put it back
}

# A bare SetFocus across processes is ignored: focus is per input queue, and
# the adopted pane's thread has its own. Attaching this thread's input queue
# to the pane's for the duration of the call is what makes typing land in the
# terminal after clicking on the shell.
function Set-PaneFocus($hwnd) {
  if ($hwnd -eq [IntPtr]::Zero) { return }
  $pid2 = 0
  $tid = $U::GetWindowThreadProcessId($hwnd, [ref]$pid2)
  $me = $U::GetCurrentThreadId()
  $attached = $false
  if ($tid -ne $me) { $attached = $U::AttachThreadInput($me, $tid, $true) }
  [void]$U::SetFocus($hwnd)
  if ($attached) { [void]$U::AttachThreadInput($me, $tid, $false) }
}

function Release($hwnd, $originalStyle) {
  if ($hwnd -eq [IntPtr]::Zero) { return }
  try {
    [void]$U::SetParent($hwnd, [IntPtr]::Zero)
    [void]$U::SetWindowLong($hwnd, $GWL_STYLE, $originalStyle)
    [void]$U::ShowWindow($hwnd, $SW_SHOW)
  } catch { }
}

# ---- server ----
if (-not (Test-Port $Port)) {
  Start-Process -WindowStyle Minimized -FilePath "py" `
    -ArgumentList @("$here\server.py", "--no-browser", "--port", $Port)
  $sw = [Diagnostics.Stopwatch]::StartNew()
  while (-not (Test-Port $Port) -and $sw.ElapsedMilliseconds -lt 15000) {
    Start-Sleep -Milliseconds 250
  }
  if (-not (Test-Port $Port)) { throw "server.py did not start on port $Port" }
  Write-Host "[shell] server started on $Port"
} else {
  Write-Host "[shell] server already running on $Port"
}

# ---- host window ----
$form = New-Object System.Windows.Forms.Form
$form.Text = "Claude Code + Thinking Narrator"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(1600, 950)
$form.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#0B0C0F")
$form.WindowState = "Maximized"

$divider = New-Object System.Windows.Forms.Panel
$divider.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#23262E")
$divider.Cursor = [System.Windows.Forms.Cursors]::SizeWE
$divider.Width = 6
$form.Controls.Add($divider)
$form.Show()
[System.Windows.Forms.Application]::DoEvents()
$hostHwnd = $form.Handle

# ---- adopt the panes ----
# Everything from here to Set-Layout runs under one try: a window that has
# been restyled to WS_CHILD and reparented is destroyed with its host, so a
# failure partway through would take an adopted terminal (and any chat in it)
# down with it. On any error, hand back what was taken.
$termHwnd = [IntPtr]::Zero; $termStyle = 0
$edgeHwnd = [IntPtr]::Zero; $edgeStyle = 0
try {

# ---- adopt the terminal (left) ----
$cmd = if ($NoClaude) { "" } else { "claude" }
$termName = "none"
# Resolve wt.exe by path as well as by PATH: it is a WindowsApps execution
# alias, and PATH does not always carry that directory into a nested,
# non-interactive shell (this is why the first run silently fell back).
$wt = (Get-Command wt.exe -ErrorAction SilentlyContinue).Source
if (-not $wt) {
  $alias = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\wt.exe"
  if (Test-Path $alias) { $wt = $alias }
}
Write-Host "[shell] wt.exe    : $(if ($wt) { $wt } else { 'NOT FOUND' })"
if ($wt) {
  # -w new is required, not cosmetic: without it wt.exe may add a TAB to an
  # existing Windows Terminal window, which would mean adopting (stealing)
  # the window Arath is already working in.
  $before = @([TNWin]::ByClass($WT_CLASS))
  $wtArgs = @("-w", "new", "-d", "`"$StartDir`"", "powershell", "-NoExit")
  if ($cmd) { $wtArgs += @("-Command", $cmd) }
  Start-Process $wt -ArgumentList $wtArgs
  $termHwnd = Wait-NewClassWindow $WT_CLASS $before
  Write-Host "[shell] wt window : before=$($before.Count) found=$termHwnd"
  if ($termHwnd -ne [IntPtr]::Zero) { $termName = "WindowsTerminal" }
}
if ($termHwnd -eq [IntPtr]::Zero) {
  Write-Warning "Windows Terminal window not found - falling back to a plain PowerShell window"
  $before = @(Get-Process -Name powershell -ErrorAction SilentlyContinue |
              ForEach-Object { $_.Id })
  $psArgs = @("-NoExit", "-Command", "Set-Location `"$StartDir`"$(if($cmd){"; $cmd"})")
  Start-Process "powershell" -ArgumentList $psArgs
  $p = Wait-NewWindow "powershell" $before
  if ($null -eq $p) { throw "no terminal window appeared to adopt" }
  $termHwnd = $p.MainWindowHandle
  $termName = "powershell"
}
$termPid = [TNWin]::PidOf($termHwnd)
$termStyle = Adopt $termHwnd $hostHwnd

# ---- adopt the narrator (right) ----
$edge = @(
  "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw "Microsoft Edge not found - needed for the narrator pane" }
$profileDir = Join-Path $env:LOCALAPPDATA "thinking-narrator\edge-profile"
$edgeProc = Find-NarratorWindow $profileDir 1200        # already open? adopt that one
if ($null -eq $edgeProc) {
  Start-Process $edge -ArgumentList @(
    "--app=http://127.0.0.1:$Port/?panel=1",
    "--user-data-dir=`"$profileDir`"",   # dedicated profile: own window, own prefs
    "--no-first-run", "--no-default-browser-check")
  $edgeProc = Find-NarratorWindow $profileDir 20000
}
if ($null -eq $edgeProc) { throw "narrator window did not appear to adopt" }
$edgeHwnd = $edgeProc.MainWindowHandle
$edgeStyle = Adopt $edgeHwnd $hostHwnd

# ---- layout ----
$script:split = $PanelPercent / 100.0
function Set-Layout {
  $w = $form.ClientSize.Width; $h = $form.ClientSize.Height
  if ($w -le 0 -or $h -le 0) { return }
  $panelW = [int]($w * $script:split)
  $termW  = $w - $panelW - $divider.Width
  [void]$U::MoveWindow($termHwnd, 0, 0, $termW, $h, $true)
  $divider.SetBounds($termW, 0, $divider.Width, $h)
  [void]$U::MoveWindow($edgeHwnd, $termW + $divider.Width, 0, $panelW, $h, $true)
}
Set-Layout

} catch {
  Write-Warning "adoption failed: $($_.Exception.Message) - releasing panes"
  Release $termHwnd $termStyle
  Release $edgeHwnd $edgeStyle
  $form.Close()
  throw
}

$form.Add_Resize({ Set-Layout })

# divider drag
$script:dragging = $false
$divider.Add_MouseDown({ $script:dragging = $true })
$divider.Add_MouseUp({ $script:dragging = $false })
$divider.Add_MouseMove({
  param($sender, $e)
  if (-not $script:dragging) { return }
  $x = $divider.Left + $e.X
  $w = $form.ClientSize.Width
  $ratio = 1.0 - ($x / [double]$w)
  if ($ratio -gt 0.15 -and $ratio -lt 0.85) { $script:split = $ratio; Set-Layout }
})

# ---- teardown: hand the terminal back to the desktop, close the narrator ----
$form.Add_FormClosing({
  Release $termHwnd $termStyle          # an in-progress chat survives as a normal window
  Release $edgeHwnd $edgeStyle
  try { $edgeProc.CloseMainWindow() | Out-Null } catch { }
})

Write-Host "[shell] terminal  : $termName pid=$termPid hwnd=$termHwnd parent=$($U::GetParent($termHwnd))"
Write-Host "[shell] narrator  : msedge pid=$($edgeProc.Id) hwnd=$edgeHwnd parent=$($U::GetParent($edgeHwnd))"
Write-Host "[shell] host      : hwnd=$hostHwnd  adopted=$(($U::GetParent($termHwnd) -eq $hostHwnd) -and ($U::GetParent($edgeHwnd) -eq $hostHwnd))"
Write-Host "[shell] running - close the window to release the terminal."

$script:termHwnd = $termHwnd
$form.Add_Activated({ Set-PaneFocus $script:termHwnd })
[void]$U::SetForegroundWindow($hostHwnd)
Set-PaneFocus $termHwnd
[System.Windows.Forms.Application]::Run($form)
