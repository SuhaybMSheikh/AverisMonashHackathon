[CmdletBinding()]
param(
    [string]$ProjectId = "averismonashhackathon-509310",
    [string]$Region = "asia-southeast1",
    [string]$Repository = "averis-demo",
    [string]$Service = "document-desk-demo",
    [string]$Tag = "demo"
)

$ErrorActionPreference = "Stop"

$gcloud = Get-Command gcloud -ErrorAction SilentlyContinue
if ($null -eq $gcloud) {
    $sdkPath = Join-Path $env:LOCALAPPDATA "Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
    if (-not (Test-Path -LiteralPath $sdkPath)) {
        throw "Google Cloud SDK was not found. Install it or add gcloud to PATH."
    }
    $gcloudPath = $sdkPath
} else {
    $gcloudPath = $gcloud.Source
}

& $gcloudPath config set project $ProjectId | Out-Null
$billingEnabled = (& $gcloudPath billing projects describe $ProjectId --format="value(billingEnabled)").Trim()
if ($billingEnabled -ne "True") {
    throw "Billing is not active for $ProjectId. Activate billing, then rerun this script."
}

& $gcloudPath services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --project=$ProjectId

$repositoryName = "projects/$ProjectId/locations/$Region/repositories/$Repository"
& $gcloudPath artifacts repositories describe $Repository --location=$Region --project=$ProjectId --format="value(name)" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $gcloudPath artifacts repositories create $Repository --repository-format=docker --location=$Region --project=$ProjectId
}

$image = "$Region-docker.pkg.dev/$ProjectId/$Repository/document-desk:$Tag"
& $gcloudPath builds submit --project=$ProjectId --tag=$image .
& $gcloudPath run deploy $Service `
    --project=$ProjectId `
    --image=$image `
    --region=$Region `
    --platform=managed `
    --port=8080 `
    --set-env-vars "DEMO_MODE=1,GEMINI_ENABLED=false,RESULTS_SNAPSHOT=results_snapshot.json" `
    --allow-unauthenticated
