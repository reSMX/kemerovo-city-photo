import json
import os
from pathlib import Path
import subprocess
import time
import pytest

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell scheduler')
SCRIPT=Path(__file__).resolve().parents[1]/'retry_after_current.ps1'


def setup_schedule(tmp_path,state='running',stamp='synthetic'):
    (tmp_path/'work').mkdir()
    (tmp_path/'retry_after_current.ps1').write_bytes(SCRIPT.read_bytes())
    (tmp_path/'retry_failed_analysis.ps1').write_text("Set-Content -LiteralPath (Join-Path $PSScriptRoot 'retry-ran.txt') -Value 'synthetic'\nexit 0\n",encoding='utf-8')
    write_state(tmp_path,state,stamp)
    return ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(tmp_path/'retry_after_current.ps1'),'-ExpectedStartedAt','synthetic','-PollSeconds','1']


def write_state(folder,state,stamp='synthetic'):
    path=folder/'work'/'analysis_status.json'
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps({'started_at':stamp,'state':state}),encoding='utf-8')
    temp.replace(path)


@pytest.mark.parametrize('state,stamp,expected,launched',[
    ('completed','synthetic','completed',True),
    ('stopped','synthetic','cancelled',False),
    ('error','synthetic','cancelled',False),
    ('running','different-run','superseded',False),
])
def test_scheduler_only_launches_after_successful_target(tmp_path,state,stamp,expected,launched):
    args=setup_schedule(tmp_path,state,stamp)
    result=subprocess.run(args,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    status=json.loads((tmp_path/'work'/'retry_schedule.json').read_text(encoding='utf-8'))
    assert status['state']==expected
    assert (tmp_path/'retry-ran.txt').exists()==launched


def test_scheduler_waits_and_does_not_allow_duplicate_waiters(tmp_path):
    args=setup_schedule(tmp_path)
    process=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        path=tmp_path/'work'/'retry_schedule.json'
        end=time.monotonic()+8
        while not path.exists() and time.monotonic()<end:time.sleep(.05)
        assert path.exists()
        assert json.loads(path.read_text(encoding='utf-8'))['state']=='waiting'
        assert not (tmp_path/'retry-ran.txt').exists()
        duplicate=subprocess.run(args,capture_output=True,timeout=10)
        assert duplicate.returncode!=0
        assert json.loads(path.read_text(encoding='utf-8'))['state']=='waiting'
        write_state(tmp_path,'completed')
        assert process.wait(timeout=10)==0
        assert (tmp_path/'retry-ran.txt').exists()
    finally:
        if process.poll() is None:process.terminate()
        process.communicate(timeout=5)
