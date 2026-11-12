import hashlib, json
ACTION_POLICY_VERSION='casegraph_action_policy_v3'
POLICY={'version':ACTION_POLICY_VERSION,'human_approval_required':True,'unknown_outcome_no_retry':True,'fresh_paypal_revalidation':True}
def action_policy_hash()->str: return hashlib.sha256(json.dumps(POLICY,sort_keys=True,separators=(',',':')).encode()).hexdigest()
