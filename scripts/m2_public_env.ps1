# Load only public addresses used in PowerShell commands. Forge/Python load secrets
# from .env themselves; private RPC URLs never need to be command-line arguments.
$m2EnvPath = Join-Path $PSScriptRoot '../.env'
if (-not (Test-Path -LiteralPath $m2EnvPath)) { throw 'Create local .env from .env.example first.' }
$m2PublicNames = @('FACTORY_ADDRESS', 'DEMO_OWNER_ADDRESS')
foreach ($m2Line in Get-Content -LiteralPath $m2EnvPath) {
    if ($m2Line -match '^\s*([A-Z_]+)\s*=(.*)$' -and $Matches[1] -in $m2PublicNames) {
        $m2Name = $Matches[1]
        $m2Value = $Matches[2].Trim().Trim('"').Trim("'")
        if ($m2Value -and $m2Value -notmatch '^0x[0-9a-fA-F]{40}$') { throw "Invalid public address: $m2Name" }
        [Environment]::SetEnvironmentVariable($m2Name, $m2Value, 'Process')
    }
}
