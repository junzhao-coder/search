# Attempt 3 (last quota of this batch): mobile UA, absolute paths, fresh profile.
# Window sampled every 300ms and filtered by profile_empty3.
$ErrorActionPreference = 'Continue'
$repo = 'D:\桌面\two'
Set-Location $repo
$env:PYTHONPATH = $repo
$py = 'C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe'
$probe = "$repo\docs\validation\v10\weibo-probe"
$out = "$probe\probe3.out.txt"
$err = "$probe\probe3.err.txt"
$evidence = "$probe\window_evidence3.txt"

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W32s {
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L,T,R,B; }
}
'@

$started = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
"START_UTC=$started"
$procArgs = @('-X','utf8','-m','tools.selection.access.weibo',
              '--state-dir',"$probe\state-probe3",
              '--batch-id','weibo-probe-3','--mode','authenticated-browser',
              '--profile',"$probe\profile_empty3",
              'search','学习计划模板','--limit','5','--visible','--timeout','60',
              '--diagnostics-dir',"$probe\diag3")
$proc = Start-Process -FilePath $py -ArgumentList $procArgs -WorkingDirectory $repo `
    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
"PY_PID=$($proc.Id)"
$proc.Id | Out-File "$probe\probe3.pid" -Encoding ascii

$first = $null
$samples = 0
$ourPids = @()
for ($i = 0; $i -lt 600; $i++) {
    $alive = -not $proc.HasExited
    $ours = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'profile_empty3' })
    $ourPids = @($ours | Select-Object -ExpandProperty ProcessId)
    foreach ($p in $ours) {
        $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $gp -or $gp.MainWindowHandle -eq 0) { continue }
        $handle = $gp.MainWindowHandle
        $rect = New-Object W32s+RECT
        [void][W32s]::GetWindowRect($handle, [ref]$rect)
        $row = [pscustomobject]@{
            sampled_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
            pid = $gp.Id
            title = $gp.MainWindowTitle
            handle = $handle
            visible = [W32s]::IsWindowVisible($handle)
            responding = $gp.Responding
            rect = "$($rect.L),$($rect.T),$($rect.R),$($rect.B)"
        }
        $samples++
        if ($null -eq $first) {
            $first = $row
            $row | ConvertTo-Json -Compress | Out-File $evidence -Encoding utf8
        }
        break
    }
    if (-not $alive) { break }
    Start-Sleep -Milliseconds 300
}

if ($first) {
    "FIRST_WINDOW pid=$($first.pid) handle=$($first.handle) visible=$($first.visible) responding=$($first.responding) title=$($first.title) rect=$($first.rect)"
    "WINDOW_SAMPLES=$samples"
} else {
    "FIRST_WINDOW none (our chrome pids seen: $($ourPids -join ','))"
}
$proc.WaitForExit(180000) | Out-Null
"PROC_EXITED=$($proc.HasExited) EXIT=$($proc.ExitCode)"
"FINISH_UTC=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'
