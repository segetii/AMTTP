param(
  [ValidateSet('train','train-data','info','reload')]
  [string]$Task = 'train',
  [string]$DataPath = ''
)

$ErrorActionPreference = 'Stop'

# Ensure venv
if (!(Test-Path -Path ".venv")) {
  python -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
pip install -r automation\requirements.txt | Out-Null

switch ($Task) {
  'train' { python automation\automation_cli.py train }
  'train-data' { if ($DataPath -eq '') { throw 'Provide -DataPath' } ; python automation\automation_cli.py train --data $DataPath }
  'info' { python automation\automation_cli.py info }
  'reload' { python automation\automation_cli.py reload-engine }
}
