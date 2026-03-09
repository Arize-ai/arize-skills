#Requires -Version 5.1
<#
.SYNOPSIS
    Arize Skills Installer for Windows

.DESCRIPTION
    Installs Arize agent skills into project or global directories.
    PowerShell equivalent of install.sh for Windows machines.

.EXAMPLE
    .\install.ps1 -List
    .\install.ps1 -Project ~/my-app
    .\install.ps1 -Project . -Skill arize-trace
    .\install.ps1 -Global
    .\install.ps1 -Project ~/my-app -Copy
    .\install.ps1 -Project ~/my-app -Uninstall
#>

[CmdletBinding()]
param(
    [string]$Project,
    [switch]$Global,
    [switch]$Copy,
    [switch]$Force,
    [switch]$SkipCli,
    [string[]]$Agent,
    [string[]]$Skill,
    [switch]$Yes,
    [switch]$Uninstall,
    [switch]$List
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$SkillsSrc = Join-Path $ScriptDir "skills"

# --- List mode ---

if ($List) {
    Write-Host "Available skills:"
    Get-ChildItem -Path $SkillsSrc -Directory | ForEach-Object {
        Write-Host "  $($_.Name)"
    }
    exit 0
}

# --- Validate --Skill names ---

if ($Skill.Count -gt 0) {
    foreach ($name in $Skill) {
        $skillPath = Join-Path $SkillsSrc $name
        if (-not (Test-Path $skillPath -PathType Container)) {
            Write-Host "Error: unknown skill '$name'"
            Write-Host ""
            Write-Host "Available skills:"
            Get-ChildItem -Path $SkillsSrc -Directory | ForEach-Object {
                Write-Host "  $($_.Name)"
            }
            exit 1
        }
    }
}

# --- Agent detection ---

function Get-AgentSkillsDir {
    param([string]$AgentName, [string]$Base)
    switch ($AgentName) {
        "cursor" { Join-Path $Base ".cursor\skills" }
        "claude" { Join-Path $Base ".claude\skills" }
        "codex"  { Join-Path $Base ".codex\skills" }
        default  { Join-Path $Base ".$AgentName\skills" }
    }
}

function Find-Agents {
    param([string]$Base)
    $found = @()
    if (Test-Path (Join-Path $Base ".cursor")) { $found += "cursor" }
    if (Test-Path (Join-Path $Base ".claude")) { $found += "claude" }
    if (Test-Path (Join-Path $Base ".codex"))  { $found += "codex" }
    return $found
}

if (-not $Global -and -not $Project) {
    Write-Host "Error: -Project <dir> is required (or use -Global for global install)."
    Write-Host ""
    Write-Host "Usage: .\install.ps1 -Project <dir> [flags]"
    Write-Host "       .\install.ps1 -Global [flags]"
    Write-Host "       .\install.ps1 -List"
    exit 1
}

$Agents = @()

if ($Agent.Count -gt 0) {
    $Agents = $Agent
} elseif ($Global) {
    $Agents = Find-Agents $HOME
} else {
    $resolved = Resolve-Path $Project -ErrorAction SilentlyContinue
    if ($resolved) {
        $Agents = Find-Agents $resolved.Path
    } else {
        $Agents = Find-Agents $Project
    }
}

if ($Agents.Count -eq 0) {
    if (-not $Yes) {
        Write-Host "No agents detected (looked for .cursor/, .claude/, .codex/)."
        Write-Host ""
        Write-Host "Which agent(s) are you using?"
        Write-Host "  1) cursor"
        Write-Host "  2) claude"
        Write-Host "  3) codex"
        Write-Host ""
        $choices = Read-Host "Enter number(s) separated by spaces [1]"
        if (-not $choices) { $choices = "1" }
        foreach ($choice in $choices -split '\s+') {
            switch ($choice) {
                "1" { $Agents += "cursor" }
                "2" { $Agents += "claude" }
                "3" { $Agents += "codex" }
                default { Write-Host "Unknown choice: $choice"; exit 1 }
            }
        }
    } else {
        Write-Host "No agents detected (looked for .cursor/, .claude/, .codex/)."
        Write-Host "Use -Agent <name> to specify manually, e.g.: .\install.ps1 -Agent cursor"
        exit 1
    }
}

# --- Resolve base directory ---

if ($Global) {
    $Base = $HOME
} else {
    $Base = $Project
}

# Resolve to absolute path
if (-not [System.IO.Path]::IsPathRooted($Base)) {
    $Base = Join-Path (Get-Location).Path $Base
}
$Base = [System.IO.Path]::GetFullPath($Base)

Write-Host "Arize Skills Installer"
Write-Host "======================"
Write-Host ""
Write-Host "Detected agents: $($Agents -join ', ')"
if ($Global) {
    Write-Host "Scope: global ($HOME)"
} else {
    Write-Host "Scope: project ($Base)"
}
Write-Host ""

# --- Install or uninstall ---

function Install-Skill {
    param([string]$SkillSrc, [string]$Target)
    $skillName = Split-Path -Leaf $SkillSrc

    if (Test-Path $Target) {
        if ($Force) {
            Remove-Item -Recurse -Force $Target
        } else {
            Write-Host "  Skipped $skillName (already exists, use -Force to overwrite)"
            return
        }
    }

    if ($Copy) {
        Copy-Item -Recurse -Path $SkillSrc -Destination $Target
        Write-Host "  Copied  $skillName -> $Target"
    } else {
        # On Windows, directory symlinks require special handling
        # Try symbolic link first, fall back to directory junction
        try {
            New-Item -ItemType SymbolicLink -Path $Target -Target $SkillSrc -ErrorAction Stop | Out-Null
            Write-Host "  Linked  $skillName -> $Target"
        } catch {
            # Symbolic links may require admin/developer mode on Windows
            # Fall back to directory junction which doesn't require elevation
            try {
                cmd /c mklink /J "$Target" "$SkillSrc" 2>&1 | Out-Null
                Write-Host "  Linked  $skillName -> $Target (junction)"
            } catch {
                Write-Host "  Warning: Could not create symlink for $skillName. Copying instead."
                Copy-Item -Recurse -Path $SkillSrc -Destination $Target
                Write-Host "  Copied  $skillName -> $Target"
            }
        }
    }
}

function Uninstall-Skill {
    param([string]$SkillSrc, [string]$Target)
    $skillName = Split-Path -Leaf $SkillSrc

    if (-not (Test-Path $Target)) { return }

    $item = Get-Item $Target -Force
    $isLink = ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0

    if ($isLink) {
        # Check if this link points to our source
        $linkTarget = $item.Target
        # Junctions use a different format, normalize paths for comparison
        $normalizedSrc = [System.IO.Path]::GetFullPath($SkillSrc)
        if ($linkTarget -and ([System.IO.Path]::GetFullPath($linkTarget) -eq $normalizedSrc)) {
            Remove-Item $Target -Force
            Write-Host "  Removed $skillName ($Target)"
        } else {
            Write-Host "  Skipped $skillName (symlink points elsewhere)"
        }
    } elseif ($item.PSIsContainer) {
        Write-Host "  Skipped $skillName (is a directory, not a symlink from this repo)"
    }
}

# Build list of skills to process
$SkillDirs = @()
if ($Skill.Count -gt 0) {
    foreach ($name in $Skill) {
        $SkillDirs += Join-Path $SkillsSrc $name
    }
} else {
    Get-ChildItem -Path $SkillsSrc -Directory | ForEach-Object {
        $SkillDirs += $_.FullName
    }
}

foreach ($agentName in $Agents) {
    $skillsDir = Get-AgentSkillsDir -AgentName $agentName -Base $Base
    if (-not (Test-Path $skillsDir)) {
        New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
    }
    Write-Host "Agent: $agentName ($skillsDir)"

    foreach ($skillDir in $SkillDirs) {
        if (-not (Test-Path $skillDir -PathType Container)) { continue }
        $target = Join-Path $skillsDir (Split-Path -Leaf $skillDir)

        if ($Uninstall) {
            Uninstall-Skill -SkillSrc $skillDir -Target $target
        } else {
            Install-Skill -SkillSrc $skillDir -Target $target
        }
    }
}

Write-Host ""

if ($Uninstall) {
    Write-Host "Done! Skills uninstalled."
    exit 0
}

# --- Output directory setup ---

if (-not $Global -and $Project) {
    $tracesDir = Join-Path $Base ".arize-tmp-traces"
    if (-not (Test-Path $tracesDir)) {
        New-Item -ItemType Directory -Path $tracesDir -Force | Out-Null
    }

    $gitignore = Join-Path $Base ".gitignore"
    $entry = ".arize-tmp-traces/"
    if (Test-Path $gitignore) {
        $content = Get-Content $gitignore -Raw -ErrorAction SilentlyContinue
        if ($content -notmatch [regex]::Escape($entry)) {
            Add-Content -Path $gitignore -Value $entry
        }
    } else {
        Set-Content -Path $gitignore -Value $entry
    }
    Write-Host "Output directory: $tracesDir (added to .gitignore)"
}

# --- CLI installation ---

function Install-AxCli {
    $installed = $false

    # Try uv
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "Installing ax CLI via uv..."
        uv tool install --force arize-ax-cli
        $installed = $true
    }
    # Try pipx
    elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
        Write-Host "Installing ax CLI via pipx..."
        pipx install --force arize-ax-cli
        $installed = $true
    }
    # Try pip
    elseif (Get-Command pip -ErrorAction SilentlyContinue) {
        Write-Host "Installing ax CLI via pip..."
        try {
            pip install arize-ax-cli 2>$null
            $installed = $true
        } catch {
            pip install --user arize-ax-cli
            $installed = $true
        }
    } else {
        Write-Host "Warning: No Python package manager found (tried uv, pipx, pip)."
        Write-Host "Install ax manually: https://github.com/Arize-ai/arize-ax-cli"
        return $false
    }
    return $installed
}

if (Get-Command ax -ErrorAction SilentlyContinue) {
    $axVersion = try { ax --version 2>$null } catch { "unknown" }
    Write-Host "ax CLI: installed ($axVersion)"
} elseif ($SkipCli) {
    Write-Host "ax CLI: not found (skipped with -SkipCli)"
    Write-Host "  Install manually: pipx install arize-ax-cli"
} else {
    if (Install-AxCli) {
        Write-Host "ax CLI: installed"
    } else {
        Write-Host "ax CLI: installation failed (install manually)"
    }
}

Write-Host ""
if ($Copy) {
    Write-Host "Done! Skills copied into place."
} else {
    Write-Host "Done! Skills are ready to use."
    Write-Host "Keep this directory in place -- skills are symlinked here."
    Write-Host "To make standalone copies instead, re-run with -Copy."
}
