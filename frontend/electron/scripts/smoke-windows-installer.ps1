param(
  [Parameter(Mandatory=$true)][string]$ArtifactDirectory,
  [Parameter(Mandatory=$true)][string]$EvidenceDirectory
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Path $EvidenceDirectory -Force | Out-Null
$EvidenceDirectory = (Resolve-Path $EvidenceDirectory).Path
$installDirectory = Join-Path $env:RUNNER_TEMP 'UniMindInstallerSmoke'
$exePath = Join-Path $installDirectory 'UniMind.exe'
$report = [ordered]@{ os = [Environment]::OSVersion.VersionString; passed = $false }
function Invoke-Browser {
  param([string[]]$BrowserArguments)
  $output = & agent-browser --session unimind-installer-smoke @BrowserArguments
  if ($LASTEXITCODE -ne 0) { throw "Browser check failed: $($BrowserArguments[0])" }
  return ($output -join "`n")
}
try {
  $installers = @(Get-ChildItem -LiteralPath $ArtifactDirectory -Filter '*-setup.exe')
  if ($installers.Count -ne 1) { throw 'Expected exactly one installer' }
  $installer = $installers[0]
  $report.installer = $installer.Name
  $report.sha256 = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash
  $manifest = Get-Content (Join-Path $ArtifactDirectory 'windows-sha256.txt') -Raw
  if ($manifest -notmatch [regex]::Escape($report.sha256)) { throw 'Installer hash differs from build artifact' }
  if (Test-Path $installDirectory) { throw 'Install directory must not already exist' }
  $process = Start-Process -FilePath $installer.FullName -ArgumentList '/S', '/currentuser', "/D=$installDirectory" -WindowStyle Hidden -PassThru
  if (-not $process.WaitForExit(180000)) { throw 'Installer timed out' }
  $report.installExitCode = $process.ExitCode
  if ($process.ExitCode -ne 0) { throw "Installer exit code: $($process.ExitCode)" }
  foreach ($file in @('UniMind.exe', 'resources\app.asar', 'icudtl.dat', 'ffmpeg.dll', 'Uninstall UniMind.exe')) {
    if (-not (Test-Path (Join-Path $installDirectory $file))) { throw "Missing installed file: $file" }
  }
  $report.installedFilesPresent = $true
  $shortcutShell = New-Object -ComObject WScript.Shell
  $shortcutPaths = @(
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'UniMind.lnk'),
    (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'UniMind.lnk')
  )
  $shortcut = $shortcutPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $shortcut) { throw 'Desktop shortcut was not created' }
  if ($shortcutShell.CreateShortcut($shortcut).TargetPath -ne $exePath) { throw 'Desktop shortcut targets the wrong application' }
  $report.desktopShortcutValid = $true
  # Stop only an automatic launch of this fresh installation, to relaunch with diagnostics.
  Get-Process UniMind -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exePath } | Stop-Process
  $launchArgs = @('--remote-debugging-port=9333', '--enable-logging', "--log-file=$EvidenceDirectory\electron.log")
  $appProcess = Start-Process -FilePath $exePath -ArgumentList $launchArgs -WindowStyle Hidden -PassThru
  $deadline = (Get-Date).AddSeconds(90)
  $ready = $false
  do {
    try { $null = Invoke-RestMethod 'http://127.0.0.1:9333/json/version' -TimeoutSec 2; $ready = $true } catch { Start-Sleep -Seconds 2 }
  } until ($ready -or (Get-Date) -gt $deadline)
  if (-not $ready) { throw 'Installed app did not expose a working renderer' }
  Invoke-Browser -BrowserArguments @('connect','9333') | Out-Null
  $deadline = (Get-Date).AddSeconds(90)
  do {
    $snapshot = Invoke-Browser -BrowserArguments @('snapshot','-i')
    $snapshot | Set-Content (Join-Path $EvidenceDirectory 'login-snapshot.txt') -Encoding utf8
    if ($snapshot -match '通过浏览器登录') { break }
    Start-Sleep -Seconds 3
  } until ((Get-Date) -gt $deadline)
  Invoke-Browser -BrowserArguments @('screenshot',(Join-Path $EvidenceDirectory 'installed-login.png')) | Out-Null
  if ($snapshot -notmatch '通过浏览器登录') { throw 'Online desktop login interface did not appear' }
  $url = Invoke-Browser -BrowserArguments @('get','url')
  if ($url.Trim() -ne 'https://unimind-ai.com/login') { throw 'Unexpected login URL' }
  $report.loginPageLoaded = $true
  $bridge = Invoke-Browser -BrowserArguments @('eval','(async () => { if (!window.unimindDesktop) throw new Error("Desktop bridge missing"); await window.unimindDesktop.getState(); return "desktop-bridge-ok"; })()')
  if ($bridge -notmatch 'desktop-bridge-ok') { throw 'Desktop bridge did not respond' }
  $report.desktopBridgeResponded = $true
  Invoke-Browser -BrowserArguments @('reload') | Out-Null
  $deadline = (Get-Date).AddSeconds(60)
  do {
    $snapshot = Invoke-Browser -BrowserArguments @('snapshot','-i')
    if ($snapshot -match '通过浏览器登录') { break }
    Start-Sleep -Seconds 2
  } until ((Get-Date) -gt $deadline)
  if ($snapshot -notmatch '通过浏览器登录') { throw 'Login page failed after reload' }
  $report.reloadPassed = $true
  Invoke-Browser -BrowserArguments @('errors') | Set-Content (Join-Path $EvidenceDirectory 'page-errors.txt') -Encoding utf8
  $report.passed = $true
} catch {
  $report.error = $_.Exception.Message
  throw
} finally {
  $report | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $EvidenceDirectory 'result.json') -Encoding utf8
  Get-Process UniMind -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exePath } | Stop-Process -ErrorAction SilentlyContinue
}
