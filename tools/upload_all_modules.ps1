# upload_all_modules.ps1  -  validates, dry-runs, then uploads every finished module folder.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File C:\kampuslink-content\tools\upload_all_modules.ps1
# Idempotent: running it again just updates the same lessons (ids never change).
# v2: also uploads figures on cards/questions, practice.json and exams.json (needs backend file 15). Add -Basic to skip those.
param([switch]$Basic)
$extra = @("--sets"); if (-not $Basic) { $extra += "--full" }
Set-Location C:\kampuslink-content
Write-Host ("Folder: " + (Get-Location))

# Modules NOT ready yet (Maths 3 = 839, Mecanique des fluides = 841). Add ids here to skip more.
$skip = @(839, 841)

# Safety: this old copy of the Python content must never be uploaded as module 904.
if (Test-Path "mining\L2\S4\904_methodes_numeriques") {
  Write-Host "STOP: delete mining\L2\S4\904_methodes_numeriques first (it is the Python copy; Python lives in S3\994_python)." -ForegroundColor Red
  return
}

$mods = @()
foreach ($sem in "mining\L2\S3", "mining\L2\S4") {
  if (-not (Test-Path $sem)) { continue }
  foreach ($d in Get-ChildItem $sem -Directory) {
    if ($d.Name -match '^(\d+)_') {
      $id = [int]$Matches[1]
      if ($skip -contains $id) { Write-Host ("skip " + $d.Name); continue }
      if (-not (Get-ChildItem $d.FullName -Directory -Filter "chapter_*")) { Write-Host ("no chapters yet: " + $d.Name); continue }
      $mods += [pscustomobject]@{ Id = $id; Name = $d.Name; Path = $d.FullName }
    }
  }
}
Write-Host ""
Write-Host "Modules to upload:" -ForegroundColor Cyan
$mods | ForEach-Object { Write-Host ("  " + $_.Id + "  " + $_.Name) }

# 1) optional validators if the tools exist
foreach ($m in $mods) {
  foreach ($c in Get-ChildItem $m.Path -Directory -Filter "chapter_*") {
    if (Test-Path "tools\validate_content.py") { python tools\validate_content.py $c.FullName | Select-String -Pattern "ERROR|FAIL" }
    if (($m.Id -eq 842) -and (Test-Path "tools\chem_check.py")) { python tools\chem_check.py --file $c.FullName | Select-String -Pattern "ERROR|FAIL" }
  }
}

# 2) dry run for all; stop on the first failure
foreach ($m in $mods) {
  Write-Host ("`n--- DRY RUN " + $m.Id + " " + $m.Name) -ForegroundColor Yellow
  python tools\import_content.py --module-dir $m.Path --module-id $m.Id --dry-run @extra
  if ($LASTEXITCODE -ne 0) { Write-Host ("STOP: dry run failed for " + $m.Name) -ForegroundColor Red; return }
}

# 3) real upload
if (-not $env:KAMPUS_SUPABASE_URL) { $env:KAMPUS_SUPABASE_URL = Read-Host "Supabase URL (https://xxxx.supabase.co)" }
if (-not $env:KAMPUS_SERVICE_KEY)  { $env:KAMPUS_SERVICE_KEY  = Read-Host "service key" }
$ok = Read-Host "All dry runs passed. Type YES to upload and publish"
if ($ok -ne "YES") { Write-Host "Cancelled."; return }
foreach ($m in $mods) {
  Write-Host ("`n=== UPLOAD " + $m.Id + " " + $m.Name) -ForegroundColor Green
  python tools\import_content.py --module-dir $m.Path --module-id $m.Id --publish @extra
  if ($LASTEXITCODE -ne 0) { Write-Host ("STOP: upload failed for " + $m.Name + " - fix it, then run the script again (safe to repeat)") -ForegroundColor Red; return }
}
Write-Host "`nALL DONE." -ForegroundColor Green
