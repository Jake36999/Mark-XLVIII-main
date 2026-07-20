$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ConfigPath = Join-Path $Root "config\api_keys.json"

function Read-MarkConfig {
    if (Test-Path -LiteralPath $ConfigPath) {
        return Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    }
    return [pscustomobject]@{}
}

function Get-ConfigValue($Config, [string]$Name, [string]$Default = "") {
    if ($Config.PSObject.Properties.Name -contains $Name) {
        $Value = $Config.$Name
        if ($null -ne $Value -and "$Value".Trim()) {
            return "$Value"
        }
    }
    return $Default
}

$Config = Read-MarkConfig
$ApiKey = $env:OPENAI_API_KEY
if (-not $ApiKey) {
    $ApiKey = Get-ConfigValue $Config "openai_api_key"
}

if (-not $ApiKey) {
    Write-Host "[OpenAI] No API key configured. Set OPENAI_API_KEY or config/api_keys.json: openai_api_key."
    exit 2
}

$Model = Get-ConfigValue $Config "planner_model" "gpt-5.5"
$BaseUrl = (Get-ConfigValue $Config "openai_url" "https://api.openai.com/v1").TrimEnd("/")
$Uri = "$BaseUrl/responses"

$Headers = @{
    "Authorization" = "Bearer $ApiKey"
    "Content-Type" = "application/json"
}

$Body = @{
    model = $Model
    input = "Reply with exactly: ok"
} | ConvertTo-Json -Depth 8

try {
    $Response = Invoke-RestMethod -Method Post -Uri $Uri -Headers $Headers -Body $Body -TimeoutSec 60
    $Text = ""
    if ($Response.PSObject.Properties.Name -contains "output_text") {
        $Text = "$($Response.output_text)".Trim()
    }
    if (-not $Text -and ($Response.PSObject.Properties.Name -contains "output")) {
        $Text = (($Response.output | ForEach-Object {
            $_.content | ForEach-Object { $_.text }
        }) -join "`n").Trim()
    }
    if ($Text) {
        Write-Host "[OpenAI] OK: $Text"
        exit 0
    }
    Write-Host "[OpenAI] Request completed but no text was returned."
    exit 1
}
catch {
    $Message = $_.Exception.Message
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        $Message = $_.ErrorDetails.Message
    }
    Write-Host "[OpenAI] Request failed: $Message"
    exit 1
}
