Write-Host "🚀 Lokal Ajan kuruluyor..." -ForegroundColor Cyan

$InstallDir = Join-Path $HOME ".lokal-ajan"

if (-Not (Test-Path "pyproject.toml")) {
    Write-Host "📦 GitHub'dan proje indiriliyor..."
    if (Test-Path $InstallDir) {
        Write-Host "🔄 Mevcut kurulum güncelleniyor..."
        Set-Location $InstallDir
        git pull origin main
    } else {
        git clone https://github.com/ilhanakd-max/Local_Ajan.git $InstallDir
        Set-Location $InstallDir
    }
} else {
    $InstallDir = (Get-Location).Path
}

Write-Host "🐍 Python sanal ortamı oluşturuluyor..."
if (-Not (Test-Path ".venv")) {
    python -m venv .venv
}

Write-Host "📦 Bağımlılıklar yükleniyor..."
& ".\.venv\Scripts\python.exe" -m pip install -e .

Write-Host "🔗 Terminal 'localajan' fonksiyonu Profile dosyasına ekleniyor..."
$ProfilePath = $PROFILE
if (-Not (Test-Path (Split-Path $ProfilePath))) {
    New-Item -Type Directory -Path (Split-Path $ProfilePath) -Force | Out-Null
}
if (-Not (Test-Path $ProfilePath)) {
    New-Item -Type File -Path $ProfilePath -Force | Out-Null
}

$FunctionCode = @"

function localajan {
    & `"$InstallDir\.venv\Scripts\python.exe`" -m lokal_ajan.cli `$args
}
"@

$ProfileContent = Get-Content $ProfilePath -ErrorAction SilentlyContinue
if ($ProfileContent -notmatch "function localajan") {
    Add-Content -Path $ProfilePath -Value $FunctionCode
} else {
    Write-Host "✅ Kısayol zaten profilinizde mevcut."
}

Write-Host "`n🎉 KURULUM BAŞARIYLA TAMAMLANDI! 🎉" -ForegroundColor Green
Write-Host "👉 Yeni bir PowerShell penceresi açın veya şunu çalıştırın:"
Write-Host "    . `$PROFILE"
Write-Host "👉 Ardından istediğiniz yerde ajanı başlatabilirsiniz:"
Write-Host "    localajan" -ForegroundColor Yellow
