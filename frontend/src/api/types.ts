export interface VerifiedFact { fact_id:string; type:string; value:string; source:string; verified:boolean }
export interface ExternalEvidence { source_ref:string; revision:number; evidence_type:string; speaker:string|null; content:string; metadata:Record<string,unknown>; content_hash:string; created_by:string }
export interface CaseDetail {
  case_id:string; paypal_dispute_id:string; paypal_transaction_id:string|null; dispute_status:string; dispute_reason:string|null;
  dispute_amount:string|null; allowed_response_options:string[]; simulated:boolean; sync_revision:number; evidence_set_revision:number;
  verified_facts:VerifiedFact[]; external_evidence:ExternalEvidence[];
}
export interface GraphNode { node_id:string; node_type:string; title:string; statement:string; source_kind?:string; source_ref?:string; source_revision?:number; source_excerpt?:string; confidence?:number|null }
export interface GraphEdge { edge_id:string; source_node_id:string; target_node_id:string; relation_type:string; rationale?:string|null }
export interface GraphRevision { graph_id:string; case_id:string; revision:number; input_case_revision:number; current_case_revision:number; input_evidence_set_revision:number; current_evidence_set_revision:number; is_stale:boolean; creation_mode:string; created_by:string; content_hash:string; created_at:string; nodes:GraphNode[]; edges:GraphEdge[] }
export interface EvidenceRevision { source_ref:string; revision:number; evidence_type:string; speaker:string|null; content:string; metadata:Record<string,unknown>; content_hash:string; created_by:string; created_at:string }
export interface EvidenceSet { evidence_set_id:string; case_id:string; revision:number; request_id:string; request_hash:string; content_hash:string; created_by:string; created_at:string; members:Array<{ordinal:number;evidence:EvidenceRevision}> }
export interface AIAnalysis { analysis_uid:string; request_id:string; case_id:string; input_case_revision:number; input_evidence_set_revision:number; model_provider:string; model_name:string; prompt_version:string; schema_version:string; schema_hash:string; bundle_hash:string; output_hash:string|null; provider_response_id:string|null; status:string; validation_status:string; graph_id:string|null; output:Record<string,unknown>|null; error:string|null }
export interface SafetyAssessment { safety_uid:string; case_id:string; analysis_uid:string; graph_id:string; policy_version:string; policy_hash:string; safety_status:string; action_risk:string; recommended_action:string; effective_action:string; abstain_required:boolean; report:Record<string,any>; input_case_revision:number; input_evidence_set_revision:number; is_stale:boolean; stale_reason:string|null }
export interface ActionApproval { action_uid:string; action_request_id:string; case_id:string; analysis_uid:string; safety_uid:string; graph_id:string; action_type:string; action_risk:string; approved_by:string; payload:Record<string,unknown>; payload_hash:string; approval_hash:string; execution_status:string; post_action_sync_pending:boolean; approved_at:string }
export interface ActionExecution { action_uid:string; action_request_id:string; case_id:string; action_type:string; execution_status:string; result_status:string; post_action_sync_pending:boolean; paypal_response:Record<string,unknown>; updated_dispute_status:string|null; warning:string|null; last_error:string|null }
export type ActionPayload={action_type:string;[k:string]:unknown}
export interface SupportIntakeRequest{intake_request_id?:string;created_by:string;transcript:Array<{speaker:'customer'|'merchant_agent';message:string}>;merchant_notes?:string|null;attachment_metadata?:Record<string,unknown>|null}
export interface StoredFile { file_uid:string; case_id:string; original_name:string; detected_mime:string; extension:string; size_bytes:number; sha256:string; scan_status:string; created_by:string; created_at:string }
export interface Reconciliation { reconciliation_uid:string; action_uid:string; case_id:string; method:string; outcome:string; observed_snapshot_hash:string|null; details:Record<string,unknown>; reconciled_by:string|null; created_at:string; execution_status:string }
export interface SafetyFinding { code:string; severity:string; message:string; node_id?:string; supporting_node_ids?:string[] }
export interface ExplanationGrounding {
  node_id:string; resolved?:boolean; title?:string; node_type?:string; statement?:string;
  source?:{kind:string;ref:string|null;revision:number|null;excerpt:string|null};
  grounded_in?:Array<Array<{node_id:string;kind:string;ref:string|null;revision:number}>>;
  grounded?:boolean;
}
export interface ReadinessRequirement {
  code:string; label:string; detail:string; critical:boolean;
  status:'present'|'missing'|'unknown'|'contradicted'; how_to_satisfy:string;
}
export interface Readiness {
  reason:string|null; basis:string; coverage:number|null; summary:string;
  requirements:ReadinessRequirement[];
  missing_critical:string[]; contradicted_critical:string[]; unknown_critical:string[];
  can_attach_evidence:boolean; can_supplement:boolean; next_action:string;
}
export interface Explanation {
  case_id:string; analysis_uid:string; graph_id:string; graph_revision:number; safety_uid:string;
  policy_version:string; policy_hash:string;
  reasoning:{provider:string;model:string;summary:string;uncertainties:string[]};
  revisions:{graph_input_case_revision:number;graph_input_evidence_set_revision:number;current_case_revision:number;current_evidence_set_revision:number};
  verdict:{status:string;risk:string;recommended_action:string;effective_action:string;abstain_required:boolean;is_stale:boolean;stale_reason:string|null};
  confidence:{recommendation:number;required_minimum:number};
  grounding:ExplanationGrounding[];
  ungrounded_inferences:string[];
  contradictions:Array<{left:string;right:string;left_title:string|null;right_title:string|null;rationale:string|null;affects_recommendation:boolean}>;
  evidence_gaps:Array<{node_id:string;title:string;statement:string;required_for:string[]}>;
  readiness:Readiness;
  findings:Array<{code:string;severity:string;explanation:string;node_ids:string[]}>;
  next_step:string;
}
