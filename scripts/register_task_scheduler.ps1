# blog_claude の日次投稿タスクをWindowsタスクスケジューラへ登録する。
#
# money_claude/scripts/register_task_scheduler.ps1 と同様、OSのタスク
# スケジューラ設定を変更する操作のため、Claudeからは実行しない。内容を
# 確認した上で、ご自身の判断でPowerShellから実行してください。
#
#   powershell -ExecutionPolicy Bypass -File scripts\register_task_scheduler.ps1
#
# 毎日17:00（ローカル時刻。マシンがJST設定である前提）に
# scripts\run_daily_post.bat を起動する。run_daily_post.bat が
# python -m scripts.generate_daily_post を実行し、非営業日であれば
# スクリプト自身が即終了する（is_trading_day判定）。

$repoRoot = Split-Path -Parent $PSScriptRoot
$batPath = Join-Path $repoRoot "scripts\run_daily_post.bat"

if (-not (Test-Path $batPath)) {
    throw "run_daily_post.bat が見つかりません: $batPath"
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -WakeToRun `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
$action = New-ScheduledTaskAction -Execute $batPath -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At "17:00"

Register-ScheduledTask `
    -TaskName "blog_claude_daily_post" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "blog_claude: money_claudeのペーパートレード結果から日次記事を生成しGitHub Pagesへ公開する（毎日17:00、非営業日は自動スキップ）" `
    -Force

Write-Host "登録しました。taskschd.msc で 'blog_claude_daily_post' を確認できます。"
Write-Host "MultipleInstances=IgnoreNew のため、前回の実行が終わっていない場合は新しい実行を開始しません。"
