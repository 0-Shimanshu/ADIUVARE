from .base import HardSignal
from .patterns import check_secret
from ..core.models import RequestContext


class CredentialLeakSignal(HardSignal):
    name = "credential_leak"
    action = "block"

    def check(self, ctx: RequestContext) -> bool:
        if not ctx.payload:
            return False

        hit, _, _ = check_secret(str(ctx.payload))
        return hit