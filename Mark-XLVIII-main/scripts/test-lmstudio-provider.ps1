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

function Normalize-LmStudioUrl([string]$Url) {
    $Clean = $Url.Trim().TrimEnd("/")
    if ($Clean -notmatch "/v1$") {
        $Clean = "$Clean/v1"
    }
    return $Clean
}

$Config = Read-MarkConfig
$BaseUrl = Normalize-LmStudioUrl (Get-ConfigValue $Config "lmstudio_url" (Get-ConfigValue $Config "llm_url" "http://localhost:1234/v1"))
$Model = Get-ConfigValue $Config "worker_model" (Get-ConfigValue $Config "llm_model" "")

try {
    $Models = Invoke-RestMethod -Method Get -Uri "$BaseUrl/models" -TimeoutSec 10
    $Available = @($Models.data)
    if (-not $Model -and $Available.Count -gt 0 -and ($Available[0].PSObject.Properties.Name -contains "id")) {
        $Model = "$($Available[0].id)"
    }
    if (-not $Model) {
        $Model = "qwen/qwen3-4b"
    }

    $Body = @{
        model = $Model
        messages = @(@{ role = "user"; content = "Reply with exactly: ok" })
        stream = $false
        max_tokens = 16
    } | ConvertTo-Json -Depth 8

    $Response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/chat/completions" -ContentType "application/json" -Body $Body -TimeoutSec 120
    $Text = "$($Response.choices[0].message.content)".Trim()
    if ($Text) {
        Write-Host "[LM Studio] OK ($Model): $Text"
        exit 0
    }
    Write-Host "[LM Studio] Request completed but no text was returned."
    exit 1
}
catch {
    $Message = $_.Exception.Message
    if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
        $Message = $_.ErrorDetails.Message
    }
    Write-Host "[LM Studio] Request failed at $BaseUrl. Start LM Studio API/server mode and load the worker model. $Message"
    exit 1
}
