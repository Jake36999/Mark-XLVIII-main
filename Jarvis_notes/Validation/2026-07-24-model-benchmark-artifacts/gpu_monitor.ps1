# Cross-vendor GPU monitor -> CSV. Adapted from the owner's Get-Counter script.
# Samples dedicated VRAM (both adapters) + summed engine utilization every 2s.
# LUID map (confirmed 2026-07-24 vs nvidia-smi): 0x..13d4b = GTX 1080 (Nvidia),
# 0x..11b30 = RX 5500 XT (AMD).
param(
    [string]$OutCsv = "F:\Mark-XLVIII-main\Jarvis_notes\Validation\2026-07-24-model-benchmark-artifacts\gpu_samples.csv",
    [int]$IntervalSeconds = 2
)

$luidNames = @{
    "0x00000000_0x00013d4b" = "GTX_1080"
    "0x00000000_0x00011b30" = "RX_5500XT"
}

if (-not (Test-Path $OutCsv)) {
    "timestamp,card,luid,dedicated_mib,util_pct" | Out-File -FilePath $OutCsv -Encoding utf8
}

while ($true) {
    $ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ss.fffZ")

    # Dedicated VRAM per adapter (LUID)
    $mem = Get-Counter "\GPU Adapter Memory(*)\Dedicated Usage" -ErrorAction SilentlyContinue
    $memByLuid = @{}
    if ($mem) {
        foreach ($s in $mem.CounterSamples) {
            $luid = [regex]::Match($s.Path, 'luid_(0x[0-9a-f]+_0x[0-9a-f]+)').Groups[1].Value
            if ($luid) {
                if (-not $memByLuid.ContainsKey($luid)) { $memByLuid[$luid] = 0 }
                $memByLuid[$luid] += $s.CookedValue
            }
        }
    }

    # Summed engine utilization per adapter (LUID)
    $eng = Get-Counter "\GPU Engine(*)\Utilization Percentage" -ErrorAction SilentlyContinue
    $utilByLuid = @{}
    if ($eng) {
        foreach ($s in $eng.CounterSamples) {
            if ($s.CookedValue -gt 0) {
                $luid = [regex]::Match($s.Path, 'luid_(0x[0-9a-f]+_0x[0-9a-f]+)').Groups[1].Value
                if ($luid) {
                    if (-not $utilByLuid.ContainsKey($luid)) { $utilByLuid[$luid] = 0 }
                    $utilByLuid[$luid] += $s.CookedValue
                }
            }
        }
    }

    $allLuids = @($memByLuid.Keys) + @($utilByLuid.Keys) | Sort-Object -Unique
    foreach ($luid in $allLuids) {
        $card = if ($luidNames.ContainsKey($luid)) { $luidNames[$luid] } else { $luid }
        $mib = if ($memByLuid.ContainsKey($luid)) { [math]::Round($memByLuid[$luid] / 1MB, 0) } else { 0 }
        $util = if ($utilByLuid.ContainsKey($luid)) { [math]::Round($utilByLuid[$luid], 1) } else { 0 }
        "$ts,$card,$luid,$mib,$util" | Add-Content -Path $OutCsv -Encoding utf8
    }

    Start-Sleep -Seconds $IntervalSeconds
}
