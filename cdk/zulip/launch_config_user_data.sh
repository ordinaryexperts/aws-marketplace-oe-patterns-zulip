#!/bin/bash

echo 'test'
success=$?
cfn-signal --exit-code $success --stack ${AWS::StackName} --resource ZulipAsg --region ${AWS::Region}
