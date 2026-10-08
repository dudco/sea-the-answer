param([ValidateRange(1, 65535)][int]$Port = 5173)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Open PowerShell as Administrator, then run this script again.'
    exit 1
}
$ruleName = "Haedap-LAN-TCP-$Port"
$existingRule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "Rule already exists: $ruleName. Existing settings were kept."
    $existingRule | Format-Table Name, Enabled, Profile
} else {
    New-NetFirewallRule -Name $ruleName -DisplayName "Haedap LAN TCP $Port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress LocalSubnet -Profile Private,Domain | Out-Null
    Write-Host "Added $ruleName for Private/Domain networks, local subnet only."
}
Write-Host 'Public Wi-Fi is not opened by this rule. Use your trusted private network for sharing.'
Write-Host "To remove this rule: Remove-NetFirewallRule -Name '$ruleName'"
