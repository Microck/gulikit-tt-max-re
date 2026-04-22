param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("backup", "restore")]
    [string]$Mode,

    [Parameter(Mandatory = $true)]
    [string]$Path,

    [int]$TimeoutSeconds = 300
)

$resolvedPath = [System.IO.Path]::GetFullPath($Path)
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

function Find-GuliKitApGVolume {
    while ((Get-Date) -lt $deadline) {
        $volume = Get-Volume | Where-Object { $_.FileSystemLabel -eq "GuliKit dat" } | Select-Object -First 1
        if ($volume -and $volume.DriveLetter) {
            return $volume
        }
        Start-Sleep -Milliseconds 500
    }

    throw "Timed out waiting for the GuliKit dat volume."
}

$volume = Find-GuliKitApGVolume
$controllerFile = "$($volume.DriveLetter):\Auto.apg"

if ($Mode -eq "backup") {
    if (-not (Test-Path $controllerFile)) {
        throw "Auto.apg was not found on the controller volume."
    }

    New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($resolvedPath)) | Out-Null
    Copy-Item -Force $controllerFile $resolvedPath
    $hash = (Get-FileHash $resolvedPath -Algorithm SHA256).Hash.ToLower()
    [pscustomobject]@{
        Mode = $Mode
        Source = $controllerFile
        Dest = $resolvedPath
        Sha256 = $hash
        Size = (Get-Item $resolvedPath).Length
    } | ConvertTo-Json -Compress
    exit 0
}

if (-not (Test-Path $resolvedPath)) {
    throw "Input file not found: $resolvedPath"
}

Copy-Item -Force $resolvedPath $controllerFile
$hash = (Get-FileHash $resolvedPath -Algorithm SHA256).Hash.ToLower()
[pscustomobject]@{
    Mode = $Mode
    Source = $resolvedPath
    Dest = $controllerFile
    Sha256 = $hash
    Size = (Get-Item $resolvedPath).Length
    Note = "The controller should power off automatically after the write completes."
} | ConvertTo-Json -Compress
