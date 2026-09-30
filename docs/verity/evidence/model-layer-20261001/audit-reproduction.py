from pathlib import Path
import hashlib,json,subprocess,urllib.request
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
root=Path.cwd()
out=root/'docs/verity/evidence/model-layer-20261001'
research=root/'docs/verity/evidence/commercial-production-20260930/rights-research'
def sha(path): return hashlib.file_digest(path.open('rb'),'sha256').hexdigest()
def save(name,data): (out/name).write_text(json.dumps(data,indent=2)+'\n')
selected={'Qwen/Qwen3-4B-Instruct-2507','HuggingFaceTB/SmolLM3-3B','Qwen/Qwen3-Embedding-0.6B'}
def inspect(item):
    path=research/item['dossier']; dossier=json.loads(path.read_bytes())
    files=[]
    for name,entry in dossier['local_metadata'].items():
        local=path.parent/name
        files.append({'path':str(local),'sha256':sha(local),'expected_sha256':entry['sha256'],'match':sha(local)==entry['sha256'],'source':entry['source']})
    result={**item,'evidence_path':str(path),'evidence_sha256':sha(path),'declared_license':dossier['declared_license'],'verified_local_metadata':files,'payload_inventory':dossier['unverified_payload_inventory'],'production_admission':'BLOCKED','commercial_review':'NOT FOUND','weight_bytes_locally_verified':False,'tokenizer_payload_locally_verified':False}
    if item['repository'] in selected:
        license_entry=next((e for n,e in dossier['local_metadata'].items() if n.startswith('LICENSE')),None)
        if license_entry:
            try:
                req=urllib.request.Request(license_entry['source'],headers={'User-Agent':'Azaeron-metadata-audit/1'})
                with urllib.request.urlopen(req,timeout=20) as response: data=response.read(2*1024**2+1)
                if len(data)>2*1024**2: raise ValueError('metadata_limit')
                actual=hashlib.sha256(data).hexdigest()
                result['current_primary_license_check']={'source':license_entry['source'],'sha256':actual,'matches_captured':actual==license_entry['sha256']}
            except Exception as e: result['current_primary_license_check']={'status':'BLOCKED','reason':type(e).__name__}
    return result
items=json.loads((research/'index.json').read_bytes())
with ThreadPoolExecutor(max_workers=3) as pool:
    inspected=list(pool.map(inspect,items))
save('candidate-admission.json',{'status':'BLOCKED','selected_for_review':[x for x in inspected if x['repository'] in selected],'admitted':0,'note':'License metadata verification is not legal approval, weight verification, training or model ownership.'})
save('dataset-rights-admission.json',{'status':'BLOCKED','approved':0,'datasets':[x for x in inspected if x['repository'] in {'databricks/databricks-dolly-15k','OpenAssistant/oasst1','HuggingFaceH4/no_robots','allenai/Dolci-Instruct-SFT'}],'unknown_rights':'REJECT'})
ci=root/'.verity-local/hosted-6632f2b-evidence/verity-gate-evidence/docs/verity/evidence/ci'
scans=[]
for p in sorted((ci/'images').glob('*-vulnerabilities.json')):
    report=json.loads(p.read_bytes()); findings=[v for r in report.get('Results',[]) for v in r.get('Vulnerabilities',[])]
    scans.append({'path':str(p),'sha256':sha(p),'reported_findings':len(findings),'high':sum(v['Severity']=='HIGH' for v in findings),'critical':sum(v['Severity']=='CRITICAL' for v in findings)})
registries={}
for p in ['config/models/registry.json','config/model-platform/candidates.json','config/model-platform/datasets.json']:
    file=root/p
    registries[p]={'sha256':sha(file),'contents':json.loads(file.read_bytes())}
save('repo-truth.json',{'captured_at':datetime.now(timezone.utc).isoformat(),'review_head':subprocess.check_output(['git','rev-parse','codex/private-agent-core-20260929'],text=True).strip(),'normal_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'normal_index_tree':subprocess.check_output(['git','write-tree'],text=True).strip(),'registries':registries,'prior_ci':json.loads((out/'prior-ci.json').read_bytes()),'prior_images':scans,'current_patch_ci':'NOT_RUN','external_ai_apis_used':False,'approved_models':0,'rights_discovery_scope':'Repository registries, immutable rights dossiers and previously inventoried local caches; no customer documents or secret files read.','audit_script_sha256':sha(Path(__file__))})
print(json.dumps({'candidate_admission':'BLOCKED','dataset_admission':'BLOCKED','approved_models':0,'prior_image_reports':len(scans)}))
