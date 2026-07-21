$ProgressPreference='SilentlyContinue'
$articles = @("ChatGPT","GPT-3","Artificial_intelligence","OpenAI","Large_language_model","DALL-E","Generative_artificial_intelligence","Machine_learning")
$base = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/all-agents"
$all = @{}
foreach ($a in $articles) {
    $u = "$base/$a/daily/20220601/20231231"
    try {
        $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 30 -Headers @{ "User-Agent" = "amttp-research/1.0" }
        $d = $r.Content | ConvertFrom-Json
        $all[$a] = $d.items
        Write-Host "$a : $($d.items.Count) days"
    } catch { Write-Host "$a ERR: $($_.Exception.Message)" }
}
$json = $all | ConvertTo-Json -Depth 6 -Compress
Set-Content -Path "C:\amttp\data\external_validation\social\wikipedia_pageviews_ai.json" -Value $json -Encoding UTF8
"Saved $((Get-Item C:\amttp\data\external_validation\social\wikipedia_pageviews_ai.json).Length) bytes"
