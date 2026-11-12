from __future__ import annotations
from decimal import Decimal
from fastapi import HTTPException
from backend.actions.schemas import *

def _rels(d): return {str(x.get('rel','')).upper().replace('-','_') for x in d.get('links',[]) if isinstance(x,dict)}
def live_action_context(d, action):
    aro=d.get('allowed_response_options') or {}
    return {'dispute_id':d.get('dispute_id') or d.get('id'),'status':d.get('status'),'life_cycle_stage':d.get('dispute_life_cycle_stage'),'action_type':action,'links':sorted(_rels(d)),'allowed_response_options':aro,'dispute_amount':d.get('dispute_amount'),'refund_details':d.get('refund_details'),'seller_response_due_date':d.get('seller_response_due_date')}

def _money(x):
    if not isinstance(x,dict) or x.get('value') is None:return None,None
    return Decimal(str(x['value'])),str(x.get('currency_code') or '')

def validate_action_payload_against_dispute(payload, dispute):
    rel=payload.action_type.lower().replace('_','-')
    rels={str(x.get('rel','')).lower() for x in dispute.get('links',[]) if isinstance(x,dict)}
    mapping={'SEND_MESSAGE':'send-message','MAKE_OFFER':'make-offer','ACCEPT_CLAIM':'accept-claim','PROVIDE_EVIDENCE':'provide-evidence','ESCALATE':'escalate','PROVIDE_SUPPORTING_INFO':'provide-supporting-info','ACKNOWLEDGE_RETURN_ITEM':'acknowledge-return-item','APPEAL':'appeal'}
    expected=mapping[payload.action_type]
    if expected not in rels:
        raise HTTPException(status_code=409,detail=f'PayPal does not currently expose {expected!r} for this dispute')
    aro=dispute.get('allowed_response_options') or {}
    if isinstance(payload,MakeOfferPayload):
        allowed=((aro.get('make_offer') or {}).get('offer_types') or [])
        if allowed and payload.offer_type not in allowed: raise HTTPException(409,'offer type is not allowed by current PayPal state')
        if payload.offer_amount:
            ceiling=(dispute.get('refund_details') or {}).get('allowed_refund_amount') or dispute.get('dispute_amount')
            lim,cur=_money(ceiling); val=Decimal(payload.offer_amount.value)
            if lim is not None and (val>lim or payload.offer_amount.currency_code!=cur): raise HTTPException(422,'offer exceeds current PayPal refund ceiling/currency')
    if isinstance(payload,AcceptClaimPayload):
        allowed=((aro.get('accept_claim') or {}).get('accept_claim_types') or [])
        if allowed and payload.accept_claim_type not in allowed: raise HTTPException(409,'accept-claim type is not allowed')
        if payload.refund_amount:
            ceiling=(dispute.get('refund_details') or {}).get('allowed_refund_amount') or dispute.get('dispute_amount')
            lim,cur=_money(ceiling); val=Decimal(payload.refund_amount.value)
            if lim is not None and (val>lim or payload.refund_amount.currency_code!=cur): raise HTTPException(422,'partial refund exceeds current ceiling/currency')
    if isinstance(payload,AcknowledgeReturnItemPayload):
        allowed=((aro.get('acknowledge_return_item') or {}).get('acknowledgement_types') or [])
        if allowed and payload.acknowledgement_type not in allowed: raise HTTPException(409,'acknowledgement type is not allowed')
    return True
