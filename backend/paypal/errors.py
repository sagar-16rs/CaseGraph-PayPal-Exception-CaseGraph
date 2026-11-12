class PayPalError(RuntimeError): pass
class PayPalAPIError(PayPalError):
    def __init__(self,message,status_code=500,body=None): super().__init__(message); self.status_code=status_code; self.body=body or {}
class PayPalTransportError(PayPalError): pass
