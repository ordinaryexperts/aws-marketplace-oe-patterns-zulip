from aws_cdk import core

from oe_patterns_cdk_common import (
    Util,
    Vpc
)

class ZulipStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # vpc
        vpc = Vpc(
            self,
            "Vpc"
        )
