# prova_avviso.ps1
# Invia ad Alertmanager un avviso di prova e, dopo qualche secondo, il suo "risolto", per
# verificare che la notifica arrivi davvero dove l'hai configurata (Slack, Teams, webhook).
#
# Prima: avvia il monitoraggio (docker compose -f docker-compose.monitoring.yml up -d) e
# configura il destinatario (docs/MONITORING.md, deploy/monitoring/alertmanager.slack-teams.example.yml).
#
# Uso:  .\scripts\prova_avviso.ps1 [-Url http://localhost:9093] [-Secondi 20]

param(
    [string]$Url = "http://localhost:9093",
    [int]$Secondi = 20
)

$adesso = (Get-Date).ToUniversalTime()
function Invia([datetime]$fine) {
    $avviso = @(@{
        labels      = @{ alertname = "ErmesProvaAvviso"; severity = "warning"; origine = "prova_avviso.ps1" }
        annotations = @{ summary = "Avviso di prova di Ermes: se lo leggi, la consegna funziona." }
        startsAt    = $adesso.ToString("o")
        endsAt      = $fine.ToString("o")
    })
    Invoke-RestMethod -Method Post -Uri "$Url/api/v2/alerts" -ContentType "application/json" -Body (ConvertTo-Json -InputObject $avviso -Depth 5) | Out-Null
}

try {
    Invoke-RestMethod -Uri "$Url/-/ready" | Out-Null
} catch {
    Write-Host "Alertmanager non risponde su $Url. Avvia prima il monitoraggio." -ForegroundColor Red
    exit 1
}

Invia $adesso.AddMinutes(10)
Write-Host "Avviso di prova inviato (arriva dopo il 'group_wait' di 30 secondi)." -ForegroundColor Green
Write-Host "Attendo $Secondi secondi e poi lo chiudo, cosi' arriva anche il messaggio 'risolto'..."
Start-Sleep -Seconds ([Math]::Max($Secondi, 35))
Invia (Get-Date).ToUniversalTime()
Write-Host "Chiuso. Controlla il canale: devono essere arrivati un messaggio FIRING e uno RESOLVED." -ForegroundColor Green
