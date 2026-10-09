$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$skillRoot = Join-Path $env:USERPROFILE '.codex\skills\nmr-ppt-workflow'
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'skill\SKILL.md') -Destination (Join-Path $skillRoot 'SKILL.md')
@{ project_root = $projectRoot } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $skillRoot 'project.json') -Encoding utf8
Write-Output "Skill 已安装到 $skillRoot"
