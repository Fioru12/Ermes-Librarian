<#
.SYNOPSIS
    Installatore Grafico Wizard di Ermes Knowledge per Windows
.DESCRIPTION
    Fornisce una procedura guidata grafica (GUI WPF) a passi per l'installazione,
    configurazione e primo avvio di Ermes Knowledge su Windows.
#>

param(
    [switch]$NoGui
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $PSScriptRoot
if (-not $scriptDir) { $scriptDir = (Get-Location).Path }

# Path utili
$projectRoot   = $scriptDir
$venvPython    = Join-Path $projectRoot ".venv-ermes\Scripts\python.exe"
$envFile       = Join-Path $projectRoot ".env"
$envExample    = Join-Path $projectRoot ".env.example"

# Funzioni di controllo prerequisiti
function Test-CommandExists {
    param([string]$cmd)
    $res = Get-Command $cmd -ErrorAction SilentlyContinue
    return ($null -ne $res)
}

function Get-PythonStatus {
    if (Test-CommandExists "python") {
        $v = (& python --version 2>&1)
        return @{ Found = $true; Version = $v; Cmd = "python" }
    } elseif (Test-CommandExists "py") {
        $v = (& py -3 --version 2>&1)
        return @{ Found = $true; Version = $v; Cmd = "py" }
    }
    return @{ Found = $false; Version = "Non installato"; Cmd = $null }
}

function Get-NodeStatus {
    if (Test-CommandExists "npm") {
        $v = (& npm --version 2>&1)
        return @{ Found = $true; Version = "npm v$v" }
    }
    return @{ Found = $false; Version = "Non installato" }
}

function Get-DockerStatus {
    if (Test-CommandExists "docker") {
        $v = (& docker --version 2>&1)
        return @{ Found = $true; Version = $v }
    }
    return @{ Found = $false; Version = "Non installato o non avviato" }
}

# Se l'utente richiede modalita' non grafica (fallback console)
if ($NoGui) {
    Write-Host "=== Ermes Knowledge Wizard (Console Mode) ===" -ForegroundColor Cyan
    & "$projectRoot\INSTALLA_ERMES.bat"
    exit 0
}

# Caricamento librerie WPF
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

[xml]$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Ermes Knowledge - Installazione Guidata (Setup Wizard)"
        Height="540" Width="760"
        WindowStartupLocation="CenterScreen"
        ResizeMode="CanMinimize"
        Background="#0F172A"
        FontFamily="Segoe UI">
    <Window.Resources>
        <Style TargetType="Button">
            <Setter Property="Padding" Value="14,6"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Foreground" Value="White"/>
            <Setter Property="Background" Value="#2563EB"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border Background="{TemplateBinding Background}" CornerRadius="6" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
    </Window.Resources>

    <Grid>
        <Grid.ColumnDefinitions>
            <ColumnDefinition Width="220"/>
            <ColumnDefinition Width="*"/>
        </Grid.ColumnDefinitions>

        <!-- Barra Laterale Sinistra (Branding e Passi) -->
        <Border Grid.Column="0" Background="#1E293B" BorderBrush="#334155" BorderThickness="0,0,1,0" Padding="20">
            <DockPanel LastChildFill="True">
                <!-- Header Branding -->
                <StackPanel DockPanel.Dock="Top" Margin="0,0,0,24">
                    <Border Width="64" Height="64" CornerRadius="14" Background="#2563EB" Margin="0,0,0,12" HorizontalAlignment="Left">
                        <TextBlock Text="EK" FontSize="26" FontWeight="Bold" Foreground="White" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                    </Border>
                    <TextBlock Text="Ermes Knowledge" FontSize="18" FontWeight="Bold" Foreground="White"/>
                    <TextBlock Text="v2.2.6 Enterprise Setup" FontSize="12" Foreground="#94A3B8" Margin="0,2,0,0"/>
                </StackPanel>

                <!-- Indicatori dei Passi del Wizard -->
                <StackPanel VerticalAlignment="Center">
                    <TextBlock x:Name="StepInd1" Text="1. Benvenuto" FontSize="13" Foreground="#38BDF8" FontWeight="Bold" Margin="0,8"/>
                    <TextBlock x:Name="StepInd2" Text="2. Modalita' Setup" FontSize="13" Foreground="#64748B" Margin="0,8"/>
                    <TextBlock x:Name="StepInd3" Text="3. Controllo Requisiti" FontSize="13" Foreground="#64748B" Margin="0,8"/>
                    <TextBlock x:Name="StepInd4" Text="4. Installazione" FontSize="13" Foreground="#64748B" Margin="0,8"/>
                    <TextBlock x:Name="StepInd5" Text="5. Completamento" FontSize="13" Foreground="#64748B" Margin="0,8"/>
                </StackPanel>

                <!-- Footer Laterale -->
                <TextBlock DockPanel.Dock="Bottom" Text="Sicuro - Local First - Evidence Based" FontSize="10" Foreground="#475569" TextWrapping="Wrap"/>
            </DockPanel>
        </Border>

        <!-- Area Contenuti Destra -->
        <Grid Grid.Column="1" Background="#0F172A" Margin="24">
            <Grid.RowDefinitions>
                <RowDefinition Height="*"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>

            <!-- PAGINA 1: BENVENUTO -->
            <StackPanel x:Name="Page1" Visibility="Visible" Grid.Row="0">
                <TextBlock Text="Benvenuto in Ermes Knowledge" FontSize="22" FontWeight="Bold" Foreground="White" Margin="0,0,0,8"/>
                <TextBlock Text="Piattaforma Sovrana di Enterprise Document Intelligence" FontSize="13" Foreground="#38BDF8" Margin="0,0,0,16"/>
                <TextBlock Text="Questa procedura guidata configurera' il sistema sul tuo computer in pochi minuti, preparando l'ambiente locale, i modelli di embedding e l'interfaccia web." FontSize="13" Foreground="#CBD5E1" TextWrapping="Wrap" LineHeight="20" Margin="0,0,0,16"/>
                
                <Border Background="#1E293B" CornerRadius="8" Padding="14" Margin="0,0,0,16">
                    <StackPanel>
                        <TextBlock Text="Caratteristiche Principali:" FontSize="13" FontWeight="SemiBold" Foreground="White" Margin="0,0,0,8"/>
                        <TextBlock Text="[x] 100% Locale e Privato: i tuoi file non lasciano il perimetro aziendale" FontSize="12" Foreground="#94A3B8" Margin="0,3"/>
                        <TextBlock Text="[x] Evidence-First: ogni risposta cita l'esatta pagina del documento" FontSize="12" Foreground="#94A3B8" Margin="0,3"/>
                        <TextBlock Text="[x] Streaming Real-Time: risposte istantanee token-by-token (SSE)" FontSize="12" Foreground="#94A3B8" Margin="0,3"/>
                        <TextBlock Text="[x] Multi-Formato: PDF con OCR, DOCX, XLSX, TXT, Markdown e NAS" FontSize="12" Foreground="#94A3B8" Margin="0,3"/>
                    </StackPanel>
                </Border>
                <TextBlock Text="Fai clic su 'Avanti' per selezionare la modalita' di installazione." FontSize="12" Foreground="#64748B"/>
            </StackPanel>

            <!-- PAGINA 2: MODALITA INSTALLAZIONE -->
            <StackPanel x:Name="Page2" Visibility="Collapsed" Grid.Row="0">
                <TextBlock Text="Scegli la modalita' di installazione" FontSize="20" FontWeight="Bold" Foreground="White" Margin="0,0,0,6"/>
                <TextBlock Text="Seleziona come desideri eseguire Ermes Knowledge sul tuo computer." FontSize="13" Foreground="#94A3B8" Margin="0,0,0,16"/>

                <Border Background="#1E293B" CornerRadius="8" Padding="14" Margin="0,0,0,12">
                    <StackPanel>
                        <RadioButton x:Name="RadioStandalone" GroupName="Mode" IsChecked="True" Foreground="White" FontSize="14" FontWeight="SemiBold">
                            <TextBlock Text="Installazione Standalone (Consigliata per Windows)" Margin="6,0,0,0"/>
                        </RadioButton>
                        <TextBlock Text="Esegue Ermes direttamente su Windows creando un ambiente Python isolato. Ideale per la massima velocita' e per PC individuali." FontSize="12" Foreground="#94A3B8" Margin="26,4,0,0" TextWrapping="Wrap"/>
                    </StackPanel>
                </Border>

                <Border Background="#1E293B" CornerRadius="8" Padding="14" Margin="0,0,0,16">
                    <StackPanel>
                        <RadioButton x:Name="RadioDocker" GroupName="Mode" Foreground="White" FontSize="14" FontWeight="SemiBold">
                            <TextBlock Text="Installazione con Docker Compose" Margin="6,0,0,0"/>
                        </RadioButton>
                        <TextBlock Text="Esegue l'intero stack (Frontend + Backend + Nginx) all'interno di container Docker. Ideale per server aziendali o sistemisti." FontSize="12" Foreground="#94A3B8" Margin="26,4,0,0" TextWrapping="Wrap"/>
                    </StackPanel>
                </Border>

                <CheckBox x:Name="CheckDesktopShortcut" IsChecked="True" Foreground="White" FontSize="13" Margin="4,4,0,0">
                    <TextBlock Text="Crea un'icona di avvio rapido sul Desktop di Windows" Margin="4,0,0,0"/>
                </CheckBox>
            </StackPanel>

            <!-- PAGINA 3: CONTROLLO REQUISITI -->
            <StackPanel x:Name="Page3" Visibility="Collapsed" Grid.Row="0">
                <TextBlock Text="Verifica dei Prerequisiti" FontSize="20" FontWeight="Bold" Foreground="White" Margin="0,0,0,6"/>
                <TextBlock Text="Controllo dei componenti necessari prima di procedere all'installazione." FontSize="13" Foreground="#94A3B8" Margin="0,0,0,16"/>

                <Border Background="#1E293B" CornerRadius="8" Padding="14" Margin="0,0,0,12">
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="36"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="Auto"/>
                        </Grid.ColumnDefinitions>
                        <TextBlock Text="PY" FontSize="14" FontWeight="Bold" Foreground="#38BDF8" VerticalAlignment="Center" Margin="0,0,8,0"/>
                        <StackPanel Grid.Column="1" VerticalAlignment="Center">
                            <TextBlock Text="Python (3.11 o 3.12)" FontSize="13" FontWeight="SemiBold" Foreground="White"/>
                            <TextBlock x:Name="TxtPythonStatus" Text="Verifica in corso..." FontSize="12" Foreground="#94A3B8"/>
                        </StackPanel>
                        <TextBlock x:Name="BadgePython" Grid.Column="2" Text="OK" FontSize="13" FontWeight="Bold" Foreground="#EAB308" VerticalAlignment="Center"/>
                    </Grid>
                </Border>

                <Border Background="#1E293B" CornerRadius="8" Padding="14" Margin="0,0,0,12">
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="36"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="Auto"/>
                        </Grid.ColumnDefinitions>
                        <TextBlock Text="JS" FontSize="14" FontWeight="Bold" Foreground="#38BDF8" VerticalAlignment="Center" Margin="0,0,8,0"/>
                        <StackPanel Grid.Column="1" VerticalAlignment="Center">
                            <TextBlock Text="Node.js e npm (Frontend React)" FontSize="13" FontWeight="SemiBold" Foreground="White"/>
                            <TextBlock x:Name="TxtNodeStatus" Text="Verifica in corso..." FontSize="12" Foreground="#94A3B8"/>
                        </StackPanel>
                        <TextBlock x:Name="BadgeNode" Grid.Column="2" Text="OK" FontSize="13" FontWeight="Bold" Foreground="#EAB308" VerticalAlignment="Center"/>
                    </Grid>
                </Border>

                <Border Background="#1E293B" CornerRadius="8" Padding="14" Margin="0,0,0,12">
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="36"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="Auto"/>
                        </Grid.ColumnDefinitions>
                        <TextBlock Text="DK" FontSize="14" FontWeight="Bold" Foreground="#38BDF8" VerticalAlignment="Center" Margin="0,0,8,0"/>
                        <StackPanel Grid.Column="1" VerticalAlignment="Center">
                            <TextBlock Text="Docker Desktop (Opzionale)" FontSize="13" FontWeight="SemiBold" Foreground="White"/>
                            <TextBlock x:Name="TxtDockerStatus" Text="Verifica in corso..." FontSize="12" Foreground="#94A3B8"/>
                        </StackPanel>
                        <TextBlock x:Name="BadgeDocker" Grid.Column="2" Text="--" FontSize="13" FontWeight="Bold" Foreground="#94A3B8" VerticalAlignment="Center"/>
                    </Grid>
                </Border>

                <TextBlock x:Name="TxtPrereqAdvice" Text="Tutti i prerequisiti principali sono soddisfatti. Premi 'Installa Ora' per procedere." FontSize="12" Foreground="#38BDF8" Margin="4,4,0,0" TextWrapping="Wrap"/>
            </StackPanel>

            <!-- PAGINA 4: INSTALLAZIONE IN CORSO -->
            <StackPanel x:Name="Page4" Visibility="Collapsed" Grid.Row="0">
                <TextBlock Text="Installazione in corso..." FontSize="20" FontWeight="Bold" Foreground="White" Margin="0,0,0,6"/>
                <TextBlock x:Name="TxtInstallStatus" Text="Preparazione ambiente..." FontSize="13" Foreground="#38BDF8" Margin="0,0,0,16"/>

                <ProgressBar x:Name="InstallProgressBar" Height="10" Value="10" Maximum="100" Margin="0,0,0,16" Background="#1E293B" Foreground="#2563EB"/>

                <Border Background="#1E293B" CornerRadius="8" Padding="12" Height="200">
                    <ScrollViewer x:Name="LogScrollViewer" VerticalScrollBarVisibility="Auto">
                        <TextBox x:Name="TxtInstallLog" Background="Transparent" Foreground="#94A3B8" BorderThickness="0" FontFamily="Consolas" FontSize="11" TextWrapping="Wrap" IsReadOnly="True"/>
                    </ScrollViewer>
                </Border>
            </StackPanel>

            <!-- PAGINA 5: COMPLETAMENTO -->
            <StackPanel x:Name="Page5" Visibility="Collapsed" Grid.Row="0">
                <TextBlock Text="Installazione Completata con Successo!" FontSize="22" FontWeight="Bold" Foreground="#4ADE80" Margin="0,0,0,6"/>
                <TextBlock Text="Ermes Knowledge e' stato configurato ed e' pronto all'uso." FontSize="13" Foreground="#CBD5E1" Margin="0,0,0,16"/>

                <Border Background="#1E293B" CornerRadius="8" Padding="14" Margin="0,0,0,16">
                    <StackPanel>
                        <TextBlock Text="Credenziali di Accesso Generate:" FontSize="13" FontWeight="SemiBold" Foreground="White" Margin="0,0,0,8"/>
                        <TextBlock Text="URL Accesso: http://localhost:3000 (o porta 8000 con Docker)" FontSize="12" Foreground="#38BDF8" Margin="0,2"/>
                        <TextBlock Text="Username: admin" FontSize="12" Foreground="#94A3B8" Margin="0,2"/>
                        <TextBlock Text="File credenziali: salvate in sicurezza nel file LOCAL_LOGIN.txt" FontSize="12" Foreground="#94A3B8" Margin="0,2"/>
                    </StackPanel>
                </Border>

                <CheckBox x:Name="CheckLaunchNow" IsChecked="True" Foreground="White" FontSize="13" Margin="4,0,0,12">
                    <TextBlock Text="Avvia subito Ermes Knowledge e apri il browser" Margin="4,0,0,0"/>
                </CheckBox>

                <TextBlock Text="Puoi avviare Ermes in qualunque momento dal Desktop o con il file 'AVVIA_ERMES.bat'." FontSize="12" Foreground="#64748B" TextWrapping="Wrap"/>
            </StackPanel>

            <!-- BARRA PULSANTI DI NAVIGAZIONE IN BASSO -->
            <Border Grid.Row="1" BorderBrush="#334155" BorderThickness="0,1,0,0" Padding="0,16,0,0">
                <DockPanel LastChildFill="False">
                    <Button x:Name="BtnCancel" Content="Annulla" DockPanel.Dock="Left" Background="#334155" Width="90"/>
                    <Button x:Name="BtnNext" Content="Avanti >" DockPanel.Dock="Right" Width="110"/>
                    <Button x:Name="BtnBack" Content="&lt; Indietro" DockPanel.Dock="Right" Background="#334155" Width="90" Margin="0,0,10,0" Visibility="Collapsed"/>
                </DockPanel>
            </Border>
        </Grid>
    </Grid>
</Window>
"@

$reader = (New-Object System.Xml.XmlNodeReader $xaml)
$window = [System.Windows.Markup.XamlReader]::Load($reader)

# Mappa elementi per nome
$xaml.SelectNodes("//*[@*[local-name()='Name']]") | ForEach-Object {
    Set-Variable -Name ($_.Name) -Value $window.FindName($_.Name) -Scope Script
}

# Variabile di stato del passo corrente
$script:CurrentStep = 1

function Update-WizardUI {
    # Reset indicatori laterali
    $StepInd1.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#64748B")
    $StepInd2.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#64748B")
    $StepInd3.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#64748B")
    $StepInd4.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#64748B")
    $StepInd5.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#64748B")
    $StepInd1.FontWeight = [System.Windows.FontWeights]::Normal
    $StepInd2.FontWeight = [System.Windows.FontWeights]::Normal
    $StepInd3.FontWeight = [System.Windows.FontWeights]::Normal
    $StepInd4.FontWeight = [System.Windows.FontWeights]::Normal
    $StepInd5.FontWeight = [System.Windows.FontWeights]::Normal

    $Page1.Visibility = [System.Windows.Visibility]::Collapsed
    $Page2.Visibility = [System.Windows.Visibility]::Collapsed
    $Page3.Visibility = [System.Windows.Visibility]::Collapsed
    $Page4.Visibility = [System.Windows.Visibility]::Collapsed
    $Page5.Visibility = [System.Windows.Visibility]::Collapsed

    $activeBrush = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#38BDF8")

    switch ($script:CurrentStep) {
        1 {
            $Page1.Visibility = [System.Windows.Visibility]::Visible
            $StepInd1.Foreground = $activeBrush
            $StepInd1.FontWeight = [System.Windows.FontWeights]::Bold
            $BtnBack.Visibility = [System.Windows.Visibility]::Collapsed
            $BtnNext.Content = "Avanti >"
            $BtnNext.IsEnabled = $true
        }
        2 {
            $Page2.Visibility = [System.Windows.Visibility]::Visible
            $StepInd2.Foreground = $activeBrush
            $StepInd2.FontWeight = [System.Windows.FontWeights]::Bold
            $BtnBack.Visibility = [System.Windows.Visibility]::Visible
            $BtnNext.Content = "Avanti >"
            $BtnNext.IsEnabled = $true
        }
        3 {
            $Page3.Visibility = [System.Windows.Visibility]::Visible
            $StepInd3.Foreground = $activeBrush
            $StepInd3.FontWeight = [System.Windows.FontWeights]::Bold
            $BtnBack.Visibility = [System.Windows.Visibility]::Visible
            $BtnNext.Content = "Installa Ora"
            Run-PrereqCheck
        }
        4 {
            $Page4.Visibility = [System.Windows.Visibility]::Visible
            $StepInd4.Foreground = $activeBrush
            $StepInd4.FontWeight = [System.Windows.FontWeights]::Bold
            $BtnBack.Visibility = [System.Windows.Visibility]::Collapsed
            $BtnNext.Visibility = [System.Windows.Visibility]::Collapsed
            $BtnCancel.IsEnabled = $false
        }
        5 {
            $Page5.Visibility = [System.Windows.Visibility]::Visible
            $StepInd5.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#4ADE80")
            $StepInd5.FontWeight = [System.Windows.FontWeights]::Bold
            $BtnBack.Visibility = [System.Windows.Visibility]::Collapsed
            $BtnNext.Visibility = [System.Windows.Visibility]::Visible
            $BtnNext.Content = "Fine e Avvia"
            $BtnNext.IsEnabled = $true
            $BtnCancel.Visibility = [System.Windows.Visibility]::Collapsed
        }
    }
}

function Run-PrereqCheck {
    $py = Get-PythonStatus
    if ($py.Found) {
        $TxtPythonStatus.Text = $py.Version
        $BadgePython.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#4ADE80")
        $BadgePython.Text = "OK"
    } else {
        $TxtPythonStatus.Text = "Non trovato. Scarica Python 3.11/3.12 da python.org"
        $BadgePython.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#EF4444")
        $BadgePython.Text = "NO"
    }

    $node = Get-NodeStatus
    if ($node.Found) {
        $TxtNodeStatus.Text = $node.Version
        $BadgeNode.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#4ADE80")
        $BadgeNode.Text = "OK"
    } else {
        $TxtNodeStatus.Text = "npm non trovato. Necessario solo per compilare frontend locale."
        $BadgeNode.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#EAB308")
        $BadgeNode.Text = "WARN"
    }

    $dock = Get-DockerStatus
    if ($dock.Found) {
        $TxtDockerStatus.Text = $dock.Version
        $BadgeDocker.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#4ADE80")
        $BadgeDocker.Text = "OK"
    } else {
        $TxtDockerStatus.Text = "Non attivo (necessario solo per modalita' Docker)"
        $BadgeDocker.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#94A3B8")
        $BadgeDocker.Text = "--"
    }

    if ($RadioDocker.IsChecked -and -not $dock.Found) {
        $BtnNext.IsEnabled = $false
        $TxtPrereqAdvice.Text = "La modalita' Docker richiede Docker Desktop in esecuzione."
        $TxtPrereqAdvice.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#EF4444")
    } elseif ($RadioStandalone.IsChecked -and -not $py.Found) {
        $BtnNext.IsEnabled = $false
        $TxtPrereqAdvice.Text = "Python 3.11+ e' necessario per l'installazione Standalone."
        $TxtPrereqAdvice.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#EF4444")
    } else {
        $BtnNext.IsEnabled = $true
        $TxtPrereqAdvice.Text = "Prerequisiti verificati. Fai clic su 'Installa Ora' per avviare il processo."
        $TxtPrereqAdvice.Foreground = [System.Windows.Media.BrushConverter]::new().ConvertFromString("#38BDF8")
    }
}

# Esecuzione Installazione
function Start-InstallationProcess {
    $script:CurrentStep = 4
    Update-WizardUI

    $useDocker = $RadioDocker.IsChecked
    $createShortcut = $CheckDesktopShortcut.IsChecked

    $worker = [System.ComponentModel.BackgroundWorker]::new()
    $worker.WorkerReportsProgress = $true

    $worker.DoWork += {
        param($sender, $e)

        if ($useDocker) {
            $sender.ReportProgress(20, "Avvio configurazione Docker Compose...")
            Start-Sleep -Seconds 1
            $sender.ReportProgress(50, "Creazione container e build immagini...")
            cmd.exe /c "docker compose up -d" 2>&1 | Out-Null
            $sender.ReportProgress(100, "Container Docker pronti!")
        } else {
            $sender.ReportProgress(15, "Controllo ambiente virtuale .venv-ermes...")
            $py = Get-PythonStatus
            $pyCmd = $py.Cmd
            if (-not (Test-Path "$projectRoot\.venv-ermes")) {
                $sender.ReportProgress(25, "Creazione ambiente virtuale Python...")
                & $pyCmd -m venv "$projectRoot\.venv-ermes"
            } else {
                $sender.ReportProgress(30, "Ambiente virtuale .venv-ermes presente.")
            }

            $sender.ReportProgress(40, "Aggiornamento pip...")
            & "$projectRoot\.venv-ermes\Scripts\python.exe" -m pip install --upgrade pip 2>&1 | Out-Null

            $sender.ReportProgress(55, "Installazione requisiti backend (FastAPI, Docling)...")
            & "$projectRoot\.venv-ermes\Scripts\pip.exe" install -r "$projectRoot\requirements.txt" 2>&1 | Out-Null

            if (Test-Path "$projectRoot\frontend\package.json") {
                $sender.ReportProgress(75, "Preparazione frontend React...")
                if (Test-CommandExists "npm") {
                    cmd.exe /c "npm --prefix `"$projectRoot\frontend`" install" 2>&1 | Out-Null
                    $sender.ReportProgress(85, "Compilazione bundle frontend...")
                    cmd.exe /c "npm --prefix `"$projectRoot\frontend`" run build" 2>&1 | Out-Null
                }
            }

            $sender.ReportProgress(90, "Configurazione .env e generazione credenziali...")
            if (-not (Test-Path "$projectRoot\.env") -and (Test-Path "$projectRoot\.env.example")) {
                Copy-Item "$projectRoot\.env.example" "$projectRoot\.env"
            }
            & "$projectRoot\.venv-ermes\Scripts\python.exe" "$projectRoot\scripts\provision_local_demo_auth.py" --write 2>&1 | Out-Null

            if ($createShortcut) {
                $sender.ReportProgress(95, "Creazione icona Desktop Ermes Knowledge...")
                & powershell.exe -ExecutionPolicy Bypass -File "$projectRoot\scripts\CREA_COLLEGAMENTO_DESKTOP.ps1" 2>&1 | Out-Null
            }

            $sender.ReportProgress(100, "Installazione completata con successo!")
        }
    }

    $worker.ProgressChanged += {
        param($sender, $e)
        $InstallProgressBar.Value = $e.ProgressPercentage
        $TxtInstallStatus.Text = $e.UserState
        $TxtInstallLog.AppendText("[$((Get-Date).ToString('HH:mm:ss'))] $($e.UserState)`r`n")
        $LogScrollViewer.ScrollToEnd()
    }

    $worker.RunWorkerCompleted += {
        param($sender, $e)
        $script:CurrentStep = 5
        Update-WizardUI
    }

    $worker.RunWorkerAsync()
}

# Eventi Pulsanti
$BtnNext.Add_Click({
    if ($script:CurrentStep -eq 1) {
        $script:CurrentStep = 2
        Update-WizardUI
    } elseif ($script:CurrentStep -eq 2) {
        $script:CurrentStep = 3
        Update-WizardUI
    } elseif ($script:CurrentStep -eq 3) {
        Start-InstallationProcess
    } elseif ($script:CurrentStep -eq 5) {
        if ($CheckLaunchNow.IsChecked) {
            if ($RadioDocker.IsChecked) {
                Start-Process "$projectRoot\AVVIA_DOCKER.bat"
            } else {
                Start-Process "$projectRoot\AVVIA_ERMES.bat"
            }
        }
        $window.Close()
    }
})

$BtnBack.Add_Click({
    if ($script:CurrentStep -gt 1) {
        $script:CurrentStep--
        Update-WizardUI
    }
})

$BtnCancel.Add_Click({
    $window.Close()
})

# Avvio finestra
Update-WizardUI
$window.ShowDialog() | Out-Null
