import os
import subprocess
from aws_cdk import (
    aws_ec2,
    aws_elasticloadbalancingv2,
    aws_iam,
    aws_logs,
    aws_route53,
    Aws,
    CfnCondition,
    CfnDeletionPolicy,
    CfnMapping,
    CfnOutput,
    CfnParameter,
    Fn,
    Stack,
    Tags,
    Token
)
from constructs import Construct

from oe_patterns_cdk_common.alb import Alb
from oe_patterns_cdk_common.asg import Asg
from oe_patterns_cdk_common.aurora_cluster import AuroraPostgresql
from oe_patterns_cdk_common.db_secret import DbSecret
from oe_patterns_cdk_common.dns import Dns
from oe_patterns_cdk_common.elasticache_cluster import ElasticacheRedis
from oe_patterns_cdk_common.vpc import Vpc

# Begin generated code block
AMI_ID="ami-0e24dac492b7d62c8"
AMI_NAME="ordinary-experts-patterns-zulip-alpha-20220908-0745"
generated_ami_ids = {
    "us-east-1": "ami-0e24dac492b7d62c8"
}
# End generated code block.

if 'TEMPLATE_VERSION' in os.environ:
    template_version = os.environ['TEMPLATE_VERSION']
else:
    try:
        template_version = subprocess.check_output(["git", "describe"]).strip().decode('ascii')
    except:
        template_version = "CICD"


class ZulipStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        ami_mapping={ "AMI": { "OEZULIP": AMI_NAME } }
        for region in generated_ami_ids.keys():
            ami_mapping[region] = { "AMI": generated_ami_ids[region] }
        aws_ami_region_map = CfnMapping(
            self,
            "AWSAMIRegionMap",
            mapping=ami_mapping
        )

        # vpc
        vpc = Vpc(self, "Vpc")

        # db_secret
        db_secret = DbSecret(
            self,
            "DbSecret"
        )

        db = AuroraPostgresql(
            self,
            "Db",
            db_secret=db_secret,
            vpc=vpc
        )

        # redis
        redis = ElasticacheRedis(
            self,
            "Redis",
            vpc=vpc
        )

        # asg
        with open("zulip/launch_config_user_data.sh") as f:
            launch_config_user_data = f.read()
        asg = Asg(
            self,
            "Asg",
            allow_associate_address = True,
            data_volume_size = 100,
            default_instance_type = "t3.xlarge",
            secret_arns=[db_secret.secret_arn()],
            singleton = True, # implied by data_volume_size > 0
            user_data_contents=launch_config_user_data,
            user_data_variables = {},
            vpc=vpc
        )
        asg.asg.node.add_dependency(db.db_primary_instance)
        db.add_asg_ingress(asg)

        redis_ingress = aws_ec2.CfnSecurityGroupIngress(
            self,
            "RedisSgIngress",
            source_security_group_id=asg.sg.ref,
            description="Allow traffic from ASG to Redis",
            from_port=redis.port,
            group_id=redis.elasticache_sg.ref,
            ip_protocol="tcp",
            to_port=redis.port
        )

        alb = Alb(self, "Alb", asg=asg, vpc=vpc)
        asg.asg.target_group_arns = [ alb.target_group.ref ]

        dns = Dns(self, "Dns", alb=alb)

        parameter_groups = alb.metadata_parameter_group()
        parameter_groups += dns.metadata_parameter_group()
        parameter_groups += asg.metadata_parameter_group()
        parameter_groups += vpc.metadata_parameter_group()

        # AWS::CloudFormation::Interface
        self.template_options.metadata = {
            "OE::Patterns::TemplateVersion": template_version,
            "AWS::CloudFormation::Interface": {
                "ParameterGroups": parameter_groups,
                "ParameterLabels": {
                    **alb.metadata_parameter_labels(),
                    **dns.metadata_parameter_labels(),
                    **asg.metadata_parameter_labels(),
                    **vpc.metadata_parameter_labels()
                }
            }
        }
