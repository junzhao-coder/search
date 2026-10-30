# Start the single real weibo probe, then sample OUR chrome window every 300ms.
# Window evidence is filtered by command line (profile_empty) so the user's own
# Chrome can never be mistaken for ours.
$ErrorActionPreference = 'Continue'
Set-Location 'D:\桌面\two'
$env:PYTHONPATH = 'D:\桌面\two'
$py = 'C:\Users\19183\.dsh\tools\x-collect\venv\Scripts\python.exe'
$probe = 'docs\validation\v10\weibo-probe'
$out = "$probe\probe1.out.txt"
$err = "$probe\probe1.err.txt"
$evidence = "$probe\window_evidence.txt"

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class W32q {
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public struct RECT { public int L,T,R,B; }
}
'@

$started = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
"START_UTC=$started"
$procArgs = @('-X','utf8','-m','tools.selection.access.weibo',
              '--state-dir','docs\validation\v10\weibo-probe\state-probe1',
              '--batch-id','weibo-probe-1','--mode','authenticated-browser',
              '--profile','docs\validation\v10\weibo-probe\profile_empty',
              'search','学习计划模板','--limit','5','--visible','--timeout','60',
              '--diagnostics-dir','docs\validation\v10\weibo-probe\diag')
$proc = Start-Process -FilePath $py -ArgumentList $procArgs -WorkingDirectory (Get-Location).Path `
    -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
"PY_PID=$($proc.Id)"
$proc.Id | Out-File "$probe\probe1.pid" -Encoding ascii

$first = $null
$samples = 0
$ourPids = @()
for ($i = 0; $i -lt 600; $i++) {
    $alive = -not $proc.HasExited
    $ours = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'weibo-probe' })
    $ourPids = @($ours | Select-Object -ExpandProperty ProcessId)
    foreach ($p in $ours) {
        $gp = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $gp -or $gp.MainWindowHandle -eq 0) { continue }
        $handle = $gp.MainWindowHandle
        $rect = New-Object W32q+RECT
        [void][W32q]::GetWindowRect($handle, [ref]$rect)
        $row = [pscustomobject]@{
            sampled_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
            pid = $gp.Id
            title = $gp.MainWindowTitle
            handle = $handle
            visible = [W32q]::IsWindowVisible($handle)
            responding = $gp.Responding
            rect = "$($rect.L),$($rect.T),$($rect.R),$($rect.B)"
            process_alive_after = $alive
        }
        $samples++
        if ($null -eq $first) {
            $first = $row
            $row | ConvertTo-Json -Compress | Out-File $evidence -Encoding utf8
        }
        break
    }
    if ($first -and -not $alive) { break }
    if (-not $alive) { break }
    Start-Sleep -Milliseconds 300
}

if ($first) {
    "FIRST_WINDOW pid=$($first.pid) handle=$($first.handle) visible=$($first.visible) responding=$($first.responding) title=$($first.title) rect=$($first.rect)"
    "WINDOW_SAMPLES=$samples"
} else {
    "FIRST_WINDOW none (chrome procs seen for our profile: $($ourPids -join ','))"
}
"OUR_CHROME_PIDS=$($ourPids -join ',')"
$proc.WaitForExit(180000) | Out-Null
"PROC_EXITED=$($proc.HasExited) EXIT=$($proc.ExitCode)"
"FINISH_UTC=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
Get-Date -Format 'yyyy-MM-ddTHH:mm:sszzz'
