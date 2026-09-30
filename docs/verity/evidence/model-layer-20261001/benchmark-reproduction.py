import sys,time,json,statistics,random,hashlib,platform
from pathlib import Path
sys.path.insert(0,'backend')
from app.modules.model_platform.detector_metrics import operating_thresholds
rng=random.Random(764)
rows=[]
for size in [1000,10000,50000]:
 scores=[rng.random() for _ in range(size)]
 labels=[i%3 for i in range(size)]
 times=[]
 for _ in range(5):
  start=time.perf_counter(); thresholds=operating_thresholds(scores,labels); times.append(time.perf_counter()-start)
 rows.append({'examples':size,'seconds':times,'median_seconds':statistics.median(times),'thresholds':thresholds,'input_sha256':hashlib.sha256(json.dumps([scores,labels]).encode()).hexdigest()})
result={'purpose':'TEST_ONLY','benchmark':'calibration_threshold_computation','seed':764,'python':platform.python_version(),'model_inference':False,'model_quality_evidence':False,'runs':rows,'complexity':'O(n log n); thresholds equivalent to prior quadratic reference on seeded tie fixtures'}
Path('docs/verity/evidence/model-layer-20261001/threshold-benchmark.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'runs':len(rows),'largest_median_seconds':rows[-1]['median_seconds'],'quality_claim':False}))
