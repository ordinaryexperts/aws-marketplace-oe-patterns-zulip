#!/usr/bin/env python3

from aws_cdk import core

from zulip.zulip_stack import ZulipStack


app = core.App()
ZulipStack(app, "zulip")

app.synth()
