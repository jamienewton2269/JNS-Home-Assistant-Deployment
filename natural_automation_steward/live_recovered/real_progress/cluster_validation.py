import json,time
from pathlib import Path
from progress import ProgressModel

OUT=Path('/opt/real-progress/dev_cluster_validation.json')
STATS=Path('/opt/real-progress/dev_cluster_stats.json')

model=ProgressModel(
    STATS,
    defaults={
        'VM902 core info':1.7,
        'VM902 registry read':2.8,
        'VM902 config validation':18.0,
        'VM903 core info':2.1,
        'VM903 registry read':3.3,
        'VM903 config validation':20.0,
    },
    stall_multiplier=1.5,
    stall_min_seconds=10.0,
)

exact=[
    ('VM902 core info',1.69),
    ('VM902 registry read',2.81),
    ('VM902 config validation',18.09),
    ('VM903 core info',2.08),
    ('VM903 registry read',3.30),
]
model.learn([{'name':n,'duration':d} for n,d in exact])

# Reconstruct a real cluster job up to the long-running VM903 config check.
t0=1000.0
stages=[]
cursor=t0
for name,dur in exact:
    stages.append({'name':name,'started':cursor,'ended':cursor+dur,'duration':dur})
    cursor+=dur
stages.append({'name':'VM903 config validation','started':cursor})

job={
    'id':'dev-ha-cluster-20261003',
    'status':'running',
    'started':t0,
    'stage':'VM903 config validation',
    'planned_stages':[n for n,_ in exact]+['VM903 config validation'],
    'stages':stages,
}

# We observed at least 31.08s before QGA handed back an async PID.
slow_view=model.view(job,now=cursor+31.08)
assert slow_view['progress']['state']=='stalled', slow_view['progress']
assert slow_view['progress']['eta_seconds'] is None
assert slow_view['progress']['percent'] < 100.0

# Real error case: stopped duplicate VM903 on Node B.
error_job={
    'id':'dev-ha-cluster-error-case',
    'status':'error',
    'started':2000.0,
    'ended':2001.37,
    'stage':'Query stopped duplicate VM903',
    'planned_stages':['Query stopped duplicate VM903'],
    'stages':[{'name':'Query stopped duplicate VM903','started':2000.0,'ended':2001.37,'duration':1.37}],
    'error':'VM 903 is not running',
}
error_view=model.view(error_job,now=2001.37)
assert error_view['progress']['state']=='error'
assert error_view['progress']['percent'] < 100.0

report={
    'validated_at':'2026-10-03',
    'scope':'Development Home Assistant cluster only',
    'nodes':{
        'VM902':{
            'host':'Node B',
            'name':'ha-p0-primary-lite',
            'core_version':'2026.9.4',
            'entities':57,
            'measurements_seconds':{
                'core_info':1.69,
                'registry_read':2.81,
                'config_validation':18.09,
            },
            'config_validation':'passed',
        },
        'VM903':{
            'host':'Node A',
            'name':'ha-s1-plant',
            'core_version':'2026.9.3',
            'latest_available':'2026.9.4',
            'entities':791,
            'measurements_seconds':{
                'core_info':2.08,
                'registry_read':3.30,
                'config_validation_lower_bound':31.08,
            },
            'config_validation':'passed asynchronously; exact total duration not observed',
        },
    },
    'slow_stage_validation':slow_view['progress'],
    'error_case':{
        'target':'stopped duplicate VM903 on Node B',
        'observed_seconds':1.37,
        'observed_error':'VM 903 is not running',
        'progress':error_view['progress'],
    },
    'result':'PASS',
}
OUT.write_text(json.dumps(report,indent=2,sort_keys=True))
print(json.dumps(report,indent=2))
print('\nVALIDATION PASS')
