# Shut down BOTH servers (live 8000 + dev 8001). Run this "after yourself".
foreach ($port in 8000, 8001) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "stopped server on port $port" -ForegroundColor Yellow
    } else {
        Write-Host "nothing on port $port" -ForegroundColor DarkGray
    }
}
