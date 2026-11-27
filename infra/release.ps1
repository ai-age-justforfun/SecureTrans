# ============================================================
# SecureTrans Gitea Release 发布脚本（每次发布用）
# 用法: powershell -ExecutionPolicy Bypass -File infra/release.ps1 -Version v1.5.0
# 前置: 1) main 已推送最新代码（不强制预先 push tag；脚本 POST 创建 release 时 Gitea 会自动打 tag）
#       2) packages/ 下已有 securetrans-<ver>.tar.gz（先跑 infra/package.sh <ver>）
#       2) packages/ 下已有 securetrans-<ver>.tar.gz（先跑 infra/package.sh <ver>）
# 说明: 从 git remote 提取 Gitea token（不打印），创建 release 并上传资产
# ============================================================
param([string]$Version = "v1.5.0")

$ErrorActionPreference = "Stop"

$repo = "opencodegit/SecureTrans"
# Gitea 地址支持环境变量 GITEA_BASE 覆盖（默认 http://localhost:3000）
$giteaBase = $env:GITEA_BASE
if (-not $giteaBase) { $giteaBase = "http://localhost:3000" }
$base = "$giteaBase/api/v1"
$tag = $Version

# 项目根目录（脚本位于 infra/ 下）
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projRoot = Split-Path -Parent $scriptDir
$pkgDir = Join-Path $projRoot "packages"

$remote = git remote get-url origin
$m = [regex]::Match($remote, 'http://([^@]+)@')
$cred = $m.Groups[1].Value   # user:token
$token = ($cred -split ':', 2)[1]
if (-not $token) { Write-Error "无法从 git remote 提取 Gitea token"; exit 1 }
$headers = @{ Authorization = "token $token" }

# 1. 检查/创建 release
Write-Host "=== 发布 $tag ==="
try {
    $existing = Invoke-RestMethod -Uri "$base/repos/$repo/releases/tags/$tag" -Headers $headers -Method Get
    Write-Host "Release $tag 已存在，id=$($existing.id)"
    $releaseId = $existing.id
} catch {
    $body = @{
        tag_name = $tag
        target_commitish = "main"
        name = $tag
        body = "SecureTrans 发布 $tag"
        draft = $false
        prerelease = $false
    } | ConvertTo-Json
    try {
        $r = Invoke-RestMethod -Uri "$base/repos/$repo/releases" -Headers $headers -Method Post -ContentType "application/json; charset=utf-8" -Body $body
        Write-Host "Release $tag 创建成功，id=$($r.id)"
        $releaseId = $r.id
    } catch {
        # Gitea 为已推送的 tag 自动建占位记录（is_tag=1，API 不可见），POST 撞 UNIQUE 唯一约束
        # 处理：删除远程 tag（释放占位）后重试 POST（Gitea 会自动重建 tag 并关联本 release）
        Write-Host "POST 创建失败（可能 tag 占位已存在），删除远程 tag $tag 后重试..."
        git push origin ":refs/tags/$tag" 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        $r = Invoke-RestMethod -Uri "$base/repos/$repo/releases" -Headers $headers -Method Post -ContentType "application/json; charset=utf-8" -Body $body
        Write-Host "Release $tag 创建成功（重试），id=$($r.id)"
        $releaseId = $r.id
    }
}

# 2. 上传资产（packages/ 下所有 tar.gz + md5 + sha256）
# v2.4.0 修复：Filter *.tar.gz 只选压缩包，.md5/.sha256 校验文件漏传 → CD 下载校验步骤取不到 MD5_URL 失败
$matchTag = $tag.TrimStart('v')
$assets = @(
    (Get-ChildItem "$pkgDir" -Filter "*.tar.gz" | Where-Object { $_.Name -like "securetrans-${matchTag}*" -or $_.Name -eq "securetrans-offline-deps.tar.gz" })
    (Get-ChildItem "$pkgDir" -Filter "*.md5" | Where-Object { $_.Name -like "securetrans-${matchTag}*" })
    (Get-ChildItem "$pkgDir" -Filter "*.sha256" | Where-Object { $_.Name -like "securetrans-${matchTag}*" })
) | Where-Object { $_ }
# 若无匹配资产，不自动上传（避免误传旧版本包）
foreach ($a in $assets) {
    $name = $a.Name
    $existingAssets = Invoke-RestMethod -Uri "$base/repos/$repo/releases/$releaseId/assets" -Headers $headers -Method Get
    if ($existingAssets | Where-Object { $_.name -eq $name }) {
        Write-Host "资产 $name 已存在，跳过"
        continue
    }
    Write-Host "上传资产: $name ..."
    $out = & curl.exe -s -X POST -H "Authorization: token $token" `
        -F "attachment=@$($a.FullName)" `
        "$base/repos/$repo/releases/$releaseId/assets?name=$name"
    Write-Host $out.Substring(0, [Math]::Min(150, $out.Length))
}

# 3. 汇总
$rel = Invoke-RestMethod -Uri "$base/repos/$repo/releases/tags/$tag" -Headers $headers -Method Get
Write-Host "=== 发布完成 ==="
Write-Host "Release URL: $($rel.html_url)"
$rel.assets | ForEach-Object { Write-Host "  资产: $($_.name) ($($_.size) bytes)" }
