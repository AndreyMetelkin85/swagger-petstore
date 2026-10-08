param([string]$Tag = 'latest')
$ErrorActionPreference = 'Stop'
if ($Tag -notmatch '^(latest|sha-[a-f0-9]{40})$') { throw 'Use latest or a verified sha-<40 hex> release tag.' }
$projectPath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectPath
try {
    $configuration = docker compose config --format json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration is invalid.' }
    $imageRepository = $configuration.services.petstore.image -replace ':[^/:]+$', ''
    $targetImage = "$($imageRepository):$Tag"
    docker pull $targetImage
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the verified release.' }
    $image = docker image inspect $targetImage | ConvertFrom-Json
    $revision = $image.Config.Labels.'org.opencontainers.image.revision'
    if ($revision -notmatch '^[a-f0-9]{40}$') { throw 'Image is missing its release revision.' }
    if ($Tag -like 'sha-*' -and $revision -ne $Tag.Substring(4)) { throw 'Image revision does not match the requested release.' }
    $running = docker ps --filter name=^/swagger-petstore$ --format '{{.Image}}'
    if ($running) {
        $current = docker inspect swagger-petstore | ConvertFrom-Json
        if ($current.Image -eq $image.Id -and $current.State.Health.Status -eq 'healthy') {
            Write-Output "Already running the verified release $revision."
            return
        }
    }
    $oldTag = $env:PETSTORE_IMAGE_TAG
    try {
        $env:PETSTORE_IMAGE_TAG = $Tag
        docker compose up -d --no-build --pull never --wait --wait-timeout 300
        if ($LASTEXITCODE -ne 0) { throw 'Release did not become healthy. Data volumes were preserved.' }
    } finally {
        if ($null -eq $oldTag) { Remove-Item Env:PETSTORE_IMAGE_TAG -ErrorAction SilentlyContinue } else { $env:PETSTORE_IMAGE_TAG = $oldTag }
    }
    Write-Output "Running verified release $revision. Database, media and mail volumes were preserved."
} finally {
    Pop-Location
}
