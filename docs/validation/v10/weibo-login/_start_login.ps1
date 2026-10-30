# Start the visible weibo login window (300s). Returns as soon as the window is
# captured so the planner can be woken immediately; the login keeps running.
#
# NOTE on argv: the acceptance command omitted the CLI's required --state-dir and
# passed --visible, which the login subparser does not define (only
# search/detail/comments do). The login subcommand is visible by default
# (--headless is store_true), so we pass --state-dir and drop --visible.
$ErrorActionPreference = 'Continue'
$repo = 'D:\桌面\two'
Set-Location $repo
$env:PYTHONPATH = $repo
$py = 'C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe'
$base = 'D:\桌面\two\docs\validation\v10\weibo-login'
New-Item -ItemType Directory -Force -Path $base | Out-Null
$out = "$base\login.out.txt"
$err = "$base\login.err.txt"

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W32M {
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L,T,R,B; }
}
'@

$started = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
"LOGIN_START_UTC=$started"
$procArgs = @('-X','utf8','-m','tools.selection.access.weibo',
              '--state-dir',"$base\state-login",
              '--profile',"$base\profile",
              'login','--timeout','300')
$proc = Start-Process -FilePath $py -ArgumentList $procArgs -WorkingDirectory $repo `
    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
"PY_PID=$($proc.Id)"
$proc.Id | Out-File "$base\login.pid" -Encoding ascii

$first = $null
for ($i = 0; $i -lt 500; $i++) {
    $ours = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'weibo-login' })
    foreach ($p in $ours) {
        $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $gp -or $gp.MainWindowHandle -eq 0) { continue }
        $h = $gp.MainWindowHandle
        $r = New-Object W32M+RECT
        [void][W32M]::GetWindowRect($h, [ref]$r)
        $first = [pscustomobject]@{
            sampled_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
            python_pid = $proc.Id
            chrome_pid = $gp.Id
            title = $gp.MainWindowTitle
            handle = $h
            visible = [W32M]::IsWindowVisible($h)
            responding = $gp.Responding
            rect = "$($r.L),$($r.T),$($r.R),$($r.B)"
        }
        break
    }
    if ($first) { break }
    if ($proc.HasExited) { break }
    Start-Sleep -Milliseconds 300
}

if ($first) {
    $first | ConvertTo-Json -Compress | Out-File "$base\window_evidence.txt" -Encoding utf8
    "WINDOW_OK python_pid=$($first.python_pid) chrome_pid=$($first.chrome_pid) title=$($first.title) handle=$($first.handle) visible=$($first.visible) rect=$($first.rect)"
} else {
    "WINDOW_NONE python_alive=$(-not $proc.HasExited)"
    Get-Content $err -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -First 5
}
"LOGIN_STILL_RUNNING=$(-not $proc.HasExited)"
Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'
