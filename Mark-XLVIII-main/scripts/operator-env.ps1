$ErrorActionPreference = "Stop"

$MarkAppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WorkspaceRoot = (Resolve-Path (Join-Path $MarkAppRoot "..")).Path
$AgentBackendRoot = Join-Path $WorkspaceRoot "Agent_backend"
$ToolSetRoot = Join-Path $WorkspaceRoot "ToolSet"

$OperatorRoots = @(
    "F:\quantule_mapper",
    "F:\knowledge_compiler_engine (DAG Engine)",
    "F:\Mark-XLVIII-main",
    "F:\network_management"
)

$env:MARK_OPERATOR_MARK_ROOT = $MarkAppRoot
$env:MARK_OPERATOR_WORKSPACE_ROOT = $WorkspaceRoot
$env:MARK_OPERATOR_AGENT_BACKEND_ROOT = $AgentBackendRoot
$env:MARK_OPERATOR_TOOLSET_ROOT = $ToolSetRoot

$env:ALETHEIA_PROJECT_ROOT = $WorkspaceRoot
$env:ALETHEIA_PROJECT_ID = "mark_operator"
$env:ALETHEIA_ALLOWED_ROOTS = ($OperatorRoots -join ";")
$env:ALETHEIA_STATE_DIR = Join-Path $MarkAppRoot ".aletheia_operator"
$env:ALETHEIA_CHROMA_PATH = Join-Path $env:ALETHEIA_STATE_DIR "chroma"
$env:ALETHEIA_BRIDGE_HOST = "127.0.0.1"
$env:ALETHEIA_BRIDGE_PORT = "8765"
$env:ALETHEIA_ENABLE_ADMIN_BRIDGE = "false"
$env:ALETHEIA_ENABLE_LMSTUDIO_WATCHER = "false"
$env:ALETHEIA_ACTIVE_PARTITION_NULL_POLICY = "allow"
$env:ALETHEIA_SKILL_REGISTRY_ROOT = Join-Path $AgentBackendRoot "backend\agent_backend_skill_registry"

if ($env:LM_API_TOKEN -and -not $env:ALETHEIA_LM_STUDIO_API_TOKEN) {
    $env:ALETHEIA_LM_STUDIO_API_TOKEN = $env:LM_API_TOKEN
}

if (-not $env:ALETHEIA_LM_STUDIO_BASE_URL) {
    $env:ALETHEIA_LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
}

if (-not $env:ALETHEIA_LM_STUDIO_API_BASE_URL) {
    $env:ALETHEIA_LM_STUDIO_API_BASE_URL = "http://127.0.0.1:1234/api/v1"
}

if (-not $env:ALETHEIA_EMBEDDING_MODEL) {
    $env:ALETHEIA_EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5"
}

$env:ALETHEIA_AUTO_LOAD_EMBEDDING_MODEL = "true"

New-Item -ItemType Directory -Force -Path $env:ALETHEIA_STATE_DIR | Out-Null

Write-Host "Mark operator environment ready."
Write-Host "Allowed roots: $env:ALETHEIA_ALLOWED_ROOTS"
Write-Host "Aletheia state: $env:ALETHEIA_STATE_DIR"
